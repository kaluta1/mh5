"""Ensure voting_type table and cover_image_url column exist

Revision ID: ensure_voting_type_cover_image
Revises: convert_location_level_string
Create Date: 2025-12-28 01:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'ensure_voting_type_cover_image'
down_revision = 'convert_location_level_string'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check if voting_type table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'voting_type'
        )
    """))
    table_exists = result.fetchone()[0]
    
    if not table_exists:
        # Create ENUM types if they don't exist
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE votinglevel AS ENUM ('city', 'country', 'regional', 'continent', 'global');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        
        op.execute("""
            DO $$ BEGIN
                CREATE TYPE commissionsource AS ENUM ('advert', 'affiliate', 'kyc', 'MFM');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        
        # Create voting_type table
        voting_level_enum = postgresql.ENUM('city', 'country', 'regional', 'continent', 'global', name='votinglevel', create_type=False)
        commission_source_enum = postgresql.ENUM('advert', 'affiliate', 'kyc', 'MFM', name='commissionsource', create_type=False)
        
        op.create_table(
            'voting_type',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('voting_level', voting_level_enum, nullable=False),
            sa.Column('commission_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('commission_source', commission_source_enum, nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Check if cover_image_url column exists in contest table
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'contest' AND column_name = 'cover_image_url'
        )
    """))
    column_exists = result.fetchone()[0]
    
    if not column_exists:
        op.execute("""
            DO $$ BEGIN 
                ALTER TABLE contest ADD COLUMN cover_image_url VARCHAR(500);
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)
    
    # Check if voting_type_id column exists in contest table
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'contest' AND column_name = 'voting_type_id'
        )
    """))
    voting_type_id_exists = result.fetchone()[0]
    
    if not voting_type_id_exists:
        op.execute("""
            DO $$ BEGIN 
                ALTER TABLE contest ADD COLUMN voting_type_id INTEGER;
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)
        
        # Check if foreign key exists
        result = conn.execute(sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.table_constraints 
                WHERE table_name = 'contest' 
                AND constraint_name = 'fk_contest_voting_type'
            )
        """))
        fk_exists = result.fetchone()[0]
        
        if not fk_exists and table_exists:
            op.execute("""
                DO $$ BEGIN 
                    ALTER TABLE contest 
                    ADD CONSTRAINT fk_contest_voting_type 
                    FOREIGN KEY (voting_type_id) 
                    REFERENCES voting_type(id) 
                    ON DELETE SET NULL;
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END $$;
            """)


def downgrade() -> None:
    # Remove foreign key if it exists
    op.execute("""
        DO $$ BEGIN 
            ALTER TABLE contest DROP CONSTRAINT IF EXISTS fk_contest_voting_type;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
    
    # Remove voting_type_id column if it exists
    op.execute("""
        DO $$ BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' AND column_name = 'voting_type_id'
            ) THEN
                ALTER TABLE contest DROP COLUMN voting_type_id;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
    
    # Remove cover_image_url column if it exists
    op.execute("""
        DO $$ BEGIN 
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contest' AND column_name = 'cover_image_url'
            ) THEN
                ALTER TABLE contest DROP COLUMN cover_image_url;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
    
    # Note: We don't drop voting_type table or ENUMs in downgrade
    # as they might be used by other migrations

