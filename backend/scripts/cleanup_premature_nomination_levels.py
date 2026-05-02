#!/usr/bin/env python3
"""
Deactivate nomination ContestSeason links that are too early for a round.

This is a data-repair script for cases where COUNTRY winners were promoted to
REGIONAL/CONTINENT/GLOBAL before the round calendar allowed that level.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

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
    if round_id is not None:
        rnd = db.query(Round).filter(Round.id == round_id).first()
    elif round_name:
        rnd = db.query(Round).filter(Round.name == round_name).first()
    else:
        raise SystemExit("Provide --round-id or --round-name")
    if not rnd:
        raise SystemExit("Round not found")
    return rnd


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean premature nomination season levels for a round")
    parser.add_argument("--round-id", type=int)
    parser.add_argument("--round-name")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rnd = _resolve_round(db, args.round_id, args.round_name)
        contest_ids = [
            row[0]
            for row in db.execute(
                select(round_contests.c.contest_id).where(round_contests.c.round_id == rnd.id)
            ).fetchall()
        ]
        nomination_ids = {
            c.id
            for c in (
                db.query(Contest.id)
                .filter(Contest.id.in_(contest_ids or [-1]))
                .filter(Contest.contest_mode == "nomination")
                .all()
            )
        }

        levels_to_check = [SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL]
        today = date.today()

        print(f"Round: {rnd.name} (id={rnd.id})")
        print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
        print()

        total_links = 0
        total_memberships = 0
        for level in levels_to_check:
            min_start = SeasonMigrationService._nomination_min_start_for_level(rnd, level)
            if min_start is None or today >= min_start:
                print(f"{level.value}: allowed now (min_start={min_start}); keeping active links")
                continue

            rows = (
                db.query(ContestSeasonLink, ContestSeason)
                .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                .filter(
                    ContestSeason.round_id == rnd.id,
                    ContestSeason.level == level,
                    ContestSeason.is_deleted == False,
                    ContestSeasonLink.is_active == True,
                    ContestSeasonLink.contest_id.in_(list(nomination_ids) or [-1]),
                )
                .all()
            )
            print(f"{level.value}: too early until {min_start}; active contest links={len(rows)}")
            for link, season in rows:
                member_count = (
                    db.query(ContestantSeason)
                    .filter(
                        ContestantSeason.season_id == season.id,
                        ContestantSeason.is_active == True,
                    )
                    .count()
                )
                print(
                    f"  contest_id={link.contest_id} season_id={season.id} "
                    f"active_memberships={member_count}"
                )
                total_links += 1
                total_memberships += member_count
                if args.apply:
                    link.is_active = False
                    (
                        db.query(ContestantSeason)
                        .filter(
                            ContestantSeason.season_id == season.id,
                            ContestantSeason.is_active == True,
                        )
                        .update({ContestantSeason.is_active: False}, synchronize_session=False)
                    )

        if args.apply:
            db.commit()
        else:
            db.rollback()

        print()
        print(
            f"Summary: links_to_deactivate={total_links}, "
            f"memberships_to_deactivate={total_memberships}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
