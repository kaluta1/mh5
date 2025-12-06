from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
from app.core.config import settings
from app.api.api_v1.api import api_router

# Import all models to ensure they are registered with SQLAlchemy
import app.models

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API pour MyFav - Plateforme de concours modernes multi-langues",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
)

# Configuration CORS - DOIT être avant les autres middlewares
cors_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "https://mh5.vercel.app",
    "https://mh5-sbe4.onrender.com",
]

# Ajouter les origines depuis les settings
if settings.BACKEND_CORS_ORIGINS:
    cors_origins.extend(settings.BACKEND_CORS_ORIGINS)

# Nettoyer et supprimer les doublons
cors_origins = list(set([origin.strip() for origin in cors_origins if origin]))

print(f"CORS Origins configured: {cors_origins}")

# IMPORTANT: Ajouter le middleware CORS EN PREMIER
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Inclusion des routes API
app.include_router(api_router, prefix=settings.API_V1_STR)

# Servir les fichiers statiques (médias)
if os.path.exists(settings.LOCAL_STORAGE_PATH):
    app.mount("/media", StaticFiles(directory=settings.LOCAL_STORAGE_PATH), name="media")

# Route racine
@app.get("/", tags=["Status"])
def read_root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": "0.1.0",
        "documentation": "/docs"
    }

# Route de debug CORS
@app.get("/debug/cors", tags=["Debug"])
def debug_cors():
    return {
        "cors_origins": cors_origins,
        "environment": os.getenv("ENVIRONMENT", "not set"),
        "backend_cors_origins_from_settings": settings.BACKEND_CORS_ORIGINS
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.1.1.1", port=8000, reload=True)
