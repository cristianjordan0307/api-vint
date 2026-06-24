from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import get_current_user
from app.core.supabase import supabase, ui_status_to_db, db_status_to_ui
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter(prefix="/products", tags=["products"])

class ProductCreatePayload(BaseModel):
    name: str
    description: Optional[str] = ""
    price: float
    category: Optional[str] = None
    image_url: Optional[str] = None
    size: Optional[str] = "Única"
    color: Optional[str] = "Combinado"
    gender: Optional[str] = "Unisex"
    condition: Optional[str] = "NUEVO"
    status: Optional[str] = "draft"

class ProductUpdatePayload(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    status: Optional[str] = None

class DeleteProductsPayload(BaseModel):
    ids: List[int]

def resolve_id_usuario(email: str) -> Optional[int]:
    try:
        response = supabase.rpc("get_id_usuario_por_correo", {"p_correo": email}).execute()
        if response.data is not None:
            return int(response.data)
        return None
    except Exception as e:
        print(f"[resolve_id_usuario] Error al resolver id_usuario para {email}: {e}")
        return None

def parse_category_id(cat: Optional[str]) -> int:
    if not cat:
        return 1
    try:
        return int(float(cat))
    except ValueError:
        return 1

@router.get("")
async def get_products(user: dict = Depends(get_current_user)):
    email = user.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado o sin correo electrónico."
        )
        
    id_usuario = resolve_id_usuario(email)
    if not id_usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no registrado en la base de datos de Vint."
        )
        
    try:
        response = supabase.schema("catalogo").table("prendas").select(
            "id_prenda, titulo, descripcion, precio, talla, color, genero, condicion, estado_publicacion, fecha_publicacion, id_categoria, imagenes_prendas(url_imagen, es_principal)"
        ).eq("id_usuario", id_usuario).order("fecha_publicacion", desc=True).execute()
        
        raw_products = response.data or []
        mapped = []
        for p in raw_products:
            imgs = p.get("imagenes_prendas", []) or []
            principal = next((i for i in imgs if i.get("es_principal")), None)
            if not principal and imgs:
                principal = imgs[0]
            
            image_url = principal.get("url_imagen") if principal else None
            
            mapped.append({
                "id": str(p["id_prenda"]),
                "name": p.get("titulo") or "",
                "description": p.get("descripcion") or "",
                "price": float(p.get("precio") or 0),
                "stock": 1,
                "sku": "",
                "category": "",
                "category_id": p.get("id_categoria"),
                "status": db_status_to_ui(p.get("estado_publicacion") or "PAUSADA"),
                "image_url": image_url,
                "created_at": p.get("fecha_publicacion") or datetime.utcnow().isoformat(),
                "updated_at": p.get("fecha_publicacion") or datetime.utcnow().isoformat(),
            })
            
        return {"data": mapped, "count": len(mapped)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar productos: {str(e)}"
        )

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreatePayload, user: dict = Depends(get_current_user)):
    email = user.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado o sin correo electrónico."
        )
        
    id_usuario = resolve_id_usuario(email)
    if not id_usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no registrado en la base de datos de Vint."
        )
        
    try:
        prenda_data = {
            "id_usuario": id_usuario,
            "id_categoria": parse_category_id(payload.category),
            "id_marca": 1,
            "titulo": payload.name,
            "descripcion": payload.description or "",
            "precio": float(payload.price),
            "talla": payload.size or "Única",
            "color": payload.color or "Combinado",
            "genero": payload.gender or "Unisex",
            "condicion": "NUEVO" if (payload.condition or "NUEVO").upper() == "NUEVO" else "USADO",
            "estado_publicacion": ui_status_to_db(payload.status or "draft"),
        }
        
        response = supabase.schema("catalogo").table("prendas").insert(prenda_data).execute()
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo crear la prenda en la base de datos."
            )
            
        prenda = response.data[0]
        id_prenda = prenda.get("id_prenda")
        
        if payload.image_url and id_prenda:
            img_data = {
                "id_prenda": id_prenda,
                "url_imagen": payload.image_url,
                "es_principal": True,
                "orden": 0
            }
            supabase.schema("catalogo").table("imagenes_prendas").insert(img_data).execute()
            
        return {"data": prenda}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear el producto: {str(e)}"
        )

@router.patch("")
async def update_product(payload: ProductUpdatePayload, user: dict = Depends(get_current_user)):
    email = user.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado."
        )
        
    try:
        db_update = {}
        if payload.name is not None:
            db_update["titulo"] = payload.name
        if payload.description is not None:
            db_update["descripcion"] = payload.description
        if payload.price is not None:
            db_update["precio"] = float(payload.price)
        if payload.status is not None:
            db_update["estado_publicacion"] = ui_status_to_db(payload.status)
            
        if not db_update:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se proporcionaron campos para actualizar."
            )
            
        response = supabase.schema("catalogo").table("prendas").update(db_update).eq("id_prenda", payload.id).execute()
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Producto no encontrado o no autorizado para actualizar."
            )
            
        return {"data": response.data[0]}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el producto: {str(e)}"
        )

@router.delete("")
async def delete_products(payload: DeleteProductsPayload, user: dict = Depends(get_current_user)):
    email = user.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no autenticado."
        )
        
    if not payload.ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se requieren los IDs de los productos a eliminar."
        )
        
    try:
        supabase.schema("catalogo").table("prendas").delete().in_("id_prenda", payload.ids).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar productos: {str(e)}"
        )
