"""Add Kaluta to KYC verification provider enum.

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
"""
from alembic import op


revision = "s3t4u5v6w7x8"
down_revision = "r2s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL native enum — safe no-op if type/column is varchar in some envs
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verificationprovider') THEN
                ALTER TYPE verificationprovider ADD VALUE IF NOT EXISTS 'kaluta';
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    pass
