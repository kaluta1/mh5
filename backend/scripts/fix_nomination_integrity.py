"""
Full nomination integrity repair (run on staging/production after deploy).

Fixes:
  1. Duplicate active contest rows per (category, contest_mode)
  2. Duplicate nomination rows per nominator per category per round
     (merge votes → canonical row, soft-delete extras, deactivate season links)

Examples:
  cd backend
  python scripts/fix_nomination_integrity.py
  python scripts/fix_nomination_integrity.py --apply
  python scripts/fix_nomination_integrity.py --apply --round-id 12
  python scripts/fix_nomination_integrity.py --apply --overlap
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.contest_category_integrity import (
    find_active_duplicate_groups,
    find_duplicate_nominator_nomination_groups,
    repair_all_nomination_integrity,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair duplicate contests and duplicate nominator nominations"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write fixes to DB (default: dry-run audit only)",
    )
    parser.add_argument("--round-id", type=int, default=None, help="Limit nominator repair to one round")
    parser.add_argument(
        "--overlap",
        action="store_true",
        help="After repairs, run cleanup_country_regional_overlap.py --all-nomination",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        dup_contests = find_active_duplicate_groups(db)
        dup_nominators = find_duplicate_nominator_nomination_groups(db, round_id=args.round_id)

        print("=== Audit ===\n")
        if dup_contests:
            print(f"Duplicate contest rows: {len(dup_contests)} group(s)")
            for g in dup_contests:
                print(f"  {g['key']} -> contest ids {g['contest_ids']}")
        else:
            print("Duplicate contest rows: none")

        if dup_nominators:
            print(f"\nDuplicate nominator nominations: {len(dup_nominators)} group(s)")
            for g in dup_nominators:
                print(
                    f"  user_id={g['user_id']} round={g['round_id']} "
                    f"scope={g['category_scope']} contestants={g['contestant_ids']} "
                    f"scores={g['scores']}"
                )
        else:
            print("\nDuplicate nominator nominations: none")

        if not dup_contests and not dup_nominators:
            print("\nNothing to repair.")
            return 0

        print(f"\n=== Repair ({'APPLY' if args.apply else 'dry-run'}) ===\n")
        result = repair_all_nomination_integrity(
            db, apply=args.apply, round_id=args.round_id
        )

        for act in result.get("contest_row_repairs") or []:
            print(
                f"  contest id={act['contest_id']} -> mode={act['set_contest_mode']} "
                f"level={act['set_level']} ({act['reason']})"
            )
        for act in result.get("duplicate_nominator_repairs") or []:
            print(
                f"  keep contestant {act['keep_contestant_id']}, "
                f"remove {act['remove_contestant_id']} "
                f"(user {act['user_id']}, {act['category_scope']})"
            )

        if not args.apply:
            print("\nRe-run with --apply to commit.")
            return 0

        if args.overlap:
            script = Path(__file__).resolve().parent / "cleanup_country_regional_overlap.py"
            print("\n=== Country/regional overlap cleanup ===\n")
            subprocess.run(
                [sys.executable, str(script), "--all-nomination", "--apply"],
                check=False,
            )

        print("\nDone. Restart API and hard-refresh contest pages.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
