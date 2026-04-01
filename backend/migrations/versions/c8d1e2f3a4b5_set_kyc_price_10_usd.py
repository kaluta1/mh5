"""set kyc product price to 10 usd

Revision ID: c8d1e2f3a4b5
Revises: f2a1c9d4e7b8
Create Date: 2026-04-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c8d1e2f3a4b5"
down_revision = "f2a1c9d4e7b8"
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
