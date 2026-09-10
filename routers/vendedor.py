"""
routers/vendedor.py — Endpoints del dashboard del vendedor autenticado.
"""

from fastapi import APIRouter, Depends, HTTPException
from dependencies import get_current_user, resolve_id_usuario
from supabase_client import get_admin_client

router = APIRouter(prefix="/api/vendedor", tags=["Vendedor"])


# -- GET /api/vendedor/stats --------------------------------------------------

@router.get("/stats")
async def get_vendedor_stats(user=Depends(get_current_user)):
    """
    Retorna las estadisticas del vendedor autenticado desde la vista
    seguridad.v_dashboard_vendedores. Se usa en la pantalla Home de la app.
    """
    id_usuario = await resolve_id_usuario(user.email)
    if not id_usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    client = get_admin_client()

    resp = (
        client.schema("seguridad")
        .from_("v_dashboard_vendedores")
        .select("*")
        .eq("id_usuario", id_usuario)
        .execute()
    )

    if not resp.data:
        # Retornar stats en cero si el vendedor no tiene registros aun
        return {
            "vendedor": user.email,
            "total_publicadas": 0,
            "disponibles": 0,
            "vendidas": 0,
            "pausadas": 0,
            "ingresos_totales": 0.0,
            "precio_promedio_vendido": 0.0,
        }

    row = resp.data[0]
    return {
        "vendedor": row.get("vendedor", user.email),
        "total_publicadas": row.get("total_publicadas", 0),
        "disponibles": row.get("disponibles", 0),
        "vendidas": row.get("vendidas", 0),
        "pausadas": row.get("pausadas", 0),
        "ingresos_totales": float(row.get("ingresos_totales") or 0),
        "precio_promedio_vendido": float(row.get("precio_promedio_vendido") or 0),
    }
