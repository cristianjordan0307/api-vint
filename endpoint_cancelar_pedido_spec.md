# Especificación: Endpoint para Cancelar Compra / Pedido

## Contexto

En VINT, un comprador puede cancelar una compra desde su historial de **Mis Compras**.
Al cancelar la compra:
1. El pedido en `public.pedidos` cambia su `estado` a `'cancelado'`.
2. La prenda asociada en `catalogo.prendas` cambia su `estado_publicacion` a `'DISPONIBLE'` para que vuelva a aparecer en el marketplace.

---

## Tablas involucradas

### 1. `public.pedidos` (ya existente)
| Columna | Tipo | Uso en este endpoint |
|---------|------|----------------------|
| `id` | UUID | Identificador del pedido (parámetro de ruta `{pedido_id}`) |
| `user_id` | UUID | Debe coincidir con el `auth.uid` del comprador autenticado |
| `id_prenda` | INTEGER | ID de la prenda a reactivar |
| `estado` | TEXT | Se actualiza a `'cancelado'` |

### 2. `catalogo.prendas` (ya existente)
| Columna | Tipo | Uso en este endpoint |
|---------|------|----------------------|
| `id_prenda` | INTEGER | Clave primaria |
| `estado_publicacion` | VARCHAR | Se actualiza a `'DISPONIBLE'` |

> **Nota:** No se requiere crear ninguna tabla nueva. Solo se modifican estados en registros existentes.

---

## Endpoint: `POST /api/pedidos/{pedido_id}/cancelar`

### 1. Descripción
Cancela un pedido realizado por el comprador autenticado. Solo el comprador que realizó la compra (o un administrador) puede cancelar el pedido.

### 2. Autenticación
- **Requerida**: `Authorization: Bearer <jwt_supabase>`
- Se decodifica el token para extraer el `sub` (UUID del usuario autenticado).

### 3. Parámetros de Ruta
- `pedido_id` (UUID): El ID del pedido en `public.pedidos`.

### 4. Lógica del Endpoint (en una transacción)

```python
1. Decodificar JWT -> obtener user_id (UUID del comprador).
2. Consultar el pedido:
   SELECT id, id_prenda, user_id, estado 
   FROM public.pedidos 
   WHERE id = :pedido_id;

3. Validaciones:
   - Si no existe: Retornar 404 {"detail": "Pedido no encontrado"}
   - Si pedido.user_id != user_id: Retornar 403 {"detail": "No tienes permiso para cancelar este pedido"}
   - Si pedido.estado == 'cancelado': Retornar 400 {"detail": "Este pedido ya se encuentra cancelado"}

4. En una transacción de base de datos:
   a) Actualizar el pedido:
      UPDATE public.pedidos 
      SET estado = 'cancelado' 
      WHERE id = :pedido_id;

   b) Actualizar la prenda asociada para que vuelva a estar disponible:
      UPDATE catalogo.prendas 
      SET estado_publicacion = 'DISPONIBLE' 
      WHERE id_prenda = :id_prenda;

5. Retornar 200 OK:
   {
     "success": true,
     "message": "Compra cancelada correctamente. La prenda vuelve a estar disponible para la venta.",
     "data": {
       "pedido_id": str(pedido.id),
       "id_prenda": pedido.id_prenda,
       "estado": "cancelado"
     }
   }
```

---

## Ejemplo de Implementación en FastAPI / SQLAlchemy

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

router = APIRouter(prefix="/api/pedidos", tags=["Pedidos"])

@router.post("/{pedido_id}/cancelar")
def cancelar_pedido(
    pedido_id: UUID,
    current_user: dict = Depends(get_current_user), # Extrae user_id del JWT de Supabase
    db: Session = Depends(get_db)
):
    user_id = current_user.get("sub") or current_user.get("id")

    # 1. Buscar pedido
    pedido = db.execute(
        text("SELECT id, id_prenda, user_id, estado FROM public.pedidos WHERE id = :id"),
        {"id": str(pedido_id)}
    ).mappings().first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    if str(pedido["user_id"]) != str(user_id):
        raise HTTPException(status_code=403, detail="No tienes permiso para cancelar este pedido")

    if pedido["estado"] == "cancelado":
        raise HTTPException(status_code=400, detail="Este pedido ya ha sido cancelado previamente")

    # 2. Transacción de anulación
    try:
        # Marcar pedido como cancelado
        db.execute(
            text("UPDATE public.pedidos SET estado = 'cancelado' WHERE id = :id"),
            {"id": str(pedido_id)}
        )
        
        # Volver la prenda a DISPONIBLE
        db.execute(
            text("UPDATE catalogo.prendas SET estado_publicacion = 'DISPONIBLE' WHERE id_prenda = :id_prenda"),
            {"id_prenda": pedido["id_prenda"]}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al cancelar el pedido: {str(e)}")

    return {
        "success": True,
        "message": "Compra cancelada correctamente y prenda reincorporada al catálogo",
        "data": {
            "pedido_id": str(pedido["id"]),
            "id_prenda": pedido["id_prenda"],
            "estado": "cancelado"
        }
    }
```

---

## Códigos de Respuesta HTTP
- `200 OK`: Cancelación exitosa.
- `400 Bad Request`: El pedido ya estaba cancelado.
- `401 Unauthorized`: Token JWT ausente o inválido.
- `403 Forbidden`: El pedido pertenece a otro usuario.
- `404 Not Found`: El ID del pedido no existe.
- `500 Internal Server Error`: Error al persistir la transacción.
