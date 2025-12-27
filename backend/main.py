from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn
import os
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.services.payment_scheduler import payment_scheduler
from app.services.contest_status import contest_status_scheduler
from app.services.season_migration_scheduler import season_migration_scheduler
from app.services.socketio_app import create_socketio_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop background services"""
    # Startup
    print("Starting payment scheduler...")
    await payment_scheduler.start()
    
    print("Starting contest status scheduler...")
    await contest_status_scheduler.start()
    
    print("Starting season migration scheduler...")
    await season_migration_scheduler.start()
    
    yield
    
    # Shutdown
    print("Stopping season migration scheduler...")
    await season_migration_scheduler.stop()
    
    print("Stopping contest status scheduler...")
    await contest_status_scheduler.stop()
    
    print("Stopping payment scheduler...")
    await payment_scheduler.stop()

# Import all models to ensure they are registered with SQLAlchemy
import app.models

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API pour MyHigh5 - Plateforme de concours modernes multi-langues",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
    lifespan=lifespan,
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
# Permettre tous les CORS sans restriction pour le développement
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Inclusion des routes API
app.include_router(api_router, prefix=settings.API_V1_STR)

# Servir les fichiers statiques (médias)
if os.path.exists(settings.LOCAL_STORAGE_PATH):
    app.mount("/media", StaticFiles(directory=settings.LOCAL_STORAGE_PATH), name="media")

# Intégration Socket.IO (optionnel)
socketio_app = create_socketio_app(app)
if socketio_app:
    # Si Socket.IO est disponible, utiliser l'app Socket.IO qui encapsule FastAPI
    # Sinon, utiliser directement l'app FastAPI
    pass  # L'app sera montée dans le serveur ASGI

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
