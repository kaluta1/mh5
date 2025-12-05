"""
Configuration Celery pour les tâches asynchrones
"""
from celery import Celery
from app.core.config import settings

# Construire l'URL Redis
def get_redis_url():
    """Construire l'URL Redis depuis les paramètres"""
    redis_host = getattr(settings, 'REDIS_HOST', 'localhost')
    redis_port = getattr(settings, 'REDIS_PORT', 6379)
    redis_url = getattr(settings, 'REDIS_URL', None)
    
    if redis_url:
        return redis_url
    return f"redis://{redis_host}:{redis_port}/0"

# Créer l'instance Celery
celery_app = Celery(
    "myfav",
    broker=get_redis_url(),
    backend=get_redis_url(),
    include=["app.tasks.season_migration", "app.tasks.contest_status"]
)

# Configuration Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

# Configuration des tâches périodiques (beat schedule)
celery_app.conf.beat_schedule = {
    "process-season-migrations": {
        "task": "app.tasks.season_migration.process_season_migrations",
        "schedule": 3600.0,  # Exécuter toutes les heures (3600 secondes)
    },
    "update-contest-statuses": {
        "task": "app.tasks.contest_status.update_contest_statuses",
        "schedule": 3600.0,  # Exécuter toutes les heures (3600 secondes)
    },
}

