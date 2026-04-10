#!/usr/bin/env python3
"""
Backfill payment journals and optional Founding pool (2104) accrual corrections.

Run from the backend directory:

  cd /path/to/backend
  python scripts/backfill_payment_accounting.py --dry-run
  python scripts/backfill_payment_accounting.py
  python scripts/backfill_payment_accounting.py --founding-pool --dry-run
  python scripts/backfill_payment_accounting.py --founding-pool
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Repo root = parent of scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.payment_accounting_backfill import (
    backfill_missing_founding_pool_accruals,
    backfill_missing_payment_journals,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill payment accounting journals")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="No DB writes (where supported)",
    )
    p.add_argument(
        "--founding-pool",
        action="store_true",
        help="Only run 2104 accrual backfill (journals exist but pool line missing)",
    )
    args = p.parse_args()

    db = SessionLocal()
    try:
        if args.founding_pool:
            result = backfill_missing_founding_pool_accruals(db, dry_run=args.dry_run)
        else:
            result = backfill_missing_payment_journals(db, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, default=str))
        if result.get("errors"):
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
