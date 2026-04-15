"""
Real-data test script for Round 3 winner selection + migration preview.

Default behavior is NON-PERSISTENT:
- Winner ranking is computed from real DB data.
- Migration is executed as a dry-run (commit patched to flush).
- Full rollback at the end.

Usage:
  cd backend
  source venv/bin/activate
  export PYTHONPATH=/root/mh5/backend
  python scripts/test_round3_real_data.py

Optional:
  python scripts/test_round3_real_data.py --round-id 3
  python scripts/test_round3_real_data.py --persist
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from typing import Dict, List, Tuple

import app.models  # noqa: F401
from sqlalchemy import and_, func

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    Contestant,
    ContestantSeason,
    SeasonLevel,
)
from app.models.round import Round
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService


@contextmanager
def non_persistent_commits(db):
    """Patch db.commit() -> db.flush() to keep script rollback-safe."""
    original_commit = db.commit
    db.commit = db.flush  # type: ignore[assignment]
    try:
        yield
    finally:
        db.commit = original_commit  # type: ignore[assignment]


def _next_level(from_level: SeasonLevel) -> SeasonLevel | None:
    mapping = {
        SeasonLevel.CITY: SeasonLevel.COUNTRY,
        SeasonLevel.COUNTRY: SeasonLevel.REGIONAL,
        SeasonLevel.REGIONAL: SeasonLevel.CONTINENT,
        SeasonLevel.CONTINENT: SeasonLevel.GLOBAL,
    }
    return mapping.get(from_level)


def _location_field_for_to_level(to_level: SeasonLevel) -> str | None:
    mapping = {
        SeasonLevel.COUNTRY: "city",
        SeasonLevel.REGIONAL: "country",
        SeasonLevel.CONTINENT: "region",
        SeasonLevel.GLOBAL: "continent",
    }
    return mapping.get(to_level)


def _points_map(db, season_id: int, contestant_ids: List[int]) -> Dict[int, int]:
    if not contestant_ids:
        return {}
    rows = (
        db.query(
            ContestantVoting.contestant_id,
            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
        )
        .filter(
            and_(
                ContestantVoting.season_id == season_id,
                ContestantVoting.contestant_id.in_(contestant_ids),
            )
        )
        .group_by(ContestantVoting.contestant_id)
        .all()
    )
    return {r.contestant_id: int(r.total_points or 0) for r in rows}


def _display_name(contestant: Contestant) -> str:
    if contestant.user and contestant.user.full_name:
        return contestant.user.full_name
    if contestant.user and contestant.user.email:
        return contestant.user.email
    return f"Contestant#{contestant.id}"


def _format_metrics_line(
    rank: int,
    contestant: Contestant,
    points_by_id: Dict[int, int],
    engagement_by_id: Dict[int, Dict[str, int]],
) -> str:
    e = engagement_by_id.get(contestant.id, {})
    return (
        f"{rank:>2}. {_display_name(contestant)} "
        f"(id={contestant.id}, stars={points_by_id.get(contestant.id, 0)}, "
        f"shares={e.get('shares', 0)}, likes={e.get('likes', 0)}, "
        f"comments={e.get('comments', 0)}, views={e.get('views', 0)})"
    )


def _print_empty_promotion_diagnostics(db, season: ContestSeason, from_level: SeasonLevel) -> None:
    """Print root-cause counters when no contestants are promoted."""
    all_active_rows = (
        db.query(Contestant.id, Contestant.user_id)
        .join(ContestantSeason)
        .filter(
            and_(
                ContestantSeason.season_id == season.id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
            )
        )
        .all()
    )
    active_ids = [r.id for r in all_active_rows]
    qualified_count = (
        db.query(Contestant)
        .join(ContestantSeason)
        .filter(
            and_(
                ContestantSeason.season_id == season.id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == True,
            )
        )
        .count()
    )
    non_qualified_count = (
        db.query(Contestant)
        .join(ContestantSeason)
        .filter(
            and_(
                ContestantSeason.season_id == season.id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == False,
            )
        )
        .count()
    )

    # Required location by from_level (used for next promotion step selection).
    # city -> needs user.city ; country -> user.country ; regional -> user.region ; continent -> user.continent
    location_attr = {
        SeasonLevel.CITY: "city",
        SeasonLevel.COUNTRY: "country",
        SeasonLevel.REGIONAL: "region",
        SeasonLevel.CONTINENT: "continent",
    }.get(from_level)

    with_location = 0
    without_location = 0
    if active_ids and location_attr:
        active_contestants = (
            db.query(Contestant)
            .filter(Contestant.id.in_(active_ids))
            .all()
        )
        for c in active_contestants:
            val = getattr(c.user, location_attr, None) if c.user else None
            if val:
                with_location += 1
            else:
                without_location += 1

    voted_count = 0
    if active_ids:
        voted_count = (
            db.query(func.count(func.distinct(ContestantVoting.contestant_id)))
            .filter(
                and_(
                    ContestantVoting.season_id == season.id,
                    ContestantVoting.contestant_id.in_(active_ids),
                )
            )
            .scalar()
            or 0
        )

    print("Diagnostics:")
    print(f"  - Active contestants in season: {len(active_ids)}")
    print(f"  - Qualified contestants: {qualified_count}")
    print(f"  - Non-qualified contestants: {non_qualified_count}")
    if location_attr:
        print(f"  - With {location_attr}: {with_location}")
        print(f"  - Missing {location_attr}: {without_location}")
    print(f"  - Contestants with at least one vote in season: {voted_count}")


def _preview_non_global_winners(
    db,
    season: ContestSeason,
    to_level: SeasonLevel,
    limit: int,
) -> Tuple[Dict[str, List[Contestant]], Dict[int, int], Dict[int, Dict[str, int]]]:
    location_field = _location_field_for_to_level(to_level)
    if not location_field:
        return {}, {}, {}

    grouped = SeasonMigrationService.get_top_contestants_by_location(
        db=db,
        season_id=season.id,
        location_field=location_field,
        limit=limit,
        stage_id=None,
    )
    all_contestants = [c for arr in grouped.values() for c in arr]
    all_ids = [c.id for c in all_contestants]
    points_by_id = _points_map(db, season.id, all_ids)
    engagement_by_id = SeasonMigrationService._engagement_by_contestant(db, all_ids)
    return grouped, points_by_id, engagement_by_id


def _preview_global_winners(
    db,
    season: ContestSeason,
    limit: int,
) -> Tuple[List[Contestant], Dict[int, int], Dict[int, Dict[str, int]]]:
    contestants = (
        db.query(Contestant)
        .join(ContestantSeason)
        .filter(
            and_(
                ContestantSeason.season_id == season.id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == True,
            )
        )
        .all()
    )
    contestant_ids = [c.id for c in contestants]
    points_by_id = _points_map(db, season.id, contestant_ids)
    engagement_by_id = SeasonMigrationService._engagement_by_contestant(db, contestant_ids)
    ranked = sorted(
        contestants,
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
    return ranked[:limit], points_by_id, engagement_by_id


def run_real_data_test(round_id: int = 3, limit: int = 5, persist: bool = False):
    db = SessionLocal()
    try:
        ctx = contextmanager(lambda: (yield))() if persist else non_persistent_commits(db)
        with ctx:
            round_obj = db.query(Round).filter(Round.id == round_id).first()
            if not round_obj:
                raise RuntimeError(f"Round {round_id} not found.")

            links = (
                db.query(ContestSeasonLink, ContestSeason, Contest)
                .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                .join(Contest, Contest.id == ContestSeasonLink.contest_id)
                .filter(
                    and_(
                        ContestSeason.round_id == round_id,
                        ContestSeasonLink.is_active == True,
                        ContestSeason.is_deleted == False,
                    )
                )
                .all()
            )
            if not links:
                raise RuntimeError(f"No active contest-season links found for round {round_id}.")

            print("\n=== Round Real-Data Winner + Migration Test ===")
            print(f"Round: {round_obj.id} - {round_obj.name}")
            print(f"Active contest-season links: {len(links)}")
            print(f"Mode: {'PERSISTENT' if persist else 'NON-PERSISTENT (rollback)'}")

            for link, season, contest in links:
                from_level = season.level
                to_level = _next_level(from_level)
                print("\n------------------------------------------------------------")
                print(
                    f"Contest: {contest.name} | Type: {contest.contest_type} | "
                    f"From: {from_level.value} -> To: {to_level.value if to_level else 'N/A'}"
                )
                print(f"Source season: {season.id} ({season.title})")

                if not to_level:
                    print("No next migration level (already global or unsupported).")
                    continue

                print("\n[1] Winner selection preview")
                if to_level == SeasonLevel.GLOBAL:
                    ranked, points_by_id, engagement_by_id = _preview_global_winners(
                        db=db,
                        season=season,
                        limit=3,
                    )
                    if not ranked:
                        print("No qualified contestants found for GLOBAL ranking.")
                    else:
                        print("GLOBAL candidate ranking (top 3):")
                        for i, c in enumerate(ranked, start=1):
                            print(_format_metrics_line(i, c, points_by_id, engagement_by_id))
                else:
                    grouped, points_by_id, engagement_by_id = _preview_non_global_winners(
                        db=db,
                        season=season,
                        to_level=to_level,
                        limit=limit,
                    )
                    if not grouped:
                        print("No grouped winners found for this season/level.")
                    else:
                        for group_name, winners in grouped.items():
                            print(f"Group: {group_name} (top {min(limit, len(winners))})")
                            for i, c in enumerate(winners, start=1):
                                print(_format_metrics_line(i, c, points_by_id, engagement_by_id))

                print("\n[2] Migration dry-run using service")
                result = SeasonMigrationService.promote_to_next_level(
                    db=db,
                    from_level=from_level,
                    to_level=to_level,
                    contest_id=contest.id,
                    limit=3 if to_level == SeasonLevel.GLOBAL else limit,
                )
                if "error" in result:
                    print(f"ERROR: {result['error']}")
                    continue

                promoted_ids = result.get("promoted_contestant_ids", [])
                if not promoted_ids:
                    print("No contestants promoted in dry-run.")
                    _print_empty_promotion_diagnostics(db, season, from_level)
                else:
                    promoted = db.query(Contestant).filter(Contestant.id.in_(promoted_ids)).all()
                    promoted_by_id = {c.id: c for c in promoted}
                    print(f"Promoted IDs: {promoted_ids}")
                    print("Promoted names:")
                    for i, cid in enumerate(promoted_ids, start=1):
                        contestant = promoted_by_id.get(cid)
                        name = _display_name(contestant) if contestant else f"Contestant#{cid}"
                        print(f"  {i}. {name} (id={cid})")

        if not persist:
            db.rollback()
            print("\nRollback complete (non-persistent mode).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run real-data winner determination + migration dry-run for a round."
    )
    parser.add_argument("--round-id", type=int, default=3, help="Round ID to test (default: 3).")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Per-group promotion limit for non-global transitions (default: 5).",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist migration changes (default is rollback-safe dry-run).",
    )
    args = parser.parse_args()
    run_real_data_test(round_id=args.round_id, limit=args.limit, persist=args.persist)

