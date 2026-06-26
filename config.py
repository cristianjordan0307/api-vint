"""
config.py — Configuración centralizada con pydantic-settings.
Lee las variables de entorno desde .env automáticamente.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    FRONTEND_URL: str = "http://localhost:3000"
    ANTHROPIC_API_KEY: str | None = None
    MERCADOPAGO_ACCESS_TOKEN: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
