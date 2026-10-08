from ..LLMInterface import LLMInterface
from ..LLMEnums import OpenAIEnum
from openai import OpenAI
import logging
from ..LLMEnums import OpenAIEnum
class OpenAIProvider(LLMInterface):
    def __init__(self,api_key:str,base_url:str,
                 default_input_max_characters:int=1000,
                 default_generation_max_tokens:int=1000,
                 default_temperature:float=0.1):
        self.api_key = api_key
        self.base_url = base_url
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_tokens = default_generation_max_tokens
        self.default_temperature = default_temperature

        self.generation_model_id = None

        self.embedding_model_id = None
        self.embedding_size = None

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        self.logger = logging.getLogger(__name__)

        self.enums = OpenAIEnum

    def set_generation_model(self,model_id:str):
        self.generation_model_id = model_id

    def set_embedding_model(self,model_id:str,embedding_size:int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def generate_text(self,prompt:str,
                          chat_history:list=[],
                          max_output_tokens:int=None,
                          temperature:float = None
                          ):
        if not self.client:
            self.logger.error('openai client was not set')
            return None

        
        max_output_tokens = max_output_tokens if max_output_tokens else self.default_generation_max_tokens
        temperature = temperature if temperature else self.default_temperature

        chat_history.append(
            self.construct_prompt(prompt=prompt,role=OpenAIEnum.USER.value)
        )

        response = self.client.chat.completions.create(
            model=self.generation_model_id,
            messages=chat_history,
            max_tokens= max_output_tokens,
            temperature=temperature
        )

        if not response or not response.choices or len(response.choices) == 0 or not response.choices[0].message:
            self.logger.error('error while generating text with openai')
            return None

        return response.choices[0].message.content

    def embed_texts(self, texts: list, document_type: str = None):

        if not self.client:
            self.logger.error('openai client was not set')
            return None

        if not self.embedding_model_id:
            self.logger.error('openai embedding model was not set')
            return None

        response = self.client.embeddings.create(
            model=self.embedding_model_id,
            input=texts
        )

        if not response or not response.data:
            self.logger.error('error while embedding texts with openai')
            return None

        return [item.embedding for item in response.data]


    def construct_prompt(self,prompt: str,role: str):
        return {
            'role':role,
            'content':self.process_text(prompt)
        }


    def process_text(self,text:str):
        return text[:self.default_input_max_characters].strip()