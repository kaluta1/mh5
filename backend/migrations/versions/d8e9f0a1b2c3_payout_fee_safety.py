"""Crypto cashout: recording gate, estimate safety margin, payout suspension.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-11

The member's fee limit is checked against the provider's ESTIMATE; the actual
fee is known only after the provider has sent the payout. These columns keep
that exposure small. They do not, and cannot, guarantee the actual fee of a
payout.

Two different things: a payout whose actual fee is missing or not verified yet
only holds further payouts back until it is verified (the recording gate, which
stores nothing here); a CONFIRMED inconsistency suspends payouts until an
administrator reactivates them (the suspension columns).

Additive only. Nothing that exists is rewritten:

payment_settings             + fee_estimate_margin_percent (NULL = not set:
                               no payout is created), max_unreconciled_payouts
                               (0 = one payout at a time, each verified before
                               the next), and the payout suspension: reason,
                               time and the cashout that caused it (all NULL).
affiliate_cashout_requests   + fee_estimate_adjusted, fee_margin_percent (what
                               was compared with the member's limit),
                               fee_reconciliation and fee_evidence (how far the
                               actual fee was verified). All NULL on existing
                               rows: an existing completed beneficiary-paid
                               payout therefore counts as NOT reconciled.

No journal entry, commission, cashout amount or deposit is read or changed.

Downgrade refuses to run while payouts are suspended or once a reconciliation
has been recorded: it would destroy the reason for a suspension or the record
of how an actual fee was verified.
"""
from alembic import op


revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

_SETTINGS = (
    ("fee_estimate_margin_percent", "NUMERIC(7, 3)"),
    ("max_unreconciled_payouts", "INTEGER NOT NULL DEFAULT 0"),
    ("payout_suspended_reason", "VARCHAR(40)"),
    ("payout_suspended_at", "TIMESTAMP"),
    ("payout_suspended_cashout_id", "INTEGER"),
)
_SETTINGS_CHECKS = (
    ("ck_payment_settings_fee_margin",
     "fee_estimate_margin_percent IS NULL OR (fee_estimate_margin_percent >= 0 AND fee_estimate_margin_percent <= 500)"),
    ("ck_payment_settings_unreconciled", "max_unreconciled_payouts >= 0 AND max_unreconciled_payouts <= 1000"),
    ("ck_payment_settings_suspension",
     "payout_suspended_reason IS NULL OR payout_suspended_reason IN ('PROVIDER_FEE_MODE_MISMATCH', "
     "'PROVIDER_AMOUNT_MISMATCH', 'FEE_CAP_EXCEEDED')"),
)
_CASHOUT = (
    ("fee_estimate_adjusted", "NUMERIC(24, 8)"),
    ("fee_margin_percent", "NUMERIC(7, 3)"),
    ("fee_reconciliation", "VARCHAR(24)"),
    ("fee_evidence", "VARCHAR(30)"),
)
_CASHOUT_CHECK = (
    "(fee_estimate_adjusted IS NULL OR fee_estimate_adjusted >= 0) "
    "AND (fee_margin_percent IS NULL OR fee_margin_percent >= 0) "
    "AND (fee_reconciliation IS NULL OR fee_reconciliation IN ('PROVIDER_VERIFIED', 'ADMIN_VERIFIED', "
    "'PROVIDER_UNVERIFIED', 'ADMIN_UNVERIFIED')) "
    # A verified reconciliation without the figures it verifies cannot exist.
    "AND (fee_reconciliation IS NULL OR fee_reconciliation NOT IN ('PROVIDER_VERIFIED', 'ADMIN_VERIFIED') "
    "OR (network_fee_actual IS NOT NULL AND net_received IS NOT NULL AND fee_evidence IS NOT NULL))"
)


def upgrade() -> None:
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
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cashout_fee_reconciliation') THEN
                ALTER TABLE affiliate_cashout_requests ADD CONSTRAINT ck_cashout_fee_reconciliation
                    CHECK ({_CASHOUT_CHECK});
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM payment_settings WHERE payout_suspended_reason IS NOT NULL)
               OR EXISTS (SELECT 1 FROM affiliate_cashout_requests
                          WHERE fee_reconciliation IS NOT NULL OR fee_evidence IS NOT NULL) THEN
                RAISE EXCEPTION 'a payout suspension or a fee reconciliation is recorded; this downgrade would destroy it';
            END IF;
        END $$""")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP CONSTRAINT IF EXISTS ck_cashout_fee_reconciliation")
    for name, _definition in reversed(_CASHOUT):
        op.execute(f"ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS {name}")
    for name, _rule in _SETTINGS_CHECKS:
        op.execute(f"ALTER TABLE payment_settings DROP CONSTRAINT IF EXISTS {name}")
    for name, _definition in reversed(_SETTINGS):
        op.execute(f"ALTER TABLE payment_settings DROP COLUMN IF EXISTS {name}")
