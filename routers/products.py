"""
routers/products.py — CRUD de prendas del vendedor autenticado.

Migrado de: src/app/api/products/route.ts
"""

from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_user, resolve_id_usuario
from supabase_client import get_admin_client
from schemas.products import ProductCreate, ProductUpdate, ProductDelete, ImagenCreate

router = APIRouter(prefix="/api/products", tags=["Productos"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def ui_status_to_db(status: str) -> str:
    if status == "published":
        return "DISPONIBLE"
    if status == "sold":
        return "VENDIDA"
    if status == "archived":
        return "PAUSADA"
    return "PAUSADA"


def db_status_to_ui(estado: str) -> str:
    if estado == "DISPONIBLE":
        return "published"
    if estado == "VENDIDA":
        return "sold"
    if estado == "PAUSADA":
        return "archived"
    return "draft"


def normalize_genero(gender_raw: str | None) -> str:
    """Normaliza el género para cumplir con la restricción check constraint ck_prenda_genero ('Unisex', 'Hombre', 'Mujer')."""
    val = (gender_raw or "unisex").lower()
    if "mujer" in val or "female" in val:
        return "Mujer"
    elif "hombre" in val or "male" in val:
        return "Hombre"
    else:
        return "Unisex"


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


# ── Helpers de ownership ─────────────────────────────────────────────────────

async def _verify_prenda_owner(client, id_prenda: int, id_usuario: int):
    """Verifica que la prenda exista y pertenezca al usuario. Lanza HTTPException si no."""
    resp = (
        client.schema("catalogo")
        .from_("prendas")
        .select("id_usuario")
        .eq("id_prenda", id_prenda)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Prenda no encontrada.")
    if resp.data[0]["id_usuario"] != id_usuario:
        raise HTTPException(status_code=403, detail="No tienes permisos para modificar esta prenda.")


# ── GET /api/products/categories ─────────────────────────────────────────────

@router.get("/categories")
async def get_categories():
    """Obtener todas las categorías de prendas del catálogo."""
    client = get_admin_client()
    resp = (
        client.schema("catalogo")
        .from_("categorias")
        .select("id_categoria, nombre")
        .order("nombre")
        .execute()
    )
    mapped = [{"id": str(c["id_categoria"]), "nombre": c["nombre"]} for c in resp.data or []]
    return mapped


# ── GET /api/products/marcas ──────────────────────────────────────────────────

@router.get("/marcas")
async def get_marcas():
    """Retorna todas las marcas del catálogo para el dropdown de publicación. Sin auth."""
    client = get_admin_client()
    resp = (
        client.schema("catalogo")
        .from_("marcas")
        .select("id_marca, nombre")
        .order("nombre")
        .execute()
    )
    return resp.data or []


# ── GET /api/products/estados ─────────────────────────────────────────────────

@router.get("/estados", summary="Get Estados Prenda", tags=["Productos"])
async def get_estados_prenda():
    """Retorna los estados o condiciones físicas disponibles para las prendas."""
    client = get_admin_client()
    res = (
        client.schema("catalogo")
        .from_("estados_prenda")
        .select("id_estado_prenda, nombre, codigo, descripcion, orden")
        .eq("activo", True)
        .order("orden")
        .execute()
    )
    return res.data or []


# ── GET /api/products/{id_prenda} ─────────────────────────────────────────────

@router.get("/{id_prenda}")
async def get_product_detail(id_prenda: int, user=Depends(get_current_user)):
    """Retorna datos completos de una prenda con sus imágenes. Solo el propietario puede acceder."""
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()

    resp = (
        client.schema("catalogo")
        .from_("prendas")
        .select(
            "id_prenda, titulo, descripcion, precio, talla, color, genero, "
            "condicion, id_estado_prenda, estado_publicacion, fecha_publicacion, "
            "id_categoria, categorias!left(nombre), "
            "id_marca, marcas!left(nombre), "
            "estados_prenda!left(id_estado_prenda, nombre, codigo), "
            "imagenes_prendas!left(id_imagen, url_imagen, es_principal, orden)"
        )
        .eq("id_prenda", id_prenda)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=404, detail="Prenda no encontrada.")

    p = resp.data[0]
    if p["id_usuario"] != id_usuario if "id_usuario" in p else True:
        # Re-verificar con query directo para asegurar ownership
        owner_check = (
            client.schema("catalogo")
            .from_("prendas")
            .select("id_usuario")
            .eq("id_prenda", id_prenda)
            .execute()
        )
        if not owner_check.data or owner_check.data[0]["id_usuario"] != id_usuario:
            raise HTTPException(status_code=404, detail="Prenda no encontrada o no pertenece al usuario autenticado.")

    # Normalizar datos de joins
    categoria_data = p.get("categorias")
    categoria_nombre = ""
    if isinstance(categoria_data, dict):
        categoria_nombre = categoria_data.get("nombre", "")
    elif isinstance(categoria_data, list) and categoria_data:
        categoria_nombre = categoria_data[0].get("nombre", "")

    marca_data = p.get("marcas")
    marca_nombre = ""
    if isinstance(marca_data, dict):
        marca_nombre = marca_data.get("nombre", "")
    elif isinstance(marca_data, list) and marca_data:
        marca_nombre = marca_data[0].get("nombre", "")

    estado_data = p.get("estados_prenda")
    estado_obj = None
    if isinstance(estado_data, dict):
        estado_obj = estado_data
    elif isinstance(estado_data, list) and estado_data:
        estado_obj = estado_data[0]

    estado_nombre = (estado_obj.get("nombre") if estado_obj else None) or p.get("condicion")

    imagenes_raw = p.get("imagenes_prendas") or []
    imagenes = sorted(
        [{"id_imagen": img["id_imagen"], "url_imagen": img["url_imagen"],
          "es_principal": img["es_principal"], "orden": img["orden"]}
         for img in imagenes_raw],
        key=lambda x: (not x["es_principal"], x["orden"])
    )

    return {
        "id_prenda": p["id_prenda"],
        "titulo": p.get("titulo"),
        "descripcion": p.get("descripcion"),
        "id_categoria": p.get("id_categoria"),
        "categoria": categoria_nombre,
        "id_marca": p.get("id_marca"),
        "marca": marca_nombre,
        "talla": p.get("talla"),
        "color": p.get("color"),
        "precio": float(p.get("precio", 0)),
        "genero": p.get("genero"),
        "id_estado_prenda": p.get("id_estado_prenda") or (estado_obj.get("id_estado_prenda") if estado_obj else None),
        "condicion": estado_nombre,
        "condition": estado_nombre,
        "estado_prenda": estado_obj,
        "estado_publicacion": p.get("estado_publicacion"),
        "fecha_publicacion": p.get("fecha_publicacion"),
        "imagenes": imagenes,
    }


# ── POST /api/products/{id_prenda}/imagenes ───────────────────────────────────

@router.post("/{id_prenda}/imagenes", status_code=201)
async def add_imagen(id_prenda: int, body: ImagenCreate, user=Depends(get_current_user)):
    """Agrega una imagen a una prenda. La app sube el archivo a Storage y envía la URL."""
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()
    await _verify_prenda_owner(client, id_prenda, id_usuario)

    resp = (
        client.schema("catalogo")
        .from_("imagenes_prendas")
        .insert({
            "id_prenda": id_prenda,
            "url_imagen": body.url_imagen,
            "es_principal": body.es_principal,
            "orden": body.orden,
        })
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Error al guardar la imagen.")

    img = resp.data[0]
    return {
        "id_imagen": img["id_imagen"],
        "id_prenda": img["id_prenda"],
        "url_imagen": img["url_imagen"],
        "es_principal": img["es_principal"],
        "orden": img["orden"],
    }


# ── DELETE /api/products/{id_prenda}/imagenes/{id_imagen} ─────────────────────

@router.delete("/{id_prenda}/imagenes/{id_imagen}")
async def delete_imagen(id_prenda: int, id_imagen: int, user=Depends(get_current_user)):
    """Elimina una imagen de una prenda. Verifica ownership antes de proceder."""
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()
    await _verify_prenda_owner(client, id_prenda, id_usuario)

    # Verificar que la imagen existe y pertenece a esa prenda
    img_check = (
        client.schema("catalogo")
        .from_("imagenes_prendas")
        .select("id_imagen")
        .eq("id_imagen", id_imagen)
        .eq("id_prenda", id_prenda)
        .execute()
    )
    if not img_check.data:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")

    client.schema("catalogo").from_("imagenes_prendas").delete().eq(
        "id_imagen", id_imagen
    ).execute()

    return {"message": "Imagen eliminada correctamente"}


# ── PATCH /api/products/{id_prenda}/imagenes/{id_imagen}/principal ─────────────

@router.patch("/{id_prenda}/imagenes/{id_imagen}/principal")
async def set_imagen_principal(id_prenda: int, id_imagen: int, user=Depends(get_current_user)):
    """Marca una imagen como principal y desmarca el resto (solo una principal por prenda)."""
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()
    await _verify_prenda_owner(client, id_prenda, id_usuario)

    # Verificar que la imagen existe
    img_check = (
        client.schema("catalogo")
        .from_("imagenes_prendas")
        .select("id_imagen")
        .eq("id_imagen", id_imagen)
        .eq("id_prenda", id_prenda)
        .execute()
    )
    if not img_check.data:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")

    # Desmarcar todas las imágenes de la prenda
    client.schema("catalogo").from_("imagenes_prendas").update(
        {"es_principal": False}
    ).eq("id_prenda", id_prenda).execute()

    # Marcar la imagen seleccionada como principal
    client.schema("catalogo").from_("imagenes_prendas").update(
        {"es_principal": True}
    ).eq("id_imagen", id_imagen).execute()

    return {"message": "Imagen principal actualizada"}


# ── GET /api/products ────────────────────────────────────────────────────────

@router.get("")
async def get_products(user=Depends(get_current_user)):
    """Obtener las prendas del vendedor autenticado, con nombre de categoría."""
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()

    # Obtener prendas con join a categorías, marcas, estados_prenda e imágenes
    resp = (
        client.schema("catalogo")
        .from_("prendas")
        .select(
            "id_prenda, titulo, descripcion, precio, talla, color, genero, "
            "condicion, id_estado_prenda, estado_publicacion, fecha_publicacion, id_categoria, "
            "categorias!left(nombre), "
            "marcas!left(nombre), id_marca, "
            "estados_prenda!left(id_estado_prenda, nombre, codigo), "
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

        # Extraer nombre de marca del join
        marca_data = p.get("marcas")
        marca_nombre = ""
        if isinstance(marca_data, dict):
            marca_nombre = marca_data.get("nombre", "")
        elif isinstance(marca_data, list) and marca_data:
            marca_nombre = marca_data[0].get("nombre", "")

        # Extraer estado de prenda del join
        estado_data = p.get("estados_prenda")
        estado_obj = None
        if isinstance(estado_data, dict):
            estado_obj = estado_data
        elif isinstance(estado_data, list) and estado_data:
            estado_obj = estado_data[0]

        estado_nombre = (estado_obj.get("nombre") if estado_obj else None) or p.get("condicion")

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
            "id_estado_prenda": p.get("id_estado_prenda") or (estado_obj.get("id_estado_prenda") if estado_obj else None),
            "condition": estado_nombre,
            "condicion": estado_nombre,
            "estado_prenda": estado_obj,
            "id_marca": p.get("id_marca"),
            "brand": marca_nombre,
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

    # Convertir category a int si es posible, o usar category_id si viene
    id_categoria = body.category_id
    if id_categoria is None and body.category:
        try:
            id_categoria = int(body.category)
        except (ValueError, TypeError):
            id_categoria = 1
    if id_categoria is None:
        id_categoria = 1

    # Convertir brand a int si es posible, o usar brand_id si viene
    id_marca = body.brand_id
    if id_marca is None and body.brand and str(body.brand).isdigit():
        try:
            id_marca = int(body.brand)
        except (ValueError, TypeError):
            id_marca = 1
    if id_marca is None:
        id_marca = 1

    # Resolver id_estado_prenda y texto sincronizado para condicion
    id_estado = body.id_estado_prenda
    condicion_texto = None

    if id_estado:
        try:
            res_est = (
                client.schema("catalogo")
                .from_("estados_prenda")
                .select("id_estado_prenda, nombre")
                .eq("id_estado_prenda", id_estado)
                .limit(1)
                .execute()
            )
            if res_est.data:
                condicion_texto = res_est.data[0]["nombre"]
        except Exception:
            pass
    elif body.condition:
        try:
            res_est = (
                client.schema("catalogo")
                .from_("estados_prenda")
                .select("id_estado_prenda, nombre")
                .or_(f"codigo.eq.{body.condition},nombre.ilike.{body.condition}")
                .limit(1)
                .execute()
            )
            if res_est.data:
                id_estado = res_est.data[0]["id_estado_prenda"]
                condicion_texto = res_est.data[0]["nombre"]
        except Exception:
            pass

    if not id_estado:
        # Fallback de seguridad al estado por defecto BUEN_ESTADO
        try:
            res_def = (
                client.schema("catalogo")
                .from_("estados_prenda")
                .select("id_estado_prenda, nombre")
                .eq("codigo", "BUEN_ESTADO")
                .limit(1)
                .execute()
            )
            if res_def.data:
                id_estado = res_def.data[0]["id_estado_prenda"]
                if not condicion_texto:
                    condicion_texto = res_def.data[0]["nombre"]
        except Exception:
            pass

    if not condicion_texto:
        condicion_texto = body.condition or "Buen estado"

    if not body.name.strip():
        raise HTTPException(status_code=400, detail="El nombre del producto no puede estar vacío.")

    if body.price <= 0:
        raise HTTPException(status_code=400, detail="El precio debe ser mayor a cero.")

    # Validar y normalizar descripción
    desc_val = "Sin descripción adicional sobre la prenda."
    if body.description:
        desc_stripped = body.description.strip()
        if len(desc_stripped) > 0 and len(desc_stripped) < 10:
            raise HTTPException(
                status_code=400,
                detail="La descripción debe tener al menos 10 caracteres."
            )
        if len(desc_stripped) >= 10:
            desc_val = desc_stripped

    insert_data = {
        "id_usuario": id_usuario,
        "id_categoria": id_categoria,
        "id_marca": id_marca,
        "titulo": body.name.strip(),
        "descripcion": desc_val,
        "precio": body.price,
        "talla": body.size or "Única",
        "color": body.color or "Combinado",
        "genero": normalize_genero(body.gender),
        "id_estado_prenda": id_estado,
        "condicion": condicion_texto,
        "estado_publicacion": ui_status_to_db(body.status or "draft"),
    }

    try:
        resp = (
            client.schema("catalogo")
            .from_("prendas")
            .insert(insert_data)
            .execute()
        )
        prenda = resp.data[0] if resp.data else None
    except Exception as e:
        error_msg = str(e)
        if "id_categoria" in error_msg:
            raise HTTPException(status_code=400, detail="La categoría seleccionada no es válida.")
        raise HTTPException(status_code=500, detail=f"Error al crear la prenda: {error_msg}")

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
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()
    prenda_id = int(body.id)

    # Verificar que la prenda le pertenece al usuario
    prenda_resp = (
        client.schema("catalogo")
        .from_("prendas")
        .select("id_usuario")
        .eq("id_prenda", prenda_id)
        .execute()
    )
    if not prenda_resp.data:
        raise HTTPException(status_code=404, detail="Prenda no encontrada.")
    if prenda_resp.data[0]["id_usuario"] != id_usuario:
        raise HTTPException(status_code=403, detail="No tienes permisos para modificar esta prenda.")

    db_update: dict = {}

    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="El nombre del producto no puede estar vacío.")
        db_update["titulo"] = body.name.strip()
    if body.description is not None:
        desc_stripped = body.description.strip()
        if len(desc_stripped) > 0 and len(desc_stripped) < 10:
            raise HTTPException(
                status_code=400,
                detail="La descripción debe tener al menos 10 caracteres."
            )
        db_update["descripcion"] = desc_stripped if len(desc_stripped) >= 10 else "Sin descripción adicional sobre la prenda."
    if body.price is not None:
        if body.price <= 0:
            raise HTTPException(status_code=400, detail="El precio debe ser mayor a cero.")
        db_update["precio"] = body.price
    if body.status is not None:
        db_update["estado_publicacion"] = ui_status_to_db(body.status)
    if body.size is not None:
        db_update["talla"] = body.size
    if body.color is not None:
        db_update["color"] = body.color
    if body.gender is not None:
        db_update["genero"] = normalize_genero(body.gender)
    if body.id_estado_prenda is not None:
        db_update["id_estado_prenda"] = body.id_estado_prenda
        try:
            res_est = (
                client.schema("catalogo")
                .from_("estados_prenda")
                .select("nombre")
                .eq("id_estado_prenda", body.id_estado_prenda)
                .limit(1)
                .execute()
            )
            if res_est.data:
                db_update["condicion"] = res_est.data[0]["nombre"]
        except Exception:
            pass
    elif body.condition is not None:
        try:
            res_est = (
                client.schema("catalogo")
                .from_("estados_prenda")
                .select("id_estado_prenda, nombre")
                .or_(f"codigo.eq.{body.condition},nombre.ilike.{body.condition}")
                .limit(1)
                .execute()
            )
            if res_est.data:
                db_update["id_estado_prenda"] = res_est.data[0]["id_estado_prenda"]
                db_update["condicion"] = res_est.data[0]["nombre"]
            else:
                db_update["condicion"] = body.condition
        except Exception:
            db_update["condicion"] = body.condition

    if body.category_id is not None:
        db_update["id_categoria"] = body.category_id
    elif body.category is not None:
        try:
            db_update["id_categoria"] = int(body.category) if body.category else 1
        except (ValueError, TypeError):
            db_update["id_categoria"] = 1

    if body.brand_id is not None:
        db_update["id_marca"] = body.brand_id
    elif body.brand is not None:
        try:
            db_update["id_marca"] = int(body.brand) if str(body.brand).isdigit() else 1
        except (ValueError, TypeError):
            pass

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
        try:
            resp = (
                client.schema("catalogo")
                .from_("prendas")
                .update(db_update)
                .eq("id_prenda", prenda_id)
                .execute()
            )
            result_data = resp.data[0] if resp.data else None
        except Exception as e:
            error_msg = str(e)
            if "id_categoria" in error_msg:
                raise HTTPException(status_code=400, detail="La categoría seleccionada no es válida.")
            raise HTTPException(status_code=500, detail=f"Error al actualizar la prenda: {error_msg}")

    return {"data": result_data}


# ── DELETE /api/products ─────────────────────────────────────────────────────

@router.delete("")
async def delete_products(body: ProductDelete, user=Depends(get_current_user)):
    """
    Eliminar una o varias prendas por sus IDs.
    Primero elimina las imágenes asociadas para evitar errores de FK constraint.
    """
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()

    # Convertir IDs a enteros de forma segura
    try:
        ids_int = [int(i) for i in body.ids]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Los IDs deben ser números válidos.")

    # Verificar que todas las prendas a eliminar le pertenecen al usuario
    prendas_resp = (
        client.schema("catalogo")
        .from_("prendas")
        .select("id_prenda")
        .in_("id_prenda", ids_int)
        .eq("id_usuario", id_usuario)
        .execute()
    )
    valid_ids = [p["id_prenda"] for p in prendas_resp.data or []]
    
    if len(valid_ids) != len(ids_int):
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para eliminar una o más de las prendas seleccionadas."
        )

    # 1. Eliminar imágenes asociadas primero (evitar FK constraint)
    client.schema("catalogo").from_("imagenes_prendas").delete().in_(
        "id_prenda", ids_int
    ).execute()

    # 2. Eliminar las prendas
    client.schema("catalogo").from_("prendas").delete().in_(
        "id_prenda", ids_int
    ).execute()

    return {"success": True, "deleted": ids_int}
