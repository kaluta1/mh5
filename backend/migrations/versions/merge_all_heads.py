"""Merge all migration heads

Revision ID: merge_all_heads
Revises: d7831cdf8d92, add_sponsor_id
Create Date: 2025-12-05

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_all_heads'
down_revision = ('d7831cdf8d92', 'add_sponsor_id')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
