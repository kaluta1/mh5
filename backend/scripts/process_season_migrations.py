#!/usr/bin/env python3
"""
Script pour traiter les migrations de saisons.
Ce script peut être exécuté par un scheduler (cron, Celery, etc.) pour vérifier
et traiter automatiquement les migrations de saisons.
"""
import sys
import os

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.services.season_migration import season_migration_service
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Fonction principale pour traiter les migrations"""
    db: Session = SessionLocal()
    try:
        logger.info("Début du traitement des migrations de saisons...")
        result = season_migration_service.check_and_process_migrations(db)
        
        logger.info(f"Traitement terminé. {result['processed']} action(s) effectuée(s).")
        
        if result['results']:
            for item in result['results']:
                logger.info(f"Contest {item['contest_id']}: {item['action']} - {item['result']}")
        
        return result
    except Exception as e:
        logger.error(f"Erreur lors du traitement des migrations: {str(e)}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

