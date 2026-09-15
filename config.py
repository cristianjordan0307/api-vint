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
    FRONTEND_URL: str = "https://vint-project-git-develop-elbrayanf022-6820s-projects.vercel.app/"
    ANTHROPIC_API_KEY: str | None = None
    MERCADOPAGO_ACCESS_TOKEN: str | None = None

    # Tasa de comisión que VINT retiene sobre las ventas válidas de un vendedor.
    # No hay todavía una tasa de negocio confirmada en ningún otro lugar del código;
    # 0.15 (15%) es un valor de referencia. Ajustar aquí cuando el negocio la confirme.
    VINT_COMISION_PORCENTAJE: float = 0.15

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
