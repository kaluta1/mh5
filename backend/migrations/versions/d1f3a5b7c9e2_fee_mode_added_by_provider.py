"""payment_settings.provider_fee_mode may be ADDED_BY_PROVIDER (SoncoPay).

Revision ID: d1f3a5b7c9e2
Revises: c9e1f3a5b7d0
Create Date: 2026-10-30

The check constraint of c7d8e9f0a1b2 predates SoncoPay and listed only UNVERIFIED, DEDUCTED_BY_PROVIDER and
CHARGED_TO_BALANCE, so saving the SoncoPay fee behaviour failed in the database (503). Constraint only, no row
rewritten. Downgrade refuses while the stored value is ADDED_BY_PROVIDER.
"""
from alembic import op


revision = "d1f3a5b7c9e2"
down_revision = "c9e1f3a5b7d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE payment_settings DROP CONSTRAINT IF EXISTS ck_payment_settings_fee_mode")
    op.execute("ALTER TABLE payment_settings ADD CONSTRAINT ck_payment_settings_fee_mode CHECK (provider_fee_mode IN "
               "('UNVERIFIED', 'DEDUCTED_BY_PROVIDER', 'CHARGED_TO_BALANCE', 'ADDED_BY_PROVIDER'))")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM payment_settings WHERE provider_fee_mode = 'ADDED_BY_PROVIDER') THEN
                RAISE EXCEPTION 'provider_fee_mode is ADDED_BY_PROVIDER: change it before downgrading';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE payment_settings DROP CONSTRAINT IF EXISTS ck_payment_settings_fee_mode")
    op.execute("ALTER TABLE payment_settings ADD CONSTRAINT ck_payment_settings_fee_mode CHECK (provider_fee_mode IN "
               "('UNVERIFIED', 'DEDUCTED_BY_PROVIDER', 'CHARGED_TO_BALANCE'))")
