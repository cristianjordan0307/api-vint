from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False
    NEXT_PUBLIC_SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    NEXT_PUBLIC_SUPABASE_ANON_KEY: str
    ANTHROPIC_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()