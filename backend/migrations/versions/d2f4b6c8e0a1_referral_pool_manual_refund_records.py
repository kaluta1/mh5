"""Multi-Unit Referral Pool P7: two-person records of manual (non-provider-verified) refunds.

Revision ID: d2f4b6c8e0a1
Revises: c1e3a5b7d9f2
Create Date: 2026-10-24

Additive: one new table, no existing row touched.

  * referral_pool_refund_records  a refund the platform cannot verify with the provider (no signed
                                  partial-refund callback) is a controlled exception: one finance
                                  administrator PROPOSES it with the provider reference and evidence,
                                  a DIFFERENT one APPROVES it; only then are units refunded and money
                                  reversed. The provider reference is recorded, never treated as
                                  verified evidence by itself.

Downgrade drops the table; it refuses while an APPROVED record exists (its units were refunded on it).
"""
from alembic import op


revision = "d2f4b6c8e0a1"
down_revision = "c1e3a5b7d9f2"
branch_labels = None
depends_on = None

_BASE = "id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now()"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_refund_records ({_BASE},
            purchase_id INTEGER NOT NULL REFERENCES referral_pool_purchases(id),
            quantity INTEGER NOT NULL,
            amount NUMERIC(15,2) NOT NULL,
            provider_reference VARCHAR(120) NOT NULL,
            evidence_note TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'PROPOSED',
            proposed_by INTEGER NOT NULL REFERENCES users(id),
            decided_by INTEGER REFERENCES users(id),
            decided_at TIMESTAMP,
            decision_note VARCHAR(500),
            executed_unit_ids TEXT,
            CONSTRAINT uq_referral_pool_refund_reference UNIQUE (provider_reference),
            CONSTRAINT ck_referral_pool_refund_quantity CHECK (quantity >= 1),
            CONSTRAINT ck_referral_pool_refund_amount CHECK (amount > 0),
            CONSTRAINT ck_referral_pool_refund_status CHECK (status IN ('PROPOSED','APPROVED','REJECTED')),
            CONSTRAINT ck_referral_pool_refund_decided CHECK ((status = 'PROPOSED') = (decided_at IS NULL)),
            CONSTRAINT ck_referral_pool_refund_four_eyes CHECK (decided_by IS NULL OR decided_by <> proposed_by))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_refund_records_purchase ON referral_pool_refund_records "
               "(purchase_id)")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF to_regclass('public.referral_pool_refund_records') IS NOT NULL THEN
                IF EXISTS (SELECT 1 FROM referral_pool_refund_records WHERE status = 'APPROVED') THEN
                    RAISE EXCEPTION 'referral_pool_refund_records holds executed refunds; downgrade refused';
                END IF;
            END IF;
        END $$""")
    op.execute("DROP TABLE IF EXISTS referral_pool_refund_records")
