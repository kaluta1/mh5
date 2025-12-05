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
        BEGIN
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
        END $$;
    """)
    
    # Now add the unique constraint (only on non-deleted seasons)
    # We'll use a partial unique index since we only want uniqueness for active seasons
    op.create_index(
        'uq_contest_seasons_level_active',
        'contest_seasons',
        ['level'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false'),
        if_not_exists=True
    )


def downgrade():
    # Drop the unique index
    op.drop_index('uq_contest_seasons_level_active', table_name='contest_seasons')
