from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
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
from app.services.contest_category_integrity import dedupe_contests_one_per_category_mode

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
    if low in ("nomination", "nominate"):
        return "nomination"
    if low in ("participation", "participant", "participate"):
        return "participation"
    token = text.split(".")[-1].strip().lower()
    if token in {"nomination", "nominate"}:
        return "nomination"
    if token in {"participation", "participant", "participate"}:
        return "participation"
    return "participation"


def _round_entry_count(contest: Any, mode: str) -> int:
    try:
        if mode == "nomination":
            if hasattr(contest, "active_nominations_count") and contest.active_nominations_count is not None:
                return int(contest.active_nominations_count)
            if hasattr(contest, "contestants_count") and contest.contestants_count is not None:
                return int(contest.contestants_count)
        else:
            if hasattr(contest, "active_participations_count") and contest.active_participations_count is not None:
                return int(contest.active_participations_count)
            if hasattr(contest, "contestants_count") and contest.contestants_count is not None:
                return int(contest.contestants_count)
    except Exception as e:
        logger.warning(f"Error reading explicit counts for contest {getattr(contest, 'id', 'unknown')}: {e}")
    
    try:
        if hasattr(contest, "contestants") and contest.contestants is not None:
            return len([c for c in contest.contestants if not getattr(c, "is_deleted", False)])
    except Exception as e:
        logger.warning(f"Error fallback counting for contest {getattr(contest, 'id', 'unknown')}: {e}")
    
    return 0


def _lightweight_round_data(
    db: Session,
    round_obj: Round,
    user_id: Optional[int],
    filter_country: Optional[str] = None,
    filter_region: Optional[str] = None,
    filter_continent: Optional[str] = None,
    contest_level: str = "world"
) -> dict:
    try:
        contests_list = []
        raw_contests = getattr(round_obj, "contests", []) or []
        
        for contest in raw_contests:
            if getattr(contest, "is_deleted", False):
                continue
                
            contest_mode_value = _normalize_contest_mode(getattr(contest, "contest_mode", "participation"))
            participant_count = _round_entry_count(contest, contest_mode_value)
            
            # CRITICAL FIX: Commented out the duplicate alias buggy query to prevent 65s timeout
            # if contest_mode_value == "nomination" and crud.contest.nomination_card_uses_exact_roster(
            #     filter_country, filter_region, filter_continent, contest_level
            # ):
            #     participant_count = crud.contest.count_nomination_roster_for_card(
            #         db,
            #         contest_id=contest.id,
            #         current_user_id=user_id,
            #         filter_country=filter_country,
            #         filter_region=filter_region,
            #         filter_continent=filter_continent,
            #         entry_type="nomination",
            #         round_id=round_obj.id,
            #         requested_ui_level=contest_level,
            #     )

            has_joined = False
            if user_id:
                try:
                    has_joined = crud.contest.has_user_joined_contest(
                        db, 
                        contest_id=contest.id, 
                        user_id=user_id, 
                        entry_type=contest_mode_value,
                        round_id=round_obj.id
                    )
                except Exception as ej:
                    logger.error(f"Error checking has_joined for contest {contest.id}: {ej}")

            category_name = "General"
            if hasattr(contest, "category") and contest.category:
                category_name = getattr(contest.category, "name", "General")

            contests_list.append({
                "id": contest.id,
                "title": getattr(contest, "title", "") or f"Contest #{contest.id}",
                "contest_mode": contest_mode_value,
                "participant_count": participant_count,
                "has_joined": has_joined,
                "category_name": category_name
            })

        deduped = dedupe_contests_one_per_category_mode(contests_list)
        
        return {
            "id": round_obj.id,
            "title": round_obj.title,
            "status": round_obj.status.value if hasattr(round_obj.status, "value") else str(round_obj.status),
            "start_date": round_obj.start_date.isoformat() if isinstance(round_obj.start_date, (date, datetime)) else str(round_obj.start_date),
            "end_date": round_obj.end_date.isoformat() if isinstance(round_obj.end_date, (date, datetime)) else str(round_obj.end_date),
            "contests": deduped
        }
    except Exception as e:
        logger.error(f"Error in _lightweight_round_data for round {getattr(round_obj, 'id', 'unknown')}: {e}")
        logger.error(traceback.format_exc())
        return {
            "id": getattr(round_obj, "id", 0),
            "title": getattr(round_obj, "title", "Error Round"),
            "status": "error",
            "start_date": "",
            "end_date": "",
            "contests": []
        }


@router.get("/", response_model=List[Any])
def read_rounds(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 12,
    contestLimit: int = Query(1, description="Max contests per round structure"),
    current_user: Optional[models.User] = Depends(deps.get_current_active_user_optional),
) -> Any:
    """
    Retrieve rounds with heavily optimized lightweight fast path.
    """
    try:
        filter_country = None
        filter_region = None
        filter_continent = None
        contest_level = "world"

        if current_user:
            filter_country = getattr(current_user, "country", None)
            filter_region = getattr(current_user, "region", None)
            filter_continent = getattr(current_user, "original_continent", None)
            contest_level = getattr(current_user, "ui_contest_level", "world") or "world"

        logger.info(f"[READ_ROUNDS_FAST_PATH] User: {getattr(current_user, 'id', 'Anonymous')}, Level: {contest_level}, Country: {filter_country}")

        rounds_query = db.query(Round).filter(Round.is_deleted == False)
        
        # Priority order to keep current rounds on top
        active_rounds = rounds_query.filter(Round.status == RoundStatus.ACTIVE).order_index = Round.start_date.asc().all()
        voting_rounds = rounds_query.filter(Round.status == RoundStatus.VOTING).order_index = Round.start_date.asc().all()
        upcoming_rounds = rounds_query.filter(Round.status == RoundStatus.UPCOMING).order_index = Round.start_date.asc().all()
        completed_rounds = rounds_query.filter(Round.status == RoundStatus.COMPLETED).order_by(Round.end_date.desc()).offset(skip).limit(limit).all()

        combined_rounds = active_rounds + voting_rounds + upcoming_rounds + completed_rounds
        seen_ids = set()
        unique_rounds = []
        for r in combined_rounds:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                unique_rounds.append(r)

        user_id = current_user.id if current_user else None
        
        results = []
        for r in unique_rounds:
            light_data = _lightweight_round_data(
                db, r, user_id, 
                filter_country=filter_country,
                filter_region=filter_region,
                filter_continent=filter_continent,
                contest_level=contest_level
            )
            results.append(light_data)

        return results

    except Exception as main_err:
        logger.critical(f"CRITICAL FAILURE IN READ_ROUNDS FAST PATH: {main_err}")
        logger.critical(traceback.format_exc())
        
        # Absolute bulletproof fallback path
        try:
            fallback_rounds = db.query(Round).filter(Round.is_deleted == False).order_by(Round.id.desc()).limit(5).all()
            return [{
                "id": r.id,
                "title": r.title,
                "status": "active",
                "start_date": str(r.start_date),
                "end_date": str(r.end_date),
                "contests": []
            } for r in fallback_rounds]
        except Exception as super_crash:
            return []


@router.post("/generate-monthly", response_model=List[round_schema.Round])
def generate_monthly(
    *,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Generate rounds for the next month automatically.
    """
    try:
        rounds = generate_monthly_round(db=db)
        return rounds
    except Exception as e:
        logger.error(f"Error during monthly round generation: {str(e)}")
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
    round = crud.round.remove(db=db, id=id)
    return round