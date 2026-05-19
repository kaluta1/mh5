"""
Full nomination integrity repair (run on staging/production after deploy).

Fixes:
  1. Duplicate active contest rows per (category, contest_mode)
  2. Duplicate nomination rows per nominator per category per round
     (merge votes → canonical row, soft-delete extras, deactivate season links)

Requires the backend virtualenv OR the API Docker container (system python has no pydantic).

Examples (from repo root ~/mh5):

  # Docker (recommended — same deps + DATABASE_URL as the API):
  docker compose -f backend/docker-compose.yml exec app python scripts/fix_nomination_integrity.py
  docker compose -f backend/docker-compose.yml exec app python scripts/fix_nomination_integrity.py --apply

  # Or use the helper script:
  bash backend/scripts/run_fix_nomination_integrity.sh
  bash backend/scripts/run_fix_nomination_integrity.sh --apply --overlap

  # Host venv (only if API is not in Docker):
  cd backend && python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  python scripts/fix_nomination_integrity.py --apply
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))


def _ensure_backend_deps() -> None:
    try:
        import pydantic  # noqa: F401
    except ModuleNotFoundError:
        print(
            "ERROR: Backend dependencies are not installed for this Python.\n\n"
            "Use ONE of:\n"
            "  1) Docker (same env as API):\n"
            "     docker compose -f backend/docker-compose.yml exec app "
            "python scripts/fix_nomination_integrity.py\n\n"
            "  2) Host venv:\n"
            "     cd backend && python3 -m venv .venv && source .venv/bin/activate\n"
            "     pip install -r requirements.txt\n"
            "     python scripts/fix_nomination_integrity.py\n\n"
            "  3) Helper:\n"
            "     bash backend/scripts/run_fix_nomination_integrity.sh\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


_ensure_backend_deps()

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
