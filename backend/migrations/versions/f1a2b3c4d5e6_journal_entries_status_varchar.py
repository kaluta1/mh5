"""journal_entries.status: use VARCHAR for lowercase posted/draft/reversed.

PostgreSQL deployments may have a native `entrystatus` enum whose labels do not match
Python's EntryStatus values (e.g. rejects 'posted'). Store plain VARCHAR instead.

Revision ID: f1a2b3c4d5e6
Revises: c1a2b3c4d5e6
Create Date: 2026-04-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "f1a2b3c4d5e6"
down_revision = "c1a2b3c4d5e6"
branch_labels = None
depends_on = None


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


def downgrade() -> None:
    # Recreating a matching PG enum is environment-specific; leave as VARCHAR.
    pass
