"""
schemas/admin.py — Modelos Pydantic para la gestión administrativa.
"""

from pydantic import BaseModel


class UserPatch(BaseModel):
    userId: int
    activo: bool


class RoleCreate(BaseModel):
    nombre: str


class RolePatch(BaseModel):
    id_rol: int
    nombre: str


class RoleAssign(BaseModel):
    userId: int
    roleId: int


class PermissionAssign(BaseModel):
    roleId: int
    permissionIds: list[int]


class CategoryCreate(BaseModel):
    nombre: str
    descripcion: str | None = None


class CategoryUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None


class BrandCreate(BaseModel):
    nombre: str


class BrandUpdate(BaseModel):
    nombre: str

