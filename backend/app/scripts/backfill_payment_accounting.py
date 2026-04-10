"""
CLI: backfill payment journals, KYC Step 2 recognition, and Founding pool (2104) corrections.

From your project backend directory (example: cd ~/mh5/backend), not a placeholder path.

  python scripts/backfill_payment_accounting.py --dry-run
  python scripts/backfill_payment_accounting.py --kyc-recognition --dry-run
  python scripts/backfill_payment_accounting.py --kyc-recognition
  python scripts/backfill_payment_accounting.py --founding-pool --dry-run
  python scripts/backfill_payment_accounting.py --all --dry-run
  python scripts/backfill_payment_accounting.py --all
"""

from __future__ import annotations

import argparse
import json
import sys

BACKFILL_CLI_VERSION = "4"

from app.db.session import SessionLocal
from app.services.payment_accounting_backfill import (
    backfill_missing_founding_pool_accruals,
    backfill_missing_kyc_recognition,
    backfill_missing_payment_journals,
)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Accounting backfills (run from backend/ with .env pointing at production DB).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"CLI revision {BACKFILL_CLI_VERSION}. "
            "If --kyc-recognition and --all are missing on the server, git pull and redeploy this repo."
        ),
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {BACKFILL_CLI_VERSION}",
    )
    p.add_argument("--dry-run", action="store_true", help="No DB writes (where supported)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--founding-pool",
        action="store_true",
        help="Only 2104 accrual lines (membership/club/KYC after recognition is posted)",
    )
    mode.add_argument(
        "--kyc-recognition",
        action="store_true",
        help="Only KYC Step 2: posts 4001 / 2104 / 2003 when user is APPROVED and Step 1 exists",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Run KYC recognition, then payment journals, then founding-pool (same order as dry-run)",
    )
    args = p.parse_args()

    db = SessionLocal()
    try:
        if args.all:
            result = {
                "kyc_recognition": backfill_missing_kyc_recognition(db, dry_run=args.dry_run),
                "payment_journals": backfill_missing_payment_journals(db, dry_run=args.dry_run),
                "founding_pool": backfill_missing_founding_pool_accruals(db, dry_run=args.dry_run),
            }
            print(json.dumps(result, indent=2, default=str))
            errs = []
            for part in result.values():
                if isinstance(part, dict) and part.get("errors"):
                    errs.extend(part["errors"])
            if errs:
                sys.exit(1)
        elif args.founding_pool:
            result = backfill_missing_founding_pool_accruals(db, dry_run=args.dry_run)
            print(json.dumps(result, indent=2, default=str))
            if result.get("errors"):
                sys.exit(1)
        elif args.kyc_recognition:
            result = backfill_missing_kyc_recognition(db, dry_run=args.dry_run)
            print(json.dumps(result, indent=2, default=str))
            if result.get("errors"):
                sys.exit(1)
        else:
            result = backfill_missing_payment_journals(db, dry_run=args.dry_run)
            print(json.dumps(result, indent=2, default=str))
            if result.get("errors"):
                sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
