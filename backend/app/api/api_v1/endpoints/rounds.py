from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
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
        # Load contests with their category relationship for efficient search
        from app.models.contest import Contest
        query = db.query(Round).options(
            joinedload(Round.contests).joinedload(Contest.category)
        ).filter(Round.status != "cancelled")
        if round_id:
            query = query.filter(Round.id == round_id)
        db_rounds = query.order_by(Round.submission_start_date.desc()).offset(skip).limit(limit).all()
        rounds_with_stats = []
    
    
    # Enrich rounds with requested data
    enriched_rounds = []
    
    # Import here to avoid circular dependencies
    from app.schemas.contest import Contest, TopContestantPreview
    
    # Import methods for enrichment
    # We would ideally put this in CRUD or Service layer
    
    # Prepare list for later use
    if not contest_id:
         # Need to iterate over what we fetched from DB
         rounds_iterable = db_rounds
    else:
         # If contest_id, we used CRUD which returned schemas, not ORM objects
         # We need to re-fetch ORM or be careful.
         # Actually crud.round.get_rounds_with_stats returns dicts/Pydantic models
         rounds_iterable = rounds_with_stats

    # Since we are modifying the response structure significantly and mixing ORM/dicts
    # It is safer to rebuild the response list.
    
    # Function to get search keywords for matching
    def matches_search(contest, search_lower):
        if not search_lower:
            return True
        contest_name = (contest.name or "").lower()
        contest_description = (contest.description or "").lower()
        contest_type = (contest.contest_type or "").lower()
        category_name = ""
        if hasattr(contest, 'category') and contest.category:
            category_name = (contest.category.name or "").lower() if hasattr(contest.category, 'name') else ""
        return (search_lower in contest_name or 
                search_lower in contest_description or 
                search_lower in contest_type or
                search_lower in category_name)

    search_lower = search_term.lower().strip() if search_term else None

    # Process each round
    for r_item in rounds_iterable:
        if hasattr(r_item, '__dict__'):
            r_dict = {k: v for k, v in r_item.__dict__.items() if not k.startswith('_')}
        else:
             r_dict = dict(r_item)
             
        if "participants_count" not in r_dict:
             r_dict["participants_count"] = crud.round.count_participants_for_round(db, r_dict["id"])
        if "current_user_participated" not in r_dict:
             r_dict["current_user_participated"] = crud.round.user_participated_in_round(db, r_dict["id"], user_id) if user_id else False
        if "is_completed" not in r_dict:
             r_dict["is_completed"] = False

        r_dict["contests"] = []
        r_dict["top_contestants"] = []
        r_dict["votes_count"] = 0
        
        if hasattr(r_item, "contests") and r_item.contests:
            # 1. Filter contests in memory
            valid_contests = []
            for c in r_item.contests:
                if has_voting_type is not None:
                    if has_voting_type and c.voting_type_id is None:
                        continue
                    if not has_voting_type and c.voting_type_id is not None:
                        continue
                if search_lower and not matches_search(c, search_lower):
                    continue
                valid_contests.append(c)
            
            r_dict["contests_count"] = len(valid_contests)
            
            # Apply pagination
            paginated_contests = valid_contests[contest_skip : contest_skip + contest_limit]
            contest_ids = [c.id for c in paginated_contests]
            
            participant_counts = {}
            user_participation = {}
            
            if contest_ids:
                from app.models.contests import Contestant
                from sqlalchemy import select, func, or_
                
                # --- Batch Query 1: Participant Counts ---
                p_query = db.query(
                    Contestant.season_id, 
                    func.count(Contestant.id)
                ).filter(
                    Contestant.season_id.in_(contest_ids),
                    Contestant.is_deleted == False
                )
                
                # Apply location filters to the count query
                if filter_country and filter_country != 'all':
                    from app.crud.crud_contest import _get_country_match_patterns
                    country_patterns = _get_country_match_patterns(filter_country)
                    if country_patterns:
                        country_conds = [Contestant.country.ilike(pat) for pat in country_patterns]
                        p_query = p_query.filter(or_(*country_conds))
                    else:
                        p_query = p_query.filter(func.lower(Contestant.country) == func.lower(filter_country))
                        
                if filter_continent and filter_continent != 'all':
                    p_query = p_query.filter(func.lower(Contestant.continent) == func.lower(filter_continent))
                    
                counts_result = p_query.group_by(Contestant.season_id).all()
                participant_counts = {season_id: count for season_id, count in counts_result}

                # --- Batch Query 2: Current User Participation ---
                if user_id:
                    user_entries = db.query(Contestant.season_id).filter(
                        Contestant.user_id == user_id,
                        Contestant.season_id.in_(contest_ids),
                        Contestant.is_deleted == False
                    ).all()
                    # Store as a set/dict for O(1) lookup
                    user_participation = {row[0]: True for row in user_entries}

            # 3. Assemble the response
            for contest in paginated_contests:
                c_data = {
                    "id": contest.id,
                    "name": contest.name,
                    "description": contest.description,
                    "contest_type": contest.contest_type,
                    "cover_image_url": contest.cover_image_url,
                    "level": contest.level,
                    "participants_count": participant_counts.get(contest.id, 0),
                    "votes_count": 0, 
                    "image_url": contest.image_url,
                    "created_at": getattr(contest, "created_at", None),
                    "updated_at": getattr(contest, "updated_at", None),
                    "current_user_contesting": user_participation.get(contest.id, False)
                }
                r_dict["contests"].append(c_data)
            
            # Sort contests by participants_count (descending)
            r_dict["contests"].sort(key=lambda x: x.get("participants_count", 0), reverse=True)
        
        # Fallback to legacy contest_id logic if no N:N links found
        if not r_dict["contests"] and r_dict.get("contest_id"):
             linked_contest = crud.contest.get(db, id=r_dict["contest_id"])
             if linked_contest:
                 c_data = {
                     "id": linked_contest.id,
                     "name": linked_contest.name,
                     "description": linked_contest.description,
                     "contest_type": linked_contest.contest_type,
                     "cover_image_url": linked_contest.cover_image_url,
                     "level": linked_contest.level,
                     "participants_count": linked_contest.participant_count,
                     "votes_count": 0,
                     "image_url": linked_contest.image_url,
                     "created_at": getattr(linked_contest, "created_at", None),
                     "updated_at": getattr(linked_contest, "updated_at", None)
                 }
                 r_dict["contests"].append(c_data)
        
        # Fetch Top Contestants
        if r_dict.get("contest_id"):
            top_c = crud.contestant.get_multi_by_contest(
                db=db, contest_id=r_dict["contest_id"], limit=3, order_by="votes"
            )
            for tc in top_c:
                 author = crud.user.get(db, id=tc.user_id)
                 r_dict["top_contestants"].append({
                     "id": tc.id,
                     "author_name": author.username if author else "Unknown",
                     "author_avatar_url": author.avatar_url if author else None,
                     "image_url": None, 
                     "votes_count": 0, 
                     "rank": 0
                 })

        enriched_rounds.append(r_dict)
    
    return enriched_rounds


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

