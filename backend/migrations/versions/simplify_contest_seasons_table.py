"""Simplify contest_seasons table

Revision ID: simplify_contest_seasons
Revises: 4443c46923b6
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'simplify_contest_seasons'
down_revision = 'add_is_deleted_contestants'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    insp = inspect(bind)
    
    def column_exists(table_name, column_name):
        if table_name not in insp.get_table_names():
            return False
        columns = [c['name'] for c in insp.get_columns(table_name)]
        return column_name in columns
    
    # Create SeasonLevel enum type
    op.execute("""
        DO $$ BEGIN 
            CREATE TYPE seasonlevel AS ENUM ('city', 'country', 'regional', 'continent', 'global');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Check if columns exist before dropping foreign key
    # Drop foreign key constraint to contest_types if it exists
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE contest_seasons DROP CONSTRAINT IF EXISTS contest_seasons_contest_type_id_fkey;
        EXCEPTION WHEN undefined_object THEN null;
        END $$;
    """)
    
    # Add level column only if it doesn't exist
    if not column_exists('contest_seasons', 'level'):
        # Use the enum type we just created
        level_enum = postgresql.ENUM('city', 'country', 'regional', 'continent', 'global', name='seasonlevel', create_type=False)
        level_enum.create(op.get_bind(), checkfirst=True)
        op.add_column('contest_seasons', sa.Column('level', level_enum, nullable=True))
        
        # Set default value for existing rows
        op.execute("UPDATE contest_seasons SET level = 'city' WHERE level IS NULL")
        
        # Make level NOT NULL
        op.alter_column('contest_seasons', 'level', nullable=False)
    
    # Make title NOT NULL (if it's not already)
    # First check if title column exists, if yes, set a default and make it NOT NULL
    op.execute("""
        DO $$ 
        BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest_seasons' AND column_name = 'title'
            ) THEN
                BEGIN
                    UPDATE contest_seasons SET title = 'Saison sans titre' WHERE title IS NULL;
                    ALTER TABLE contest_seasons ALTER COLUMN title SET NOT NULL;
                EXCEPTION WHEN OTHERS THEN
                    -- Column might not exist or already NOT NULL, ignore
                    NULL;
                END;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- Table or column might not exist, ignore
            NULL;
        END $$;
    """)
    
    # Drop obsolete columns (check if they exist first)
    op.execute("""
        DO $$ BEGIN
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


def downgrade():
    # Re-add dropped columns
    op.add_column('contest_seasons', sa.Column('contest_type_id', sa.Integer(), nullable=True))
    op.add_column('contest_seasons', sa.Column('year', sa.Integer(), nullable=True))
    op.add_column('contest_seasons', sa.Column('season_number', sa.Integer(), nullable=True))
    op.add_column('contest_seasons', sa.Column('status', postgresql.ENUM('UPCOMING', 'UPLOAD_PHASE', 'VOTING_ACTIVE', 'VOTING_ENDED', 'COMPLETED', 'CANCELLED', name='conteststatus'), nullable=True))
    op.add_column('contest_seasons', sa.Column('start_date', sa.DateTime(), nullable=True))
    op.add_column('contest_seasons', sa.Column('end_date', sa.DateTime(), nullable=True))
    op.add_column('contest_seasons', sa.Column('upload_end_date', sa.DateTime(), nullable=True))
    
    # Re-add foreign key constraint
    op.create_foreign_key('contest_seasons_contest_type_id_fkey', 'contest_seasons', 'contest_types', ['contest_type_id'], ['id'])
    
    # Make title nullable again
    op.alter_column('contest_seasons', 'title', nullable=True)
    
    # Drop level column
    op.drop_column('contest_seasons', 'level')
    
    # Drop enum type
    op.execute('DROP TYPE IF EXISTS seasonlevel')

