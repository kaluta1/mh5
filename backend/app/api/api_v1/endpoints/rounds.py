from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime
import logging
import traceback
import os

from app import crud, models
from app.schemas import round as round_schema
from app.api import deps
from app.models.round import Round, RoundStatus
from app.scripts.generate_monthly_rounds import generate_monthly_round

router = APIRouter()
logger = logging.getLogger(__name__)


def _normalize_contest_mode(mode: Any) -> str:
    if mode is None:
        return "participation"
    value = mode.value if hasattr(mode, "value") else mode
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return "participation"
    low = text.lower()
    # Whole-string labels (DB text / some enum serializations)
    if low in ("nomination", "nominate"):
        return "nomination"
    if low in ("participation", "participant", "participate"):
        return "participation"
    token = text.split(".")[-1].strip().lower()
    if token in {"nomination", "nominate"}:
        return "nomination"
    if token in {"participation", "participant", "participate"}:
        return "participation"
    # e.g. "ContestMode.NOMINATION" already handled by token; substring fallback for odd DB values
    if "nomination" in low and "participation" not in low:
        return "nomination"
    return "participation"


def _normalize_contest_level(level: Any) -> Optional[str]:
    if level is None:
        return None
    value = level.value if hasattr(level, "value") else level
    token = str(value).strip().strip('"').strip("'").lower()
    if not token or token == "all":
        return None
    if token in {"region", "regional"}:
        return "regional"
    if token in {"continent", "continental"}:
        return "continental"
    if token in {"city", "country", "global"}:
        return token
    return token


def _to_date_value(value: Any) -> Optional[date]:
    """Normalize ORM/JSON dates to date for comparisons."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _effective_is_voting_open(r_data: dict, round_obj: Optional[Round]) -> bool:
    """
    Voting is open when the round is not completed and the voting calendar says so
    (voting_start_date / voting_end_date + grace rules). The DB is_voting_open flag
    is still honored when true, but must not block voting when automation lags
    (e.g. April country vote opens 01 May while is_voting_open is still false).
    """
    if round_obj is not None:
        st = round_obj.status
        st_val = st.value if hasattr(st, "value") else str(st)
        if st_val == RoundStatus.COMPLETED.value:
            return False
    else:
        st_raw = r_data.get("status")
        if st_raw and str(st_raw).lower() == "completed":
            return False

    from app.services.contest_status import contest_status_service

    now = contest_status_service._utc_now()
    ro = round_obj
    if ro is not None and getattr(ro, "voting_start_date", None) and getattr(
        ro, "voting_end_date", None
    ):
        if contest_status_service.round_voting_open_at(ro, now):
            return True

    if not r_data.get("is_voting_open"):
        return False
    today = date.today()
    ve = _to_date_value(r_data.get("voting_end_date"))
    if ve is not None and today > ve:
        return False
    vs = _to_date_value(r_data.get("voting_start_date"))
    if vs is not None and today < vs:
        return False
    return True


def _dedupe_voting_open_to_latest_round(result: List[dict]) -> None:
    """
    Monthly rounds can leave is_voting_open=True on older months while voting_end_date
    spans the whole season (global). Only the latest round (max id) should stay open for API/UI.
    """
    if not result or len(result) < 2:
        return
    flagged = [r for r in result if r.get("is_voting_open")]
    if len(flagged) <= 1:
        return
    max_id = max(r["id"] for r in flagged)
    for r in result:
        if r.get("is_voting_open") and r["id"] != max_id:
            r["is_voting_open"] = False


def _contest_card_level_for_round(db: Session, round_obj: Round, contest: Any, mode: str) -> str:
    """
    Resolve the level shown on contest cards from the selected round timeline.

    Business rules for the current nomination flow:
    - participation contests stay CITY
    - nomination contests are COUNTRY until that round is allowed to advance
    - March can show REGIONAL now, but CONTINENT/GLOBAL must not appear early
    """
    if mode != "nomination":
        return "city"

    from app.models.contests import ContestSeason, ContestSeasonLink, SeasonLevel
    from app.services.season_migration import SeasonMigrationService

    today = date.today()
    for level in (SeasonLevel.GLOBAL, SeasonLevel.CONTINENT, SeasonLevel.REGIONAL):
        min_start = SeasonMigrationService._nomination_min_start_for_level(round_obj, level)
        if min_start and today < min_start:
            continue
        active_link = (
            db.query(ContestSeasonLink.id)
            .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
            .filter(
                ContestSeasonLink.contest_id == contest.id,
                ContestSeasonLink.is_active == True,
                ContestSeason.round_id == round_obj.id,
                ContestSeason.level == level,
                ContestSeason.is_deleted == False,
            )
            .first()
        )
        if active_link:
            return level.value

    return "country"


def _round_response_base(round_obj: Round) -> dict:
    """Build the common RoundWithStats shape without loading related contests."""
    return {
        "id": round_obj.id,
        "contest_id": getattr(round_obj, "contest_id", None),
        "name": round_obj.name or f"Round {round_obj.id}",
        "status": round_obj.status.value if hasattr(round_obj.status, "value") else str(round_obj.status),
        "is_submission_open": getattr(round_obj, "is_submission_open", True),
        "is_voting_open": getattr(round_obj, "is_voting_open", False),
        "current_season_level": getattr(round_obj, "current_season_level", None),
        "submission_start_date": getattr(round_obj, "submission_start_date", None),
        "submission_end_date": getattr(round_obj, "submission_end_date", None),
        "voting_start_date": getattr(round_obj, "voting_start_date", None),
        "voting_end_date": getattr(round_obj, "voting_end_date", None),
        "created_at": getattr(round_obj, "created_at", datetime.now()),
        "updated_at": getattr(round_obj, "updated_at", datetime.now()),
    }


def _schema_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _lightweight_round_data(
    db: Session,
    round_obj: Round,
    contest_mode: Optional[str],
    contest_level: Optional[str],
    search_term: Optional[str],
    contest_limit: int,
    contest_skip: int,
) -> dict:
    """
    Fast path for the round selector/page-open request.
    It avoids per-contest stat enrichment and uses denormalized contest counts.
    """
    r_data = _round_response_base(round_obj)
    try:
        is_completed = crud.round.is_round_completed(round_obj)
    except Exception as e:
        logger.warning(f"Error checking if round {round_obj.id} is completed: {str(e)}")
        is_completed = False

    contests_data = []
    contests_count = 0
    try:
        from app.models.contest import Contest as ContestModel
        from app.models.round import round_contests

        query = db.query(ContestModel).join(
            round_contests, ContestModel.id == round_contests.c.contest_id
        ).filter(
            round_contests.c.round_id == round_obj.id,
            ContestModel.is_active == True,
            ContestModel.is_deleted == False,
        )

        if search_term:
            search_like = f"%{search_term.lower().strip()}%"
            query = query.filter(
                (ContestModel.name.ilike(search_like)) |
                (ContestModel.description.ilike(search_like))
            )

        all_contests = query.order_by(ContestModel.participant_count.desc(), ContestModel.id.desc()).all()
        if contest_mode is not None:
            # Apply normalized filtering in Python to support enum/string drift
            # like "ContestMode.PARTICIPATION" across environments.
            all_contests = [
                c for c in all_contests
                if _normalize_contest_mode(getattr(c, "contest_mode", "participation")) == contest_mode
            ]
        wanted_level = _normalize_contest_level(contest_level)
        if wanted_level:
            all_contests = [
                c for c in all_contests
                if _normalize_contest_level(_contest_card_level_for_round(
                    db,
                    round_obj,
                    c,
                    _normalize_contest_mode(getattr(c, "contest_mode", "participation")),
                )) == wanted_level
            ]

        contests_count = len(all_contests)
        contests = all_contests[contest_skip:contest_skip + contest_limit]

        for contest in contests:
            contest_mode_value = _normalize_contest_mode(getattr(contest, "contest_mode", "participation"))
            try:
                display_level = _contest_card_level_for_round(db, round_obj, contest, contest_mode_value)
            except Exception as e:
                logger.warning(f"Error resolving lightweight contest level {contest.id}: {str(e)}")
                display_level = getattr(contest, "level", None) or ("country" if contest_mode_value == "nomination" else "city")

            participant_count = int(getattr(contest, "participant_count", 0) or 0)
            contests_data.append({
                "id": contest.id,
                "name": contest.name,
                "description": getattr(contest, "description", None),
                "contest_type": getattr(contest, "contest_type", None),
                "cover_image_url": getattr(contest, "cover_image_url", None),
                "is_active": getattr(contest, "is_active", True),
                "is_submission_open": getattr(contest, "is_submission_open", True),
                "is_voting_open": getattr(contest, "is_voting_open", False),
                "level": display_level,
                "location_id": getattr(contest, "location_id", None),
                "gender_restriction": getattr(contest, "gender_restriction", None),
                "voting_restriction": _schema_value(getattr(contest, "voting_restriction", None)),
                "max_entries_per_user": getattr(contest, "max_entries_per_user", 1),
                "template_id": getattr(contest, "template_id", None),
                "contest_mode": contest_mode_value,
                "category_id": getattr(contest, "category_id", None),
                "requires_kyc": getattr(contest, "requires_kyc", True),
                "verification_type": _schema_value(getattr(contest, "verification_type", "none")),
                "participant_type": _schema_value(getattr(contest, "participant_type", "individual")),
                "requires_visual_verification": getattr(contest, "requires_visual_verification", False),
                "requires_voice_verification": getattr(contest, "requires_voice_verification", False),
                "requires_brand_verification": getattr(contest, "requires_brand_verification", False),
                "requires_content_verification": getattr(contest, "requires_content_verification", False),
                "min_age": getattr(contest, "min_age", None),
                "max_age": getattr(contest, "max_age", None),
                "image_url": getattr(contest, "image_url", None),
                "created_at": getattr(contest, "created_at", None),
                "updated_at": getattr(contest, "updated_at", None),
                "entries_count": participant_count,
                "participants_count": participant_count,
                "votes_count": 0,
                "current_user_contesting": False,
            })
    except Exception as e:
        logger.warning(f"Error building lightweight contests for round {round_obj.id}: {str(e)}")

    result = {
        **r_data,
        "participants_count": 0,
        "contests_count": contests_count,
        "votes_count": 0,
        "current_user_participated": False,
        "is_completed": is_completed,
        "top_contestants": [],
        "contests": contests_data,
    }
    result["is_voting_open"] = _effective_is_voting_open(result, round_obj)
    return result


@router.get("/", response_model=List[round_schema.RoundWithStats])
def read_rounds(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 24,
    contest_id: Optional[int] = Query(None, description="ID du contest pour récupérer ses rounds"),
    round_id: Optional[int] = Query(None, alias="roundId", description="ID du round spécifique"),
    current_user: Optional[models.User] = Depends(deps.get_current_active_user_optional),
    contest_mode: Optional[str] = Query(None, alias="contestMode", description="Filtrer par mode: nomination ou participation"),
    contest_level: Optional[str] = Query(None, alias="contestLevel", description="Filtrer par niveau affiché: country, regional, continental, global"),
    filter_country: Optional[str] = Query(None, alias="filterCountry", description="Filtrer les participants par pays"),
    filter_region: Optional[str] = Query(None, alias="filterRegion", description="Filtrer les participants par région"),
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
        contest_mode = _normalize_contest_mode(contest_mode) if contest_mode else None
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
                    round_obj = _enrich_round_data(db, r_data, user_id, contest_mode, contest_level, filter_country,
                                                  filter_region, filter_continent, search_term, contest_limit, contest_skip)
                    if round_obj:
                        result.append(round_obj)
                _dedupe_voting_open_to_latest_round(result)
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

                if not round_id and not contest_id and not filter_country and not filter_region and not filter_continent:
                    result = [
                        _lightweight_round_data(
                            db,
                            r,
                            contest_mode,
                            contest_level,
                            search_term,
                            contest_limit,
                            contest_skip,
                        )
                        for r in db_rounds
                    ]
                    _dedupe_voting_open_to_latest_round(result)
                    return result
                
                # Convert ORM objects to dict format
                result = []
                for r in db_rounds:
                    try:
                        r_data = _round_response_base(r)
                        round_obj = _enrich_round_data(db, r_data, user_id, contest_mode, contest_level, filter_country,
                                                      filter_region, filter_continent, search_term, contest_limit, contest_skip)
                        if round_obj:
                            result.append(round_obj)
                    except Exception as round_error:
                        logger.error(f"Error processing round {r.id}: {str(round_error)}", exc_info=True)
                        continue
                
                _dedupe_voting_open_to_latest_round(result)
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
    contest_mode: Optional[str],
    contest_level: Optional[str],
    filter_country: Optional[str],
    filter_region: Optional[str],
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
        
        # Load round row for status + completion (used below for effective voting flag)
        round_obj: Optional[Round] = None
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
            wanted_level = _normalize_contest_level(contest_level)
            for c in contests:
                # Filter by contest_mode
                if contest_mode is not None:
                    c_mode = _normalize_contest_mode(getattr(c, 'contest_mode', 'participation'))
                    if c_mode != contest_mode:
                        continue

                if wanted_level:
                    c_mode_for_level = _normalize_contest_mode(getattr(c, 'contest_mode', 'participation'))
                    display_level_for_filter = _contest_card_level_for_round(db, round_obj, c, c_mode_for_level)
                    if _normalize_contest_level(display_level_for_filter) != wanted_level:
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

            # Always derive card counts from enrich_contest_with_stats for this calendar
            # round_id. Previously counts used Contest.participant_count unless geo filters
            # were set — that column is often stale, so gospel (and others) showed 1 while
            # the DB/detail API had many nominations for the active round.
            contest_participant_counts = {
                vc.id: int(getattr(vc, "participant_count", 0) or 0)
                for vc in valid_contests
            }
            valid_contests_by_id = {vc.id: vc for vc in valid_contests}
            valid_contest_ids = set(valid_contests_by_id.keys())

            if valid_contests:
                try:
                    current_user_obj = None
                    if user_id:
                        current_user_obj = (
                            db.query(models.User)
                            .filter(models.User.id == user_id)
                            .first()
                        )

                    for vc in valid_contests:
                        c_mode = _normalize_contest_mode(getattr(vc, "contest_mode", "participation"))
                        entry_type = "nomination" if c_mode == "nomination" else "participation"
                        stats = crud.contest.enrich_contest_with_stats(
                            db,
                            vc,
                            current_user=current_user_obj,
                            filter_country=filter_country,
                            filter_region=filter_region,
                            filter_continent=filter_continent,
                            include_top_contestants=False,
                            entry_type=entry_type,
                            round_id=round_id,
                        )
                        contest_participant_counts[vc.id] = int(
                            stats.get("participants_count", stats.get("entries_count", 0))
                        )
                except Exception as e:
                    logger.warning(
                        f"Per-contest enrich stats for round {round_id} failed, using DB columns: {e}"
                    )

            valid_contests.sort(key=lambda c: contest_participant_counts.get(c.id, 0), reverse=True)

            # Apply pagination AFTER sorting
            paginated_contests = valid_contests[contest_skip:contest_skip + contest_limit]
            
            # Batch query: find all contests where current user has participated in this round
            # IMPORTANT: "Edit" must be shown only for the exact contest/category where
            # the user already has a nomination/participation, not every contest sharing voting_type.
            user_contested_contest_ids: set = set()
            if user_id:
                try:
                    from app.models.contests import Contestant, ContestSeason, ContestSeasonLink
                    from app.api.api_v1.endpoints import contestant as contestant_ep

                    def _entry_type_for_contest(cid: int) -> str:
                        c = valid_contests_by_id.get(cid)
                        if not c:
                            return "participation"
                        cm = _normalize_contest_mode(getattr(c, "contest_mode", "participation"))
                        return "nomination" if cm == "nomination" else "participation"

                    season_by_contest_id: dict = {}
                    if valid_contest_ids:
                        rows = (
                            db.query(ContestSeasonLink.contest_id, ContestSeason)
                            .join(
                                ContestSeason,
                                ContestSeason.id == ContestSeasonLink.season_id,
                            )
                            .filter(
                                ContestSeasonLink.contest_id.in_(list(valid_contest_ids)),
                                ContestSeasonLink.is_active == True,
                            )
                            .all()
                        )
                        for cid, s in rows:
                            if cid is not None and s is not None and cid not in season_by_contest_id:
                                season_by_contest_id[cid] = s
                        for cid in valid_contest_ids:
                            season_by_contest_id.setdefault(cid, None)

                    unique_seasons: dict = {}
                    for _cid, _se in season_by_contest_id.items():
                        if _se is not None and _se.id not in unique_seasons:
                            unique_seasons[_se.id] = _se

                    all_user_contestants = db.query(Contestant).filter(
                        Contestant.user_id == user_id,
                        Contestant.is_deleted == False,
                    ).all()

                    if valid_contests:
                        user_contestants = [uc for uc in all_user_contestants if uc.round_id == round_id]
                        expected_type = "nomination" if contest_mode == "nomination" else "participation"
                        contested_ids: set = set()
                        for uc in user_contestants:
                            if getattr(uc, "entry_type", "participation") != expected_type:
                                continue
                            cid_direct = getattr(uc, "season_id", None)
                            if (
                                cid_direct in valid_contest_ids
                                and _entry_type_for_contest(cid_direct) == expected_type
                            ):
                                contested_ids.add(cid_direct)
                                continue
                            for _s in unique_seasons.values():
                                resolved = contestant_ep._resolve_contest_for_contestant_vote(
                                    db, uc, _s
                                )
                                if (
                                    resolved
                                    and resolved.id in valid_contest_ids
                                    and _entry_type_for_contest(resolved.id) == expected_type
                                ):
                                    contested_ids.add(resolved.id)
                                    break
                        user_contested_contest_ids = contested_ids
                except Exception as e:
                    logger.warning(f"Error batch-checking user participation for round {round_id}: {str(e)}")

            # Build contest data
            for contest in paginated_contests:
                try:
                    # Use pre-calculated participant count (already computed for sorting)
                    participant_count = contest_participant_counts.get(contest.id, 0)
                    # Strict per-contest check: only true when the user has already contested THIS contest.
                    is_contesting = contest.id in user_contested_contest_ids
                    contest_mode_value = _normalize_contest_mode(getattr(contest, 'contest_mode', 'participation'))
                    display_level = _contest_card_level_for_round(
                        db,
                        round_obj,
                        contest,
                        contest_mode_value,
                    )
                    
                    contest_data = {
                        "id": contest.id,
                        "name": contest.name,
                        "description": getattr(contest, 'description', None),
                        "contest_type": getattr(contest, 'contest_type', None),
                        "cover_image_url": getattr(contest, 'cover_image_url', None),
                        "level": display_level,
                        "participants_count": participant_count,
                        "votes_count": 0,
                        "image_url": getattr(contest, 'image_url', None),
                        "created_at": getattr(contest, 'created_at', None),
                        "updated_at": getattr(contest, 'updated_at', None),
                        "contest_mode": contest_mode_value,
                        "current_user_contesting": bool(is_contesting)  # Explicitly convert to bool
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
        result["is_voting_open"] = _effective_is_voting_open(r_data, round_obj)

        return result
        
    except Exception as e:
        logger.error(f"Error in _enrich_round_data: {str(e)}", exc_info=True)
        return None


@router.get("/{id}", response_model=round_schema.RoundWithStats)
def read_round(
    *,
    db: Session = Depends(deps.get_db),
    id: int,
):
    """Get a single round by ID with enriched stats"""
    db_round = db.query(Round).filter(Round.id == id).first()
    if not db_round:
        raise HTTPException(status_code=404, detail=f"Round {id} not found")
    # Convert ORM object to dict for _enrich_round_data
    round_dict = {
        "id": db_round.id,
        "name": db_round.name,
        "status": db_round.status,
        "is_submission_open": db_round.is_submission_open,
        "is_voting_open": db_round.is_voting_open,
        "current_season_level": db_round.current_season_level,
        "submission_start_date": db_round.submission_start_date,
        "submission_end_date": db_round.submission_end_date,
        "voting_start_date": db_round.voting_start_date,
        "voting_end_date": db_round.voting_end_date,
        "city_season_start_date": getattr(db_round, 'city_season_start_date', None),
        "city_season_end_date": getattr(db_round, 'city_season_end_date', None),
        "country_season_start_date": getattr(db_round, 'country_season_start_date', None),
        "country_season_end_date": getattr(db_round, 'country_season_end_date', None),
        "regional_start_date": getattr(db_round, 'regional_start_date', None),
        "regional_end_date": getattr(db_round, 'regional_end_date', None),
        "continental_start_date": getattr(db_round, 'continental_start_date', None),
        "continental_end_date": getattr(db_round, 'continental_end_date', None),
        "global_start_date": getattr(db_round, 'global_start_date', None),
        "global_end_date": getattr(db_round, 'global_end_date', None),
        "contest_id": db_round.contest_id,
        "created_at": db_round.created_at,
        "updated_at": db_round.updated_at,
    }
    return _enrich_round_data(
        db, round_dict,
        user_id=None,
        contest_mode=None,
        contest_level=None,
        filter_country=None,
        filter_region=None,
        filter_continent=None,
        search_term=None,
        contest_limit=50,
        contest_skip=0,
    )


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
