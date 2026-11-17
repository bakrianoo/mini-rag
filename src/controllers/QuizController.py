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
import time

QUIZ_TIME_BUDGET = 500

LETTERS = ("A", "B", "C", "D")
MAX_ATTEMPTS = 3
MAX_CHUNK_CHARS = 1500
DUPLICATE_THRESHOLD = 0.85
GROUNDING_MIN = 0.25

LETTER_REF = re.compile(
    r"((?i:\b(?:option|answer|choice)s?|الإجابة|الاجابة|الخيار|الخيارات|الاختيار)\s*[(\"']?\s*)"
    r"([A-D]\b(?:(?:\s*[,،]\s*(?:(?:and|or|&|و|أو)\s+)?|\s+(?:and|or|&|و|أو)\s+)[(\"']?[A-D]\b)*)"
)

# Bibliographic / citation-heavy chunks are bad quiz material
_CITATION_HIT_RE = re.compile(
    r"https?://|doi:\s*\S+|\bvol\.?\s*\d|\bpp\.?\s*\d"
    r"|\b(?:19|20)\d{2}\)\."
    r"|\b[A-Z][a-z]+,\s*(?:[A-Z]\.\s*){1,3}"
)
_CITE_NARRATIVE_RE = re.compile(
    r"(?:[A-Z][\w\-]+(?:,\s*(?:and\s+|&\s*)?|\s+and\s+|\s*&\s*|\s+et\s+al\.?\s*))*"
    r"[A-Z][\w\-]+\s*\(\s*(?:19|20)\d{2}[a-z]?\s*\)"
)
_CITE_PAREN_RE = re.compile(r"\([^()]*\b(?:19|20)\d{2}[a-z]?\b[^()]*\)")
_DIAGRAM_RE = re.compile(r"\b(diagram|symbols?|appears?\s+(?:twice|once))\b", re.I)

CHARS_PER_QUESTION = 300
MIN_CHUNK_CHARS = 60

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

        if not raw:
            raise ValueError("The AI response is empty.")

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
        letter_map = {LETTERS[old]: LETTERS[i] for i, old in enumerate(order)}
        explanation = LETTER_REF.sub(
            lambda m: m.group(1)
            + re.sub(r"\b[A-D]\b", lambda x: letter_map[x.group(0)], m.group(2)),
            explanation,
        )

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

    @staticmethod
    def _is_citation_chunk(text: str) -> bool:
     hits = len(_CITATION_HIT_RE.findall(text))
     n = len(text)
     return hits >= 3 or (hits >= 2 and n < 600) or (hits >= 1 and n < 300)
  
    @staticmethod
    def _is_useful_chunk(text: str) -> bool:
     words = re.findall(r"\w{4,}", text.lower())
     if len(words) < 12 or len(text) < 80:
        return False
     return not QuizController._is_citation_chunk(text)

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
            max_output_tokens=64,
            temperature=0.0,
            response_format="json",
        )

        if not isinstance(raw, str) or not raw.strip():
            return False

        try:
            cleaned = re.sub(
                r"^\s*```(?:json)?\s*|\s*```\s*$",
                "",
                raw.strip(),
                flags=re.IGNORECASE,
            ).strip()
            result = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return False
            try:
                result = json.loads(match.group(0))
            except json.JSONDecodeError:
                return False

        answer = str(result.get("answer", "")).strip().upper() if isinstance(result, dict) else ""
        return answer.rstrip(".):") == question["correct_answer"]

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
        hint: str = "",
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
  "explanation": "Why the correct option is right, based on the material"
}}

Rules:
- Output JSON only, without Markdown or extra text.
- Include exactly four non-empty options: A, B, C, D.
- All four options must be different.
- Keep each option short (under 15 words) and clearly different from the others.
- correct_answer must be A, B, C, or D.
- Only one option can be correct.
- "evidence" must be copied exactly from the study material, without changing any word.
- Ask ONLY about facts explicitly written in the study material.
- Every name, label, or number used in the question must appear in the study material. Never invent examples, node names, or values.
- Do NOT ask about paper titles, authors, years, journals, or references.
- Do NOT use bibliographic citations as answer options.
- Ask about concepts, definitions, processes, or facts stated in the material.
- The explanation must be supported by the material.
- In the explanation, never mention option letters (A, B, C, D). Refer to options by their text.
- Do not invent facts absent from the material.
- Do not mention "the passage" or "the text" in the question.
- The question must NOT contain the words of the correct option. The correct option must be information the reader has to know, not a rephrase of the question.
- Do NOT write questions like "Which X is described as <the answer>?". Ask what, why, or how instead.
- Bad (leaks the answer): Question: "Which strategy uses animations and narration together?" Correct option: "Using animations and narration together".
- Good: Question: "What is the benefit of presenting animations together with narration?" Correct option: the actual benefit stated in the material.
- Never write "according to <author name>" in the question. Ask about the concept itself.
- NEVER put a person's name or a year in the question or in any option (no "according to Liu (2011)"). Ask about the concept only.
- The question must NOT repeat the words of the correct option. If the answer is "Using X together", do not write "Which strategy uses X together?".
- Do NOT ask about the shape, symbols, letters, or layout of a diagram. Ask only about the concept the diagram teaches.
- No two options may mean the same thing.
- Ensure every question is clear, self-contained, student-friendly, and unambiguous;
 use natural educational wording with enough context, avoid vague references or unexplained terms, 
 prevent semantic overlap between questions, and keep all answer options concise, grammatically consistent,
  similar in length and detail, and equally plausible, without making the correct answer noticeably longer or easier to guess from its wording or structure.
- If the material has no clear fact to ask about, return exactly {{"insufficient": true}} and nothing else.
{avoid}{hint}

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

        texts = [t for t in texts if not self._is_citation_chunk(t)] or texts
        chunks = self._pick_diverse_chunks(texts)
        if not chunks:
            raise LookupError(
                "No usable study material was found for this project."
            )
        chunks = [c for c in chunks if len(c) >= MIN_CHUNK_CHARS] or chunks
        useful = [c for c in chunks if self._is_useful_chunk(c)]


        chunks = useful or [c for c in chunks if not self._is_citation_chunk(c)]
        if not chunks:
           raise LookupError("No usable study material was found for this project.")



        logger.info(
            "quiz chunks: pdf=%d image=%d total=%d",
            len(pdf_docs),
            len(image_docs),
            len(chunks),
        )

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
        deadline = time.monotonic() + QUIZ_TIME_BUDGET

        for chunk_index, raw_chunk in enumerate(chunks):
            if len(questions) >= target_count or time.monotonic() > deadline:
                break

            chunk = self._strip_citations(raw_chunk)[:MAX_CHUNK_CHARS]
            hint = ""
            for attempt in range(MAX_ATTEMPTS):
                if time.monotonic() > deadline:
                    break
                raw_response = ""
                previous = [question["question"] for question in questions]
                prompt = self._build_prompt(chunk, difficulty, previous, hint)
                try:
                    raw_response = await asyncio.to_thread(
                        self.generation_client.generate_text,
                        prompt=prompt,
                        chat_history=list(chat_history),
                        max_output_tokens=1200,
                        temperature=0.2 + 0.2 * attempt,
                        response_format="json",
                    )

                    question = self._parse_question(raw_response, previous)

                    evidence_norm = self._normalize(question["evidence"])
                    if len(evidence_norm) < 15 or evidence_norm not in self._normalize(chunk):
                        raise ValueError("Evidence is not in the passage.")
                    self._validate_quality(question)

                    if verify_answers:
                        if not await self._verify(question, chunk):
                            logger.warning(
                                "Soft verification failed | chunk=%s | question=%s",
                                chunk_index,
                                question["question"][:60],
                            )
                            # soft: do not reject; keep the question

                except InsufficientMaterialError as exc:
                    last_error = exc
                    logger.info(
                        "Quiz chunk skipped | chunk=%s | reason=%s",
                        chunk_index,
                        exc,
                    )
                    break
                except DuplicateQuestionError as exc:
                    last_error = exc
                    hint = (
                        "\nYour previous question was too similar to an existing one. "
                        "Ask about a COMPLETELY DIFFERENT fact from the material. "
                        "Do not rephrase the same idea.\n"
                    )
                    logger.warning(
                        "Quiz duplicate rejected | chunk=%s | attempt=%s/%s",
                        chunk_index,
                        attempt + 1,
                        MAX_ATTEMPTS,
                    )
                    if attempt >= 1:
                         break   
                    continue
                except (ValueError, json.JSONDecodeError) as exc:
                    last_error = exc
                    msg = str(exc)
                    if "Options are not distinct" in msg or "valid JSON" in msg or "empty" in msg.lower():
                        hint = (
                            "\nPrevious output was invalid or incomplete. "
                            "Return ONE complete JSON object only. "
                            "Make all four options short and clearly different. "
                            "Do not use paper titles or citations as options.\n"
                        )
                    else:
                        hint = f"\nYour previous answer was rejected: {exc} Fix it.\n"
                    logger.warning(
                        "Quiz validation failed | chunk=%s | attempt=%s | reason=%s | raw=%r | chunk_head=%r",
                        chunk_index,
                        attempt + 1,
                        exc,
                        (raw_response or "")[:300],
                        chunk[:150],
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

                question["id"] = f"q{len(questions) + 1}"
                questions.append(question)
                break

        if not questions:
            raise RuntimeError(f"Could not generate any valid questions: {last_error}")
        if len(questions) < target_count:
            logger.warning(
                "Returning %d of %d questions. Last error: %s",
                len(questions),
                target_count,
                last_error,
            )

        async with self.db_client() as session:
            quiz = Quiz(
                project_id=project.project_id,
                card_id=card_id,
                questions=questions,
            )
            session.add(quiz)
            await session.commit()
            await session.refresh(quiz)

        return {
            "quiz_id": quiz.quiz_id,
            "project_id": quiz.project_id,
            "question_count": len(questions),
            "difficulty": difficulty,
            "questions": self._public_questions(questions),
        }

    # ---------- knowledge quiz (no uploaded material) ----------
    @staticmethod
    def _build_knowledge_prompt(
        topic: str,
        difficulty: str,
        previous: list[str],
        language: str,
        hint: str = "",
    ) -> str:
        avoid = ""
        if previous:
            listed = "\n".join(f"- {q}" for q in previous)
            avoid = (
                "\nDo not repeat or rephrase these questions:\n"
                f"{listed}\n"
            )

        return f"""Create exactly ONE multiple-choice question about the topic below, using well-established textbook knowledge.
Topic: {topic}
Difficulty: {difficulty}
Language: {language}. Keep technical terms in English.

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
  "evidence": "One sentence stating the fact that proves the answer",
  "explanation": "Why the correct option is right"
}}

Rules:
- Output JSON only, without Markdown or extra text.
- Include exactly four non-empty options: A, B, C, D, all different.
- Keep each option short (under 15 words) and clearly different.
- correct_answer must be A, B, C, or D, and only one option can be correct.
- Ask ONLY about standard, widely accepted facts that you are certain about.
- Do not invent names, numbers, formulas, or examples. If unsure, ask about a simpler, more basic fact.
- In the explanation, never mention option letters (A, B, C, D). Refer to options by their text.
- Do not mention "the passage" or "the text" in the question.
- Write grammatically correct, natural {language}. Every question must be a complete, clear sentence.
- Ask about one fact only, and avoid ambiguous or tricky wording.
- No two options may mean the same thing, and exactly one must be correct.
- The question must NOT repeat the words of the correct option.
- If you are not 100% sure of the fact, choose a simpler, more basic fact.
{avoid}{hint}"""

    async def _verify_knowledge(self, question: dict) -> bool:
        """Self-consistency check: the model must pick the same answer key without seeing it."""
        options = "\n".join(
            f"{key}. {value}" for key, value in question["options"].items()
        )
        prompt = (
            "Answer the multiple-choice question using your knowledge.\n\n"
            f"Question: {question['question']}\n{options}\n\n"
            "Return a JSON object with a single field 'answer' containing the letter "
            "of the correct option (A, B, C, or D)."
        )
        raw = await asyncio.to_thread(
            self.generation_client.generate_text,
            prompt=prompt,
            chat_history=[],
            max_output_tokens=64,
            temperature=0.0,
            response_format="json",
        )
        if not isinstance(raw, str) or not raw.strip():
            return False
        try:
            cleaned = re.sub(
                r"^\s*```(?:json)?\s*|\s*```\s*$",
                "",
                raw.strip(),
                flags=re.IGNORECASE,
            ).strip()
            result = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return False
            try:
                result = json.loads(match.group(0))
            except json.JSONDecodeError:
                return False
        answer = str(result.get("answer", "")).strip().upper() if isinstance(result, dict) else ""
        return answer.rstrip(".):") == question["correct_answer"]

    async def generate_knowledge_quiz(
        self,
        project,
        card_id: int,
        topic: str,
        question_count: int = 5,
        difficulty: str = "medium",
        language: str = "English",
        verify_answers: bool = True,
    ) -> dict:
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic is required.")
        if not isinstance(question_count, int) or isinstance(question_count, bool):
            raise ValueError("question_count must be an integer.")
        if not 1 <= question_count <= 20:
            raise ValueError("question_count must be between 1 and 20.")
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError("difficulty must be easy, medium, or hard.")

        topic = topic.strip()[:120]
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
        deadline = time.monotonic() + QUIZ_TIME_BUDGET
        failed_slots_in_row = 0
        QUESTION_ANGLES = (
             "a precise definition",
             "how it works step by step",
             "time or space complexity",
             "an advantage or disadvantage",
             "a real-world use case",
             "a comparison with a similar concept",
             "a common mistake or edge case",
                )

        for slot in range(question_count):
            if time.monotonic() > deadline or failed_slots_in_row >= 2:
              break

            hint = ""
            focus = f"\nThis question must focus on: {QUESTION_ANGLES[slot % len(QUESTION_ANGLES)]}.\n"
            accepted = False
            for attempt in range(MAX_ATTEMPTS):
                if time.monotonic() > deadline:
                    break
                raw_response = ""
                previous = [question["question"] for question in questions]
                prompt = self._build_knowledge_prompt(
                   topic, difficulty, previous, language, focus + hint
                )
                try:
                    raw_response = await asyncio.to_thread(
                        self.generation_client.generate_text,
                        prompt=prompt,
                        chat_history=list(chat_history),
                        max_output_tokens=1200,
                        temperature=0.2 + 0.2 * attempt,
                        response_format="json",
                    )
                    question = self._parse_question(raw_response, previous)

                    if verify_answers and not await self._verify_knowledge(question):
                        raise ValueError("Answer key failed verification.")

                except (ValueError, json.JSONDecodeError) as exc:
                    last_error = exc
                    msg = str(exc)
                    if "Options are not distinct" in msg or "valid JSON" in msg or "empty" in msg.lower():
                        hint = (
                            "\nPrevious output was invalid or incomplete. "
                            "Return ONE complete JSON object only. "
                            "Make all four options short and clearly different.\n"
                        )
                    else:
                        hint = f"\nYour previous answer was rejected: {exc} Fix it.\n"
                    logger.warning(
                        "Knowledge quiz validation failed | attempt=%s | reason=%s | raw=%r",
                        attempt + 1,
                        exc,
                        (raw_response or "")[:300],
                    )
                    continue
                except requests.exceptions.RequestException as exc:
                    last_error = exc
                    logger.warning(
                        "Knowledge quiz request failed | attempt=%s | reason=%s",
                        attempt + 1,
                        exc,
                    )
                    if attempt < MAX_ATTEMPTS - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue

                question["id"] = f"q{len(questions) + 1}"
                questions.append(question)
                accepted = True
                break

            failed_slots_in_row = 0 if accepted else failed_slots_in_row + 1

        if not questions:
            raise RuntimeError(f"Could not generate any valid questions: {last_error}")
        if len(questions) < question_count:
            logger.warning(
                "Returning %d of %d knowledge questions. Last error: %s",
                len(questions),
                question_count,
                last_error,
            )

        async with self.db_client() as session:
            quiz = Quiz(
                project_id=project.project_id,
                card_id=card_id,
                questions=questions,
            )
            session.add(quiz)
            await session.commit()
            await session.refresh(quiz)

        return {
            "quiz_id": quiz.quiz_id,
            "project_id": quiz.project_id,
            "question_count": len(questions),
            "difficulty": difficulty,
            "source": "knowledge",
            "questions": self._public_questions(questions),
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
    def _source_text_to_documents(source_text: str, max_chars: int = 700) -> list:
     text = re.sub(r"\s+", " ", source_text or "").strip()
     if not text:
         return []
     sentences = [s.strip() for s in re.split(r"(?<=[.!?؟])\s+", text) if s.strip()]
     parts, current = [], ""
     for s in sentences:
         if current and len(current) + len(s) + 1 > max_chars:
             parts.append(current)
             current = s
         else:
             current = f"{current} {s}".strip()
     if current:
         parts.append(current)
     final = []
     for p in parts:
         if len(p) > max_chars * 2:
             final.extend(p[i:i + max_chars] for i in range(0, len(p), max_chars - 100))
         else:
             final.append(p)
     return [SimpleNamespace(text=p) for p in final]



    @staticmethod
    def _strip_citations(text: str) -> str:
     """Remove in-text citations so the model can't copy author names into questions."""
     text = _CITE_NARRATIVE_RE.sub("the authors", text)
     text = _CITE_PAREN_RE.sub("", text)
     return re.sub(r"\s{2,}", " ", text).strip()

    def _validate_quality(self, question: dict) -> None:
     q, opts, key = question["question"], question["options"], question["correct_answer"]
     tok = lambda s: set(re.findall(r"\w{3,}", s.lower()))

     if _DIAGRAM_RE.search(q):
         raise ValueError("Do not ask about diagrams or symbols. Ask about the concept itself.")

     sets = [tok(v) for v in opts.values()]
     for i, a in enumerate(sets):
         for j, b in enumerate(sets):
             if i != j and a and a < b:
                 raise ValueError("Two options mean the same thing. Make them clearly different.")

     qt = tok(q)
     ov = lambda o: len(tok(o) & qt) / max(len(tok(o)), 1)
     others = max(ov(v) for k, v in opts.items() if k != key)
     if ov(opts[key]) >= 0.6 and ov(opts[key]) > others:
         raise ValueError("The correct option repeats the question. Ask about a fact the question does not contain.")