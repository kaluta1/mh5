"""KYC settings: sessions per attempt becomes an Admin Panel setting.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-15

Additive only. Nothing that exists is changed, moved or deleted.

  * kyc_settings.sessions_per_attempt (NEW, NULL): how many provider sessions
    one KYC attempt may open before an administrator must allow another. NULL
    (every existing row, and the table is normally empty) means the built-in
    default of 3, exactly the limit in force before this revision. Allowed
    values 1 to 10 (CHECK constraint).

From this release the database is the ONLY source of the Kaluta KYC settings
(on/off, API key, webhook secret): the KALUTA_KYC_ENABLED, KALUTA_API_KEY and
KALUTA_WEBHOOK_SECRET environment variables are no longer read. This revision
does NOT copy anything from the environment, does NOT create the settings row
and does NOT switch Kaluta KYC on: with no row, Kaluta KYC is OFF until an
administrator holding manage_kyc_settings saves the key, the secret and the
switch in Admin > KYC.

No user, role, permission, verification, payment, deposit, ledger or commission
row is read or changed. Re-running the upgrade is a no-op. Downgrade drops only
the new column.
"""
from alembic import op


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE kyc_settings ADD COLUMN IF NOT EXISTS sessions_per_attempt INTEGER NULL")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_kyc_settings_sessions_per_attempt') THEN
                ALTER TABLE kyc_settings ADD CONSTRAINT ck_kyc_settings_sessions_per_attempt
                    CHECK (sessions_per_attempt IS NULL OR sessions_per_attempt BETWEEN 1 AND 10);
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute("ALTER TABLE kyc_settings DROP CONSTRAINT IF EXISTS ck_kyc_settings_sessions_per_attempt")
    op.execute("ALTER TABLE kyc_settings DROP COLUMN IF EXISTS sessions_per_attempt")
