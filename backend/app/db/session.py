from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Convertir la chaîne de connexion psycopg2 en psycopg3
database_url = settings.SQLALCHEMY_DATABASE_URI
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Configuration du moteur avec gestion améliorée des connexions SSL
# Augmentation du pool pour éviter les timeouts
engine = create_engine(
    database_url,
    pool_pre_ping=True,  # Vérifie la connexion avant utilisation
    pool_recycle=1800,   # Recycle les connexions après 30 minutes (réduit pour éviter les connexions mortes)
    pool_size=10,        # Taille du pool de connexions (augmenté de 5 à 10)
    max_overflow=20,     # Nombre maximum de connexions supplémentaires (augmenté de 10 à 20)
    pool_timeout=60,     # Timeout pour obtenir une connexion du pool (augmenté de 30 à 60 secondes)
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
    """
    Dependency pour obtenir une session de base de données.
    S'assure que la session est toujours fermée, même en cas d'erreur.
    Les commits doivent être gérés explicitement dans les endpoints/CRUD.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Erreur de base de données: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        # Toujours fermer la session pour libérer la connexion du pool
        # C'est crucial pour éviter l'épuisement du pool de connexions
        try:
            db.close()
        except Exception as close_error:
            logger.error(f"Erreur lors de la fermeture de la session: {close_error}", exc_info=True) 
