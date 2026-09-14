#!/usr/bin/env python3
"""
Reconciliation check (spec section 23): for every finalized Top High5 group
that migrated contestants to a next season, the frozen `migrated=True`
contestant set must exactly match the contest's actual active
ContestantSeason membership in that destination season. Migration and
reporting must never show different creative sets.

This should pass by construction -- the freeze hook derives `migrated` from
this same membership check at freeze time -- so a mismatch here means either
a bug, or a later run changed destination-season membership without
re-freezing (which the write-once freeze hook would then miss).

Read-only. Exit code 1 if any mismatch is found.

Examples:
  PYTHONPATH=. python scripts/check_top_high5_reconciliation.py
  PYTHONPATH=. python scripts/check_top_high5_reconciliation.py --round-id 3
"""
from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.session import SessionLocal
from app.models.contests import Contestant, ContestantSeason, TopHigh5Result
from app.services.contestant_contest_resolution import contestant_belongs_to_contest_clause


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-id", type=int, help="Only check this round (default: all)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(TopHigh5Result).filter(TopHigh5Result.to_season_id.isnot(None))
        if args.round_id is not None:
            query = query.filter(TopHigh5Result.round_id == args.round_id)
        rows = query.all()

        groups: dict[tuple[int, int], list] = {}
        for r in rows:
            groups.setdefault((r.contest_id, r.to_season_id), []).append(r)

        mismatches = []
        for (contest_id, to_season_id), group_rows in groups.items():
            frozen_migrated_ids = {r.contestant_id for r in group_rows if r.migrated}

            actual_ids = {
                row[0]
                for row in db.query(ContestantSeason.contestant_id)
                .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
                .filter(
                    ContestantSeason.season_id == to_season_id,
                    ContestantSeason.is_active == True,
                    contestant_belongs_to_contest_clause(contest_id),
                )
                .all()
            }

            if frozen_migrated_ids != actual_ids:
                mismatches.append(
                    {
                        "contest_id": contest_id,
                        "to_season_id": to_season_id,
                        "round_id": group_rows[0].round_id,
                        "level": group_rows[0].level.value,
                        "frozen_migrated_ids": sorted(frozen_migrated_ids),
                        "actual_active_ids": sorted(actual_ids),
                    }
                )

        print(f"Groups checked: {len(groups)}")
        print(f"Mismatches: {len(mismatches)}")
        for m in mismatches:
            print(
                f"  contest={m['contest_id']} level={m['level']} round={m['round_id']} "
                f"to_season={m['to_season_id']}: "
                f"frozen={m['frozen_migrated_ids']} actual={m['actual_active_ids']}"
            )
        if mismatches:
            sys.exit(1)
        print("OK: frozen migrated sets match actual destination-season membership exactly.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
