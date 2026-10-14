#!/usr/bin/env python3
"""Grant (or revoke) Finance & Payments and administrator security permissions
to ONE administrator.

Six permissions exist, created by migrations and assigned to nobody. None is
implied by is_admin or by the 'all' wildcard, so somebody has to be given them
deliberately:

  manage_payment_settings         configuration, credentials, connection test
  activate_financial_operations   WITH manage_payment_settings: switch automatic
                                  payouts or USD settlement on, approve the
                                  network fee limits, confirm the provider fee
                                  behaviour, lift a payout suspension
  process_cashouts                cancel, record a USD settlement, settle an
                                  unknown payout, run a payout cycle
  manage_administrators           make an account an administrator or remove
                                  that; activate or deactivate an
                                  administrator account
  grant_manual_payments           record a payment by hand for a member
  manage_kyc_settings             the Member KYC Verification Fee, the Kaluta
                                  API key, webhook secret and on/off switch,
                                  and an extra provider session for a member

EVERY permission to grant must be named with --permission. There is no
default and no "all": nothing is granted that was not asked for by name.

This tool uses the existing role / permission model, the same way as
grant_email_settings_permission:

  * the account must already be an ACTIVE ADMINISTRATOR;
  * a dedicated role "finance_manager_<permissions>[_<base role>]" is used. It
    INHERITS from the account's current role, so the account keeps every
    permission it has today, and it holds exactly the Finance & Payments
    permissions named in its own name;
  * the account is moved to that role. A role is never given a permission it
    did not have when it was created, so nobody else is ever affected: two
    administrators share a role only when they were granted exactly the same
    permissions on the same base role.

DRY-RUN BY DEFAULT. Nothing is written without --apply.

    python -m app.scripts.grant_payment_permissions --email admin@example.com --permission manage_payment_settings
    python -m app.scripts.grant_payment_permissions --email admin@example.com --permission manage_payment_settings --apply
    python -m app.scripts.grant_payment_permissions --email admin@example.com --permission manage_payment_settings --permission process_cashouts --apply
    python -m app.scripts.grant_payment_permissions --email admin@example.com --revoke --permission process_cashouts --apply
    python -m app.scripts.grant_payment_permissions --email admin@example.com --revoke --apply

--revoke without --permission removes every Finance & Payments permission this
tool gave the account.

The database is the one in DATABASE_URL. The tool prints which database it is
connected to (host and name only) before doing anything.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.user import Permission, Role, User
from app.services import admin_security, payment_config

ROLE_PREFIX = "finance_manager"
PERMISSIONS = (payment_config.PERMISSION_MANAGE, payment_config.PERMISSION_PROCESS,
               payment_config.PERMISSION_ACTIVATE, admin_security.PERMISSION_MANAGE_ADMINS,
               admin_security.PERMISSION_GRANT_PAYMENTS, admin_security.PERMISSION_MANAGE_KYC)
# One letter per permission in the role name, always in this order.
_TAGS = ((payment_config.PERMISSION_MANAGE, "m"), (payment_config.PERMISSION_ACTIVATE, "a"),
         (payment_config.PERMISSION_PROCESS, "p"), (admin_security.PERMISSION_MANAGE_ADMINS, "r"),
         (admin_security.PERMISSION_GRANT_PAYMENTS, "g"), (admin_security.PERMISSION_MANAGE_KYC, "k"))


class GrantError(Exception):
    pass


def _admin(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email.strip().lower()).first() or \
        db.query(User).filter(User.email == email.strip()).first()
    if user is None:
        raise GrantError("No account with this email address.")
    if not user.is_active or not user.is_admin:
        raise GrantError("The account must be an active administrator.")
    if admin_security.role_is_super_admin_role(user.role):
        # It holds every permission already, and this tool would move it off
        # the Super Admin role. A Super Admin is managed by another Super Admin.
        raise GrantError("The account is a Super Admin: it holds every permission. Nothing was changed.")
    return user


def _audit(db: Session, user: User, action: str, old: dict, new: dict, actor_id: Optional[int]) -> None:
    db.add(AuditTrail(table_name="users", record_id=user.id, action=action, old_values=old, new_values=new,
                      user_id=actor_id))


def _named(names: Optional[Sequence[str]]) -> List[str]:
    """The permissions asked for, each one by name. Nothing is assumed."""
    chosen = list(dict.fromkeys(names or ()))
    unknown = sorted(set(chosen) - set(PERMISSIONS))
    if unknown:
        raise GrantError("Not a Finance & Payments permission: " + ", ".join(unknown))
    return chosen


def _own(role: Optional[Role]) -> Set[str]:
    """The Finance & Payments permissions a role holds ITSELF (not inherited)."""
    return {p.name for p in (role.permissions or [])} & set(PERMISSIONS) if role is not None else set()


def _split(user: User) -> Tuple[Optional[Role], Optional[Role]]:
    """(the role of this tool the account is on, the role it had before)."""
    current = user.role
    if current is not None and current.name.startswith(ROLE_PREFIX):
        return current, current.inherit_from
    return None, current


def role_name(permissions: Set[str], base: Optional[Role]) -> str:
    tags = "".join(tag for name, tag in _TAGS if name in permissions)
    return (f"{ROLE_PREFIX}_{tags}" + (f"_{base.name}" if base is not None else ""))[:64]


def _role_for(db: Session, permissions: Set[str], base: Optional[Role], *, apply: bool) -> Tuple[str, Optional[Role]]:
    """The role holding EXACTLY these permissions on this base. An existing
    role is used only as it is: it is never given another permission, because
    every account already on it would receive that permission too."""
    name = role_name(permissions, base)
    role = db.query(Role).filter(Role.name == name).first()
    if role is not None:
        if role.inherit_from_id != (base.id if base is not None else None):
            raise GrantError(f'A role named "{name}" already exists with a different base role.')
        if _own(role) != permissions:
            raise GrantError(f'A role named "{name}" already exists with other Finance & Payments permissions '
                             "than its name says. Nothing was changed; correct that role first.")
        return name, role
    if not apply:
        return name, None
    rows = db.query(Permission).filter(Permission.name.in_(permissions)).all()
    if {p.name for p in rows} != permissions:
        raise GrantError("A Finance & Payments permission does not exist. Run the migrations first.")
    role = Role(name=name, description="Finance & Payments: " + ", ".join(sorted(permissions)), is_system=False,
                inherit_from_id=base.id if base is not None else None)
    role.permissions = rows
    db.add(role)
    db.flush()
    return name, role


def grant(db: Session, email: str, names: Sequence[str], *, apply: bool = False,
          actor_id: Optional[int] = None) -> Tuple[str, Optional[str], bool]:
    """(action, role name, applied)."""
    names = _named(names)
    if not names:
        raise GrantError("Name every permission to grant with --permission. Nothing is granted by default.")
    user = _admin(db, email)
    missing = [n for n in names if not payment_config.has_permission(user, n)]
    if not missing:
        return "already_granted", user.role.name if user.role else None, False
    existing = db.query(Permission.name).filter(Permission.name.in_(missing)).all()
    if {row[0] for row in existing} != set(missing):
        raise GrantError("A Finance & Payments permission does not exist. Run the migrations first.")
    tool_role, base = _split(user)
    target = _own(tool_role) | set(missing)
    name, role = _role_for(db, target, base, apply=apply)
    if not apply:
        return "granted", name, False
    old_role = user.role.name if user.role is not None else None
    user.role_id = role.id
    _audit(db, user, "PAYMENT_PERMISSION_GRANTED", {"role": old_role},
           {"role": name, "permissions": sorted(missing)}, actor_id)
    db.commit()
    return "granted", name, True


def revoke(db: Session, email: str, names: Optional[Sequence[str]] = None, *, apply: bool = False,
           actor_id: Optional[int] = None) -> Tuple[str, Optional[str], bool]:
    """Remove the named permissions, or every one this tool gave when none is named."""
    names = _named(names)
    user = _admin(db, email)
    tool_role, base = _split(user)
    if tool_role is None:
        if any(payment_config.has_permission(user, n) for n in PERMISSIONS):
            raise GrantError("This account holds a permission through a role this tool did not create; "
                             "remove it with the role management API.")
        return "not_granted", user.role.name if user.role else None, False
    held = _own(tool_role)
    removed = held & set(names) if names else held
    if not removed:
        return "not_granted", tool_role.name, False
    remaining = held - removed
    if remaining:
        name, role = _role_for(db, remaining, base, apply=apply)
    else:
        name, role = (base.name if base is not None else None), base
    if not apply:
        return "revoked", name, False
    user.role_id = role.id if role is not None else None
    _audit(db, user, "PAYMENT_PERMISSION_REVOKED", {"role": tool_role.name},
           {"role": name, "permissions": sorted(removed)}, actor_id)
    db.commit()
    return "revoked", name, True


def _database_label() -> str:
    from sqlalchemy.engine import make_url

    from app.core.config import settings

    try:
        url = make_url(settings.DATABASE_URL)
        return f"{url.host or 'local'}/{url.database}"
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--email", required=True, help="email address of the administrator")
    parser.add_argument("--permission", action="append", choices=PERMISSIONS, default=[],
                        help="a permission to grant; repeat it for each one. Required to grant: there is no default")
    parser.add_argument("--revoke", action="store_true",
                        help="remove the named permissions (or every one this tool gave) instead of granting")
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    args = parser.parse_args(argv)
    if not args.revoke and not args.permission:
        parser.error("name every permission to grant with --permission; nothing is granted by default")

    from app.db.session import SessionLocal

    print(f"Database: {_database_label()}")
    db = SessionLocal()
    try:
        if args.revoke:
            action, role_name_, applied = revoke(db, args.email, args.permission, apply=args.apply)
        else:
            action, role_name_, applied = grant(db, args.email, args.permission, apply=args.apply)
    except GrantError as exc:
        db.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        db.close()
    mode = "APPLIED" if applied else ("no change needed" if action in ("already_granted", "not_granted")
                                      else "DRY RUN - nothing written (use --apply)")
    named = ", ".join(args.permission) or "every Finance & Payments permission of this tool"
    print(f"{action}: {args.email}, {named}, role: {role_name_} [{mode}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
