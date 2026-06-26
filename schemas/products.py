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
    image_url: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    condition: Optional[str] = None
    brand: Optional[str] = None
    status: Optional[str] = None


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
    condition: Optional[str] = None
    brand: Optional[str] = None


class ProductDelete(BaseModel):
    # Acepta tanto strings como ints para máxima compatibilidad con el frontend
    ids: list[str]
