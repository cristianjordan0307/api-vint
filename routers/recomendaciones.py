"""
routers/recomendaciones.py — Motor de recomendaciones personalizadas.

Usa el catálogo real de Supabase (catalogo.v_catalogo_publico) con
algoritmo local + fallback a Claude (Anthropic) si hay API key.
"""

import json
import re
from fastapi import APIRouter
from pydantic import BaseModel
from supabase_client import get_admin_client_for_schema
from config import get_settings
import httpx

router = APIRouter(prefix="/api/recomendaciones", tags=["Recomendaciones"])


class RecomendacionesRequest(BaseModel):
    userId: str | None = None
    preferencias: dict | None = None
    favoritoIds: list[str] = []


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extraer_json(text: str) -> dict:
    """
    Extrae JSON válido aunque Claude lo envuelva en bloques markdown.
    Intenta tres estrategias: parseo directo, bloque ```json, primer { }.
    """
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    raise ValueError("No se pudo extraer JSON válido de la respuesta de Claude")


def _obtener_recomendaciones_locales(
    prendas: list, preferencias: dict | None, favorito_ids: list[str] | None = None
) -> list:
    """Algoritmo local de recomendaciones sin IA."""
    # Normalizar IDs de favoritos a strings para comparación segura
    fav_set = {str(fid) for fid in (favorito_ids or [])}
    pool = [p for p in prendas if str(p.get("id_prenda", "")) not in fav_set]

    if not pool:
        return []

    if not preferencias:
        return [
            {
                "id_prenda": str(p.get("id_prenda", "")),
                "titulo": p.get("titulo", ""),
                "precio": float(p.get("precio", 0)),
                "talla": p.get("talla", ""),
                "condicion": p.get("condicion", ""),
                "vendedor": p.get("vendedor", ""),
                "imagen_principal": p.get("imagen_principal"),
                "categoria": p.get("categoria", ""),
                "razon": "Seleccionado especialmente para ti basándonos en las últimas novedades.",
            }
            for p in pool[:10]
        ]

    filtradas = list(pool)

    tallas = preferencias.get("tallas", [])
    if tallas:
        tallas_set = {t.upper() for t in tallas}
        pre = [p for p in filtradas if p.get("talla") and p["talla"].upper() in tallas_set]
        if len(pre) >= 5:
            filtradas = pre

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

    pmax = preferencias.get("presupuesto_max")
    if pmax:
        try:
            pmax_val = float(pmax)
            pre = [p for p in filtradas if float(p.get("precio", 0)) <= pmax_val]
            if len(pre) >= 5:
                filtradas = pre
        except (ValueError, TypeError):
            pass

    seleccionadas = filtradas[:10]

    # Rellenar si hay menos de 10
    if len(seleccionadas) < 10:
        ids_sel = {str(p.get("id_prenda")) for p in seleccionadas}
        for p in pool:
            if len(seleccionadas) >= 10:
                break
            if str(p.get("id_prenda")) not in ids_sel:
                seleccionadas.append(p)

    result = []
    for p in seleccionadas:
        razones = []
        if tallas and p.get("talla") and p["talla"].upper() in {t.upper() for t in tallas}:
            razones.append(f"disponible en tu talla ({p['talla']})")
        if categorias and p.get("categoria") and p["categoria"].lower() in {c.lower() for c in categorias}:
            razones.append("es de tus categorías favoritas")
        try:
            if pmax and float(p.get("precio", 0)) <= float(pmax):
                razones.append("se ajusta a tu presupuesto")
        except (ValueError, TypeError):
            pass

        result.append({
            "id_prenda": str(p.get("id_prenda", "")),
            "titulo": p.get("titulo", ""),
            "precio": float(p.get("precio", 0)),
            "talla": p.get("talla", ""),
            "condicion": p.get("condicion", ""),
            "vendedor": p.get("vendedor", ""),
            "imagen_principal": p.get("imagen_principal"),
            "categoria": p.get("categoria", ""),
            "razon": f"Recomendado porque {' y '.join(razones)}."
            if razones
            else "Elegido especialmente para complementar tu estilo.",
        })

    return result


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("")
async def get_recomendaciones(body: RecomendacionesRequest):
    """Obtener hasta 10 recomendaciones personalizadas de prendas disponibles."""

    # Usar cliente con schema 'catalogo' directamente (evita problemas con .schema() en runtime)
    try:
        catalogo_client = get_admin_client_for_schema("catalogo")
        resp = (
            catalogo_client
            .from_("v_catalogo_publico")
            .select("id_prenda, titulo, precio, talla, condicion, vendedor, imagen_principal, categoria")
            .limit(60)
            .execute()
        )
        prendas = resp.data or []
    except Exception as e:
        print(f"[recomendaciones] Error al consultar v_catalogo_publico: {e}")
        prendas = []

    if not prendas:
        print("[recomendaciones] Catálogo vacío — sin prendas DISPONIBLES")
        return {"recomendaciones": []}

    print(f"[recomendaciones] Catálogo cargado: {len(prendas)} prendas")

    # Algoritmo local (siempre disponible)
    fallback = _obtener_recomendaciones_locales(prendas, body.preferencias, body.favoritoIds)

    # Intentar Claude si hay API key
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        print("[recomendaciones] Sin ANTHROPIC_API_KEY — usando algoritmo local")
        return {"recomendaciones": fallback}

    try:
        prendas_para_claude = prendas[:30]

        prompt = f"""Eres el motor de recomendaciones de Vint (moda segunda mano Colombia).
Recomienda exactamente 10 prendas del catálogo para el usuario.

Preferencias: {json.dumps(body.preferencias or {}, ensure_ascii=False)}
IDs a EXCLUIR (ya son favoritos): {json.dumps(body.favoritoIds or [], ensure_ascii=False)}

Catálogo disponible:
{json.dumps(prendas_para_claude, ensure_ascii=False)}

Responde ÚNICAMENTE con JSON válido, sin texto extra, sin backticks:
{{"recomendaciones": [
  {{
    "id_prenda": "string",
    "titulo": "string",
    "precio": number,
    "talla": "string",
    "condicion": "string",
    "vendedor": "string",
    "imagen_principal": "string o null",
    "categoria": "string",
    "razon": "Frase corta explicando por qué"
  }}
]}}"""

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
            text = data.get("content", [{}])[0].get("text", "")
            parsed = _extraer_json(text)
            recs = parsed.get("recomendaciones", [])
            if recs:
                print(f"[recomendaciones] Claude devolvió {len(recs)} recomendaciones")
                return {"recomendaciones": recs}
        else:
            print(f"[recomendaciones] Claude error {ai_resp.status_code}")

    except Exception as e:
        print(f"[recomendaciones] Error con Claude, usando fallback: {e}")

    return {"recomendaciones": fallback}
