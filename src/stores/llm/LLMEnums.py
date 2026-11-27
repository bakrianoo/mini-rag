from enum import Enum
 
 
class LLMEnums(Enum):
    GEMINI = "GEMINI"
 
class GeminiEnums(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
 
 
class DocumentTypeEnum(Enum):
    DOCUMENT = "document"
    QUERY = "query"