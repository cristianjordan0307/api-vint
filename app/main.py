from fastapi import FastAPI
from app.routers import users

app = FastAPI(title="Mi API", version="1.0.0")

app.include_router(users.router, prefix="/api/v1")