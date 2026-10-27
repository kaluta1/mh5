"""Marketplace: server-recorded buyer acceptance, seller verification, settlement initiation status.

Revision ID: f4b6d8a0c2e4
Revises: e3a5c7e9b1d3
Create Date: 2026-10-28

Additive on market_orders (production holds no marketplace order): six nullable columns, no row rewritten.

  * acceptance_reference       unique reference of the buyer's acceptance (server-generated)
  * acceptance_policy_version  the acceptance/policy text version the buyer acknowledged
  * seller_verified_at         the seller checked the acceptance before handing over
  * release_requested_at       settlement asked of the custodian (separate from acceptance)
  * release_request_error      last failed settlement request (kept for retry; never undoes acceptance)
  * support_reason             why support refunded the order (non-handover, duplicate charge, fraud, ...)

Downgrade drops the columns; it refuses while an order carries an acceptance reference.
"""
from alembic import op


revision = "f4b6d8a0c2e4"
down_revision = "e3a5c7e9b1d3"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("acceptance_reference", "VARCHAR(40)"),
    ("acceptance_policy_version", "VARCHAR(40)"),
    ("seller_verified_at", "TIMESTAMP"),
    ("release_requested_at", "TIMESTAMP"),
    ("release_request_error", "VARCHAR(200)"),
    ("support_reason", "VARCHAR(40)"),
)


def upgrade() -> None:
    for name, kind in _COLUMNS:
        op.execute(f"ALTER TABLE market_orders ADD COLUMN IF NOT EXISTS {name} {kind}")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_market_orders_acceptance_reference ON market_orders "
               "(acceptance_reference) WHERE acceptance_reference IS NOT NULL")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM market_orders WHERE acceptance_reference IS NOT NULL) THEN
                RAISE EXCEPTION 'market_orders holds buyer acceptances; downgrade refused';
            END IF;
        END $$""")
    op.execute("DROP INDEX IF EXISTS uq_market_orders_acceptance_reference")
    for name, _kind in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE market_orders DROP COLUMN IF EXISTS {name}")
