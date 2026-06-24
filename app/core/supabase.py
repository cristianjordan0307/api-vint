from supabase import create_client, Client
from app.core.config import settings

# Cliente con service role para realizar operaciones administrativas y de bypass de RLS si es necesario
supabase: Client = create_client(
    settings.NEXT_PUBLIC_SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)

def ui_status_to_db(status: str) -> str:
    if status == 'published':
        return 'DISPONIBLE'
    if status == 'archived':
        return 'VENDIDA'
    return 'PAUSADA'

def db_status_to_ui(estado: str) -> str:
    if estado == 'DISPONIBLE':
        return 'published'
    if estado == 'VENDIDA':
        return 'archived'
    return 'draft'
