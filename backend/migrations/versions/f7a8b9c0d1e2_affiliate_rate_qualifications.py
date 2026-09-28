"""Permanent qualified direct-affiliate rate (client rule confirmed 2026-09-28).

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-09-28

Additive only: one new table, affiliate_rate_qualifications (at most one row per member).

Why a table is required: the 40% rate is permanent once earned, but the facts it is derived
from are not immutable (a provider sync can revoke a referral's KYC, an approval can be
re-run and move processed_at, an account can be closed, an admin can change a sponsor).
A pure on-the-fly derivation could therefore later revoke a legitimately earned rate. The
row is written once, at the moment the rule is first met, and never updated or deleted by
the application.

Nothing is backfilled: the rule applies prospectively. No existing row is read or rewritten.
Downgrade drops only the new table.
"""
from alembic import op


revision = "f7a8b9c0d1e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS affiliate_rate_qualifications (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            rule_version VARCHAR(40) NOT NULL,
            qualified_rate NUMERIC(5, 4) NOT NULL,
            qualified_at TIMESTAMP NOT NULL,
            window_start TIMESTAMP NOT NULL,
            window_deadline TIMESTAMP NOT NULL,
            qualifying_referral_count INTEGER NOT NULL,
            required_referral_count INTEGER NOT NULL,
            CONSTRAINT uq_affiliate_rate_qualification_user UNIQUE (user_id),
            CONSTRAINT ck_affiliate_rate_qualification_rate CHECK (qualified_rate > 0 AND qualified_rate <= 1),
            CONSTRAINT ck_affiliate_rate_qualification_window CHECK (qualified_at <= window_deadline))""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_affiliate_rate_qualifications_id ON affiliate_rate_qualifications (id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS affiliate_rate_qualifications")
