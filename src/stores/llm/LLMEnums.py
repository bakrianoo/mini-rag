from enum import Enum

class LLMEnums(Enum):
    OPENAI = 'OPENAI'
    COHERE = 'COHERE'


class OpenAIEnum(Enum):
    SYSTEM = 'system'
    USER = 'user'
    ASSISTANT = 'assistant'
    DOCUMENT = 'document'
    QUERY = 'query'
    
class CohereEnums(Enum):
    SYSTEM = 'SYSTEM'
    USER = 'USER'
    ASSISTANT = 'CHATBOT'

    DOCUMENT = 'search_document'
    QUERY = 'search_query'

