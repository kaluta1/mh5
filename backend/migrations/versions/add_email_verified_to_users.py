"""Add email_verified field to users table

Revision ID: add_email_verified
Revises: 
Create Date: 2025-12-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_email_verified'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ajout idempotent : ne crée la colonne que si elle n'existe pas déjà
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'email_verified'
            ) THEN
                ALTER TABLE users
                ADD COLUMN email_verified BOOLEAN DEFAULT FALSE NOT NULL;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Supprime la colonne uniquement si elle existe
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'email_verified'
            ) THEN
                ALTER TABLE users DROP COLUMN email_verified;
            END IF;
        END
        $$;
        """
    )
