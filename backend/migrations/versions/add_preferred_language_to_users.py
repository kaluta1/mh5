"""Add preferred_language to users table

Revision ID: add_preferred_language
Revises: add_mfm_annual_prods
Create Date: 2024-12-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'add_preferred_language'
down_revision = 'add_mfm_annual_prods'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add preferred_language column with default 'fr' if it doesn't exist
    if not column_exists('users', 'preferred_language'):
        op.add_column('users', sa.Column('preferred_language', sa.String(5), nullable=False, server_default='fr'))


def downgrade() -> None:
    if column_exists('users', 'preferred_language'):
        op.drop_column('users', 'preferred_language')
