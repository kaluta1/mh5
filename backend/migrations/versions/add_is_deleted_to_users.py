"""Add is_deleted column to users table

Revision ID: add_is_deleted_users
Revises: d663619d4a51
Create Date: 2025-11-22 15:26:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_deleted_users'
down_revision = 'd663619d4a51'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_deleted column to users table
    op.add_column('users', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove is_deleted column from users table
    op.drop_column('users', 'is_deleted')
