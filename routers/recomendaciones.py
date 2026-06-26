"""
routers/recomendaciones.py — Motor de recomendaciones personalizadas.

Migrado de: src/app/api/recomendaciones/route.ts
Incluye algoritmo local + fallback a Claude (Anthropic) si la API key está configurada.
"""

import json
import re
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
        # FIX: especificar schema correcto para eventos_usuario
        resp = (
            client.schema("catalogo")
            .from_("eventos_usuario")
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
    except Exception as e:
        print(f"[recomendaciones] Error obteniendo comportamiento: {e}")
        return None


def _extraer_json(text: str) -> dict:
    """
    Extrae JSON válido de la respuesta de Claude aunque venga envuelta en
    bloques de markdown (```json ... ```) u otro texto adicional.
    """
    # Intentar parsear directamente
    try:
        return json.loads(text)
    except Exception:
        pass

    # Buscar bloque ```json ... ``` o ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    # Buscar el primer objeto JSON { ... }
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
    """Algoritmo local de recomendaciones basado en filtros."""
    # FIX: normalizar favorito_ids a strings para comparación segura
    fav_set = {str(fid) for fid in (favorito_ids or [])}
    pool = [p for p in prendas if str(p.get("id_prenda", "")) not in fav_set]

    if not preferencias:
        return [
            {
                **{k: p.get(k) for k in ("id_prenda", "titulo", "talla", "condicion", "vendedor", "imagen_principal", "categoria")},
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
    """Obtener hasta 10 recomendaciones personalizadas de prendas."""
    client = get_admin_client()

    # FIX: especificar schema 'catalogo' para la vista v_catalogo_publico
    try:
        resp = (
            client.schema("catalogo")
            .from_("v_catalogo_publico")
            .select("id_prenda, titulo, precio, talla, condicion, vendedor, imagen_principal, categoria")
            .limit(60)
            .execute()
        )
        prendas = resp.data or []
    except Exception as e:
        print(f"[recomendaciones] Error al consultar catálogo con schema: {e}")
        # Fallback: intentar sin schema explícito (compatible con algunas configs de Supabase)
        try:
            resp = (
                client.from_("v_catalogo_publico")
                .select("id_prenda, titulo, precio, talla, condicion, vendedor, imagen_principal, categoria")
                .limit(60)
                .execute()
            )
            prendas = resp.data or []
        except Exception as e2:
            print(f"[recomendaciones] Error en fallback de catálogo: {e2}")
            prendas = []

    if not prendas:
        return {"recomendaciones": []}

    # Algoritmo local (siempre disponible como fallback)
    fallback = _obtener_recomendaciones_locales(prendas, body.preferencias, body.favoritoIds)

    # Intentar con Claude si hay API key configurada
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return {"recomendaciones": fallback}

    try:
        comportamiento = _get_resumen_comportamiento(client, body.userId) if body.userId else None

        # Limitar catálogo enviado a Claude para no exceder tokens
        prendas_para_claude = prendas[:30]

        prompt = f"""Eres el motor de recomendaciones de Vint (moda de segunda mano en Colombia).
Recomienda exactamente 10 prendas del catálogo para el usuario.

Preferencias del usuario: {json.dumps(body.preferencias or {}, ensure_ascii=False)}
Comportamiento reciente: {json.dumps(comportamiento or {}, ensure_ascii=False)}
IDs a EXCLUIR (ya son favoritos): {json.dumps(body.favoritoIds or [], ensure_ascii=False)}

Catálogo disponible:
{json.dumps(prendas_para_claude, ensure_ascii=False)}

Responde ÚNICAMENTE con JSON válido, sin texto adicional, sin bloques markdown:
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
    "razon": "Frase corta explicando por qué se recomienda"
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
            # FIX: usar extractor robusto de JSON
            parsed = _extraer_json(text)
            recs = parsed.get("recomendaciones", [])
            if recs:
                return {"recomendaciones": recs}
        else:
            print(f"[recomendaciones] Claude error {ai_resp.status_code}: {ai_resp.text[:200]}")

    except Exception as e:
        print(f"[recomendaciones] Error con Claude, usando fallback local: {e}")

    return {"recomendaciones": fallback}
