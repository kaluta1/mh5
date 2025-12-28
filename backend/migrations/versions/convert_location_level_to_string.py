"""Convert location.level and contest.level from ENUM to VARCHAR

Revision ID: convert_location_level_string
Revises: add_cover_image_url_contest
Create Date: 2025-12-28 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'convert_location_level_string'
down_revision = 'add_cover_image_url_contest'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert location.level from ENUM to VARCHAR(20)
    conn = op.get_bind()
    
    # Check if location_level enum type exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type 
            WHERE typname = 'location_level'
        )
    """))
    location_enum_exists = result.fetchone()[0]
    
    if location_enum_exists:
        # Convert ENUM to VARCHAR by casting
        op.execute("""
            DO $$ 
            BEGIN 
                -- Convert the column type from ENUM to VARCHAR
                ALTER TABLE location 
                ALTER COLUMN level TYPE VARCHAR(20) 
                USING level::text;
            EXCEPTION WHEN OTHERS THEN
                -- If conversion fails, try alternative method
                BEGIN
                    -- Add a temporary column
                    ALTER TABLE location ADD COLUMN level_temp VARCHAR(20);
                    
                    -- Copy data with cast
                    UPDATE location SET level_temp = level::text;
                    
                    -- Drop old column
                    ALTER TABLE location DROP COLUMN level;
                    
                    -- Rename new column
                    ALTER TABLE location RENAME COLUMN level_temp TO level;
                    
                    -- Make it NOT NULL
                    ALTER TABLE location ALTER COLUMN level SET NOT NULL;
                END;
            END $$;
        """)
        
        # Drop the ENUM type
        op.execute("""
            DO $$ 
            BEGIN 
                DROP TYPE IF EXISTS location_level;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)
    
    # Convert contest.level from ENUM to VARCHAR(20)
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type 
            WHERE typname = 'contest_level'
        )
    """))
    contest_enum_exists = result.fetchone()[0]
    
    if contest_enum_exists:
        # Convert ENUM to VARCHAR by casting
        op.execute("""
            DO $$ 
            BEGIN 
                -- Convert the column type from ENUM to VARCHAR
                ALTER TABLE contest 
                ALTER COLUMN level TYPE VARCHAR(20) 
                USING level::text;
            EXCEPTION WHEN OTHERS THEN
                -- If conversion fails, try alternative method
                BEGIN
                    -- Add a temporary column
                    ALTER TABLE contest ADD COLUMN level_temp VARCHAR(20);
                    
                    -- Copy data with cast
                    UPDATE contest SET level_temp = level::text;
                    
                    -- Drop old column
                    ALTER TABLE contest DROP COLUMN level;
                    
                    -- Rename new column
                    ALTER TABLE contest RENAME COLUMN level_temp TO level;
                    
                    -- Make it NOT NULL
                    ALTER TABLE contest ALTER COLUMN level SET NOT NULL;
                END;
            END $$;
        """)
        
        # Drop the ENUM type
        op.execute("""
            DO $$ 
            BEGIN 
                DROP TYPE IF EXISTS contest_level;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)


def downgrade() -> None:
    # Revert to ENUM (if needed)
    # This is complex and may not be necessary, but included for completeness
    conn = op.get_bind()
    
    # Recreate the ENUM types
    op.execute("""
        DO $$ 
        BEGIN 
            CREATE TYPE location_level AS ENUM ('city', 'country', 'region', 'continent', 'global');
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END $$;
    """)
    
    op.execute("""
        DO $$ 
        BEGIN 
            CREATE TYPE contest_level AS ENUM ('city', 'country', 'region', 'continent', 'global');
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END $$;
    """)
    
    # Convert back to ENUM
    op.execute("""
        ALTER TABLE location 
        ALTER COLUMN level TYPE location_level 
        USING level::location_level;
    """)
    
    op.execute("""
        ALTER TABLE contest 
        ALTER COLUMN level TYPE contest_level 
        USING level::contest_level;
    """)

