"""Add preferred_language to users table

Revision ID: add_preferred_language
Revises: add_mfm_annual_prods
Create Date: 2024-12-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_preferred_language'
down_revision = 'add_mfm_annual_prods'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add preferred_language column with default 'fr'
    op.add_column('users', sa.Column('preferred_language', sa.String(5), nullable=False, server_default='fr'))


def downgrade() -> None:
    op.drop_column('users', 'preferred_language')
