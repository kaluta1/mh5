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
from datetime import datetime, timezone
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


def _points_map(
    db,
    season_id: int,
    contestant_ids: List[int],
    contest_id: int | None = None,
) -> Dict[int, int]:
    if not contestant_ids:
        return {}
    query = (
        db.query(
            ContestantVoting.contestant_id,
            func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
        )
    )
    if contest_id is not None:
        query = query.filter(
            and_(
                ContestantVoting.season_id == season_id,
                ContestantVoting.contest_id == contest_id,
                ContestantVoting.contestant_id.in_(contestant_ids),
            )
        )
    else:
        query = query.filter(
            and_(
                ContestantVoting.season_id == season_id,
                ContestantVoting.contestant_id.in_(contestant_ids),
            )
        )
    rows = query.group_by(ContestantVoting.contestant_id).all()
    if not rows and contest_id is not None:
        rows = (
            db.query(
                ContestantVoting.contestant_id,
                func.coalesce(func.sum(ContestantVoting.points), 0).label("total_points"),
            )
            .filter(
                and_(
                    ContestantVoting.contest_id == contest_id,
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


def _active_linked_count(db, season_id: int) -> int:
    return (
        db.query(ContestantSeason)
        .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
        .filter(
            and_(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
            )
        )
        .count()
    )


def _backfill_contestants_into_season(db, contest_id: int, season_id: int) -> int:
    """
    Ensure active contest contestants are linked to the target season.
    This repairs cases where season link exists but contestant links are empty.
    """
    contestants = (
        db.query(Contestant)
        .filter(
            and_(
                Contestant.season_id == contest_id,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
            )
        )
        .all()
    )
    added = 0
    for contestant in contestants:
        contestant.is_qualified = True
        link = (
            db.query(ContestantSeason)
            .filter(
                and_(
                    ContestantSeason.contestant_id == contestant.id,
                    ContestantSeason.season_id == season_id,
                )
            )
            .first()
        )
        if not link:
            db.add(
                ContestantSeason(
                    contestant_id=contestant.id,
                    season_id=season_id,
                    joined_at=datetime.now(timezone.utc),
                    is_active=True,
                )
            )
            added += 1
        else:
            link.is_active = True
            link.joined_at = datetime.now(timezone.utc)
    db.flush()
    return added


def _auto_initialize_if_empty(db, round_id: int, contest: Contest, season: ContestSeason) -> None:
    """
    Auto-fix empty source season by running init and/or backfilling links.
    """
    before = _active_linked_count(db, season.id)
    if before > 0:
        return

    mode = (contest.contest_mode or "").lower()
    print(
        f"[Auto-fix] Empty season detected for contest {contest.id} "
        f"(level={season.level.value}, mode={mode or 'unknown'})."
    )

    if season.level == SeasonLevel.CITY and mode == "participation":
        init_result = SeasonMigrationService.migrate_to_city_season(
            db=db, contest_id=contest.id, round_id=round_id
        )
        print(f"[Auto-fix] migrate_to_city_season result: {init_result}")
    elif season.level == SeasonLevel.COUNTRY and mode == "nomination":
        init_result = SeasonMigrationService.migrate_to_country_start(
            db=db, contest_id=contest.id, round_id=round_id
        )
        print(f"[Auto-fix] migrate_to_country_start result: {init_result}")
    else:
        print(
            "[Auto-fix] No direct initializer mapped for this level/mode; "
            "trying link backfill only."
        )

    after_init = _active_linked_count(db, season.id)
    if after_init == 0:
        repaired = _backfill_contestants_into_season(db, contest.id, season.id)
        print(f"[Auto-fix] Backfilled contestant-season links: {repaired}")

    after = _active_linked_count(db, season.id)
    print(f"[Auto-fix] Active linked contestants: before={before}, after={after}")


def _preview_non_global_winners(
    db,
    contest: Contest,
    season: ContestSeason,
    to_level: SeasonLevel,
    limit: int,
    country_filter: str | None = None,
) -> Tuple[Dict[str, List[Contestant]], Dict[int, int], Dict[int, Dict[str, int]]]:
    location_field = _location_field_for_to_level(to_level)
    if not location_field:
        return {}, {}, {}

    grouped = SeasonMigrationService.get_top_contestants_by_location(
        db=db,
        season_id=season.id,
        location_field=location_field,
        contest_id=contest.id,
        country_filter=country_filter,
        limit=limit,
        stage_id=None,
    )

    all_contestants = [c for arr in grouped.values() for c in arr]
    all_ids = [c.id for c in all_contestants]
    points_by_id = _points_map(db, season.id, all_ids, contest_id=contest.id)
    engagement_by_id = SeasonMigrationService._engagement_by_contestant(db, all_ids)
    return grouped, points_by_id, engagement_by_id


def _preview_global_winners(
    db,
    contest: Contest,
    season: ContestSeason,
    limit: int,
    country_filter: str | None = None,
) -> Tuple[List[Contestant], Dict[int, int], Dict[int, Dict[str, int]]]:
    contestants = (
        db.query(Contestant)
        .join(ContestantSeason)
        .filter(
            and_(
                ContestantSeason.season_id == season.id,
                Contestant.season_id == contest.id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == True,
            )
        )
        .all()
    )
    if country_filter:
        wanted = country_filter.strip().lower()
        contestants = [
            c for c in contestants
            if c.user and (c.user.country or "").strip().lower() == wanted
        ]

    contestant_ids = [c.id for c in contestants]
    points_by_id = _points_map(db, season.id, contestant_ids, contest_id=contest.id)
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


def run_real_data_test(
    round_id: int = 3,
    limit: int = 5,
    persist: bool = False,
    auto_init_empty: bool = False,
    country: str | None = None,
    source_season_id: int | None = None,
    source_level_filter: str | None = None,
    respect_contest_current_level: bool = True,
    contest_id_filter: int | None = None,
    only_with_winners: bool = True,
):
    db = SessionLocal()
    try:
        ctx = contextmanager(lambda: (yield))() if persist else non_persistent_commits(db)
        with ctx:
            final_summary = []
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
                .order_by(ContestSeasonLink.linked_at.desc(), ContestSeasonLink.id.desc())
                .all()
            )
            if not links:
                raise RuntimeError(f"No active contest-season links found for round {round_id}.")

            print("\n=== Round Real-Data Winner + Migration Test ===")
            print(f"Round: {round_obj.id} - {round_obj.name}")
            print(f"Active contest-season links: {len(links)}")
            print(f"Mode: {'PERSISTENT' if persist else 'NON-PERSISTENT (rollback)'}")
            if country:
                print(f"Country filter: {country}")
            if source_season_id is not None:
                print(f"Source season filter: {source_season_id}")
            if source_level_filter:
                print(f"From-level filter: {source_level_filter}")
            print(f"Respect contest current level: {respect_contest_current_level}")
            if contest_id_filter is not None:
                print(f"Contest filter: {contest_id_filter}")
            print(f"Only categories with winners: {only_with_winners}")

            processed_contests = set()

            for link, season, contest in links:
                contest_tx = db.begin_nested() if not persist else None
                from_level = season.level
                to_level = _next_level(from_level)
                print("\n------------------------------------------------------------")
                print(
                    f"Contest: {contest.name} (id={contest.id}) | Type: {contest.contest_type} | "
                    f"From: {from_level.value} -> To: {to_level.value if to_level else 'N/A'}"
                )
                print(f"Source season: {season.id} ({season.title})")

                if contest_id_filter is not None and contest.id != contest_id_filter:
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue

                # Keep one record per contest in this run.
                if contest.id in processed_contests:
                    print("Skipped contest: already processed with a newer season link.")
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue

                # Optional strict filter to test only a specific source level.
                if source_level_filter and season.level.value != source_level_filter.strip().lower():
                    print(f"Skipped contest: source level is not '{source_level_filter}'.")
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue

                # Align with dashboard: only test the link that matches current contest level.
                if respect_contest_current_level and contest.level and contest.level != season.level.value:
                    print(
                        f"Skipped contest: contest current level is '{contest.level}', "
                        f"but this link is '{season.level.value}'."
                    )
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue

                processed_contests.add(contest.id)

                if source_season_id is not None and season.id != source_season_id:
                    print(
                        "Skipped contest: source season does not match --source-season-id "
                        f"({source_season_id})."
                    )
                    final_summary.append(
                        {
                            "contest_id": contest.id,
                            "contest_name": contest.name,
                            "from_level": from_level.value,
                            "to_level": to_level.value if to_level else "N/A",
                            "expected_ids": [],
                            "expected_names": [],
                            "promoted_ids": [],
                            "promoted_names": [],
                            "status": "SKIPPED_BY_SOURCE_SEASON_FILTER",
                        }
                    )
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue

                if not to_level:
                    print("No next migration level (already global or unsupported).")
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue

                if auto_init_empty:
                    _auto_initialize_if_empty(db=db, round_id=round_id, contest=contest, season=season)

                print("\n[1] Winner selection preview")
                expected_ids: List[int] = []
                if to_level == SeasonLevel.GLOBAL:
                    ranked, points_by_id, engagement_by_id = _preview_global_winners(
                        db=db,
                        contest=contest,
                        season=season,
                        limit=3,
                        country_filter=country,
                    )
                    if not ranked:
                        print("No qualified contestants found for GLOBAL ranking.")
                    else:
                        expected_ids = [c.id for c in ranked]
                        print("GLOBAL candidate ranking (top 3):")
                        for i, c in enumerate(ranked, start=1):
                            print(_format_metrics_line(i, c, points_by_id, engagement_by_id))
                else:
                    grouped, points_by_id, engagement_by_id = _preview_non_global_winners(
                        db=db,
                        contest=contest,
                        season=season,
                        to_level=to_level,
                        limit=limit,
                        country_filter=country,
                    )
                    if not grouped:
                        print("No grouped winners found for this season/level.")
                    else:
                        for group_name, winners in grouped.items():
                            expected_ids.extend([c.id for c in winners])
                            print(f"Group: {group_name} (top {min(limit, len(winners))})")
                            for i, c in enumerate(winners, start=1):
                                print(_format_metrics_line(i, c, points_by_id, engagement_by_id))

                print("\n[2] Migration dry-run using service")
                if not expected_ids and only_with_winners:
                    print("Skipped contest: no winner candidates for current filters.")
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue
                if country and not expected_ids:
                    print(
                        "Skipped migration dry-run for this contest because country filter "
                        "returned no winner candidates."
                    )
                    final_summary.append(
                        {
                            "contest_id": contest.id,
                            "contest_name": contest.name,
                            "from_level": from_level.value,
                            "to_level": to_level.value,
                            "expected_ids": expected_ids,
                            "expected_names": [],
                            "promoted_ids": [],
                            "promoted_names": [],
                            "status": "SKIPPED_BY_COUNTRY_FILTER",
                        }
                    )
                    if contest_tx is not None:
                        contest_tx.rollback()
                    continue

                result = SeasonMigrationService.promote_to_next_level(
                    db=db,
                    from_level=from_level,
                    to_level=to_level,
                    contest_id=contest.id,
                    limit=3 if to_level == SeasonLevel.GLOBAL else limit,
                    from_season_id=season.id,
                )
                if "error" in result:
                    print(f"ERROR: {result['error']}")
                    final_summary.append(
                        {
                            "contest_id": contest.id,
                            "contest_name": contest.name,
                            "from_level": from_level.value,
                            "to_level": to_level.value,
                            "expected_ids": expected_ids,
                            "promoted_ids": [],
                            "status": "ERROR",
                        }
                    )
                    if contest_tx is not None:
                        contest_tx.rollback()
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

                expected_names = []
                if expected_ids:
                    expected_objs = db.query(Contestant).filter(Contestant.id.in_(expected_ids)).all()
                    expected_by_id = {c.id: c for c in expected_objs}
                    expected_names = [
                        _display_name(expected_by_id[cid]) if cid in expected_by_id else f"Contestant#{cid}"
                        for cid in expected_ids
                    ]

                promoted_names = []
                if promoted_ids:
                    promoted_objs = db.query(Contestant).filter(Contestant.id.in_(promoted_ids)).all()
                    promoted_by_id = {c.id: c for c in promoted_objs}
                    promoted_names = [
                        _display_name(promoted_by_id[cid]) if cid in promoted_by_id else f"Contestant#{cid}"
                        for cid in promoted_ids
                    ]

                match_status = "MATCH" if expected_ids == promoted_ids else "MISMATCH"
                final_summary.append(
                    {
                        "contest_id": contest.id,
                        "contest_name": contest.name,
                        "from_level": from_level.value,
                        "to_level": to_level.value,
                        "expected_ids": expected_ids,
                        "expected_names": expected_names,
                        "promoted_ids": promoted_ids,
                        "promoted_names": promoted_names,
                        "status": match_status,
                    }
                )
                if contest_tx is not None:
                    # Critical for dry-run accuracy across many contests sharing same seasons:
                    # undo this contest's promotion side-effects before evaluating next one.
                    contest_tx.rollback()

            print("\n================ FINAL CHECKOUT ================")
            if not final_summary:
                print("No qualifying categories found with current filters.")
            for idx, row in enumerate(final_summary, start=1):
                print(
                    f"{idx}. Contest {row['contest_id']} ({row['contest_name']}) | "
                    f"{row['from_level']} -> {row['to_level']} | {row['status']}"
                )
                print(f"   Expected IDs: {row.get('expected_ids', [])}")
                if row.get("expected_names") is not None:
                    print(f"   Expected Names: {row.get('expected_names', [])}")
                print(f"   Promoted IDs: {row.get('promoted_ids', [])}")
                if row.get("promoted_names") is not None:
                    print(f"   Promoted Names: {row.get('promoted_names', [])}")
            print("================================================\n")

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
    parser.add_argument(
        "--auto-init-empty",
        action="store_true",
        help="Auto-initialize/backfill empty source seasons before preview/migration.",
    )
    parser.add_argument(
        "--country",
        type=str,
        default=None,
        help="Filter winner preview/final checkout to one country (e.g. Tanzania).",
    )
    parser.add_argument(
        "--source-season-id",
        type=int,
        default=None,
        help="Only evaluate contests whose source season matches this season ID.",
    )
    parser.add_argument(
        "--from-level",
        type=str,
        default=None,
        help="Only evaluate source seasons of this level (city, country, regional, continent).",
    )
    parser.add_argument(
        "--ignore-contest-current-level",
        action="store_true",
        help="Do not force source season to match contest.current level.",
    )
    parser.add_argument(
        "--contest-id",
        type=int,
        default=None,
        help="Only evaluate one specific contest ID.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include categories with no winner candidates in final output.",
    )
    args = parser.parse_args()
    run_real_data_test(
        round_id=args.round_id,
        limit=args.limit,
        persist=args.persist,
        auto_init_empty=args.auto_init_empty,
        country=args.country,
        source_season_id=args.source_season_id,
        source_level_filter=args.from_level,
        respect_contest_current_level=not args.ignore_contest_current_level,
        contest_id_filter=args.contest_id,
        only_with_winners=not args.include_empty,
    )

