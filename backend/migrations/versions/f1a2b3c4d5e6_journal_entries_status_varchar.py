"""journal_entries.status: use VARCHAR for lowercase posted/draft/reversed.

PostgreSQL deployments may have a native `entrystatus` enum whose labels do not match
Python's EntryStatus values (e.g. rejects 'posted'). Store plain VARCHAR instead.

Revision ID: f1a2b3c4d5e6
Revises: c1a2b3c4d5e6
Create Date: 2026-04-09

"""
import warnings

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError, OperationalError


revision = "f1a2b3c4d5e6"
down_revision = "c1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _is_privilege_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    orig = getattr(exc, "orig", None)
    if orig is not None:
        msg += " " + str(orig).lower()
    return (
        "must be owner" in msg
        or "insufficientprivilege" in msg.replace(" ", "")
        or "permission denied" in msg
    )


def _journal_status_is_varchar(bind) -> bool:
    row = bind.execute(
        text(
            """
            SELECT c.data_type, c.udt_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = 'journal_entries'
              AND c.column_name = 'status'
            """
        )
    ).fetchone()
    if not row:
        return False
    udt = (row[1] or "").lower()
    return udt in ("varchar", "text", "bpchar")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    insp = inspect(bind)
    if not insp.has_table("journal_entries"):
        return
    colset = {c["name"] for c in insp.get_columns("journal_entries")}
    if "status" not in colset:
        return
    if _journal_status_is_varchar(bind):
        return

    try:
        op.execute(text("ALTER TABLE journal_entries ALTER COLUMN status DROP DEFAULT"))
        op.execute(
            text(
                """
                ALTER TABLE journal_entries
                ALTER COLUMN status TYPE VARCHAR(20)
                USING (lower(status::text))
                """
            )
        )
        op.execute(text("ALTER TABLE journal_entries ALTER COLUMN status SET DEFAULT 'posted'"))
    except (ProgrammingError, OperationalError) as e:
        if _is_privilege_error(e):
            warnings.warn(
                "journal_entries.status was not converted to VARCHAR (DB user is not table owner). "
                "Run backend/scripts/sql/fix_accounting_schema_privileged.sql as PostgreSQL superuser.",
                stacklevel=1,
            )
            return
        raise


def downgrade() -> None:
    # Recreating a matching PG enum is environment-specific; leave as VARCHAR.
    pass
