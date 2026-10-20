#!/usr/bin/env python3
"""Name the FIRST Super Admins. Once only: while there is no Super Admin.

The Super Admin role (migration c4d5e6f7a8b9) starts with no member, and only
a Super Admin can grant it (PUT /admin/users/{id}/super-admin). This tool
breaks that circle once, from the server, for named accounts:

  * every account is named by BOTH its id and its email address, and both
    must match the same account (a typo cannot pick somebody else);
  * at least TWO accounts, so that from the start one Super Admin can act on
    the other (nobody acts on their own account) and neither is the last one.
    ONE account only with --single, said on purpose: that Super Admin can
    promote others in the application, but until a second one exists nobody
    can change or remove it (it is the last one, and nobody acts on their own
    account);
  * at most super_admin.MAX_SUPER_ADMINS accounts;
  * each must be an active administrator with a verified email address;
  * each must have a password that is NOT among the exposed ones
    (app.services.password_exposure). The list of exposed fingerprints must
    have been loaded (app/scripts/load_exposed_password_fingerprints.py):
    without it the tool cannot tell, and refuses;
  * it refuses if anybody is on the Super Admin role already: from then on
    the role is granted and revoked through the application, by a Super Admin.

Each account is moved to the Super Admin role (its previous role is kept on the
account, restored if the role is revoked, and written to the audit trail) and
one SUPER_ADMIN_BOOTSTRAP audit row per account is added.
Nothing else is changed: no password, no session, no other permission.

DRY-RUN BY DEFAULT. Nothing is written without --apply.

    python -m app.scripts.bootstrap_super_admins --account 12:owner@example.com --account 34:operator@example.com
    python -m app.scripts.bootstrap_super_admins --account 12:owner@example.com --account 34:operator@example.com --apply
    python -m app.scripts.bootstrap_super_admins --single --account 34:operator@example.com --apply

The database is the one in DATABASE_URL. The tool prints which database it is
connected to (host and name only) before doing anything.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import admin_security, password_exposure, super_admin

MINIMUM_ACCOUNTS = 2


class BootstrapError(Exception):
    pass


def parse_account(value: str) -> Tuple[int, str]:
    user_id, sep, email = value.partition(":")
    if not sep or not user_id.strip().isdigit() or "@" not in email:
        raise argparse.ArgumentTypeError("expected ID:EMAIL, for example 12:owner@example.com")
    return int(user_id), email.strip()


def plan(db: Session, accounts: Sequence[Tuple[int, str]], *, single: bool = False) -> Tuple[object, List[User]]:
    """Check everything; return (the Super Admin role, the accounts). Writes nothing."""
    ids = [user_id for user_id, _ in accounts]
    if len(set(ids)) != len(ids):
        raise BootstrapError("The same account is named twice.")
    if single:
        if len(ids) != 1:
            raise BootstrapError("--single names exactly one account.")
    elif len(ids) < MINIMUM_ACCOUNTS:
        raise BootstrapError(f"Name at least {MINIMUM_ACCOUNTS} accounts: a Super Admin never acts on their own "
                             "account, so a single one could never be managed. To start with one on purpose, use "
                             "--single.")
    if len(ids) > super_admin.MAX_SUPER_ADMINS:
        raise BootstrapError(f"Name at most {super_admin.MAX_SUPER_ADMINS} accounts: that is the most Super Admins "
                             "there can be.")
    role = admin_security.super_admin_role(db)
    if role is None:
        raise BootstrapError("The Super Admin role does not exist. Run the migrations first.")
    holders = db.query(User.id).filter(User.role_id == role.id).count()
    if holders:
        raise BootstrapError(f"{holders} account(s) already hold the Super Admin role. From now on a Super Admin "
                             "grants it in the Admin Panel; this tool does nothing.")
    if password_exposure.loaded_count(db) == 0:
        raise BootstrapError("The list of exposed password fingerprints is empty, so an exposed password could not be "
                             "recognised. Load it first (app/scripts/load_exposed_password_fingerprints.py).")
    users = []
    for user_id, email in accounts:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or (user.email or "").strip().lower() != email.lower():
            raise BootstrapError(f"Account {user_id}: no account with this id AND this email address.")
        if not admin_security.eligible_for_super_admin(user):
            raise BootstrapError(f"Account {user_id}: must be an active administrator with a verified email "
                                 "address.")
        if password_exposure.is_exposed(db, user):
            raise BootstrapError(f"Account {user_id}: {password_exposure.PASSWORD_CHANGE_REQUIRED}: its password was "
                                 "exposed and has not been changed since.")
        users.append(user)
    return role, users


def bootstrap(db: Session, accounts: Sequence[Tuple[int, str]], *, apply: bool = False,
              single: bool = False) -> List[User]:
    role, users = plan(db, accounts, single=single)
    if not apply:
        return users
    for user in users:
        old = {"role_id": user.role_id, "role": user.role.name if user.role is not None else None}
        user.role_before_super_admin_id = user.role_id     # given back if the role is ever revoked
        user.role_id = role.id
        new = {"role_id": role.id, "role": role.name}
        if single:
            new["single_initial_super_admin"] = True
        admin_security.audit(db, actor_id=None, record_id=user.id, action=admin_security.AUDIT_SUPER_ADMIN_BOOTSTRAP,
                             old=old, new=new)
    db.commit()
    return users


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
    parser.add_argument("--account", action="append", type=parse_account, default=[], required=True,
                        help="ID:EMAIL of an account to make a Super Admin; repeat it for each one")
    parser.add_argument("--single", action="store_true",
                        help="start with exactly ONE Super Admin, on purpose (default: at least two)")
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    print(f"Database: {_database_label()}")
    db = SessionLocal()
    try:
        users = bootstrap(db, args.account, apply=args.apply, single=args.single)
        listed = ", ".join(f"#{u.id}" for u in users)
    except BootstrapError as exc:
        db.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        db.close()
    mode = "APPLIED" if args.apply else "DRY RUN - nothing written (use --apply)"
    print(f"Super Admins: {listed}{' (single initial Super Admin)' if args.single else ''} [{mode}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
