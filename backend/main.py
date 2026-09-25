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
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").strip().lower() == "production"

# Fix Windows console encoding for emoji/log output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from app.core.config import settings
from app.core.build_info import BACKEND_BUILD_ID
from app.api.api_v1.api import api_router
from app.services.socketio_app import create_socketio_app


def validate_critical_settings():
    """Fail fast when required critical secrets are missing, but warn for optional features."""
    # .env-এ ENVIRONMENT সেট করা না থাকলে ডিফল্ট 'development' ধরবে, যাতে লোকাল বা টেস্ট সার্ভারে হুট করে ক্র্যাশ না করে
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    
    critical_errors = []
    payment_warnings = []

    raw_cors = os.getenv("BACKEND_CORS_ORIGINS", "").strip()
    if is_production:
        configured_origins = [item.strip() for item in raw_cors.split(",") if item.strip()]
        if not configured_origins:
            critical_errors.append("BACKEND_CORS_ORIGINS must be explicitly configured in production.")
        elif any(origin == "*" or not origin.startswith("https://") for origin in configured_origins):
            critical_errors.append("Production CORS origins must be explicit HTTPS origins without wildcards.")

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

    if settings.ALGORITHM not in {"HS256", "HS384", "HS512"}:
        critical_errors.append("ALGORITHM must be an approved HMAC JWT algorithm.")

    if is_production:
        if not settings.FRONTEND_URL.startswith("https://") or not settings.BACKEND_PUBLIC_URL.startswith("https://"):
            critical_errors.append("Public frontend/backend URLs must use HTTPS in production.")
        active_kyc = (settings.KYC_PROVIDER or "kaluta").strip().lower()
        if active_kyc == "kaluta" and settings.KALUTA_KYC_ENABLED and (not settings.KALUTA_API_KEY or not settings.KALUTA_WEBHOOK_SECRET):
            critical_errors.append("Active Kaluta KYC requires its API key and webhook secret.")
        if active_kyc in {"shufti", "shufti_pro"} and (not settings.SHUFTI_CLIENT_ID or not settings.SHUFTI_SECRET_KEY):
            critical_errors.append("Active Shufti KYC requires its client ID and secret.")
        url_shaped_checks = {
            "SHUFTI_SECRET_KEY": settings.SHUFTI_SECRET_KEY,
            "NOWPAYMENTS_IPN_SECRET": settings.NOWPAYMENTS_IPN_SECRET,
        }
        if settings.KALUTA_KYC_ENABLED:
            url_shaped_checks["KALUTA_WEBHOOK_SECRET"] = settings.KALUTA_WEBHOOK_SECRET
        if settings.ANNUALADS_ENABLED:
            url_shaped_checks["ANNUALADS_WEBHOOK_SECRET"] = settings.ANNUALADS_WEBHOOK_SECRET
        for name, value in url_shaped_checks.items():
            if value and str(value).strip().lower().startswith(("http://", "https://")):
                critical_errors.append(f"{name} has URL-shaped content instead of a secret.")

    if not settings.KALUTA_KYC_ENABLED:
        payment_warnings.append(
            "KALUTA KYC DISABLED — REAL WEBHOOK SECRET REQUIRED. Re-enable only after: "
            "(1) obtaining the real whsec_... webhook secret from the Kaluta Dashboard, "
            "(2) setting KALUTA_WEBHOOK_SECRET to that value, (3) verifying signature checks "
            "work safely, (4) setting KALUTA_KYC_ENABLED=true, then restarting."
        )
    if not settings.ANNUALADS_ENABLED:
        payment_warnings.append(
            "ANNUALADS DISABLED — REAL WEBHOOK SECRET REQUIRED. Re-enable only after: "
            "(1) obtaining the real webhook secret from the AnnualAds tenant dashboard, "
            "(2) setting ANNUALADS_WEBHOOK_SECRET to that value, (3) verifying provider-side "
            "webhook configuration, (4) setting ANNUALADS_ENABLED=true, then restarting."
        )
    if not settings.NOWPAYMENTS_API_KEY:
        payment_warnings.append(
            "NOWPAYMENTS_API_KEY is missing. Crypto checkout will not work."
        )
    if not settings.NOWPAYMENTS_IPN_SECRET:
        payment_warnings.append(
            "NOWPAYMENTS_IPN_SECRET is missing. Payment webhooks cannot be verified."
        )
        if is_production:
            critical_errors.append("NOWPAYMENTS_IPN_SECRET is required for production payment callbacks.")

    from app.services.nowpayments_service import payout_config_status

    payout_status = payout_config_status()
    if not payout_status["payouts_ready"]:
        payment_warnings.append(
            "Affiliate payouts are disabled until NOWPayments 2FA is configured. Missing: "
            + ", ".join(payout_status["missing"])
            + ". Use Authenticator app 2FA (not email), same as SmartBlogger."
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
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    redirect_slashes=True,
    lifespan=lifespan,
)

# Configuration CORS - DOIT être avant les autres middlewares
development_cors_origins = [
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

cors_origins = [] if IS_PRODUCTION else development_cors_origins

# Ajouter les origines depuis les settings
if settings.BACKEND_CORS_ORIGINS:
    if isinstance(settings.BACKEND_CORS_ORIGINS, str):
        cors_origins.extend([origin.strip() for origin in settings.BACKEND_CORS_ORIGINS.split(",") if origin.strip()])
    elif isinstance(settings.BACKEND_CORS_ORIGINS, list):
        cors_origins.extend([origin.strip() for origin in settings.BACKEND_CORS_ORIGINS if origin.strip()])

# Nettoyer et supprimer les doublons
cors_origins = list(set([origin.strip() for origin in cors_origins if origin]))

logger.info("CORS configured with %d explicit origins", len(cors_origins))

# Origin regex
_CORS_ORIGIN_REGEX = None if IS_PRODUCTION else (
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
    expose_headers=["X-Backend-Build-Id"],
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

        is_allowed = origin in cors_origins or (not IS_PRODUCTION and (
            re.match(r"^https://.*\.vercel\.(app|dev)$", origin) or
            re.match(r"^https://.*\.onrender\.com$", origin) or
            re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", origin) or
            re.match(r"^https?://(?:[0-9]{1,3}\.){3}[0-9]{1,3}(:\d+)?$", origin)
        ))
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


class BuildIdMiddleware(BaseHTTPMiddleware):
    """Expose build id on every API response (nginx may not proxy public /health)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Backend-Build-Id"] = BACKEND_BUILD_ID
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to every API response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), payment=(self)"
        )
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


from app.core.rate_limit import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BuildIdMiddleware)

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


# Servir les fichiers statiques (médias) — always mount primary storage dir
from app.core.storage import PublicMediaStaticFiles, media_storage_roots

_media_root = next(
    (p for p in media_storage_roots() if os.path.isdir(p)),
    settings.LOCAL_STORAGE_PATH,
)
try:
    os.makedirs(_media_root, exist_ok=True)
    # PublicMediaStaticFiles refuses KYC documents (legacy ones live in this root).
    app.mount("/media", PublicMediaStaticFiles(directory=_media_root), name="media")
except Exception as mount_err:
    logger.warning("Static /media mount skipped: %s", mount_err)

# Intégration Socket.IO
socketio_app = create_socketio_app(app)

# Route racine
@app.get("/", tags=["Status"])
def read_root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": "0.1.0",
        "documentation": None if IS_PRODUCTION else "/docs"
    }


# Route health check
@app.get("/health", tags=["Status"])
def health_check():
    return {
        "status": "healthy",
        "build_id": BACKEND_BUILD_ID,
        "git_sha": os.getenv("GIT_SHA", BACKEND_BUILD_ID),
    }

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
@app.get("/debug/cors", tags=["Debug"], include_in_schema=not IS_PRODUCTION)
def debug_cors():
    if IS_PRODUCTION:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
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
    safe_detail = "Internal server error" if IS_PRODUCTION and exc.status_code >= 500 else exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": safe_detail,
            "code": f"HTTP_{exc.status_code}",
            "message": str(safe_detail)
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
