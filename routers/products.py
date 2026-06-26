"""
routers/products.py — CRUD de prendas del vendedor autenticado.

Migrado de: src/app/api/products/route.ts
"""

from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_user, resolve_id_usuario
from supabase_client import get_admin_client
from schemas.products import ProductCreate, ProductUpdate, ProductDelete

router = APIRouter(prefix="/api/products", tags=["Productos"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def ui_status_to_db(status: str) -> str:
    if status == "published":
        return "DISPONIBLE"
    if status == "archived":
        return "VENDIDA"
    return "PAUSADA"


def db_status_to_ui(estado: str) -> str:
    if estado == "DISPONIBLE":
        return "published"
    if estado == "VENDIDA":
        return "archived"
    return "draft"


def get_catalogo_client():
    """Cliente admin apuntando al esquema catalogo."""
    from supabase import create_client
    from config import get_settings

    s = get_settings()
    return create_client(
        s.SUPABASE_URL,
        s.SUPABASE_SERVICE_ROLE_KEY,
        options={"schema": "catalogo"},  # type: ignore[arg-type]
    )


# ── GET /api/products ────────────────────────────────────────────────────────

@router.get("")
async def get_products(user=Depends(get_current_user)):
    """Obtener las prendas del vendedor autenticado, con nombre de categoría."""
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()

    # Obtener prendas con join a categorías e imágenes
    resp = (
        client.schema("catalogo")
        .from_("prendas")
        .select(
            "id_prenda, titulo, descripcion, precio, talla, color, genero, "
            "condicion, estado_publicacion, fecha_publicacion, id_categoria, "
            "categorias!left(nombre), "
            "imagenes_prendas!left(url_imagen, es_principal)"
        )
        .eq("id_usuario", id_usuario)
        .order("fecha_publicacion", desc=True)
        .execute()
    )

    mapped = []
    for p in resp.data or []:
        imgs = p.get("imagenes_prendas") or []
        principal = next((i for i in imgs if i.get("es_principal")), None)
        if not principal and imgs:
            principal = imgs[0]

        # Extraer nombre de categoría del join
        categoria_data = p.get("categorias")
        categoria_nombre = ""
        if isinstance(categoria_data, dict):
            categoria_nombre = categoria_data.get("nombre", "")
        elif isinstance(categoria_data, list) and categoria_data:
            categoria_nombre = categoria_data[0].get("nombre", "")

        mapped.append({
            "id": str(p["id_prenda"]),
            "name": p.get("titulo", ""),
            "description": p.get("descripcion", ""),
            "price": float(p.get("precio", 0)),
            "stock": 1,
            "sku": "",
            "category": categoria_nombre,
            "category_id": p.get("id_categoria"),
            "status": db_status_to_ui(p.get("estado_publicacion", "PAUSADA")),
            "image_url": principal.get("url_imagen") if principal else None,
            "created_at": p.get("fecha_publicacion", ""),
            "updated_at": p.get("fecha_publicacion", ""),
            # Campos físicos de la prenda
            "size": p.get("talla"),
            "color": p.get("color"),
            "gender": p.get("genero"),
            "condition": p.get("condicion"),
        })

    return {"data": mapped, "count": len(mapped)}


# ── POST /api/products ───────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_product(body: ProductCreate, user=Depends(get_current_user)):
    """Crear una nueva prenda en el catálogo."""
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en el sistema.")

    client = get_admin_client()

    # Convertir category a int si es posible, default a 1
    try:
        id_categoria = int(body.category) if body.category else 1
    except (ValueError, TypeError):
        id_categoria = 1

    # Normalizar condición
    condicion_raw = (body.condition or "buen_estado").lower()
    if condicion_raw in ("nuevo", "new"):
        condicion = "NUEVO"
    else:
        condicion = "USADO"

    insert_data = {
        "id_usuario": id_usuario,
        "id_categoria": id_categoria,
        "id_marca": 1,
        "titulo": body.name,
        "descripcion": body.description or "",
        "precio": body.price,
        "talla": body.size or "Única",
        "color": body.color or "Combinado",
        "genero": body.gender or "UNISEX",
        "condicion": condicion,
        "estado_publicacion": ui_status_to_db(body.status or "draft"),
    }

    resp = (
        client.schema("catalogo")
        .from_("prendas")
        .insert(insert_data)
        .execute()
    )

    prenda = resp.data[0] if resp.data else None

    if body.image_url and prenda:
        client.schema("catalogo").from_("imagenes_prendas").insert({
            "id_prenda": prenda["id_prenda"],
            "url_imagen": body.image_url,
            "es_principal": True,
            "orden": 0,
        }).execute()

    return {"data": prenda}


# ── PATCH /api/products ──────────────────────────────────────────────────────

@router.patch("")
async def update_product(body: ProductUpdate, user=Depends(get_current_user)):
    """Actualizar campos de una prenda existente (incluyendo imagen principal)."""
    client = get_admin_client()
    db_update: dict = {}

    if body.name is not None:
        db_update["titulo"] = body.name
    if body.description is not None:
        db_update["descripcion"] = body.description
    if body.price is not None:
        db_update["precio"] = body.price
    if body.status is not None:
        db_update["estado_publicacion"] = ui_status_to_db(body.status)
    if body.size is not None:
        db_update["talla"] = body.size
    if body.color is not None:
        db_update["color"] = body.color
    if body.gender is not None:
        db_update["genero"] = body.gender
    if body.condition is not None:
        condicion_raw = body.condition.lower()
        db_update["condicion"] = "NUEVO" if condicion_raw in ("nuevo", "new") else "USADO"

    prenda_id = int(body.id)

    # Actualizar imagen principal si se proporciona
    if body.image_url is not None:
        # Primero intentar actualizar la imagen principal existente
        img_resp = (
            client.schema("catalogo")
            .from_("imagenes_prendas")
            .select("id_imagen")
            .eq("id_prenda", prenda_id)
            .eq("es_principal", True)
            .execute()
        )
        if img_resp.data:
            # Actualizar imagen existente
            client.schema("catalogo").from_("imagenes_prendas").update(
                {"url_imagen": body.image_url}
            ).eq("id_prenda", prenda_id).eq("es_principal", True).execute()
        else:
            # Insertar nueva imagen principal
            client.schema("catalogo").from_("imagenes_prendas").insert({
                "id_prenda": prenda_id,
                "url_imagen": body.image_url,
                "es_principal": True,
                "orden": 0,
            }).execute()

    if not db_update and body.image_url is None:
        raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar.")

    result_data = None
    if db_update:
        resp = (
            client.schema("catalogo")
            .from_("prendas")
            .update(db_update)
            .eq("id_prenda", prenda_id)
            .execute()
        )
        result_data = resp.data[0] if resp.data else None

    return {"data": result_data}


# ── DELETE /api/products ─────────────────────────────────────────────────────

@router.delete("")
async def delete_products(body: ProductDelete, user=Depends(get_current_user)):
    """
    Eliminar una o varias prendas por sus IDs.
    Primero elimina las imágenes asociadas para evitar errores de FK constraint.
    """
    client = get_admin_client()

    # Convertir IDs a enteros de forma segura
    try:
        ids_int = [int(i) for i in body.ids]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Los IDs deben ser números válidos.")

    # 1. Eliminar imágenes asociadas primero (evitar FK constraint)
    client.schema("catalogo").from_("imagenes_prendas").delete().in_(
        "id_prenda", ids_int
    ).execute()

    # 2. Eliminar las prendas
    client.schema("catalogo").from_("prendas").delete().in_(
        "id_prenda", ids_int
    ).execute()

    return {"success": True, "deleted": ids_int}
