"""
routers/perfil.py — Endpoints para gestión de perfil y consulta pública de vendedores.
"""

import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from dependencies import get_current_user
from supabase_client import get_admin_client
from schemas.perfil import (
    ActualizarPerfilInput,
    PerfilPublicoResponse,
    ActualizarPerfilResponse,
)

router = APIRouter(prefix="/api/perfil", tags=["Perfil"])


def is_valid_uuid(val: str) -> bool:
    """Verifica si un string tiene formato UUID válido."""
    try:
        uuid.UUID(str(val).strip())
        return True
    except (ValueError, AttributeError, TypeError):
        return False


async def consultar_perfil_publico_vendedor(identifier: str) -> Dict[str, Any]:
    """
    Lógica compartida para consultar los datos públicos y estadísticas
    de un vendedor por username, id_auth_supabase (UUID) o id_usuario.
    """
    clean_id = identifier.lstrip("@").strip()
    if not clean_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendedor no encontrado",
        )

    client = get_admin_client()
    user = None

    # 1. Búsqueda según formato del identificador
    if is_valid_uuid(clean_id):
        resp = (
            client.schema("seguridad")
            .from_("usuarios")
            .select("id_usuario, id_auth_supabase, correo, primer_nombre, primer_apellido, username, avatar_url, descripcion, ciudad, fecha_registro")
            .eq("id_auth_supabase", clean_id)
            .execute()
        )
        if resp.data:
            user = resp.data[0]

    elif clean_id.isdigit():
        resp = (
            client.schema("seguridad")
            .from_("usuarios")
            .select("id_usuario, id_auth_supabase, correo, primer_nombre, primer_apellido, username, avatar_url, descripcion, ciudad, fecha_registro")
            .eq("id_usuario", int(clean_id))
            .execute()
        )
        if resp.data:
            user = resp.data[0]

    # Si no se encontró por UUID o ID numérico, buscar por username (case insensitive)
    if not user:
        resp = (
            client.schema("seguridad")
            .from_("usuarios")
            .select("id_usuario, id_auth_supabase, correo, primer_nombre, primer_apellido, username, avatar_url, descripcion, ciudad, fecha_registro")
            .ilike("username", clean_id)
            .execute()
        )
        if resp.data:
            user = resp.data[0]

    # Fallback adicional: buscar por correo si clean_id tiene formato de email
    if not user and "@" in identifier:
        resp = (
            client.schema("seguridad")
            .from_("usuarios")
            .select("id_usuario, id_auth_supabase, correo, primer_nombre, primer_apellido, username, avatar_url, descripcion, ciudad, fecha_registro")
            .ilike("correo", identifier.strip())
            .execute()
        )
        if resp.data:
            user = resp.data[0]

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendedor no encontrado",
        )

    user_id = user.get("id_usuario")
    auth_id = user.get("id_auth_supabase")
    username_val = user.get("username")

    # 2. Conteo de ventas exitosas:
    # a) Pedidos completados con vendedor_id = auth_id
    ventas_pedidos_count = 0
    if auth_id:
        try:
            pedidos_resp = (
                client.schema("public")
                .from_("pedidos")
                .select("id", count="exact")
                .eq("vendedor_id", str(auth_id))
                .eq("estado", "completado")
                .execute()
            )
            ventas_pedidos_count = pedidos_resp.count or len(pedidos_resp.data or [])
        except Exception:
            ventas_pedidos_count = 0

    # b) Prendas marcadas como VENDIDA
    prendas_vendidas_count = 0
    if user_id:
        try:
            prendas_v_resp = (
                client.schema("catalogo")
                .from_("prendas")
                .select("id_prenda", count="exact")
                .eq("id_usuario", user_id)
                .eq("estado_publicacion", "VENDIDA")
                .execute()
            )
            prendas_vendidas_count = prendas_v_resp.count or len(prendas_v_resp.data or [])
        except Exception:
            prendas_vendidas_count = 0

    total_ventas_exitosas = ventas_pedidos_count + prendas_vendidas_count

    # 3. Conteo de prendas disponibles en venta
    prendas_disponibles_count = 0
    if user_id:
        try:
            prendas_d_resp = (
                client.schema("catalogo")
                .from_("prendas")
                .select("id_prenda", count="exact")
                .eq("id_usuario", user_id)
                .eq("estado_publicacion", "DISPONIBLE")
                .execute()
            )
            prendas_disponibles_count = prendas_d_resp.count or len(prendas_d_resp.data or [])
        except Exception:
            prendas_disponibles_count = 0

    # 4. Calificación promedio y total de comentarios
    promedio_calif = 5.0
    total_resenas = 0
    try:
        if auth_id and username_val:
            calif_resp = (
                client.schema("public")
                .from_("vendedor_comentarios")
                .select("calificacion")
                .or_(f"vendedor_id.eq.{username_val},vendedor_id.eq.{auth_id}")
                .execute()
            )
        elif auth_id:
            calif_resp = (
                client.schema("public")
                .from_("vendedor_comentarios")
                .select("calificacion")
                .eq("vendedor_id", str(auth_id))
                .execute()
            )
        elif username_val:
            calif_resp = (
                client.schema("public")
                .from_("vendedor_comentarios")
                .select("calificacion")
                .eq("vendedor_id", str(username_val))
                .execute()
            )
        else:
            calif_resp = None

        if calif_resp and calif_resp.data:
            calificaciones = [
                float(row["calificacion"])
                for row in calif_resp.data
                if row.get("calificacion") is not None
            ]
            if calificaciones:
                total_resenas = len(calificaciones)
                promedio_calif = sum(calificaciones) / total_resenas
    except Exception:
        promedio_calif = 5.0
        total_resenas = 0

    nombre_completo = f"{user.get('primer_nombre') or ''} {user.get('primer_apellido') or ''}".strip()

    return {
        "success": True,
        "data": {
            "id_usuario": user_id,
            "id_auth_supabase": str(auth_id) if auth_id else None,
            "nombre": nombre_completo,
            "username": username_val or clean_id,
            "email": user.get("correo"),
            "avatar_url": user.get("avatar_url"),
            "descripcion": user.get("descripcion") or "",
            "ciudad": user.get("ciudad") or "Colombia",
            "fecha_registro": user.get("fecha_registro"),
            "ventas_exitosas": total_ventas_exitosas,
            "prendas_en_venta": prendas_disponibles_count,
            "calificacion": round(float(promedio_calif), 1),
            "total_resenas": total_resenas,
        },
    }


# ── Endpoint Público: GET /api/perfil/vendedor/{identifier}/publico ──────────

@router.get("/vendedor/{identifier}/publico", response_model=PerfilPublicoResponse)
async def get_perfil_publico_vendedor(identifier: str):
    """
    Retorna el perfil público y las estadísticas reales del vendedor.
    Acceso público sin requerir token JWT.
    """
    return await consultar_perfil_publico_vendedor(identifier)


# ── Endpoint Autenticado: GET /api/perfil/me ──────────────────────────────────

@router.get("/me")
async def get_mi_perfil(user=Depends(get_current_user)):
    """
    Retorna la información del perfil del usuario autenticado.
    """
    client = get_admin_client()
    resp = (
        client.schema("seguridad")
        .from_("usuarios")
        .select("id_usuario, id_auth_supabase, correo, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido, username, avatar_url, descripcion, ciudad, fecha_registro")
        .or_(f"id_auth_supabase.eq.{user.id},correo.eq.{user.email}")
        .execute()
    )

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado en la base de datos",
        )

    user_data = resp.data[0]
    nombre_completo = f"{user_data.get('primer_nombre') or ''} {user_data.get('primer_apellido') or ''}".strip()

    return {
        "success": True,
        "data": {
            **user_data,
            "nombre": nombre_completo,
        },
    }


# ── Endpoint Autenticado: PUT /api/perfil/me ──────────────────────────────────

@router.put("/me", response_model=ActualizarPerfilResponse)
async def actualizar_mi_perfil(
    body: ActualizarPerfilInput,
    user=Depends(get_current_user),
):
    """
    Actualiza los datos de perfil del usuario autenticado en seguridad.usuarios.
    Valida que el username sea único y formatea los nombres.
    """
    client = get_admin_client()

    # 1. Obtener usuario actual
    resp = (
        client.schema("seguridad")
        .from_("usuarios")
        .select("id_usuario, id_auth_supabase, correo, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido, username, avatar_url, descripcion, ciudad")
        .or_(f"id_auth_supabase.eq.{user.id},correo.eq.{user.email}")
        .execute()
    )

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado en el sistema",
        )

    current_user_row = resp.data[0]
    current_id_usuario = current_user_row["id_usuario"]

    # 2. Validar username único
    clean_user = None
    if body.username is not None:
        clean_user = body.username.lstrip("@").strip().lower()
        if len(clean_user) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El username debe tener al menos 3 caracteres.",
            )

        exists_resp = (
            client.schema("seguridad")
            .from_("usuarios")
            .select("id_usuario")
            .ilike("username", clean_user)
            .neq("id_usuario", current_id_usuario)
            .execute()
        )

        if exists_resp.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El username '@{clean_user}' ya está en uso",
            )

    # 3. Separar nombre completo si viene provisto
    update_data: Dict[str, Any] = {}
    if body.nombre is not None:
        parts = body.nombre.strip().split()
        p_nom = parts[0] if parts else ""
        s_nom = parts[1] if len(parts) >= 3 else ""
        p_ape = parts[2] if len(parts) >= 3 else (parts[1] if len(parts) == 2 else "")
        s_ape = " ".join(parts[3:]) if len(parts) >= 4 else ""

        if p_nom:
            update_data["primer_nombre"] = p_nom
        update_data["segundo_nombre"] = s_nom or None
        if p_ape:
            update_data["primer_apellido"] = p_ape
        update_data["segundo_apellido"] = s_ape or None

    if clean_user is not None:
        update_data["username"] = clean_user

    if body.descripcion is not None:
        update_data["descripcion"] = body.descripcion.strip()

    if body.avatar_url is not None:
        update_data["avatar_url"] = body.avatar_url.strip()

    if body.ciudad is not None:
        update_data["ciudad"] = body.ciudad.strip()

    # Si no había id_auth_supabase vinculado, asociarlo ahora
    if not current_user_row.get("id_auth_supabase") and user.id:
        update_data["id_auth_supabase"] = str(user.id)

    # 4. Actualizar en BD si hay campos
    if update_data:
        update_resp = (
            client.schema("seguridad")
            .from_("usuarios")
            .update(update_data)
            .eq("id_usuario", current_id_usuario)
            .execute()
        )
        updated_data = update_resp.data[0] if update_resp.data else {**current_user_row, **update_data}
    else:
        updated_data = current_user_row

    nombre_actualizado = f"{updated_data.get('primer_nombre') or ''} {updated_data.get('primer_apellido') or ''}".strip()

    return {
        "success": True,
        "message": "Perfil actualizado correctamente",
        "data": {
            "id_usuario": updated_data.get("id_usuario"),
            "id_auth_supabase": str(updated_data.get("id_auth_supabase")) if updated_data.get("id_auth_supabase") else None,
            "nombre": nombre_actualizado,
            "primer_nombre": updated_data.get("primer_nombre"),
            "segundo_nombre": updated_data.get("segundo_nombre"),
            "primer_apellido": updated_data.get("primer_apellido"),
            "segundo_apellido": updated_data.get("segundo_apellido"),
            "username": updated_data.get("username"),
            "email": updated_data.get("correo"),
            "avatar_url": updated_data.get("avatar_url"),
            "descripcion": updated_data.get("descripcion"),
            "ciudad": updated_data.get("ciudad"),
        },
    }
