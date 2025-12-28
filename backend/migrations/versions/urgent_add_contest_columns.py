"""Urgent: Add missing contest columns and voting_type table

Revision ID: urgent_contest_cols
Revises: 5a9dda393841
Create Date: 2025-12-28 03:00:00.000000

This migration adds critical missing columns to the contest table and creates voting_type table.
It is idempotent and safe to run multiple times.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'urgent_contest_cols'
down_revision = '5a9dda393841'  # Se rattache directement à la tête actuelle
branch_labels = None
depends_on = None


def table_exists(table_name, insp):
    return table_name in insp.get_table_names()


def column_exists(table_name, column_name, insp):
    if not table_exists(table_name, insp):
        return False
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    
    # ============== ENUM TYPES ==============
    # Create required ENUM types if they don't exist
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
    
    # ============== VOTING_TYPE TABLE ==============
    if not table_exists('voting_type', insp):
        op.create_table(
            'voting_type',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('voting_level', postgresql.ENUM('city', 'country', 'regional', 'continent', 'global', name='votinglevel', create_type=False), nullable=False),
            sa.Column('commission_rules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('commission_source', postgresql.ENUM('advert', 'affiliate', 'kyc', 'MFM', name='commissionsource', create_type=False), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        print("Created voting_type table")
    
    # ============== CONTEST TABLE - Add critical missing columns ==============
    if table_exists('contest', insp):
        critical_columns = [
            ('cover_image_url', 'VARCHAR(500)'),
            ('voting_type_id', 'INTEGER'),
        ]
        
        for col_name, col_type in critical_columns:
            if not column_exists('contest', col_name, insp):
                op.execute(f"ALTER TABLE contest ADD COLUMN {col_name} {col_type};")
                print(f"Added column contest.{col_name}")
        
        # Add foreign key constraint for voting_type_id if voting_type table exists
        if table_exists('voting_type', insp) and column_exists('contest', 'voting_type_id', insp):
            op.execute("""
                DO $$ BEGIN
                    ALTER TABLE contest ADD CONSTRAINT fk_contest_voting_type 
                    FOREIGN KEY (voting_type_id) REFERENCES voting_type(id) ON DELETE SET NULL;
                EXCEPTION WHEN duplicate_object THEN null;
                END $$;
            """)
    
    print("Urgent migration completed!")


def downgrade() -> None:
    # Downgrade not implemented - this is an urgent fix migration
    pass

