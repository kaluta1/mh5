"""Dual cashout: member preference, payout wallet history, cashout tracking.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-10-08

Additive only.

users
  cashout_method              NULL (not chosen) / 'CRYPTO' / 'USD'
  cashout_method_changed_at
  payout_wallet_verified_at   when the CURRENT wallet was set with the member's
                              password. NULL for every wallet saved before this
                              migration: those are unverified and are not paid
                              to until the member saves the wallet again.

affiliate_cashout_requests (empty in production at the time of writing)
  cashout_method, payout_currency, provider_batch_id, provider_status,
  failure_code, last_checked_at, reviewed_by, reviewed_at, settlement_reference
  uq_cashout_one_active_per_user  partial UNIQUE (user_id) over the open states
                                  requested / processing / unknown
  uq_cashout_payout_reference     UNIQUE (payout_reference): one row per intent

payout_wallet_changes (new, append-only): one row per accepted wallet change.

No commission, balance, deposit or journal row is read or changed. The unique
indexes are created only if no existing rows violate them (the upgrade stops
with a clear message otherwise; nothing is deleted to make them fit).
Downgrade drops exactly what is added here (wallet-change history and cashout
tracking values are lost; commissions and journals are not affected).
"""
from alembic import op


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

_CASHOUT_COLUMNS = (
    ("cashout_method", "VARCHAR(10)"),
    ("payout_currency", "VARCHAR(20)"),
    ("provider_batch_id", "VARCHAR(100)"),
    ("provider_status", "VARCHAR(30)"),
    ("failure_code", "VARCHAR(60)"),
    ("last_checked_at", "TIMESTAMP"),
    ("reviewed_by", "INTEGER REFERENCES users(id)"),
    ("reviewed_at", "TIMESTAMP"),
    ("settlement_reference", "VARCHAR(255)"),
)


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cashout_method VARCHAR(10)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cashout_method_changed_at TIMESTAMP")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS payout_wallet_verified_at TIMESTAMP")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_cashout_method")
    op.execute("ALTER TABLE users ADD CONSTRAINT ck_users_cashout_method "
               "CHECK (cashout_method IS NULL OR cashout_method IN ('CRYPTO', 'USD'))")

    for name, ddl in _CASHOUT_COLUMNS:
        op.execute(f"ALTER TABLE affiliate_cashout_requests ADD COLUMN IF NOT EXISTS {name} {ddl}")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM affiliate_cashout_requests
                       WHERE status IN ('requested', 'processing', 'unknown')
                       GROUP BY user_id HAVING COUNT(*) > 1) THEN
                RAISE EXCEPTION 'dual cashout: a member has more than one open cashout; reconcile before upgrading';
            END IF;
            IF EXISTS (SELECT 1 FROM affiliate_cashout_requests WHERE payout_reference IS NOT NULL
                       GROUP BY payout_reference HAVING COUNT(*) > 1) THEN
                RAISE EXCEPTION 'dual cashout: duplicate payout_reference values; reconcile before upgrading';
            END IF;
        END $$;
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_cashout_one_active_per_user "
               "ON affiliate_cashout_requests (user_id) WHERE status IN ('requested', 'processing', 'unknown')")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_cashout_payout_reference "
               "ON affiliate_cashout_requests (payout_reference)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS payout_wallet_changes (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL REFERENCES users(id),
            old_address VARCHAR(100),
            new_address VARCHAR(100) NOT NULL,
            currency VARCHAR(20) NOT NULL,
            changed_at TIMESTAMP NOT NULL DEFAULT now(),
            payable_from TIMESTAMP NOT NULL,
            ip_address VARCHAR(45)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_payout_wallet_changes_id ON payout_wallet_changes (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payout_wallet_changes_user_id ON payout_wallet_changes (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payout_wallet_changes")
    op.execute("DROP INDEX IF EXISTS uq_cashout_payout_reference")
    op.execute("DROP INDEX IF EXISTS uq_cashout_one_active_per_user")
    for name, _ddl in reversed(_CASHOUT_COLUMNS):
        op.execute(f"ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS {name}")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_cashout_method")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS payout_wallet_verified_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cashout_method_changed_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS cashout_method")
