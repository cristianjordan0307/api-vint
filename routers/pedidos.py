"""
routers/pedidos.py — Gestión de pedidos e historial de compras y ventas.
"""

from fastapi import APIRouter, Depends
from typing import Any, Dict
from dependencies import get_current_user_pedidos
from supabase_client import get_admin_client
from schemas.pedidos import CompraRequest, PedidoError

router = APIRouter(prefix="/api/pedidos", tags=["Pedidos"])


def format_amount(val: Any) -> int | float:
    """Convierte números flotantes sin decimales a int para respuestas limpias."""
    if val is None:
        return 0
    try:
        f = float(val)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return val


async def ejecutar_compra_simulada(body: CompraRequest, user) -> Dict[str, Any]:
    """
    Lógica de procesamiento transaccional de compra simulada.
    Valida disponibilidad, vendedores e imágenes antes de persistir,
    e implementa rollback por compensación si ocurre algún fallo.
    """
    if not body.items or len(body.items) == 0:
        raise PedidoError(
            status_code=400,
            error="El carrito está vacío",
            code="CARRITO_VACIO",
        )

    client = get_admin_client()
    comprador_uuid = str(user.id)
    costo_envio = float(body.costo_envio if body.costo_envio is not None else 15000.0)
    cantidad_items = len(body.items)
    envio_por_item = round(costo_envio / cantidad_items, 2)

    # 1. Validación previa de todos los items
    prepared_items = []
    for item in body.items:
        # Consultar catalogo.prendas
        prenda_res = (
            client.schema("catalogo")
            .from_("prendas")
            .select("id_prenda, id_usuario, titulo, precio, estado_publicacion")
            .eq("id_prenda", item.id_prenda)
            .execute()
        )

        if not prenda_res.data:
            raise PedidoError(
                status_code=409,
                error=f"La prenda #{item.id_prenda} no está disponible",
                code="PRENDA_NO_DISPONIBLE",
            )

        prenda = prenda_res.data[0]
        if prenda.get("estado_publicacion") != "DISPONIBLE":
            titulo = prenda.get("titulo") or f"Prenda #{item.id_prenda}"
            raise PedidoError(
                status_code=409,
                error=f"La prenda '{titulo}' ya no está disponible",
                code="PRENDA_NO_DISPONIBLE",
            )

        # Consultar vendedor en seguridad.usuarios
        vendedor_res = (
            client.schema("seguridad")
            .from_("usuarios")
            .select("id_usuario, id_auth_supabase")
            .eq("id_usuario", prenda["id_usuario"])
            .execute()
        )

        if not vendedor_res.data or not vendedor_res.data[0].get("id_auth_supabase"):
            raise PedidoError(
                status_code=400,
                error=f"El vendedor de la prenda '{prenda.get('titulo')}' no es válido",
                code="VENDEDOR_INVALIDO",
            )

        vendedor_auth_id = str(vendedor_res.data[0]["id_auth_supabase"])

        # Validación anti-autocompra
        if vendedor_auth_id == comprador_uuid:
            raise PedidoError(
                status_code=400,
                error=f"No puedes comprar tu propia prenda '{prenda.get('titulo')}'",
                code="AUTOCOMPRA_NO_PERMITIDA",
            )

        # Consultar imagen principal
        img_res = (
            client.schema("catalogo")
            .from_("imagenes_prendas")
            .select("url_imagen")
            .eq("id_prenda", item.id_prenda)
            .eq("es_principal", True)
            .limit(1)
            .execute()
        )

        url_imagen = None
        if img_res.data and len(img_res.data) > 0:
            url_imagen = img_res.data[0].get("url_imagen")
        else:
            # Fallback a cualquier imagen de la prenda
            any_img_res = (
                client.schema("catalogo")
                .from_("imagenes_prendas")
                .select("url_imagen")
                .eq("id_prenda", item.id_prenda)
                .limit(1)
                .execute()
            )
            if any_img_res.data and len(any_img_res.data) > 0:
                url_imagen = any_img_res.data[0].get("url_imagen")

        item_precio = float(item.precio) if item.precio is not None else float(prenda.get("precio", 0))
        item_total = round(item_precio + envio_por_item, 2)

        prepared_items.append({
            "id_prenda": prenda["id_prenda"],
            "titulo": prenda["titulo"],
            "vendedor_id": vendedor_auth_id,
            "url_imagen": url_imagen,
            "precio": item_precio,
            "total": item_total,
        })

    # 2. Inserción en pedidos y actualización de catalogo.prendas con rollback
    pedidos_creados = []
    inserted_ids = []
    updated_prenda_ids = []

    direccion_envio_dict = body.envio.model_dump() if hasattr(body.envio, "model_dump") else dict(body.envio)

    try:
        for prep in prepared_items:
            pedido_payload = {
                "user_id": comprador_uuid,
                "vendedor_id": prep["vendedor_id"],
                "id_prenda": prep["id_prenda"],
                "titulo_prenda": prep["titulo"],
                "imagen_prenda": prep["url_imagen"],
                "precio": prep["precio"],
                "total": prep["total"],
                "estado": "completado",
                "metodo_pago": "simulado",
                "direccion_envio": direccion_envio_dict,
            }

            ins_res = client.schema("public").from_("pedidos").insert(pedido_payload).execute()
            if not ins_res.data:
                raise RuntimeError(f"Fallo al registrar pedido para la prenda {prep['id_prenda']}")

            created_order = ins_res.data[0]
            inserted_ids.append(created_order["id"])

            client.schema("catalogo").from_("prendas").update({
                "estado_publicacion": "VENDIDA"
            }).eq("id_prenda", prep["id_prenda"]).execute()
            updated_prenda_ids.append(prep["id_prenda"])

            pedidos_creados.append({
                "id": created_order["id"],
                "id_prenda": prep["id_prenda"],
                "titulo_prenda": prep["titulo"],
                "precio": format_amount(prep["precio"]),
                "total": format_amount(prep["total"]),
                "estado": created_order.get("estado", "completado"),
            })

    except Exception as e:
        # ROLLBACK: compensación reversando cambios en BD
        for p_id in inserted_ids:
            try:
                client.schema("public").from_("pedidos").delete().eq("id", p_id).execute()
            except Exception:
                pass

        for pr_id in updated_prenda_ids:
            try:
                client.schema("catalogo").from_("prendas").update({
                    "estado_publicacion": "DISPONIBLE"
                }).eq("id_prenda", pr_id).execute()
            except Exception:
                pass

        raise PedidoError(
            status_code=500,
            error=f"Error al procesar la compra: {str(e)}",
            code="ERROR_PROCESAMIENTO",
        )

    total_compra = sum(p["total"] for p in pedidos_creados)

    return {
        "success": True,
        "message": "Compra procesada exitosamente",
        "data": {
            "pedidos": pedidos_creados,
            "total_compra": format_amount(total_compra),
            "cantidad_items": len(pedidos_creados),
        },
    }


# ── GET /api/pedidos/mis-compras ─────────────────────────────────────────────

@router.get("/mis-compras")
async def get_mis_compras(user=Depends(get_current_user_pedidos)):
    """
    Retorna todas las compras del usuario autenticado (como comprador),
    ordenadas de más reciente a más antigua.
    """
    client = get_admin_client()
    resp = (
        client.schema("public")
        .from_("pedidos")
        .select("id, id_prenda, titulo_prenda, imagen_prenda, precio, total, estado, metodo_pago, direccion_envio, created_at")
        .eq("user_id", str(user.id))
        .order("created_at", desc=True)
        .execute()
    )

    data = resp.data or []
    formatted = []
    for row in data:
        formatted.append({
            "id": row.get("id"),
            "id_prenda": row.get("id_prenda"),
            "titulo_prenda": row.get("titulo_prenda"),
            "imagen_prenda": row.get("imagen_prenda"),
            "precio": format_amount(row.get("precio")),
            "total": format_amount(row.get("total")),
            "estado": row.get("estado"),
            "metodo_pago": row.get("metodo_pago"),
            "direccion_envio": row.get("direccion_envio"),
            "created_at": row.get("created_at"),
        })

    return {
        "success": True,
        "data": formatted,
        "count": len(formatted),
    }


# ── GET /api/pedidos/mis-ventas ──────────────────────────────────────────────

@router.get("/mis-ventas")
async def get_mis_ventas(user=Depends(get_current_user_pedidos)):
    """
    Retorna todas las ventas del usuario autenticado (como vendedor),
    ordenadas de más reciente a más antigua con el nombre del comprador.
    """
    client = get_admin_client()
    resp = (
        client.schema("public")
        .from_("pedidos")
        .select("id, id_prenda, titulo_prenda, imagen_prenda, precio, total, estado, metodo_pago, direccion_envio, created_at, user_id")
        .eq("vendedor_id", str(user.id))
        .order("created_at", desc=True)
        .execute()
    )

    data = resp.data or []

    # Obtener nombres de compradores
    buyer_ids = list({str(row["user_id"]) for row in data if row.get("user_id")})
    buyer_names = {}
    if buyer_ids:
        try:
            users_res = (
                client.schema("seguridad")
                .from_("usuarios")
                .select("id_auth_supabase, primer_nombre, primer_apellido, correo")
                .in_("id_auth_supabase", buyer_ids)
                .execute()
            )
            for u in (users_res.data or []):
                full_name = f"{u.get('primer_nombre') or ''} {u.get('primer_apellido') or ''}".strip()
                buyer_names[str(u.get("id_auth_supabase"))] = full_name or u.get("correo")
        except Exception:
            pass

    formatted = []
    for row in data:
        buyer_uid = str(row.get("user_id") or "")
        buyer_name = buyer_names.get(buyer_uid)
        if not buyer_name:
            dir_envio = row.get("direccion_envio") or {}
            if isinstance(dir_envio, dict) and dir_envio.get("nombre"):
                buyer_name = dir_envio.get("nombre")

        formatted.append({
            "id": row.get("id"),
            "id_prenda": row.get("id_prenda"),
            "titulo_prenda": row.get("titulo_prenda"),
            "imagen_prenda": row.get("imagen_prenda"),
            "precio": format_amount(row.get("precio")),
            "total": format_amount(row.get("total")),
            "estado": row.get("estado"),
            "metodo_pago": row.get("metodo_pago"),
            "nombre_comprador": buyer_name,
            "created_at": row.get("created_at"),
        })

    return {
        "success": True,
        "data": formatted,
        "count": len(formatted),
    }


# ── POST /api/pedidos/comprar (Alias conveniente) ────────────────────────────

@router.post("/comprar")
async def comprar_alias(body: CompraRequest, user=Depends(get_current_user_pedidos)):
    """Alias para POST /api/checkout/comprar permitiendo consumo bajo /api/pedidos/comprar."""
    return await ejecutar_compra_simulada(body, user)
