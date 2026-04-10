"""
journal_entries.status: legacy PostgreSQL enum `entrystatus` uses uppercase labels (POSTED);
VARCHAR columns (after migration f1a2b3c4d5e6) use lowercase (posted).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# Cache per engine URL so we don't query information_schema on every journal insert.
_cache: dict[str, str] = {}


def posted_status_literal_for_db(db: Session) -> str:
    """Value to store for a posted journal entry for this database's status column type."""
    bind = db.get_bind()
    key = str(bind.url)
    if key in _cache:
        return _cache[key]

    row = db.execute(
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
    udt = (row[0] or "").lower() if row else ""
    if udt in ("varchar", "text", "bpchar"):
        literal = "posted"
    else:
        # Native enum (e.g. entrystatus) — rejects lowercase 'posted'
        literal = "POSTED"
    _cache[key] = literal
    return literal
