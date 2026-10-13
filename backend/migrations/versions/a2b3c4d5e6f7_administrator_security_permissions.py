"""Administrator security: manage_administrators and grant_manual_payments.

Revision ID: a2b3c4d5e6f7
Revises: f0a1b2c3d4e5
Create Date: 2026-10-13

Data only: TWO rows in permissions. No table, column, index or constraint is
added or changed.

The is_admin flag alone no longer allows
  * making somebody an administrator, taking that away, or switching an
    administrator's account on or off   -> manage_administrators
  * recording a payment by hand          -> grant_manual_payments
(app/services/admin_security.py; both also need the current password).

The permissions are inserted only if they do not exist and are assigned to NO
role and NO user: granting them is a deliberate act
(app/scripts/grant_payment_permissions.py --permission ...). Until that is
done NOBODY can perform those two actions; everything else an administrator
does is unaffected.

No user, role, role_permissions or financial row is read or changed. Downgrade
removes each row only if no role holds it.
"""
from alembic import op


revision = "a2b3c4d5e6f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("manage_administrators",
     "Make an account an administrator or remove that, and activate or deactivate an administrator account"),
    ("grant_manual_payments",
     "Record a payment by hand for a member (creates a validated deposit, its ledger entries and commissions)"),
)


def upgrade() -> None:
    for name, description in _PERMISSIONS:
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.permissions') IS NOT NULL THEN
                    INSERT INTO permissions (name, description, category, created_at, updated_at)
                    SELECT '{name}', '{description}', 'admin', now(), now()
                    WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = '{name}');
                END IF;
            END $$""")


def downgrade() -> None:
    for name, _description in _PERMISSIONS:
        op.execute(f"""
            DO $$
            BEGIN
                IF to_regclass('public.permissions') IS NOT NULL
                   AND to_regclass('public.role_permissions') IS NOT NULL THEN
                    DELETE FROM permissions p
                    WHERE p.name = '{name}'
                      AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id);
                END IF;
            END $$""")
