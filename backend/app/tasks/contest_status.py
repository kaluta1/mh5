"""
Tâches Celery pour la mise à jour des statuts des contests
"""
import logging
from celery import Task
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.services.contest_status import contest_status_service

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
    name="app.tasks.contest_status.update_contest_statuses",
    bind=True,
    max_retries=3,
    default_retry_delay=300
)
def update_contest_statuses(self):
    """
    Tâche Celery pour mettre à jour les statuts des contests.
    Cette tâche est exécutée automatiquement toutes les heures via Celery Beat.
    """
    try:
        logger.info("Début de la mise à jour des statuts des contests (Celery task)...")
        
        db: Session = self.db
        
        try:
            result = contest_status_service.update_contest_statuses(db)
            db.commit()
            
            logger.info(f"Mise à jour terminée. {result['updated_count']} contest(s) mis à jour.")
            
            if result['results']:
                for item in result['results']:
                    logger.info(
                        f"Contest {item['contest_id']} ({item['contest_name']}): "
                        f"submission_open: {item['old_submission_open']} -> {item['new_submission_open']}, "
                        f"voting_open: {item['old_voting_open']} -> {item['new_voting_open']}"
                    )
            
            return {
                "status": "success",
                "updated_count": result['updated_count'],
                "results": result['results']
            }
        except Exception as e:
            db.rollback()
            raise e
        
    except Exception as exc:
        logger.error(
            f"Erreur lors de la mise à jour des statuts: {str(exc)}",
            exc_info=True
        )
        raise self.retry(exc=exc)

