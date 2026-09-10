# VINT API — Nuevos Endpoints para CRUD de Prendas (App Móvil)

> **Para:** Desarrollador de la API FastAPI  
> **Contexto:** La app móvil de VINT necesita gestión completa de prendas (crear, editar, eliminar, imágenes). La API ya tiene los endpoints base de productos. Se necesitan los siguientes endpoints adicionales.

---

## Autenticación

Todos los endpoints marcados con 🔒 requieren el header:
```
Authorization: Bearer <supabase_jwt_token>
```
El token es el JWT de Supabase Auth (`session.access_token`). La API ya usa `HTTPBearer` para los endpoints existentes — el mismo esquema aplica aquí.

---

## Endpoints existentes (ya funcionan, no tocar)

| Método | Path | Descripción |
|--------|------|-------------|
| `GET` | `/api/products/categories` | Lista categorías |
| `GET` | `/api/products` 🔒 | Prendas del vendedor autenticado |
| `POST` | `/api/products` 🔒 | Crear prenda |
| `PATCH` | `/api/products` 🔒 | Actualizar prenda |
| `DELETE` | `/api/products` 🔒 | Eliminar prendas (array de IDs) |

---

## Nuevos endpoints requeridos

---

### 1. Listar marcas

```
GET /api/products/marcas
```

- **Auth:** No requerida
- **Descripción:** Retorna todas las marcas de `catalogo.marcas` para el dropdown del formulario de publicación.
- **Response 200:**
```json
[
  { "id_marca": 1, "nombre": "Nike" },
  { "id_marca": 2, "nombre": "Zara" }
]
```

---

### 2. Detalle de una prenda con sus imágenes

```
GET /api/products/{id_prenda}
```

- **Auth:** 🔒 Requerida (solo el propietario puede ver su prenda por este endpoint)
- **Path params:** `id_prenda: int`
- **Descripción:** Retorna los datos completos de una prenda + todas sus imágenes. Se usa en la pantalla de detalle y edición.
- **Response 200:**
```json
{
  "id_prenda": 42,
  "titulo": "Camiseta Vintage Nike",
  "descripcion": "Camiseta de algodón, poco uso",
  "id_categoria": 1,
  "categoria": "Camisetas",
  "id_marca": 3,
  "marca": "Nike",
  "talla": "M",
  "color": "Blanco",
  "precio": 45000,
  "genero": "Hombre",
  "condicion": "USADO",
  "estado_publicacion": "DISPONIBLE",
  "fecha_publicacion": "2026-09-10T20:00:00",
  "imagenes": [
    {
      "id_imagen": 10,
      "url_imagen": "https://...",
      "es_principal": true,
      "orden": 0
    }
  ]
}
```
- **Response 404:** Prenda no encontrada o no pertenece al usuario autenticado.

---

### 3. Agregar imagen a una prenda

```
POST /api/products/{id_prenda}/imagenes
```

- **Auth:** 🔒 Requerida
- **Path params:** `id_prenda: int`
- **Descripción:** Inserta una nueva fila en `catalogo.imagenes_prendas`. La app sube la imagen a Supabase Storage y manda la URL resultante.
- **Request body:**
```json
{
  "url_imagen": "https://nthcmtvncuevvczhlrhk.supabase.co/storage/v1/...",
  "es_principal": false,
  "orden": 1
}
```
- **Response 201:**
```json
{
  "id_imagen": 15,
  "id_prenda": 42,
  "url_imagen": "https://...",
  "es_principal": false,
  "orden": 1
}
```

---

### 4. Eliminar imagen de una prenda

```
DELETE /api/products/{id_prenda}/imagenes/{id_imagen}
```

- **Auth:** 🔒 Requerida
- **Path params:** `id_prenda: int`, `id_imagen: int`
- **Descripción:** Elimina la fila de `catalogo.imagenes_prendas`. Verificar que la prenda pertenezca al usuario autenticado antes de eliminar.
- **Response 200:**
```json
{ "message": "Imagen eliminada correctamente" }
```
- **Response 404:** Imagen no encontrada.

---

### 5. Marcar imagen como principal

```
PATCH /api/products/{id_prenda}/imagenes/{id_imagen}/principal
```

- **Auth:** 🔒 Requerida
- **Path params:** `id_prenda: int`, `id_imagen: int`
- **Descripción:** Pone `es_principal = true` a la imagen indicada y `es_principal = false` a todas las demás imágenes de esa prenda (solo puede haber una principal).
- **Response 200:**
```json
{ "message": "Imagen principal actualizada" }
```

---

### 6. Stats del dashboard del vendedor

```
GET /api/vendedor/stats
```

- **Auth:** 🔒 Requerida
- **Descripción:** Retorna las estadísticas del vendedor autenticado desde la vista `seguridad.v_dashboard_vendedores`. Se usa en la pantalla de inicio (Home) de la app.
- **Response 200:**
```json
{
  "vendedor": "Juan Pérez",
  "total_publicadas": 10,
  "disponibles": 6,
  "vendidas": 3,
  "pausadas": 1,
  "ingresos_totales": 450000,
  "precio_promedio_vendido": 150000
}
```

---

## Notas importantes para la implementación

1. **Verificación de ownership:** En los endpoints de imágenes (POST, DELETE, PATCH), siempre verificar que `catalogo.prendas.id_usuario` coincida con el `id_usuario` del JWT antes de proceder. Esto evita que un vendedor manipule prendas de otro.

2. **Tabla de imágenes:** `catalogo.imagenes_prendas` — columnas: `id_imagen`, `id_prenda`, `url_imagen`, `es_principal` (boolean), `orden` (smallint).

3. **Storage de imágenes:** La app móvil subirá imágenes directamente a **Supabase Storage** y mandará la URL pública al endpoint `POST /imagenes`. La API no maneja el upload del archivo, solo guarda la URL en la BD.

4. **Endpoint de marcas:** Puede leerse directamente desde Supabase sin necesidad de endpoint si se prefiere, pero tenerlo en la API mantiene la arquitectura consistente.

5. **Schema catalogo:** Los endpoints existentes ya usan el schema `catalogo`. Mantener el mismo patrón.
