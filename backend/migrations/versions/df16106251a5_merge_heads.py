"""merge_heads

Revision ID: df16106251a5
Revises: add_contest_verification, add_media_reqs_001
Create Date: 2025-12-08 15:20:46.135346

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'df16106251a5'
down_revision = ('add_contest_verification', 'add_media_reqs_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
