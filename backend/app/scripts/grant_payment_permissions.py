#!/usr/bin/env python3
"""Grant (or revoke) the Finance & Payments permissions to ONE administrator.

manage_payment_settings (configuration, credentials, connection test) and
process_cashouts (cancel, record a USD settlement, settle an unknown payout,
run a payout cycle) are created by migration a5b6c7d8e9f0 and assigned to
nobody. Neither is implied by is_admin or by the 'all' wildcard, so after a
deployment somebody has to be given them deliberately. This tool does that
with the existing role / permission model, the same way as
grant_email_settings_permission:

  * the account must already be an ACTIVE ADMINISTRATOR;
  * a dedicated role "finance_manager[_<base role>]" is used. It INHERITS from
    the account's current role, so the account keeps every permission it has
    today, and it holds the chosen Finance & Payments permissions itself;
  * the account is moved to that role. Nobody else is affected.

DRY-RUN BY DEFAULT. Nothing is written without --apply.

    python -m app.scripts.grant_payment_permissions --email admin@example.com
    python -m app.scripts.grant_payment_permissions --email admin@example.com --apply
    python -m app.scripts.grant_payment_permissions --email admin@example.com --only process_cashouts --apply
    python -m app.scripts.grant_payment_permissions --email admin@example.com --revoke --apply

The database is the one in DATABASE_URL. The tool prints which database it is
connected to (host and name only) before doing anything.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.user import Permission, Role, User
from app.services import payment_config

ROLE_PREFIX = "finance_manager"
PERMISSIONS = (payment_config.PERMISSION_MANAGE, payment_config.PERMISSION_PROCESS)


class GrantError(Exception):
    pass


def _admin(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email.strip().lower()).first() or \
        db.query(User).filter(User.email == email.strip()).first()
    if user is None:
        raise GrantError("No account with this email address.")
    if not user.is_active or not user.is_admin:
        raise GrantError("The account must be an active administrator.")
    return user


def _audit(db: Session, user: User, action: str, old: dict, new: dict, actor_id: Optional[int]) -> None:
    db.add(AuditTrail(table_name="users", record_id=user.id, action=action, old_values=old, new_values=new,
                      user_id=actor_id))


def grant(db: Session, email: str, names: List[str], *, apply: bool = False,
          actor_id: Optional[int] = None) -> Tuple[str, Optional[str], bool]:
    """(action, role name, applied)."""
    user = _admin(db, email)
    missing = [n for n in names if not payment_config.has_permission(user, n)]
    if not missing:
        return "already_granted", user.role.name if user.role else None, False
    permissions = db.query(Permission).filter(Permission.name.in_(names)).all()
    if {p.name for p in permissions} != set(names):
        raise GrantError("The Finance & Payments permissions do not exist. Run the migrations first.")
    current = user.role
    if current is not None and current.name.startswith(ROLE_PREFIX):
        role, base, name = current, current.inherit_from, current.name      # already on a role of this tool
    else:
        base = current
        name = f"{ROLE_PREFIX}_{base.name}"[:64] if base is not None else ROLE_PREFIX
        role = db.query(Role).filter(Role.name == name).first()
        if role is not None and role.inherit_from_id != (base.id if base is not None else None):
            raise GrantError(f'A role named "{name}" already exists with a different base role.')
    if not apply:
        return "granted", name, False
    if role is None:
        role = Role(name=name, description="Administrator who may manage Finance & Payments", is_system=False,
                    inherit_from_id=base.id if base is not None else None)
        db.add(role)
        db.flush()
    for permission in permissions:
        if permission not in role.permissions:
            role.permissions.append(permission)
    old_role = current.name if current is not None else None
    user.role_id = role.id
    _audit(db, user, "PAYMENT_PERMISSION_GRANTED", {"role": old_role},
           {"role": name, "permissions": sorted(names)}, actor_id)
    db.commit()
    return "granted", name, True


def revoke(db: Session, email: str, *, apply: bool = False,
           actor_id: Optional[int] = None) -> Tuple[str, Optional[str], bool]:
    user = _admin(db, email)
    role = user.role
    if role is None or not role.name.startswith(ROLE_PREFIX):
        if any(payment_config.has_permission(user, n) for n in PERMISSIONS):
            raise GrantError("This account holds a permission through a role this tool did not create; "
                             "remove it with the role management API.")
        return "not_granted", role.name if role else None, False
    base_name = role.inherit_from.name if role.inherit_from is not None else None
    if not apply:
        return "revoked", base_name, False
    user.role_id = role.inherit_from_id
    _audit(db, user, "PAYMENT_PERMISSION_REVOKED", {"role": role.name}, {"role": base_name}, actor_id)
    db.commit()
    return "revoked", base_name, True


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
    parser.add_argument("--only", choices=PERMISSIONS, help="grant just this permission (default: both)")
    parser.add_argument("--revoke", action="store_true", help="remove the permissions instead of granting them")
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    print(f"Database: {_database_label()}")
    db = SessionLocal()
    try:
        if args.revoke:
            action, role_name, applied = revoke(db, args.email, apply=args.apply)
        else:
            action, role_name, applied = grant(db, args.email, [args.only] if args.only else list(PERMISSIONS),
                                               apply=args.apply)
    except GrantError as exc:
        db.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        db.close()
    mode = "APPLIED" if applied else ("no change needed" if action in ("already_granted", "not_granted")
                                      else "DRY RUN - nothing written (use --apply)")
    print(f"{action}: {args.email}, role: {role_name} [{mode}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
