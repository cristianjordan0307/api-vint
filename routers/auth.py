"""
routers/auth.py — Registro de usuarios y cambio de contraseña.

Endpoints:
  POST /api/auth/register        → Crear cuenta nueva
  POST /api/auth/change-password → Cambiar contraseña (requiere auth)
"""

import re
from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_user, get_token
from supabase_client import get_admin_client, get_anon_client
from schemas.auth import RegisterPayload, ChangePasswordPayload

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


# ═══════════════════════════════════════════════════════════════════════════════
#  REGISTRO
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/register")
async def register(body: RegisterPayload):
    """
    Registra un nuevo usuario en Supabase Auth.
    El trigger de la base de datos se encarga de crear el registro
    correspondiente en seguridad.usuarios con la metadata proporcionada.
    """
    # ── Validación de contraseña ──────────────────────────────────────────
    if not re.search(r"[A-Z]", body.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe incluir al menos una letra mayúscula.",
        )
    if not re.search(r"[0-9]", body.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe incluir al menos un número.",
        )

    # ── Determinar id_rol según el tipo de usuario ────────────────────────
    id_rol = 2 if body.role == "vendedor" else 3

    # ── Construir metadata para el trigger de Supabase ────────────────────
    user_metadata = {
        "full_name": f"{body.primer_nombre} {body.primer_apellido}".strip(),
        "primer_nombre": body.primer_nombre,
        "segundo_nombre": body.segundo_nombre or "",
        "primer_apellido": body.primer_apellido,
        "segundo_apellido": body.segundo_apellido or "",
        "telefono": body.telefono or "",
        "genero": body.genero or "",
        "fecha_nacimiento": body.fecha_nacimiento or "",
        "id_rol": id_rol,
        "role": body.role,
    }

    # ── Crear usuario en Supabase Auth ────────────────────────────────────
    anon = get_anon_client()
    try:
        result = anon.auth.sign_up({
            "email": body.email,
            "password": body.password,
            "options": {"data": user_metadata},
        })
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower():
            raise HTTPException(
                status_code=409,
                detail="Este correo electrónico ya está registrado.",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Error al crear el usuario: {error_msg}",
        )

    if not result.user:
        raise HTTPException(
            status_code=500,
            detail="No se pudo crear el usuario. Intente de nuevo.",
        )

    # ── Respuesta ─────────────────────────────────────────────────────────
    # Si Supabase requiere verificación de correo, no habrá sesión.
    needs_verification = result.session is None
    message = (
        "Cuenta creada. Revisa tu correo electrónico para verificar tu cuenta."
        if needs_verification
        else "Cuenta creada exitosamente."
    )

    return {
        "success": True,
        "message": message,
        "user_id": result.user.id,
        "email": result.user.email,
        "needs_verification": needs_verification,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CAMBIO DE CONTRASEÑA
# ═══════════════════════════════════════════════════════════════════════════════

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
