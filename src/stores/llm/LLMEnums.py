from enum import Enum


class LLMEnums(Enum):
    OLLAMA = "OLLAMA"


class OllamaEnums(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class DocumentTypeEnum(Enum):
    DOCUMENT = "document"
    QUERY = "query"