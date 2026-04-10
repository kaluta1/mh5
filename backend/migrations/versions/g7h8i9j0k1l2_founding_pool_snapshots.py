"""Founding pool month-end snapshots (2104 -> 2105 audit).

Revision ID: g7h8i9j0k1l2
Revises: 20260330_accounting_rollout
Create Date: 2026-04-10

"""
from alembic import op
import sqlalchemy as sa


revision = "g7h8i9j0k1l2"
down_revision = "20260330_accounting_rollout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "founding_pool_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("accrued_pool_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("prepared_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("journal_entry_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_year", "period_month", name="uq_founding_pool_calendar_month"),
    )
    op.create_table(
        "founding_pool_snapshot_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("share_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("weight_ratio", sa.Numeric(12, 8), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["founding_pool_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "user_id", name="uq_founding_pool_line_user"),
    )


def downgrade() -> None:
    op.drop_table("founding_pool_snapshot_lines")
    op.drop_table("founding_pool_snapshots")
