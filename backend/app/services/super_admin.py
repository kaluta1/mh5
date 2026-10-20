"""Who is a Super Admin. The ONE rule every permission check asks.

A Super Admin holds every administrative permission, the protected ones
included (Finance & Payments, administrator management, manual payments, the
KYC settings, the email settings, child-safety resolution). It is a role: the
system role `super_admin`, created by migration c4d5e6f7a8b9 with no member.

A Super Admin is an account that is ALL of:
  * active and not deleted;
  * an administrator (`is_admin`);
  * on the system role named `super_admin`.

Holding every permission changes nothing else. The safeguards that do not
depend on a permission stay in force for a Super Admin as for anybody: the
current password for every privileged action, the audit trail, no privileged
action on one's own account, no payment recorded for one's own referral line,
the financial activation rules and master switches, and the server
environment switches.

Granting and revoking (app.services.admin_security) need a Super Admin, the
current password, never on one's own account, and never leave the platform
without an active Super Admin. At most MAX_SUPER_ADMINS accounts hold the role.

This module imports nothing from the application, so every permission check
can use it without an import cycle.
"""
from __future__ import annotations

SUPER_ADMIN_ROLE_NAME = "super_admin"
# Seats on the role. Every account on it counts, switched off or not: one
# switched off can be switched back on without a new grant.
MAX_SUPER_ADMINS = 5


def is_super_admin_role(role) -> bool:
    """Is this THE Super Admin role (the system role, not a look-alike)?"""
    return (role is not None and getattr(role, "name", None) == SUPER_ADMIN_ROLE_NAME
            and getattr(role, "is_system", False) is True)


def is_super_admin(user) -> bool:
    """An active, not deleted administrator on the Super Admin role."""
    if user is None:
        return False
    if getattr(user, "is_active", False) is not True or getattr(user, "is_deleted", False) is True:
        return False
    if getattr(user, "is_admin", False) is not True:
        return False
    return is_super_admin_role(getattr(user, "role", None))
