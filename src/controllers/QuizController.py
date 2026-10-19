import asyncio
import json
import logging
import random
import re
from difflib import SequenceMatcher

import requests
from sqlalchemy import select

from controllers.NLPController import NLPController
from models.db_schemes.minirag.schemes.quiz import Quiz

LETTERS = ("A", "B", "C", "D")
MAX_ATTEMPTS = 3          # attempts per question
MAX_CHUNK_CHARS = 1000    # keep the prompt small for a 2b model
DUPLICATE_THRESHOLD = 0.92
GROUNDING_MIN = 0.25

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
            match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if not match:
                raise ValueError("The AI did not return valid JSON.")
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError("The AI did not return valid JSON.") from exc

        if not isinstance(data, dict):
            raise ValueError("The AI response must be a JSON object.")

        question_text = data.get("question")
        options = data.get("options")
        correct_answer = data.get("correct_answer")
        explanation = data.get("explanation")

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
  "explanation": "Why A is correct based on the material"
}}

Rules:
- Output JSON only, without Markdown or extra text.
- Include exactly four non-empty options: A, B, C, D.
- All four options must be different.
- correct_answer must be A, B, C, or D.
- Only one option can be correct.
- The explanation must be supported by the material.
- Do not invent facts absent from the material.
- Do not mention "the passage" or "the text" in the question.
{avoid}

Study material:
{chunk}
"""
    # ---------- quiz generation ----------
    async def generate_quiz(
        self,
        project,
        question_count: int = 5,
        difficulty: str = "medium",
        topic: str | None = None,
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
        documents = await self.nlp_controller.search_vector_db_collection(
            project=project,
            text=search_query,
            # Retrieve a larger candidate pool so failed/duplicate chunks have fallbacks.
            limit=max(question_count * 6, 30),
        )
        if not isinstance(documents, list) or not documents:
            raise LookupError("No indexed study material was found for this project.")

        # Keep chunks whose CONTENT is distinct (overlapping chunks give duplicate questions).
        texts = [
            doc.text.strip()
            for doc in documents
            if isinstance(getattr(doc, "text", None), str) and doc.text.strip()
        ]
        chunks = self._pick_diverse_chunks(texts)
        logger.warning(
            "Quiz chunks: %d retrieved, %d distinct, %d questions requested",
            len(texts), len(chunks), question_count,
        )

        if not chunks:
            raise LookupError("The retrieved study material is empty.")

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
            if len(questions) >= question_count:
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
                    if not await self._verify(question, chunk):
                        raise ValueError("Answer key failed verification.")
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

                # Append only after generation, validation, grounding, and verification pass.
                question["id"] = f"q{len(questions) + 1}"
                questions.append(question)
                break

        if not questions:
            raise RuntimeError(f"Could not generate any valid questions: {last_error}")
        if len(questions) < question_count:
            logger.warning(
                "Returning %d of %d questions. Last error: %s",
                len(questions), question_count, last_error,
            )

        async with self.db_client() as session:
            quiz = Quiz(
                project_id=project.project_id,
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
        quiz_id: int,
        question_id: str,
        answer: str,
    ) -> dict | None:
        if answer not in LETTERS:
            raise ValueError("Answer must be A, B, C, or D.")

        async with self.db_client() as session:
            result = await session.execute(
                select(Quiz).where(Quiz.quiz_id == quiz_id)
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

    async def submit_answers(self, quiz_id: int, answers: dict) -> dict | None:
        async with self.db_client() as session:
            result = await session.execute(
                select(Quiz).where(Quiz.quiz_id == quiz_id)
            )
            quiz = result.scalar_one_or_none()
            if quiz is None:
                return None

            questions = quiz.questions
            if not isinstance(answers, dict):
                raise ValueError("Answers must be a JSON object.")

            question_ids = {question["id"] for question in questions}
            unknown_ids = set(answers.keys()) - question_ids
            if unknown_ids:
                raise ValueError("Answers contain unknown question IDs.")

            results = []
            score = 0
            for question in questions:
                question_id = question["id"]
                selected = answers.get(question_id)
                correct = question["correct_answer"]
                is_correct = selected == correct
                if is_correct:
                    score += 1
                results.append(
                    {
                        "question_id": question_id,
                        "selected_answer": selected,
                        "correct_answer": correct,
                        "explanation": question["explanation"],
                        "is_correct": is_correct,
                    }
                )

            total = len(questions)
            return {
                "quiz_id": quiz_id,
                "score": score,
                "total_questions": total,
                "percentage": round(score / total * 100, 2) if total else 0,
                "results": results,
            }

