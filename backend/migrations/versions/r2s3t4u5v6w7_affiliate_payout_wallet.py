"""Affiliate payout wallet fields and cashout audit table.

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


revision = "r2s3t4u5v6w7"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("usdt_wallet_address", sa.String(length=100), nullable=True))
    op.add_column(
        "users",
        sa.Column("payout_currency", sa.String(length=20), nullable=True, server_default="usdtbsc"),
    )

    op.add_column(
        "affiliate_commissions",
        sa.Column("payout_reference", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "affiliate_cashout_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("fee", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("payout_method", sa.String(length=30), nullable=True, server_default="nowpayments_crypto"),
        sa.Column("wallet_snapshot", sa.String(length=100), nullable=True),
        sa.Column("payout_reference", sa.String(length=255), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_affiliate_cashout_requests_user_id", "affiliate_cashout_requests", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_affiliate_cashout_requests_user_id", table_name="affiliate_cashout_requests")
    op.drop_table("affiliate_cashout_requests")
    op.drop_column("affiliate_commissions", "payout_reference")
    op.drop_column("users", "payout_currency")
    op.drop_column("users", "usdt_wallet_address")
