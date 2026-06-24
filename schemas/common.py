"""
schemas/common.py — Modelos genéricos compartidos.
"""

from pydantic import BaseModel
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Respuesta genérica de la API, compatible con el formato del frontend."""
    success: bool
    message: str
    data: T | None = None
