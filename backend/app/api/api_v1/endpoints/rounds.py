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
    
    # Helper to calculate votes count (Mock implementation for migration)
    def get_round_votes_count(round_id):
        # TODO: Implement real count query
        return 0

    for r_item in rounds_iterable:
        # Normalize to dict
        if hasattr(r_item, '__dict__'):
            r_dict = {k: v for k, v in r_item.__dict__.items() if not k.startswith('_')}
        else:
             r_dict = dict(r_item)
             
        # Ensure base stats are present if coming from raw ORM
        if "participants_count" not in r_dict:
             r_id = r_dict["id"]
             r_dict["participants_count"] = crud.round.count_participants_for_round(db, r_id)
        if "current_user_participated" not in r_dict:
             r_id = r_dict["id"]
             r_dict["current_user_participated"] = crud.round.user_participated_in_round(db, r_id, user_id) if user_id else False
        if "is_completed" not in r_dict:
             # creating a dummy object to use the existing utility
             # or just copy reuse logic
             is_completed = False # simplified
             r_dict["is_completed"] = is_completed

        # Initialize new fields
        r_dict["contests"] = []
        r_dict["top_contestants"] = []
        r_dict["votes_count"] = get_round_votes_count(r_dict["id"])
        
        if hasattr(r_item, "contests") and r_item.contests:
            # First, calculate total contests (before filtering/limiting) that match the filter criteria
            total_contests = 0
            for c in r_item.contests:
                # Filter by voting_type presence if requested
                if has_voting_type is not None:
                    if has_voting_type and c.voting_type_id is None:
                        continue
                    if not has_voting_type and c.voting_type_id is not None:
                        continue
                
                # Filter by search term if provided
                if search_term:
                    search_lower = search_term.lower().strip()
                    if search_lower:  # Only filter if search term is not empty
                        contest_name = (c.name or "").lower()
                        contest_description = (c.description or "").lower()
                        contest_type = (c.contest_type or "").lower()
                        # Also search in category name if available
                        category_name = ""
                        if hasattr(c, 'category') and c.category:
                            category_name = (c.category.name or "").lower() if hasattr(c.category, 'name') else ""
                        elif hasattr(c, 'category_id') and c.category_id:
                            # Try to get category name from relationship if not loaded
                            try:
                                from app.models.category import Category
                                category = db.query(Category).filter(Category.id == c.category_id).first()
                                if category and hasattr(category, 'name'):
                                    category_name = (category.name or "").lower()
                            except:
                                pass
                        
                        # Search in all fields
                        if (search_lower not in contest_name and 
                            search_lower not in contest_description and 
                            search_lower not in contest_type and
                            search_lower not in category_name):
                            continue
                
                total_contests += 1
            
            r_dict["contests_count"] = total_contests
            
            contests_added = 0
            contests_skipped = 0
            for contest in r_item.contests:
                 # Filter by voting_type presence if requested
                 if has_voting_type is not None:
                     if has_voting_type and contest.voting_type_id is None:
                         continue
                     if not has_voting_type and contest.voting_type_id is not None:
                         continue
                 
                 # Filter by search term if provided
                 if search_term:
                     search_lower = search_term.lower().strip()
                     if search_lower:  # Only filter if search term is not empty
                         contest_name = (contest.name or "").lower()
                         contest_description = (contest.description or "").lower()
                         contest_type = (contest.contest_type or "").lower()
                         # Also search in category name if available
                         category_name = ""
                         if hasattr(contest, 'category') and contest.category:
                             category_name = (contest.category.name or "").lower() if hasattr(contest.category, 'name') else ""
                         elif hasattr(contest, 'category_id') and contest.category_id:
                             # Try to get category name from relationship if not loaded
                             try:
                                 from app.models.category import Category
                                 category = db.query(Category).filter(Category.id == contest.category_id).first()
                                 if category and hasattr(category, 'name'):
                                     category_name = (category.name or "").lower()
                             except:
                                 pass
                         
                         # Search in all fields
                         if (search_lower not in contest_name and 
                             search_lower not in contest_description and 
                             search_lower not in contest_type and
                             search_lower not in category_name):
                             continue
                 
                 # Skip contests for pagination
                 if contests_skipped < contest_skip:
                     contests_skipped += 1
                     continue
                     
                 if contests_added >= contest_limit:
                     break

                 # Count participants for this specific contest using the Contestant table
                 # Contestant.season_id stores the contest ID (legacy field name)
                 # Apply location filters if provided
                 from app.models.contests import Contestant
                 from app.models.round import round_contests
                 from sqlalchemy import select
                 
                 # Find round IDs linked to this contest
                 round_ids = []
                 try:
                     round_ids_via_table = db.execute(
                         select(round_contests.c.round_id).where(
                             round_contests.c.contest_id == contest.id
                         )
                     ).fetchall()
                     if round_ids_via_table:
                         round_ids.extend([r[0] for r in round_ids_via_table])
                 except Exception:
                     pass
                 
                 # Build query for participant count
                 p_query = db.query(func.count(Contestant.id)).filter(
                     Contestant.season_id == contest.id,
                     Contestant.is_deleted == False
                 )
                 # Apply country filter with pattern matching (handles "CI" vs "Côte d'Ivoire")
                 if filter_country and filter_country != 'all':
                     from app.crud.crud_contest import _get_country_match_patterns
                     country_patterns = _get_country_match_patterns(filter_country)
                     if country_patterns:
                         from sqlalchemy import or_
                         country_conds = [Contestant.country.ilike(pat) for pat in country_patterns]
                         p_query = p_query.filter(or_(*country_conds))
                     else:
                         p_query = p_query.filter(func.lower(Contestant.country) == func.lower(filter_country))
                 if filter_continent and filter_continent != 'all':
                     p_query = p_query.filter(func.lower(Contestant.continent) == func.lower(filter_continent))
                 real_p_count = p_query.scalar() or 0
                 
                 # Check if current user has participated in this contest
                 # Need to check: season_id via ContestSeasonLink, season_id = contest.id (legacy), and round_id
                 current_user_contesting = False
                 if user_id:
                     try:
                         from sqlalchemy import or_
                         from app.models.contests import ContestSeasonLink
                         
                         # Get season_id for this contest via ContestSeasonLink
                         season_link = db.query(ContestSeasonLink).filter(
                             ContestSeasonLink.contest_id == contest.id,
                             ContestSeasonLink.is_active == True
                         ).first()
                         season_id = season_link.season_id if season_link else None
                         
                         # Build conditions to check
                         conditions = []
                         
                         # 1. Check via season_id from ContestSeasonLink
                         if season_id:
                             conditions.append(Contestant.season_id == season_id)
                         
                         # 2. Check if season_id directly equals contest.id (legacy)
                         conditions.append(Contestant.season_id == contest.id)
                         
                         # 3. Check via round_id
                         if round_ids:
                             conditions.append(Contestant.round_id.in_(round_ids))
                         
                         # Query user contestants matching any condition
                         if conditions:
                             user_contestant = db.query(Contestant).filter(
                                 Contestant.is_deleted == False,
                                 Contestant.user_id == user_id,
                                 or_(*conditions) if len(conditions) > 1 else conditions[0]
                             ).first()
                             current_user_contesting = user_contestant is not None
                             
                             # Debug log
                             if current_user_contesting:
                                 logger.info(f"User {user_id} has nominated in contest {contest.id} ({contest.name})")
                     except Exception as e:
                         logger.warning(f"Error checking user participation for contest {contest.id}: {str(e)}")
                         current_user_contesting = False

                 c_data = {
                     "id": contest.id,
                     "name": contest.name,
                     "description": contest.description,
                     "contest_type": contest.contest_type,
                     "cover_image_url": contest.cover_image_url,
                     "level": contest.level,
                     "participants_count": real_p_count,
                     "votes_count": 0, # TODO: Fix vote count
                     "image_url": contest.image_url,
                     "created_at": getattr(contest, "created_at", None),
                     "updated_at": getattr(contest, "updated_at", None),
                     "current_user_contesting": current_user_contesting
                 }
                 r_dict["contests"].append(c_data)
                 contests_added += 1
            
            # Sort contests by participants_count (descending - most contestants first)
            # This ensures contests with more participants appear at the top
            r_dict["contests"].sort(key=lambda x: x.get("participants_count", 0), reverse=True)
        
        # Fallback to legacy contest_id logic if specific contest_id column is set and no N:N links found
        # (Only if we didn't already add it via N:N - avoiding duplicates if migration happened)
        if not r_dict["contests"] and r_dict.get("contest_id"):
             # It belongs to a specific contest (legacy)
             # Fetch that contest
             linked_contest = crud.contest.get(db, id=r_dict["contest_id"])
             if linked_contest:
                 # Minimal contest data
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
        
        # 2. Fetch Top Contestants
        # Need to query contestants for this round (or contest of this round)
        # ordered by votes.
        # Using crud.contestant logic
        if r_dict.get("contest_id"):
            top_c = crud.contestant.get_multi_by_contest(
                db=db, contest_id=r_dict["contest_id"], limit=3, order_by="votes"
            )
            for tc in top_c:
                 # Map to TopContestantPreview
                 # Need to fetch author info
                 author = crud.user.get(db, id=tc.user_id)
                 r_dict["top_contestants"].append({
                     "id": tc.id,
                     "author_name": author.username if author else "Unknown",
                     "author_avatar_url": author.avatar_url if author else None,
                     "image_url": None, # Extract from media
                     "votes_count": 0, # Need vote count
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

