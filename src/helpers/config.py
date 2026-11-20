from pydantic_settings import BaseSettings
from typing import List, Optional

from sqlalchemy.engine.url import make_url

def build_url(raw_url: str, driver: str):
    url = make_url(raw_url)
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)

    if driver == "asyncpg":
        url = url.set(drivername="postgresql+asyncpg")
        if sslmode in ("require", "verify-ca", "verify-full"):
            query["ssl"] = "require"
    else:
        url = url.set(drivername="postgresql+psycopg")
        if sslmode:
            query["sslmode"] = sslmode

    return url.set(query=query)
class Settings(BaseSettings):

    APP_NAME: str
    APP_VERSION: str
    
    FILE_ALLOWED_TYPES: list
    FILE_MAX_SIZE: int
    FILE_DEFAULT_CHUNK_SIZE: int

    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_MAIN_DATABASE: str

    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str


    GENERATION_MODEL_ID_LITERAL: Optional[List[str]] = None

    GENERATION_MODEL_ID: str = None
    EMBEDDING_MODEL_ID: str = None
    EMBEDDING_MODEL_SIZE: int = None
    INPUT_DEFAULT_MAX_CHARACTERS: int = None
    GENERATION_DEFAULT_MAX_TOKENS: int = None
    GENERATION_DEFAULT_TEMPERATURE: float = None

    VECTOR_DB_BACKEND_LITERAL: List[str] = None
    VECTOR_DB_BACKEND : str
    VECTOR_DB_PATH : str
    VECTOR_DB_DISTANCE_METHOD: str = None
    VECTOR_DB_PGVEC_INDEX_THRESHOLD: int = 100

    PRIMARY_LANG: str = "en"
    DEFAULT_LANG: str = "en"

    # Celery Configuration
    CELERY_BROKER_URL: str = None
    CELERY_RESULT_BACKEND: str = None
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_TASK_TIME_LIMIT: int = 600
    CELERY_TASK_ACKS_LATE: bool = True
    CELERY_WORKER_CONCURRENCY: int = 2
    CELERY_FLOWER_PASSWORD: str = None

    # Vllm Configuration
    VISION_MODEL_ID: str = "gemini-3.5-flash-lite"
    BOARD_REDIS_URL: Optional[str] = None
    BOARD_SESSION_TTL: int = 86400
    


    GEMINI_API_KEY: str
    class Config:
        env_file = ".env"

def get_settings():
    return Settings()
