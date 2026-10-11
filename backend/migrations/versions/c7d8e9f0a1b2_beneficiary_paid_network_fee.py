"""Crypto cashout: the network fee is paid by the beneficiary.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-10-11

Owner decision: the network fee of a crypto payout is borne by the
beneficiary, who receives the payout net of it. The whole amount is handed to
the provider, which takes its fee out of it (provider fee behaviour
DEDUCTED_BY_PROVIDER). Members accept the fee terms and a maximum fee first.

Additive only. Nothing that exists is rewritten:

payment_settings             + provider_fee_mode (UNVERIFIED), the member fee
                               limits (0 = not set), min_net_payout_usd,
                               fee_terms_version, fee_consent_valid_days,
                               fee_terms_approved (false). Every default fails
                               closed: with them no payout can be created. An
                               existing network_fee_policy is NOT changed.
affiliate_cashout_requests   + the full-precision figures of a payout:
                               amount_sent, network_fee_estimate,
                               network_fee_actual, net_received, the fee
                               source, the member's limit, the consent used
                               and a flag. All NULL on existing rows.
cashout_fee_consents         new: one row per acceptance of the fee terms.

No journal entry, commission, cashout or deposit is read or changed. Account
5005 is left exactly as it is.

Downgrade refuses to run once an acceptance or a beneficiary-paid payout has
been recorded: it would destroy financial records.
"""
from alembic import op


revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None

_SETTINGS = (
    ("provider_fee_mode", "VARCHAR(24) NOT NULL DEFAULT 'UNVERIFIED'"),
    ("member_fee_cap_percent", "NUMERIC(6, 3) NOT NULL DEFAULT 0"),
    ("member_fee_cap_usd", "NUMERIC(12, 2) NOT NULL DEFAULT 0"),
    ("min_net_payout_usd", "NUMERIC(12, 2) NOT NULL DEFAULT 0.01"),
    ("fee_terms_version", "INTEGER NOT NULL DEFAULT 1"),
    ("fee_consent_valid_days", "INTEGER NOT NULL DEFAULT 0"),
    ("fee_terms_approved", "BOOLEAN NOT NULL DEFAULT false"),
)
_SETTINGS_CHECKS = (
    ("ck_payment_settings_fee_mode",
     "provider_fee_mode IN ('UNVERIFIED', 'DEDUCTED_BY_PROVIDER', 'CHARGED_TO_BALANCE')"),
    ("ck_payment_settings_fee_caps",
     "member_fee_cap_percent >= 0 AND member_fee_cap_percent <= 100 AND member_fee_cap_usd >= 0"),
    ("ck_payment_settings_min_net", "min_net_payout_usd > 0"),
    ("ck_payment_settings_fee_terms", "fee_terms_version >= 1 AND fee_consent_valid_days >= 0"),
)
_CASHOUT = (
    ("provider_fee_mode", "VARCHAR(24)"),
    ("amount_sent", "NUMERIC(24, 8)"),
    ("network_fee_estimate", "NUMERIC(24, 8)"),
    ("network_fee_actual", "NUMERIC(24, 8)"),
    ("net_received", "NUMERIC(24, 8)"),
    ("network_fee_source", "VARCHAR(20)"),
    ("fee_cap", "NUMERIC(24, 8)"),
    ("fee_consent_id", "INTEGER"),
    ("fee_flag", "VARCHAR(40)"),
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS cashout_fee_consents (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL REFERENCES users (id),
            terms_version INTEGER NOT NULL CHECK (terms_version >= 1),
            cap_percent NUMERIC(6, 3) NOT NULL CHECK (cap_percent >= 0 AND cap_percent <= 100),
            cap_usd NUMERIC(12, 2) NOT NULL CHECK (cap_usd >= 0),
            accepted_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP,
            revoked_at TIMESTAMP,
            revoked_reason VARCHAR(30),
            ip_address VARCHAR(45),
            CONSTRAINT ck_cashout_fee_consents_a_limit CHECK (cap_percent > 0 OR cap_usd > 0)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cashout_fee_consents_id ON cashout_fee_consents (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cashout_fee_consents_user_id ON cashout_fee_consents (user_id)")
    # One acceptance in force per member; two concurrent requests cannot both insert one.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_cashout_fee_consents_active "
               "ON cashout_fee_consents (user_id) WHERE revoked_at IS NULL")

    for name, definition in _SETTINGS:
        op.execute(f"ALTER TABLE payment_settings ADD COLUMN IF NOT EXISTS {name} {definition}")
    for name, rule in _SETTINGS_CHECKS:
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN
                    ALTER TABLE payment_settings ADD CONSTRAINT {name} CHECK ({rule});
                END IF;
            END $$""")

    for name, definition in _CASHOUT:
        op.execute(f"ALTER TABLE affiliate_cashout_requests ADD COLUMN IF NOT EXISTS {name} {definition}")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cashout_fee_consent') THEN
                ALTER TABLE affiliate_cashout_requests ADD CONSTRAINT fk_cashout_fee_consent
                    FOREIGN KEY (fee_consent_id) REFERENCES cashout_fee_consents (id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cashout_beneficiary_fee') THEN
                ALTER TABLE affiliate_cashout_requests ADD CONSTRAINT ck_cashout_beneficiary_fee CHECK (
                    (amount_sent IS NULL OR amount_sent > 0)
                    AND (network_fee_estimate IS NULL OR network_fee_estimate >= 0)
                    AND (network_fee_actual IS NULL OR network_fee_actual >= 0)
                    AND (net_received IS NULL OR net_received > 0)
                    AND (fee_cap IS NULL OR fee_cap >= 0));
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM cashout_fee_consents)
               OR EXISTS (SELECT 1 FROM affiliate_cashout_requests
                          WHERE network_fee_actual IS NOT NULL OR fee_consent_id IS NOT NULL
                             OR amount_sent IS NOT NULL) THEN
                RAISE EXCEPTION 'beneficiary-paid network fee records exist; this downgrade would destroy them';
            END IF;
        END $$""")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP CONSTRAINT IF EXISTS ck_cashout_beneficiary_fee")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP CONSTRAINT IF EXISTS fk_cashout_fee_consent")
    for name, _definition in reversed(_CASHOUT):
        op.execute(f"ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS {name}")
    for name, _rule in _SETTINGS_CHECKS:
        op.execute(f"ALTER TABLE payment_settings DROP CONSTRAINT IF EXISTS {name}")
    for name, _definition in reversed(_SETTINGS):
        op.execute(f"ALTER TABLE payment_settings DROP COLUMN IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS cashout_fee_consents")
