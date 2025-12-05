"""Add participant_count to contest table

Revision ID: add_contest_participant_count
Revises: add_contest_admin_fields
Create Date: 2025-11-21 18:55:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_contest_participant_count'
down_revision = 'add_contest_admin_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add participant_count column if it doesn't exist
    op.execute("""
        DO $$ BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' AND column_name = 'participant_count'
            ) THEN
                ALTER TABLE contest ADD COLUMN participant_count INTEGER DEFAULT 0 NOT NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove participant_count column
    op.drop_column('contest', 'participant_count')
