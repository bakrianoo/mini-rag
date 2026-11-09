import asyncio
import base64
import logging
 
import httpx
 
from helpers.config import get_settings
 
logger = logging.getLogger("uvicorn.error")
 
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
RETRY_STATUSES = (429, 500, 502, 503, 504)
 
 
class VisionController:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.GEMINI_API_KEY
        self.model_id = settings.VISION_MODEL_ID
 
    @staticmethod
    def _mime(image_b64: str) -> str:
        # detect the image type from the first base64 characters
        if image_b64.startswith("iVBOR"):
            return "image/png"
        if image_b64.startswith("UklGR"):
            return "image/webp"
        if image_b64.startswith("R0lGO"):
            return "image/gif"
        return "image/jpeg"
 
    @classmethod
    def _to_gemini(cls, messages: list) -> list:
        """Convert {"images": [b64]} messages to the image_url format."""
        out = []
        for m in messages:
            imgs = m.get("images")
            if not imgs:
                out.append({"role": m["role"], "content": m["content"]})
                continue
            parts = [{"type": "text", "text": m["content"]}]
            parts += [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{cls._mime(b)};base64,{b}"},
                }
                for b in imgs
            ]
            out.append({"role": m["role"], "content": parts})
        return out
 
    async def _call_ollama(
        self,
        messages: list,
        timeout: float = 60.0,
        max_tokens: int = 4096,
        retries: int = 2,
    ) -> str:
        payload = {
            "model": self.model_id,
            "messages": self._to_gemini(messages),
            "max_tokens": max_tokens,
            "reasoning_effort": "low",
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
 
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0)
        ) as client:
            for attempt in range(retries + 1):
                response = await client.post(GEMINI_URL, json=payload, headers=headers)
 
                if response.status_code in RETRY_STATUSES and attempt < retries:
                    logger.warning(
                        "Gemini returned %s (attempt %d/%d), retrying",
                        response.status_code, attempt + 1, retries + 1,
                    )
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
 
                if response.status_code >= 400:
                    logger.error(
                        "Gemini error %s: %s", response.status_code, response.text[:500]
                    )
                response.raise_for_status()
 
                result = response.json()
                choice = (result.get("choices") or [{}])[0]
                answer = ((choice.get("message") or {}).get("content") or "").strip()
                if answer:
                    return answer
 
                logger.warning(
                    "Empty vision content (attempt %d/%d) finish_reason=%s usage=%s",
                    attempt + 1, retries + 1,
                    choice.get("finish_reason"), result.get("usage"),
                )
 
        raise ValueError("EMPTY_RESPONSE. pleas try again")
 
    async def analyze_image(self, image_bytes: bytes) -> str:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
 
        return await self._call_ollama([
            {
                "role": "user",
                "content": (
                "You are extracting study material from an educational image "
                "so a student can revise from it.\n\n"
                "Write the result in this order:\n"
                "1. TOPIC: name the topic or concept shown "
                "(e.g. \"Types of linked lists\").\n"
                "2. TEXT: transcribe all visible text, headings and labels exactly.\n"
                "3. CONCEPTS: state each concept as a full sentence with its "
                "definition or property "
                "(e.g. \"A doubly linked list has nodes with next and previous pointers.\").\n"
                "4. DIAGRAM: only after the concepts, briefly say what the "
                "diagram/arrows illustrate.\n\n"
                "Rules:\n"
                "- Use the exact terms written in the image.\n"
                "- Do not describe colors, layout or shapes unless they carry meaning.\n"
                "- Do not add anything that is not visible in the image.\n"
                "- Return only the extracted content."
                        ),
                    "images": [image_base64],
                }
            ],
            timeout=60.0,
            max_tokens=3000,
        )
 
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
            "You are STUDY GATE AI, an educational assistant.\n"
            "## Source priority\n"
            "- IMAGE-only questions: answer from the image and its description only.\n\n"
            "- PDF/document-only questions: do not use this image path.\n"
            "- BOTH: combine the image with the provided document context.\n"
            "- Do not invent visual details that are not in the image.\n"
            "- Do not claim a fact is in the PDF unless the document context supports it.\n"
            "- If the sources conflict, say so instead of guessing.\n"
            "- Answer in the same language as the user.\n"
            "- Do not repeat the same sentence or phrase.\n"
            "- If the answer is not in the image or the documents, say so clearly in the user's language, and tell them you can answer from general knowledge if they ask. Do not answer from general knowledge unless they ask\n\n"
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