import asyncio
import json
import logging
import random
import re
from difflib import SequenceMatcher
import requests
from sqlalchemy import select
from types import SimpleNamespace
from controllers.NLPController import NLPController
from models.db_schemes.minirag.schemes.quiz import Quiz

LETTERS = ("A", "B", "C", "D")
MAX_ATTEMPTS = 3          # attempts per question
MAX_CHUNK_CHARS = 1500    
DUPLICATE_THRESHOLD = 0.90
GROUNDING_MIN = 0.25

CHARS_PER_QUESTION = 300     # tokens per q 
MIN_CHUNK_CHARS = 60  # dispoint a mini chunks 

logger = logging.getLogger(__name__)

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "enum": ["A", "B", "C", "D"],
            "description": "The letter of the correct option",
        }
    },
    "required": ["answer"],
    "additionalProperties": False,
}


class DuplicateQuestionError(ValueError):
    """Raised when the model repeats a question already accepted for this quiz."""

class InsufficientMaterialError(ValueError):
    """Raised when the model says the passage has nothing to ask about."""

class QuizController:
    def __init__(
        self,
        db_client,
        vectordb_client,
        generation_client,
        embedding_client,
        template_parser,
    ):
        self.db_client = db_client
        self.nlp_controller = NLPController(
            vectordb_client=vectordb_client,
            generation_client=generation_client,
            embedding_client=embedding_client,
            template_parser=template_parser,
        )
        self.generation_client = generation_client

    # ---------- parsing / validation (one question at a time) ----------
    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\W+", " ", text.lower()).strip()

    def _parse_question(self, raw_response: str, previous: list[str]) -> dict:
        if not isinstance(raw_response, str):
            raise ValueError("The AI response is not text.")

        raw = re.sub(
            r"^\s*```(?:json)?\s*|\s*```\s*$",
            "",
            raw_response.strip(),
            flags=re.IGNORECASE,
        ).strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)

            if not match:
                raise ValueError("The AI did not return valid JSON.")
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError("The AI did not return valid JSON.") from exc

        if not isinstance(data, dict):
            raise ValueError("The AI response must be a JSON object.")
        
        if data.get("insufficient") is True:
            raise InsufficientMaterialError("Not enough material in this passage.")

        question_text = data.get("question")
        options = data.get("options")
        correct_answer = data.get("correct_answer")
        explanation = data.get("explanation")

        evidence = data.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("Missing evidence.")

        if not isinstance(question_text, str) or not question_text.strip():
            raise ValueError("Missing question text.")
        if not isinstance(options, dict) or set(options.keys()) != set(LETTERS):
            raise ValueError("Options must be exactly A, B, C and D.")
        if any(not isinstance(value, str) or not value.strip() for value in options.values()):
            raise ValueError("An option is empty.")
        if correct_answer not in LETTERS:
            raise ValueError("Invalid correct answer.")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError("Missing explanation.")

        normalized_options = {self._normalize(value) for value in options.values()}
        if len(normalized_options) != 4:
            raise ValueError("Options are not distinct.")

        normalized_question = self._normalize(question_text)
        for previous_question in previous:
            ratio = SequenceMatcher(
                None,
                normalized_question,
                self._normalize(previous_question),
            ).ratio()
            if ratio >= DUPLICATE_THRESHOLD:
                raise DuplicateQuestionError("Duplicate question.")

        texts = [options[key].strip() for key in LETTERS]
        correct_index = LETTERS.index(correct_answer)
        order = list(range(4))
        random.shuffle(order)
        shuffled = {LETTERS[i]: texts[old] for i, old in enumerate(order)}
        new_correct = LETTERS[order.index(correct_index)]

        return {
            "question": question_text.strip(),
            "options": shuffled,
            "correct_answer": new_correct,
            "evidence": evidence.strip(),
            "explanation": explanation.strip(),

        }

    @staticmethod
    def _pick_diverse_chunks(texts: list[str], max_similarity: float = 0.5) -> list[str]:
        """Drop chunks whose content mostly overlaps an already picked chunk."""
        picked: list[str] = []
        picked_tokens: list[set[str]] = []
        for text in texts:
            tokens = set(re.findall(r"\w{4,}", text.lower()))
            if not tokens:
                continue
            if any(len(tokens & t) / len(tokens | t) >= max_similarity for t in picked_tokens):
                continue
            picked.append(text)
            picked_tokens.append(tokens)
        return picked

    def _is_grounded(self, question: dict, chunk: str) -> bool:
        words = set(re.findall(r"\w{4,}", question["explanation"].lower()))
        if not words:
            return True
        chunk_words = set(re.findall(r"\w{4,}", chunk.lower()))
        return len(words & chunk_words) / len(words) >= GROUNDING_MIN

    async def _verify(self, question: dict, chunk: str) -> bool:
        """Solve the question from the passage alone; the answer key must match."""
        options = "\n".join(
            f"{key}. {value}" for key, value in question["options"].items()
        )
        prompt = (
            "Answer using ONLY the passage.\n\n"
            f"Passage:\n{chunk}\n\n"
            f"Question: {question['question']}\n{options}\n\n"
            "Return a JSON object with a single field 'answer' containing the letter "
            "of the correct option (A, B, C, or D)."
        )
        raw = await asyncio.to_thread(
            self.generation_client.generate_text,
            prompt=prompt,
            chat_history=[],
            max_output_tokens=20,
            temperature=0.0,
            response_format="json",
        )

        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return False
        return isinstance(result, dict) and result.get("answer") == question["correct_answer"]

    @staticmethod
    def _public_questions(questions: list[dict]) -> list[dict]:
        """Never expose the answer key before submission."""
        return [
            {
                "id": question["id"],
                "question": question["question"],
                "options": question["options"],
            }
            for question in questions
        ]

    @staticmethod
    def _build_prompt(
        chunk: str,
        difficulty: str,
        previous: list[str],
    ) -> str:
        avoid = ""
        if previous:
            listed = "\n".join(f"- {q}" for q in previous)
            avoid = (
                "\nDo not repeat or rephrase these questions:\n"
                f"{listed}\n"
            )

        return f"""Create exactly ONE multiple-choice question.
Difficulty: {difficulty}

Use ONLY the study material below.
Return exactly one JSON object with this structure:
{{
  "question": "Question text",
  "options": {{
    "A": "First option",
    "B": "Second option",
    "C": "Third option",
    "D": "Fourth option"
  }},
  "correct_answer": "A",
  "evidence": "One sentence copied word-for-word from the material that proves the answer",
  "explanation": "Why A is correct based on the material"
}}

Rules:
- Output JSON only, without Markdown or extra text.
- Include exactly four non-empty options: A, B, C, D.
- All four options must be different.
- correct_answer must be A, B, C, or D.
- Only one option can be correct.
- "evidence" must be copied exactly from the study material, without changing any word.
- Ask ONLY about facts explicitly written in the study material.
- Every name, label, or number used in the question must appear in the study material. Never invent examples, node names, or values.
- The explanation must be supported by the material.
- Do not invent facts absent from the material.
- Do not mention "the passage" or "the text" in the question.
- If the material has no clear fact to ask about, return exactly {{"insufficient": true}} and nothing else.
{avoid}

Study material:
{chunk}
"""
    # ---------- quiz generation ----------
    async def generate_quiz(
        self,
        project,
        card_id: int,
        question_count: int = 5,
        difficulty: str = "medium",
        
        verify_answers: bool = True,
        topic: str | None = None,
        source_text=None,
        use_documents=True,
    ) -> dict:
        if not isinstance(question_count, int) or isinstance(question_count, bool):
            raise ValueError("question_count must be an integer.")
        if not 1 <= question_count <= 20:
            raise ValueError("question_count must be between 1 and 20.")
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError("difficulty must be easy, medium, or hard.")
        

        search_query = (
            topic.strip()
            if topic and topic.strip()
            else (
                "main concepts, definitions, examples, and important "
                "relationships in the uploaded study material"
            )
        )

        pdf_docs = []
        if use_documents:
            retrieved_documents = await self.nlp_controller.search_vector_db_collection(
                project=project,
                text=search_query,
                limit=max(question_count * 6, 30),
                card_id=card_id,
            )
            if isinstance(retrieved_documents, list):
                pdf_docs = retrieved_documents

        image_docs = (
            self._source_text_to_documents(source_text)
            if source_text and source_text.strip()
            else []
        )

        pdf_docs = []
        if use_documents:
            retrieved = await self.nlp_controller.search_vector_db_collection(
                project=project,
                text=search_query,
                limit=max(question_count * 6, 30),
                card_id=card_id,
            )
            if isinstance(retrieved, list):
                pdf_docs = retrieved

        image_docs = (
            self._source_text_to_documents(source_text)
            if source_text and source_text.strip()
            else []
        )

        documents = []
        for i in range(max(len(image_docs), len(pdf_docs))):
            if i < len(image_docs):
                documents.append(image_docs[i])
            if i < len(pdf_docs):
                documents.append(pdf_docs[i])

        if not documents:
            raise LookupError(
                "No indexed study material was found for this project."
            )
        texts = [
            document.text.strip()
            for document in documents
            if isinstance(getattr(document, "text", None), str)
            and document.text.strip()
        ]

        chunks = self._pick_diverse_chunks(texts)

        if not chunks:
            raise LookupError(
                "No usable study material was found for this project."
            )

        # Skip tiny fragments, but never end up with nothing.
        chunks = [c for c in chunks if len(c) >= MIN_CHUNK_CHARS] or chunks
        logger.info("quiz chunks: pdf=%d image=%d total=%d", len(pdf_docs), len(image_docs), len(chunks))
        # The number of questions follows the amount of material.
        total_chars = sum(min(len(c), MAX_CHUNK_CHARS) for c in chunks)
        max_by_material = max(1, total_chars // CHARS_PER_QUESTION)
        target_count = min(question_count, max_by_material, len(chunks))

        chat_history = [
            self.generation_client.construct_prompt(
                prompt=(
                    "You are a careful educational quiz writer. "
                    "Return only JSON that follows the requested schema."
                ),
                role=self.generation_client.enums.SYSTEM.value,
            )
        ]
        questions: list[dict] = []
        last_error: Exception | None = None

        for chunk_index, raw_chunk in enumerate(chunks):
            if len(questions) >= target_count:
                break

            chunk = raw_chunk[:MAX_CHUNK_CHARS]
            for attempt in range(MAX_ATTEMPTS):
                previous = [question["question"] for question in questions]
                prompt = self._build_prompt(chunk, difficulty, previous)
                try:
                    raw_response = await asyncio.to_thread(
                        self.generation_client.generate_text,
                        prompt=prompt,
                        chat_history=list(chat_history),
                        max_output_tokens=700,
                        temperature=0.2 + 0.2 * attempt,
                        response_format="json",
                    )

                    question = self._parse_question(raw_response, previous)

                    if not self._is_grounded(question, chunk):
                        raise ValueError("Explanation is not grounded in the passage.")

                    evidence_norm = self._normalize(question["evidence"])
                    if len(evidence_norm) < 15 or evidence_norm not in self._normalize(chunk):
                        raise ValueError("Evidence is not in the passage.")

                    if verify_answers:
                        if not await self._verify(question, chunk):
                            raise ValueError("Answer key failed verification.")

                except InsufficientMaterialError as exc:
                    # Retrying a passage the model called too thin won't help.
                    last_error = exc
                    logger.info(
                        "Quiz chunk skipped | chunk=%s | reason=%s",
                        chunk_index,
                        exc,
                    )
                    break
                except DuplicateQuestionError as exc:
                    # Retrying the same passage often produces the same duplicate.
                    # Abandon this passage and let the outer loop try another chunk.
                    last_error = exc
                    logger.warning(
                        "Quiz duplicate rejected | chunk=%s | reason=%s",
                        chunk_index,
                        exc,
                    )
                    break
                except (ValueError, json.JSONDecodeError) as exc:
                    last_error = exc
                    logger.warning(
                        "Quiz validation failed | chunk=%s | attempt=%s | reason=%s",
                        chunk_index,
                        attempt + 1,
                        exc,
                    )
                    continue
                except requests.exceptions.RequestException as exc:
                    last_error = exc
                    logger.warning(
                        "Quiz generation request failed | chunk=%s | attempt=%s | reason=%s",
                        chunk_index,
                        attempt + 1,
                        exc,
                    )
                    if attempt < MAX_ATTEMPTS - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue

                # Append only after generation, validation, grounding, evidence and verification pass.
                question["id"] = f"q{len(questions) + 1}"
                questions.append(question)
                break

        if not questions:
            raise RuntimeError(f"Could not generate any valid questions: {last_error}")
        if len(questions) < target_count:
            logger.warning(
                "Returning %d of %d questions. Last error: %s",
                len(questions), target_count, last_error,
            )

        async with self.db_client() as session:
            quiz = Quiz(
                project_id=project.project_id,
                card_id=card_id,
                questions=questions,  # full version (with answers)
            )
            session.add(quiz)
            await session.commit()
            await session.refresh(quiz)

        return {
            "quiz_id": quiz.quiz_id,
            "project_id": quiz.project_id,
            "question_count": len(questions),
            "difficulty": difficulty,
            "questions": self._public_questions(questions),  # safe version
        }

    async def check_answer(
        self,
        project_id: int,
        quiz_id: int,
        question_id: str,
        answer: str,
    ) -> dict | None:
        if answer not in LETTERS:
            raise ValueError("Answer must be A, B, C, or D.")

        async with self.db_client() as session:
            result = await session.execute(
                select(Quiz).where(
                    Quiz.quiz_id == quiz_id,
                    Quiz.project_id == project_id,
                )
            )
            quiz = result.scalar_one_or_none()

            if quiz is None:
                return None

            question = next(
                (item for item in quiz.questions if item.get("id") == question_id),
                None,
            )
            if question is None:
                raise ValueError("Question does not belong to this quiz.")

            return {
                "question_id": question_id,
                "is_correct": answer == question["correct_answer"],
                "correct_answer": question["correct_answer"],
                "explanation": question["explanation"],
            }

    async def submit_answers(
        self,
        project_id: int,
        quiz_id: int,
        answers: dict,
    ) -> dict | None:
        if not isinstance(answers, dict) or not answers:
            raise ValueError("answers must be a non-empty object.")

        for letter in answers.values():
            if letter not in LETTERS:
                raise ValueError("Answers must be A, B, C, or D.")

        async with self.db_client() as session:
            result = await session.execute(
                select(Quiz).where(
                    Quiz.quiz_id == quiz_id,
                    Quiz.project_id == project_id,
                )
            )
            quiz = result.scalar_one_or_none()

            if quiz is None:
                return None

            valid_ids = {q["id"] for q in quiz.questions}
            if not set(answers).issubset(valid_ids):
                raise ValueError("Some question ids do not belong to this quiz.")

            details = []
            score = 0
            for q in quiz.questions:
                given = answers.get(q["id"])
                is_correct = given == q["correct_answer"]
                score += int(is_correct)
                details.append({
                    "question_id": q["id"],
                    "your_answer": given,
                    "is_correct": is_correct,
                    "correct_answer": q["correct_answer"],
                    "explanation": q["explanation"],
                })

            return {
                "quiz_id": quiz_id,
                "score": score,
                "total": len(quiz.questions),
                "details": details,
            }

    @staticmethod
    def _source_text_to_documents(source_text: str) -> list:
        text = re.sub(r"\s+", " ", source_text or "").strip()

        if not text:
            return []
        
        # Prefer sentence boundaries to preserve complete ideas.
        parts = [
            part.strip()
            for part in re.split(r"(?<=[.!?؟])\s+", text)
            if part.strip()
        ]

        # If there are no sentence boundaries, split into bounded chunks.
        if len(parts) <= 1:
            chunk_size = 700
            overlap = 100
            parts = [
                text[start:start + chunk_size].strip()
                for start in range(0, len(text), chunk_size - overlap)
                if text[start:start + chunk_size].strip()
            ]

        return [
            SimpleNamespace(text=part)
            for part in parts
        ]