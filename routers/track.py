"""
routers/track.py — Registro de eventos de comportamiento del usuario.

Migrado de: src/app/api/track/route.ts
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase_client import get_admin_client

router = APIRouter(prefix="/api/track", tags=["Tracking"])


class TrackEvent(BaseModel):
    tipo: str
    id_usuario: str
    id_prenda: str | None = None
    termino: str | None = None
    categoria: str | None = None


@router.post("")
async def track_event(body: TrackEvent):
    """
    Registra eventos de comportamiento del usuario.
    No requiere autenticación por JWT (el id_usuario viene en el body).
    """
    client = get_admin_client()

    try:
        client.from_("eventos_usuario").insert({
            "tipo": body.tipo,
            "id_usuario": body.id_usuario,
            "id_prenda": body.id_prenda,
            "termino": body.termino,
            "categoria": body.categoria,
        }).execute()
    except Exception as e:
        error_str = str(e)
        if "42P01" in error_str:
            return {"ok": False, "reason": "table_missing"}
        print(f"[track] Error: {error_str}")
        raise HTTPException(status_code=500, detail="Error al registrar evento.")

    return {"ok": True}
