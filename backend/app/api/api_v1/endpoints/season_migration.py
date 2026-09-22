"""
Endpoints pour gérer les migrations de saisons
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import joinedload
from functools import wraps
import inspect
import threading

from app.api import deps
from app.services.season_migration import SeasonMigrationService, season_migration_service
from app.services.top_high5_live import resolve_live_top_high5
from app.tasks.season_migration import (
    process_season_migrations,
    migrate_contest_to_city,
    promote_contest_level
)
from app.models.user import User
from app.models.round import Round, RoundStatus
from app.models.contest import Contest
from app.models.contests import SeasonLevel, TopHigh5Result, Contestant
from sqlalchemy import text, and_, or_

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

# The Round column that carries the *actual calendar close date* for each
# level's voting -- the one authoritative "did this cohort's voting for this
# level really finish" signal. Neither TopHigh5Result.round_id (a bare
# autoincrement PK -- an admin can generate a round for an out-of-sequence
# past month via POST /rounds/generate-monthly?year=&month=) nor
# TopHigh5Result.created_at (stamped at INSERT time, and repeatedly proven to
# be rewritten out of order by backfill/repair maintenance) can be trusted
# for this; the Round's own level-specific end date is what the rest of the
# system's calendar actually means by "this level closed".
#
# IMPORTANT: this is PARTICIPATION's calendar only (Country=M+2, Regional=
# M+3, Continental=M+4, Global=M+5 -- see generate_monthly_rounds.py).
# Nomination mode has its own, independent, earlier calendar (Country=M+1,
# Regional=M+2, Continental=M+3) that is never written to these columns.
# Gating a nomination result on these columns directly (as the resolver did
# before the 2026 mode-aware fix) hides real, already-frozen nomination
# results for up to a month -- see _level_close_date_for_mode below, which
# is mode-aware and is what COUNTRY/REGIONAL/CONTINENT auto-resolution now
# actually uses. This dict remains the source of truth for PARTICIPATION,
# and is still used as-is for: an explicit ?round_id= request, CITY
# (always empty), and GLOBAL (terminal level, verified against live
# production data during the 2026 audit to not exhibit the same mismatch --
# preserved untouched rather than refactored for symmetry).
_LEVEL_END_DATE_COL = {
    SeasonLevel.COUNTRY: Round.country_season_end_date,
    SeasonLevel.REGIONAL: Round.regional_end_date,
    SeasonLevel.CONTINENT: Round.continental_end_date,
    SeasonLevel.GLOBAL: Round.global_end_date,
}
_LEVEL_END_DATE_ATTR = {
    SeasonLevel.COUNTRY: "country_season_end_date",
    SeasonLevel.REGIONAL: "regional_end_date",
    SeasonLevel.CONTINENT: "continental_end_date",
    SeasonLevel.GLOBAL: "global_end_date",
}


def _level_close_date_for_mode(round_obj: Round, level: SeasonLevel, contest_mode: str):
    """
    Authoritative "this level's voting closed" date for one Round, aware of
    contest mode. Participation uses the Round's own shared calendar
    columns (_LEVEL_END_DATE_ATTR); nomination uses its own, independent,
    earlier calendar (SeasonMigrationService._nomination_vote_close_date_for_level)
    computed from the Round's submission month -- never the shared columns,
    which hold participation's later dates for the very same Round.
    """
    mode = (contest_mode or "").strip().lower()
    if mode == "nomination":
        return SeasonMigrationService._nomination_vote_close_date_for_level(round_obj, level)
    attr = _LEVEL_END_DATE_ATTR.get(level)
    if attr is None:
        return None
    return getattr(round_obj, attr, None)


def _level_result_eligible(round_obj: Round, level: SeasonLevel, contest_mode: str, today: date) -> bool:
    """True when a frozen result at this (round, level, mode) is safe to display."""
    # A CANCELLED round (e.g. a duplicate-calendar-identity round created
    # and then cancelled -- production has had several, see round-guard
    # protections in season_migration.py) must never be shown as a source
    # of truth, regardless of what its close-date columns say. Found during
    # the 2026-09-22 completed-stage audit: currently inert in production
    # (zero TopHigh5Result rows are attached to any cancelled round today),
    # but the prior code had no explicit guard against it ever happening.
    if round_obj.status == RoundStatus.CANCELLED:
        return False
    close = _level_close_date_for_mode(round_obj, level, contest_mode)
    if close is not None:
        return close <= today
    # Legacy rows with no stored end date: fall back to the round's own
    # completion status -- identical fallback to the original resolver.
    return round_obj.status == RoundStatus.COMPLETED


def _apply_country_level_filters(rows: list, variants: set) -> list:
    """COUNTRY-level jurisdiction filter, plus the existing Singeli/Tanzania override."""
    out = [r for r in rows if (r.jurisdiction or "").strip().lower() in variants]
    out = [
        r for r in out
        if not (r.contest_id == 17 and any(v in variants for v in {"tanzania", "tz"}))
    ]
    return out


def _apply_regional_level_filters(rows: list, selected_country: str) -> list:
    """REGIONAL-level jurisdiction filter: only the requester's own regional pool."""
    selected_pool_id = SeasonMigrationService.regional_pool_id_for_raw_country(selected_country)
    if selected_pool_id is None:
        return rows
    return [
        r for r in rows
        if SeasonMigrationService.regional_pool_id_for_region_label(r.jurisdiction) == selected_pool_id
    ]


def _build_contests_out(groups: dict, requested_level: SeasonLevel, *, include_round_fields: bool = False) -> list:
    """
    Shared response-row builder. `groups` maps (contest_id, jurisdiction) ->
    list[TopHigh5Result], all rows in one group already scoped to a single
    source round by the caller.
    """
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
        entry = {
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
        if include_round_fields:
            src_round = group_rows[0].round
            entry["round_id"] = src_round.id if src_round else group_rows[0].round_id
            entry["round_name"] = src_round.name if src_round else None
            entry["contest_mode"] = (getattr(contest, "contest_mode", "") or "").strip().lower()
        contests_out.append(entry)
    contests_out.sort(key=lambda c: (c["country_group"] or "").lower())
    return contests_out


def _get_top_high5_single_round(
    db, *, round_id, requested_level: SeasonLevel, selected_country: str, variants: set, today: date,
) -> dict:
    """
    Original (pre-2026-mode-aware-fix) single-round resolver, preserved
    unchanged. Used for: an explicit ?round_id= request (the caller is
    being explicit, no eligibility gating needed), CITY (always empty), and
    GLOBAL (terminal level -- verified against live production data to NOT
    exhibit the participation/nomination calendar mismatch; preserved
    as-is rather than refactored for symmetry, per design decision).
    """
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
        #
        # "Latest" must mean the most recently *closed* calendar cohort
        # for this level -- never merely the most recently written row.
        # Neither `round_id` (an admin can backfill a past month's round
        # out of numeric sequence via /rounds/generate-monthly) nor
        # `created_at` (repeatedly rewritten out of order by
        # backfill_top_high5_results.py / repair_continent_top_high5.py)
        # is safe here. The Round's own level-specific end date is the
        # actual calendar signal the rest of the system means by "this
        # level's voting closed" -- and, proven against production data,
        # a frozen row existing is *not* by itself proof the level really
        # closed (maintenance tooling has written premature CONTINENT
        # rows for a round still 9 days from its own continental close).
        # So eligibility is gated on the date, not just sorted by it.
        #
        # A handful of legacy rounds (e.g. round 3) have this date column
        # NULL despite being genuinely finished (`Round.status ==
        # COMPLETED`) -- a population gap, not an open cohort -- so those
        # fall back to the status flag instead of being excluded.
        level_end_date = _LEVEL_END_DATE_COL[requested_level]
        latest = (
            db.query(TopHigh5Result.round_id)
            .join(Round, Round.id == TopHigh5Result.round_id)
            .filter(
                TopHigh5Result.level == requested_level,
                or_(
                    and_(level_end_date.isnot(None), level_end_date <= today),
                    and_(level_end_date.is_(None), Round.status == RoundStatus.COMPLETED),
                ),
            )
            .order_by(
                level_end_date.desc().nullslast(),
                TopHigh5Result.round_id.desc(),
                TopHigh5Result.created_at.desc(),
            )
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
        rows = _apply_country_level_filters(rows, variants)
    elif requested_level == SeasonLevel.REGIONAL:
        rows = _apply_regional_level_filters(rows, selected_country)
    # CONTINENT: no country-based filtering -- every continent pool that
    # has frozen results for this round is shown, matching prior behavior.

    groups: dict[tuple[int, str], list] = {}
    for r in rows:
        groups.setdefault((r.contest_id, r.jurisdiction), []).append(r)

    contests_out = _build_contests_out(groups, requested_level)

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


def _get_top_high5_mode_aware(
    db, *, requested_level: SeasonLevel, selected_country: str, variants: set, today: date,
) -> dict:
    """
    Not called by the default route since the 2026 derived-architecture
    change (see app.services.top_high5_live) -- the default path no longer
    reads top_high5_results at all. Kept, with its existing test coverage
    (test_top_high5_mode_aware_resolver.py) unmodified, as mode-aware
    frozen-snapshot resolution logic that predates and remains independent
    of the live derivation, in case a future explicit "historical mode-aware
    view" is ever needed; not wired into any current endpoint path.

    COUNTRY / REGIONAL / CONTINENT, auto-resolved (no explicit round_id):
    mode-aware round selection (2026 fix). Participation and nomination
    contests keep their own independent calendars -- there is no single
    "the round" for the whole response. Each (contest_id, jurisdiction)
    group independently picks the freshest round that is genuinely
    eligible under its own contest's mode (_level_result_eligible).

    Single bounded query (no N+1): every TopHigh5Result row at this level,
    across every round, with contest/contestant/round eager-loaded.
    Eligibility per (round_id, mode) is computed once and cached in a dict,
    not re-derived per row.
    """
    rows = (
        db.query(TopHigh5Result)
        .options(
            joinedload(TopHigh5Result.contest).joinedload(Contest.category),
            joinedload(TopHigh5Result.contestant).joinedload(Contestant.user),
            joinedload(TopHigh5Result.round),
        )
        .join(Contest, Contest.id == TopHigh5Result.contest_id)
        .filter(TopHigh5Result.level == requested_level)
        .all()
    )

    eligibility_cache: dict[tuple[int, str], bool] = {}

    def _eligible(row: "TopHigh5Result", mode: str) -> bool:
        key = (row.round_id, mode)
        cached = eligibility_cache.get(key)
        if cached is not None:
            return cached
        result = _level_result_eligible(row.round, requested_level, mode, today)
        eligibility_cache[key] = result
        return result

    candidate_rows = []
    for r in rows:
        mode = (getattr(r.contest, "contest_mode", "") or "").strip().lower()
        if _eligible(r, mode):
            candidate_rows.append(r)

    if requested_level == SeasonLevel.COUNTRY:
        candidate_rows = _apply_country_level_filters(candidate_rows, variants)
    elif requested_level == SeasonLevel.REGIONAL:
        candidate_rows = _apply_regional_level_filters(candidate_rows, selected_country)
    # CONTINENT: no jurisdiction filtering, matches original behavior.

    if not candidate_rows:
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
                "resolution": "mode_aware",
            },
        }

    # Per (contest_id, jurisdiction): keep only the freshest eligible round's rows.
    best_round: dict[tuple[int, str], int] = {}
    for r in candidate_rows:
        key = (r.contest_id, r.jurisdiction)
        if key not in best_round or r.round_id > best_round[key]:
            best_round[key] = r.round_id

    groups: dict[tuple[int, str], list] = {}
    for r in candidate_rows:
        key = (r.contest_id, r.jurisdiction)
        if r.round_id != best_round[key]:
            continue
        groups.setdefault(key, []).append(r)

    contests_out = _build_contests_out(groups, requested_level, include_round_fields=True)

    rounds_used = sorted(set(best_round.values()), reverse=True)
    top_round = db.query(Round).filter(Round.id == rounds_used[0]).first() if rounds_used else None

    return {
        "round_id": top_round.id if top_round else None,
        "round_name": top_round.name if top_round else None,
        "country": selected_country,
        "level": requested_level.value,
        "contests": contests_out,
        "fallback_applied": False,
        "diagnostics": {
            "round_id": top_round.id if top_round else None,
            "round_name": top_round.name if top_round else None,
            "country": selected_country,
            "requested_level": requested_level.value,
            "source": "frozen",
            "resolution": "mode_aware",
            "distinct_rounds_represented": rounds_used,
        },
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
    Top High5: the current top 5 per stage, DERIVED LIVE from authoritative
    lifecycle + cohort membership + voting/ranking data (see
    app.services.top_high5_live for the full architecture and rationale).
    `top_high5_results` (the historical frozen snapshot table) is no longer
    in the path of this default display -- it is never read here. A
    missing or stale frozen snapshot can no longer hide or corrupt a
    current, otherwise-valid result.

    - `level=country` (default): top 5 for the selected country.
    - `level=regional` / `continent`: top 5 for the country's regional
      voting pool / one leaderboard per continent.
    - `level=city`: top 5 per city (participation only -- nomination has no
      City stage and never appears here).
    - `level=global`: top 5 worldwide, no country filter.

    A level/round whose voting hasn't closed yet is never shown, so it
    returns `contests: []` for that group -- that means "not finalized
    yet", not an error; an in-progress stage is never displayed as final.

    Each contest resolves independently to its own freshest fully-completed
    round under its own contest_mode's lifecycle calendar (participation
    and nomination each have their own offsets -- see
    app.services.top_high5_live). There is therefore no longer one single
    "the round" for the whole response; each card also carries its own
    `round_id` / `round_name` / `contest_mode`.

    An explicit `?round_id=` bypasses all of this and reads the frozen
    historical snapshot for that exact round instead (see
    _get_top_high5_single_round) -- this is the one remaining consumer of
    `top_high5_results` for the live API, preserved for explicit
    historical-round viewing so existing links/features keep working.
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
        today = date.today()

        if round_id is not None:
            # Explicit historical-round request: read the frozen snapshot
            # for that exact round, unchanged. The only remaining default
            # consumer of top_high5_results.
            return _get_top_high5_single_round(
                db,
                round_id=round_id,
                requested_level=requested_level,
                selected_country=selected_country,
                variants=variants,
                today=today,
            )

        return resolve_live_top_high5(
            db,
            level=requested_level,
            selected_country=selected_country,
            variants=variants,
            today=today,
        )
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

