"""Add is_deleted column to comment table

Revision ID: add_is_deleted_to_comment
Revises: 
Create Date: 2025-11-22 13:52:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_deleted_to_comment'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_deleted column to comment table
    # Add is_deleted column if it doesn't exist
    op.execute("""
        DO $$ BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'comment' AND column_name = 'is_deleted'
            ) THEN
                ALTER TABLE comment ADD COLUMN is_deleted BOOLEAN DEFAULT false NOT NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove is_deleted column from comment table
    op.drop_column('comment', 'is_deleted')
