from ..LLMInterface import LLMInterface
from ..LLMEnums import DocumentTypeEnum
import requests
import logging
from typing import List, Union


class OllamaProvider(LLMInterface):

    def __init__(
        self,
        api_key: str = "ollama",
        api_url: str = "http://localhost:11434",
        default_input_max_characters: int = 1000,
        default_generation_max_output_tokens: int = 1000,
        default_generation_temperature: float = 0.1
    ):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

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
        chat_history: list = [],
        max_output_tokens: int = None,
        temperature: float = None
    ):
        response = requests.post(
            f"{self.api_url}/api/chat",
            json={
                "model": self.generation_model_id,
                "messages": chat_history + [
                    {"role": "user", "content": self.process_text(prompt)}
                ],
                "stream": False,
                "options": {
                    "temperature": temperature or self.default_generation_temperature,
                    "num_predict": max_output_tokens or self.default_generation_max_output_tokens
                }
            }
        )

        response.raise_for_status()

        return response.json()["message"]["content"]

    def embed_text(
        self,
        text: Union[str, List[str]],
        document_type: str = None
    ):
        if isinstance(text, str):
            text = [text]

        response = requests.post(
            f"{self.api_url}/api/embed",
            json={
                "model": self.embedding_model_id,
                "input": [self.process_text(t) for t in text]
            }
        )

        response.raise_for_status()

        return response.json()["embeddings"]

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": prompt
        }