#!/usr/bin/env python3
"""
Soft-delete participation contestants (entry_type='participation' only).
Never touches nominations (entry_type='nomination').

Two modes (pick one):
  --contest-id N     Only participations linked to that contest.
  --all-participation  Every participation contestant in the database (all contests).

For --all-participation, confirmation is stricter (see below).

Usage (from backend/, venv active):
  python scripts/remove_contestants_for_contest.py --contest-id 15 --dry-run
  python scripts/remove_contestants_for_contest.py --contest-id 15 --yes

  python scripts/remove_contestants_for_contest.py --all-participation --dry-run
  python scripts/remove_contestants_for_contest.py --all-participation --yes --confirm-all-contests
  # or interactive: omit --yes and type: DELETE ALL PARTICIPATION
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import and_

from app.db.session import SessionLocal
from app.models.contests import Contestant, ContestantSeason, ContestSeason, ContestSeasonLink
from app.models.round import round_contests


def collect_participation_contestant_ids(db, contest_id: int) -> list[int]:
    """Contestant IDs for this contest with entry_type=participation only."""
    ids: set[int] = set()

    def q_participation():
        return (
            db.query(Contestant.id)
            .filter(
                Contestant.is_deleted == False,
                Contestant.entry_type == "participation",
            )
        )

    for (cid,) in q_participation().filter(Contestant.season_id == contest_id).all():
        ids.add(cid)

    season_ids = [
        s
        for s, in db.query(ContestSeasonLink.season_id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True,
        )
        .all()
    ]
    if season_ids:
        for (cid,) in q_participation().filter(Contestant.season_id.in_(season_ids)).all():
            ids.add(cid)

    round_ids = [
        r
        for r, in db.query(round_contests.c.round_id)
        .filter(round_contests.c.contest_id == contest_id)
        .all()
    ]
    if round_ids:
        for (cid,) in q_participation().filter(Contestant.round_id.in_(round_ids)).all():
            ids.add(cid)

    for (cid,) in (
        db.query(Contestant.id)
        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
        .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
        .join(
            ContestSeasonLink,
            and_(
                ContestSeasonLink.season_id == ContestSeason.id,
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.is_active == True,
            ),
        )
        .filter(
            Contestant.is_deleted == False,
            Contestant.entry_type == "participation",
        )
        .all()
    ):
        ids.add(cid)

    return sorted(ids)


def collect_all_participation_contestant_ids(db) -> list[int]:
    """Every non-deleted participation contestant id (all contests)."""
    rows = (
        db.query(Contestant.id)
        .filter(
            Contestant.is_deleted == False,
            Contestant.entry_type == "participation",
        )
        .all()
    )
    return sorted(r[0] for r in rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Soft-delete participation contestants only (never nominations)."
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--contest-id", type=int, help="Limit to one contest (contest.id)")
    scope.add_argument(
        "--all-participation",
        action="store_true",
        help="Soft-delete every participation contestant in the DB (all contests).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List IDs only; do not update the database.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip typing YES (single contest only, or with --confirm-all-contests).")
    parser.add_argument(
        "--confirm-all-contests",
        action="store_true",
        help="Required with --yes when using --all-participation (safety).",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.all_participation:
            ids = collect_all_participation_contestant_ids(db)
            print(
                f"ALL CONTESTS: {len(ids)} participation contestant(s) "
                f"(entry_type=participation only; nominations unchanged)."
            )
        else:
            ids = collect_participation_contestant_ids(db, args.contest_id)
            print(
                f"Contest {args.contest_id}: {len(ids)} participation contestant(s) "
                f"(entry_type=participation only; nominations unchanged)."
            )
        if ids:
            preview = ids[:40]
            print(f"  IDs: {preview}{' ...' if len(ids) > 40 else ''}")
        if not ids:
            return 0
        if args.dry_run:
            print("Dry-run: no changes committed.")
            return 0

        if args.all_participation:
            if args.yes:
                if not args.confirm_all_contests:
                    print(
                        "Aborted: for --all-participation with --yes you must also pass "
                        "--confirm-all-contests."
                    )
                    return 1
            else:
                s = input("Type DELETE ALL PARTICIPATION to soft-delete every participation row: ")
                if s.strip() != "DELETE ALL PARTICIPATION":
                    print("Aborted.")
                    return 1
        else:
            if not args.yes:
                s = input("Type YES to soft-delete these participation contestants: ")
                if s.strip() != "YES":
                    print("Aborted.")
                    return 1
        n = 0
        for cid in ids:
            c = (
                db.query(Contestant)
                .filter(
                    Contestant.id == cid,
                    Contestant.is_deleted == False,
                    Contestant.entry_type == "participation",
                )
                .first()
            )
            if c:
                c.is_deleted = True
                n += 1
        db.commit()
        print(f"Soft-deleted {n} participation contestant row(s) (is_deleted=True).")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
