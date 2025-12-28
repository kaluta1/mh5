"""Add cover_image_url to contest table

Revision ID: add_cover_image_url_contest
Revises: add_mfm_annual_prods
Create Date: 2025-12-28 01:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_cover_image_url_contest'
down_revision = 'add_mfm_annual_prods'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add cover_image_url column if it doesn't exist
    op.execute("""
        DO $$ BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' AND column_name = 'cover_image_url'
            ) THEN
                ALTER TABLE contest ADD COLUMN cover_image_url VARCHAR(500);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove cover_image_url column
    op.execute("""
        DO $$ BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' AND column_name = 'cover_image_url'
            ) THEN
                ALTER TABLE contest DROP COLUMN cover_image_url;
            END IF;
        END $$;
    """)

