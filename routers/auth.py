"""
routers/auth.py — Cambio de contraseña.

Migrado de: src/app/api/auth/change-password/route.ts
"""

import re
from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_user, get_token
from supabase_client import get_admin_client, get_anon_client
from schemas.auth import ChangePasswordPayload

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/change-password")
async def change_password(
    body: ChangePasswordPayload,
    user=Depends(get_current_user),
    token: str = Depends(get_token),
):
    """
    Cambia la contraseña del usuario autenticado.
    Valida la contraseña actual y la fortaleza de la nueva.
    """
    # Validar fortaleza
    if len(body.newPassword) < 8:
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña debe tener al menos 8 caracteres.",
        )
    if not re.search(r"[A-Z]", body.newPassword):
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña debe incluir al menos una letra mayúscula.",
        )
    if not re.search(r"[0-9]", body.newPassword):
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña debe incluir al menos un número.",
        )

    # Verificar contraseña actual
    anon = get_anon_client()
    try:
        anon.auth.sign_in_with_password({
            "email": user.email,
            "password": body.currentPassword,
        })
    except Exception:
        raise HTTPException(
            status_code=403,
            detail="La contraseña actual es incorrecta.",
        )

    # Actualizar contraseña
    admin = get_admin_client()
    try:
        admin.auth.admin.update_user_by_id(user.id, {"password": body.newPassword})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al actualizar la contraseña: {e}",
        )

    return {"success": True, "message": "Contraseña actualizada correctamente."}
