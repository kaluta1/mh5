#!/usr/bin/env python3
"""Grant (or revoke) the manage_email_settings permission to ONE administrator.

manage_email_settings is created by migration b9c0d1e2f3a4 and assigned to
nobody. It is never implied by is_admin or by the 'all' wildcard, so after a
deployment somebody has to be given it deliberately. This tool does exactly
that with the existing role / permission model (no new mechanism):

  * the account must already be an ACTIVE ADMINISTRATOR;
  * a dedicated role "email_settings_manager[_<base role>]" is used. It
    INHERITS from the account's current role, so the account keeps every
    permission it has today, and it holds manage_email_settings itself;
  * the account is moved to that role. Nobody else is affected: the
    permission is not added to the shared admin role.

The same result can be obtained through the existing API by an account that
holds manage_roles and manage_users:
    POST /api/v1/rbac/roles              {name, inherit_from_id, permission_ids}
    POST /api/v1/rbac/users/assign-role  {user_id, role_id}

DRY-RUN BY DEFAULT. Nothing is written without --apply.

    python -m app.scripts.grant_email_settings_permission --email admin@example.com
    python -m app.scripts.grant_email_settings_permission --email admin@example.com --apply
    python -m app.scripts.grant_email_settings_permission --email admin@example.com --revoke --apply

The database is the one in DATABASE_URL. The tool prints which database it is
connected to (host and name only) before doing anything.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import Permission, Role, User
from app.services import email_settings_service as svc

ROLE_PREFIX = "email_settings_manager"


class GrantError(Exception):
    pass


@dataclass(frozen=True)
class GrantResult:
    action: str          # "granted" | "already_granted" | "revoked" | "not_granted"
    user_id: int
    role_name: Optional[str]
    applied: bool


def _admin(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email.strip().lower()).first() or \
        db.query(User).filter(User.email == email.strip()).first()
    if user is None:
        raise GrantError("No account with this email address.")
    if not user.is_active or not user.is_admin:
        raise GrantError("The account must be an active administrator.")
    return user


def grant(db: Session, email: str, *, apply: bool = False, actor_id: Optional[int] = None) -> GrantResult:
    user = _admin(db, email)
    if svc.can_manage_email_settings(user):
        return GrantResult("already_granted", user.id, user.role.name if user.role else None, False)
    permission = db.query(Permission).filter(Permission.name == svc.PERMISSION_MANAGE_EMAIL_SETTINGS).first()
    if permission is None:
        raise GrantError("The manage_email_settings permission does not exist. Run the migrations first.")
    base = user.role
    name = f"{ROLE_PREFIX}_{base.name}"[:64] if base is not None else ROLE_PREFIX
    role = db.query(Role).filter(Role.name == name).first()
    if role is not None and role.inherit_from_id != (base.id if base is not None else None):
        raise GrantError(f'A role named "{name}" already exists with a different base role.')
    if not apply:
        return GrantResult("granted", user.id, name, False)
    if role is None:
        role = Role(name=name, description="Administrator who may manage Email Settings", is_system=False,
                    inherit_from_id=base.id if base is not None else None)
        db.add(role)
        db.flush()
    if permission not in role.permissions:
        role.permissions.append(permission)
    old_role = base.name if base is not None else None
    user.role_id = role.id
    svc.audit(db, actor_id=actor_id, action="EMAIL_PERMISSION_GRANTED", record_id=user.id,
              old={"role": old_role}, new={"role": name, "user_id": user.id})
    db.commit()
    return GrantResult("granted", user.id, name, True)


def revoke(db: Session, email: str, *, apply: bool = False, actor_id: Optional[int] = None) -> GrantResult:
    user = _admin(db, email)
    role = user.role
    if role is None or not role.name.startswith(ROLE_PREFIX):
        if svc.can_manage_email_settings(user):
            raise GrantError("This account holds the permission through a role this tool did not create; "
                             "remove it with the role management API.")
        return GrantResult("not_granted", user.id, role.name if role else None, False)
    if not apply:
        return GrantResult("revoked", user.id, role.name, False)
    base_id = role.inherit_from_id
    base_name = role.inherit_from.name if role.inherit_from is not None else None
    user.role_id = base_id
    svc.audit(db, actor_id=actor_id, action="EMAIL_PERMISSION_REVOKED", record_id=user.id,
              old={"role": role.name}, new={"role": base_name, "user_id": user.id})
    db.commit()
    return GrantResult("revoked", user.id, base_name, True)


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
    parser.add_argument("--revoke", action="store_true", help="remove the permission instead of granting it")
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    print(f"Database: {_database_label()}")
    db = SessionLocal()
    try:
        result = (revoke if args.revoke else grant)(db, args.email, apply=args.apply)
    except GrantError as exc:
        db.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        db.close()
    mode = "APPLIED" if result.applied else ("no change needed" if result.action in ("already_granted", "not_granted")
                                             else "DRY RUN - nothing written (use --apply)")
    print(f"{result.action}: user #{result.user_id}, role: {result.role_name} [{mode}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
