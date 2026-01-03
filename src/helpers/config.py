from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):

    APP_NAME: str
    APP_VERSION:  str
    OPENAI_API_KEY: str
    FILE_MAX_SIZE:int
    FILE_ALLOWED_TYPES:list
    FILE_DEFAULT_CHUNK_SIZE: int


    
    class config:
       env_file = ".env"
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


def get_settings():
   return Settings()