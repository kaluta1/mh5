"""restore kyc price to 10 usd

Revision ID: 20260330_restore_kyc_price_to_10_usd
Revises: 20260330_accounting_rollout
Create Date: 2026-03-30 22:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260330_restore_kyc_price_to_10_usd"
down_revision = "20260330_accounting_rollout"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            UPDATE product_types
            SET price = 10.00,
                updated_at = NOW()
            WHERE code = 'kyc'
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            """
            UPDATE product_types
            SET price = 1.00,
                updated_at = NOW()
            WHERE code = 'kyc'
            """
        )
    )
