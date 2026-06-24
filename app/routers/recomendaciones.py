from fastapi import APIRouter, HTTPException, status
from app.core.config import settings
from app.core.supabase import supabase
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import json
from anthropic import Anthropic

router = APIRouter(prefix="/recomendaciones", tags=["recomendaciones"])

class RecomendacionesPayload(BaseModel):
    userId: Optional[str] = None
    preferencias: Optional[dict] = None
    favoritoIds: Optional[List[str]] = []

def obtener_recomendaciones_locales(prendas: list, preferencias: dict, favorito_ids: list = None) -> list:
    if favorito_ids is None:
        favorito_ids = []
    
    fav_set = set(str(fid) for fid in favorito_ids)
    pool = [p for p in prendas if str(p.get("id_prenda")) not in fav_set]

    if not preferencias:
        return [
            {
                "id_prenda": p.get("id_prenda"),
                "titulo": p.get("titulo"),
                "precio": float(p.get("precio") or 0),
                "talla": p.get("talla"),
                "condicion": p.get("condicion"),
                "vendedor": p.get("vendedor"),
                "imagen_principal": p.get("imagen_principal"),
                "categoria": p.get("categoria"),
                "razon": "Seleccionado especialmente para ti basándonos en las últimas novedades.",
            }
            for p in pool[:10]
        ]

    filtradas = list(pool)
    tallas_pref = preferencias.get("tallas", [])
    categorias_pref = preferencias.get("categorias", [])
    presupuesto_max = preferencias.get("presupuesto_max")

    # 1. Filtrar por talla
    if tallas_pref:
        tallas_set = set(t.upper() for t in tallas_pref)
        pre_filtro = [p for p in filtradas if p.get("talla") and p.get("talla").upper() in tallas_set]
        if len(pre_filtro) >= 5:
            filtradas = pre_filtro

    # 2. Filtrar por categoría
    if categorias_pref:
        categorias_set = set(c.lower() for c in categorias_pref)
        pre_filtro = [
            p for p in filtradas
            if p.get("categoria") and (
                p.get("categoria").lower() in categorias_set or
                any(c.lower() in p.get("categoria").lower() for c in categorias_pref)
            )
        ]
        if len(pre_filtro) >= 5:
            filtradas = pre_filtro

    # 3. Filtrar por presupuesto máximo
    if presupuesto_max is not None:
        try:
            max_p = float(presupuesto_max)
            pre_filtro = [p for p in filtradas if float(p.get("precio") or 0) <= max_p]
            if len(pre_filtro) >= 5:
                filtradas = pre_filtro
        except ValueError:
            pass

    seleccionadas = filtradas[:10]

    # Rellenar si faltan
    if len(seleccionadas) < 10:
        ids_seleccionados = set(str(p.get("id_prenda")) for p in seleccionadas)
        for p in pool:
            if len(seleccionadas) >= 10:
                break
            if str(p.get("id_prenda")) not in ids_seleccionados:
                seleccionadas.append(p)

    recs = []
    for p in seleccionadas:
        razones = []
        p_talla = p.get("talla")
        p_categoria = p.get("categoria")
        p_precio = float(p.get("precio") or 0)

        if tallas_pref and p_talla and p_talla.upper() in set(t.upper() for t in tallas_pref):
            razones.append(f"disponible en tu talla ({p_talla})")
        if categorias_pref and p_categoria and p_categoria.lower() in set(c.lower() for c in categorias_pref):
            razones.append("es de tus categorías favoritas")
        if presupuesto_max is not None:
            try:
                if p_precio <= float(presupuesto_max):
                    razones.append("se ajusta a tu presupuesto")
            except ValueError:
                pass

        if razones:
            razon = f"Recomendado porque {' y '.join(razones)}."
        else:
            razon = "Elegido especialmente para complementar tu estilo."

        recs.append({
            "id_prenda": p.get("id_prenda"),
            "titulo": p.get("titulo"),
            "precio": p_precio,
            "talla": p_talla,
            "condicion": p.get("condicion"),
            "vendedor": p.get("vendedor"),
            "imagen_principal": p.get("imagen_principal"),
            "categoria": p_categoria,
            "razon": razon
        })

    return recs

def get_resumen_comportamiento(user_id: str) -> Optional[dict]:
    try:
        hace_7_dias = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        response = supabase.table("eventos_usuario").select(
            "tipo, termino, categoria, creado_en"
        ).eq("id_usuario", user_id).gte("creado_en", hace_7_dias).order(
            "creado_en", desc=True
        ).limit(100).execute()
        
        eventos = response.data or []
        if not eventos:
            return None
            
        busquedas = [
            e.get("termino") for e in eventos 
            if e.get("tipo") == "busqueda" and e.get("termino")
        ][:10]
        
        categorias_vistas = {}
        for e in eventos:
            if e.get("tipo") == "vista" and e.get("categoria"):
                cat = e.get("categoria")
                categorias_vistas[cat] = categorias_vistas.get(cat, 0) + 1
                
        top_categorias = sorted(
            categorias_vistas.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        top_categorias_str = [f"{cat} ({count} veces)" for cat, count in top_categorias]
        
        total_favoritos = len([e for e in eventos if e.get("tipo") == "favorito"])
        total_carrito = len([e for e in eventos if e.get("tipo") == "carrito"])
        
        return {
            "busquedas": busquedas,
            "topCategorias": top_categorias_str,
            "totalFavoritos": total_favoritos,
            "totalCarrito": total_carrito
        }
    except Exception as e:
        print(f"[get_resumen_comportamiento] Error: {e}")
        return None

def get_detalles_favoritos(favorito_ids: list) -> list:
    if not favorito_ids:
        return []
    try:
        response = supabase.table("v_catalogo_publico").select(
            "id_prenda, titulo, categoria, talla, precio"
        ).in_("id_prenda", favorito_ids).execute()
        return response.data or []
    except Exception as e:
        print(f"[get_detalles_favoritos] Error: {e}")
        return []

@router.post("")
async def obtener_recomendaciones(payload: RecomendacionesPayload):
    try:
        # 1. Catálogo ampliado
        response = supabase.table("v_catalogo_publico").select(
            "id_prenda, titulo, precio, talla, condicion, vendedor, imagen_principal, categoria"
        ).limit(60).execute()
        
        prendas = response.data or []
        if not prendas:
            return {"recomendaciones": []}

        favorito_ids = payload.favoritoIds or []
        
        # 2. Comportamiento y favoritos
        comportamiento = None
        detalles_favoritos = []
        if payload.userId:
            comportamiento = get_resumen_comportamiento(payload.userId)
            if favorito_ids:
                detalles_favoritos = get_detalles_favoritos(favorito_ids)

        preferencias = payload.preferencias

        # 3. Construir prompt
        seccion_preferencias = "PERFIL EXPLÍCITO: No disponible aún"
        if preferencias:
            seccion_preferencias = f"""PERFIL EXPLÍCITO (lo que el usuario eligió al registrarse):
- Categorías favoritas: {", ".join(preferencias.get("categorias", []) or ["No especificado"])}
- Tallas: {", ".join(preferencias.get("tallas", []) or ["No especificado"])}
- Presupuesto máximo: ${preferencias.get("presupuesto_max", 500000)} COP
- Estilos de vida: {", ".join(preferencias.get("estilos", []) or ["No especificado"])}"""

        seccion_favoritos = "FAVORITOS ACTUALES: Sin favoritos guardados todavía."
        if detalles_favoritos:
            favs_str = "\n".join(
                f"- \"{f.get('titulo')}\" | Categoría: {f.get('categoria')} | Talla: {f.get('talla')} | Precio: ${f.get('precio')}"
                for f in detalles_favoritos
            )
            seccion_favoritos = f"""FAVORITOS ACTUALES DEL USUARIO (prendas que ya tiene guardadas — NO las recomiendes de nuevo, pero úsalas como señal de su gusto):
{favs_str}

IMPORTANTE: Estas prendas revelan el gusto real del usuario. Busca en el catálogo prendas similares en estilo, categoría o precio que aún no tiene."""

        seccion_comportamiento = "COMPORTAMIENTO REAL: Sin datos suficientes aún."
        if comportamiento:
            seccion_comportamiento = f"""COMPORTAMIENTO REAL (últimos 7 días — mayor peso que el perfil explícito):
- Términos buscados: {", ".join(comportamiento.get("busquedas", []) or ["Ninguno aún"])}
- Categorías más vistas: {", ".join(comportamiento.get("topCategorias", []) or ["Ninguna aún"])}
- Prendas agregadas a favoritos esta semana: {comportamiento.get("totalFavoritos", 0)}
- Prendas agregadas al carrito esta semana: {comportamiento.get("totalCarrito", 0)}

IMPORTANTE: El comportamiento real debe tener mayor peso que las preferencias declaradas."""

        prompt = f"""Eres el motor de recomendaciones de Vint, una plataforma de moda de segunda mano en Colombia. Analiza el perfil completo del usuario para recomendarle exactamente 10 prendas del catálogo disponible.

PRIORIDAD DE SEÑALES (de mayor a menor):
1. FAVORITOS ACTUALES — revelan el gusto real del usuario
2. COMPORTAMIENTO REAL — búsquedas y vistas recientes
3. PERFIL EXPLÍCITO — preferencias declaradas al registrarse

{seccion_preferencias}
{seccion_favoritos}
{seccion_comportamiento}

CATÁLOGO DISPONIBLE:
{json.dumps(prendas, indent=2, ensure_ascii=False)}

REGLAS:
- Recomienda exactamente 10 prendas distintas
- NO recomiendes prendas que ya están en los favoritos del usuario
- Varía las categorías y precios para ofrecer diversidad
- La razón debe ser corta, personalizada y en español

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin backticks, con este formato exacto:
{{
  "recomendaciones": [
    {{
      "id_prenda": "string_uuid",
      "titulo": "string",
      "precio": número,
      "talla": "string",
      "condicion": "string",
      "vendedor": "string",
      "imagen_principal": "string",
      "categoria": "string",
      "razon": "Frase corta y personalizada explicando por qué esta prenda es perfecta para este usuario"
    }}
  ]
}}"""

        recs = []
        if settings.ANTHROPIC_API_KEY:
            try:
                anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                message = anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2500,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = message.content[0].text
                parsed = json.loads(text)
                recs = parsed.get("recomendaciones", [])
            except Exception as ae:
                print(f"[recomendaciones] Error llamando a Anthropic: {ae}")
                recs = obtener_recomendaciones_locales(prendas, preferencias, favorito_ids)
        else:
            recs = obtener_recomendaciones_locales(prendas, preferencias, favorito_ids)

        return {"recomendaciones": recs}
    except Exception as e:
        print(f"[recomendaciones] Error general: {e}")
        # En caso de error crítico, intentar un fallback local básico
        try:
            response = supabase.table("v_catalogo_publico").select(
                "id_prenda, titulo, precio, talla, condicion, vendedor, imagen_principal, categoria"
            ).limit(60).execute()
            prendas = response.data or []
            if prendas:
                recs = obtener_recomendaciones_locales(prendas, payload.preferencias, payload.favoritoIds)
                return {"recomendaciones": recs}
        except Exception as fallback_err:
            print(f"[recomendaciones] Fallback de emergencia falló: {fallback_err}")
            
        return {"recomendaciones": []}
