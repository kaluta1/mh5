from fastapi import FastAPI, Response, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import sys
import time
import uvicorn

# Fix Windows console encoding for emoji/log output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.services.socketio_app import create_socketio_app


def validate_critical_settings():
    """Fail fast when required secrets are not provided via env."""
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    errors = []
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        errors.append(
            "SECRET_KEY is missing or too short (min 32 chars). JWT tokens are insecure. "
            "Set a strong SECRET_KEY in your .env file."
        )
    if not settings.MASTER_ENCRYPTION_KEY:
        errors.append(
            "MASTER_ENCRYPTION_KEY is missing. End-to-end messaging encryption will not work."
        )
    if not settings.ENCRYPTION_KEY_DERIVATION_SALT:
        errors.append(
            "ENCRYPTION_KEY_DERIVATION_SALT is missing. Set a random salt in your .env file."
        )
    if not settings.BSC_PAYMENT_CONTRACT:
        errors.append(
            "BSC_PAYMENT_CONTRACT is missing. On-chain crypto payments will not work."
        )
    if not settings.BSC_USDT_ADDRESS:
        errors.append(
            "BSC_USDT_ADDRESS is missing. On-chain USDT payments will not work."
        )

    if errors:
        print("\n" + "=" * 70)
        print("SECURITY / CONFIGURATION ERRORS")
        print("=" * 70)
        for e in errors:
            print(f"🚫  {e}")
        print("=" * 70 + "\n")
        if is_production:
            raise RuntimeError("Missing required secrets. See console output above.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop background services."""
    validate_critical_settings()

    # NOTE: Database migrations are intentionally NOT run automatically here.
    # They should be applied explicitly during deployment (e.g. Render
    # buildCommand or a manual `alembic upgrade heads`). Running migrations in
    # a background thread can race with the first requests and hide failures.

    # Start all background schedulers through the unified manager.
    # If an external task runner (e.g. Celery) is enabled, skip the in-process
    # schedulers to avoid running the same jobs twice.
    from app.services.scheduler_manager import scheduler_manager
    use_celery = os.getenv("USE_CELERY", "false").lower() in ("true", "1", "yes")
    scheduler_task: asyncio.Task | None = None
    if use_celery:
        print("USE_CELERY is enabled: skipping in-process background schedulers.")
    else:
        scheduler_task = asyncio.create_task(scheduler_manager.start(delay_seconds=10))

    yield

    # Shutdown
    if scheduler_task is not None:
        await scheduler_manager.stop()
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

# Import all models to ensure they are registered with SQLAlchemy
import app.models

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API pour MyHigh5 - Plateforme de concours modernes multi-langues",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=True,
    lifespan=lifespan,
)

# Configuration CORS - DOIT être avant les autres middlewares
cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
    "https://myhigh5.com",
    "https://www.myhigh5.com",
    "https://mh5-hbjp.onrender.com",
    "https://mh5-backend.onrender.com",  # Alternative backend URL
    "https://frontend-rho-eight-72.vercel.app",  # Vercel frontend
    # Note: Wildcards don't work in allow_origins list, use allow_origin_regex instead
]

# Ajouter les origines depuis les settings
if settings.BACKEND_CORS_ORIGINS:
    # Handle both comma-separated string and list
    if isinstance(settings.BACKEND_CORS_ORIGINS, str):
        cors_origins.extend([origin.strip() for origin in settings.BACKEND_CORS_ORIGINS.split(",") if origin.strip()])
    elif isinstance(settings.BACKEND_CORS_ORIGINS, list):
        cors_origins.extend([origin.strip() for origin in settings.BACKEND_CORS_ORIGINS if origin.strip()])

# Nettoyer et supprimer les doublons
cors_origins = list(set([origin.strip() for origin in cors_origins if origin]))

print(f"CORS Origins configured: {cors_origins}")

# Origin regex: localhost, Vercel/Render deploys, and raw IPv4 (e.g. http://203.0.113.1:3000 on a VPS dev box).
_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|^https://.*\.vercel\.app$"
    r"|^https://.*\.vercel\.dev$"
    r"|^https://.*\.onrender\.com$"
    r"|^https?://(?:[0-9]{1,3}\.){3}[0-9]{1,3}(:\d+)?$"
)

# IMPORTANT: Ajouter le middleware CORS EN PREMIER
# Use regex to allow all Vercel deployments and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,  # Use explicit origins list
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=True,  # Allow credentials for authentication cookies/tokens
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Additional CORS handling for edge cases
import re
from starlette.middleware.base import BaseHTTPMiddleware

class CORSExtraMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        origin = request.headers.get("origin")
        if origin:
            # Check if origin matches our patterns
            is_allowed = (
                origin in cors_origins or
                re.match(r"^https://.*\.vercel\.(app|dev)$", origin) or
                re.match(r"^https://.*\.onrender\.com$", origin) or
                re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", origin) or
                re.match(r"^https?://(?:[0-9]{1,3}\.){3}[0-9]{1,3}(:\d+)?$", origin)
            )
            if is_allowed:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD"
                response.headers["Access-Control-Allow-Headers"] = "*"
        return response

app.add_middleware(CORSExtraMiddleware)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Lightweight request/response logging for debugging and monitoring."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s %s - %.2fms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "%s %s ERROR %s - %.2fms",
                request.method,
                request.url.path,
                exc.__class__.__name__,
                duration_ms,
                exc_info=True,
            )
            raise


app.add_middleware(RequestLoggingMiddleware)

# Inclusion des routes API
app.include_router(api_router, prefix=settings.API_V1_STR)

# GraphQL endpoint (optional - skip if strawberry not available)
try:
    from app.graphql.schema import graphql_app
    app.include_router(graphql_app, prefix="/graphql")
    print("✅ GraphQL endpoint available at /graphql")
except ImportError as e:
    print(f"⚠️  GraphQL endpoint not available: {e}")
    print("   Continuing without GraphQL support...")


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

# Route health check pour Docker
@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "healthy"}

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

# Route de debug CORS
@app.get("/debug/cors", tags=["Debug"])
def debug_cors():
    return {
        "cors_origins": cors_origins,
        "environment": os.getenv("ENVIRONMENT", "not set"),
        "backend_cors_origins_from_settings": settings.BACKEND_CORS_ORIGINS
    }

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

# Custom exception handler for all HTTP exceptions
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
