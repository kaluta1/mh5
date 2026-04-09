#!/usr/bin/env python3
"""
Fix alembic_version when multiple rows exist (e.g. add_social_groups + 20260330_accounting_rollout).

The merge revision e8f9a0b1c2d3 already combines accounting and add_social_groups; a leftover
add_social_groups row causes: "overlaps with other requested revisions add_social_groups".

Usage (from backend/):
  python scripts/fix_alembic_duplicate_version_rows.py
  python scripts/fix_alembic_duplicate_version_rows.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL missing", file=sys.stderr)
        return 1

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num")).fetchall()
        versions = [r[0] for r in rows]
        print("alembic_version rows:", versions)

        if len(versions) <= 1:
            print("Nothing to fix.")
            return 0

        # Stale branch head: add_social_groups is merged into e8f9a0b1c2d3; if another row exists, drop this one.
        stale = "add_social_groups"
        if stale in versions and len(versions) == 2:
            if args.dry_run:
                print(f"Would DELETE FROM alembic_version WHERE version_num = '{stale}'")
                return 0
            conn.execute(text("DELETE FROM alembic_version WHERE version_num = :v"), {"v": stale})
            conn.commit()
            rows2 = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            print("After fix:", [r[0] for r in rows2])
            return 0

        print(
            "Multiple rows but not the expected pair; fix manually or extend this script.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
