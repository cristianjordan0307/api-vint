# Especificación Técnica: Normalización de Estados/Condición de Prenda

> **Destinatario:** Agente de Backend / API FastAPI (`api-vint`) y Administrador de Base de Datos (Supabase)  
> **Fecha:** 15 de Septiembre de 2026  
> **Objetivo:** Reemplazar el campo libre `VARCHAR` de condición/estado de la prenda por una tabla normalizada en el esquema `catalogo` (`catalogo.estados_prenda`), relacionarla mediante clave foránea con `catalogo.prendas` y exponer el nuevo endpoint en FastAPI para alimentar el selector de estado en la app móvil y web.

---

## 1. Contexto y Justificación

Actualmente, el estado físico o condición de la prenda se almacena como texto plano (`VARCHAR`) en `catalogo.prendas` (`condicion` o `condition`), lo cual causa:
- Inconsistencias ortográficas y de formato (`'BUEN_ESTADO'`, `'Buen estado'`, `'buen_estado'`).
- Imposibilidad de que el cliente móvil/web consuma las opciones reales y dinámicas configuradas en la base de datos.
- Falta de integridad referencial.

Se requiere:
1. Una tabla maestra `catalogo.estados_prenda` con los 6 estados definidos por negocio:
   - **Nuevo con etiqueta**
   - **Nuevo sin etiqueta**
   - **Excelente estado**
   - **Buen estado**
   - **Aceptable**
   - **Regular**
2. Conexión de clave foránea `catalogo.prendas.id_estado_prenda -> catalogo.estados_prenda(id_estado_prenda)`.
3. Migración segura de datos existentes para no romper publicaciones activas.
4. Endpoint público en FastAPI `GET /api/products/estados` (análogo a `/categories` y `/marcas`).
5. Actualización de `ProductCreate`, `ProductUpdate` y respuestas de productos para aceptar y retornar el estado normalizado.

---

## 2. Script SQL de Migración (Supabase / PostgreSQL)

Ejecutar el siguiente bloque SQL en el **SQL Editor** de Supabase:

```sql
-- =============================================================================
-- MIGRACIÓN: CREACIÓN DE TABLA catalogo.estados_prenda Y RELACIÓN CON catalogo.prendas
-- =============================================================================

BEGIN;

-- 1. Crear tabla catalogo.estados_prenda
CREATE TABLE IF NOT EXISTS catalogo.estados_prenda (
    id_estado_prenda SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    descripcion TEXT,
    orden INT NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Comentario descriptivo
COMMENT ON TABLE catalogo.estados_prenda IS 'Catálogo maestro de condiciones físicas o estados de uso de las prendas.';

-- 2. Poblar los 6 estados solicitados
INSERT INTO catalogo.estados_prenda (nombre, codigo, descripcion, orden, activo)
VALUES
    ('Nuevo con etiqueta', 'NUEVO_CON_ETIQUETA', 'Prenda jamás usada que conserva sus etiquetas originales de fábrica.', 1, TRUE),
    ('Nuevo sin etiqueta', 'NUEVO_SIN_ETIQUETA', 'Prenda nueva sin uso, pero sin la etiqueta original de tienda.', 2, TRUE),
    ('Excelente estado',   'EXCELENTE_ESTADO',   'Prenda usada en contadas ocasiones, sin marcas visibles de desgaste.', 3, TRUE),
    ('Buen estado',        'BUEN_ESTADO',        'Prenda con uso moderado, bien conservada y sin defectos funcionales.', 4, TRUE),
    ('Aceptable',          'ACEPTABLE',          'Prenda con signos evidentes de uso o desgaste leve.', 5, TRUE),
    ('Regular',            'REGULAR',            'Prenda con desgaste notorio, detalles estéticos o para restaurar.', 6, TRUE)
ON CONFLICT (codigo) DO UPDATE
SET 
    nombre = EXCLUDED.nombre,
    descripcion = EXCLUDED.descripcion,
    orden = EXCLUDED.orden,
    activo = EXCLUDED.activo;

-- 3. Agregar columna id_estado_prenda a catalogo.prendas (si no existe)
ALTER TABLE catalogo.prendas 
ADD COLUMN IF NOT EXISTS id_estado_prenda INTEGER REFERENCES catalogo.estados_prenda(id_estado_prenda);

-- Índice para optimizar búsquedas y joins
CREATE INDEX IF NOT EXISTS idx_prendas_id_estado_prenda 
ON catalogo.prendas(id_estado_prenda);

-- 4. Migrar los valores de texto actuales en catalogo.prendas (si existe la columna condicion o estado_prenda)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'catalogo' 
          AND table_name = 'prendas' 
          AND column_name = 'condicion'
    ) THEN
        -- Mapear valores antiguos a la nueva FK
        UPDATE catalogo.prendas p
        SET id_estado_prenda = e.id_estado_prenda
        FROM catalogo.estados_prenda e
        WHERE p.id_estado_prenda IS NULL
          AND (
              (UPPER(p.condicion) LIKE '%ETIQUETA%' AND UPPER(p.condicion) NOT LIKE '%SIN%' AND e.codigo = 'NUEVO_CON_ETIQUETA')
              OR (UPPER(p.condicion) LIKE '%SIN%ETIQUETA%' AND e.codigo = 'NUEVO_SIN_ETIQUETA')
              OR (UPPER(p.condicion) LIKE '%EXCELENTE%' OR UPPER(p.condicion) LIKE '%COMO_NUEVO%' AND e.codigo = 'EXCELENTE_ESTADO')
              OR (UPPER(p.condicion) LIKE '%BUEN%' AND e.codigo = 'BUEN_ESTADO')
              OR (UPPER(p.condicion) LIKE '%ACEPTABLE%' AND e.codigo = 'ACEPTABLE')
              OR (UPPER(p.condicion) LIKE '%REGULAR%' AND e.codigo = 'REGULAR')
              OR (UPPER(p.condicion) LIKE '%USADO%' AND e.codigo = 'BUEN_ESTADO')
          );

        -- Valor por defecto seguro para registros antiguos sin mapeo previo
        UPDATE catalogo.prendas
        SET id_estado_prenda = (SELECT id_estado_prenda FROM catalogo.estados_prenda WHERE codigo = 'BUEN_ESTADO')
        WHERE id_estado_prenda IS NULL;
    END IF;
END $$;

-- 5. Configurar permisos RLS (Row Level Security) para Supabase
ALTER TABLE catalogo.estados_prenda ENABLE ROW LEVEL SECURITY;

-- Lectura pública para cualquier usuario anon o autenticado
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'catalogo' 
          AND tablename = 'estados_prenda' 
          AND policyname = 'estados_prenda_select_public'
    ) THEN
        CREATE POLICY estados_prenda_select_public 
        ON catalogo.estados_prenda 
        FOR SELECT 
        TO anon, authenticated, service_role 
        USING (activo = TRUE);
    END IF;
END $$;

-- Otorgar privilegios de consulta
GRANT USAGE ON SCHEMA catalogo TO anon, authenticated, service_role;
GRANT SELECT ON catalogo.estados_prenda TO anon, authenticated, service_role;

-- 6. Actualizar o recrear vista pública catalogo.v_catalogo_publico si aplica
-- (Para exponer el nuevo id_estado_prenda y el nombre_estado_prenda)
CREATE OR REPLACE VIEW catalogo.v_catalogo_publico AS
SELECT 
    p.id_prenda,
    p.titulo,
    p.descripcion,
    p.id_categoria,
    c.nombre AS categoria,
    p.id_marca,
    m.nombre AS marca,
    p.talla,
    p.color,
    p.precio,
    p.genero,
    p.id_estado_prenda,
    COALESCE(ep.nombre, p.condicion) AS condicion,
    ep.nombre AS estado_prenda,
    p.fecha_publicacion,
    p.vendedor_id,
    u.nombre AS vendedor,
    u.email AS correo_vendedor,
    (
        SELECT pi.url_imagen 
        FROM catalogo.prendas_imagenes pi 
        WHERE pi.id_prenda = p.id_prenda AND pi.es_principal = TRUE 
        LIMIT 1
    ) AS imagen_principal
FROM catalogo.prendas p
LEFT JOIN catalogo.categorias c ON c.id_categoria = p.id_categoria
LEFT JOIN catalogo.marcas m ON m.id_marca = p.id_marca
LEFT JOIN catalogo.estados_prenda ep ON ep.id_estado_prenda = p.id_estado_prenda
LEFT JOIN seguridad.usuarios u ON u.id_auth_supabase::text = p.vendedor_id::text
WHERE p.estado_publicacion = 'DISPONIBLE' OR p.estado_publicacion = 'PUBLISHED';

GRANT SELECT ON catalogo.v_catalogo_publico TO anon, authenticated, service_role;

COMMIT;
```

---

## 3. Especificación de Cambios en la API FastAPI (`api-vint`)

### 3.1. Nuevo Endpoint: `GET /api/products/estados`

- **Tags:** `["Productos"]`
- **Auth:** Pública (sin token requerido, igual que `/api/products/categories` y `/api/products/marcas`).
- **Descripción:** Retorna todos los estados activos de las prendas para alimentar el dropdown del formulario de publicación y edición.

#### Respuesta Exitosa (200 OK)
```json
[
  {
    "id_estado_prenda": 1,
    "nombre": "Nuevo con etiqueta",
    "codigo": "NUEVO_CON_ETIQUETA",
    "descripcion": "Prenda jamás usada que conserva sus etiquetas originales de fábrica.",
    "orden": 1
  },
  {
    "id_estado_prenda": 2,
    "nombre": "Nuevo sin etiqueta",
    "codigo": "NUEVO_SIN_ETIQUETA",
    "descripcion": "Prenda nueva sin uso, pero sin la etiqueta original de tienda.",
    "orden": 2
  },
  {
    "id_estado_prenda": 3,
    "nombre": "Excelente estado",
    "codigo": "EXCELENTE_ESTADO",
    "descripcion": "Prenda usada en contadas ocasiones, sin marcas visibles de desgaste.",
    "orden": 3
  },
  {
    "id_estado_prenda": 4,
    "nombre": "Buen estado",
    "codigo": "BUEN_ESTADO",
    "descripcion": "Prenda con uso moderado, bien conservada y sin defectos funcionales.",
    "orden": 4
  },
  {
    "id_estado_prenda": 5,
    "nombre": "Aceptable",
    "codigo": "ACEPTABLE",
    "descripcion": "Prenda con signos evidentes de uso o desgaste leve.",
    "orden": 5
  },
  {
    "id_estado_prenda": 6,
    "nombre": "Regular",
    "codigo": "REGULAR",
    "descripcion": "Prenda con desgaste notorio, detalles estéticos o para restaurar.",
    "orden": 6
  }
]
```

---

### 3.2. Actualización de Modelos Pydantic (`schemas/products.py`)

Actualizar los esquemas de entrada y salida para soportar `id_estado_prenda`:

```python
class ProductCreate(BaseModel):
    name: str
    price: float
    description: Optional[str] = None
    category: Optional[str] = None
    category_id: Optional[int] = None
    brand: Optional[str] = None
    brand_id: Optional[int] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    id_estado_prenda: Optional[int] = None  # <-- NUEVO: ID de catalogo.estados_prenda
    condition: Optional[str] = None         # Mantener por retrocompatibilidad
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
    id_estado_prenda: Optional[int] = None  # <-- NUEVO: ID de catalogo.estados_prenda
    condition: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
```

---

### 3.3. Implementación en FastAPI (`routers/products.py`)

#### A. Endpoint `GET /api/products/estados`
```python
@router.get("/estados", summary="Get Estados Prenda", tags=["Productos"])
async def get_estados_prenda():
    """Retorna los estados o condiciones físicas disponibles para las prendas."""
    client = get_admin_client()
    res = (
        client.schema("catalogo")
        .from_("estados_prenda")
        .select("id_estado_prenda, nombre, codigo, descripcion, orden")
        .eq("activo", True)
        .order("orden")
        .execute()
    )
    return res.data or []
```

#### B. Inserción en `POST /api/products`
Al insertar en `catalogo.prendas`:
```python
# Resolver id_estado_prenda si viene directamente o mapear por condition string
id_estado = payload.id_estado_prenda
if not id_estado and payload.condition:
    # Búsqueda fallback por nombre o código si el cliente antiguo envió texto
    res_est = (
        client.schema("catalogo")
        .from_("estados_prenda")
        .select("id_estado_prenda")
        .or_(f"codigo.eq.{payload.condition},nombre.ilike.{payload.condition}")
        .limit(1)
        .execute()
    )
    if res_est.data:
        id_estado = res_est.data[0]["id_estado_prenda"]

insert_data = {
    "titulo": payload.name,
    "descripcion": payload.description,
    "precio": payload.price,
    "talla": payload.size,
    "color": payload.color,
    "genero": payload.gender,
    "id_estado_prenda": id_estado,
    # Mantener condicion como texto sincronizado para clientes antiguos si existe la columna:
    "condicion": payload.condition or "BUEN_ESTADO",
    ...
}
```

#### C. Actualización en `PATCH /api/products`
```python
update_data = {}
if payload.id_estado_prenda is not None:
    update_data["id_estado_prenda"] = payload.id_estado_prenda
    # Opcional: sincronizar nombre en columna de texto si existe
```

#### D. Consultas `GET /api/products` y `GET /api/products/{id_prenda}`
Añadir el JOIN o selección del objeto `estados_prenda`:
```python
.select(
    """
    *,
    categorias(id_categoria, nombre),
    marcas(id_marca, nombre),
    estados_prenda(id_estado_prenda, nombre, codigo)
    """
)
```
Y en el mapeo de respuesta retornar:
```json
{
  "id_prenda": 123,
  "id_estado_prenda": 1,
  "condicion": "Nuevo con etiqueta",
  "estado_prenda": {
    "id_estado_prenda": 1,
    "nombre": "Nuevo con etiqueta",
    "codigo": "NUEVO_CON_ETIQUETA"
  }
}
```

---

## 4. Pruebas de Aceptación

1. **SQL:** La tabla `catalogo.estados_prenda` contiene exactamente los 6 registros con sus órdenes del 1 al 6.
2. **FK:** `catalogo.prendas` no permite insertar un `id_estado_prenda` inexistente (lanza error de clave foránea).
3. **API:** `GET https://api-vint.onrender.com/api/products/estados` responde código 200 con la lista de los 6 estados.
4. **App Móvil:** El dropdown de "Estado de la prenda" en `CreateProductPage` se puebla dinámicamente mediante `GET /api/products/estados`, mostrando los nombres reales guardados en base de datos.
