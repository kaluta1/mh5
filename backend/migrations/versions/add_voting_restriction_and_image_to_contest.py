"""Add voting_restriction and image_url to contest table

Revision ID: add_contest_admin_fields
Revises: f9e6829e1555
Create Date: 2025-11-21 18:48:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_contest_admin_fields'
down_revision = 'f9e6829e1555'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type for voting_restriction
    voting_restriction_enum = postgresql.ENUM(
        'NONE', 'MALE_ONLY', 'FEMALE_ONLY', 'GEOGRAPHIC', 'AGE_RESTRICTED',
        name='votingrestriction'
    )
    voting_restriction_enum.create(op.get_bind(), checkfirst=True)
    
    # Add voting_restriction column if it doesn't exist
    op.execute("""
        DO $$ BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' AND column_name = 'voting_restriction'
            ) THEN
                ALTER TABLE contest ADD COLUMN voting_restriction votingrestriction DEFAULT 'NONE' NOT NULL;
            END IF;
        END $$;
    """)
    
    # Add image_url column if it doesn't exist
    op.execute("""
        DO $$ BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' AND column_name = 'image_url'
            ) THEN
                ALTER TABLE contest ADD COLUMN image_url VARCHAR(500);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove image_url column
    op.drop_column('contest', 'image_url')
    
    # Remove voting_restriction column
    op.drop_column('contest', 'voting_restriction')
    
    # Drop the enum type
    voting_restriction_enum = postgresql.ENUM(
        'NONE', 'MALE_ONLY', 'FEMALE_ONLY', 'GEOGRAPHIC', 'AGE_RESTRICTED',
        name='votingrestriction'
    )
    voting_restriction_enum.drop(op.get_bind(), checkfirst=True)
