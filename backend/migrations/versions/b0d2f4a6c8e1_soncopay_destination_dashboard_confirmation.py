"""SoncoPay payout destinations: recorded dashboard confirmation, ownership evidence and suspension.

Revision ID: b0d2f4a6c8e1
Revises: a6c8e0f2b4d6
Create Date: 2026-11-02

SoncoPay Compliance conditions (2026-10-31): a destination must be confirmed in the SoncoPay dashboard
and the first payout waits 24 hours after that confirmation. The confirmation is never inferred from the
API registration: an administrator records its time and evidence. Additive nullable columns only; no
existing row changes (every existing destination simply has no recorded confirmation yet).
"""
from alembic import op


revision = "b0d2f4a6c8e1"
down_revision = "a6c8e0f2b4d6"
branch_labels = None
depends_on = None

COLUMNS = (
    ("dashboard_confirmed_at", "TIMESTAMP NULL"),
    ("dashboard_confirmed_by", "INTEGER NULL REFERENCES users(id)"),
    ("dashboard_evidence", "VARCHAR(300) NULL"),
    ("ownership_evidence", "VARCHAR(300) NULL"),
    ("recorded_at", "TIMESTAMP NULL"),
    ("suspended_at", "TIMESTAMP NULL"),
    ("suspended_by", "INTEGER NULL REFERENCES users(id)"),
    ("suspension_reason", "VARCHAR(300) NULL"),
)


def upgrade() -> None:
    for name, ddl in COLUMNS:
        op.execute(f"ALTER TABLE soncopay_payout_destinations ADD COLUMN IF NOT EXISTS {name} {ddl}")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM soncopay_payout_destinations
                       WHERE dashboard_confirmed_at IS NOT NULL OR suspended_at IS NOT NULL) THEN
                RAISE EXCEPTION 'Recorded SoncoPay confirmations or suspensions exist: export them before downgrading b0d2f4a6c8e1';
            END IF;
        END $$;
    """)
    for name, _ddl in reversed(COLUMNS):
        op.execute(f"ALTER TABLE soncopay_payout_destinations DROP COLUMN IF EXISTS {name}")
