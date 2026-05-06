"""
Endpoints pour gérer les migrations de saisons
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, select
from datetime import date

from app.api import deps
from app.services.season_migration import SeasonMigrationService, season_migration_service
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


def _subtract_months(base: date, months: int) -> date:
    """Return `base` shifted backward by `months` calendar months."""
    y, m = base.year, base.month
    for _ in range(max(0, months)):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    day = min(base.day, 28)
    return date(y, m, day)


@router.get("/top-high5")
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
    Read-only preview for Top High5 per stage (nomination contests).

    - `level=country` (default): top 5 for the selected country.
    - `level=city` / `regional` / `continent`: top 5 grouped by that location
      within the selected country. One leaderboard per distinct location value.
    - `level=global`: top 5 worldwide, no country filter.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Prevent stale CDN/browser caches for rapidly-changing leaderboard data.
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

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
        today = date.today()

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
            # Business rule: City Top High5 is reserved for participation flow.
            # Nomination Top High5 should not expose city-level contestants for now.
            if requested_level == SeasonLevel.CITY:
                return []
            min_start = season_migration_service._nomination_min_start_for_level(rnd, requested_level)
            if min_start and today < min_start:
                return []

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
                        ContestSeason.level == requested_level,
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
                    ivc_variants = {"côte d'ivoire", "cote d'ivoire", "ivory coast", "ivory cost", "ci"}
                    strict_round_scope_for_country = any(v in ivc_variants for v in variants)
                    grouped = season_migration_service.get_top_contestants_by_location(
                        db,
                        season.id,
                        "country",
                        contest_id=contest.id,
                        limit=None,
                        stage_id=None,
                        diagnostics=False,
                        qualified_only=False,
                        strict_season_scope=True,
                    )
                    matched_key = None
                    for key in grouped.keys():
                        if (key or "").strip().lower() in variants:
                            matched_key = key
                            break
                    if matched_key is not None:
                        members = grouped.get(matched_key, [])
                        if strict_round_scope_for_country:
                            members = [c for c in members if getattr(c, "round_id", None) == rnd.id]
                        if members:
                            per_location_groups.append((matched_key, members))
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
                        if strict_round_scope_for_country:
                            filtered = [c for c in filtered if getattr(c, "round_id", None) == rnd.id]
                        if filtered:
                            per_location_groups.append((selected_country, filtered))

                else:
                    # city / regional / continent
                    grouped = season_migration_service.get_top_contestants_by_location(
                        db,
                        season.id,
                        location_field,
                        contest_id=contest.id,
                        limit=None,
                        stage_id=None,
                        diagnostics=False,
                        qualified_only=False,
                        strict_season_scope=True,
                    )
                    for key, members in grouped.items():
                        if not key:
                            continue
                        if season.level == SeasonLevel.REGIONAL:
                            # Regional winners must be ranked on the whole voting pool
                            # (East/West/Southern/...) rather than only one country.
                            pool_members = [
                                c for c in members
                                if SeasonMigrationService.same_regional_voting_pool(
                                    selected_country,
                                    (c.country or c.nominator_country),
                                ) is True
                            ]
                            if pool_members:
                                per_location_groups.append((key, pool_members))
                            continue

                        # city / continent keep country-scoped view as before
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
                        "regional_pool" if season.level == SeasonLevel.REGIONAL else
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

            # Regional leaderboard: one slot per nominator (user). Stale migrations can
            # leave two nominee rows for the same person in one category pool.
            if getattr(season, "level", None) == SeasonLevel.REGIONAL:
                seen_user_ids: set[int] = set()
                deduped: list = []
                for c in sorted_ranked:
                    uid = getattr(c, "user_id", None)
                    if uid is None:
                        deduped.append(c)
                        continue
                    if uid in seen_user_ids:
                        continue
                    seen_user_ids.add(uid)
                    deduped.append(c)
                sorted_ranked = deduped

            rows = []
            for idx, c in enumerate(sorted_ranked[:5], start=1):
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

        # Prioritize rounds by requested level active window.
        # This keeps month separation explicit:
        # - country view -> rounds active in country season (e.g. April round in May)
        # - regional view -> rounds active in regional season (e.g. March round in May)
        level_window_map = {
            SeasonLevel.CITY: ("city_season_start_date", "city_season_end_date"),
            SeasonLevel.COUNTRY: ("country_season_start_date", "country_season_end_date"),
            SeasonLevel.REGIONAL: ("regional_start_date", "regional_end_date"),
            SeasonLevel.CONTINENT: ("continental_start_date", "continental_end_date"),
            SeasonLevel.GLOBAL: ("global_start_date", "global_end_date"),
        }
        start_attr, end_attr = level_window_map.get(requested_level, (None, None))

        in_level_window = []
        outside_level_window = []
        for r in candidate_rounds:
            if not start_attr or not end_attr:
                outside_level_window.append(r)
                continue
            start_val = getattr(r, start_attr, None)
            end_val = getattr(r, end_attr, None)
            if start_val and end_val and start_val <= today <= end_val:
                in_level_window.append(r)
            else:
                outside_level_window.append(r)

        # First preference: rounds that already have active links for requested level.
        level_linked_round_ids = {
            row[0]
            for row in (
                db.query(ContestSeason.round_id)
                .join(ContestSeasonLink, ContestSeasonLink.season_id == ContestSeason.id)
                .filter(ContestSeason.level == requested_level)
                .filter(ContestSeason.is_deleted == False)
                .filter(ContestSeasonLink.is_active == True)
                .filter(ContestSeason.round_id.isnot(None))
                .distinct()
                .all()
            )
            if row and row[0] is not None
        }

        linked_in_window = [r for r in in_level_window if r.id in level_linked_round_ids]
        unlinked_in_window = [r for r in in_level_window if r.id not in level_linked_round_ids]
        linked_outside_window = [r for r in outside_level_window if r.id in level_linked_round_ids]
        unlinked_outside_window = [r for r in outside_level_window if r.id not in level_linked_round_ids]

        # Secondary preference for currently voting-open rounds within each bucket.
        def _prioritize_voting_open(rounds):
            open_rounds = [r for r in rounds if bool(r.is_voting_open)]
            closed_rounds = [r for r in rounds if not bool(r.is_voting_open)]
            return open_rounds + closed_rounds

        search_rounds = (
            _prioritize_voting_open(linked_in_window)
            + _prioritize_voting_open(unlinked_in_window)
            + _prioritize_voting_open(linked_outside_window)
            + _prioritize_voting_open(unlinked_outside_window)
        )

        # Business month mapping override for nomination leaderboard UX:
        # - in May: country => April round, regional => March round, ...
        level_round_offset = {
            SeasonLevel.CITY: 0,
            SeasonLevel.COUNTRY: 1,
            SeasonLevel.REGIONAL: 2,
            SeasonLevel.CONTINENT: 3,
            SeasonLevel.GLOBAL: 4,
        }
        target_offset = level_round_offset.get(requested_level)
        if target_offset is not None:
            target_date = _subtract_months(today, target_offset)
            target_name = f"Round {target_date.strftime('%B %Y')}".lower()
            preferred = [r for r in candidate_rounds if (r.name or "").strip().lower() == target_name]
            if preferred:
                preferred_ids = {r.id for r in preferred}
                search_rounds = preferred + [r for r in search_rounds if r.id not in preferred_ids]

        # Default to the first prioritized round instead of newest round, so
        # diagnostics/metadata stay aligned with requested level intent.
        chosen_round = search_rounds[0] if search_rounds else candidate_rounds[0]
        chosen_contests = []
        fallback_applied = False
        for idx, rnd in enumerate(search_rounds):
            contests_out = _build_for_round(rnd)
            if contests_out:
                chosen_round = rnd
                chosen_contests = contests_out
                fallback_applied = idx != 0
                break

        # If no contests matched country filter, keep selected round aligned with the
        # prioritized search order (which already applies business month mapping).
        # Fallback to linked rounds only if search list is empty.
        if not chosen_contests:
            if search_rounds:
                chosen_round = search_rounds[0]
                fallback_applied = True
            else:
                linked_candidates = linked_in_window + linked_outside_window
                if linked_candidates:
                    chosen_round = linked_candidates[0]
                    fallback_applied = True

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

