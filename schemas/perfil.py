"""
schemas/perfil.py — Modelos Pydantic para endpoints de Perfil y Vendedores Públicos.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ActualizarPerfilInput(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=120)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    descripcion: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[str] = None
    ciudad: Optional[str] = Field(None, max_length=100)


class PerfilPublicoData(BaseModel):
    id_usuario: int
    id_auth_supabase: Optional[str] = None
    nombre: str
    username: str
    email: str
    avatar_url: Optional[str] = None
    descripcion: str
    ciudad: str
    fecha_registro: Optional[str] = None
    ventas_exitosas: int = 0
    prendas_en_venta: int = 0
    calificacion: float = 5.0
    total_resenas: int = 0


class PerfilPublicoResponse(BaseModel):
    success: bool = True
    data: PerfilPublicoData


class ActualizarPerfilResponse(BaseModel):
    success: bool = True
    message: str = "Perfil actualizado correctamente"
    data: Dict[str, Any]
