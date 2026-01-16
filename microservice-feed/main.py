"""
Feed Microservice - MyHigh5
Handles Groups, Messaging (E2E Encrypted), Posts, and Feed Generation
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api.v1.router import api_router
from app.services.encryption import init_encryption_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    logger.info("🚀 Starting Feed Microservice...")
    
    # Initialize database connection
    await init_db()
    logger.info("✅ Database connection initialized")
    
    # Initialize encryption service
    init_encryption_service()
    logger.info("✅ Encryption service initialized")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Feed Microservice...")
    await close_db()
    logger.info("✅ Database connection closed")


app = FastAPI(
    title="Feed Microservice - MyHigh5",
    description="Microservice for Groups, Messaging (E2E Encrypted), Posts, and Feed",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "feed-microservice",
        "version": "1.0.0"
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Feed Microservice",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
