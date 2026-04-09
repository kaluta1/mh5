"""Add chart_of_accounts.balance if missing (legacy DBs).

Revision ID: c1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-04-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c1a2b3c4d5e6"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def _column_exists(bind, table: str, column: str) -> bool:
    insp = inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "chart_of_accounts", "balance"):
        return
    op.add_column(
        "chart_of_accounts",
        sa.Column("balance", sa.Numeric(precision=15, scale=2), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "chart_of_accounts", "balance"):
        return
    op.drop_column("chart_of_accounts", "balance")
