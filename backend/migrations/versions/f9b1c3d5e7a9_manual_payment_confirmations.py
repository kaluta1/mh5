"""Two-administrator confirmation of manually recorded payments.

Revision ID: f9b1c3d5e7a9
Revises: e6f7a8b9c0d1
Create Date: 2026-10-16

Additive only. One new, EMPTY table, manual_payment_confirmations: an
administrator records that a member paid outside the payment provider; the
payment is credited (and any commission created) only when a different
authorised administrator confirms that the money was received.

No existing row is read or changed. Payments recorded before this revision
keep their state. Re-running is a no-op; downgrade drops the table only when
it is empty (a decision record is never destroyed).
"""
from alembic import op

revision = "f9b1c3d5e7a9"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS manual_payment_confirmations (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            deposit_id INTEGER NOT NULL UNIQUE REFERENCES deposits(id),
            member_id INTEGER NOT NULL REFERENCES users(id),
            product_code VARCHAR(50) NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            currency VARCHAR(10) NOT NULL DEFAULT 'USD',
            status VARCHAR(12) NOT NULL DEFAULT 'REQUESTED',
            created_new_deposit BOOLEAN NOT NULL DEFAULT TRUE,
            verify_identity_requested BOOLEAN NOT NULL DEFAULT FALSE,
            requested_by INTEGER NOT NULL REFERENCES users(id),
            requested_at TIMESTAMP NOT NULL DEFAULT now(),
            request_reason TEXT NOT NULL,
            decided_by INTEGER NULL REFERENCES users(id),
            decided_at TIMESTAMP NULL,
            evidence_reference VARCHAR(255) NULL,
            decision_note TEXT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT ck_manual_payment_confirmations_status
                CHECK (status IN ('REQUESTED', 'CONFIRMED', 'REJECTED', 'CANCELLED')),
            CONSTRAINT ck_manual_payment_confirmations_two_people
                CHECK (decided_by IS NULL OR decided_by <> requested_by)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_payment_confirmations_id ON manual_payment_confirmations (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_payment_confirmations_member_id ON manual_payment_confirmations (member_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_payment_confirmations_status ON manual_payment_confirmations (status)")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_payment_open_per_member_product
                  ON manual_payment_confirmations (member_id, product_code) WHERE status = 'REQUESTED'""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.manual_payment_confirmations') IS NOT NULL THEN
                IF EXISTS (SELECT 1 FROM manual_payment_confirmations) THEN
                    RAISE EXCEPTION 'manual_payment_confirmations holds records; refusing to drop it';
                END IF;
                DROP TABLE manual_payment_confirmations;
            END IF;
        END $$""")
