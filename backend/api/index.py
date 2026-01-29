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
from fastapi import FastAPI, Response, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
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

# Route favicon pour éviter les erreurs 404
@app.get("/favicon.ico", tags=["Static"], include_in_schema=False)
def favicon():
    """Handle favicon requests to prevent 404 errors"""
    return Response(status_code=204)  # No Content - browser will use default favicon

# Route robots.txt pour éviter les erreurs 404
@app.get("/robots.txt", tags=["Static"], include_in_schema=False)
def robots_txt():
    """Handle robots.txt requests to prevent 404 errors"""
    return Response(
        content="User-agent: *\nDisallow: /api/\nDisallow: /docs\nDisallow: /redoc\n",
        media_type="text/plain"
    )

# Custom exception handler for HTTP exceptions (including 404)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions (404, etc.) with a consistent error format"""
    if exc.status_code == 404:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": f"Route not found: {request.method} {request.url.path}",
                "code": "NOT_FOUND",
                "message": "The requested endpoint does not exist. Please check the API documentation at /docs",
                "path": str(request.url.path),
                "method": request.method
            }
        )
    # For other HTTP exceptions, return the default format
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail)
        }
    )

# Custom exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with a consistent format"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed"
        }
    )

# Create Mangum handler for Vercel
handler = Mangum(app, lifespan="off")
