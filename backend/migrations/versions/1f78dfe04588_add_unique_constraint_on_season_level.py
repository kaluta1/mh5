"""add_unique_constraint_on_season_level

Revision ID: 1f78dfe04588
Revises: 96848672da85
Create Date: 2025-11-27 11:24:11.036888

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f78dfe04588'
down_revision = '96848672da85'
branch_labels = None
depends_on = None


def upgrade():
    # Add unique constraint on level column in contest_seasons table
    # First, we need to handle any duplicate levels by keeping only one active season per level
    op.execute("""
        DO $$ 
        DECLARE
            dup_level RECORD;
            has_is_deleted BOOLEAN;
        BEGIN
            -- Check if is_deleted column exists
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'is_deleted'
            ) INTO has_is_deleted;
            
            IF has_is_deleted THEN
                -- For each duplicate level, keep only the first one (by id) and mark others as deleted
                FOR dup_level IN 
                    SELECT level, array_agg(id ORDER BY id) as ids
                    FROM contest_seasons
                    WHERE is_deleted = false
                    GROUP BY level
                    HAVING count(*) > 1
                LOOP
                    -- Keep the first id, mark others as deleted
                    UPDATE contest_seasons
                    SET is_deleted = true
                    WHERE level = dup_level.level
                      AND id != dup_level.ids[1]
                      AND is_deleted = false;
                END LOOP;
            ELSE
                -- If is_deleted doesn't exist, just delete duplicates (keep first one by id)
                FOR dup_level IN 
                    SELECT level, array_agg(id ORDER BY id) as ids
                    FROM contest_seasons
                    GROUP BY level
                    HAVING count(*) > 1
                LOOP
                    -- Delete all but the first one
                    DELETE FROM contest_seasons
                    WHERE level = dup_level.level
                      AND id != dup_level.ids[1];
                END LOOP;
            END IF;
        END $$;
    """)
    
    # Now add the unique constraint
    # Check if is_deleted column exists to determine if we need a partial index
    op.execute("""
        DO $$ 
        DECLARE
            has_is_deleted BOOLEAN;
        BEGIN
            -- Check if is_deleted column exists
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'is_deleted'
            ) INTO has_is_deleted;
            
            IF has_is_deleted THEN
                -- Create partial unique index for active seasons only
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = 'uq_contest_seasons_level_active'
                ) THEN
                    CREATE UNIQUE INDEX uq_contest_seasons_level_active 
                    ON contest_seasons (level) 
                    WHERE is_deleted = false;
                END IF;
            ELSE
                -- Create simple unique index if is_deleted doesn't exist
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = 'uq_contest_seasons_level_active'
                ) THEN
                    CREATE UNIQUE INDEX uq_contest_seasons_level_active 
                    ON contest_seasons (level);
                END IF;
            END IF;
        END $$;
    """)


def downgrade():
    # Drop the unique index
    op.drop_index('uq_contest_seasons_level_active', table_name='contest_seasons')
