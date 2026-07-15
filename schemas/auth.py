"""
schemas/auth.py — Modelos Pydantic para autenticación y usuarios.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import date, timedelta


# ── Registro ─────────────────────────────────────────────────────────────────

class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    primer_nombre: str = Field(..., min_length=3, max_length=30)
    segundo_nombre: str | None = Field(default=None, max_length=30)
    primer_apellido: str = Field(..., min_length=3, max_length=30)
    segundo_apellido: str | None = Field(default=None, max_length=30)
    telefono: str | None = Field(default=None, pattern=r"^\d{10}$")
    genero: str | None = Field(default=None)
    fecha_nacimiento: str | None = Field(default=None)
    role: str = Field(default="comprador")

    @field_validator("primer_nombre", "primer_apellido")
    @classmethod
    def validate_name_required(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"[A-Za-záéíóúÁÉÍÓÚñÑ]+", v):
            raise ValueError(
                "Solo se permiten letras (incluyendo tildes y ñ). "
                "Mínimo 3, máximo 30 caracteres."
            )
        return v

    @field_validator("segundo_nombre", "segundo_apellido")
    @classmethod
    def validate_name_optional(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        import re
        if not re.fullmatch(r"[A-Za-záéíóúÁÉÍÓÚñÑ]+", v):
            raise ValueError(
                "Solo se permiten letras (incluyendo tildes y ñ)."
            )
        return v

    @field_validator("genero")
    @classmethod
    def validate_genero(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        allowed = ("Hombre", "Mujer", "Prefiero no decirlo")
        if v not in allowed:
            raise ValueError(
                f"Género debe ser uno de: {', '.join(allowed)}."
            )
        return v

    @field_validator("fecha_nacimiento")
    @classmethod
    def validate_fecha_nacimiento(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        try:
            parsed = date.fromisoformat(v)
        except ValueError:
            raise ValueError("Fecha de nacimiento inválida. Use formato YYYY-MM-DD.")
        today = date.today()
        if parsed > today:
            raise ValueError("La fecha de nacimiento no puede ser en el futuro.")
        if parsed < today - timedelta(days=365 * 120):
            raise ValueError("La fecha de nacimiento no es válida.")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("comprador", "vendedor"):
            raise ValueError("El rol debe ser 'comprador' o 'vendedor'.")
        return v


class RegisterResponse(BaseModel):
    success: bool
    message: str
    user_id: str | None = None


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    success: bool
    access_token: str
    refresh_token: str
    user_id: str
    email: str


# ── Cambio de contraseña ──────────────────────────────────────────────────────

class ChangePasswordPayload(BaseModel):
    currentPassword: str
    newPassword: str = Field(..., min_length=8)


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str


# ── Perfil ────────────────────────────────────────────────────────────────────

class UpdateProfilePayload(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    apellido: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=20)


class ProfileResponse(BaseModel):
    user_id: str
    email: str
    nombre: str | None = None
    apellido: str | None = None
    telefono: str | None = None
    rol: str | None = None
