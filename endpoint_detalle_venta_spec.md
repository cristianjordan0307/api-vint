# Especificación: Endpoint de Detalle de Venta de una Prenda (Opcional)

> **Para:** Agente de la API FastAPI (`api-vint`)  
> **Contexto:** La app móvil VINT consume las ventas mediante `GET /api/pedidos/mis-ventas`. Este nuevo endpoint puntual permite consultar el detalle de venta de una prenda específica por su `id_prenda`.

---

## 🔒 `GET /api/pedidos/prenda/{id_prenda}`

- **Auth:** 🔒 Requerida (`Authorization: Bearer <token>`)
- **Descripción:** Obtiene los datos del pedido asociado a una prenda vendida perteneciente al vendedor autenticado.
- **Path Parameter:** `id_prenda` (integer)

### Reglas de Validación
1. El usuario debe estar autenticado con su JWT de Supabase.
2. La prenda debe pertenecer al vendedor autenticado (`vendedor_id == user.id`).
3. Si la prenda no tiene un pedido en `public.pedidos`, retornar 404.

---

### Respuesta Exitosa (200 OK)

```json
{
  "success": true,
  "data": {
    "id": "ce53b844-0d62-4056-906f-cc1147ba4fcb",
    "id_prenda": 331,
    "titulo_prenda": "Chaqueta Levi's Vintage",
    "imagen_prenda": "https://vint.com/imagen.jpg",
    "precio": 70000,
    "total": 85000,
    "estado": "completado",
    "metodo_pago": "simulado",
    "nombre_comprador": "Juan Pérez",
    "created_at": "2026-09-12T20:36:43.042087+00:00"
  }
}
```

---

### Respuestas de Error

- **401 Unauthorized:**
```json
{
  "success": false,
  "error": "Token inválido o expirado",
  "code": "AUTH_ERROR"
}
```

- **404 Not Found:**
```json
{
  "success": false,
  "error": "No se encontró registro de venta para esta prenda",
  "code": "VENTA_NO_ENCONTRADA"
}
```

---

### Código para FastAPI (`routers/pedidos.py`)

```python
@router.get("/prenda/{id_prenda}")
async def get_detalle_venta_prenda(id_prenda: int, user=Depends(get_current_user_pedidos)):
    """Obtiene los datos del pedido de una prenda vendida específica."""
    client = get_admin_client()
    vendedor_uuid = str(user.id)

    res = (
        client.schema("public")
        .from_("pedidos")
        .select("*")
        .eq("id_prenda", id_prenda)
        .eq("vendedor_id", vendedor_uuid)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        raise PedidoError(
            status_code=404,
            error="No se encontró registro de venta para esta prenda",
            code="VENTA_NO_ENCONTRADA",
        )

    order = res.data[0]
    return {
        "success": True,
        "data": {
            "id": order["id"],
            "id_prenda": order["id_prenda"],
            "titulo_prenda": order.get("titulo_prenda"),
            "imagen_prenda": order.get("imagen_prenda"),
            "precio": order.get("precio"),
            "total": order.get("total"),
            "estado": order.get("estado"),
            "metodo_pago": order.get("metodo_pago"),
            "nombre_comprador": order.get("nombre_comprador", "Comprador"),
            "created_at": order.get("created_at"),
        }
    }
```
