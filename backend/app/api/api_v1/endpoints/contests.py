from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_current_active_user, get_current_active_user_optional
from app.crud import contest
from app.db.session import get_db
from app.schemas.contest import Contest, ContestCreate, ContestUpdate, ContestWithEntries, ContestWithEnrichedContestants
from app.core.cache import cache_service
import traceback
import logging

logger = logging.getLogger(__name__)


def _normalize_contest_mode(mode: Any) -> str:
    if mode is None:
        return "participation"
    value = mode.value if hasattr(mode, "value") else mode
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return "participation"
    low = text.lower()
    if low in ("nomination", "nominate"):
        return "nomination"
    if low in ("participation", "participant", "participate"):
        return "participation"
    token = text.split(".")[-1].strip().lower()
    if token in {"nomination", "nominate"}:
        return "nomination"
    if token in {"participation", "participant", "participate"}:
        return "participation"
    if "nomination" in low and "participation" not in low:
        return "nomination"
    return "participation"


def _entry_type_from_contest_mode(mode: Any) -> str:
    return "nomination" if _normalize_contest_mode(mode) == "nomination" else "participation"


class ParticipateRequest(BaseModel):
    """Request schema for participating in a contest"""
    title: str
    description: str
    image_media_ids: Optional[List[str]] = None
    video_media_ids: Optional[List[str]] = None
    nominator_city: Optional[str] = None
    nominator_country: Optional[str] = None
    round_id: Optional[int] = None


class VideoLinkValidationRequest(BaseModel):
    """Request schema for validating a contestant video link before submission."""
    video_media_ids: List[str]
    round_id: Optional[int] = None
    contestant_id: Optional[int] = None

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
    contest_mode: str = Query(None, description="Filtrer par mode: nomination ou participation"),
    filter_country: str = Query(None, description="Filtrer par pays (pour compter les contestants de ce pays)"),
    filter_region: str = Query(None, description="Filtrer par région (pour compter les contestants de cette région)"),
    filter_continent: str = Query(None, description="Filtrer par continent (pour compter les contestants de ce continent)"),
    round_id: Optional[int] = Query(None, alias="roundId", description="Calendar round id so participant counts match that round"),
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
    if contest_mode:
        filters["contest_mode"] = contest_mode
        
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
            # Build contest_mode map for entry_type filtering
            contest_mode_map = {c.id: _normalize_contest_mode(getattr(c, 'contest_mode', 'participation')) for c in contests}

            for contest_id in contest_ids:
                count = 0
                # Determine expected entry_type based on contest_mode
                expected_entry_type = _entry_type_from_contest_mode(contest_mode_map.get(contest_id))
                # Check via season_id from ContestSeasonLink
                if contest_id in season_by_contest:
                    season_id = season_by_contest[contest_id]
                    count = db.query(func.count(Contestant.id)).filter(
                        Contestant.season_id == season_id,
                        Contestant.is_deleted == False,
                        Contestant.entry_type == expected_entry_type
                    ).scalar() or 0
                
                # Also check if season_id directly equals contest_id (legacy)
                direct_count = db.query(func.count(Contestant.id)).filter(
                    Contestant.season_id == contest_id,
                    Contestant.is_deleted == False,
                    Contestant.entry_type == expected_entry_type
                ).scalar() or 0
                
                # Prefer direct_count (season_id == contest_id) as it is contest-specific
                # ContestSeasonLink seasons may be shared across contests
                contestant_counts[contest_id] = direct_count if direct_count > 0 else count
            
            # Check current_user_contesting in batch if user is authenticated
            # We want to know if the user is participating in the ACTIVE round or ACTIVE season
            if current_user:
                from app.models.round import Round
                from sqlalchemy import literal
                
                # For each contest, find its active round (if any)
                active_rounds_by_contest = {}
                try:
                    # Query active rounds via round_contests N:N table
                    from app.models.round import round_contests
                    from datetime import date
                    today = date.today()

                    active_round_links = db.query(
                        round_contests.c.contest_id,
                        Round.id
                    ).join(
                        Round, Round.id == round_contests.c.round_id
                    ).filter(
                        round_contests.c.contest_id.in_(contest_ids),
                        Round.submission_start_date <= today,
                        Round.submission_end_date >= today,
                        Round.status != 'cancelled'
                    ).all()
                    for link in active_round_links:
                        active_rounds_by_contest[link[0]] = link[1]
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
                        expected_entry_type = _entry_type_from_contest_mode(contest_mode_map.get(contest_id))
                        is_nomination = expected_entry_type == "nomination"

                        def _entry_matches(uc) -> bool:
                            raw_et = getattr(uc, "entry_type", None)
                            if is_nomination:
                                if raw_et is None:
                                    return True
                                return str(raw_et).strip().lower() == "nomination"
                            return (raw_et or "participation") == expected_entry_type

                        # Nominations: any round for this contest (hub pill may be vote month).
                        if is_nomination:
                            is_contesting = any(
                                uc.season_id == contest_id and _entry_matches(uc)
                                for uc in user_contestants
                            )
                            if is_contesting:
                                current_user_contesting_map[contest_id] = True
                            continue

                        # Participations: round-scoped when an active submission round exists.
                        if contest_id in active_rounds_by_contest:
                            target_round_id = active_rounds_by_contest[contest_id]
                            is_contesting = any(
                                uc.round_id == target_round_id
                                and uc.season_id == contest_id
                                and _entry_matches(uc)
                                for uc in user_contestants
                            )
                            if is_contesting:
                                current_user_contesting_map[contest_id] = True
                                continue

                        is_contesting = any(
                            uc.season_id == contest_id and _entry_matches(uc)
                            for uc in user_contestants
                        )
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
            expected_entry_type = _entry_type_from_contest_mode(
                _normalize_contest_mode(getattr(c, "contest_mode", "participation"))
            )
            stats_for_card = contest.enrich_contest_with_stats(
                db=db,
                contest=c,
                current_user=current_user,
                filter_country=filter_country,
                filter_region=filter_region,
                filter_continent=filter_continent,
                include_top_contestants=False,
                entry_type=expected_entry_type,
                round_id=round_id,
            )
            visible_participants_count = int(stats_for_card.get("participants_count") or 0)
            # Singeli/East Africa special alignment: card count must match opened roster.
            if (
                c.id == 17
                and str(filter_region or "").strip().lower() in {"east africa", "east_africa"}
                and _normalize_contest_mode(getattr(c, "contest_mode", "participation")) == "nomination"
            ):
                opened_view_data = contest.get_contest_with_enriched_contestants(
                    db=db,
                    contest_id=c.id,
                    current_user_id=current_user.id if current_user else None,
                    filter_country=filter_country,
                    filter_region=filter_region,
                    filter_continent=filter_continent,
                    entry_type=expected_entry_type,
                    round_id=None,
                )
                opened_rows = (opened_view_data or {}).get("contestants") or []
                visible_participants_count = len(opened_rows)
            elif (
                _normalize_contest_mode(getattr(c, "contest_mode", "participation")) == "nomination"
                and contest.explicit_geo_filters_for_nomination_card(
                    filter_country, filter_region, filter_continent
                )
            ):
                visible_participants_count = contest.count_nomination_roster_for_card(
                    db,
                    contest_id=c.id,
                    current_user_id=current_user.id if current_user else None,
                    filter_country=filter_country,
                    filter_region=filter_region,
                    filter_continent=filter_continent,
                    entry_type=expected_entry_type,
                    round_id=round_id,
                )

            
            user_entry_round_id = None
            if current_user and current_user_contesting_map.get(c.id, False):
                expected_et = _entry_type_from_contest_mode(
                    _normalize_contest_mode(getattr(c, "contest_mode", "participation"))
                )
                from app.crud import contestant as crud_contestant_mod

                latest = crud_contestant_mod.get_latest_entry_in_contest(
                    db,
                    contest_id=c.id,
                    user_id=current_user.id,
                    entry_type=expected_et,
                    round_id=None,
                )
                if latest and getattr(latest, "round_id", None) is not None:
                    user_entry_round_id = latest.round_id

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
                "contest_mode": _normalize_contest_mode(getattr(c, 'contest_mode', 'participation')),
                # Keep card count aligned with opened contest roster filters.
                "entries_count": visible_participants_count,
                "contestants": visible_participants_count,  # For compatibility
                "participant_count": visible_participants_count,
                "total_votes": 0,  # Skip vote counting for list view
                "current_user_contesting": bool(current_user_contesting_map.get(c.id, False)),  # Explicitly convert to bool, default False
                "user_entry_round_id": user_entry_round_id,
            }
            # Debug log for current_user_contesting
            if current_user and current_user_contesting_map.get(c.id, False):
                logger.info(f"Contest {c.id} ({c.name}): User {current_user.id} has already nominated")
            enriched_contests.append(basic_contest)
        except Exception as e:
            logger.error(f"Error creating basic contest data for {c.id}: {str(e)}")
            continue
    
    # Sort contests by participant count (descending - highest first) only if not custom sorted
    # Use the dynamically calculated contestants count (entries_count) which is accurate
    # 1. First by contestants count (entries_count) - most participants first
    # 2. Then by participant_count from DB as fallback
    # 3. Finally by ID to ensure deterministic sorting
    if not sort_by:
        enriched_contests.sort(
            key=lambda x: (
                x.get("contestants", 0) or x.get("entries_count", 0) or x.get("participant_count", 0),
                x.get("id", 0)
            ), 
            reverse=True  # Descending order - highest participant count first
        )
    
    # Backend business rule for tab consistency (Meme Contest only):
    # - nomination tab: hide empty "Meme Contest" nominations
    # - participation tab: include empty "Meme Contest" nominations as city level
    requested_mode = (contest_mode or "").strip().lower()
    if requested_mode in {"nomination", "participation"}:
        filtered_contests = []
        for item in enriched_contests:
            normalized_mode = _normalize_contest_mode(item.get("contest_mode"))
            participants_count = int(item.get("entries_count") or item.get("contestants") or item.get("participant_count") or 0)
            contest_name = str(item.get("name") or "").strip().lower()
            is_meme_contest = contest_name == "meme contest"

            if requested_mode == "nomination":
                # Only special-case Meme Contest with zero participants.
                # Other nomination contests keep default behavior.
                if not (is_meme_contest and normalized_mode == "nomination" and participants_count == 0):
                    filtered_contests.append(item)
            else:
                if normalized_mode == "participation" or (is_meme_contest and normalized_mode == "nomination" and participants_count == 0):
                    # Render shifted empty Meme Contest nomination in city level for participation tab UX.
                    if is_meme_contest and normalized_mode == "nomination" and participants_count == 0:
                        item = {**item, "level": "city"}
                    filtered_contests.append(item)

        enriched_contests = filtered_contests

    logger.info(f"Successfully enriched {len(enriched_contests)} out of {len(contests)} contests")
    return enriched_contests


# IMPORTANT: These routes must come BEFORE /{contest_id} to avoid route conflicts
@router.post("/{contest_id}/validate-video-link", status_code=status.HTTP_200_OK)
def validate_contest_video_link(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Any = Depends(get_current_active_user),
    request: VideoLinkValidationRequest = Body(...),
) -> Any:
    """
    Validate a video link before the user proceeds to the next participation step.
    Blocks duplicate content links from the same social platform in the same category/round.
    """
    import json

    from app.api.api_v1.endpoints.contestant import (
        _find_duplicate_video_submission,
        _get_contest_context_from_season,
        _get_contest_ids_from_season,
    )
    from app.models.contest import Contest as ContestModel
    from app.models.contests import ContestSeason, ContestSeasonLink
    from app.models.round import Round

    contest_obj = db.query(ContestModel).filter(
        ContestModel.id == contest_id,
        ContestModel.is_deleted == False
    ).first()

    season = None
    if not contest_obj:
        season = db.query(ContestSeason).filter(
            ContestSeason.id == contest_id,
            ContestSeason.is_deleted == False
        ).first()
        if not season:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contest not found"
            )

    real_contest_id = contest_obj.id if contest_obj else contest_id
    if not contest_obj and season:
        link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.season_id == season.id,
            ContestSeasonLink.is_active == True
        ).first()
        if link:
            real_contest_id = link.contest_id
            contest_obj = db.query(ContestModel).filter(
                ContestModel.id == real_contest_id,
                ContestModel.is_deleted == False
            ).first()

    target_round_id = request.round_id
    if target_round_id is None and real_contest_id:
        from app import crud
        active_round = crud.round.get_active_round_for_contest(db, real_contest_id)
        if active_round:
            target_round_id = active_round.id

    if target_round_id:
        round_obj = db.query(Round).filter(Round.id == target_round_id).first()
        if not round_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Round id not found"
            )

    video_media_ids = json.dumps(request.video_media_ids or [])
    season_id_for_context = real_contest_id or (season.id if season else None)
    current_contexts = _get_contest_context_from_season(db, season_id_for_context)
    current_category_id, current_contest_mode = next(
        iter(current_contexts),
        (
            contest_obj.category_id if contest_obj else None,
            contest_obj.contest_mode if contest_obj else None
        )
    )
    current_contest_ids = (
        {real_contest_id}
        if real_contest_id
        else _get_contest_ids_from_season(db, season_id_for_context)
    )

    duplicate_submission = _find_duplicate_video_submission(
        db,
        video_media_ids=video_media_ids,
        target_round_id=target_round_id,
        current_category_id=current_category_id,
        current_contest_mode=current_contest_mode,
        current_contest_ids=current_contest_ids,
        exclude_contestant_id=request.contestant_id,
    )

    if duplicate_submission:
        existing_contestant, matched_url = duplicate_submission
        return {
            "is_duplicate": True,
            "detail": (
                "This content link has already been submitted by another participant "
                "on the same social media in this category and round."
            ),
            "matched_url": matched_url,
            "existing_contestant_id": existing_contestant.id,
        }

    return {
        "is_duplicate": False,
        "detail": "Video link is available for submission."
    }


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
    filter_country: Optional[str] = Query(None, alias="filterCountry", description="Filtrer par pays"),
    country: Optional[str] = Query(None, description="Legacy: filtrer par pays (même effet que filterCountry)"),
    filter_region: Optional[str] = Query(None, alias="filterRegion", description="Filtrer par région"),
    filter_continent: Optional[str] = Query(None, alias="filterContinent", description="Filtrer par continent"),
    continent_q: Optional[str] = Query(None, alias="continent", description="Legacy: filtrer par continent"),
    entry_type: Optional[str] = Query(None, alias="entryType", description="Filtrer par type: nomination ou participation"),
    round_id: Optional[int] = Query(
        None,
        alias="roundId",
        description="Calendar round (e.g. March vs April). Only contestants for this round are listed.",
    ),
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
    
    merged_country = filter_country if filter_country is not None else country
    merged_continent = filter_continent if filter_continent is not None else continent_q

    # Utiliser la méthode simplifiée qui utilise directement les champs du Contestant
    current_user_id = current_user.id if current_user else None
    enriched_contest = contest.get_contest_with_enriched_contestants(
        db=db, 
        contest_id=contest_id, 
        current_user_id=current_user_id,
        filter_country=merged_country,
        filter_region=filter_region,
        filter_continent=merged_continent,
        entry_type=entry_type,
        round_id=round_id,
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
        # Use the same calendar round as the roster (display_round_id), not a stale URL round.
        display_rid = enriched_contest.get("display_round_id") if isinstance(enriched_contest, dict) else None
        target_round_id = display_rid
        if target_round_id is None:
            active_round = crud.round.get_active_round_for_contest(db, contest_id)
            target_round_id = active_round.id if active_round else None

        expected_entry_type = _entry_type_from_contest_mode(getattr(contest_obj, "contest_mode", "participation"))
        participation = crud_contestant.get_latest_entry_in_contest(
            db=db,
            contest_id=contest_id,
            user_id=current_user.id,
            entry_type=expected_entry_type,
            round_id=target_round_id,
        )
        if participation is None and expected_entry_type == "nomination":
            participation = crud_contestant.get_latest_entry_in_contest(
                db=db,
                contest_id=contest_id,
                user_id=current_user.id,
                entry_type=expected_entry_type,
                round_id=None,
            )

        if participation:
            try:
                participation_dict = {
                    "id": participation.id,
                    "user_id": participation.user_id,
                    "title": getattr(participation, 'title', None),
                    "description": getattr(participation, 'description', None),
                    "image_media_ids": getattr(participation, 'image_media_ids', None),
                    "video_media_ids": getattr(participation, 'video_media_ids', None),
                    "total_score": getattr(participation, 'total_score', None),
                    "rank": getattr(participation, 'rank', None),
                    "entry_type": getattr(participation, 'entry_type', 'participation'),
                    "round_id": getattr(participation, 'round_id', None),
                    "season_id": getattr(participation, 'season_id', None),
                    "nominator_country": getattr(participation, 'nominator_country', None),
                    "nominator_city": getattr(participation, 'nominator_city', None),
                }
                enriched_contest["current_user_participation"] = participation_dict
                enriched_contest["current_user_contesting"] = True
                if getattr(participation, "round_id", None) is not None:
                    enriched_contest["user_entry_round_id"] = participation.round_id
            except Exception as e:
                logger.warning(f"Error enriching user participation for contest {contest_id}: {str(e)}")
                logger.debug(traceback.format_exc())

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
