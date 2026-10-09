"""Finance & Payments: Admin-managed payment configuration for the dual cashout.

Revision ID: a5b6c7d8e9f0
Revises: f3a4b5c6d7e8
Create Date: 2026-10-09

Additive only.

payment_settings              one row (id = 1), created by the first Admin
                              change, never by this migration: until then the
                              application uses its built-in defaults, which
                              are the values production runs with today.
payment_credentials           provider credentials as AES-256-GCM ciphertext.
                              EMPTY after this migration: nothing is imported,
                              copied or rotated from the environment.
payment_config_audit          append-only, versioned configuration history.
payout_wallet_verifications   pending email confirmations of a payout wallet
                              (token digest only).
payment_webhook_stats         per-day counters of provider callbacks.

affiliate_cashout_requests    + network_fee, network_fee_policy,
                                destination_ciphertext
payout_wallet_changes         + verification_method

permissions                   manage_payment_settings and process_cashouts are
                              created and assigned to NO role: granting them is
                              a deliberate Admin action
                              (app/scripts/grant_payment_permissions.py).

No commission, balance, deposit, cashout or journal row is read or changed and
no secret is written. Downgrade drops exactly what is added here (stored
credentials, the configuration and its history are lost; the application then
runs on its defaults again) and removes the two permissions only if no role
holds them.
"""
from alembic import op


revision = "a5b6c7d8e9f0"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("manage_payment_settings",
     "Manage Finance & Payments: provider, credentials, cashout settings, payout security, connection test"),
    ("process_cashouts",
     "Process cashouts: cancel a request, record a USD settlement, settle an unknown payout, run a payout cycle"),
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS payment_settings (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            version INTEGER NOT NULL DEFAULT 1,
            provider_display_name VARCHAR(80) NOT NULL,
            provider_enabled BOOLEAN NOT NULL,
            payin_credential_source VARCHAR(12) NOT NULL
                CONSTRAINT ck_payment_settings_payin_source
                CHECK (payin_credential_source IN ('ENVIRONMENT', 'DATABASE')),
            payout_credential_source VARCHAR(12) NOT NULL
                CONSTRAINT ck_payment_settings_payout_source
                CHECK (payout_credential_source IN ('ENVIRONMENT', 'DATABASE')),
            crypto_cashout_enabled BOOLEAN NOT NULL,
            crypto_auto_payout_enabled BOOLEAN NOT NULL,
            crypto_min_usd NUMERIC(12, 2) NOT NULL CHECK (crypto_min_usd > 0),
            crypto_payout_currency VARCHAR(20) NOT NULL,
            network_fee_policy VARCHAR(16) NOT NULL
                CONSTRAINT ck_payment_settings_fee_policy
                CHECK (network_fee_policy IN ('COMPANY_PAYS', 'MEMBER_PAYS')),
            max_network_fee_percent NUMERIC(6, 2) NOT NULL CHECK (max_network_fee_percent > 0),
            payout_interval_seconds INTEGER NOT NULL CHECK (payout_interval_seconds >= 60),
            max_single_payout_usd NUMERIC(12, 2) NOT NULL CHECK (max_single_payout_usd > 0),
            max_daily_payout_usd NUMERIC(12, 2) NOT NULL CHECK (max_daily_payout_usd > 0),
            max_daily_payout_count INTEGER NOT NULL CHECK (max_daily_payout_count > 0),
            min_hours_between_payouts INTEGER NOT NULL CHECK (min_hours_between_payouts >= 0),
            retry_backoff_hours INTEGER NOT NULL CHECK (retry_backoff_hours > 0),
            retry_max_attempts INTEGER NOT NULL CHECK (retry_max_attempts > 0),
            provider_balance_reserve_usd NUMERIC(12, 2) NOT NULL CHECK (provider_balance_reserve_usd >= 0),
            wallet_email_verification_required BOOLEAN NOT NULL,
            wallet_hold_hours INTEGER NOT NULL CHECK (wallet_hold_hours >= 0),
            wallet_max_changes_per_day INTEGER NOT NULL CHECK (wallet_max_changes_per_day > 0),
            wallet_verification_ttl_minutes INTEGER NOT NULL CHECK (wallet_verification_ttl_minutes > 0),
            usd_cashout_enabled BOOLEAN NOT NULL,
            usd_min_usd NUMERIC(12, 2) NOT NULL CHECK (usd_min_usd > 0),
            usd_fee_percent NUMERIC(6, 3) NOT NULL CHECK (usd_fee_percent >= 0),
            usd_fee_min NUMERIC(12, 2) NOT NULL CHECK (usd_fee_min >= 0),
            usd_fee_max NUMERIC(12, 2) NOT NULL CHECK (usd_fee_max >= usd_fee_min),
            usd_settlement_enabled BOOLEAN NOT NULL,
            usd_settlement_account VARCHAR(20),
            usd_admin_approval_required BOOLEAN NOT NULL,
            usd_processing_policy VARCHAR(20) NOT NULL,
            usd_member_cancellation_allowed BOOLEAN NOT NULL,
            usd_reference_min_length INTEGER NOT NULL CHECK (usd_reference_min_length > 0),
            usd_destination_required BOOLEAN NOT NULL,
            usd_destination_note VARCHAR(500),
            last_connection_test_at TIMESTAMP,
            last_connection_test_status VARCHAR(30),
            last_connection_ok_at TIMESTAMP,
            last_connection_test_detail JSONB,
            updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT ck_payment_settings_single_row CHECK (id = 1)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_settings_id ON payment_settings (id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS payment_credentials (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            provider VARCHAR(30) NOT NULL,
            name VARCHAR(40) NOT NULL,
            ciphertext TEXT NOT NULL,
            set_at TIMESTAMP NOT NULL DEFAULT now(),
            set_by INTEGER REFERENCES users(id) ON DELETE SET NULL
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_credentials_id ON payment_credentials (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_credentials_provider_name "
               "ON payment_credentials (provider, name)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS payment_config_audit (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            version INTEGER NOT NULL,
            action VARCHAR(50) NOT NULL,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            changed_fields JSONB,
            old_values JSONB,
            new_values JSONB,
            ip_address VARCHAR(45)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_config_audit_id ON payment_config_audit (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_config_audit_created_at ON payment_config_audit (created_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS payout_wallet_verifications (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL REFERENCES users(id),
            address VARCHAR(100) NOT NULL,
            currency VARCHAR(20) NOT NULL,
            token_hash VARCHAR(64) NOT NULL CONSTRAINT uq_payout_wallet_verifications_token_hash UNIQUE,
            requested_at TIMESTAMP NOT NULL DEFAULT now(),
            expires_at TIMESTAMP NOT NULL,
            consumed_at TIMESTAMP,
            revoked_at TIMESTAMP,
            ip_address VARCHAR(45)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payout_wallet_verifications_id ON payout_wallet_verifications (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payout_wallet_verifications_user_id "
               "ON payout_wallet_verifications (user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS payment_webhook_stats (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            provider VARCHAR(30) NOT NULL,
            day DATE NOT NULL,
            outcome VARCHAR(30) NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            last_at TIMESTAMP NOT NULL
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_webhook_stats_id ON payment_webhook_stats (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_webhook_stats "
               "ON payment_webhook_stats (provider, day, outcome)")

    op.execute("ALTER TABLE affiliate_cashout_requests ADD COLUMN IF NOT EXISTS network_fee NUMERIC(10, 2)")
    op.execute("ALTER TABLE affiliate_cashout_requests ADD COLUMN IF NOT EXISTS network_fee_policy VARCHAR(16)")
    op.execute("ALTER TABLE affiliate_cashout_requests ADD COLUMN IF NOT EXISTS destination_ciphertext TEXT")
    op.execute("ALTER TABLE payout_wallet_changes ADD COLUMN IF NOT EXISTS verification_method VARCHAR(20)")

    # The permissions exist but are held by nobody until an Admin grants them.
    for name, description in _PERMISSIONS:
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.permissions') IS NOT NULL THEN
                    INSERT INTO permissions (name, description, category, created_at, updated_at)
                    SELECT '{name}', '{description}', 'admin', now(), now()
                    WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = '{name}');
                END IF;
            END $$""")


def downgrade() -> None:
    op.execute("ALTER TABLE payout_wallet_changes DROP COLUMN IF EXISTS verification_method")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS destination_ciphertext")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS network_fee_policy")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS network_fee")
    op.execute("DROP TABLE IF EXISTS payment_webhook_stats")
    op.execute("DROP TABLE IF EXISTS payout_wallet_verifications")
    op.execute("DROP TABLE IF EXISTS payment_config_audit")
    op.execute("DROP TABLE IF EXISTS payment_credentials")
    op.execute("DROP TABLE IF EXISTS payment_settings")
    for name, _description in _PERMISSIONS:
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.permissions') IS NOT NULL
                   AND to_regclass('public.role_permissions') IS NOT NULL THEN
                    DELETE FROM permissions p
                    WHERE p.name = '{name}'
                      AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id);
                END IF;
            END $$""")
