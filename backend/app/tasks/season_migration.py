"""
Tâches Celery pour les migrations de saisons
"""
import logging
from celery import Task
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.season_migration import season_migration_service

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """
    Classe de base pour les tâches qui nécessitent une session de base de données.
    Gère automatiquement la création et la fermeture de la session.
    """
    def __init__(self):
        super().__init__()
        self._db = None

    def __call__(self, *args, **kwargs):
        """Créer une session avant l'exécution de la tâche"""
        self._db = SessionLocal()
        try:
            return super().__call__(*args, **kwargs)
        finally:
            if self._db:
                self._db.close()
                self._db = None

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Fermer la session en cas d'erreur"""
        if self._db:
            try:
                self._db.rollback()
            except:
                pass
            finally:
                self._db.close()
                self._db = None
        logger.error(f"Task {task_id} failed: {exc}", exc_info=einfo)

    @property
    def db(self) -> Session:
        """Récupérer la session de base de données"""
        if self._db is None:
            self._db = SessionLocal()
        return self._db


@celery_app.task(
    base=DatabaseTask,
    name="app.tasks.season_migration.process_season_migrations",
    bind=True,
    max_retries=3,
    default_retry_delay=300  # 5 minutes entre les tentatives
)
def process_season_migrations(self):
    """
    Tâche Celery pour traiter les migrations de saisons.
    Cette tâche est exécutée automatiquement toutes les heures via Celery Beat.
    """
    try:
        logger.info("Début du traitement des migrations de saisons (Celery task)...")
        
        # Récupérer la session de base de données depuis la classe de base
        db: Session = self.db
        
        try:
            result = season_migration_service.check_and_process_migrations(db)
            db.commit()
            
            logger.info(f"Traitement terminé. {result['processed']} action(s) effectuée(s).")
            
            if result['results']:
                for item in result['results']:
                    logger.info(
                        f"Contest {item['contest_id']}: {item['action']} - {item['result']}"
                    )
            
            return {
                "status": "success",
                "processed": result['processed'],
                "results": result['results']
            }
        except Exception as e:
            db.rollback()
            raise e
        
    except Exception as exc:
        logger.error(
            f"Erreur lors du traitement des migrations: {str(exc)}",
            exc_info=True
        )
        # Retry la tâche en cas d'erreur
        raise self.retry(exc=exc)


@celery_app.task(
    base=DatabaseTask,
    name="app.tasks.season_migration.migrate_contest_to_city",
    bind=True,
    max_retries=3,
    default_retry_delay=300
)
def migrate_contest_to_city(self, contest_id: int):
    """
    Tâche Celery pour migrer un contest spécifique vers la saison CITY.
    
    Args:
        contest_id: ID du contest à migrer
    """
    try:
        logger.info(f"Début de la migration du contest {contest_id} vers CITY...")
        
        db: Session = self.db
        try:
            result = season_migration_service.migrate_to_city_season(db, contest_id)
            db.commit()
            
            if "error" in result:
                logger.error(f"Erreur lors de la migration: {result['error']}")
                return {
                    "status": "error",
                    "error": result["error"]
                }
            
            logger.info(f"Migration réussie: {result['message']}")
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            db.rollback()
            raise e
        
    except Exception as exc:
        logger.error(
            f"Erreur lors de la migration du contest {contest_id}: {str(exc)}",
            exc_info=True
        )
        raise self.retry(exc=exc)


@celery_app.task(
    base=DatabaseTask,
    name="app.tasks.season_migration.promote_contest_level",
    bind=True,
    max_retries=3,
    default_retry_delay=300
)
def promote_contest_level(self, contest_id: int, from_level: str, to_level: str):
    """
    Tâche Celery pour promouvoir un contest d'un niveau à un autre.
    
    Args:
        contest_id: ID du contest
        from_level: Niveau source (city, country, regional, continent, global)
        to_level: Niveau destination (city, country, regional, continent, global)
    """
    try:
        from app.models.contests import SeasonLevel
        
        level_map = {
            "city": SeasonLevel.CITY,
            "country": SeasonLevel.COUNTRY,
            "regional": SeasonLevel.REGIONAL,
            "continent": SeasonLevel.CONTINENT,
            "global": SeasonLevel.GLOBAL
        }
        
        if from_level.lower() not in level_map or to_level.lower() not in level_map:
            return {
                "status": "error",
                "error": "Invalid level. Must be one of: city, country, regional, continent, global"
            }
        
        logger.info(
            f"Début de la promotion du contest {contest_id} de {from_level} à {to_level}..."
        )
        
        db: Session = self.db
        try:
            result = season_migration_service.promote_to_next_level(
                db,
                level_map[from_level.lower()],
                level_map[to_level.lower()],
                contest_id
            )
            db.commit()
            
            if "error" in result:
                logger.error(f"Erreur lors de la promotion: {result['error']}")
                return {
                    "status": "error",
                    "error": result["error"]
                }
            
            logger.info(f"Promotion réussie: {result['message']}")
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            db.rollback()
            raise e
        
    except Exception as exc:
        logger.error(
            f"Erreur lors de la promotion du contest {contest_id}: {str(exc)}",
            exc_info=True
        )
        raise self.retry(exc=exc)

