"""
Vercel Serverless Function adapter for FastAPI
This file adapts the FastAPI app to work with Vercel's serverless functions
"""
import sys
import os

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from mangum import Mangum
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.api_v1.api import api_router

# Create FastAPI app WITHOUT lifespan (serverless doesn't support long-running tasks)
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API pour MyHigh5 - Plateforme de concours modernes multi-langues",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=True,
)

# CORS Configuration
cors_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "https://myhigh5.com",
    "https://www.myhigh5.com",
    "https://myhigh5.vercel.app",
]

if settings.BACKEND_CORS_ORIGINS:
    cors_origins.extend(settings.BACKEND_CORS_ORIGINS)

cors_origins = list(set([origin.strip() for origin in cors_origins if origin]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|.*\.vercel\.app)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)

# Health check
@app.get("/", tags=["Status"])
def read_root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": "0.1.0",
        "deployment": "vercel-serverless",
        "documentation": "/docs"
    }

@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "healthy", "deployment": "vercel-serverless"}

# Create Mangum handler for Vercel
handler = Mangum(app, lifespan="off")
