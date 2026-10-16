"""Payout review of historical commissions.

Revision ID: a8c0e2f4b6d8
Revises: f9b1c3d5e7a9
Create Date: 2026-10-16

Additive only. One new, EMPTY table, commission_payout_reviews. From this
release a historical commission (business_model_version other than NEW_V2; in production NULL, written by the
retired engine) is held from every payout path until an authorised
administrator records an explicit decision for it here (RELEASE or CANCEL).

No commission row is read or changed by this revision: the hold is applied by
the application. Re-running is a no-op; downgrade drops the table only when it
is empty.
"""
from alembic import op

revision = "a8c0e2f4b6d8"
down_revision = "f9b1c3d5e7a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS commission_payout_reviews (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            commission_id INTEGER NOT NULL UNIQUE REFERENCES affiliate_commissions(id),
            decision VARCHAR(10) NOT NULL,
            reason TEXT NOT NULL,
            evidence_reference VARCHAR(255) NULL,
            decided_by INTEGER NOT NULL REFERENCES users(id),
            decided_at TIMESTAMP NOT NULL DEFAULT now(),
            executed_at TIMESTAMP NULL,
            CONSTRAINT ck_commission_payout_reviews_decision CHECK (decision IN ('RELEASE', 'CANCEL'))
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_commission_payout_reviews_id ON commission_payout_reviews (id)")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.commission_payout_reviews') IS NOT NULL THEN
                IF EXISTS (SELECT 1 FROM commission_payout_reviews) THEN
                    RAISE EXCEPTION 'commission_payout_reviews holds decisions; refusing to drop it';
                END IF;
                DROP TABLE commission_payout_reviews;
            END IF;
        END $$""")
