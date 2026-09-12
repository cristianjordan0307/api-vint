"""
schemas/pedidos.py — Modelos Pydantic para compras y pedidos simulados.
"""

from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any, Dict


class ItemCompra(BaseModel):
    id_prenda: int
    precio: float

    model_config = ConfigDict(extra="allow")


class DatosEnvio(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    direccion: str
    ciudad: Optional[str] = None
    info_adicional: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class CompraRequest(BaseModel):
    items: List[ItemCompra]
    envio: DatosEnvio | Dict[str, Any]
    costo_envio: Optional[float] = 15000.0

    model_config = ConfigDict(extra="allow")


class PedidoError(Exception):
    def __init__(self, status_code: int, error: str, code: str):
        self.status_code = status_code
        self.error = error
        self.code = code
