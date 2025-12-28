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
    """Add title, is_deleted, created_at, and updated_at columns to contest_seasons if they don't exist"""
    # Add title column if it doesn't exist
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
    
    # Add is_deleted column if it doesn't exist
    if not column_exists('contest_seasons', 'is_deleted'):
        op.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'contest_seasons' AND column_name = 'is_deleted'
                ) THEN
                    ALTER TABLE contest_seasons ADD COLUMN is_deleted BOOLEAN DEFAULT false NOT NULL;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)
    
    # Add created_at column if it doesn't exist
    if not column_exists('contest_seasons', 'created_at'):
        op.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'contest_seasons' AND column_name = 'created_at'
                ) THEN
                    ALTER TABLE contest_seasons ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)
    
    # Add updated_at column if it doesn't exist
    if not column_exists('contest_seasons', 'updated_at'):
        op.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'contest_seasons' AND column_name = 'updated_at'
                ) THEN
                    ALTER TABLE contest_seasons ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)
    
    # Drop obsolete columns that are no longer in the model
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS registration_start;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS registration_end;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS contest_type_id;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS year;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS season_number;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS status;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS start_date;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS end_date;
            ALTER TABLE contest_seasons DROP COLUMN IF EXISTS upload_end_date;
        EXCEPTION WHEN undefined_column THEN null;
        END $$;
    """)
    
    # Convert contest.level from ENUM to VARCHAR(20) if it's still an ENUM
    op.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' 
                AND column_name = 'level'
                AND udt_name = 'contest_level'
            ) THEN
                ALTER TABLE contest ALTER COLUMN level TYPE VARCHAR(20) USING level::text;
                
                -- Drop the ENUM type if it's no longer used
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE udt_name = 'contest_level'
                ) THEN
                    DROP TYPE IF EXISTS contest_level;
                END IF;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)


def downgrade():
    """Remove title, is_deleted, created_at, and updated_at columns from contest_seasons"""
    op.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'title'
            ) THEN
                ALTER TABLE contest_seasons DROP COLUMN title;
            END IF;
            
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'is_deleted'
            ) THEN
                ALTER TABLE contest_seasons DROP COLUMN is_deleted;
            END IF;
            
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'created_at'
            ) THEN
                ALTER TABLE contest_seasons DROP COLUMN created_at;
            END IF;
            
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE contest_seasons DROP COLUMN updated_at;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
