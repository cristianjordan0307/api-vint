"""
dependencies.py — Dependencias inyectables de FastAPI.

Provee autenticación JWT y verificación de rol ADMIN
para proteger los endpoints de la API.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase_client import get_admin_client

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Extrae el JWT del header Authorization, lo verifica con Supabase Auth.
    Retorna el objeto user si es válido, sino lanza 401.
    """
    token = credentials.credentials
    try:
        client = get_admin_client()
        response = client.auth.get_user(token)
        if not response or not response.user:
            raise ValueError("No user")
        return response.user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado. Inicia sesión nuevamente.",
        )


async def get_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Extrae el token raw del header Authorization."""
    return credentials.credentials


async def verify_admin(user=Depends(get_current_user)):
    """
    Verifica que el usuario autenticado tenga rol ADMIN.
    Consulta seguridad.usuarios → seguridad.roles.
    """
    client = get_admin_client()

    # Buscar el id_rol del usuario
    user_resp = (
        client.schema("seguridad")
        .from_("usuarios")
        .select("id_rol")
        .eq("id_auth_supabase", user.id)
        .single()
        .execute()
    )

    if not user_resp.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador.",
        )

    # Buscar el nombre del rol
    rol_resp = (
        client.schema("seguridad")
        .from_("roles")
        .select("nombre")
        .eq("id_rol", user_resp.data["id_rol"])
        .single()
        .execute()
    )

    if not rol_resp.data or rol_resp.data.get("nombre") != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador.",
        )

    return user


async def resolve_id_usuario(email: str) -> int | None:
    """Resuelve el id_usuario (integer) a partir del correo, usando la función RPC."""
    client = get_admin_client()
    try:
        resp = client.rpc("get_id_usuario_por_correo", {"p_correo": email}).execute()
        if resp.data is not None:
            return int(resp.data)
    except Exception:
        pass
    return None
