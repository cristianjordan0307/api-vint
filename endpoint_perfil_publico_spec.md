# Especificación: Endpoints de Perfil Público, Avatares y Estadísticas de Vendedor

## Contexto

En VINT (marketplace de ropa vintage), los usuarios necesitan:
1. **Ver el perfil público de cualquier vendedor** (`/tienda/{username}`):
   - Avatar público del vendedor (URL de imagen guardada en Supabase Storage o BD).
   - Nombre visible y `@username`.
   - Descripción o biografía pública ("Cuéntale a otros cómo describes tu estilo...").
   - Conteo real de **ventas exitosas** (pedidos completados).
   - Conteo de prendas activas en venta y calificación promedio.
2. **Consultar los datos del vendedor desde el modal de detalle de producto** en `/explorar`:
   - Mostrar foto de perfil real del vendedor, ventas reales y calificación real.
3. **Actualizar el propio perfil** desde `/perfil`:
   - Cambiar nombre, username (@), biografía/descripción, ciudad y URL del avatar.

Actualmente los endpoints existentes en la API (`/api/pedidos/mis-ventas` y `/api/vendedor/stats`) requieren token privado del propio usuario y no permiten que un comprador o visitante anónimo consulte el perfil ni las ventas de otro vendedor.

---

## Modificación de Base de Datos Necesaria

Se debe ejecutar previamente el script `actualizar_perfiles.sql` en Supabase para agregar las columnas y vistas:

```sql
ALTER TABLE seguridad.usuarios 
  ADD COLUMN IF NOT EXISTS username VARCHAR(60) UNIQUE,
  ADD COLUMN IF NOT EXISTS avatar_url TEXT,
  ADD COLUMN IF NOT EXISTS descripcion VARCHAR(255),
  ADD COLUMN IF NOT EXISTS ciudad VARCHAR(100) DEFAULT 'Colombia';
```

---

## Endpoint 1: `GET /api/vendedor/{identifier}/publico`

### 1. Descripción
Endpoint **público** (sin autenticación requerida) para obtener la tarjeta y datos de la tienda de un vendedor por su `username`, su `id_auth_supabase` (UUID) o su `id_usuario`.

### 2. Autenticación
- **No requerida** (público para cualquier visitante o comprador).

### 3. Parámetros de Ruta
- `identifier` (string): Puede ser:
  - El nombre de usuario sin `@` (ej: `hueleavo4`, `juanperez`)
  - O el UUID de Supabase Auth (ej: `0c50da0a-b08a-4008-8a78-29a3157aaa87`)
  - O el ID numérico (`id_usuario`)

### 4. Lógica del Endpoint

```python
1. Limpiar el identificador recibido (quitar '@' inicial si viene con arroba, trim, lowercase).

2. Buscar al usuario en la base de datos:
   - Si identifier tiene formato UUID:
       SELECT * FROM seguridad.usuarios WHERE id_auth_supabase = :identifier;
   - Si identifier es numérico:
       SELECT * FROM seguridad.usuarios WHERE id_usuario = :identifier;
   - De lo contrario:
       SELECT * FROM seguridad.usuarios WHERE LOWER(username) = LOWER(:identifier);

3. Si no se encuentra:
   - Retornar 404 {"detail": "Vendedor no encontrado"}

4. Consultar estadísticas de ventas reales:
   a) Ventas completadas en pedidos:
      SELECT COUNT(*) FROM public.pedidos 
      WHERE vendedor_id = :user.id_auth_supabase AND estado = 'completado';
   
   b) Prendas marcadas como vendidas:
      SELECT COUNT(*) FROM catalogo.prendas 
      WHERE id_usuario = :user.id_usuario AND estado_publicacion = 'VENDIDA';

   Total ventas exitosas = (a) + (b)

5. Consultar prendas disponibles en venta:
   SELECT COUNT(*) FROM catalogo.prendas 
   WHERE id_usuario = :user.id_usuario AND estado_publicacion = 'DISPONIBLE';

6. Consultar calificación promedio y total reseñas:
   SELECT 
     COALESCE(AVG(calificacion), 5.0) as promedio,
     COUNT(*) as total_comentarios
   FROM public.vendedor_comentarios 
   WHERE vendedor_id = :user.username OR vendedor_id = :user.id_auth_supabase::text;

7. Retornar 200 OK:
   {
     "success": true,
     "data": {
       "id_usuario": user.id_usuario,
       "id_auth_supabase": str(user.id_auth_supabase),
       "nombre": f"{user.primer_nombre} {user.primer_apellido or ''}".strip(),
       "username": user.username,
       "email": user.correo,
       "avatar_url": user.avatar_url,
       "descripcion": user.descripcion or "",
       "ciudad": user.ciudad or "Colombia",
       "fecha_registro": user.fecha_registro.isoformat() if user.fecha_registro else None,
       "ventas_exitosas": total_ventas_exitosas,
       "prendas_en_venta": prendas_disponibles,
       "calificacion": round(float(promedio), 1),
       "total_resenas": total_comentarios
     }
   }
```

---

## Endpoint 2: `PUT /api/perfil/me`

### 1. Descripción
Actualiza los datos de perfil del usuario autenticado en la tabla `seguridad.usuarios`.

### 2. Autenticación
- **Requerida**: `Authorization: Bearer <jwt_supabase>`
- Se decodifica el token para extraer `sub` (UUID) o `email`.

### 3. Request Body (JSON)

```json
{
  "nombre": "Cristian Jordan",
  "username": "cristianjordan",
  "descripcion": "Amante de las chaquetas retro y el estilo vintage de los 90s.",
  "avatar_url": "https://nthcmtvncuevvczhlrhk.supabase.co/storage/v1/object/public/avatars/user-id.jpg",
  "ciudad": "Bogotá, Colombia"
}
```

### 4. Lógica del Endpoint

```python
1. Validar que el usuario exista a partir del token JWT (por id_auth_supabase o correo).

2. Validar username único:
   - Si se envía un nuevo username, verificar que no pertenezca a otro id_usuario:
     SELECT id_usuario FROM seguridad.usuarios 
     WHERE LOWER(username) = LOWER(:nuevo_username) AND id_usuario != :current_user.id_usuario;
   - Si ya existe: retornar 400 {"detail": "El nombre de usuario ya está en uso"}

3. Parsear nombre:
   - Desglosar 'nombre' en primer_nombre, segundo_nombre, primer_apellido, segundo_apellido.

4. Actualizar registro en seguridad.usuarios:
   UPDATE seguridad.usuarios
   SET primer_nombre = :primer_nombre,
       segundo_nombre = :segundo_nombre,
       primer_apellido = :primer_apellido,
       segundo_apellido = :segundo_apellido,
       username = LOWER(:username),
       descripcion = :descripcion,
       avatar_url = :avatar_url,
       ciudad = :ciudad
   WHERE id_usuario = :current_user.id_usuario;

5. Retornar 200 OK con los datos actualizados.
```

---

## Ejemplo de Implementación en FastAPI / SQLAlchemy

```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, text
import uuid

router = APIRouter(prefix="/api/perfil", tags=["Perfiles"])

# ── Schemas Pydantic ──────────────────────────────────────────────────────────

class ActualizarPerfilInput(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    descripcion: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[str] = None
    ciudad: Optional[str] = Field(None, max_length=100)

class PerfilPublicoResponse(BaseModel):
    success: bool = True
    data: dict

# ── Endpoint Público de Vendedor ──────────────────────────────────────────────

@router.get("/vendedor/{identifier}/publico", response_model=PerfilPublicoResponse)
def get_vendedor_publico(identifier: str, db: Session = Depends(get_db)):
    clean_id = identifier.lstrip("@").strip()
    
    # 1. Buscar usuario
    query = text("""
        SELECT id_usuario, id_auth_supabase, correo, primer_nombre, primer_apellido,
               username, avatar_url, descripcion, ciudad, fecha_registro
        FROM seguridad.usuarios
        WHERE LOWER(username) = LOWER(:id)
           OR id_auth_supabase::text = :id
           OR id_usuario::text = :id
        LIMIT 1
    """)
    user = db.execute(query, {"id": clean_id}).mappings().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Vendedor no encontrado"
        )

    # 2. Conteo de ventas exitosas
    ventas_query = text("""
        SELECT 
          COALESCE((SELECT COUNT(*) FROM public.pedidos WHERE vendedor_id = :auth_id AND estado = 'completado'), 0) +
          COALESCE((SELECT COUNT(*) FROM catalogo.prendas WHERE id_usuario = :user_id AND estado_publicacion = 'VENDIDA'), 0) 
          AS ventas_exitosas,
          COALESCE((SELECT COUNT(*) FROM catalogo.prendas WHERE id_usuario = :user_id AND estado_publicacion = 'DISPONIBLE'), 0) 
          AS prendas_disponibles
    """)
    stats_counts = db.execute(ventas_query, {
        "auth_id": user["id_auth_supabase"],
        "user_id": user["id_usuario"]
    }).mappings().first()

    # 3. Reseñas y Calificación
    calif_query = text("""
        SELECT COALESCE(AVG(calificacion), 5.0) as promedio, COUNT(*) as total
        FROM public.vendedor_comentarios
        WHERE vendedor_id = :username OR vendedor_id = :auth_id::text
    """)
    calif = db.execute(calif_query, {
        "username": user["username"] or "",
        "auth_id": user["id_auth_supabase"]
    }).mappings().first()

    nombre_completo = f"{user['primer_nombre']} {user['primer_apellido'] or ''}".strip()

    return {
        "success": True,
        "data": {
            "id_usuario": user["id_usuario"],
            "id_auth_supabase": str(user["id_auth_supabase"]) if user["id_auth_supabase"] else None,
            "nombre": nombre_completo,
            "username": user["username"] or clean_id,
            "email": user["correo"],
            "avatar_url": user["avatar_url"],
            "descripcion": user["descripcion"] or "",
            "ciudad": user["ciudad"] or "Colombia",
            "fecha_registro": user["fecha_registro"].isoformat() if user["fecha_registro"] else None,
            "ventas_exitosas": stats_counts["ventas_exitosas"] if stats_counts else 0,
            "prendas_en_venta": stats_counts["prendas_disponibles"] if stats_counts else 0,
            "calificacion": round(float(calif["promedio"]), 1) if calif else 5.0,
            "total_resenas": calif["total"] if calif else 0
        }
    }

# ── Endpoint Autenticado para Actualizar Perfil ───────────────────────────────

@router.put("/me")
def actualizar_mi_perfil(
    body: ActualizarPerfilInput,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user.get("sub") or current_user.get("id")
    email = current_user.get("email")

    # Validar username no duplicado
    if body.username:
        clean_user = body.username.lstrip("@").strip().lower()
        exists = db.execute(text("""
            SELECT id_usuario FROM seguridad.usuarios 
            WHERE LOWER(username) = :u AND (id_auth_supabase IS DISTINCT FROM :uid AND correo != :email)
        """), {"u": clean_user, "uid": user_id, "email": email}).first()
        if exists:
            raise HTTPException(status_code=400, detail=f"El username '@{clean_user}' ya está en uso")
    else:
        clean_user = None

    # Separar nombre
    parts = body.nombre.strip().split()
    p_nom = parts[0] if parts else ""
    s_nom = parts[1] if len(parts) >= 3 else ""
    p_ape = parts[2] if len(parts) >= 3 else (parts[1] if len(parts) == 2 else "")
    s_ape = " ".join(parts[3:]) if len(parts) >= 4 else ""

    update_query = text("""
        UPDATE seguridad.usuarios
        SET primer_nombre = COALESCE(NULLIF(:p_nom, ''), primer_nombre),
            segundo_nombre = NULLIF(:s_nom, ''),
            primer_apellido = COALESCE(NULLIF(:p_ape, ''), primer_apellido),
            segundo_apellido = NULLIF(:s_ape, ''),
            username = COALESCE(:username, username),
            descripcion = COALESCE(:desc, descripcion),
            avatar_url = COALESCE(:avatar, avatar_url),
            ciudad = COALESCE(:ciudad, ciudad)
        WHERE id_auth_supabase = :uid OR correo = :email
        RETURNING id_usuario, primer_nombre, primer_apellido, username, avatar_url, descripcion, ciudad;
    """)

    res = db.execute(update_query, {
        "p_nom": p_nom,
        "s_nom": s_nom,
        "p_ape": p_ape,
        "s_ape": s_ape,
        "username": clean_user,
        "desc": body.descripcion,
        "avatar": body.avatar_url,
        "ciudad": body.ciudad,
        "uid": user_id,
        "email": email
    }).mappings().first()

    db.commit()

    return {
        "success": True,
        "message": "Perfil actualizado correctamente",
        "data": dict(res) if res else {}
    }
```
