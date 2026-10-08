from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):

    APP_NAME: str
    APP_VERSION: str
    FILE_ALLOWED_TYPES: list
    FILE_MAX_SIZE: int
    FILE_DEFAULT_CHUNK_SIZE: int
    MONGODB_URL: str
    MOGODB_DATABASE: str
    GENERATION_BACKEND: str
    EMBEDDING_BACKEND : str


    OPENAI_API_KEY: str = None
    OPENAI_BASE_URL: str = None

    COHERE_API_KEY : str = None

    GENERATION_MODEL_ID : str = None
    EMBEDDING_MODEL_ID : str = None
    EMBEDDING_MODEL_SIZE : int = None


    DEDAULT_INPUT_MAX_CHARACTERS : int = None
    DEFAULT_GENERATION_MAX_CHARACTERS : int = None
    DEFAULT_TEMPRETURE : float = None

    # Vector DB
    VECTOR_DB_BACKEND :str
    VECTOR_DB_PATH : str
    VECTOR_DB_DISTANCE_METHOD : str = None

    # Template Configs
    DEFAULT_LANGUAGE : str

    
    class Config:
        env_file = '.env'


def get_settings():
    return Settings()