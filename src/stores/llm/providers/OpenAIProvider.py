from ..LLMInterface import LLMInterface
from ..LLMEnums import OpenAIEnums
from openai import OpenAI
import logging
from typing import List, Union


class OpenAIProvider(LLMInterface):

    def __init__(
        self,
        api_key: str,
        api_url: str = None,
        default_input_max_characters: int = 4000,
        default_generation_max_output_tokens: int = 8000,
        default_generation_temperature: float = 0.1,
    ):
        self.api_key = api_key
        self.api_url = api_url

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_url if self.api_url and len(self.api_url) else None,
        )

        self.enums = OpenAIEnums
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
    ):
        if not self.client:
            self.logger.error("OpenAI client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for OpenAI was not set")
            return None

        max_output_tokens = max_output_tokens or self.default_generation_max_output_tokens
        temperature = (
            temperature
            if temperature is not None
            else self.default_generation_temperature
        )

        messages = list(chat_history or [])
        messages.append(
            self.construct_prompt(prompt=prompt, role=OpenAIEnums.USER.value)
        )

        request = {
            "model": self.generation_model_id,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
        }

        if response_format == "json":
            request["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**request)

        if (
            not response
            or not response.choices
            or not response.choices[0].message
        ):
            self.logger.error("Error while generating text with OpenAI")
            return None

        return response.choices[0].message.content

    def embed_text(self, text: Union[str, List[str]], document_type: str = None):
        if not self.client:
            self.logger.error("OpenAI client was not set")
            return None

        if isinstance(text, str):
            text = [text]

        if not self.embedding_model_id:
            self.logger.error("Embedding model for OpenAI was not set")
            return None

        response = self.client.embeddings.create(
            model=self.embedding_model_id,
            input=text,
        )

        if (
            not response
            or not response.data
            or not response.data[0].embedding
        ):
            self.logger.error("Error while embedding text with OpenAI")
            return None

        return [rec.embedding for rec in response.data]

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": prompt,
        }
