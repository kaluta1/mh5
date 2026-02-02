from fastapi import FastAPI, Response, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
import uvicorn
import os
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.services.payment_scheduler import payment_scheduler
from app.services.contest_status import contest_status_scheduler
from app.services.season_migration_scheduler import season_migration_scheduler
from app.services.monthly_round_scheduler import monthly_round_scheduler
from app.services.socketio_app import create_socketio_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop background services"""
    # Startup
    print("Starting schema fix for contest table...")
    try:
        from backend.fix_contest_schema import fix_schema
        fix_schema()
        print("✅ Schema fix completed")
    except ImportError:
        # Try local import if backend package not resolvable (local dev)
        try:
            from fix_contest_schema import fix_schema
            fix_schema()
            print("✅ Schema fix completed (local)")
        except Exception as e:
            print(f"⚠️ Could not import/run fix_contest_schema: {e}")
    except Exception as e:
        print(f"⚠️ Error running schema fix: {e}")

    print("Starting payment scheduler...")
    await payment_scheduler.start()
    
    print("Starting contest status scheduler...")
    await contest_status_scheduler.start()
    
    # --- AUTOMATIC MIGRATIONS ---
    def run_migrations():
        """Run alembic migrations in background"""
        import subprocess
        import os
        import logging
        
        logger = logging.getLogger("uvicorn.error")
        logger.info("Starting background database migrations...")
        
        try:
            env = os.environ.copy()
            # Ensure we can find the app
            project_root = os.path.dirname(os.path.abspath(__file__))
            if 'PYTHONPATH' in env:
                env['PYTHONPATH'] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
            else:
                env['PYTHONPATH'] = project_root
                
            # Run alembic upgrade heads
            result = subprocess.run(["alembic", "upgrade", "heads"], check=True, env=env, capture_output=True, text=True)
            logger.info("✅ Database migrations completed successfully")
            logger.info(result.stdout)
            
            # Init data after migrations if needed
            try:
                from app.initial_data import init_db
                logger.info("Initializing base data...")
                init_db()
                logger.info("✅ Base data initialized")
            except Exception as e:
                logger.warning(f"⚠️ Data initialization skipped or failed: {e}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Migration failed: {e}")
            logger.error(f"Stderr: {e.stderr}")
        except Exception as e:
            logger.error(f"❌ Error during background migration: {e}")

    # Start migrations in background thread
    import threading
    migration_thread = threading.Thread(target=run_migrations)
    migration_thread.daemon = True
    migration_thread.start()
    # ---------------------------

    
    # Start delayed background services (schedulers)
    # This ensures the API starts immediately and migrations have time to run
    def start_background_services():
        import time
        import asyncio
        import logging
        
        logger = logging.getLogger("uvicorn.error")
        
        async def _delayed_start():
            # Wait for migrations to likely complete (10 seconds)
            logger.info("⏳ Waiting 10s before starting background schedulers...")
            await asyncio.sleep(10)
            
            logger.info("Starting payment scheduler...")
            await payment_scheduler.start()
            
            logger.info("Starting contest status scheduler...")
            await contest_status_scheduler.start()
            
            logger.info("Starting season migration scheduler...")
            await season_migration_scheduler.start()
            
            logger.info("Starting monthly round scheduler...")
            await monthly_round_scheduler.start()
            
            # Ensure January round exists
            logger.info("Ensuring January round exists...")
            try:
                # Run in thread pool to avoid blocking async loop if it does heavy sync work
                # ensure_january_round_exists is synchronous DB code
                loop = asyncio.get_event_loop()
                january_round = await loop.run_in_executor(None, monthly_round_scheduler.ensure_january_round_exists)
                
                if january_round:
                    logger.info(f"✅ January round ready (id={january_round.id})")
                else:
                    logger.warn("⚠️ Could not create/verify January round")
            except Exception as e:
                logger.error(f"⚠️ Error ensuring January round: {e}")
                
        # Fire and forget the async task
        asyncio.create_task(_delayed_start())

    start_background_services()
    
    # Initialize encryption service for E2E messaging
    
    yield
    
    # Shutdown
    print("Stopping monthly round scheduler...")
    await monthly_round_scheduler.stop()
    
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
    redirect_slashes=True,
    lifespan=lifespan,
)

# Configuration CORS - DOIT être avant les autres middlewares
cors_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "https://myhigh5.com",
    "https://www.myhigh5.com",
    "https://mh5-hbjp.onrender.com",
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

# IMPORTANT: Ajouter le middleware CORS EN PREMIER
# Permettre tous les CORS sans restriction pour le développement
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,  # Use explicit origins list
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.vercel\.app$|^https://.*\.vercel\.dev$",  # Allow localhost and all Vercel deployments (both .app and .dev)
    allow_credentials=True,  # Allow credentials for authentication cookies/tokens
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
