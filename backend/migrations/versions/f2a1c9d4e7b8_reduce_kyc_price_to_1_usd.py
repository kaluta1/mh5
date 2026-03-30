"""reduce kyc price to 1 usd

Revision ID: f2a1c9d4e7b8
Revises: 90abe9f932ab
Create Date: 2026-03-30 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a1c9d4e7b8'
down_revision = '90abe9f932ab'
branch_labels = None
depends_on = None


def upgrade():
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


def downgrade():
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
