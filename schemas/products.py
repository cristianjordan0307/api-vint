"""
schemas/products.py — Modelos Pydantic para el CRUD de productos.
"""

from pydantic import BaseModel
from typing import Optional


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    category: Optional[str] = None
    category_id: Optional[int] = None
    brand: Optional[str] = None
    brand_id: Optional[int] = None
    otra_marca: Optional[str] = None  # Texto de marca personalizada
    image_url: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    id_estado_prenda: Optional[int] = None  # ID de catalogo.estados_prenda
    condition: Optional[str] = None         # Mantener por retrocompatibilidad
    status: Optional[str] = "DISPONIBLE"


class ProductUpdate(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    status: Optional[str] = None
    image_url: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    id_estado_prenda: Optional[int] = None  # ID de catalogo.estados_prenda
    condition: Optional[str] = None         # Mantener por retrocompatibilidad
    brand: Optional[str] = None
    brand_id: Optional[int] = None
    otra_marca: Optional[str] = None  # Texto de marca personalizada
    category: Optional[str] = None
    category_id: Optional[int] = None


class ProductDelete(BaseModel):
    # Acepta tanto strings como ints para máxima compatibilidad con el frontend
    ids: list[str]


class ImagenCreate(BaseModel):
    url_imagen: str
    es_principal: bool = False
    orden: int = 0
