"""Affiliate payout wallet fields and cashout audit table.

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-08-05
"""
from alembic import op


revision = "r2s3t4u5v6w7"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent DDL — VPS app role may not own tables until fix_postgres_ownership.sh runs.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS usdt_wallet_address VARCHAR(100)")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS payout_currency VARCHAR(20) DEFAULT 'usdtbsc'"
    )
    op.execute(
        "ALTER TABLE affiliate_commissions ADD COLUMN IF NOT EXISTS payout_reference VARCHAR(255)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS affiliate_cashout_requests (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL REFERENCES users(id),
            gross_amount NUMERIC(10, 2) NOT NULL,
            fee NUMERIC(10, 2) NOT NULL DEFAULT 0,
            net_amount NUMERIC(10, 2) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'processing',
            payout_method VARCHAR(30) DEFAULT 'nowpayments_crypto',
            wallet_snapshot VARCHAR(100),
            payout_reference VARCHAR(255),
            requested_at TIMESTAMP NOT NULL DEFAULT now(),
            processed_at TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_affiliate_cashout_requests_user_id "
        "ON affiliate_cashout_requests (user_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_affiliate_cashout_requests_user_id", table_name="affiliate_cashout_requests")
    op.drop_table("affiliate_cashout_requests")
    op.drop_column("affiliate_commissions", "payout_reference")
    op.drop_column("users", "payout_currency")
    op.drop_column("users", "usdt_wallet_address")
