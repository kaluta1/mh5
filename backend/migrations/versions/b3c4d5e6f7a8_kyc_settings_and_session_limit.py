"""KYC settings in the Admin Panel, the manage_kyc_settings permission and the
provider-session limit of a KYC attempt.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-10-14

Additive only. Nothing that exists is changed, moved or deleted.

  * kyc_settings (NEW, one row, id = 1): whether Kaluta KYC is switched on in
    the Admin Panel. The table is created EMPTY: until an administrator saves a
    setting, the server environment decides exactly as before
    (KALUTA_KYC_ENABLED). The Kaluta API key and webhook secret are not stored
    here; they go to the existing payment_credentials table as AES-256-GCM
    ciphertext (provider "kaluta"). Nothing is imported from the environment.
  * kyc_verifications.attempt_sessions_count / attempt_sessions_granted (NEW,
    NOT NULL DEFAULT 0): the provider sessions opened for the current attempt
    and the extra ones an administrator allowed. Existing rows get 0.
  * permissions: ONE row, manage_kyc_settings, assigned to NO role and NO user
    (granting it: app/scripts/grant_payment_permissions.py --permission
    manage_kyc_settings). Until then nobody can change the KYC fee or the
    Kaluta settings; everything else is unaffected.

No user, role, role_permissions, payment, deposit, ledger or commission row is
read or changed. Re-running the upgrade is a no-op. Downgrade removes only what
was added (the permission only if no role holds it).
"""
from alembic import op


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

PERMISSION = "manage_kyc_settings"
DESCRIPTION = ("Change the Member KYC Verification Fee and the Kaluta KYC settings (API key, webhook secret, "
               "on/off), and allow a member another provider session")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS kyc_settings (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            kaluta_enabled BOOLEAN NULL,
            version INTEGER NOT NULL DEFAULT 0,
            updated_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
            CONSTRAINT ck_kyc_settings_single_row CHECK (id = 1)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kyc_settings_id ON kyc_settings (id)")
    op.execute("ALTER TABLE kyc_verifications ADD COLUMN IF NOT EXISTS attempt_sessions_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE kyc_verifications ADD COLUMN IF NOT EXISTS attempt_sessions_granted INTEGER NOT NULL DEFAULT 0")
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL THEN
                INSERT INTO permissions (name, description, category, created_at, updated_at)
                SELECT '{PERMISSION}', '{DESCRIPTION}', 'admin', now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = '{PERMISSION}');
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL
               AND to_regclass('public.role_permissions') IS NOT NULL THEN
                DELETE FROM permissions p
                WHERE p.name = '{PERMISSION}'
                  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id);
            END IF;
        END $$""")
    op.execute("ALTER TABLE kyc_verifications DROP COLUMN IF EXISTS attempt_sessions_granted")
    op.execute("ALTER TABLE kyc_verifications DROP COLUMN IF EXISTS attempt_sessions_count")
    op.execute("DROP TABLE IF EXISTS kyc_settings")
