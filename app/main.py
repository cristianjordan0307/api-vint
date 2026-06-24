from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import products, recomendaciones, track

app = FastAPI(
    title="VINT API Backend",
    description="Servidor de API independiente en FastAPI para la aplicación VINT.",
    version="1.0.0"
)

# Configuración de CORS para permitir solicitudes del frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar los dominios permitidos (ej. localhost:3000)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar los enrutadores bajo el prefijo /api para coincidir con las llamadas del frontend
app.include_router(products.router, prefix="/api")
app.include_router(recomendaciones.router, prefix="/api")
app.include_router(track.router, prefix="/api")

@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": "VINT API Backend",
        "version": "1.0.0"
    }