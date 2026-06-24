"""
schemas/products.py — Modelos Pydantic para el CRUD de productos.
"""

from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    price: float
    category: str | None = None
    image_url: str | None = None
    size: str | None = None
    color: str | None = None
    gender: str | None = None
    condition: str | None = None
    status: str | None = None


class ProductUpdate(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    price: float | None = None
    status: str | None = None


class ProductDelete(BaseModel):
    ids: list[int]
