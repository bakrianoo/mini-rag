from ..LLMInterface import LLMInterface
from ..LLMEnums import CohereEnums
import cohere
import logging
from ..LLMEnums import CohereEnums
class CohereProvider(LLMInterface):
    def __init__(self,api_key:str,
                 default_input_max_characters:int=1000,
                 default_generation_max_tokens:int=1000,
                 default_temperature:float=0.1):
        self.api_key = api_key
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_tokens = default_generation_max_tokens
        self.default_temperature = default_temperature

        self.generation_model_id = None

        self.embedding_model_id = None
        self.embedding_size = None

        self.client = cohere.Client(api_key=self.api_key)

        self.logger = logging.getLogger(__name__)

        self.enums = CohereEnums

    def set_generation_model(self,model_id:str):
        self.generation_model_id = model_id
    
    def set_embedding_model(self,model_id:str,embedding_size:int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self,text:str):
        return text[:self.default_input_max_characters].strip()

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
        response = self.client.chat(
            model=self.generation_model_id,
            chat_history=chat_history,
            message=self.process_text(prompt),
            temperature= temperature,
            max_tokens=max_output_tokens
        )
        if not response or not response.text:
            self.logger.error('Error while generating text with cohere')
            return None
        return response.text
             
    def construct_prompt(self,prompt: str,role: str):
        return {
            'role':role,
            'text':self.process_text(prompt)
        }

    def embed_texts(self, texts: list, document_type=None):
        if not self.client:
            self.logger.error('cohere client was not set')
            return None

        if not self.embedding_model_id:
            self.logger.error('cohere embedding model was not set')
            return None

        input_type = CohereEnums.DOCUMENT.value

        if document_type == CohereEnums.QUERY.value:
            input_type = CohereEnums.QUERY.value

        response = self.client.embed(
            model=self.embedding_model_id,
            input_type=input_type,
            texts=texts,
            embedding_types=['float']
        )

        if (
            not response
            or not response.embeddings
            or not response.embeddings.float_
        ):
            self.logger.error('error while embedding texts with cohere')
            return None

        return response.embeddings.float_

            