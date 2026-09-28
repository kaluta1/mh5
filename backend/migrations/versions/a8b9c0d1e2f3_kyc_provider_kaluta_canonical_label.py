"""KYC: make 'KALUTA' the single canonical verificationprovider label.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-29

Root cause: KYCVerification.provider uses the default SQLEnum(VerificationProvider),
which persists enum member NAMES (SHUFTI_PRO, JUMIO, ONFIDO, MANUAL, KALUTA). The type
was created by Base.metadata.create_all with the uppercase names; s3t4u5v6w7x8 later
added the lowercase VALUE 'kaluta'. So every write of VerificationProvider.KALUTA failed
with "invalid input value for enum verificationprovider: "KALUTA"", and a row holding
'kaluta' could not be read back into the Python enum either.

This migration converges every database to one label, 'KALUTA', without touching the
other labels or the Python enum:
  * 'kaluta' only          -> RENAME VALUE 'kaluta' TO 'KALUTA' (in place: existing rows
                              keep their value and simply read as KALUTA; no rewrite)
  * neither                -> ADD VALUE 'KALUTA'
  * 'KALUTA' only          -> nothing (fresh create_all databases already match)
  * both (only if created by hand) -> rows holding 'kaluta' are normalised to 'KALUTA';
                              the unused lowercase label is left (PostgreSQL cannot drop an
                              enum label without rebuilding the type) and a NOTICE is raised
  * type absent            -> nothing (create_all will create it from the model)

Requires PostgreSQL >= 10 for RENAME VALUE (ADD VALUE inside a transaction, already used by
s3t4u5v6w7x8, needs >= 12). No column, default, index or constraint changes.

Downgrade is a deliberate no-op: the previous application code writes the same enum name
'KALUTA', so restoring the lowercase label would only reintroduce the failure.
"""
from alembic import op


revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            has_lower boolean;
            has_upper boolean;
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verificationprovider') THEN
                RETURN;
            END IF;
            SELECT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                           WHERE t.typname = 'verificationprovider' AND e.enumlabel = 'kaluta') INTO has_lower;
            SELECT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                           WHERE t.typname = 'verificationprovider' AND e.enumlabel = 'KALUTA') INTO has_upper;
            IF has_lower AND NOT has_upper THEN
                ALTER TYPE verificationprovider RENAME VALUE 'kaluta' TO 'KALUTA';
            ELSIF NOT has_lower AND NOT has_upper THEN
                ALTER TYPE verificationprovider ADD VALUE 'KALUTA';
            ELSIF has_lower AND has_upper THEN
                IF to_regclass('public.kyc_verifications') IS NOT NULL THEN
                    UPDATE kyc_verifications SET provider = 'KALUTA' WHERE provider = 'kaluta';
                END IF;
                RAISE NOTICE 'verificationprovider: lowercase kaluta label left unused (rows normalised to KALUTA)';
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    pass
