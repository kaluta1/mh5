"""merge_contact_messages_and_contestant_voting_heads

Revision ID: 5a9dda393841
Revises: add_contact_messages_table, adeb003edcef
Create Date: 2025-12-27 21:32:26.860519

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5a9dda393841'
down_revision = ('add_contact_messages_table', 'adeb003edcef')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
