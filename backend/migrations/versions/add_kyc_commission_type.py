"""Add KYC_PAYMENT and EFM_MEMBERSHIP to CommissionType enum

Revision ID: add_kyc_commission
Revises: 
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_kyc_commission'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new enum values to commissiontype
    # PostgreSQL requires ALTER TYPE to add new values to an enum
    op.execute("ALTER TYPE commissiontype ADD VALUE IF NOT EXISTS 'kyc_payment'")
    op.execute("ALTER TYPE commissiontype ADD VALUE IF NOT EXISTS 'efm_membership'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values easily
    # This would require recreating the enum type
    pass
