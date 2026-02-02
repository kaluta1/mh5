from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date

from app import crud, models
from app.schemas import round as round_schema
from app.api import deps
from app.models.round import Round
from app.scripts.generate_monthly_rounds import generate_monthly_round

router = APIRouter()

@router.get("/", response_model=List[round_schema.RoundWithStats])
def read_rounds(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    contest_id: Optional[int] = Query(None, description="ID du contest pour récupérer ses rounds"),
    current_user: Optional[models.User] = Depends(deps.get_current_active_user_optional),
) -> Any:
    """
    Récupère les rounds (optionnellement filtrés par contest) avec leurs statistiques.
    Inclut le nombre de participants et si l'utilisateur actuel a participé.
    """
    user_id = current_user.id if current_user else None
    
    if contest_id:
        rounds_with_stats = crud.round.get_rounds_with_stats(
            db=db, contest_id=contest_id, user_id=user_id
        )
    else:
        # Fallback: get all active rounds or recent ones if no contest specified
        # For now, let's use a new CRUD method or just get all rounds
        rounds_with_stats = []
        # TODO: Implement get_all_rounds_with_stats if needed
        # For now, return empty or implement simple fetch
        pass 
       
    # If no contest_id provided, we might want to return all rounds or filter differently.
    # Given the previous error, the client might be calling this without contest_id.
    # Let's support fetching all rounds if contest_id is missing.
    if not contest_id:
        db_rounds = db.query(Round).filter(Round.status != "cancelled").order_by(Round.submission_start_date.desc()).offset(skip).limit(limit).all()
        rounds_with_stats = []
        for r in db_rounds:
             # Calculate stats manually here re-using logic or refactor CRUD
             # For brevity/safety, let's reuse the logic from get_rounds_with_stats but per round
             participants_count = crud.round.count_participants_for_round(db, r.id)
             current_user_participated = False
             if user_id:
                 current_user_participated = crud.round.user_participated_in_round(db, r.id, user_id)
             
             current_season_level = crud.round.calculate_current_season_level(r)
             is_completed = crud.round.is_round_completed(r)
             
             rounds_with_stats.append({
                "id": r.id,
                "contest_id": r.contest_id,
                "name": r.name,
                "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                "is_submission_open": r.is_submission_open,
                "is_voting_open": r.is_voting_open,
                "current_season_level": current_season_level or r.current_season_level,
                "submission_start_date": r.submission_start_date,
                "submission_end_date": r.submission_end_date,
                "voting_start_date": r.voting_start_date,
                "voting_end_date": r.voting_end_date,
                "city_season_start_date": r.city_season_start_date,
                "city_season_end_date": r.city_season_end_date,
                "country_season_start_date": r.country_season_start_date,
                "country_season_end_date": r.country_season_end_date,
                "regional_start_date": r.regional_start_date,
                "regional_end_date": r.regional_end_date,
                "continental_start_date": r.continental_start_date,
                "continental_end_date": r.continental_end_date,
                "global_start_date": r.global_start_date,
                "global_end_date": r.global_end_date,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "participants_count": participants_count,
                "current_user_participated": current_user_participated,
                "is_completed": is_completed,
            })
            
    return rounds_with_stats[skip:skip+limit] if contest_id else rounds_with_stats # slicing managed above for no-contest case? No, slicing on list.


@router.post("/ensure-january", response_model=round_schema.Round)
def ensure_january_round(
    *,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Ensure January round exists for current year and links all active contests.
    Public endpoint - can be called without authentication for initial setup.
    """
    from app.services.monthly_round_scheduler import monthly_round_scheduler
    
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting ensure_january_round_exists...")
        round_obj = monthly_round_scheduler.ensure_january_round_exists()
        if round_obj:
            logger.info(f"Successfully retrieved/created January round (id={round_obj.id})")
            return round_obj
        else:
            logger.error("ensure_january_round_exists returned None")
            raise HTTPException(
                status_code=500,
                detail="Failed to create or retrieve January round (returned None)"
            )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error in ensure_january_round endpoint: {str(e)}", exc_info=True)
        logger.error(f"Full traceback: {error_traceback}")
        
        # Return more detailed error message
        error_detail = str(e)
        if "Failed to ensure" in error_detail:
            # Extract the underlying error
            error_detail = error_detail.split(": ", 1)[-1] if ": " in error_detail else error_detail
        
        # Include more context in debug mode
        import os
        if os.getenv("DEBUG") == "true":
            raise HTTPException(
                status_code=500,
                detail=f"Error ensuring January round: {error_detail}\n\nTraceback:\n{error_traceback}"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Error ensuring January round: {error_detail}. Check server logs for details."
            )


@router.post("/generate-monthly", response_model=round_schema.Round)
def generate_monthly(
    *,
    db: Session = Depends(deps.get_db),
    year: Optional[int] = Query(None, description="Année cible (défaut: année courante)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Mois cible (défaut: mois courant)"),
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Génère un round mensuel pour tous les contests actifs.
    Admin uniquement.
    """
    try:
        if year and month:
            target_date = date(year, month, 1)
        else:
            target_date = date.today()
        
        new_round = generate_monthly_round(db=db, target_date=target_date)
        return new_round
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération: {str(e)}")


@router.post("/", response_model=round_schema.Round)
def create_round(
    *,
    db: Session = Depends(deps.get_db),
    round_in: round_schema.RoundCreate,
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Create new round.
    """
    round = crud.round.create_with_contest(db=db, obj_in=round_in)
    return round

@router.put("/{id}", response_model=round_schema.Round)
def update_round(
    *,
    db: Session = Depends(deps.get_db),
    id: int,
    round_in: round_schema.RoundUpdate,
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Update a round.
    """
    round = crud.round.get(db=db, id=id)
    if not round:
        raise HTTPException(status_code=404, detail="Round not found")
    round = crud.round.update(db=db, db_obj=round, obj_in=round_in)
    return round

@router.delete("/{id}", response_model=round_schema.Round)
def delete_round(
    *,
    db: Session = Depends(deps.get_db),
    id: int,
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Delete a round.
    """
    round = crud.round.get(db=db, id=id)
    if not round:
        raise HTTPException(status_code=404, detail="Round not found")
        
    # CRUDRound needs remove method? For now manually delete
    db.delete(round)
    db.commit()
    return round

