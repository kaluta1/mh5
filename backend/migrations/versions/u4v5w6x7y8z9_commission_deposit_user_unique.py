"""Deduplicate affiliate commissions per deposit and enforce uniqueness.

Revision ID: u4v5w6x7y8z9
Revises: r2s3t4u5v6w7
Create Date: 2026-08-12
"""
from alembic import op


revision = "u4v5w6x7y8z9"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep earliest level (then lowest id) when sponsor cycles created duplicate rows.
    op.execute(
        """
        DELETE FROM affiliate_commissions a
        USING affiliate_commissions b
        WHERE a.deposit_id IS NOT NULL
          AND a.deposit_id = b.deposit_id
          AND a.user_id = b.user_id
          AND (
            a.level > b.level
            OR (a.level = b.level AND a.id > b.id)
          )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_affiliate_commissions_deposit_user
        ON affiliate_commissions (deposit_id, user_id)
        WHERE deposit_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_affiliate_commissions_deposit_user")
