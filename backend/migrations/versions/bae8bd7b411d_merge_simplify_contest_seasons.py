"""merge simplify_contest_seasons

Revision ID: bae8bd7b411d
Revises: 4443c46923b6, simplify_contest_seasons
Create Date: 2025-11-27 10:34:37.517039

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bae8bd7b411d'
down_revision = ('4443c46923b6', 'simplify_contest_seasons')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
