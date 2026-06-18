#!/usr/bin/env python3
"""
Apply accounting DDL from DATABASE_URL (same user as the app — needs table owner / sufficient rights).

  cd backend
  python scripts/apply_accounting_schema_fix.py

Uses backend/.env via app.core.config. Safe to re-run: skips journal status conversion if already VARCHAR.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from app.core.config import settings


def _journal_status_is_varchar(conn) -> bool:
    row = conn.execute(
        text(
            """
            SELECT c.udt_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = 'journal_entries'
              AND c.column_name = 'status'
            """
        )
    ).fetchone()
    if not row:
        return False
    udt = (row[0] or "").lower()
    return udt in ("varchar", "text", "bpchar")


def main() -> int:
    url = settings.DATABASE_URL
    if not url or url == "postgresql://user:password@localhost/myhigh5":
        print("DATABASE_URL missing in backend/.env", file=sys.stderr)
        return 1

    engine = create_engine(url)
    insp = inspect(engine)

    if not insp.has_table("chart_of_accounts"):
        print("No chart_of_accounts table; nothing to do.")
        return 0

    with engine.begin() as conn:
        cols = {c["name"] for c in insp.get_columns("chart_of_accounts")}
        if "balance" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE chart_of_accounts ADD COLUMN balance NUMERIC(15, 2)"
                )
            )
            print("Added chart_of_accounts.balance")
        else:
            print("chart_of_accounts.balance already present")

        if insp.has_table("journal_entries"):
            if _journal_status_is_varchar(conn):
                print("journal_entries.status already VARCHAR")
            else:
                conn.execute(text("ALTER TABLE journal_entries ALTER COLUMN status DROP DEFAULT"))
                conn.execute(
                    text(
                        """
                        ALTER TABLE journal_entries
                        ALTER COLUMN status TYPE VARCHAR(20)
                        USING (lower(status::text))
                        """
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE journal_entries ALTER COLUMN status SET DEFAULT 'posted'"
                    )
                )
                print("Converted journal_entries.status to VARCHAR(20)")
        else:
            print("No journal_entries table; skipped status conversion")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
