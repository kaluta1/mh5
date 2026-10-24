"""Multi-Unit Referral Pool P6: durable pool events (outbox) and risk reviews. Schema only.

Revision ID: c1e3a5b7d9f2
Revises: a7c9e1f3b5d2
Create Date: 2026-10-23

Additive: two new tables, no existing row touched.

  * referral_pool_events        written INSIDE a KYC decision's transaction (it commits or rolls
                                back with the decision), processed later by the pool worker in its
                                own short transaction. One row per decision (dedupe_key).
  * referral_pool_risk_reviews  anti-abuse signals for manual review. Evidence is a SHA-256 of the
                                normalized signal (no new personal data is stored). Only a
                                duplicate verified identity blocks (pending review); shared
                                wallets or login IPs are recorded, never blocking.

Downgrade drops both tables (events are a work queue; reviews are re-derivable by a rescan).
"""
from alembic import op


revision = "c1e3a5b7d9f2"
down_revision = "a7c9e1f3b5d2"
branch_labels = None
depends_on = None

_BASE = "id SERIAL PRIMARY KEY, created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now()"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_events ({_BASE},
            user_id INTEGER NOT NULL REFERENCES users(id),
            event_type VARCHAR(30) NOT NULL,
            kyc_verification_id INTEGER REFERENCES kyc_verifications(id),
            dedupe_key VARCHAR(160) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error VARCHAR(200),
            processed_at TIMESTAMP,
            CONSTRAINT uq_referral_pool_event_dedupe UNIQUE (dedupe_key),
            CONSTRAINT ck_referral_pool_event_type CHECK (event_type IN
                ('KYC_APPROVED','KYC_REJECTED','ACCOUNT_CHANGED','RISK_CLEARED')),
            CONSTRAINT ck_referral_pool_event_status CHECK (status IN ('PENDING','DONE','FAILED')),
            CONSTRAINT ck_referral_pool_event_attempts CHECK (attempts >= 0),
            CONSTRAINT ck_referral_pool_event_processed CHECK ((status = 'PENDING') = (processed_at IS NULL)))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_events_pending ON referral_pool_events (id) "
               "WHERE status = 'PENDING'")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_events_user ON referral_pool_events (user_id)")

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS referral_pool_risk_reviews ({_BASE},
            user_id INTEGER NOT NULL REFERENCES users(id),
            signal VARCHAR(40) NOT NULL,
            evidence_hash VARCHAR(64) NOT NULL,
            related_user_ids TEXT,
            blocking BOOLEAN NOT NULL DEFAULT false,
            status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            decided_by INTEGER REFERENCES users(id),
            decided_at TIMESTAMP,
            decision_note VARCHAR(500),
            CONSTRAINT uq_referral_pool_risk_review UNIQUE (user_id, signal, evidence_hash),
            CONSTRAINT ck_referral_pool_risk_signal CHECK (signal IN
                ('DUPLICATE_KYC_IDENTITY','SHARED_PAYOUT_WALLET','SHARED_LOGIN_IP')),
            CONSTRAINT ck_referral_pool_risk_status CHECK (status IN ('OPEN','CLEARED','CONFIRMED')),
            CONSTRAINT ck_referral_pool_risk_decided CHECK ((status = 'OPEN') = (decided_at IS NULL)),
            CONSTRAINT ck_referral_pool_risk_blocking CHECK (NOT blocking OR signal = 'DUPLICATE_KYC_IDENTITY'))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referral_pool_risk_blocking ON referral_pool_risk_reviews (user_id) "
               "WHERE blocking AND status IN ('OPEN','CONFIRMED')")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS referral_pool_risk_reviews")
    op.execute("DROP TABLE IF EXISTS referral_pool_events")
