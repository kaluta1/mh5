"""
Database connection and session management for Supabase PostgreSQL
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Generator
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create engine for PostgreSQL (Neon or Supabase)
# Use database_url property which prefers DATABASE_URL over SUPABASE_DB_URL
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


async def init_db():
    """Initialize database connection"""
    try:
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
    except Exception as e:
        logger.warning(f"⚠️ Database connection failed: {e}")
        logger.warning("⚠️ Application will start without database. Some features may not work.")
        logger.warning("⚠️ Please configure SUPABASE_DB_URL in your .env file")
        # Don't raise - allow app to start without database


async def close_db():
    """Close database connection"""
    try:
        engine.dispose()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.error(f"❌ Error closing database: {e}")


def get_db() -> Generator:
    """
    Dependency for getting database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
