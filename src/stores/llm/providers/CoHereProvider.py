from ..LLMInterface import LLMInterface
from ..LLMEnums import CoHereEnums, DocumentTypeEnum
import cohere
import logging
from typing import List, Union


class CoHereProvider(LLMInterface):

    def __init__(
        self,
        api_key: str,
        default_input_max_characters: int = 1000,
        default_generation_max_output_tokens: int = 8000,
        default_generation_temperature: float = 0.1,
    ):
        self.api_key = api_key

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.client = cohere.Client(api_key=self.api_key)

        self.enums = CoHereEnums
        self.logger = logging.getLogger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def _normalize_history(self, chat_history: list) -> list:
        role_map = {
            "system": CoHereEnums.SYSTEM.value,
            "user": CoHereEnums.USER.value,
            "assistant": CoHereEnums.ASSISTANT.value,
            CoHereEnums.SYSTEM.value: CoHereEnums.SYSTEM.value,
            CoHereEnums.USER.value: CoHereEnums.USER.value,
            CoHereEnums.ASSISTANT.value: CoHereEnums.ASSISTANT.value,
        }

        normalized = []
        for message in chat_history or []:
            if not isinstance(message, dict):
                continue

            role = role_map.get((message.get("role") or "").strip(), None)
            text = message.get("text")
            if text is None:
                text = message.get("content")

            if not role or not isinstance(text, str) or not text.strip():
                continue

            normalized.append({"role": role, "text": text})

        return normalized

    def generate_text(
        self,
        prompt: str,
        chat_history: list = None,
        max_output_tokens: int = None,
        temperature: float = None,
        response_format: str = None,
    ):
        if not self.client:
            self.logger.error("CoHere client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for CoHere was not set")
            return None

        max_output_tokens = max_output_tokens or self.default_generation_max_output_tokens
        temperature = (
            temperature
            if temperature is not None
            else self.default_generation_temperature
        )

        request = {
            "model": self.generation_model_id,
            "chat_history": self._normalize_history(chat_history),
            "message": prompt,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }

        if response_format == "json":
            prompt = (
                prompt
                + "\n\nReturn a valid JSON object only, with no markdown."
            )
            request["message"] = prompt

        response = self.client.chat(**request)

        if not response or not response.text:
            self.logger.error("Error while generating text with CoHere")
            return None

        return response.text

    def embed_text(self, text: Union[str, List[str]], document_type: str = None):
        if not self.client:
            self.logger.error("CoHere client was not set")
            return None

        if isinstance(text, str):
            text = [text]

        if not self.embedding_model_id:
            self.logger.error("Embedding model for CoHere was not set")
            return None

        input_type = CoHereEnums.DOCUMENT.value
        if document_type in (
            DocumentTypeEnum.QUERY,
            DocumentTypeEnum.QUERY.value,
        ):
            input_type = CoHereEnums.QUERY.value

        response = self.client.embed(
            model=self.embedding_model_id,
            texts=[self.process_text(t) for t in text],
            input_type=input_type,
            embedding_types=["float"],
        )

        if (
            not response
            or not response.embeddings
            or not response.embeddings.float
        ):
            self.logger.error("Error while embedding text with CoHere")
            return None

        return [item for item in response.embeddings.float]

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "text": prompt,
        }
