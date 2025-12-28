"""add_title_to_contest_seasons

Revision ID: 9188658746fb
Revises: fix_voting_type_contest
Create Date: 2025-12-28 04:06:11.013413

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '9188658746fb'
down_revision = 'fix_voting_type_contest'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    insp = inspect(bind)
    if table_name not in insp.get_table_names():
        return False
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Add title column to contest_seasons if it doesn't exist"""
    if not column_exists('contest_seasons', 'title'):
        op.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'contest_seasons' AND column_name = 'title'
                ) THEN
                    ALTER TABLE contest_seasons ADD COLUMN title VARCHAR(200);
                    UPDATE contest_seasons SET title = 'Saison sans titre' WHERE title IS NULL;
                    ALTER TABLE contest_seasons ALTER COLUMN title SET NOT NULL;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)


def downgrade():
    """Remove title column from contest_seasons"""
    op.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'title'
            ) THEN
                ALTER TABLE contest_seasons DROP COLUMN title;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
