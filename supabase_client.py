"""
supabase_client.py — Clientes de Supabase para la API.

- admin_client: usa service_role key, bypassa RLS. Solo para operaciones de servidor.
- Función helper para crear clientes con schema específico.
"""

from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from config import get_settings


def get_admin_client() -> Client:
    """Cliente administrativo con permisos de service_role (bypassa RLS)."""
    s = get_settings()
    return create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY)


def get_admin_client_for_schema(schema: str) -> Client:
    """Cliente administrativo con permisos de service_role configurado para un esquema específico."""
    s = get_settings()
    opts = ClientOptions(schema=schema)
    return create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY, options=opts)


def get_anon_client() -> Client:
    """Cliente con anon key (respeta RLS)."""
    s = get_settings()
    return create_client(s.SUPABASE_URL, s.SUPABASE_ANON_KEY)

