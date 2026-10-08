from .LLMEnums import LLMEnums
from .providers import OpenAIProvider,CohereProvider

class LLMProviderFactory:
    def __init__(self,config:dict):
        self.config = config

    def create(self,provider: str):
        if provider == LLMEnums.OPENAI.value:
            return OpenAIProvider(
                api_key=self.config.OPENAI_API_KEY,
                base_url=self.config.OPENAI_BASE_URL,
                default_input_max_characters=self.config.DEDAULT_INPUT_MAX_CHARACTERS,
                default_generation_max_tokens=self.config.DEFAULT_GENERATION_MAX_CHARACTERS,
                default_temperature=self.config.DEFAULT_TEMPRETURE
            )

        elif provider == LLMEnums.COHERE.value:
            return CohereProvider(
                api_key=self.config.COHERE_API_KEY,
                default_input_max_characters=self.config.DEDAULT_INPUT_MAX_CHARACTERS,
                default_generation_max_tokens=self.config.DEFAULT_GENERATION_MAX_CHARACTERS,
                default_temperature=self.config.DEFAULT_TEMPRETURE
            )
        return None

