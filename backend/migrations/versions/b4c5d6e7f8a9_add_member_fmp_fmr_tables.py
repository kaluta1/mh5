"""Add member FMP ledger and balances for FMR pool weights.

Revision ID: b4c5d6e7f8a9
Revises: p8q9r0s1t2u3
Create Date: 2026-04-23

"""
from alembic import op
import sqlalchemy as sa


revision = "b4c5d6e7f8a9"
down_revision = "p8q9r0s1t2u3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "member_fmp_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("points", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "user_id",
            name="uq_member_fmp_ledger_source_user",
        ),
    )
    op.create_index(
        "ix_member_fmp_ledger_user_id", "member_fmp_ledger", ["user_id"], unique=False
    )

    op.create_table(
        "member_fmp_balances",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "total_fmp",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade():
    op.drop_table("member_fmp_balances")
    op.drop_table("member_fmp_ledger")
