"""
Endpoints pour gérer les migrations de saisons
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.services.season_migration import season_migration_service
from app.tasks.season_migration import (
    process_season_migrations,
    migrate_contest_to_city,
    promote_contest_level
)
from app.models.user import User

router = APIRouter()


@router.post("/migrate/check")
def check_and_process_migrations(
    async_task: bool = False,
    current_user: User = Depends(deps.get_current_admin_user)
):
    """
    Vérifie et traite toutes les migrations nécessaires.
    Nécessite les privilèges administrateur.
    
    Args:
        async_task: Si True, exécute la tâche de manière asynchrone via Celery
    """
    try:
        if async_task:
            # Exécuter via Celery
            task = process_season_migrations.delay()
            return {
                "message": "Migration task started",
                "task_id": task.id,
                "status": "pending"
            }
        else:
            # Exécuter de manière synchrone
            from app.db.session import SessionLocal
            db = SessionLocal()
            try:
                result = season_migration_service.check_and_process_migrations(db)
                return result
            finally:
                db.close()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing migrations: {str(e)}"
        )


@router.post("/migrate/contest/{contest_id}/to-city")
def migrate_contest_to_city_endpoint(
    contest_id: int,
    async_task: bool = False,
    current_user: User = Depends(deps.get_current_admin_user)
):
    """
    Migre manuellement un contest vers la saison CITY.
    Nécessite les privilèges administrateur.
    
    Args:
        contest_id: ID du contest à migrer
        async_task: Si True, exécute la tâche de manière asynchrone via Celery
    """
    try:
        if async_task:
            # Exécuter via Celery
            task = migrate_contest_to_city.delay(contest_id)
            return {
                "message": "Migration task started",
                "task_id": task.id,
                "status": "pending"
            }
        else:
            # Exécuter de manière synchrone
            from app.db.session import SessionLocal
            db = SessionLocal()
            try:
                result = season_migration_service.migrate_to_city_season(db, contest_id)
                if "error" in result:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=result["error"]
                    )
                return result
            finally:
                db.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error migrating contest: {str(e)}"
        )


@router.post("/migrate/contest/{contest_id}/promote/{from_level}/{to_level}")
def promote_contest_level_endpoint(
    contest_id: int,
    from_level: str,
    to_level: str,
    async_task: bool = False,
    current_user: User = Depends(deps.get_current_admin_user)
):
    """
    Promouvoit manuellement un contest d'un niveau à un autre.
    Nécessite les privilèges administrateur.
    
    Niveaux possibles: city, country, regional, continent, global
    
    Args:
        contest_id: ID du contest
        from_level: Niveau source
        to_level: Niveau destination
        async_task: Si True, exécute la tâche de manière asynchrone via Celery
    """
    from app.models.contests import SeasonLevel
    
    level_map = {
        "city": SeasonLevel.CITY,
        "country": SeasonLevel.COUNTRY,
        "regional": SeasonLevel.REGIONAL,
        "continent": SeasonLevel.CONTINENT,
        "global": SeasonLevel.GLOBAL
    }
    
    if from_level.lower() not in level_map or to_level.lower() not in level_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid level. Must be one of: city, country, regional, continent, global"
        )
    
    try:
        if async_task:
            # Exécuter via Celery
            task = promote_contest_level.delay(contest_id, from_level, to_level)
            return {
                "message": "Promotion task started",
                "task_id": task.id,
                "status": "pending"
            }
        else:
            # Exécuter de manière synchrone
            from app.db.session import SessionLocal
            db = SessionLocal()
            try:
                result = season_migration_service.promote_to_next_level(
                    db,
                    level_map[from_level.lower()],
                    level_map[to_level.lower()],
                    contest_id
                )
                if "error" in result:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=result["error"]
                    )
                return result
            finally:
                db.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error promoting contest: {str(e)}"
        )

