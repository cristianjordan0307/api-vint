"""
main.py — Punto de entrada de la API de VINT.

Configura FastAPI, CORS y registra todos los routers.
Ejecutar con: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings

from routers import products, admin, auth, recomendaciones, track

settings = get_settings()

app = FastAPI(
    title="VINT API",
    description=(
        "API de la plataforma VINT — Moda de segunda mano en Colombia. "
        "Gestión de productos, usuarios, roles, permisos, recomendaciones y analíticas."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Permitir peticiones desde el frontend de Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,       # http://localhost:3000
        "http://localhost:3001",      # Puerto alternativo de Next.js
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Registrar routers ────────────────────────────────────────────────────────
app.include_router(products.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(recomendaciones.router)
app.include_router(track.router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def health():
    return {"status": "ok", "service": "VINT API", "version": "1.0.0"}
