"""merge_final_heads

Revision ID: 90abe9f932ab
Revises: 6d82036388b2, add_vote_rankings
Create Date: 2026-01-29 15:30:36.180581

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '90abe9f932ab'
down_revision = ('6d82036388b2', 'add_vote_rankings')  # Merge both heads
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
