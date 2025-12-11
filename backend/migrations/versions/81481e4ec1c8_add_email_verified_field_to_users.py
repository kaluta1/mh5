"""Add email_verified field to users

Revision ID: 81481e4ec1c8
Revises: add_preferred_language
Create Date: 2025-12-11 10:17:19.863138

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '81481e4ec1c8'
down_revision = 'add_preferred_language'
branch_labels = None
depends_on = None


def upgrade():
    """Add email_verified column to users table."""
    op.add_column(
        'users',
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
def downgrade():
    """Remove email_verified column from users table."""
    op.drop_column('users', 'email_verified')
