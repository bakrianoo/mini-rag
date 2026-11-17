import json
import logging
import time
from typing import List, Union
 
import requests
 
from ..LLMEnums import GeminiEnums
from ..LLMInterface import LLMInterface
 
DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
RETRY_STATUSES = (429, 500, 502, 503, 504)
OPENAI_FORMAT_TYPES = ("json_object", "json_schema", "text")
 
 
class GeminiProvider(LLMInterface):
    """Generation-only provider for the Gemini API (OpenAI-compatible endpoint).
 
    Embeddings are intentionally not supported here: keep EMBEDDING_BACKEND=OLLAMA.
    """
 
    def __init__(
        self,
        api_key: str,
        api_url: str = DEFAULT_API_URL,
        default_input_max_characters: int = 4000,
        default_generation_max_output_tokens: int = 8000,
        default_generation_temperature: float = None,
        reasoning_effort: str = "low",
        use_temperature: bool = False,
        max_retries: int = 2,
        timeout: float = 200.0,
    ):
        self.api_key = api_key
        self.api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature
 
        self.use_temperature = use_temperature
        self.reasoning_effort = reasoning_effort
        self.max_retries = max_retries
        self.timeout = timeout
 
        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None
        self.enums = GeminiEnums
 
        self.logger = logging.getLogger(__name__)
 
    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id
 
    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
 
    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()
 
    # ------------------------------------------------------------------ helpers
 
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
 
    def _map_response_format(self, response_format):
        """Translate the Ollama-style `format` value to OpenAI-style response_format."""
        if not response_format:
            return None
 
        if isinstance(response_format, str):
            if response_format.lower() == "json":
                return {"type": "json_object"}
            self.logger.warning(
                "Unsupported response_format %r for Gemini, ignoring", response_format
            )
            return None
 
        if isinstance(response_format, dict):
            # already in OpenAI shape
            if response_format.get("type") in OPENAI_FORMAT_TYPES:
                return response_format
            # otherwise treat it as a raw JSON schema (what Ollama's `format` accepts)
            return {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": response_format},
            }
 
        self.logger.warning(
            "Unsupported response_format type %s, ignoring", type(response_format)
        )
        return None
 
    def _build_payload(
        self, prompt, chat_history, max_output_tokens, temperature, response_format
    ) -> dict:
        if not self.generation_model_id:
            raise ValueError("Generation model is not set (set_generation_model).")
 
        messages = [
            {"role": m["role"], "content": m["content"]} for m in (chat_history or [])
        ]
        messages.append({"role": "user", "content": prompt})
 
        payload = {
            "model": self.generation_model_id,
            "messages": messages,
            "max_tokens": (
                max_output_tokens
                if max_output_tokens is not None
                else self.default_generation_max_output_tokens
            ),
        }
 
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
 
        if self.use_temperature:
            payload["temperature"] = (
                temperature
                if temperature is not None
                else self.default_generation_temperature
            )
 
        mapped_format = self._map_response_format(response_format)
        if mapped_format:
            payload["response_format"] = mapped_format
 
        return payload
 
    @staticmethod
    def _retry_delay(response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
        return 5.0 * (attempt + 1)
 
    def _post(self, payload: dict, stream: bool = False):
        url = f"{self.api_url}/chat/completions"
 
        for attempt in range(self.max_retries + 1):
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                stream=stream,
                timeout=(10, self.timeout),
            )
 
            if response.status_code in RETRY_STATUSES and attempt < self.max_retries:
                delay = self._retry_delay(response, attempt)
                self.logger.warning(
                    "Gemini returned %s (attempt %d/%d), retrying in %.0fs",
                    response.status_code, attempt + 1, self.max_retries + 1, delay,
                )
                response.close()
                time.sleep(delay)
                continue
 
            if response.status_code >= 400:
                self.logger.error(
                    "Gemini error %s: %s", response.status_code, response.text[:500]
                )
            response.raise_for_status()
            return response
 
    # --------------------------------------------------------------- generation
 
    def generate_text(
        self,
        prompt: str,
        chat_history: list = None,
        max_output_tokens: int = None,
        temperature: float = None,
        response_format: str = None,
        on_token=None,
    ):
        payload = self._build_payload(
            prompt, chat_history, max_output_tokens, temperature, response_format
        )
 
        if on_token is not None:
            return self._generate_stream(payload, on_token)
 
        response = self._post(payload)
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content") or "").strip()
        finish_reason = choice.get("finish_reason")
 
        if not content:
            self.logger.warning(
                "Gemini empty content | model=%s | finish_reason=%s | usage=%s",
                self.generation_model_id, finish_reason, data.get("usage"),
            )
            return None
 
        if finish_reason == "length":
            self.logger.warning(
                "Gemini output truncated (finish_reason=length) | model=%s | "
                "raise GENERATION_DEFAULT_MAX_TOKENS (thinking tokens share the budget)",
                self.generation_model_id,
            )
 
        return content
 
    def _generate_stream(self, payload: dict, on_token):
        payload["stream"] = True
        parts = []
        finish_reason = None
 
        with self._post(payload, stream=True) as response:
            # SSE has no charset header; without this requests decodes as latin-1
            # and Arabic text gets corrupted.
            response.encoding = "utf-8"
 
            for raw in response.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                if not line.startswith("data:"):
                    continue
 
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
 
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    self.logger.warning("Gemini stream: skipped malformed chunk")
                    continue
 
                choice = (data.get("choices") or [{}])[0]
                piece = (choice.get("delta") or {}).get("content") or ""
                if piece:
                    parts.append(piece)
                    on_token(piece)
                finish_reason = choice.get("finish_reason") or finish_reason
 
        content = "".join(parts).strip()
        if not content:
            self.logger.warning(
                "Gemini empty streamed content | model=%s | finish_reason=%s",
                self.generation_model_id, finish_reason,
            )
            return None
 
        if finish_reason == "length":
            self.logger.warning(
                "Gemini streamed output truncated (finish_reason=length) | model=%s",
                self.generation_model_id,
            )
        return content
 
 
    def embed_text(
        self,
        text: Union[str, List[str]],
        document_type: str = None,
    ):
        raise NotImplementedError(
            "GeminiProvider is generation-only. Use EMBEDDING_BACKEND=OLLAMA."
        )
 
    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": prompt,
        }
 