from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    database_url: str
    ai_vision_api_key: str = ""  # optional until AI-3.1

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()