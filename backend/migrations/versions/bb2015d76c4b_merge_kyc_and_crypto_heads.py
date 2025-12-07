"""merge_kyc_and_crypto_heads

Revision ID: bb2015d76c4b
Revises: add_kyc_commission, update_deposits_crypto
Create Date: 2025-12-07 12:49:18.883639

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bb2015d76c4b'
down_revision = ('add_kyc_commission', 'update_deposits_crypto')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
