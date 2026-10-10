
import asyncio
import logging
import re

from controllers.NLPController import NLPController
from controllers.VisionController import VisionController

logger = logging.getLogger("uvicorn.error")

RETRIEVAL_LIMIT = 3
MAX_CHUNK_CHARS = 800
MAX_HISTORY_MESSAGES = 10
ROUTER_HISTORY_MESSAGES = 4

ROUTER_PROMPT = """Classify the CURRENT question using the conversation history.
Return exactly one word: IMAGE, DOCS, or BOTH.

IMAGE: The user asks about the uploaded image or refers to something
visible in it. Use IMAGE for follow-up questions about image content.
DOCS: The user asks a general question that does not need the image.
BOTH: The answer requires understanding the image and information
from project documents.

If the current question uses references like "this", "that part",
"explain it", or "اشرح دي", use the conversation history to resolve
what the user means.

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
        if not has_image:
            return "DOCS"

        recent_history = self._format_history(
            history,
            limit=ROUTER_HISTORY_MESSAGES,
        )

        history_text = "\n".join(
            f"{item['role']}: {item['content'][:160]}"
            for item in recent_history
        ) or "No previous messages."

        prompt = ROUTER_PROMPT.format(
            history=history_text,
            question=question,
        )

        try:
            output = await asyncio.to_thread(
                self.generation_client.generate_text,
                prompt=prompt,
                chat_history=[],
                temperature=0.0,
                max_output_tokens=8,
            )

            match = re.search(
                r"\b(IMAGE|DOCS|BOTH)\b",
                (output or "").upper(),
            )

            if match:
                route = match.group(1)
                logger.info("Chat router selected: %s", route)
                return route

            logger.warning("Unrecognized router output; using BOTH.")
        except Exception:
            logger.exception("Chat router failed; using BOTH.")

        # Safe fallback: don't ignore the image if routing fails.
        return "BOTH"

    async def _retrieve_context(self, project, question: str) -> str:
        """Retrieve relevant project chunks without assuming score semantics."""
        try:
            documents = await self.nlp.search_vector_db_collection(
                project=project,
                text=question,
                limit=RETRIEVAL_LIMIT,
            )
        except Exception:
            logger.exception("Chat RAG retrieval failed.")
            return ""

        if not documents or documents is False:
            logger.info("No RAG documents retrieved.")
            return ""

        parts = []

        for document in documents:
            content = getattr(document, "text", "")
            if not isinstance(content, str) or not content.strip():
                continue

            score = getattr(document, "score", None)
            logger.info("RAG result score: %r", score)

            parts.append(content.strip()[:MAX_CHUNK_CHARS])

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

        logger.info("Chat route: %s", route)

        context = ""
        if route in ("DOCS", "BOTH"):
            context = await self._retrieve_context(
                project=project,
                question=question,
            )

        # Image is the primary source for IMAGE questions.
        if image and route in ("IMAGE", "BOTH"):
            description = image.get("description") or ""

            if route == "BOTH":
                if context:
                    description += (
                        "\n\nSupplementary project-document context "
                        "(use only when relevant to the question):\n"
                        f"{context}"
                    )
                else:
                    description += (
                        "\n\nNo relevant project-document context "
                        "was retrieved."
                    )

            return await self.vision.answer_question(
                image_bytes=image["image_data"],
                image_description=description,
                history=history,
                question=question,
            )

        # Text-only answer: put context in the system message.
        # OllamaProvider truncates the final prompt, so keep the actual
        # question separate from the document context.
        system_message = {
            "role": "system",
            "content": (
                "You are a helpful study assistant. Answer clearly and "
                "accurately. Use the conversation history to understand "
                "follow-up questions. Use project documents when relevant. "
                "Do not claim that a document contains something unless "
                "it appears in the supplied context. If no relevant "
                "context was retrieved, be transparent about that.\n\n"
                "Relevant project documents:\n"
                f"{context or 'No relevant project documents were retrieved.'}"
            ),
        }

        answer = await asyncio.to_thread(
            self.generation_client.generate_text,
            prompt=question,
            chat_history=[system_message] + history,
        )

        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("CHAT_EMPTY_RESPONSE")

        return answer.strip()
