"""merge_all_heads_final

Revision ID: 6d82036388b2
Revises: 9188658746fb, add_affiliate_agreement, fix_crypto_amount_wei
Create Date: 2026-01-29 12:38:28.988119

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d82036388b2'
down_revision = ('9188658746fb', 'add_affiliate_agreement', 'fix_crypto_amount_wei')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
