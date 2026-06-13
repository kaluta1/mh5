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

# Setup Logger to fix NameError globally
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

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
    """Fail fast when required critical secrets are missing, but warn for optional features."""
    # .env-এ ENVIRONMENT সেট করা না থাকলে ডিফল্ট 'development' ধরবে, যাতে লোকাল বা টেস্ট সার্ভারে হুট করে ক্র্যাশ না করে
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    
    critical_errors = []
    payment_warnings = []

    # 1. Critical Security Checks: These checks are absolutely essential, and the application should never run without them.

    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        critical_errors.append(
            "SECRET_KEY is missing or too short (min 32 chars). JWT tokens are insecure. "
            "Set a strong SECRET_KEY in your .env file."
        )
    if not settings.MASTER_ENCRYPTION_KEY:
        critical_errors.append(
            "MASTER_ENCRYPTION_KEY is missing. End-to-end messaging encryption will not work."
        )
    if not settings.ENCRYPTION_KEY_DERIVATION_SALT:
        critical_errors.append(
            "ENCRYPTION_KEY_DERIVATION_SALT is missing. Set a random salt in your .env file."
        )

    # Optional Crypto Payment Check (If any crypto payment methods are missing, display a warning but keep the application running normally.)
    if not settings.BSC_PAYMENT_CONTRACT:
        payment_warnings.append(
            "BSC_PAYMENT_CONTRACT is missing. On-chain crypto payments will not work."
        )
    if not settings.BSC_USDT_ADDRESS:
        payment_warnings.append(
            "BSC_USDT_ADDRESS is missing. On-chain USDT payments will not work."
        )

    # Cryptogriphic key missing, the app will shut down in production 
    if critical_errors:
        print("\n" + "=" * 70)
        print("CRITICAL SECURITY / CONFIGURATION ERRORS")
        print("=" * 70)
        for e in critical_errors:
            print(f"🚫  {e}")
        print("=" * 70 + "\n")
        if is_production:
            raise RuntimeError("Missing required critical secrets. See console output above.")

    # If payment key missing then print the notice, don't crush 
    if payment_warnings:
        print("\n" + "=" * 70)
        print("CONFIG WARNINGS (NON-CRITICAL)")
        print("=" * 70)
        for w in payment_warnings:
            print(f"⚠️  {w}")
        print("=" * 70 + "\n")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop background services."""
    validate_critical_settings()

    # Start all background schedulers through the unified manager.
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
    "https://mh5-backend.onrender.com",
    "https://frontend-rho-eight-72.vercel.app",
    # ---- new domain ----
    "https://kaluta.tech",
    "https://www.kaluta.tech"
]

# Ajouter les origines depuis les settings
if settings.BACKEND_CORS_ORIGINS:
    if isinstance(settings.BACKEND_CORS_ORIGINS, str):
        cors_origins.extend([origin.strip() for origin in settings.BACKEND_CORS_ORIGINS.split(",") if origin.strip()])
    elif isinstance(settings.BACKEND_CORS_ORIGINS, list):
        cors_origins.extend([origin.strip() for origin in settings.BACKEND_CORS_ORIGINS if origin.strip()])

# Nettoyer et supprimer les doublons
cors_origins = list(set([origin.strip() for origin in cors_origins if origin]))

print(f"CORS Origins configured: {cors_origins}")

# Origin regex
_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|^https://.*\.vercel\.app$"
    r"|^https://.*\.vercel\.dev$"
    r"|^https://.*\.onrender\.com$"
    r"|^https?://(?:[0-9]{1,3}\.){3}[0-9]{1,3}(:\d+)?$"
)

# IMPORTANT: Ajouter le middleware CORS EN PREMIER
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# Additional CORS handling for edge cases
import re
from starlette.middleware.base import BaseHTTPMiddleware

class CORSExtraMiddleware(BaseHTTPMiddleware):
    """Ensure CORS headers are present for edge-case origins without duplicating
    headers already set by FastAPI's CORSMiddleware.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        origin = request.headers.get("origin")
        if not origin:
            return response

        # If FastAPI's CORSMiddleware already handled this origin, do nothing.
        if "access-control-allow-origin" in response.headers:
            return response

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

# GraphQL endpoint
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

# Intégration Socket.IO
socketio_app = create_socketio_app(app)

# Route racine
@app.get("/", tags=["Status"])
def read_root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": "0.1.0",
        "documentation": "/docs"
    }

# Route health check
@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "healthy"}

# Route favicon
@app.get("/favicon.ico", tags=["Static"], include_in_schema=False)
def favicon():
    return Response(status_code=204)

# Route robots.txt
@app.get("/robots.txt", tags=["Static"], include_in_schema=False)
def robots_txt():
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

# Custom exception handler for HTTP exceptions
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
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