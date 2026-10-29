"""SoncoPay payout destinations: each approved member wallet as a SoncoPay payout destination, and the
owner's recorded authorization of member commission payouts from the SoncoPay merchant account.

Revision ID: c9e1f3a5b7d0
Revises: b8d0f2a4c6e9
Create Date: 2026-10-29

Additive: one new table and three nullable columns, no row rewritten. Downgrade refuses while a
destination exists (they are the record of which wallet each payout may go to).
"""
from alembic import op


revision = "c9e1f3a5b7d0"
down_revision = "b8d0f2a4c6e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS soncopay_payout_destinations (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL REFERENCES users(id),
            wallet_approval_id INTEGER NOT NULL REFERENCES payout_wallet_approvals(id),
            address VARCHAR(100) NOT NULL,
            environment VARCHAR(10) NOT NULL,
            status VARCHAR(24) NOT NULL DEFAULT 'QUEUED',
            destination_id VARCHAR(40),
            usable BOOLEAN NOT NULL DEFAULT false,
            usable_from TIMESTAMP,
            confirmed_at TIMESTAMP,
            registered_at TIMESTAMP,
            checked_at TIMESTAMP,
            disabled_at TIMESTAMP,
            last_error VARCHAR(60),
            CONSTRAINT uq_soncopay_destinations_approval UNIQUE (wallet_approval_id),
            CONSTRAINT uq_soncopay_destinations_destination UNIQUE (destination_id),
            CONSTRAINT ck_soncopay_destinations_environment CHECK (environment IN ('test', 'live')),
            CONSTRAINT ck_soncopay_destinations_status CHECK (status IN ('QUEUED', 'PENDING_CONFIRMATION', 'ACTIVE',
                                                                          'DISABLED', 'REJECTED', 'SUPERSEDED'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_soncopay_payout_destinations_id ON soncopay_payout_destinations (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soncopay_payout_destinations_user_id "
               "ON soncopay_payout_destinations (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soncopay_payout_destinations_status "
               "ON soncopay_payout_destinations (status)")
    op.execute("ALTER TABLE checkout_gateway_settings ADD COLUMN IF NOT EXISTS payouts_authorized_at TIMESTAMP")
    op.execute("ALTER TABLE checkout_gateway_settings ADD COLUMN IF NOT EXISTS payouts_authorized_by INTEGER "
               "REFERENCES users(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE checkout_gateway_settings ADD COLUMN IF NOT EXISTS payouts_authorization_note VARCHAR(500)")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('soncopay_payout_destinations') IS NOT NULL THEN
                IF EXISTS (SELECT 1 FROM soncopay_payout_destinations) THEN
                    RAISE EXCEPTION 'soncopay_payout_destinations holds payout destinations; refusing to drop it';
                END IF;
            END IF;
        END $$
    """)
    op.execute("DROP TABLE IF EXISTS soncopay_payout_destinations")
    op.execute("ALTER TABLE checkout_gateway_settings DROP COLUMN IF EXISTS payouts_authorization_note")
    op.execute("ALTER TABLE checkout_gateway_settings DROP COLUMN IF EXISTS payouts_authorized_by")
    op.execute("ALTER TABLE checkout_gateway_settings DROP COLUMN IF EXISTS payouts_authorized_at")
