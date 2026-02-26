from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_current_active_user, get_current_active_user_optional
from app.crud import contest
from app.db.session import get_db
from app.schemas.contest import Contest, ContestCreate, ContestUpdate, ContestWithEntries, ContestWithEnrichedContestants, VotingType
from app.core.cache import cache_service


class ParticipateRequest(BaseModel):
    """Request schema for participating in a contest"""
    title: str
    description: str
    image_media_ids: Optional[List[str]] = None
    video_media_ids: Optional[List[str]] = None
    nominator_city: Optional[str] = None
    nominator_country: Optional[str] = None
    round_id: Optional[int] = None

router = APIRouter()

@router.post("/", response_model=Contest, status_code=status.HTTP_201_CREATED)
def create_contest(
    *,
    db: Session = Depends(get_db),
    contest_in: ContestCreate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Créer un nouveau concours.
    """
    # Seuls les administrateurs peuvent créer des concours
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour créer un concours"
        )
    
    new_contest = contest.create(db=db, obj_in=contest_in)
    
    # Invalider le cache des contests
    cache_service.invalidate_contests()
    
    return new_contest

@router.get("/")
def read_contests(
    *,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 12,
    location_id: int = None,
    contest_type: str = None,
    active: bool = Query(None),
    search: str = Query(None, description="Recherche par nom de concours"),
    voting_level: str = Query(None, description="Filtrer par niveau de vote (country pour Nomination)"),
    voting_type_id: int = Query(None, description="Filtrer par ID du type de vote (pour Nominations)"),
    has_voting_type: bool = Query(None, description="Filtrer les contests avec/sans voting_type (True = avec, False = sans)"),
    filter_country: str = Query(None, description="Filtrer par pays (pour compter les contestants de ce pays)"),
    filter_region: str = Query(None, description="Filtrer par région (pour compter les contestants de cette région)"),
    filter_continent: str = Query(None, description="Filtrer par continent (pour compter les contestants de ce continent)"),
    sort_by: str = Query(None, description="Trier par un champ (ex: participant_count)"),
    sort_order: str = Query("desc", description="Ordre de tri (asc ou desc)"),
    current_user: Optional[Any] = Depends(get_current_active_user_optional),
) -> List[dict]:
    """
    Récupérer tous les concours avec filtrage optionnel, tri et statistiques.
    Endpoint public - accessible sans authentification.
    Le nombre de contestants affiché dépend de la saison du contest et de la localisation de l'utilisateur connecté (si authentifié).
    
    Paramètres de filtrage géographique (filter_country, filter_region, filter_continent):
    - Si fournis, le comptage des contestants sera basé sur ces filtres plutôt que sur la localisation de l'utilisateur
    - Par défaut (aucun filtre), utilise la localisation de l'utilisateur connecté
    """
    # Construire les filtres
    filters = {}
    # FIXED: Default to active contests only if not specified
    if active is not None:
        filters["is_active"] = active
    else:
        filters["is_active"] = True  # Default to active contests only
    
    if location_id:
        filters["location_id"] = location_id
    if contest_type:
        filters["contest_type"] = contest_type
    if search:
        filters["search"] = search
    if voting_level:
        filters["voting_level"] = voting_level
    if voting_type_id:
        filters["voting_type_id"] = voting_type_id
    if has_voting_type is not None:
        filters["has_voting_type"] = has_voting_type
        
    # Paramètres de tri
    if sort_by:
        # Map plural 'participants_count' to actual DB column 'participant_count' if needed
        if sort_by == "participants_count":
            sort_by = "participant_count"
        filters["sort_by"] = sort_by
    if sort_order:
        filters["sort_order"] = sort_order
    
    # Récupérer les contests depuis la base de données
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Fetching contests with filters: {filters}")
        contests = contest.get_multi_with_filters(
            db=db, skip=skip, limit=limit, filters=filters
        )
        logger.info(f"Successfully fetched {len(contests)} contests from database")
        
        # DEBUG: Log contest IDs and basic info
        if contests:
            logger.info(f"Sample contest IDs: {[c.id for c in contests[:5]]}")
            logger.info(f"Sample contest names: {[c.name for c in contests[:5]]}")
        else:
            logger.warning("No contests found in database with current filters!")
    except Exception as e:
        logger.error(f"Error fetching contests from database: {str(e)}", exc_info=True)
        # Re-raise to let the database session handler catch it properly
        raise
    
    # Enrichir chaque contest avec les statistiques
    # enrich_contest_with_stats retourne un dictionnaire avec toutes les valeurs converties
    enriched_contests = []
    
    # OPTIMIZED: Use lightweight enrichment for list views to avoid timeout
    # Batch query for contestant counts to avoid N+1 queries
    from app.models.contests import Contestant, ContestSeasonLink
    from sqlalchemy import func, or_
    
    contest_ids = [c.id for c in contests]
    contestant_counts = {}
    current_user_contesting_map = {}
    
    if contest_ids:
        # Batch query for contestant counts per contest
        try:
            # Get season_ids for contests
            season_links = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id.in_(contest_ids),
                ContestSeasonLink.is_active == True
            ).all()
            season_by_contest = {link.contest_id: link.season_id for link in season_links}
            
            # Batch count contestants by season_id (legacy) or round_id
            # Check both via ContestSeasonLink and direct contest_id (legacy)
            for contest_id in contest_ids:
                count = 0
                # Check via season_id from ContestSeasonLink
                if contest_id in season_by_contest:
                    season_id = season_by_contest[contest_id]
                    count = db.query(func.count(Contestant.id)).filter(
                        Contestant.season_id == season_id,
                        Contestant.is_deleted == False
                    ).scalar() or 0
                
                # Also check if season_id directly equals contest_id (legacy)
                direct_count = db.query(func.count(Contestant.id)).filter(
                    Contestant.season_id == contest_id,
                    Contestant.is_deleted == False
                ).scalar() or 0
                
                # Use the maximum count (in case both exist)
                contestant_counts[contest_id] = max(count, direct_count)
            
            # Check current_user_contesting in batch if user is authenticated
            # We want to know if the user is participating in the ACTIVE round or ACTIVE season
            if current_user:
                from app.models.round import Round
                from sqlalchemy import literal
                
                # For each contest, find its active round (if any)
                active_rounds_by_contest = {}
                try:
                    # Query active rounds for the given contests
                    active_rounds = db.query(Round).filter(
                        Round.contest_id.in_(contest_ids),
                        Round.is_active == True,
                        Round.is_deleted == False
                    ).all()
                    for r in active_rounds:
                        active_rounds_by_contest[r.contest_id] = r.id
                except Exception as e:
                    logger.warning(f"Error fetching active rounds: {str(e)}")
                
                # Fetch user's contestants that might match
                # It's safer to just fetch all active contestants for the user
                # and then match them against active rounds or seasons
                try:
                    user_contestants = db.query(Contestant).filter(
                        Contestant.user_id == current_user.id,
                        Contestant.is_deleted == False
                    ).all()
                    
                    for contest_id in contest_ids:
                        # 1. First, check active round
                        if contest_id in active_rounds_by_contest:
                            target_round_id = active_rounds_by_contest[contest_id]
                            # User is contesting if they have a contestant record for this round
                            is_contesting = any(uc.round_id == target_round_id for uc in user_contestants)
                            if is_contesting:
                                current_user_contesting_map[contest_id] = True
                                continue
                                
                        # 2. Try active Season via links
                        if contest_id in season_by_contest:
                            target_season_id = season_by_contest[contest_id]
                            is_contesting = any(uc.season_id == target_season_id for uc in user_contestants)
                            if is_contesting:
                                current_user_contesting_map[contest_id] = True
                                continue
                                
                        # 3. Fallback to contest.id itself (legacy)
                        is_contesting = any(uc.season_id == contest_id for uc in user_contestants)
                        if is_contesting:
                            current_user_contesting_map[contest_id] = True
                except Exception as e:
                    logger.warning(f"Error matching user contestants: {str(e)}")
        except Exception as e:
            logger.warning(f"Error in batch queries: {str(e)}")
    
    # Build lightweight response without full enrichment
    
    # Sort contests if returning all or by standard search
    
    basic_contests = []
    
    for c in contests:
        try:
            # Get voting type if exists
            voting_type_dict = None
            if c.voting_type_id and hasattr(c, 'voting_type') and c.voting_type:
                voting_type_dict = {
                    "id": c.voting_type.id,
                    "name": c.voting_type.name,
                    "voting_level": c.voting_type.voting_level.value if hasattr(c.voting_type.voting_level, 'value') else str(c.voting_type.voting_level),
                    "commission_source": c.voting_type.commission_source.value if hasattr(c.voting_type.commission_source, 'value') else str(c.voting_type.commission_source),
                }
            
            basic_contest = {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "contest_type": c.contest_type,
                "cover_image_url": c.cover_image_url or c.image_url,
                "image_url": c.image_url,
                "is_active": c.is_active,
                "is_submission_open": c.is_submission_open,
                "is_voting_open": c.is_voting_open,
                "level": c.level,
                "voting_type_id": getattr(c, 'voting_type_id', None),
                "voting_type": voting_type_dict,
                "entries_count": contestant_counts.get(c.id, 0),
                "contestants": contestant_counts.get(c.id, 0),  # For compatibility
                "participant_count": getattr(c, 'participant_count', 0),
                "total_votes": 0,  # Skip vote counting for list view
                "current_user_contesting": current_user_contesting_map.get(c.id, False),
            }
            # Debug log for current_user_contesting
            if current_user and current_user_contesting_map.get(c.id, False):
                logger.info(f"Contest {c.id} ({c.name}): User {current_user.id} has already nominated")
            enriched_contests.append(basic_contest)
        except Exception as e:
            logger.error(f"Error creating basic contest data for {c.id}: {str(e)}")
            continue
    
    # Sort contests by participant count only if not custom sorted
    # 1. First by actual participant_count in DB (mostly used on frontend)
    # 2. Then by the dynamically calculated contestants count
    # 3. Finally by ID to ensure deterministic sorting
    if not sort_by:
        enriched_contests.sort(
            key=lambda x: (
                x.get("participant_count", 0) or x.get("contestants", 0),
                x.get("id", 0)
            ), 
            reverse=True
        )
    
    logger.info(f"Successfully enriched {len(enriched_contests)} out of {len(contests)} contests")
    return enriched_contests


# IMPORTANT: These routes must come BEFORE /{contest_id} to avoid route conflicts
@router.post("/{contest_id}/participate", status_code=status.HTTP_201_CREATED)
def participate_in_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Any = Depends(get_current_active_user),
    request: ParticipateRequest = Body(...),
) -> Any:
    """
    Submit a nomination/participation for a contest.
    This endpoint delegates to the contestant creation endpoint.
    """
    from app.schemas.contestant import ContestantCreate
    
    # Convert media IDs to JSON strings if needed (ContestantCreate expects JSON strings)
    import json
    image_ids_str = None
    if request.image_media_ids:
        if isinstance(request.image_media_ids, list):
            image_ids_str = json.dumps(request.image_media_ids)
        else:
            image_ids_str = request.image_media_ids
    
    video_ids_str = None
    if request.video_media_ids:
        if isinstance(request.video_media_ids, list):
            video_ids_str = json.dumps(request.video_media_ids)
        else:
            video_ids_str = request.video_media_ids
    
    # Create the contestant data schema
    contestant_data = ContestantCreate(
        title=request.title or "",
        description=request.description or "",
        image_media_ids=image_ids_str,
        video_media_ids=video_ids_str,
        nominator_city=request.nominator_city,
        nominator_country=request.nominator_country,
        round_id=request.round_id
    )
    
    # Import the create_contestant function from contestant module
    from app.api.api_v1.endpoints.contestant import create_contestant
    
    # Call the contestant endpoint function
    return create_contestant(
        db=db,
        current_user=current_user,
        contest_id=contest_id,
        contestant_data=contestant_data
    )


@router.get("/{contest_id}/rounds")
def get_contest_rounds(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Optional[Any] = Depends(get_current_active_user_optional),
) -> Any:
    """
    Get all rounds for a specific contest.
    """
    from app.crud import round as crud_round
    
    # Verify contest exists
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Get rounds with stats for this contest
    user_id = current_user.id if current_user else None
    rounds_with_stats = crud_round.get_rounds_with_stats(
        db=db, contest_id=contest_id, user_id=user_id
    )
    
    return rounds_with_stats


@router.get("/{contest_id}", response_model=ContestWithEnrichedContestants)
def read_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    filter_country: str = Query(None, description="Filtrer par pays"),
    filter_continent: str = Query(None, description="Filtrer par continent"),
    current_user: Optional[Any] = Depends(get_current_active_user_optional),
) -> Any:
    """
    Récupérer un concours spécifique avec ses contestants enrichis.
    Le nombre de contestants affiché dépend de la saison du contest et de la localisation de l'utilisateur connecté (si authentifié).
    
    Filtrage géographique basé sur la saison active :
    - city: même ville et pays
    - country: même pays
    - regional: même région
    - continent: même continent
    - global: tous les contestants
    
    Si filter_country ou filter_continent sont fournis, ils ont priorité sur la localisation de l'utilisateur.
    Si aucun filtre n'est fourni, on utilise la localisation de l'utilisateur connecté par défaut.
    """
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Utiliser la méthode simplifiée qui utilise directement les champs du Contestant
    current_user_id = current_user.id if current_user else None
    enriched_contest = contest.get_contest_with_enriched_contestants(
        db=db, 
        contest_id=contest_id, 
        current_user_id=current_user_id,
        filter_country=filter_country,
        filter_continent=filter_continent
    )
    
    if not enriched_contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Enrich with current user participation
    if current_user and enriched_contest:
        from app.crud import contestant as crud_contestant
        from app.models.contests import ContestSeasonLink, ContestSeason
        
        # 1. Try to find active ContestSeason via ContestSeasonLink
        season_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True
        ).first()

        from app import crud
        # First, check active round as participation is now round-specific
        active_round = crud.round.get_active_round_for_contest(db, contest_id)
        target_round_id = active_round.id if active_round else None

        participation = None
        if target_round_id:
            participation = crud_contestant.get_by_round_and_user(
                db=db, 
                round_id=target_round_id, 
                user_id=current_user.id
            )
        else:
            # Fallback to season logic if no active round
            season_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.is_active == True
            ).first()

            season_id = None
            if season_link:
                season = db.query(ContestSeason).filter(
                    ContestSeason.id == season_link.season_id,
                    ContestSeason.is_deleted == False
                ).first()
                if season:
                    season_id = season.id
            
            # 2. Fallback to contest.id if no active season found (legacy behavior)
            if not season_id:
                season_id = contest_id

                # Check if we have participation
                participation = crud_contestant.get_by_season_and_user(
                    db=db, 
                    season_id=season_id, 
                    user_id=current_user.id
                )
                if participation:
                     # Fetch media for the participation if missing from the object
                     media_obj = participation.media
                     if not media_obj and participation.media_id:
                         from app.models.media import Media
                         media_obj = db.query(Media).filter(Media.id == participation.media_id).first()
            # Check if we have participation
            participation = crud_contestant.get_by_season_and_user(
                db=db, 
                season_id=season_id, 
                user_id=current_user.id
            )
        if participation:
             # Fetch media for the participation if missing from the object
             media_obj = participation.media
             if not media_obj and participation.media_id:
                 from app.models.media import Media
                 media_obj = db.query(Media).filter(Media.id == participation.media_id).first()

                     # Add to response - simplified map
                     participation_dict = {
                         "id": participation.id,
                         "contest_id": participation.contest_id,
                         "user_id": participation.user_id,
                         "media_id": participation.media_id,
                         "total_score": participation.total_score,
                         "rank": participation.rank,
                         # We need media object for schema validation
                         "media": media_obj
                     }
                     enriched_contest["current_user_participation"] = participation_dict
            except Exception as e:
                # Log but don't fail the request if participation enrichment fails
                logger.warning(f"Error enriching user participation for contest {contest_id}: {str(e)}")
                logger.debug(traceback.format_exc())

        return enriched_contest
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the full error for debugging
        logger.error(f"Error fetching contest {contest_id}: {str(e)}")
        logger.error(traceback.format_exc())
        # Return a 500 error with a user-friendly message
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération du concours: {str(e)}"
        )

@router.put("/{contest_id}", response_model=Contest)
def update_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    contest_in: ContestUpdate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Mettre à jour un concours.
    """
    # Seuls les administrateurs peuvent mettre à jour des concours
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour mettre à jour un concours"
        )
    
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    updated_contest = contest.update(db=db, db_obj=contest_obj, obj_in=contest_in)
    
    # Invalider le cache des contests
    cache_service.invalidate_contests()
    
    return updated_contest


@router.delete("/{contest_id}", response_model=Contest)
def delete_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Supprimer un concours (soft delete).
    """
    # Seuls les administrateurs peuvent supprimer des concours
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour supprimer un concours"
        )
    
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    deleted_contest = contest.remove(db=db, id=contest_id)
    
    # Invalider le cache des contests
    cache_service.invalidate_contests()
    
    return deleted_contest
