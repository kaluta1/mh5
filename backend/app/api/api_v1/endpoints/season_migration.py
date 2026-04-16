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


@router.get("/top-high5")
def get_top_high5_by_country(
    round_id: int | None = Query(default=None),
    country: str | None = Query(default=None),
    current_user: User | None = Depends(deps.get_current_active_user_optional),
):
    """
    Read-only preview for Top High5 by country (nomination contests).
    Returns full ranked rows for that country and marks top-5 as migrates_next_stage=True.
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        selected_country = (country or "").strip()
        if not selected_country and current_user:
            selected_country = (current_user.country or "").strip()
        if not selected_country:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Country is required (query ?country=... or authenticated user country).",
            )

        variants = _country_variants(selected_country)

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
                nxt = _next_level(season.level)
                matched_key = None
                ranking_scope = "country_group"
                ranked = []

                # Primary mode: canonical migration grouping on COUNTRY stage
                if season.level == SeasonLevel.COUNTRY:
                    grouped = season_migration_service.get_top_contestants_by_location(
                        db,
                        season.id,
                        "country",
                        contest_id=contest.id,
                        limit=None,
                        stage_id=None,
                        diagnostics=False,
                    )
                    for key in grouped.keys():
                        if (key or "").strip().lower() in variants:
                            matched_key = key
                            break
                    if matched_key is not None:
                        ranked = grouped.get(matched_key, [])

                # Fallback mode: when active season is no longer COUNTRY (or no grouped row),
                # still provide country-specific ranking snapshot from the current active season.
                if not ranked:
                    season_contestants = (
                        db.query(Contestant)
                        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
                        .filter(
                            and_(
                                ContestantSeason.season_id == season.id,
                                ContestantSeason.is_active == True,
                                Contestant.is_active == True,
                                Contestant.is_deleted == False,
                                Contestant.is_qualified == True,
                                Contestant.season_id == contest.id,
                            )
                        )
                        .all()
                    )
                    filtered = [
                        c
                        for c in season_contestants
                        if (c.country or "").strip().lower() in variants
                    ]
                    if not filtered:
                        continue
                    ranking_scope = "country_snapshot_on_active_level"
                    matched_key = selected_country

                    fallback_ids = [c.id for c in filtered]
                    fallback_points_rows = (
                        db.query(
                            ContestantVoting.contestant_id,
                            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
                        )
                        .filter(
                            and_(
                                ContestantVoting.season_id == season.id,
                                ContestantVoting.contestant_id.in_(fallback_ids),
                            )
                        )
                        .group_by(ContestantVoting.contestant_id)
                        .all()
                    )
                    fallback_points = {r.contestant_id: int(r.total_points or 0) for r in fallback_points_rows}
                    fallback_eng = season_migration_service._engagement_by_contestant(db, fallback_ids)
                    ranked = sorted(
                        filtered,
                        key=lambda c: (
                            fallback_points.get(c.id, 0),
                            fallback_eng.get(c.id, {}).get("shares", 0),
                            fallback_eng.get(c.id, {}).get("likes", 0),
                            fallback_eng.get(c.id, {}).get("comments", 0),
                            fallback_eng.get(c.id, {}).get("views", 0),
                            -(c.id or 0),
                        ),
                        reverse=True,
                    )
                contestant_ids = [c.id for c in ranked]
                points_by_id = {}
                engagement_by_id = {}
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

                rows = []
                for idx, c in enumerate(ranked, start=1):
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

                contests_out.append(
                    {
                        "contest_id": contest.id,
                        "contest_name": contest.name,
                        "from_level": season.level.value,
                        "to_level": nxt.value if nxt else None,
                        "country_group": matched_key,
                        "ranking_scope": ranking_scope,
                        "promotion_limit": 5,
                        "rows": rows,
                    }
                )
            return contests_out

        if round_id is not None:
            rnd = db.query(Round).filter(Round.id == round_id).first()
            if not rnd:
                raise HTTPException(status_code=404, detail=f"Round id={round_id} not found")
            contests_out = _build_for_round(rnd)
            return {
                "round_id": rnd.id,
                "round_name": rnd.name,
                "country": selected_country,
                "contests": contests_out,
                "fallback_applied": False,
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
            "contests": chosen_contests,
            "fallback_applied": fallback_applied,
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

