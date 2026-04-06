"""Align chart_of_accounts with Base; add journal_entries / journal_lines if missing.

Revision ID: a7f3e2d1c4b8
Revises: (set in file)
Create Date: 2026-04-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "a7f3e2d1c4b8"
down_revision = "b3e7a1c2d4f6"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return inspect(bind).has_table(name)


def _column_exists(bind, table: str, column: str) -> bool:
    insp = inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    # chart_of_accounts: Base model expects id, created_at, updated_at (002 only had created_at)
    if _table_exists(bind, "chart_of_accounts"):
        if not _column_exists(bind, "chart_of_accounts", "updated_at"):
            op.add_column(
                "chart_of_accounts",
                sa.Column("updated_at", sa.DateTime(), nullable=True),
            )
            op.execute(
                "UPDATE chart_of_accounts SET updated_at = COALESCE(created_at, NOW()) WHERE updated_at IS NULL"
            )

    if not _table_exists(bind, "journal_entries"):
        op.create_table(
            "journal_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("entry_number", sa.String(length=50), nullable=False),
            sa.Column("entry_date", sa.DateTime(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("threshold", sa.Numeric(precision=15, scale=2), nullable=True),
            sa.Column("total_debit", sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column("total_credit", sa.Numeric(precision=15, scale=2), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="posted"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("posted_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("entry_number"),
        )

    if not _table_exists(bind, "journal_lines"):
        op.create_table(
            "journal_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("entry_id", sa.Integer(), nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("debit_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
            sa.Column("credit_amount", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["entry_id"], ["journal_entries.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["account_id"], ["chart_of_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "journal_lines"):
        op.drop_table("journal_lines")
    if _table_exists(bind, "journal_entries"):
        op.drop_table("journal_entries")
    if _table_exists(bind, "chart_of_accounts") and _column_exists(bind, "chart_of_accounts", "updated_at"):
        op.drop_column("chart_of_accounts", "updated_at")
