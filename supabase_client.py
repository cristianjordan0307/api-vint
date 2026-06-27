"""
supabase_client.py — Clientes de Supabase para la API.

- admin_client: usa service_role key, bypassa RLS. Solo para operaciones de servidor.
- query_catalogo: función helper para consultar el schema 'catalogo' via PostgREST HTTP.
"""

from supabase import create_client, Client
from config import get_settings


def get_admin_client() -> Client:
    """Cliente administrativo con permisos de service_role (bypassa RLS)."""
    s = get_settings()
    return create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY)


def get_anon_client() -> Client:
    """Cliente con anon key (respeta RLS)."""
    s = get_settings()
    return create_client(s.SUPABASE_URL, s.SUPABASE_ANON_KEY)


def get_admin_client_for_schema(schema: str) -> Client:
    """
    Intenta crear cliente con schema específico.
    Si ClientOptions falla (bug en ciertas versiones de supabase-py),
    devuelve el cliente por defecto y el llamador debe usar schema() encadenado.
    """
    s = get_settings()
    try:
        from supabase.lib.client_options import ClientOptions
        opts = ClientOptions(schema=schema)
        return create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY, options=opts)
    except Exception:
        # Fallback: cliente normal, el schema se pasa con .schema() en la query
        return create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY)
