"""Merge migration branches

Revision ID: 4443c46923b6
Revises: add_is_deleted_to_comment, add_contest_participant_count, d663619d4a51
Create Date: 2025-11-22 15:29:07.549304

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4443c46923b6'
down_revision = ('add_is_deleted_to_comment', 'add_contest_participant_count', 'd663619d4a51')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
