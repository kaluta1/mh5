"""Crypto cashout: an administrator's review of a flagged payout.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-10-12

A completed beneficiary-paid payout that did not add up carries a flag
(fee_flag). These columns record that an administrator looked at it: which
flag was reviewed, by whom, when, and their note. The existing reviewed_by /
reviewed_at columns are not reused, because they already record who cancelled,
settled or resolved the cashout itself.

A review is a record and nothing else. It does not change the flag, the
reconciliation of the payout's actual fee, a payout suspension or any amount.

Additive only. Nothing that exists is rewritten:

affiliate_cashout_requests   + fee_review_flag, fee_review_note,
                               fee_reviewed_by, fee_reviewed_at (all NULL on
                               existing rows: an existing flagged payout
                               therefore counts as NOT reviewed).

No journal entry, commission, cashout amount, setting or deposit is read or
changed.

Downgrade refuses to run once a review has been recorded: it would destroy the
record of who reviewed a flagged payout and what they found.
"""
from alembic import op


revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("fee_review_flag", "VARCHAR(40)"),
    ("fee_review_note", "VARCHAR(500)"),
    ("fee_reviewed_by", "INTEGER REFERENCES users(id)"),
    ("fee_reviewed_at", "TIMESTAMP"),
)
_CHECK = (
    # A review is complete or absent: never a note without its author and time.
    "((fee_review_flag IS NULL AND fee_review_note IS NULL AND fee_reviewed_by IS NULL AND fee_reviewed_at IS NULL) "
    "OR (fee_review_flag IS NOT NULL AND fee_review_note IS NOT NULL AND fee_reviewed_by IS NOT NULL "
    "AND fee_reviewed_at IS NOT NULL AND char_length(btrim(fee_review_note)) >= 20)) "
    # Only a flagged payout can be reviewed, and only for a flag that exists.
    "AND (fee_review_flag IS NULL OR (fee_flag IS NOT NULL AND fee_review_flag IN ('PROVIDER_FEE_MODE_MISMATCH', "
    "'PROVIDER_AMOUNT_MISMATCH', 'FEE_CAP_EXCEEDED')))"
)


def upgrade() -> None:
    for name, definition in _COLUMNS:
        op.execute(f"ALTER TABLE affiliate_cashout_requests ADD COLUMN IF NOT EXISTS {name} {definition}")
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cashout_fee_review') THEN
                ALTER TABLE affiliate_cashout_requests ADD CONSTRAINT ck_cashout_fee_review CHECK ({_CHECK});
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            -- Asked only when the column is there, so a downgrade that was interrupted can be run again.
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = 'affiliate_cashout_requests'
                         AND column_name = 'fee_reviewed_at') THEN
                IF EXISTS (SELECT 1 FROM affiliate_cashout_requests WHERE fee_reviewed_at IS NOT NULL) THEN
                    RAISE EXCEPTION 'a review of a flagged payout is recorded; this downgrade would destroy it';
                END IF;
            END IF;
        END $$""")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP CONSTRAINT IF EXISTS ck_cashout_fee_review")
    for name, _definition in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS {name}")
