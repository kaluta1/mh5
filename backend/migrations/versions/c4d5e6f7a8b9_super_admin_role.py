"""The Super Admin role.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-14

Additive only. Nothing that exists is changed, moved or deleted.

  * roles: ONE row, `super_admin`, a system role (is_system = true) with NO
    permission rows and NO member. Holding it gives every administrative
    permission (app.services.super_admin decides that in code, so a permission
    added later is covered without another migration).
  * users.role_before_super_admin_id (NEW, NULL, -> roles.id ON DELETE SET
    NULL): the role an account had before it became a Super Admin, given back
    when the role is revoked. NULL for every existing row.

Nobody becomes a Super Admin through this migration. The first Super Admins
are named by app/scripts/bootstrap_super_admins.py (dry run by default, only
while there is none); after that, only a Super Admin grants or revokes the
role (PUT /admin/users/{id}/super-admin).

The upgrade stops, changing nothing, if a role called `super_admin` already
exists that this migration did not create (not a system role, or holding a
permission or a member): that role would otherwise become the Super Admin
role. Re-running the upgrade is a no-op. Downgrade removes the role and the
column only while nobody holds the role.

No existing user value, permission, role_permissions, payment, deposit,
ledger or commission row is read or changed.
"""
from alembic import op


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

ROLE = "super_admin"
DESCRIPTION = ("Super Admin: every administrative permission. Granted and revoked only by another Super Admin, "
               "with password confirmation")


def upgrade() -> None:
    op.execute(f"""
        DO $$
        DECLARE existing RECORD;
        BEGIN
            IF to_regclass('public.roles') IS NULL THEN
                RETURN;
            END IF;
            SELECT r.id, r.is_system,
                   (SELECT count(*) FROM role_permissions rp WHERE rp.role_id = r.id) AS permission_count,
                   (SELECT count(*) FROM users u WHERE u.role_id = r.id) AS member_count,
                   (SELECT count(*) FROM roles c WHERE c.inherit_from_id = r.id) AS child_count
              INTO existing
              FROM roles r WHERE r.name = '{ROLE}';
            IF FOUND THEN
                IF existing.is_system IS NOT TRUE OR existing.permission_count > 0 OR existing.member_count > 0
                   OR existing.child_count > 0 THEN
                    RAISE EXCEPTION 'A role named {ROLE} already exists and was not created by this migration '
                                    '(system=%, permissions=%, members=%, inheriting roles=%). Nothing was changed.',
                                    existing.is_system, existing.permission_count, existing.member_count,
                                    existing.child_count;
                END IF;
                RETURN;
            END IF;
            INSERT INTO roles (name, description, is_system, inherit_from_id, created_at, updated_at)
            VALUES ('{ROLE}', '{DESCRIPTION}', true, NULL, now(), now());
        END $$""")
    op.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS role_before_super_admin_id INTEGER NULL
            CONSTRAINT fk_users_role_before_super_admin REFERENCES roles(id) ON DELETE SET NULL""")


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.roles') IS NOT NULL THEN
                DELETE FROM roles r
                WHERE r.name = '{ROLE}' AND r.is_system
                  AND NOT EXISTS (SELECT 1 FROM users u WHERE u.role_id = r.id)
                  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id)
                  AND NOT EXISTS (SELECT 1 FROM roles c WHERE c.inherit_from_id = r.id);
            END IF;
        END $$""")
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.users') IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM roles WHERE name = '{ROLE}') THEN
                ALTER TABLE users DROP COLUMN IF EXISTS role_before_super_admin_id;
            END IF;
        END $$""")
