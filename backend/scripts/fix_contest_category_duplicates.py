"""
Audit / repair duplicate contest rows per category (nomination vs participation).

Examples:
  cd backend
  python scripts/fix_contest_category_duplicates.py
  python scripts/fix_contest_category_duplicates.py --apply
  python scripts/fix_contest_category_duplicates.py --contest-id 42
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.contest_category_integrity import (
    find_active_duplicate_groups,
    repair_category_mode_duplicates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix duplicate category contest_mode rows")
    parser.add_argument("--apply", action="store_true", help="Write fixes to DB")
    parser.add_argument("--contest-id", type=int, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        groups = find_active_duplicate_groups(db, contest_id=args.contest_id)
        if not groups:
            print("OK: no duplicate active contests per (category, contest_mode).")
            return 0

        print(f"Found {len(groups)} duplicate group(s):\n")
        for g in groups:
            print(f"  {g['key']} -> ids {g['contest_ids']}")
            for d in g["details"]:
                print(
                    f"    id={d['id']} mode={d['contest_mode']} level={d['level']} "
                    f"name={d['name']!r} participants={d['participant_count']}"
                )

        actions = repair_category_mode_duplicates(db, apply=args.apply)
        if not actions:
            print("\nNo automatic repair actions (manual admin review needed).")
            return 1

        print(f"\nPlanned repairs ({'APPLY' if args.apply else 'dry-run'}):")
        for act in actions:
            print(
                f"  id={act['contest_id']} -> mode={act['set_contest_mode']} "
                f"level={act['set_level']} ({act['reason']})"
            )
        if not args.apply:
            print("\nRe-run with --apply to commit.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
