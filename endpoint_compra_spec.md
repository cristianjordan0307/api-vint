# Especificación: Endpoints de Compra Simulada y Historial

## Contexto

La app VINT (marketplace de ropa vintage) necesita **3 nuevos endpoints** en la API FastAPI para:
1. Procesar una compra simulada (sin pasarela de pago real)
2. Obtener el historial de compras de un comprador
3. Obtener el historial de ventas de un vendedor

La autenticación se hace con JWT de Supabase: el frontend envía `Authorization: Bearer <token>` y la API lo decodifica para obtener el `email` del usuario.

---

## Tabla `public.pedidos` (ya creada en Supabase)

```sql
CREATE TABLE IF NOT EXISTS public.pedidos (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,           -- comprador (auth.uid de Supabase)
  vendedor_id UUID NOT NULL,       -- vendedor (id_auth_supabase del dueño de la prenda)
  id_prenda INTEGER NOT NULL,      -- FK a catalogo.prendas.id_prenda
  titulo_prenda VARCHAR NOT NULL,  -- snapshot del título al momento de compra
  imagen_prenda VARCHAR,           -- snapshot de la imagen principal
  precio NUMERIC NOT NULL,         -- precio de la prenda
  total NUMERIC NOT NULL,          -- precio + envío (si aplica)
  estado TEXT NOT NULL DEFAULT 'completado',
  metodo_pago TEXT DEFAULT 'simulado',
  direccion_envio JSONB,           -- datos de envío del comprador
  created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Tablas existentes relevantes

### `catalogo.prendas`
| Columna | Tipo | Notas |
|---------|------|-------|
| `id_prenda` | integer | PK |
| `id_usuario` | integer | FK a `seguridad.usuarios.id_usuario` (el vendedor) |
| `titulo` | varchar | Título de la prenda |
| `precio` | numeric | Precio |
| `estado_publicacion` | varchar | `'DISPONIBLE'`, `'VENDIDA'`, `'PAUSADA'` |

### `catalogo.imagenes_prendas`
| Columna | Tipo | Notas |
|---------|------|-------|
| `id_prenda` | integer | FK a prendas |
| `url_imagen` | varchar | URL de la imagen |
| `es_principal` | boolean | true = imagen principal |

### `seguridad.usuarios`
| Columna | Tipo | Notas |
|---------|------|-------|
| `id_usuario` | integer | PK |
| `id_auth_supabase` | uuid | El UUID de auth de Supabase |
| `correo` | varchar | Email del usuario |

---

## Endpoint 1: `POST /api/checkout/comprar`

### Descripción
Procesa una compra simulada. Valida que las prendas estén disponibles, crea los registros de pedido, y marca las prendas como vendidas.

### Autenticación
- **Requerida**: `Authorization: Bearer <jwt_supabase>`
- Decodificar el JWT para obtener el `sub` (UUID del comprador en auth.users) y el `email`

### Request Body

```json
{
  "items": [
    {
      "id_prenda": 42,
      "precio": 85000
    },
    {
      "id_prenda": 17,
      "precio": 120000
    }
  ],
  "envio": {
    "nombre": "Juan Pérez",
    "telefono": "3001234567",
    "email": "juan@correo.com",
    "direccion": "Calle 45 # 12-34 Apto 302",
    "ciudad": "Bogotá",
    "info_adicional": "Conjunto residencial, torre A"
  },
  "costo_envio": 15000
}
```

### Lógica paso a paso (en una transacción)

```
1. Decodificar JWT → obtener comprador_uuid (sub) y comprador_email

2. Para cada item en items:
   a. Consultar catalogo.prendas WHERE id_prenda = item.id_prenda
   b. VALIDAR que estado_publicacion = 'DISPONIBLE'
      → Si no está disponible: ROLLBACK y retornar error 409
   c. Obtener id_usuario (del vendedor) de la prenda
   d. Consultar seguridad.usuarios WHERE id_usuario = prendas.id_usuario
      → Obtener id_auth_supabase del vendedor (este es el vendedor_id para la tabla pedidos)
   e. Obtener imagen principal:
      SELECT url_imagen FROM catalogo.imagenes_prendas 
      WHERE id_prenda = item.id_prenda AND es_principal = true 
      LIMIT 1
   f. Calcular total = item.precio + (costo_envio / cantidad_items)

3. Para cada item (ya validado):
   a. INSERT INTO public.pedidos:
      - id: gen_random_uuid() (automático)
      - user_id: comprador_uuid (del JWT)
      - vendedor_id: id_auth_supabase del vendedor (obtenido en paso 2d)
      - id_prenda: item.id_prenda
      - titulo_prenda: prendas.titulo
      - imagen_prenda: url de imagen principal (o null)
      - precio: item.precio
      - total: precio + parte proporcional del envío
      - estado: 'completado'
      - metodo_pago: 'simulado'
      - direccion_envio: el objeto envio como JSONB
      - created_at: now()
   
   b. UPDATE catalogo.prendas 
      SET estado_publicacion = 'VENDIDA' 
      WHERE id_prenda = item.id_prenda

4. COMMIT la transacción
```

### Response: Éxito (200)

```json
{
  "success": true,
  "message": "Compra procesada exitosamente",
  "data": {
    "pedidos": [
      {
        "id": "a1b2c3d4-...",
        "id_prenda": 42,
        "titulo_prenda": "Chaqueta Levi's Vintage",
        "precio": 85000,
        "total": 92500,
        "estado": "completado"
      },
      {
        "id": "e5f6g7h8-...",
        "id_prenda": 17,
        "titulo_prenda": "Pantalón Nike Retro",
        "precio": 120000,
        "total": 127500,
        "estado": "completado"
      }
    ],
    "total_compra": 220000,
    "cantidad_items": 2
  }
}
```

### Response: Error - Prenda no disponible (409)

```json
{
  "success": false,
  "error": "La prenda 'Chaqueta Levi's Vintage' ya no está disponible",
  "code": "PRENDA_NO_DISPONIBLE"
}
```

### Response: Error - No autenticado (401)

```json
{
  "success": false,
  "error": "Token inválido o expirado",
  "code": "AUTH_ERROR"
}
```

### Response: Error - Carrito vacío (400)

```json
{
  "success": false,
  "error": "El carrito está vacío",
  "code": "CARRITO_VACIO"
}
```

---

## Endpoint 2: `GET /api/pedidos/mis-compras`

### Descripción
Retorna todas las compras del usuario autenticado (como comprador), ordenadas de más reciente a más antigua.

### Autenticación
- **Requerida**: `Authorization: Bearer <jwt_supabase>`

### Lógica

```sql
SELECT id, id_prenda, titulo_prenda, imagen_prenda, precio, total, 
       estado, metodo_pago, direccion_envio, created_at
FROM public.pedidos
WHERE user_id = <comprador_uuid_del_jwt>
ORDER BY created_at DESC
```

### Response (200)

```json
{
  "success": true,
  "data": [
    {
      "id": "a1b2c3d4-...",
      "id_prenda": 42,
      "titulo_prenda": "Chaqueta Levi's Vintage",
      "imagen_prenda": "https://..../imagen.jpg",
      "precio": 85000,
      "total": 92500,
      "estado": "completado",
      "metodo_pago": "simulado",
      "created_at": "2026-09-12T20:30:00Z"
    }
  ],
  "count": 1
}
```

---

## Endpoint 3: `GET /api/pedidos/mis-ventas`

### Descripción
Retorna todas las ventas del usuario autenticado (como vendedor), ordenadas de más reciente a más antigua.

### Autenticación
- **Requerida**: `Authorization: Bearer <jwt_supabase>`

### Lógica

```sql
SELECT id, id_prenda, titulo_prenda, imagen_prenda, precio, total, 
       estado, metodo_pago, created_at,
       -- Opcionalmente traer el nombre del comprador
       (SELECT u.primer_nombre || ' ' || u.primer_apellido 
        FROM seguridad.usuarios u 
        WHERE u.id_auth_supabase = pedidos.user_id) AS nombre_comprador
FROM public.pedidos
WHERE vendedor_id = <vendedor_uuid_del_jwt>
ORDER BY created_at DESC
```

### Response (200)

```json
{
  "success": true,
  "data": [
    {
      "id": "a1b2c3d4-...",
      "id_prenda": 42,
      "titulo_prenda": "Chaqueta Levi's Vintage",
      "imagen_prenda": "https://..../imagen.jpg",
      "precio": 85000,
      "total": 92500,
      "estado": "completado",
      "nombre_comprador": "Juan Pérez",
      "created_at": "2026-09-12T20:30:00Z"
    }
  ],
  "count": 1
}
```

---

## Notas de Implementación

### Patrón de autenticación existente
Los endpoints existentes en la API (como `/api/products`) ya siguen este patrón:
- Reciben `Authorization: Bearer <token>` en el header
- Decodifican el JWT de Supabase para obtener el `email` y el `sub` (UUID)
- Si el token es inválido, retornan 401

### Conexión a la base de datos
La API ya se conecta a la misma base de datos PostgreSQL de Supabase. Las tablas están en diferentes esquemas:
- `public.pedidos` → esquema público
- `catalogo.prendas` → esquema `catalogo`
- `catalogo.imagenes_prendas` → esquema `catalogo`
- `seguridad.usuarios` → esquema `seguridad`

### Transaccionalidad
El endpoint `POST /api/checkout/comprar` **DEBE ser transaccional**. Si falla cualquier paso (prenda no disponible, error de inserción), se debe hacer ROLLBACK completo. No puede quedar una prenda marcada como VENDIDA sin su pedido correspondiente.

### Validación anti-autocompra (opcional pero recomendada)
Opcionalmente validar que el comprador no esté comprando su propia prenda (comparar `comprador_uuid` con `vendedor.id_auth_supabase`). Si es así, retornar error 400.

### Costo de envío
El `costo_envio` es fijo: **$15,000 COP** por compra (no por item). Si hay múltiples items, el costo se reparte proporcionalmente en el `total` de cada pedido, o se puede poner el envío completo solo en el primer pedido.
