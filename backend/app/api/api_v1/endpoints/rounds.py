from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import date, datetime
import logging
import traceback
import os

from app import crud, models
from app.schemas import round as round_schema
from app.api import deps
from app.models.round import Round
from app.scripts.generate_monthly_rounds import generate_monthly_round

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[round_schema.RoundWithStats])
def read_rounds(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    contest_id: Optional[int] = Query(None, description="ID du contest pour récupérer ses rounds"),
    round_id: Optional[int] = Query(None, alias="roundId", description="ID du round spécifique"),
    current_user: Optional[models.User] = Depends(deps.get_current_active_user_optional),
    has_voting_type: Optional[bool] = Query(None, alias="hasVotingType", description="Filtrer les contests par présence de type de vote"),
    filter_country: Optional[str] = Query(None, alias="filterCountry", description="Filtrer les participants par pays"),
    filter_continent: Optional[str] = Query(None, alias="filterContinent", description="Filtrer les participants par continent"),
    contest_limit: int = Query(12, alias="contestLimit", description="Nombre maximum de contests par round"),
    contest_skip: int = Query(0, alias="contestSkip", description="Nombre de contests à sauter pour la pagination"),
    search_term: Optional[str] = Query(None, alias="searchTerm", description="Rechercher dans les noms et descriptions de contests"),
) -> Any:
    """
    Récupère les rounds (optionnellement filtrés par contest) avec leurs statistiques.
    Inclut le nombre de participants et si l'utilisateur actuel a participé.
    """
    try:
        user_id = current_user.id if current_user else None
        
        # Simple query - fetch rounds without complex joins first
        try:
            query = db.query(Round).filter(Round.status != "cancelled")
            if round_id:
                query = query.filter(Round.id == round_id)
            if contest_id:
                # For contest_id, use the CRUD method
                rounds_data = crud.round.get_rounds_with_stats(db=db, contest_id=contest_id, user_id=user_id)
                # Convert to RoundWithStats format
                result = []
                for r_data in rounds_data:
                    round_obj = _enrich_round_data(db, r_data, user_id, has_voting_type, filter_country, 
                                                  filter_continent, search_term, contest_limit, contest_skip)
                    if round_obj:
                        result.append(round_obj)
                return result
            else:
                # Fetch all rounds
                try:
                    db_rounds = query.order_by(Round.id.desc()).offset(skip).limit(limit).all()
                except Exception as order_error:
                    logger.warning(f"Error ordering rounds: {str(order_error)}")
                    db_rounds = query.offset(skip).limit(limit).all()
                
                if not db_rounds:
                    return []
                
                # Convert ORM objects to dict format
                result = []
                for r in db_rounds:
                    try:
                        r_data = {
                            "id": r.id,
                            "contest_id": getattr(r, 'contest_id', None),
                            "name": r.name or f"Round {r.id}",
                            "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                            "is_submission_open": getattr(r, 'is_submission_open', True),
                            "is_voting_open": getattr(r, 'is_voting_open', False),
                            "current_season_level": getattr(r, 'current_season_level', None),
                            "submission_start_date": getattr(r, 'submission_start_date', None),
                            "submission_end_date": getattr(r, 'submission_end_date', None),
                            "voting_start_date": getattr(r, 'voting_start_date', None),
                            "voting_end_date": getattr(r, 'voting_end_date', None),
                            "created_at": getattr(r, 'created_at', datetime.now()),
                            "updated_at": getattr(r, 'updated_at', datetime.now()),
                        }
                        round_obj = _enrich_round_data(db, r_data, user_id, has_voting_type, filter_country,
                                                      filter_continent, search_term, contest_limit, contest_skip)
                        if round_obj:
                            result.append(round_obj)
                    except Exception as round_error:
                        logger.error(f"Error processing round {r.id}: {str(round_error)}", exc_info=True)
                        continue
                
                return result
                
        except Exception as query_error:
            logger.error(f"Database query error: {str(query_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(query_error)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Error in read_rounds endpoint: {str(e)}", exc_info=True)
        logger.error(f"Full traceback: {error_traceback}")
        
        # Return detailed error in response for debugging
        error_detail = str(e)
        if os.getenv("DEBUG") == "true" or os.getenv("ENVIRONMENT") != "production":
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching rounds: {error_detail}\n\nTraceback:\n{error_traceback}"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching rounds: {error_detail}. Check server logs for details."
            )


def _enrich_round_data(
    db: Session,
    r_data: dict,
    user_id: Optional[int],
    has_voting_type: Optional[bool],
    filter_country: Optional[str],
    filter_continent: Optional[str],
    search_term: Optional[str],
    contest_limit: int,
    contest_skip: int
) -> Optional[dict]:
    """Enrich round data with contests and statistics"""
    try:
        round_id = r_data.get("id")
        if not round_id:
            return None
        
        # Get participants count
        try:
            participants_count = crud.round.count_participants_for_round(db, round_id)
        except Exception as e:
            logger.warning(f"Error counting participants for round {round_id}: {str(e)}")
            participants_count = 0
        
        # Check if user participated
        try:
            current_user_participated = crud.round.user_participated_in_round(db, round_id, user_id) if user_id else False
        except Exception as e:
            logger.warning(f"Error checking user participation for round {round_id}: {str(e)}")
            current_user_participated = False
        
        # Check if completed
        try:
            round_obj = db.query(Round).filter(Round.id == round_id).first()
            is_completed = crud.round.is_round_completed(round_obj) if round_obj else False
        except Exception as e:
            logger.warning(f"Error checking if round {round_id} is completed: {str(e)}")
            is_completed = False
        
        # Get contests for this round
        contests = []
        contests_count = 0
        try:
            from app.models.contest import Contest as ContestModel
            from app.models.round import round_contests
            
            # Try to get contests via round_contests table
            try:
                linked_contests = db.query(ContestModel).join(
                    round_contests, ContestModel.id == round_contests.c.contest_id
                ).filter(round_contests.c.round_id == round_id).all()
                
                if linked_contests:
                    contests = linked_contests
            except Exception as e:
                logger.warning(f"Error fetching contests via round_contests for round {round_id}: {str(e)}")
                # Fallback: try legacy contest_id
                contest_id = r_data.get("contest_id")
                if contest_id:
                    contest = crud.contest.get(db, id=contest_id)
                    if contest:
                        contests = [contest]
            
            # Filter contests
            valid_contests = []
            for c in contests:
                # Filter by voting_type
                if has_voting_type is not None:
                    if has_voting_type and getattr(c, 'voting_type_id', None) is None:
                        continue
                    if not has_voting_type and getattr(c, 'voting_type_id', None) is not None:
                        continue
                
                # Filter by search term
                if search_term:
                    search_lower = search_term.lower().strip()
                    contest_name = (c.name or "").lower()
                    contest_description = (getattr(c, 'description', None) or "").lower()
                    if search_lower not in contest_name and search_lower not in contest_description:
                        continue
                
                valid_contests.append(c)
            
            contests_count = len(valid_contests)
            
            # Apply pagination
            paginated_contests = valid_contests[contest_skip:contest_skip + contest_limit]
            
            # Batch query: find all contests where current user has participated in this round
            # Also check if user has nominated in any voting_type (category) to show Edit for all contests in that category
            user_contested_contest_ids: set = set()
            user_nominated_voting_type_ids: set = set()
            if user_id:
                try:
                    from app.models.contests import Contestant
                    from app.models.contest import Contest as ContestModel
                    from app.models.round import round_contests
                    
                    # Get ALL user contestants across ALL rounds (not just this round)
                    # This allows checking if user has nominated in any category
                    all_user_contestants = db.query(Contestant).filter(
                        Contestant.user_id == user_id,
                        Contestant.is_deleted == False
                    ).all()
                    
                    # Build set of voting_type_ids where user has nominated (across ALL rounds)
                    for uc in all_user_contestants:
                        if uc.round_id:
                            try:
                                # Get contests linked to this round
                                linked_contests = db.query(ContestModel).join(
                                    round_contests, ContestModel.id == round_contests.c.contest_id
                                ).filter(round_contests.c.round_id == uc.round_id).all()
                                for contest in linked_contests:
                                    if contest.voting_type_id:
                                        user_nominated_voting_type_ids.add(contest.voting_type_id)
                            except Exception as e:
                                logger.warning(f"Error fetching contests via round_contests for round {uc.round_id}: {str(e)}")
                        
                        # Also check via season_id (legacy - season_id can be contest_id)
                        if uc.season_id:
                            try:
                                contest = db.query(ContestModel).filter(ContestModel.id == uc.season_id).first()
                                if contest and contest.voting_type_id:
                                    user_nominated_voting_type_ids.add(contest.voting_type_id)
                            except Exception as e:
                                logger.warning(f"Error fetching contest {uc.season_id} for voting_type check: {str(e)}")
                    
                    # Now check for this specific round
                    if valid_contests:
                        all_contest_ids = [c.id for c in valid_contests]
                        # Get user contestants for THIS round only
                        user_contestants = [uc for uc in all_user_contestants if uc.round_id == round_id]
                        # Build set of contest IDs where user has directly participated in this round
                        user_contested_contest_ids = {uc.season_id for uc in user_contestants if uc.season_id}
                except Exception as e:
                    logger.warning(f"Error batch-checking user participation for round {round_id}: {str(e)}")

            # Build contest data
            for contest in paginated_contests:
                try:
                    # Get participant count for this contest in this round
                    participant_count = 0
                    try:
                        from app.models.contests import Contestant
                        participant_count = db.query(func.count(Contestant.id)).filter(
                            Contestant.season_id == contest.id,
                            Contestant.round_id == round_id,
                            Contestant.is_deleted == False
                        ).scalar() or 0
                        
                        # Apply location filters
                        if filter_country and filter_country != 'all':
                            participant_count = db.query(func.count(Contestant.id)).filter(
                                Contestant.season_id == contest.id,
                                Contestant.round_id == round_id,
                                Contestant.is_deleted == False,
                                func.lower(Contestant.country) == func.lower(filter_country)
                            ).scalar() or 0
                        
                        if filter_continent and filter_continent != 'all':
                            participant_count = db.query(func.count(Contestant.id)).filter(
                                Contestant.season_id == contest.id,
                                Contestant.round_id == round_id,
                                Contestant.is_deleted == False,
                                func.lower(Contestant.continent) == func.lower(filter_continent)
                            ).scalar() or 0
                    except Exception as e:
                        logger.warning(f"Error counting participants for contest {contest.id}: {str(e)}")
                    
                    # Check if user has nominated in this voting_type (category)
                    # If yes, show "Edit" for ALL contests with this voting_type_id
                    is_contesting = contest.id in user_contested_contest_ids
                    if not is_contesting and contest.voting_type_id and contest.voting_type_id in user_nominated_voting_type_ids:
                        is_contesting = True
                    
                    contest_data = {
                        "id": contest.id,
                        "name": contest.name,
                        "description": getattr(contest, 'description', None),
                        "contest_type": getattr(contest, 'contest_type', None),
                        "cover_image_url": getattr(contest, 'cover_image_url', None),
                        "level": getattr(contest, 'level', None),
                        "participants_count": participant_count,
                        "votes_count": 0,
                        "image_url": getattr(contest, 'image_url', None),
                        "created_at": getattr(contest, 'created_at', None),
                        "updated_at": getattr(contest, 'updated_at', None),
                        "voting_type_id": getattr(contest, 'voting_type_id', None),
                        "current_user_contesting": is_contesting
                    }
                    r_data.setdefault("contests", []).append(contest_data)
                except Exception as e:
                    logger.warning(f"Error processing contest {contest.id}: {str(e)}")
                    continue
            
            # Sort contests by participants_count (descending - highest first)
            if "contests" in r_data:
                r_data["contests"].sort(key=lambda x: x.get("participants_count", 0), reverse=True)
        
        except Exception as e:
            logger.warning(f"Error enriching contests for round {round_id}: {str(e)}")
            r_data["contests"] = []
            contests_count = 0
        
        # Build final response
        result = {
            **r_data,
            "participants_count": participants_count,
            "contests_count": contests_count,
            "votes_count": 0,
            "current_user_participated": current_user_participated,
            "is_completed": is_completed,
            "top_contestants": [],  # Can be enhanced later
            "contests": r_data.get("contests", [])
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in _enrich_round_data: {str(e)}", exc_info=True)
        return None


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
        raise
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Error in ensure_january_round endpoint: {str(e)}", exc_info=True)
        logger.error(f"Full traceback: {error_traceback}")
        
        error_detail = str(e)
        if "Failed to ensure" in error_detail:
            error_detail = error_detail.split(": ", 1)[-1] if ": " in error_detail else error_detail
        
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
