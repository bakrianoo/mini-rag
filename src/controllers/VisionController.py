import base64
import logging
import re
import httpx

from helpers.config import get_settings

logger = logging.getLogger("uvicorn.error")



class VisionController:
    def __init__(self):
        settings = get_settings()
        self.api_url = settings.OLLAMA_API_URL.rstrip("/")
        self.model_id = settings.VISION_MODEL_ID

    @staticmethod
    def _visible_text(message: dict) -> str:
     content = (message.get("content") or "").strip()

       # Never expose thinking or reasoning
     if not content:
        return ""

     if re.search(r"<think\b", content, re.IGNORECASE):
        content = re.sub(
            r"<think\b[^>]*>.*?</think\s*>",
            "",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if re.search(r"<think\b", content, re.IGNORECASE):
            return ""
     return content.strip()

    async def _call_ollama(self, messages: list) -> str:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
            },
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.api_url}/api/chat",
                json=payload,
            )
            if response.status_code >= 400:
                logger.error("Ollama error body: %s", response.text)
            response.raise_for_status()

        result = response.json()
        message = result.get("message") or {}
        answer = self._visible_text(message)

        if not answer:
            logger.error(
                "Ollama returned empty vision content. keys=%s content=%r thinking=%r",
                list(result.keys()),
                (message.get("content") or "")[:200],
                (message.get("thinking") or message.get("reasoning") or "")[:200],
            )
            raise ValueError("VISION_EMPTY_RESPONSE")

        return answer

    async def analyze_image(self, image_bytes: bytes) -> str:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        return await self._call_ollama([
            {
                "role": "user",
                "content": (
                    "Analyze this educational image carefully. "
                    "Transcribe visible text, describe diagrams, and list "
                    "key information. Do not guess details that are not visible. "
                    "Return only the extracted content.\n"
                ),
                "images": [image_base64],
            }
        ])

    async def answer_question(
        self,
        image_bytes: bytes,
        image_description: str,
        history: list,
        question: str,
        documents_context: str = "",
    ) -> str:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        system_content = (
            "You are STUDY GATE AI, an educational assistant.\n\n"
            "## Source priority\n"
            "- IMAGE-only questions: answer from the image and its description only.\n"
            "- PDF/document-only questions: do not use this image path.\n"
            "- BOTH: combine the image with the provided document context.\n"
            "- Do not invent visual details that are not in the image.\n"
            "- Do not claim a fact is in the PDF unless the document context supports it.\n"
            "- If the sources conflict, say so instead of guessing.\n"
            "- Answer in the same language as the user.\n"
            "- Do not repeat the same sentence or phrase.\n\n"
            f"Saved image description:\n{image_description or 'No image description available.'}"

            
        )

        if documents_context:
            system_content += (
                "\n\nProject documents (use these together with the image):\n"
                + documents_context
            )

        messages = [{"role": "system", "content": system_content}]
        messages.extend(history[-10:])
        messages.append({
            "role": "user",
            "content": question,
            "images": [image_base64],
        })

        return await self._call_ollama(messages)

