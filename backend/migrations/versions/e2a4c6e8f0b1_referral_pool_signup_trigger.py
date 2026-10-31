"""The Referral Pool queues a sponsorless member at sign-up (SIGNED_UP), not only after KYC approval.

Revision ID: e2a4c6e8f0b1
Revises: d1f3a5b7c9e2
Create Date: 2026-10-31

Owner rule (Shafi Abeid, 2026-10-31): a new member without a personal referral link is given a pool
sponsor without waiting for e-mail confirmation or KYC. Constraints only, no row rewritten. Downgrade
refuses while a SIGNED_UP event or queue row exists.
"""
from alembic import op


revision = "e2a4c6e8f0b1"
down_revision = "d1f3a5b7c9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE referral_pool_events DROP CONSTRAINT IF EXISTS ck_referral_pool_event_type")
    op.execute("ALTER TABLE referral_pool_events ADD CONSTRAINT ck_referral_pool_event_type CHECK (event_type IN "
               "('KYC_APPROVED', 'KYC_REJECTED', 'ACCOUNT_CHANGED', 'RISK_CLEARED', 'SIGNED_UP'))")
    op.execute("ALTER TABLE referral_pool_pending DROP CONSTRAINT IF EXISTS ck_referral_pool_pending_trigger")
    op.execute("ALTER TABLE referral_pool_pending ADD CONSTRAINT ck_referral_pool_pending_trigger CHECK "
               "(trigger_event IN ('KYC_APPROVED', 'SIGNED_UP'))")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM referral_pool_events WHERE event_type = 'SIGNED_UP')
               OR EXISTS (SELECT 1 FROM referral_pool_pending WHERE trigger_event = 'SIGNED_UP') THEN
                RAISE EXCEPTION 'SIGNED_UP rows exist: they cannot be represented before e2a4c6e8f0b1';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE referral_pool_pending DROP CONSTRAINT IF EXISTS ck_referral_pool_pending_trigger")
    op.execute("ALTER TABLE referral_pool_pending ADD CONSTRAINT ck_referral_pool_pending_trigger CHECK "
               "(trigger_event IN ('KYC_APPROVED'))")
    op.execute("ALTER TABLE referral_pool_events DROP CONSTRAINT IF EXISTS ck_referral_pool_event_type")
    op.execute("ALTER TABLE referral_pool_events ADD CONSTRAINT ck_referral_pool_event_type CHECK (event_type IN "
               "('KYC_APPROVED', 'KYC_REJECTED', 'ACCOUNT_CHANGED', 'RISK_CLEARED'))")
