"""
routers/checkout.py — Procesamiento de pagos con Mercado Pago y Webhooks.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import httpx
from config import get_settings
from supabase_client import get_admin_client

router = APIRouter(prefix="/api/checkout", tags=["Checkout"])
settings = get_settings()

class CartItem(BaseModel):
    id: str
    name: str
    price: float
    quantity: int = 1

class PreferenceCreate(BaseModel):
    items: List[CartItem]
    email_comprador: str

@router.post("/mercadopago")
async def create_mercadopago_preference(body: PreferenceCreate):
    """
    Genera una preferencia de pago en Mercado Pago y retorna el ID de preferencia
    y la URL de redirección (init_point).
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="Token de Mercado Pago no configurado.")

    # El external_reference contendrá la lista de ID de prendas compradas separadas por coma
    prenda_ids = [item.id for item in body.items]
    external_ref = ",".join(prenda_ids)

    # Estructura del body para Mercado Pago API
    mp_items = []
    for item in body.items:
        mp_items.append({
            "title": item.name,
            "quantity": item.quantity,
            "unit_price": item.price,
            "currency_id": "COP"
        })

    payload = {
        "items": mp_items,
        "payer": {
            "email": body.email_comprador
        },
        "back_urls": {
            "success": f"{settings.FRONTEND_URL}/checkout/exito",
            "failure": f"{settings.FRONTEND_URL}/checkout",
            "pending": f"{settings.FRONTEND_URL}/checkout"
        },
        "auto_return": "approved",
        "external_reference": external_ref,
        "notification_url": "https://vint-api-production.up.railway.app/api/checkout/webhook" # Reemplazar con URL de producción en despliegue si es necesario
    }

    headers = {
        "Authorization": f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://api.mercadopago.com/checkout/preferences",
                json=payload,
                headers=headers,
                timeout=10.0
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "preferenceId": data.get("id"),
                "initPoint": data.get("init_point")
            }
        except Exception as e:
            print(f"[checkout] Error al crear preferencia: {str(e)}")
            raise HTTPException(status_code=500, detail="Error de comunicación con Mercado Pago.")


@router.post("/webhook")
async def mercadopago_webhook(request: Request):
    """
    Recibe la notificación de Mercado Pago y procesa el estado del pago.
    Si está aprobado, marca las prendas como 'VENDIDA' en Supabase.
    """
    body = await request.json()
    action = body.get("action")
    data_info = body.get("data", {})
    payment_id = data_info.get("id")

    # También puede venir en query params o topic antiguo
    params = dict(request.query_params)
    topic = params.get("topic") or body.get("type")
    if topic == "payment" and not payment_id:
        payment_id = body.get("resource", "").split("/")[-1]

    if not payment_id:
        return {"ok": True, "message": "No payment ID found"}

    headers = {
        "Authorization": f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}"
    }

    async with httpx.AsyncClient() as client:
        try:
            # Consultar estado del pago a Mercado Pago
            resp = await client.get(
                f"https://api.mercadopago.com/v1/payments/{payment_id}",
                headers=headers,
                timeout=10.0
            )
            resp.raise_for_status()
            payment_data = resp.json()
            
            status = payment_data.get("status")
            external_reference = payment_data.get("external_reference") # Lista de prenda_ids separados por coma

            if status == "approved" and external_reference:
                prenda_ids = [pid.strip() for pid in external_reference.split(",") if pid.strip()]
                
                # Actualizar estado de las prendas a VENDIDA en Supabase
                supabase = get_admin_client()
                for pid in prenda_ids:
                    try:
                        supabase.schema("catalogo").from_("prendas").update({
                            "estado_publicacion": "VENDIDA"
                        }).eq("id_prenda", int(pid)).execute()
                        print(f"[webhook] Prenda {pid} marcada como VENDIDA.")
                    except Exception as err_db:
                        print(f"[webhook] Error al actualizar prenda {pid} en DB: {str(err_db)}")

        except Exception as e:
            print(f"[webhook] Error al consultar pago {payment_id}: {str(e)}")
            # Retornamos 200/201 para evitar que Mercado Pago reintente infinitamente si es error interno temporal
            return {"ok": False, "detail": str(e)}

    return {"ok": True}
