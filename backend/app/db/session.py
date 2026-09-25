from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

# Use psycopg2-binary (already in requirements.txt)
# Do not convert to psycopg3 as psycopg2-binary is installed
database_url = settings.SQLALCHEMY_DATABASE_URI
# Keep postgresql:// for psycopg2-binary (no need to change)

# PostgreSQL pool tuning is not accepted by SQLite's default pool. Keeping the
# options dialect-specific lets the application import cleanly in tests and in
# local SQLite utilities without weakening the Neon production configuration.
engine_options = {
    "pool_pre_ping": True,
    "echo": False,
}
statement_timeout_ms = 20000
if database_url.lower().startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    # No statement_timeout previously meant a runaway/unindexed query could
    # hold a pooled connection indefinitely, contributing to pool exhaustion
    # and 504s under load. Bounded, admin-configurable via env var.
    statement_timeout_ms = max(
        1000, min(int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "20000")), 120000)
    )
    engine_options.update(
        {
            "pool_recycle": 300,  # Neon timeout is approximately 10 minutes.
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 10,
            "connect_args": {
                "connect_timeout": 10,
            },
        }
    )

engine = create_engine(database_url, **engine_options)

# Event handler for connection errors
@event.listens_for(engine, "connect")
def set_ssl_mode(dbapi_conn, connection_record):
    """Configure SSL mode for PostgreSQL connections (Neon)"""
    try:
        # Neon PostgreSQL requires SSL
        # SSL configuration is managed via connection URL (sslmode=require)
        if hasattr(dbapi_conn, 'info'):
            logger.debug("Database connection established")
            # Neon pooled endpoints can reject libpq startup `options`. Apply
            # the bounded statement timeout after connecting, then close the
            # setup transaction before the connection enters the pool.
            cursor = dbapi_conn.cursor()
            try:
                cursor.execute(f"SET statement_timeout = {statement_timeout_ms}")
                dbapi_conn.commit()
            finally:
                cursor.close()
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
    from fastapi.exceptions import RequestValidationError
    from sqlalchemy.exc import OperationalError, SQLAlchemyError

    from app.core.redaction import describe_exception, safe_traceback

    # Privacy: exception messages are never logged here. SQLAlchemy/driver
    # messages embed bound parameters and row values, and validation errors embed
    # the submitted body (passwords, tokens); see app.core.redaction.
    db = SessionLocal()
    try:
        yield db
    except HTTPException:
        # Do not log HTTP errors (401, 403, etc.) as database errors
        # Propagate them as is
        raise
    except RequestValidationError as e:
        # A client input error (answered 422 by the validation handler), not a
        # database error.
        logger.debug("Request validation failed: %s", describe_exception(e))
        db.rollback()
        raise
    except OperationalError as e:
        # Network/DNS connection error
        logger.error("Database connection error: %s", describe_exception(e))
        logger.error("Please check your internet connection and DATABASE_URL configuration")
        logger.error("%s", safe_traceback(e))
        db.rollback()
        # Convert to HTTP exception for better error handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection error. Please try again later or contact support if the problem persists.",
        )
    except SQLAlchemyError as e:
        # Other database errors
        error_msg = describe_exception(e)
        logger.error("Database error: %s", error_msg)
        logger.error("%s", safe_traceback(e))
        db.rollback()
        
        # FIXED: Return more specific error message in development/debug mode
        import os
        debug_mode = os.getenv("DEBUG", "false").lower() == "true"
        
        detail_msg = "Database error occurred. Please try again later or contact support if the problem persists."
        if debug_mode:
            # Include actual error in debug mode
            detail_msg = f"Database error: {error_msg}"
        
        # Convert to HTTP exception for better error handling
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail_msg,
        )
    except Exception as e:
        # Log unexpected errors
        logger.error("Unexpected error in database session: %s\n%s", describe_exception(e), safe_traceback(e))
        db.rollback()
        # Re-raise to let FastAPI handle it
        raise
    finally:
        # Always close the session to release the connection from the pool
        # This is crucial to avoid connection pool exhaustion
        try:
            db.close()
        except Exception as close_error:
            logger.error("Error closing session: %s", describe_exception(close_error))
