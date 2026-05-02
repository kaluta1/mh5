#!/usr/bin/env python3
"""
Diagnose and optionally backfill COUNTRY -> REGIONAL migration for one round.

Examples:
  PYTHONPATH=. python scripts/diagnose_round_regional_migration.py --round-id 3
  PYTHONPATH=. python scripts/diagnose_round_regional_migration.py --round-name "Round March 2026"
  PYTHONPATH=. python scripts/diagnose_round_regional_migration.py --round-id 3 --apply
"""

from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, ContestantSeason, SeasonLevel
from app.models.round import Round, round_contests
from app.services.season_migration import SeasonMigrationService


def _resolve_round(db, round_id: int | None, round_name: str | None) -> Round:
    query = db.query(Round)
    if round_id is not None:
        rnd = query.filter(Round.id == round_id).first()
    elif round_name:
        rnd = query.filter(Round.name == round_name).first()
    else:
        raise SystemExit("Provide --round-id or --round-name")
    if not rnd:
        raise SystemExit("Round not found")
    return rnd


def _contest_ids_for_round(db, round_id: int) -> list[int]:
    rows = db.execute(
        select(round_contests.c.contest_id).where(round_contests.c.round_id == round_id)
    ).fetchall()
    return [row[0] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose/backfill COUNTRY -> REGIONAL migration for a round"
    )
    parser.add_argument("--round-id", type=int)
    parser.add_argument("--round-name")
    parser.add_argument("--apply", action="store_true", help="Actually promote missing contests")
    parser.add_argument(
        "--repair-existing",
        action="store_true",
        help="When REGIONAL already exists, prune active regional links back to the source COUNTRY Top High5.",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rnd = _resolve_round(db, args.round_id, args.round_name)
        contest_ids = _contest_ids_for_round(db, rnd.id)
        contests = (
            db.query(Contest)
            .filter(Contest.id.in_(contest_ids))
            .filter(Contest.contest_mode == "nomination")
            .order_by(Contest.id.asc())
            .all()
            if contest_ids
            else []
        )

        print(f"Round: {rnd.name} (id={rnd.id})")
        print(f"Dates: country_end={rnd.country_season_end_date}, regional_start={rnd.regional_start_date}")
        print(f"Nomination contests: {len(contests)}")
        print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        print()

        summary = {"already_regional": 0, "missing_country": 0, "promoted": 0, "skipped": 0}

        for contest in contests:
            country_link = (
                db.query(ContestSeasonLink, ContestSeason)
                .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                .filter(
                    ContestSeasonLink.contest_id == contest.id,
                    ContestSeason.round_id == rnd.id,
                    ContestSeason.level == SeasonLevel.COUNTRY,
                    ContestSeason.is_deleted == False,
                )
                .order_by(ContestSeasonLink.is_active.desc(), ContestSeasonLink.linked_at.desc())
                .first()
            )
            regional_link = (
                db.query(ContestSeasonLink, ContestSeason)
                .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                .filter(
                    ContestSeasonLink.contest_id == contest.id,
                    ContestSeasonLink.is_active == True,
                    ContestSeason.round_id == rnd.id,
                    ContestSeason.level == SeasonLevel.REGIONAL,
                    ContestSeason.is_deleted == False,
                )
                .first()
            )

            print(f"Contest {contest.id}: {contest.name}")
            if regional_link:
                regional_contest_link, regional_season = regional_link
                summary["already_regional"] += 1
                print(f"  REGIONAL already active: season_id={regional_season.id}")
                if not args.repair_existing:
                    continue
                from datetime import date
                min_regional_start = SeasonMigrationService._nomination_min_start_for_level(
                    rnd,
                    SeasonLevel.REGIONAL,
                )
                if not country_link and min_regional_start and date.today() < min_regional_start:
                    print(
                        f"  REGIONAL is too early for this round (no COUNTRY source). "
                        f"Earliest start: {min_regional_start}. Deactivating regional link."
                    )
                    if args.apply:
                        regional_contest_link.is_active = False
                        (
                            db.query(ContestantSeason)
                            .filter(ContestantSeason.season_id == regional_season.id)
                            .update({ContestantSeason.is_active: False}, synchronize_session=False)
                        )
                        db.commit()
                        print("  Too-early REGIONAL link deactivated.")
                    continue
                if not country_link:
                    print("  Cannot repair: missing COUNTRY source season link.")
                    continue
                _, country_season = country_link
                if min_regional_start and date.today() < min_regional_start:
                    source_ids = {
                        c.id
                        for c in SeasonMigrationService._contestants_for_contest_in_season(
                            db,
                            country_season.id,
                            contest.id,
                            active_only=False,
                            qualified_only=False,
                        )
                    }
                    print(
                        f"  REGIONAL is too early for this round. Earliest start: {min_regional_start}. "
                        f"Source ids to deactivate from regional: {sorted(source_ids)}"
                    )
                    if args.apply:
                        regional_contest_link.is_active = False
                        (
                            db.query(ContestantSeason)
                            .filter(
                                ContestantSeason.season_id == regional_season.id,
                                ContestantSeason.contestant_id.in_(list(source_ids) or [-1]),
                            )
                            .update({ContestantSeason.is_active: False}, synchronize_session=False)
                        )
                        db.commit()
                        print("  Too-early REGIONAL link deactivated.")
                    continue
                grouped = SeasonMigrationService.get_top_contestants_by_location(
                    db,
                    country_season.id,
                    "country",
                    contest_id=contest.id,
                    limit=args.limit,
                    diagnostics=False,
                    active_links_only=False,
                    qualified_only=False,
                )
                expected_ids = {m.id for members in grouped.values() for m in members}
                source_ids = {
                    c.id
                    for c in SeasonMigrationService._contestants_for_contest_in_season(
                        db,
                        country_season.id,
                        contest.id,
                        active_only=False,
                        qualified_only=False,
                    )
                }
                active_regional_links = (
                    db.query(ContestantSeason)
                    .filter(
                        ContestantSeason.season_id == regional_season.id,
                        ContestantSeason.is_active == True,
                        ContestantSeason.contestant_id.in_(list(source_ids) or [-1]),
                    )
                    .all()
                )
                active_ids = {link.contestant_id for link in active_regional_links}
                extra_ids = active_ids - expected_ids
                missing_ids = expected_ids - active_ids
                print(f"  Repair expected ids: {sorted(expected_ids)}")
                print(f"  Repair active ids:   {sorted(active_ids)}")
                print(f"  Repair extra ids:    {sorted(extra_ids)}")
                print(f"  Repair missing ids:  {sorted(missing_ids)}")
                if args.apply:
                    for link in active_regional_links:
                        if link.contestant_id in extra_ids:
                            link.is_active = False
                    for cid in missing_ids:
                        link = (
                            db.query(ContestantSeason)
                            .filter(
                                ContestantSeason.season_id == regional_season.id,
                                ContestantSeason.contestant_id == cid,
                            )
                            .first()
                        )
                        if link:
                            link.is_active = True
                        else:
                            db.add(ContestantSeason(
                                contestant_id=cid,
                                season_id=regional_season.id,
                                is_active=True,
                            ))
                    db.commit()
                    print("  Repair applied.")
                continue
            if not country_link:
                summary["missing_country"] += 1
                print("  Missing active COUNTRY season link; cannot promote.")
                continue

            _, country_season = country_link
            from datetime import date
            min_regional_start = SeasonMigrationService._nomination_min_start_for_level(
                rnd,
                SeasonLevel.REGIONAL,
            )
            if min_regional_start and date.today() < min_regional_start:
                print(
                    f"  REGIONAL is too early for this round. Earliest start: {min_regional_start}. "
                    "Skipping promotion."
                )
                summary["skipped"] += 1
                continue

            repaired = SeasonMigrationService._ensure_source_season_links(
                db=db,
                contest_id=contest.id,
                season_id=country_season.id,
            )
            grouped = SeasonMigrationService.get_top_contestants_by_location(
                db,
                country_season.id,
                "country",
                contest_id=contest.id,
                limit=args.limit,
                diagnostics=False,
                qualified_only=False,
            )
            selected_count = sum(len(items) for items in grouped.values())
            print(f"  COUNTRY source season_id={country_season.id}; repaired_links={repaired}")
            print(f"  Candidate groups={len(grouped)}; selected_for_regional={selected_count}")
            for location, members in grouped.items():
                ids = [m.id for m in members]
                print(f"    {location}: {len(ids)} -> {ids}")

            if not args.apply:
                continue

            result = SeasonMigrationService.promote_to_next_level(
                db,
                SeasonLevel.COUNTRY,
                SeasonLevel.REGIONAL,
                contest.id,
                limit=args.limit,
                from_season_id=country_season.id,
                source_qualified_only=False,
            )
            print(f"  APPLY result: {result}")
            if isinstance(result, dict) and not result.get("error") and not result.get("skipped"):
                summary["promoted"] += 1
            else:
                summary["skipped"] += 1

        if not args.apply:
            db.rollback()
        print()
        print(f"Summary: {summary}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
