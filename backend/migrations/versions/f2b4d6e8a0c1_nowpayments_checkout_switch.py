"""NOWPayments checkout switch, separate from automatic payouts.

Revision ID: f2b4d6e8a0c1
Revises: e1a3b5c7d9f2
Create Date: 2026-10-21

Additive only. One column on the one-row payment_settings table:

  * payment_settings.checkout_enabled BOOLEAN NOT NULL DEFAULT true
    A NEW NOWPayments checkout needs provider_enabled AND checkout_enabled.
    Payouts never read it.

Nothing is activated: with the default (true), what is in force is exactly what
was in force before (checkout = provider_enabled). On production
provider_enabled is false, so checkout and payouts both stay off until an
administrator changes them. No row is updated by this migration (a constant
default is stored in the catalogue, not written into rows). Re-running is a
no-op. Downgrade drops only this column.
"""
from alembic import op


revision = "f2b4d6e8a0c1"
down_revision = "e1a3b5c7d9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE payment_settings ADD COLUMN IF NOT EXISTS checkout_enabled BOOLEAN NOT NULL DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE payment_settings DROP COLUMN IF EXISTS checkout_enabled")
