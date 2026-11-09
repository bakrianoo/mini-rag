from ..LLMInterface import LLMInterface
from ..LLMEnums import OllamaEnums
import requests
import logging
from typing import List, Union
import json

class OllamaProvider(LLMInterface):

    def __init__(
        self,
        api_key: str = "ollama",
        api_url: str = "http://localhost:11434",
        default_input_max_characters: int = 4000,
        default_generation_max_output_tokens: int = 2000,
        default_generation_temperature: float = 0.1,
    ):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None
        self.enums = OllamaEnums

        self.logger = logging.getLogger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def generate_text(
        self,
        prompt: str,
        chat_history: list = None,
        max_output_tokens: int = None,
        temperature: float = None,
        response_format: str = None,
         on_token=None,

    ):
    
        payload = {
         "model": self.generation_model_id,
         "messages": list(chat_history or []) + [
             {"role": "user", "content": prompt},
         ],
         "stream": False,
         "think": False,
         "options": {
            "temperature": (
                temperature
                if temperature is not None
                else self.default_generation_temperature
            ),
            "num_predict": (
                max_output_tokens
                if max_output_tokens is not None
                else self.default_generation_max_output_tokens
            ),  },   }
        if response_format:
            payload["format"] = response_format
        if on_token is not None:
            return self._generate_stream(payload, on_token)



        response = requests.post(
            f"{self.api_url}/api/chat",
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message") or {}
        content = (message.get("content") or "").strip()


        if not content:
          self.logger.warning(
          "Ollama empty content | model=%s | done_reason=%s | keys=%s",
          self.generation_model_id,
          data.get("done_reason"),
          list(message.keys()),
           )
          return None

        return content

    def _generate_stream(self, payload: dict, on_token):
        payload["stream"] = True
        parts = []
        with requests.post(
            f"{self.api_url}/api/chat",
            json=payload,
            stream=True,
            timeout=(10, 300),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                piece = (data.get("message") or {}).get("content") or ""
                if piece:
                    parts.append(piece)
                    on_token(piece)
                if data.get("done"):
                    break

        content = "".join(parts).strip()
        if not content:
            self.logger.warning(
                "Ollama empty streamed content | model=%s", self.generation_model_id
            )
            return None
        return content
    def embed_text(
        self,
        text: Union[str, List[str]],
        document_type: str = None,
    ):
        if isinstance(text, str):
            text = [text]

        response = requests.post(
            f"{self.api_url}/api/embed",
            json={
                "model": self.embedding_model_id,
                "input": [self.process_text(t) for t in text],
            },
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": prompt,
        }
