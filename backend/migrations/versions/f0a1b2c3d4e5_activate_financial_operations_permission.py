"""Finance & Payments: the activate_financial_operations permission.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-10-12

Data only: ONE row in permissions. No table, column, index or constraint is
added or changed.

manage_payment_settings used to cover everything in Finance & Payments,
including switching automatic payouts on. Configuring and activating are now
two authorities: an activation (automatic payouts, USD settlement, the approval
of the network fee limits, the provider fee behaviour, lifting a payout
suspension, payout settings while automatic payouts are on) needs this
permission IN ADDITION to manage_payment_settings
(app/services/payment_config.py: activation_required).

The permission is inserted only if it does not exist and is assigned to NO
role and NO user: granting it is a deliberate act
(app/scripts/grant_payment_permissions.py --permission ...). Nobody can
activate anything after this migration until that is done.

No user, role, role_permissions, commission, balance, deposit, cashout,
journal or payment_settings row is read or changed. Downgrade removes the row
only if no role holds it.
"""
from alembic import op


revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None

NAME = "activate_financial_operations"
DESCRIPTION = ("Activate financial operations (with manage_payment_settings): automatic payouts, USD settlement, "
               "network fee approval, provider fee behaviour, payout reactivation")


def upgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL THEN
                INSERT INTO permissions (name, description, category, created_at, updated_at)
                SELECT '{NAME}', '{DESCRIPTION}', 'admin', now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = '{NAME}');
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.permissions') IS NOT NULL
               AND to_regclass('public.role_permissions') IS NOT NULL THEN
                DELETE FROM permissions p
                WHERE p.name = '{NAME}'
                  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.permission_id = p.id);
            END IF;
        END $$""")
