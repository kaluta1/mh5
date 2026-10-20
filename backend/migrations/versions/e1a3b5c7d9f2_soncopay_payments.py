"""SoncoPay customer payments: the provider of each deposit and webhook deliveries.

Revision ID: e1a3b5c7d9f2
Revises: d0f2a4c6e8b1
Create Date: 2026-10-21

Additive only. Nothing that exists is changed, moved or deleted.

  * deposits gets five NULLable columns. NULL payment_provider means a
    NOWPayments (or older) deposit, exactly as every existing row is read
    today; no existing row is written.
      payment_provider       nowpayments | soncopay, fixed when the deposit is created
      provider_environment   test | live (SoncoPay: the key that created the payment)
      provider_status        the provider's own status word, for display
      provider_checkout_url  SoncoPay hosted checkout page
      provider_expires_at    when the provider stops accepting the payment
  * uq_deposits_soncopay_payment: one SoncoPay payment belongs to ONE deposit.
    Partial (payment_provider = 'soncopay'), so existing NOWPayments rows are
    not checked and cannot make the migration fail.
  * soncopay_webhook_events (NEW): one row per processed SoncoPay delivery
    (X-SoncoPay-Delivery-Id, unique), written in the same transaction as the
    deposit change, so a retried delivery is never processed twice.

Re-running the upgrade is a no-op. Downgrade refuses while any SoncoPay
deposit exists (its provider would be lost), then drops only what this
revision added.
"""
from alembic import op


revision = "e1a3b5c7d9f2"
down_revision = "d0f2a4c6e8b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS payment_provider VARCHAR(20) NULL")
    op.execute("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS provider_environment VARCHAR(10) NULL")
    op.execute("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS provider_status VARCHAR(40) NULL")
    op.execute("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS provider_checkout_url TEXT NULL")
    op.execute("ALTER TABLE deposits ADD COLUMN IF NOT EXISTS provider_expires_at TIMESTAMP NULL")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_deposits_payment_provider') THEN
                ALTER TABLE deposits ADD CONSTRAINT ck_deposits_payment_provider
                    CHECK (payment_provider IS NULL OR payment_provider IN ('nowpayments', 'soncopay'));
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_deposits_provider_environment') THEN
                ALTER TABLE deposits ADD CONSTRAINT ck_deposits_provider_environment
                    CHECK (provider_environment IS NULL OR provider_environment IN ('test', 'live'));
            END IF;
        END $$""")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_deposits_soncopay_payment
            ON deposits (external_payment_id)
            WHERE payment_provider = 'soncopay' AND external_payment_id IS NOT NULL""")
    op.execute("""
        CREATE TABLE IF NOT EXISTS soncopay_webhook_events (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            delivery_id VARCHAR(128) NOT NULL,
            event VARCHAR(64) NOT NULL,
            environment VARCHAR(10) NOT NULL,
            payment_id VARCHAR(64) NULL,
            deposit_id INTEGER NULL REFERENCES deposits(id) ON DELETE SET NULL,
            outcome VARCHAR(40) NOT NULL,
            CONSTRAINT uq_soncopay_webhook_events_delivery UNIQUE (delivery_id),
            CONSTRAINT ck_soncopay_webhook_events_environment CHECK (environment IN ('test', 'live'))
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soncopay_webhook_events_deposit ON soncopay_webhook_events (deposit_id)")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'deposits' AND column_name = 'payment_provider')
               AND EXISTS (SELECT 1 FROM deposits WHERE payment_provider = 'soncopay') THEN
                RAISE EXCEPTION 'SoncoPay deposits exist; their provider would be lost';
            END IF;
        END $$""")
    op.execute("DROP TABLE IF EXISTS soncopay_webhook_events")
    op.execute("DROP INDEX IF EXISTS uq_deposits_soncopay_payment")
    op.execute("ALTER TABLE deposits DROP CONSTRAINT IF EXISTS ck_deposits_provider_environment")
    op.execute("ALTER TABLE deposits DROP CONSTRAINT IF EXISTS ck_deposits_payment_provider")
    for column in ("provider_expires_at", "provider_checkout_url", "provider_status", "provider_environment",
                   "payment_provider"):
        op.execute(f"ALTER TABLE deposits DROP COLUMN IF EXISTS {column}")
