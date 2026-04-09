#!/usr/bin/env python3
"""
Backfill journal entries for validated deposits missing from the ledger.

Run from the backend directory (same as other scripts in this folder):

  cd /path/to/backend
  python scripts/backfill_payment_accounting.py --dry-run
  python scripts/backfill_payment_accounting.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Repo root = parent of scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.payment_accounting_backfill import backfill_missing_payment_journals


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill payment accounting journals")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List deposits that would get journals; no writes",
    )
    args = p.parse_args()

    db = SessionLocal()
    try:
        result = backfill_missing_payment_journals(db, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, default=str))
        if result.get("errors"):
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
