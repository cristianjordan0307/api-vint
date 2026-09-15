# Especificación Técnica: Búsqueda y Registro Dinámico de Marcas con Opción "Otra"

> **Destinatario:** Agente de Backend / API FastAPI (`api-vint`) y Administrador de Base de Datos (Supabase)  
> **Fecha:** 15 de Septiembre de 2026  
> **Objetivo:** Permitir que los usuarios seleccionen marcas registradas desde `catalogo.marcas`, busquen en tiempo real, tengan por defecto "Sin marca", y puedan registrar marcas personalizadas mediante la opción "Otra (escribir marca)" persistiendo el nombre escrito en `catalogo.prendas.otra_marca`.

---

## 1. Cambios en la Base de Datos (Supabase / PostgreSQL)

Ejecutar el siguiente script en el **SQL Editor** de Supabase:

```sql
BEGIN;

-- 1. Asegurar que existe el registro 'Otra' en catalogo.marcas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM catalogo.marcas WHERE LOWER(nombre) IN ('otra', 'otra marca', 'otro')
    ) THEN
        INSERT INTO catalogo.marcas (nombre) VALUES ('Otra');
    END IF;
END $$;

-- 2. Agregar columna otra_marca a catalogo.prendas
ALTER TABLE catalogo.prendas 
ADD COLUMN IF NOT EXISTS otra_marca VARCHAR(100);

-- Comentario descriptivo
COMMENT ON COLUMN catalogo.prendas.otra_marca IS 'Almacena el nombre de la marca escrita manualmente por el usuario cuando selecciona la opción Otra.';

COMMIT;
```

---

## 2. Especificación de Cambios en la API FastAPI (`api-vint`)

### 2.1. Modelos Pydantic (`schemas/products.py`)

Actualizar `ProductCreate` y `ProductUpdate` para recibir `otra_marca` y `brand_id`:

```python
class ProductCreate(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
    category: Optional[str] = None
    category_id: Optional[int] = None
    brand: Optional[str] = None           # Nombre de marca o 'Otra' / 'Sin marca'
    brand_id: Optional[int] = None        # ID de catalogo.marcas (ej: 9 para Sin marca)
    otra_marca: Optional[str] = None      # <-- NUEVO: Texto de marca personalizada
    size: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    id_estado_prenda: Optional[int] = None
    condition: Optional[str] = None
    image_url: Optional[str] = None
    status: Optional[str] = "DISPONIBLE"

class ProductUpdate(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    status: Optional[str] = None
    image_url: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    id_estado_prenda: Optional[int] = None
    condition: Optional[str] = None
    brand: Optional[str] = None
    brand_id: Optional[int] = None
    otra_marca: Optional[str] = None      # <-- NUEVO: Texto de marca personalizada
    category: Optional[str] = None
    category_id: Optional[int] = None
```

---

### 2.2. Inserción en `POST /api/products` (`routers/products.py`)

Al insertar en `catalogo.prendas`:

```python
# 1. Resolver id_marca:
id_marca = payload.brand_id

if not id_marca and payload.brand:
    # Buscar ID por nombre en catalogo.marcas
    res_m = (
        client.schema("catalogo")
        .from_("marcas")
        .select("id_marca")
        .ilike("nombre", payload.brand.strip())
        .limit(1)
        .execute()
    )
    if res_m.data:
        id_marca = res_m.data[0]["id_marca"]

# Si el usuario seleccionó "Otra" o envió otra_marca
if payload.otra_marca:
    # Asignar id_marca de 'Otra' si existe en catalogo.marcas
    res_otra = (
        client.schema("catalogo")
        .from_("marcas")
        .select("id_marca")
        .ilike("nombre", "Otra%")
        .limit(1)
        .execute()
    )
    if res_otra.data:
        id_marca = res_otra.data[0]["id_marca"]

# Si no seleccionó ninguna marca, asignar por defecto 'Sin marca' (id_marca = 9)
if not id_marca:
    res_sin = (
        client.schema("catalogo")
        .from_("marcas")
        .select("id_marca")
        .ilike("nombre", "Sin marca")
        .limit(1)
        .execute()
    )
    if res_sin.data:
        id_marca = res_sin.data[0]["id_marca"]

insert_data = {
    "titulo": payload.name,
    "descripcion": payload.description,
    "precio": payload.price,
    "talla": payload.size,
    "id_categoria": id_categoria,
    "id_marca": id_marca,
    "otra_marca": payload.otra_marca.strip() if payload.otra_marca else None,
    "id_estado_prenda": id_estado,
    ...
}
```

---

### 2.3. Actualización en `PATCH /api/products` (`routers/products.py`)

```python
update_data = {}
if payload.brand_id is not None:
    update_data["id_marca"] = payload.brand_id

if payload.otra_marca is not None:
    update_data["otra_marca"] = payload.otra_marca.strip() if payload.otra_marca else None

if payload.brand and not payload.brand_id:
    # Resolver id_marca por nombre
    res_m = client.schema("catalogo").from_("marcas").select("id_marca").ilike("nombre", payload.brand).limit(1).execute()
    if res_m.data:
        update_data["id_marca"] = res_m.data[0]["id_marca"]
```

---

### 2.4. Respuestas en `GET /api/products` y `GET /api/products/{id}`

En el mapeo del producto, devolver:
```json
{
  "id_prenda": 123,
  "id_marca": 41,
  "marca": "Vintage Colombia",
  "otra_marca": "Vintage Colombia",
  "marca_original": "Otra"
}
```
> **Regla de visualización:** Si `otra_marca` no es null y no está vacía, el campo `marca` (o `brand`) debe reflejar el texto de `otra_marca`. Si es null, refleja el nombre de `catalogo.marcas.nombre` o `"Sin marca"`.
