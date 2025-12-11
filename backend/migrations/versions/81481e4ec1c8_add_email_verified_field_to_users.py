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
    """Add email_verified column to users table.

    Use IF NOT EXISTS so that if the column is already present (for example
    when the DB was manually altered or a previous migration partially ran),
    the migration does not fail.
    """
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT false NOT NULL;"
    )
def downgrade():
    """Remove email_verified column from users table (if present)."""
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS email_verified;"
    )
