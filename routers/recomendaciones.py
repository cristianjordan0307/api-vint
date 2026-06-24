"""
routers/recomendaciones.py — Motor de recomendaciones personalizadas.

Migrado de: src/app/api/recomendaciones/route.ts
Incluye algoritmo local + fallback a Claude (Anthropic) si la API key está configurada.
"""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase_client import get_admin_client
from config import get_settings
import httpx

router = APIRouter(prefix="/api/recomendaciones", tags=["Recomendaciones"])


class RecomendacionesRequest(BaseModel):
    userId: str | None = None
    preferencias: dict | None = None
    favoritoIds: list[str] = []


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_resumen_comportamiento(client, user_id: str) -> dict | None:
    """Resume los últimos eventos del usuario en los últimos 7 días."""
    from datetime import datetime, timedelta

    try:
        hace7dias = (datetime.utcnow() - timedelta(days=7)).isoformat()
        resp = (
            client.from_("eventos_usuario")
            .select("tipo, termino, categoria, creado_en")
            .eq("id_usuario", user_id)
            .gte("creado_en", hace7dias)
            .order("creado_en", desc=True)
            .limit(100)
            .execute()
        )

        eventos = resp.data or []
        if not eventos:
            return None

        busquedas = [
            e["termino"]
            for e in eventos
            if e.get("tipo") == "busqueda" and e.get("termino")
        ][:10]

        categorias_vistas: dict[str, int] = {}
        for e in eventos:
            if e.get("tipo") == "vista" and e.get("categoria"):
                cat = e["categoria"]
                categorias_vistas[cat] = categorias_vistas.get(cat, 0) + 1

        top_categorias = [
            f"{cat} ({count} veces)"
            for cat, count in sorted(
                categorias_vistas.items(), key=lambda x: x[1], reverse=True
            )[:5]
        ]

        total_favoritos = sum(1 for e in eventos if e.get("tipo") == "favorito")
        total_carrito = sum(1 for e in eventos if e.get("tipo") == "carrito")

        return {
            "busquedas": busquedas,
            "topCategorias": top_categorias,
            "totalFavoritos": total_favoritos,
            "totalCarrito": total_carrito,
        }
    except Exception:
        return None


def _obtener_recomendaciones_locales(
    prendas: list, preferencias: dict | None, favorito_ids: list[str] | None = None
) -> list:
    """Algoritmo local de recomendaciones basado en filtros."""
    fav_set = set(favorito_ids or [])
    pool = [p for p in prendas if p.get("id_prenda") not in fav_set]

    if not preferencias:
        return [
            {
                **{k: p[k] for k in ("id_prenda", "titulo", "talla", "condicion", "vendedor", "imagen_principal", "categoria")},
                "precio": float(p.get("precio", 0)),
                "razon": "Seleccionado especialmente para ti basándonos en las últimas novedades.",
            }
            for p in pool[:10]
        ]

    filtradas = list(pool)

    # Filtrar por talla
    tallas = preferencias.get("tallas", [])
    if tallas:
        tallas_set = {t.upper() for t in tallas}
        pre = [p for p in filtradas if p.get("talla") and p["talla"].upper() in tallas_set]
        if len(pre) >= 5:
            filtradas = pre

    # Filtrar por categoría
    categorias = preferencias.get("categorias", [])
    if categorias:
        cat_set = {c.lower() for c in categorias}
        pre = [
            p for p in filtradas
            if p.get("categoria") and (
                p["categoria"].lower() in cat_set
                or any(c.lower() in p["categoria"].lower() for c in categorias)
            )
        ]
        if len(pre) >= 5:
            filtradas = pre

    # Filtrar por presupuesto
    pmax = preferencias.get("presupuesto_max")
    if pmax:
        pre = [p for p in filtradas if float(p.get("precio", 0)) <= float(pmax)]
        if len(pre) >= 5:
            filtradas = pre

    seleccionadas = filtradas[:10]

    # Rellenar si faltan
    if len(seleccionadas) < 10:
        ids_sel = {p.get("id_prenda") for p in seleccionadas}
        for p in pool:
            if len(seleccionadas) >= 10:
                break
            if p.get("id_prenda") not in ids_sel:
                seleccionadas.append(p)

    result = []
    for p in seleccionadas:
        razones = []
        if tallas and p.get("talla") and p["talla"].upper() in {t.upper() for t in tallas}:
            razones.append(f"disponible en tu talla ({p['talla']})")
        if categorias and p.get("categoria") and p["categoria"].lower() in {c.lower() for c in categorias}:
            razones.append("es de tus categorías favoritas")
        if pmax and float(p.get("precio", 0)) <= float(pmax):
            razones.append("se ajusta a tu presupuesto")

        result.append({
            **{k: p.get(k) for k in ("id_prenda", "titulo", "talla", "condicion", "vendedor", "imagen_principal", "categoria")},
            "precio": float(p.get("precio", 0)),
            "razon": f"Recomendado porque {' y '.join(razones)}."
            if razones
            else "Elegido especialmente para complementar tu estilo.",
        })

    return result


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("")
async def get_recomendaciones(body: RecomendacionesRequest):
    """Obtener 10 recomendaciones personalizadas de prendas."""
    client = get_admin_client()

    # 1. Catálogo
    resp = (
        client.from_("v_catalogo_publico")
        .select("id_prenda, titulo, precio, talla, condicion, vendedor, imagen_principal, categoria")
        .limit(60)
        .execute()
    )

    prendas = resp.data or []
    if not prendas:
        return {"recomendaciones": []}

    # 2. Fallback local (siempre disponible)
    fallback = _obtener_recomendaciones_locales(prendas, body.preferencias, body.favoritoIds)

    # 3. Intentar con Claude si hay API key
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return {"recomendaciones": fallback}

    # Construir prompt (simplificado)
    try:
        comportamiento = _get_resumen_comportamiento(client, body.userId) if body.userId else None

        prompt = f"""Eres el motor de recomendaciones de Vint. Recomienda exactamente 10 prendas del catálogo.
Preferencias: {json.dumps(body.preferencias or {}, ensure_ascii=False)}
Comportamiento: {json.dumps(comportamiento or {}, ensure_ascii=False)}
Catálogo: {json.dumps(prendas, ensure_ascii=False)}

Responde ÚNICAMENTE con JSON válido: {{"recomendaciones": [...]}}"""

        async with httpx.AsyncClient() as http:
            ai_resp = await http.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 2500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )

        if ai_resp.status_code == 200:
            data = ai_resp.json()
            text = data.get("content", [{}])[0].get("text", "{}")
            parsed = json.loads(text)
            return parsed
    except Exception as e:
        print(f"[recomendaciones] Error con Claude: {e}")

    return {"recomendaciones": fallback}
