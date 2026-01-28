from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Use psycopg2-binary (already in requirements.txt)
# Do not convert to psycopg3 as psycopg2-binary is installed
database_url = settings.SQLALCHEMY_DATABASE_URI
# Keep postgresql:// for psycopg2-binary (no need to change)

# Engine configuration optimized for Neon PostgreSQL with SSL
# Reduced timeouts to avoid blocking
engine = create_engine(
    database_url,
    pool_pre_ping=True,  # Check connection before use
    pool_recycle=300,    # Recycle connections after 5 minutes (Neon timeout ~10 min)
    pool_size=5,         # Connection pool size
    max_overflow=10,     # Maximum number of additional connections
    pool_timeout=10,     # Timeout to get a connection from the pool (10 seconds)
    connect_args={
        "connect_timeout": 10,  # Initial connection timeout (10 seconds)
    },
    echo=False
)

# Event handler for connection errors
@event.listens_for(engine, "connect")
def set_ssl_mode(dbapi_conn, connection_record):
    """Configure SSL mode for PostgreSQL connections (Neon)"""
    try:
        # Neon PostgreSQL requires SSL
        # SSL configuration is managed via connection URL (sslmode=require)
        if hasattr(dbapi_conn, 'info'):
            logger.debug("Database connection established")
    except Exception as e:
        logger.warning(f"Error configuring connection: {e}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Dependency to get a database session.
    Ensures the session is always closed, even in case of error.
    Commits must be managed explicitly in endpoints/CRUD.
    """
    from fastapi import HTTPException, status
    from sqlalchemy.exc import OperationalError, SQLAlchemyError
    
    db = SessionLocal()
    try:
        yield db
    except HTTPException:
        # Do not log HTTP errors (401, 403, etc.) as database errors
        # Propagate them as is
        raise
    except OperationalError as e:
        # Network/DNS connection error - log with more details
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"Database connection error: {error_msg}")
        logger.error("Please check your internet connection and DATABASE_URL configuration")
        logger.error(f"Full error details: {e}", exc_info=True)
        db.rollback()
        # Convert to HTTP exception for better error handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection error. Please try again later or contact support if the problem persists.",
        )
    except SQLAlchemyError as e:
        # Other database errors
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"Database error: {error_msg}")
        logger.error(f"Full error details: {e}", exc_info=True)
        db.rollback()
        # Convert to HTTP exception for better error handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error occurred. Please try again later or contact support if the problem persists.",
        )
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error in database session: {e}", exc_info=True)
        db.rollback()
        # Re-raise to let FastAPI handle it
        raise
    finally:
        # Always close the session to release the connection from the pool
        # This is crucial to avoid connection pool exhaustion
        try:
            db.close()
        except Exception as close_error:
            logger.error(f"Error closing session: {close_error}", exc_info=True) 
