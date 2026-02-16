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
    current_user: Optional[Any] = Depends(get_current_active_user_optional),
) -> List[dict]:
    """
    Récupérer tous les concours avec filtrage optionnel et statistiques.
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
    
    # Reduced logging to improve performance
    for c in contests:
        try:
            enriched = contest.enrich_contest_with_stats(
                db=db, 
                contest=c, 
                current_user=current_user,
                filter_country=filter_country,
                filter_region=filter_region,
                filter_continent=filter_continent,
                include_top_contestants=False  # Skip expensive top_contestants query for list views
            )
            if isinstance(enriched, dict):
                enriched_contests.append(enriched)
            else:
                logger.warning(f"Contest {c.id} enrichment returned non-dict: {type(enriched)}")
        except Exception as e:
            # FIXED: Log full error with traceback for debugging
            import traceback
            logger.error(f"Erreur lors de l'enrichissement du contest {c.id}: {str(e)}")
            logger.error(traceback.format_exc())
            # FIXED: Return basic contest data even if enrichment fails
            try:
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
                    "voting_type": None,
                    "entries_count": 0,
                    "total_votes": 0,
                }
                enriched_contests.append(basic_contest)
                logger.info(f"Added basic contest data for contest {c.id} after enrichment error")
            except Exception as e2:
                logger.error(f"Failed to create basic contest data for {c.id}: {str(e2)}")
            continue
    
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
        nominator_country=request.nominator_country
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
        # Check if we have participation
        participation = contest.get_participation_for_user(
            db=db, 
            contest_id=contest_id, 
            user_id=current_user.id
        )
        if participation:
             # Add to response - simplified map
             participation_dict = {
                 "id": participation.id,
                 "contest_id": participation.contest_id,
                 "user_id": participation.user_id,
                 "media_id": participation.media_id,
                 "total_score": participation.total_score,
                 "rank": participation.rank,
                 # We need media object for schema validation
                 "media": participation.media 
             }
             enriched_contest["current_user_participation"] = participation_dict

    return enriched_contest


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
