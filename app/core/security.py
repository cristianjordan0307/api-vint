from fastapi import Request, HTTPException, status
import httpx
import urllib.parse
import json
from app.core.config import settings

def get_jwt_from_request(request: Request) -> str:
    # 1. Intentar cabecera Authorization
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]

    # 2. Intentar Cookies (Supabase puede guardar la sesión fragmentada en varias cookies)
    project_ref = settings.NEXT_PUBLIC_SUPABASE_URL.split("//")[-1].split(".")[0]
    cookie_prefix = f"sb-{project_ref}-auth-token"

    # Filtrar cookies que coincidan con la sesión de Supabase
    matching_cookies = {k: v for k, v in request.cookies.items() if k.startswith(cookie_prefix)}
    if not matching_cookies:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Token de sesión no encontrado."
        )

    # Ordenar las cookies por su índice (para casos en que Supabase divide la cookie, ej. .0, .1)
    sorted_keys = sorted(matching_cookies.keys(), key=lambda x: int(x.split(".")[-1]) if "." in x else -1)
    raw_value = "".join(matching_cookies[k] for k in sorted_keys)

    decoded_val = urllib.parse.unquote(raw_value)
    
    # Intentar parsear como JSON (Supabase SSR guarda la sesión como un JSON serializado)
    try:
        parsed = json.loads(decoded_val)
        if isinstance(parsed, list) and len(parsed) > 0:
            # En arreglos de Supabase, el primer elemento suele ser el access_token
            return parsed[0]
        elif isinstance(parsed, dict):
            return parsed.get("access_token")
    except json.JSONDecodeError:
        pass

    # Si no es un JSON, verificar si el valor tiene el formato de un JWT (3 partes separadas por puntos)
    if len(decoded_val.split('.')) == 3:
        return decoded_val

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Formato de token de sesión inválido."
    )

async def get_current_user(request: Request) -> dict:
    """
    Dependencia de FastAPI que extrae el token JWT y valida la sesión con el servidor Auth de Supabase.
    Retorna el objeto JSON del usuario si es válido.
    """
    token = get_jwt_from_request(request)
    
    # Validar el token con Supabase Auth
    headers = {
        "apikey": settings.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{settings.NEXT_PUBLIC_SUPABASE_URL}/auth/v1/user",
                headers=headers,
                timeout=5.0
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Sesión de Supabase inválida o expirada."
                )
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"No se pudo conectar con el servicio de autenticación de Supabase: {str(e)}"
            )
