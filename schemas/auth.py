"""
schemas/auth.py — Modelos Pydantic para autenticación.
"""

from pydantic import BaseModel


class ChangePasswordPayload(BaseModel):
    currentPassword: str
    newPassword: str
