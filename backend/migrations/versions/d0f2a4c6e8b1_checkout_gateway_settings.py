"""Customer checkout gateway settings (SoncoPay collection, Admin-managed).

Revision ID: d0f2a4c6e8b1
Revises: c8e0f2a4b6d8
Create Date: 2026-10-20

Additive only. Nothing that exists is changed, moved or deleted.

  * checkout_gateway_settings (NEW, one row, id = 1): the default customer
    checkout gateway and the SoncoPay on/off switch and environment. The
    table is created EMPTY: with no row NOWPayments stays the default checkout
    and SoncoPay is off (Test environment), exactly as before.
  * SoncoPay API keys and webhook signing secrets are not stored here: they
    go to the existing payment_credentials table as AES-256-GCM ciphertext
    (provider "soncopay"), written only from the Admin Panel. Nothing is
    imported from the environment.

payment_settings (the NOWPayments payout engine) and every user, role,
payment, deposit, ledger, commission and cashout row are neither read nor
changed. Re-running the upgrade is a no-op. Downgrade drops only the new table
(and refuses while SoncoPay credentials are stored, so none is orphaned).
"""
from alembic import op


revision = "d0f2a4c6e8b1"
down_revision = "c8e0f2a4b6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS checkout_gateway_settings (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            default_provider VARCHAR(30) NOT NULL DEFAULT 'nowpayments',
            soncopay_enabled BOOLEAN NOT NULL DEFAULT false,
            soncopay_environment VARCHAR(10) NOT NULL DEFAULT 'test',
            version INTEGER NOT NULL DEFAULT 0,
            updated_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT ck_checkout_gateway_settings_single_row CHECK (id = 1),
            CONSTRAINT ck_checkout_gateway_settings_default_provider
                CHECK (default_provider IN ('nowpayments', 'soncopay')),
            CONSTRAINT ck_checkout_gateway_settings_soncopay_environment
                CHECK (soncopay_environment IN ('test', 'live'))
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_checkout_gateway_settings_id ON checkout_gateway_settings (id)")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.payment_credentials') IS NOT NULL
               AND EXISTS (SELECT 1 FROM payment_credentials WHERE provider = 'soncopay') THEN
                RAISE EXCEPTION 'SoncoPay credentials are stored; remove them before downgrading';
            END IF;
        END $$""")
    op.execute("DROP TABLE IF EXISTS checkout_gateway_settings")
