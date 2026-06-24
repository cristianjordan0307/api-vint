from fastapi import APIRouter, HTTPException, status
from app.core.supabase import supabase
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/track", tags=["track"])

class TrackPayload(BaseModel):
    tipo: str
    id_usuario: str
    id_prenda: Optional[str] = None
    termino: Optional[str] = None
    categoria: Optional[str] = None

@router.post("")
async def track_event(payload: TrackPayload):
    if not payload.tipo or not payload.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faltan campos obligatorios: tipo e id_usuario."
        )

    try:
        event_data = {
            "tipo": payload.tipo,
            "id_usuario": payload.id_usuario,
            "id_prenda": payload.id_prenda or None,
            "termino": payload.termino or None,
            "categoria": payload.categoria or None
        }
        
        supabase.table("eventos_usuario").insert(event_data).execute()
        return {"ok": True}
    except Exception as e:
        error_msg = str(e)
        if "42P01" in error_msg or "does not exist" in error_msg:
            print("[track] Tabla eventos_usuario no existe aún. Ejecuta el SQL de setup.")
            return {"ok": False, "reason": "table_missing"}
            
        print(f"[track] Error insertando evento: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al registrar el evento."
        )
