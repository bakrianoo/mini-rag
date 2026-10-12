import asyncio
import logging
import re

from controllers.NLPController import NLPController
from controllers.VisionController import VisionController

logger = logging.getLogger("uvicorn.error")

OUT_OF_SCOPE_AR = (
    "أنا STUDY GATE  المساعد التعليمي داخل منصة STUDY GATE. "
    "أنا هنا لمساعدتك في فهم المحاضرات، وشرح المفاهيم العلمية، "
    "وتلخيص ملفات PDF، وشرح الصور التعليمية، وحل المسائل، "
    "وإنشاء أسئلة للمراجعة. سؤالك خارج نطاق المنصة التعليمية. "
    "اسألني عن موضوع دراسي وسأساعدك فيه."
)

OUT_OF_SCOPE_EN = (
    "I'm STUDY GATE , the educational assistant for STUDY GATE. "
    "I can help you understand lectures, explain academic concepts, "
    "summarize PDFs, explain educational images, solve problems, "
    "and prepare revision questions. Your request is outside my "
    "educational scope. Ask me about a study topic and I'll help."
)

RETRIEVAL_LIMIT = 3
MAX_CHUNK_CHARS = 800
MAX_HISTORY_MESSAGES = 10
ROUTER_HISTORY_MESSAGES = 5

ROUTER_PROMPT = """Classify the user's CURRENT request.
Return exactly one label:
STUDY, DOCS, IMAGE, BOTH, or OFF_TOPIC.

STUDY:
An educational or academic question that can be answered using
general knowledge, even if no study material was uploaded.
Examples: Explain machine learning, what is a stack, solve a math problem.

DOCS:
The user asks about their uploaded PDFs, lectures, notes, or course materials.

IMAGE:
The user asks about educational content in an uploaded image only.

BOTH:
The answer requires both an educational image and uploaded study documents.

OFF_TOPIC:
The request is unrelated to studying or education.
Examples: Recommend a car, identify a household fan model,
shopping recommendations, unrelated personal requests.

Important rules:
- Classify the user's intent, not merely the words in the question.
- Uploaded files do not make an unrelated question a DOCS request.
- An uploaded image does not automatically make a question an IMAGE request.
- A question about how an electric fan works using physics is STUDY.
- Asking which fan model someone owns is OFF_TOPIC.
- A general academic question is STUDY, not OFF_TOPIC.
- If no image is available, never return IMAGE or BOTH.
- Use conversation history only to understand references in the current question.
- If the request is clearly outside the educational scope, return OFF_TOPIC.

Image available: {image_status}

Conversation history:
{history}

Current question: {question}

Classification:"""


class ChatController:
    def __init__(
        self,
        vectordb_client,
        generation_client,
        embedding_client,
        template_parser,
    ):
        self.nlp = NLPController(
            vectordb_client=vectordb_client,
            generation_client=generation_client,
            embedding_client=embedding_client,
            template_parser=template_parser,
        )
        self.generation_client = generation_client
        self.vision = VisionController()

    @staticmethod
    def _format_history(history: list, limit: int = MAX_HISTORY_MESSAGES) -> list:
        """Keep valid user/assistant messages in chronological order."""
        valid_messages = []

        for message in history or []:
            if not isinstance(message, dict):
                continue

            role = message.get("role")
            content = message.get("content")

            if role not in ("user", "assistant") or not isinstance(content, str):
                continue

            content = content.strip()
            if content:
                valid_messages.append({
                    "role": role,
                    "content": content,
                })

        return valid_messages[-limit:]

    async def _route(
        self,
        question: str,
        history: list,
        has_image: bool,
    ) -> str:
        """Choose the answer source using the question and recent history."""


        recent_history = self._format_history(
            history,
            limit=ROUTER_HISTORY_MESSAGES,
        )

        history_text = "\n".join(
            f"{item['role']}: {item['content'][:160]}"
            for item in recent_history
        ) or "No previous messages."

        prompt = ROUTER_PROMPT.format(
            image_status="yes" if has_image else "no",
            history=history_text,
            question=question,
        )

        try:
            output = await asyncio.to_thread(
                self.generation_client.generate_text,
                prompt=prompt,
                chat_history=[],
                temperature=0.0,
                max_output_tokens=16,
            )

            match = re.search(
                r"\b(OFF_TOPIC|STUDY|DOCS|IMAGE|BOTH)\b",
                (output or "").upper(),
            )

            if match:
                route = match.group(1)
                if not has_image and route in ("IMAGE", "BOTH"):
                    route = "DOCS" if route == "BOTH" else "STUDY"
                logger.info("Chat router selected: %s", route)
                return route

            logger.warning("Unrecognized router output; using fallback.")
        except Exception:
            logger.exception("Chat router failed; using fallback.")

        # Safe fallback: don't ignore the image if routing fails.
        return "BOTH" if has_image else "DOCS"

    async def _retrieve_context(self, project, question: str) -> str:
        try:
            documents = await self.nlp.search_vector_db_collection(
                project=project,
                text=question,
                limit=RETRIEVAL_LIMIT * 2,
            )
        except Exception:
            logger.exception("Chat RAG retrieval failed.")
            return ""

        if not isinstance(documents, list) or not documents:
            logger.info("No RAG documents retrieved.")
            return ""

        parts = []
        seen_texts = set()

        for document in documents:
            content = getattr(document, "text", "")

            if not isinstance(content, str) or not content.strip():
                continue

            score = getattr(document, "score", None)

            if score is not None and score < 0.35:
                continue

            normalized_text = " ".join(content.strip().split()).casefold()

            if normalized_text in seen_texts:
                continue

            seen_texts.add(normalized_text)

            chunk_text = self.generation_client.process_text(
                content.strip()[:MAX_CHUNK_CHARS]
            )

            document_prompt = self.nlp.template_parser.get(
                "rag",
                "document_prompt",
                {
                    "doc_num": len(parts) + 1,
                    "chunk_text": chunk_text,
                },
            )

            parts.append(document_prompt)

            if len(parts) >= RETRIEVAL_LIMIT:
                break

        return "\n\n".join(parts)

    async def answer(
        self,
        project,
        question: str,
        history: list,
        image: dict | None = None,
    ) -> str:
        question = question.strip()

        if not question:
            raise ValueError("CHAT_EMPTY_QUESTION")

        history = self._format_history(history)

        route = await self._route(
            question=question,
            history=history,
            has_image=bool(image),
        )


        if route == "OFF_TOPIC":
            if re.search(r"[\u0600-\u06FF]", question):
                return OUT_OF_SCOPE_AR
            return OUT_OF_SCOPE_EN

        context = ""

        if route in ("DOCS", "BOTH"):
            context = await self._retrieve_context(
                project=project,
                question=question,
            )

        # Build the existing RAG footer using the current question.
        footer_prompt = ""

        if route in ("DOCS", "BOTH") and context:
            footer_prompt = self.nlp.template_parser.get(
                "rag",
                "footer_prompt",
                {"query": question},
            )

        # Image-only or image + document answer.
        if image and image.get("image_data") and route in ("IMAGE", "BOTH"):
            description = image.get("description") or ""

            return await self.vision.answer_question(
                image_bytes=image["image_data"],
                image_description=description,
                history=history,
                question=question,
                documents_context=(
                    context if route == "BOTH" else ""
                ),
            )

        # Reuse the existing STUDY GATE AI system prompt.
        base_system_prompt = self.nlp.template_parser.get(
            "rag",
            "system_prompt",
        )

        system_message = {
            "role": "system",
            "content": (
                f"{base_system_prompt}\n\n"
                "## Unified Chat Instructions\n"
                "- Answer the current question directly.\n"
                "- Do not introduce unrelated topics.\n"
                "- Do not repeat the same information.\n"
                "- Use conversation history to understand follow-up questions.\n"
                "- Answer general educational questions when appropriate.\n"
                "- Do not claim that information came from project documents "
                "unless it appears in the supplied context.\n\n"
                "## Relevant project documents\n"
                f"{context or 'No relevant project documents were retrieved.'}"
            ),
        }

        # Use the RAG footer when relevant documents were retrieved.
        # Otherwise, preserve normal general-chat behavior.
        prompt = footer_prompt if footer_prompt else question

        answer = await asyncio.to_thread(
            self.generation_client.generate_text,
            prompt=prompt,
            chat_history=[system_message] + history,
        )

        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("CHAT_EMPTY_RESPONSE")

        return answer.strip()