"""
routers/admin.py — Gestión de usuarios, roles y permisos (requiere ADMIN).

Migrado de:
  - src/app/api/admin/users/route.ts
  - src/app/api/admin/users/[id]/route.ts
  - src/app/api/admin/roles/route.ts
  - src/app/api/admin/roles/assign/route.ts
  - src/app/api/admin/permissions/route.ts
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from dependencies import verify_admin, get_current_user
from supabase_client import get_admin_client
from schemas.admin import (
    UserPatch,
    RoleCreate,
    RolePatch,
    RoleAssign,
    PermissionAssign,
    CategoryCreate,
    CategoryUpdate,
    BrandCreate,
    BrandUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ═══════════════════════════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/users")
async def list_users(
    search: str = "",
    role: str = "",
    status: str = "",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    admin=Depends(verify_admin),
):
    """Listar usuarios con búsqueda, filtros y paginación."""
    client = get_admin_client()
    offset = (page - 1) * limit

    query = (
        client.schema("seguridad")
        .from_("usuarios")
        .select(
            "id_usuario, id_auth_supabase, id_rol, primer_nombre, segundo_nombre, "
            "primer_apellido, segundo_apellido, correo, telefono, fecha_registro, "
            "activo, genero, roles!inner(nombre)",
            count="exact",
        )
    )

    if search:
        query = query.or_(
            f"primer_nombre.ilike.%{search}%,"
            f"primer_apellido.ilike.%{search}%,"
            f"correo.ilike.%{search}%"
        )

    if role:
        rol_resp = (
            client.schema("seguridad")
            .from_("roles")
            .select("id_rol")
            .eq("nombre", role.upper())
            .single()
            .execute()
        )
        if rol_resp.data:
            query = query.eq("id_rol", rol_resp.data["id_rol"])

    if status == "active":
        query = query.eq("activo", True)
    elif status == "inactive":
        query = query.eq("activo", False)

    query = query.order("fecha_registro", desc=True).range(offset, offset + limit - 1)
    resp = query.execute()

    usuarios = []
    for u in resp.data or []:
        nombre = " ".join(
            filter(None, [
                u.get("primer_nombre", ""),
                u.get("segundo_nombre", ""),
                u.get("primer_apellido", ""),
                u.get("segundo_apellido", ""),
            ])
        )
        usuarios.append({
            "id_usuario": u["id_usuario"],
            "id_auth_supabase": u["id_auth_supabase"],
            "nombre_completo": nombre,
            "correo": u["correo"],
            "telefono": u.get("telefono"),
            "rol": u.get("roles", {}).get("nombre", "SIN ROL") if u.get("roles") else "SIN ROL",
            "id_rol": u["id_rol"],
            "activo": u["activo"],
            "fecha_registro": u["fecha_registro"],
            "genero": u.get("genero"),
        })

    return {
        "success": True,
        "message": "Usuarios obtenidos.",
        "data": {
            "usuarios": usuarios,
            "total": resp.count or 0,
            "page": page,
            "limit": limit,
        },
    }


@router.patch("/users")
async def toggle_user(body: UserPatch, admin=Depends(verify_admin)):
    """Activar/desactivar un usuario."""
    client = get_admin_client()
    client.schema("seguridad").from_("usuarios").update(
        {"activo": body.activo}
    ).eq("id_usuario", body.userId).execute()

    estado_txt = "activado" if body.activo else "desactivado"
    return {"success": True, "message": f"Usuario {estado_txt} correctamente."}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    x_confirm_delete: str = Header(default=""),
    admin=Depends(verify_admin),
):
    """Eliminar un usuario permanentemente."""
    if x_confirm_delete != "true":
        raise HTTPException(
            status_code=400,
            detail="Debes confirmar la eliminación con el header x-confirm-delete: true.",
        )

    client = get_admin_client()

    # Buscar usuario
    user_resp = (
        client.schema("seguridad")
        .from_("usuarios")
        .select("id_auth_supabase, correo")
        .eq("id_usuario", user_id)
        .single()
        .execute()
    )

    if not user_resp.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    user_data = user_resp.data

    # No permitir auto-eliminación
    if user_data["id_auth_supabase"] == admin.id:
        raise HTTPException(
            status_code=400,
            detail="No puedes eliminar tu propia cuenta de administrador.",
        )

    # Eliminar de BD
    client.schema("seguridad").from_("usuarios").delete().eq(
        "id_usuario", user_id
    ).execute()

    # Eliminar de Supabase Auth
    if user_data.get("id_auth_supabase"):
        try:
            client.auth.admin.delete_user(user_data["id_auth_supabase"])
        except Exception:
            pass  # Ya se borró de la BD

    return {
        "success": True,
        "message": f"Usuario {user_data['correo']} eliminado permanentemente.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  ROLES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/roles")
async def list_roles(admin=Depends(verify_admin)):
    """Listar todos los roles con sus permisos asociados."""
    client = get_admin_client()

    roles_resp = (
        client.schema("seguridad")
        .from_("roles")
        .select("id_rol, nombre")
        .order("id_rol")
        .execute()
    )
    roles_data = roles_resp.data or []

    roles_con_permisos = []
    for rol in roles_data:
        try:
            permisos_resp = (
                client.schema("seguridad")
                .from_("rol_permisos")
                .select("id_permiso, permisos(id_permiso, nombre, descripcion)")
                .eq("id_rol", rol["id_rol"])
                .execute()
            )
            permisos = [
                rp["permisos"]
                for rp in (permisos_resp.data or [])
                if rp.get("permisos")
            ]
        except Exception:
            permisos = []

        roles_con_permisos.append({**rol, "permisos": permisos})

    return {
        "success": True,
        "message": "Roles obtenidos.",
        "data": {"roles": roles_con_permisos},
    }


@router.post("/roles", status_code=201)
async def create_role(body: RoleCreate, admin=Depends(verify_admin)):
    """Crear un nuevo rol."""
    if len(body.nombre.strip()) < 3:
        raise HTTPException(
            status_code=400,
            detail="El nombre del rol debe tener al menos 3 caracteres.",
        )

    client = get_admin_client()
    try:
        resp = (
            client.schema("seguridad")
            .from_("roles")
            .insert({"nombre": body.nombre.strip().upper()})
            .execute()
        )
        return {
            "success": True,
            "message": "Rol creado correctamente.",
            "data": {"rol": resp.data[0] if resp.data else None},
        }
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Ya existe un rol con ese nombre.")
        raise HTTPException(status_code=500, detail=f"Error al crear rol: {e}")


@router.patch("/roles")
async def update_role(body: RolePatch, admin=Depends(verify_admin)):
    """Modificar el nombre de un rol."""
    client = get_admin_client()
    client.schema("seguridad").from_("roles").update(
        {"nombre": body.nombre.strip().upper()}
    ).eq("id_rol", body.id_rol).execute()

    return {"success": True, "message": "Rol actualizado correctamente."}


@router.post("/roles/assign")
async def assign_role(body: RoleAssign, admin=Depends(verify_admin)):
    """Asignar un rol a un usuario."""
    client = get_admin_client()

    # Verificar que el rol exista
    rol_resp = (
        client.schema("seguridad")
        .from_("roles")
        .select("id_rol, nombre")
        .eq("id_rol", body.roleId)
        .single()
        .execute()
    )
    if not rol_resp.data:
        raise HTTPException(status_code=404, detail="El rol especificado no existe.")

    # Obtener id_auth_supabase del usuario
    user_resp = (
        client.schema("seguridad")
        .from_("usuarios")
        .select("id_auth_supabase")
        .eq("id_usuario", body.userId)
        .single()
        .execute()
    )
    if not user_resp.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Actualizar en BD
    client.schema("seguridad").from_("usuarios").update(
        {"id_rol": body.roleId}
    ).eq("id_usuario", body.userId).execute()

    # Sincronizar con Auth metadata
    role_map = {"ADMIN": "admin", "VENDEDOR": "vendedor", "COMPRADOR": "comprador"}
    role_name = role_map.get(rol_resp.data["nombre"], rol_resp.data["nombre"].lower())

    if user_resp.data.get("id_auth_supabase"):
        try:
            client.auth.admin.update_user_by_id(
                user_resp.data["id_auth_supabase"],
                {"user_metadata": {"role": role_name, "id_rol": body.roleId}},
            )
        except Exception:
            pass

    return {
        "success": True,
        "message": f"Rol {rol_resp.data['nombre']} asignado correctamente.",
    }


@router.delete("/roles/{role_id}")
async def delete_role(role_id: int, admin=Depends(verify_admin)):
    """Eliminar un rol. No se pueden eliminar los roles base (ADMIN, VENDEDOR, COMPRADOR)."""
    PROTECTED_ROLES = {"ADMIN", "VENDEDOR", "COMPRADOR"}
    client = get_admin_client()

    # Verificar que el rol exista
    rol_resp = (
        client.schema("seguridad")
        .from_("roles")
        .select("id_rol, nombre")
        .eq("id_rol", role_id)
        .single()
        .execute()
    )
    if not rol_resp.data:
        raise HTTPException(status_code=404, detail="El rol no existe.")

    # No permitir eliminar roles base
    if rol_resp.data["nombre"] in PROTECTED_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar el rol base '{rol_resp.data['nombre']}'.",
        )

    # Verificar que no haya usuarios con este rol
    users_resp = (
        client.schema("seguridad")
        .from_("usuarios")
        .select("id_usuario", count="exact")
        .eq("id_rol", role_id)
        .limit(1)
        .execute()
    )
    if users_resp.count and users_resp.count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar el rol '{rol_resp.data['nombre']}' porque tiene {users_resp.count} usuario(s) asignado(s). Reasígnalos primero.",
        )

    # Eliminar permisos asociados en rol_permisos
    try:
        client.schema("seguridad").from_("rol_permisos").delete().eq(
            "id_rol", role_id
        ).execute()
    except Exception:
        pass  # Si no hay permisos asociados o la tabla falla, continuar

    # Eliminar el rol
    client.schema("seguridad").from_("roles").delete().eq(
        "id_rol", role_id
    ).execute()

    return {
        "success": True,
        "message": f"Rol '{rol_resp.data['nombre']}' eliminado correctamente.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  PERMISSIONS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/permissions")
async def list_permissions(admin=Depends(verify_admin)):
    """Listar todos los permisos disponibles."""
    client = get_admin_client()
    resp = (
        client.schema("seguridad")
        .from_("permisos")
        .select("id_permiso, nombre, descripcion")
        .order("id_permiso")
        .execute()
    )
    permisos = resp.data or []

    return {
        "success": True,
        "message": "Permisos obtenidos.",
        "data": {"permisos": permisos},
    }


@router.post("/permissions")
async def assign_permissions(body: PermissionAssign, admin=Depends(verify_admin)):
    """Asignar permisos a un rol (reemplaza los existentes)."""
    client = get_admin_client()

    try:
        # Eliminar permisos actuales
        client.schema("seguridad").from_("rol_permisos").delete().eq(
            "id_rol", body.roleId
        ).execute()

        # Insertar nuevos
        if body.permissionIds:
            rows = [{"id_rol": body.roleId, "id_permiso": pid} for pid in body.permissionIds]
            client.schema("seguridad").from_("rol_permisos").insert(rows).execute()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al asignar permisos en base de datos: {e}"
        )

    return {
        "success": True,
        "message": f"{len(body.permissionIds)} permiso(s) asignados al rol.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CATEGORIES (ADMIN)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/categories", status_code=201)
async def create_category(body: CategoryCreate, admin=Depends(verify_admin)):
    """Crear una nueva categoría."""
    client = get_admin_client()
    try:
        resp = (
            client.schema("catalogo")
            .from_("categorias")
            .insert({
                "nombre": body.nombre.strip(),
                "descripcion": body.descripcion.strip() if body.descripcion else None
            })
            .execute()
        )
        return {
            "success": True,
            "message": "Categoría creada correctamente.",
            "data": resp.data[0] if resp.data else None
        }
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Ya existe una categoría con ese nombre.")
        raise HTTPException(status_code=500, detail=f"Error al crear categoría: {e}")


@router.patch("/categories/{category_id}")
async def update_category(category_id: int, body: CategoryUpdate, admin=Depends(verify_admin)):
    """Actualizar una categoría existente."""
    client = get_admin_client()
    update_data = {}
    if body.nombre is not None:
        update_data["nombre"] = body.nombre.strip()
    if body.descripcion is not None:
        update_data["descripcion"] = body.descripcion.strip() if body.descripcion else None

    if not update_data:
        raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar.")

    try:
        resp = (
            client.schema("catalogo")
            .from_("categorias")
            .update(update_data)
            .eq("id_categoria", category_id)
            .execute()
        )
        return {
            "success": True,
            "message": "Categoría actualizada correctamente.",
            "data": resp.data[0] if resp.data else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar categoría: {e}")


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int, admin=Depends(verify_admin)):
    """Eliminar una categoría (impide borrar si tiene prendas asociadas)."""
    client = get_admin_client()
    
    # Verificar si tiene productos asociados
    try:
        count_resp = (
            client.schema("catalogo")
            .from_("prendas")
            .select("id_prenda", count="exact")
            .eq("id_categoria", category_id)
            .limit(1)
            .execute()
        )
        if count_resp.count and count_resp.count > 0:
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar la categoría porque tiene productos asociados."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al verificar productos asociados: {e}")

    try:
        client.schema("catalogo").from_("categorias").delete().eq("id_categoria", category_id).execute()
        return {
            "success": True,
            "message": "Categoría eliminada correctamente."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar categoría: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  BRANDS (ADMIN)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/brands", status_code=201)
async def create_brand(body: BrandCreate, admin=Depends(verify_admin)):
    """Crear una nueva marca."""
    client = get_admin_client()
    try:
        resp = (
            client.schema("catalogo")
            .from_("marcas")
            .insert({"nombre": body.nombre.strip()})
            .execute()
        )
        return {
            "success": True,
            "message": "Marca creada correctamente.",
            "data": resp.data[0] if resp.data else None
        }
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Ya existe una marca con ese nombre.")
        raise HTTPException(status_code=500, detail=f"Error al crear marca: {e}")


@router.patch("/brands/{brand_id}")
async def update_brand(brand_id: int, body: BrandUpdate, admin=Depends(verify_admin)):
    """Actualizar una marca existente."""
    client = get_admin_client()
    try:
        resp = (
            client.schema("catalogo")
            .from_("marcas")
            .update({"nombre": body.nombre.strip()})
            .eq("id_marca", brand_id)
            .execute()
        )
        return {
            "success": True,
            "message": "Marca actualizada correctamente.",
            "data": resp.data[0] if resp.data else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar marca: {e}")


@router.delete("/brands/{brand_id}")
async def delete_brand(brand_id: int, admin=Depends(verify_admin)):
    """Eliminar una marca (impide borrar si tiene prendas asociadas)."""
    client = get_admin_client()

    # Verificar si tiene productos asociados
    try:
        count_resp = (
            client.schema("catalogo")
            .from_("prendas")
            .select("id_prenda", count="exact")
            .eq("id_marca", brand_id)
            .limit(1)
            .execute()
        )
        if count_resp.count and count_resp.count > 0:
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar la marca porque tiene productos asociados."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al verificar productos asociados: {e}")

    try:
        client.schema("catalogo").from_("marcas").delete().eq("id_marca", brand_id).execute()
        return {
            "success": True,
            "message": "Marca eliminada correctamente."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar marca: {e}")

