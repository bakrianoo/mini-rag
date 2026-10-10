import base64
import logging
import httpx
from helpers.config import get_settings

logger = logging.getLogger("uvicorn.error")


class VisionController:
    def __init__(self):
        settings = get_settings()
        self.api_url = settings.OLLAMA_API_URL.rstrip("/")
        self.model_id = settings.VISION_MODEL_ID

    async def _call_ollama(self, messages: list) -> str:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1},
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.api_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()

        result = response.json()
        answer = result.get("message", {}).get("content", "").strip()

        if not answer:
            logger.error(
                "Ollama returned empty content. Response keys: %s",
                list(result.keys()),
            )
            raise ValueError("VISION_EMPTY_RESPONSE")

        return answer

    async def analyze_image(self, image_bytes: bytes) -> str:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        return await self._call_ollama([
            {
                "role": "user",
                "content": (
                    "Analyze this image carefully. Describe its contents, "
                    "important details, visible text, and key information. "
                    "Do not guess details that are not visible."
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
        "You are a study assistant. The user attached an image to this "
        "conversation. Answer from the image first. The saved description "
        "below comes from analysing this same image: use it for details "
        "and the image itself to confirm layout. Use the conversation "
        "history to resolve references like 'this' or 'it'. If something "
        "is not visible or not in the description, say so. Do not invent "
        "details.\n\n"
        f"Saved description:\n{image_description}"
    )

     if documents_context:
        system_content += (
            "\n\nProject documents (use only if relevant to the question, "
            "and say when you use them):\n" + documents_context
        )

     messages = [{"role": "system", "content": system_content}]
     messages.extend(history[-10:])
     messages.append({
        "role": "user",
        "content": question,
        "images": [image_base64],
    })

     return await self._call_ollama(messages)