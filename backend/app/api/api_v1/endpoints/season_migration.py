"""
Endpoints pour gérer les migrations de saisons
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import joinedload
from functools import wraps
import inspect
import threading

from app.api import deps
from app.services.season_migration import SeasonMigrationService, season_migration_service
from app.tasks.season_migration import (
    process_season_migrations,
    migrate_contest_to_city,
    promote_contest_level
)
from app.models.user import User
from app.models.round import Round
from app.models.contest import Contest
from app.models.contests import SeasonLevel, TopHigh5Result, Contestant
from sqlalchemy import text

router = APIRouter()

_top_high5_flights_lock = threading.Lock()
_top_high5_flights: dict[tuple, dict] = {}


def _singleflight_top_high5(func):
    """Coalesce identical in-process leaderboard requests without caching stale data."""
    signature = inspect.signature(func)

    @wraps(func)
    def wrapper(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        values = bound.arguments
        response = values.get("response")
        if response is not None:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        current_user = values.get("current_user")
        requested_country = str(
            values.get("country")
            or getattr(current_user, "country", None)
            or ""
        ).strip().lower()
        key = (
            values.get("round_id"),
            requested_country,
            str(values.get("level") or "country").strip().lower(),
        )

        with _top_high5_flights_lock:
            flight = _top_high5_flights.get(key)
            leader = flight is None
            if leader:
                flight = {"event": threading.Event(), "result": None, "error": None}
                _top_high5_flights[key] = flight

        if not leader:
            # The endpoint has an 8-second DB statement limit. Fail open after
            # twelve seconds if the leader is stuck outside the database.
            if not flight["event"].wait(timeout=12):
                return func(*args, **kwargs)
            if flight["error"] is not None:
                raise flight["error"]
            return flight["result"]

        try:
            flight["result"] = func(*args, **kwargs)
            return flight["result"]
        except BaseException as exc:
            flight["error"] = exc
            raise
        finally:
            with _top_high5_flights_lock:
                flight["event"].set()
                _top_high5_flights.pop(key, None)

    return wrapper


def _next_level(level: SeasonLevel):
    order = [
        SeasonLevel.CITY,
        SeasonLevel.COUNTRY,
        SeasonLevel.REGIONAL,
        SeasonLevel.CONTINENT,
        SeasonLevel.GLOBAL,
    ]
    try:
        idx = order.index(level)
    except ValueError:
        return None
    return order[idx + 1] if idx < len(order) - 1 else None


def _country_variants(raw_country: str):
    raw = (raw_country or "").strip().lower()
    variants = {raw}
    alias_map = {
        "tanzania": "tz",
        "tz": "tanzania",
        "uganda": "ug",
        "ug": "uganda",
        "kenya": "ke",
        "ke": "kenya",
    }
    if raw in alias_map:
        variants.add(alias_map[raw])
    return variants


_LEVEL_MAP = {
    "city": SeasonLevel.CITY,
    "country": SeasonLevel.COUNTRY,
    "regional": SeasonLevel.REGIONAL,
    "continent": SeasonLevel.CONTINENT,
    "global": SeasonLevel.GLOBAL,
}


@router.get("/top-high5")
@_singleflight_top_high5
def get_top_high5_by_country(
    response: Response,
    round_id: int | None = Query(default=None),
    country: str | None = Query(default=None),
    level: str | None = Query(
        default=None,
        description="Stage filter: city | country | regional | continent | global. Defaults to country.",
    ),
    current_user: User | None = Depends(deps.get_current_active_user_optional),
):
    """
    Top High5: the finalized top 5 per stage, read from frozen historical
    results (top_high5_results) -- never recomputed from live votes.

    - `level=country` (default): top 5 for the selected country.
    - `level=regional` / `continent`: top 5 for the country's regional
      voting pool / one leaderboard per continent.
    - `level=global`: top 5 worldwide, no country filter.

    A level/round whose voting hasn't closed yet has no frozen rows, so it
    returns `contests: []` -- that means "not finalized yet", not an error;
    it must never fall back to live vote counts (see
    KALUTASOCIETY_TOP_HIGH5_FIX_DESIGN and the functional spec this
    implements).
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        try:
            db.execute(text("SET LOCAL statement_timeout = 8000"))
        except Exception:
            pass
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        requested_level = SeasonLevel.COUNTRY
        if level:
            parsed = _LEVEL_MAP.get(level.strip().lower())
            if parsed is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid level. Must be one of: city, country, regional, continent, global.",
                )
            requested_level = parsed

        is_global = requested_level == SeasonLevel.GLOBAL

        selected_country = (country or "").strip()
        if not is_global:
            if not selected_country and current_user:
                selected_country = (current_user.country or "").strip()
            if not selected_country:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Country is required (query ?country=... or authenticated user country).",
                )

        variants = _country_variants(selected_country) if selected_country else set()

        # Resolve which round to show.
        rnd: Round | None = None
        if round_id is not None:
            rnd = db.query(Round).filter(Round.id == round_id).first()
            if not rnd:
                raise HTTPException(status_code=404, detail="Round not found")
        elif requested_level != SeasonLevel.CITY:
            # Business rule: City Top High5 is reserved for participation flow
            # and is never displayed (see below) -- don't bother resolving a
            # round for it.
            latest = (
                db.query(TopHigh5Result.round_id)
                .filter(TopHigh5Result.level == requested_level)
                .order_by(TopHigh5Result.created_at.desc(), TopHigh5Result.round_id.desc())
                .first()
            )
            if latest:
                rnd = db.query(Round).filter(Round.id == latest[0]).first()

        if rnd is None:
            return {
                "round_id": None,
                "round_name": None,
                "country": selected_country,
                "level": requested_level.value,
                "contests": [],
                "fallback_applied": False,
                "diagnostics": {
                    "requested_level": requested_level.value,
                    "message": "No finalized Top High5 results exist yet for this level.",
                },
            }

        # Business rule (unchanged from before this rewrite): City Top High5
        # is reserved for the participation flow and never surfaced here.
        if requested_level == SeasonLevel.CITY:
            return {
                "round_id": rnd.id,
                "round_name": rnd.name,
                "country": selected_country,
                "level": requested_level.value,
                "contests": [],
                "fallback_applied": False,
                "diagnostics": {"requested_level": requested_level.value},
            }

        rows = (
            db.query(TopHigh5Result)
            .options(
                joinedload(TopHigh5Result.contest).joinedload(Contest.category),
                joinedload(TopHigh5Result.contestant).joinedload(Contestant.user),
            )
            .filter(
                TopHigh5Result.round_id == rnd.id,
                TopHigh5Result.level == requested_level,
            )
            .all()
        )

        if requested_level == SeasonLevel.GLOBAL:
            rows = [r for r in rows if r.jurisdiction == "Global"]
        elif requested_level == SeasonLevel.COUNTRY:
            rows = [r for r in rows if (r.jurisdiction or "").strip().lower() in variants]
            # Targeted business override requested by product: hide Singeli
            # category on Top High5 country view for Tanzania only.
            rows = [
                r
                for r in rows
                if not (
                    r.contest_id == 17
                    and any(v in variants for v in {"tanzania", "tz"})
                )
            ]
        elif requested_level == SeasonLevel.REGIONAL:
            selected_pool_id = SeasonMigrationService.regional_pool_id_for_raw_country(
                selected_country
            )
            rows = [
                r
                for r in rows
                if selected_pool_id is None
                or SeasonMigrationService.regional_pool_id_for_region_label(r.jurisdiction)
                == selected_pool_id
            ]
        # CONTINENT: no country-based filtering -- every continent pool that
        # has frozen results for this round is shown, matching prior behavior.

        groups: dict[tuple[int, str], list] = {}
        for r in rows:
            groups.setdefault((r.contest_id, r.jurisdiction), []).append(r)

        nxt = _next_level(requested_level)
        ranking_scope = (
            "global" if requested_level == SeasonLevel.GLOBAL
            else "country_group" if requested_level == SeasonLevel.COUNTRY
            else "regional_pool" if requested_level == SeasonLevel.REGIONAL
            else "continent_in_country"
        )

        contests_out = []
        for (contest_id, jurisdiction), group_rows in groups.items():
            group_rows.sort(key=lambda r: r.rank)
            contest = group_rows[0].contest
            contests_out.append(
                {
                    "contest_id": contest.id,
                    "contest_name": contest.name,
                    "category_id": contest.category_id,
                    "category_name": (contest.category.name if contest.category else None),
                    "from_level": requested_level.value,
                    "to_level": nxt.value if nxt else None,
                    "country_group": jurisdiction,
                    "ranking_scope": ranking_scope,
                    "promotion_limit": 5,
                    "rows": [_top_high5_row_dict(r) for r in group_rows],
                }
            )

        contests_out.sort(key=lambda c: (c["country_group"] or "").lower())

        return {
            "round_id": rnd.id,
            "round_name": rnd.name,
            "country": selected_country,
            "level": requested_level.value,
            "contests": contests_out,
            "fallback_applied": False,
            "diagnostics": {
                "round_id": rnd.id,
                "round_name": rnd.name,
                "country": selected_country,
                "requested_level": requested_level.value,
                "source": "frozen",
            },
        }
    finally:
        db.close()


def _top_high5_row_dict(r: "TopHigh5Result") -> dict:
    contestant = r.contestant
    author_name = None
    author_email = None
    if contestant.user:
        author_name = contestant.user.full_name or contestant.user.username or contestant.user.email
        author_email = contestant.user.email
    return {
        "rank": r.rank,
        "migrates_next_stage": bool(r.migrated),
        "contestant_id": contestant.id,
        "contestant_title": contestant.title,
        "author_name": author_name,
        "author_email": author_email,
        "city": contestant.city,
        "country": contestant.country,
        "region": contestant.region,
        "continent": contestant.continent,
        "stars_points": r.total_points,
        "votes_count": r.total_votes,
        "shares": r.shares,
        "likes": r.likes,
        "comments": r.comments,
        "views": r.views,
    }


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

