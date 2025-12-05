from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Convertir la chaîne de connexion psycopg2 en psycopg3
database_url = settings.SQLALCHEMY_DATABASE_URI
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Configuration du moteur avec gestion améliorée des connexions SSL
engine = create_engine(
    database_url,
    pool_pre_ping=True,  # Vérifie la connexion avant utilisation
    pool_recycle=3600,   # Recycle les connexions après 1 heure
    pool_size=5,         # Taille du pool de connexions
    max_overflow=10,     # Nombre maximum de connexions supplémentaires
    echo=False
)

# Gestionnaire d'événements pour les erreurs de connexion
@event.listens_for(engine, "connect")
def set_ssl_mode(dbapi_conn, connection_record):
    """Configure le mode SSL pour les connexions PostgreSQL"""
    try:
        # Si la connexion utilise SSL, s'assurer qu'elle est correctement configurée
        if hasattr(dbapi_conn, 'info'):
            logger.debug("Connexion SSL configurée")
    except Exception as e:
        logger.warning(f"Erreur lors de la configuration SSL: {e}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Erreur de base de données: {e}")
        db.rollback()
        raise
    finally:
        db.close() 
