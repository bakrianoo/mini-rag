from .LLMEnums import LLMEnums
from .providers import OllamaProvider, GeminiProvider
 
 
class LLMProviderFactory:
    def __init__(self, config: dict):
        self.config = config
 
    def create(self, provider: str):
 
 
        if provider == LLMEnums.OLLAMA.value:
            return OllamaProvider(
                api_key=self.config.OLLAMA_API_KEY,
                api_url=self.config.OLLAMA_API_URL,
                default_input_max_characters=self.config.INPUT_DEFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE,
            )
 
        if provider == LLMEnums.GEMINI.value:
            return GeminiProvider(
                api_key=self.config.GEMINI_API_KEY,
                default_input_max_characters=self.config.INPUT_DEFAULT_MAX_CHARACTERS,
                default_generation_max_output_tokens=self.config.GENERATION_DEFAULT_MAX_TOKENS,
                default_generation_temperature=self.config.GENERATION_DEFAULT_TEMPERATURE,
            )
 
        return None
 