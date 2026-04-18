"""
Endpoints pour gérer les migrations de saisons
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, select

from app.api import deps
from app.services.season_migration import season_migration_service
from app.tasks.season_migration import (
    process_season_migrations,
    migrate_contest_to_city,
    promote_contest_level
)
from app.models.user import User
from app.models.round import Round, RoundStatus, round_contests
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, SeasonLevel
from app.models.voting import ContestantVoting
from app.models.contests import Contestant, ContestantSeason

router = APIRouter()


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


def _normalized_country_candidates(contestant):
    values = []
    # 1) contestant profile country (most direct when present)
    if getattr(contestant, "country", None):
        values.append((contestant.country or "").strip().lower())
    # 2) nomination-specific origin field
    if getattr(contestant, "nominator_country", None):
        values.append((contestant.nominator_country or "").strip().lower())
    # 3) author account country as final fallback
    if getattr(contestant, "user", None) and getattr(contestant.user, "country", None):
        values.append((contestant.user.country or "").strip().lower())
    return [v for v in values if v]


_LEVEL_MAP = {
    "city": SeasonLevel.CITY,
    "country": SeasonLevel.COUNTRY,
    "regional": SeasonLevel.REGIONAL,
    "continent": SeasonLevel.CONTINENT,
    "global": SeasonLevel.GLOBAL,
}

_LEVEL_TO_LOCATION_FIELD = {
    SeasonLevel.CITY: "city",
    SeasonLevel.COUNTRY: "country",
    SeasonLevel.REGIONAL: "region",
    SeasonLevel.CONTINENT: "continent",
    SeasonLevel.GLOBAL: None,  # no grouping; treat all contestants as one pool
}


@router.get("/top-high5")
def get_top_high5_by_country(
    round_id: int | None = Query(default=None),
    country: str | None = Query(default=None),
    level: str | None = Query(
        default=None,
        description="Stage filter: city | country | regional | continent | global. Defaults to country.",
    ),
    current_user: User | None = Depends(deps.get_current_active_user_optional),
):
    """
    Read-only preview for Top High5 per stage (nomination contests).

    - `level=country` (default): top 5 for the selected country.
    - `level=city` / `regional` / `continent`: top 5 grouped by that location
      within the selected country. One leaderboard per distinct location value.
    - `level=global`: top 5 worldwide, no country filter.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Resolve the requested stage; default to COUNTRY for backward compatibility.
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

        def _diagnostics_for_round(rnd: Round):
            # Active contest-season links per level
            counts = (
                db.query(ContestSeason.level, func.count())
                .join(ContestSeasonLink, ContestSeasonLink.season_id == ContestSeason.id)
                .filter(ContestSeason.round_id == rnd.id)
                .filter(ContestSeasonLink.is_active == True)
                .group_by(ContestSeason.level)
                .all()
            )
            active_links_by_level = {str(level.value if hasattr(level, "value") else level): int(cnt) for level, cnt in counts}

            # Active nomination contests in this round
            contest_ids = [
                r[0]
                for r in db.execute(
                    select(round_contests.c.contest_id).where(round_contests.c.round_id == rnd.id)
                ).fetchall()
            ]
            nomination_contests = (
                db.query(Contest)
                .filter(Contest.id.in_(contest_ids))
                .filter(Contest.contest_mode == "nomination")
                .count()
                if contest_ids
                else 0
            )

            return {
                "round_id": rnd.id,
                "round_name": rnd.name,
                "country": selected_country,
                "country_variants": sorted(list(variants)),
                "active_links_by_level": active_links_by_level,
                "nomination_contests_in_round": int(nomination_contests),
                "requested_level": requested_level.value,
            }

        def _build_for_round(rnd: Round):
            contest_ids = [
                r[0]
                for r in db.execute(
                    select(round_contests.c.contest_id).where(round_contests.c.round_id == rnd.id)
                ).fetchall()
            ]
            if not contest_ids:
                return []

            nomination_contests = (
                db.query(Contest)
                .filter(Contest.id.in_(contest_ids))
                .filter(Contest.contest_mode == "nomination")
                .order_by(Contest.id.asc())
                .all()
            )

            contests_out = []
            for contest in nomination_contests:
                link = (
                    db.query(ContestSeasonLink, ContestSeason)
                    .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                    .filter(
                        ContestSeasonLink.contest_id == contest.id,
                        ContestSeasonLink.is_active == True,
                        ContestSeason.round_id == rnd.id,
                    )
                    .first()
                )
                if not link:
                    continue
                _, season = link

                # Only show contests whose active season matches the requested level.
                if season.level != requested_level:
                    continue

                nxt = _next_level(season.level)
                location_field = _LEVEL_TO_LOCATION_FIELD.get(season.level)

                # Build one or more "contest leaderboards". For country/global there is
                # a single leaderboard; for city/regional/continent we emit one per
                # distinct location value within the selected country.
                per_location_groups: list[tuple[str | None, list]] = []

                if season.level == SeasonLevel.GLOBAL:
                    # Global: no country filter, no grouping. Take all qualified contestants
                    # in the season for this contest and rank them together.
                    all_contestants = (
                        db.query(Contestant)
                        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
                        .filter(
                            and_(
                                ContestantSeason.season_id == season.id,
                                ContestantSeason.is_active == True,
                                Contestant.is_active == True,
                                Contestant.is_deleted == False,
                                Contestant.season_id == contest.id,
                            )
                        )
                        .all()
                    )
                    if all_contestants:
                        per_location_groups.append(("Global", all_contestants))

                elif season.level == SeasonLevel.COUNTRY:
                    # Canonical grouping by country. Match the user-selected country
                    # against the group keys (case / alias insensitive).
                    grouped = season_migration_service.get_top_contestants_by_location(
                        db,
                        season.id,
                        "country",
                        contest_id=contest.id,
                        limit=None,
                        stage_id=None,
                        diagnostics=False,
                    )
                    matched_key = None
                    for key in grouped.keys():
                        if (key or "").strip().lower() in variants:
                            matched_key = key
                            break
                    if matched_key is not None:
                        per_location_groups.append((matched_key, grouped.get(matched_key, [])))
                    else:
                        # Fallback: rebuild snapshot from active season contestants
                        # whose country matches the search (handles seasons where no
                        # canonical grouping key landed on the exact label).
                        season_contestants = (
                            db.query(Contestant)
                            .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
                            .filter(
                                and_(
                                    ContestantSeason.season_id == season.id,
                                    ContestantSeason.is_active == True,
                                    Contestant.is_active == True,
                                    Contestant.is_deleted == False,
                                    Contestant.season_id == contest.id,
                                )
                            )
                            .all()
                        )
                        filtered = [
                            c for c in season_contestants
                            if any(v in variants for v in _normalized_country_candidates(c))
                        ]
                        if filtered:
                            per_location_groups.append((selected_country, filtered))

                else:
                    # city / regional / continent: group by location_field, then keep
                    # only groups whose contestants are in the selected country.
                    grouped = season_migration_service.get_top_contestants_by_location(
                        db,
                        season.id,
                        location_field,
                        contest_id=contest.id,
                        limit=None,
                        stage_id=None,
                        diagnostics=False,
                    )
                    for key, members in grouped.items():
                        if not key:
                            continue
                        country_matching_members = [
                            c for c in members
                            if any(v in variants for v in _normalized_country_candidates(c))
                        ]
                        if country_matching_members:
                            per_location_groups.append((key, country_matching_members))

                if not per_location_groups:
                    continue

                # Render one contest_out per location group. Maintains a stable
                # alphabetical order so the dashboard lists them predictably.
                per_location_groups.sort(key=lambda kv: (kv[0] or "").lower())

                for matched_key, ranked in per_location_groups:
                    rows = _build_rows_for_group(db, contest, season, ranked)
                    ranking_scope = (
                        "global" if season.level == SeasonLevel.GLOBAL else
                        "country_group" if season.level == SeasonLevel.COUNTRY else
                        f"{location_field}_in_country"
                    )
                    contests_out.append(
                        {
                            "contest_id": contest.id,
                            "contest_name": contest.name,
                            "category_id": contest.category_id,
                            "category_name": (contest.category.name if contest.category else None),
                            "from_level": season.level.value,
                            "to_level": nxt.value if nxt else None,
                            "country_group": matched_key,
                            "ranking_scope": ranking_scope,
                            "promotion_limit": 5,
                            "rows": rows,
                        }
                    )
            return contests_out

        def _build_rows_for_group(db, contest, season, ranked):
            """Compute stars/engagement and produce ranked rows for a single group."""
            contestant_ids = [c.id for c in ranked]
            points_by_id: dict[int, int] = {}
            engagement_by_id: dict[int, dict] = {}
            if contestant_ids:
                points_rows = (
                    db.query(
                        ContestantVoting.contestant_id,
                        func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
                    )
                    .filter(
                        and_(
                            ContestantVoting.season_id == season.id,
                            ContestantVoting.contest_id == contest.id,
                            ContestantVoting.contestant_id.in_(contestant_ids),
                        )
                    )
                    .group_by(ContestantVoting.contestant_id)
                    .all()
                )
                points_by_id = {r.contestant_id: int(r.total_points or 0) for r in points_rows}
                if not points_by_id:
                    legacy_rows = (
                        db.query(
                            ContestantVoting.contestant_id,
                            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
                        )
                        .filter(
                            and_(
                                ContestantVoting.contest_id == contest.id,
                                ContestantVoting.contestant_id.in_(contestant_ids),
                            )
                        )
                        .group_by(ContestantVoting.contestant_id)
                        .all()
                    )
                    points_by_id = {r.contestant_id: int(r.total_points or 0) for r in legacy_rows}
                engagement_by_id = season_migration_service._engagement_by_contestant(db, contestant_ids)

            # Canonical winner order: stars desc -> shares -> likes -> comments ->
            # views -> earliest contestant. Kept in sync with the rendered columns.
            sorted_ranked = sorted(
                ranked,
                key=lambda c: (
                    points_by_id.get(c.id, 0),
                    engagement_by_id.get(c.id, {}).get("shares", 0),
                    engagement_by_id.get(c.id, {}).get("likes", 0),
                    engagement_by_id.get(c.id, {}).get("comments", 0),
                    engagement_by_id.get(c.id, {}).get("views", 0),
                    -(c.id or 0),
                ),
                reverse=True,
            )

            rows = []
            for idx, c in enumerate(sorted_ranked, start=1):
                author_name = None
                author_email = None
                if c.user:
                    author_name = c.user.full_name or c.user.username or c.user.email
                    author_email = c.user.email
                e = engagement_by_id.get(c.id, {})
                rows.append(
                    {
                        "rank": idx,
                        "migrates_next_stage": idx <= 5,
                        "contestant_id": c.id,
                        "contestant_title": c.title,
                        "author_name": author_name,
                        "author_email": author_email,
                        "city": c.city,
                        "country": c.country,
                        "region": c.region,
                        "continent": c.continent,
                        "stars_points": points_by_id.get(c.id, 0),
                        "shares": e.get("shares", 0),
                        "likes": e.get("likes", 0),
                        "comments": e.get("comments", 0),
                        "views": e.get("views", 0),
                    }
                )
            return rows

        if round_id is not None:
            rnd = db.query(Round).filter(Round.id == round_id).first()
            if not rnd:
                raise HTTPException(status_code=404, detail=f"Round id={round_id} not found")
            contests_out = _build_for_round(rnd)
            return {
                "round_id": rnd.id,
                "round_name": rnd.name,
                "country": selected_country,
                "level": requested_level.value,
                "contests": contests_out,
                "fallback_applied": False,
                "diagnostics": _diagnostics_for_round(rnd),
            }

        candidate_rounds = (
            db.query(Round)
            .filter(Round.status != RoundStatus.CANCELLED)
            .order_by(Round.id.desc())
            .all()
        )
        if not candidate_rounds:
            raise HTTPException(status_code=404, detail="No available rounds")

        # Prioritize rounds currently open for voting (business expectation: show current voting round first).
        voting_open_rounds = [r for r in candidate_rounds if bool(r.is_voting_open)]
        search_rounds = voting_open_rounds + [r for r in candidate_rounds if not bool(r.is_voting_open)]

        chosen_round = candidate_rounds[0]
        chosen_contests = []
        fallback_applied = False
        for idx, rnd in enumerate(search_rounds):
            contests_out = _build_for_round(rnd)
            if contests_out:
                chosen_round = rnd
                chosen_contests = contests_out
                fallback_applied = idx != 0
                break

        return {
            "round_id": chosen_round.id,
            "round_name": chosen_round.name,
            "country": selected_country,
            "level": requested_level.value,
            "contests": chosen_contests,
            "fallback_applied": fallback_applied,
            "diagnostics": _diagnostics_for_round(chosen_round),
        }
    finally:
        db.close()


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

