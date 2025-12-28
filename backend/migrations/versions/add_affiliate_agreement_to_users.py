"""add affiliate agreement fields to users

Revision ID: add_affiliate_agreement
Revises: 
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_affiliate_agreement'
down_revision = None  # Will be set to the latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add affiliate_agreement_accepted column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'affiliate_agreement_accepted'
            ) THEN
                ALTER TABLE users
                ADD COLUMN affiliate_agreement_accepted BOOLEAN DEFAULT false NOT NULL;
            END IF;
        END
        $$;
    """)
    
    # Add affiliate_agreement_accepted_at column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'affiliate_agreement_accepted_at'
            ) THEN
                ALTER TABLE users
                ADD COLUMN affiliate_agreement_accepted_at TIMESTAMP;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Remove affiliate_agreement_accepted_at column
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'affiliate_agreement_accepted_at'
            ) THEN
                ALTER TABLE users DROP COLUMN affiliate_agreement_accepted_at;
            END IF;
        END
        $$;
    """)
    
    # Remove affiliate_agreement_accepted column
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'affiliate_agreement_accepted'
            ) THEN
                ALTER TABLE users DROP COLUMN affiliate_agreement_accepted;
            END IF;
        END
        $$;
    """)

