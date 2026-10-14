"""Safeguards for the privileged administrator actions.

One administrator account used to be enough to create further administrators
and to record payments by hand: `is_admin` alone allowed both. Now:

  * making somebody an administrator (or taking that away, or switching an
    administrator account on or off) needs the explicit
    `manage_administrators` permission;
  * recording a payment by hand needs the explicit `grant_manual_payments`
    permission;
  * both need the administrator's CURRENT PASSWORD in the same request, are
    refused on the administrator's own account, and are written to the audit
    trail, refusals included.

Like the Finance & Payments permissions, these are held only by a role that
holds them EXPLICITLY: never implied by is_admin or the 'all' wildcard, and
assigned to nobody by the migration that creates them
(app/scripts/grant_payment_permissions.py grants them by name).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.user import User
from app.services import payment_config, reauth, super_admin

logger = logging.getLogger(__name__)

PERMISSION_MANAGE_ADMINS = "manage_administrators"
PERMISSION_GRANT_PAYMENTS = "grant_manual_payments"
# The KYC fee and the Kaluta settings (app.services.kyc_settings).
PERMISSION_MANAGE_KYC = "manage_kyc_settings"

# Permissions that are granted to a named administrator on purpose, by the
# grant tool, and never through the general role management API.
PROTECTED_PERMISSIONS = frozenset({
    PERMISSION_MANAGE_ADMINS, PERMISSION_GRANT_PAYMENTS, PERMISSION_MANAGE_KYC,
    payment_config.PERMISSION_MANAGE, payment_config.PERMISSION_PROCESS, payment_config.PERMISSION_ACTIVATE,
})
# Roles that make their holder an administrator (admin.check_admin) or open everything.
ADMIN_ROLE_NAME = "admin"
WILDCARD_PERMISSION = "all"

AUDIT_DENIED = "ADMIN_ACTION_DENIED"
AUDIT_SUPER_ADMIN_GRANTED = "SUPER_ADMIN_GRANTED"
AUDIT_SUPER_ADMIN_REVOKED = "SUPER_ADMIN_REVOKED"
AUDIT_SUPER_ADMIN_BOOTSTRAP = "SUPER_ADMIN_BOOTSTRAP"

SUPER_ADMIN_REQUIRED = "SUPER_ADMIN_REQUIRED"


class AdminSecurityError(Exception):
    """A privileged action was refused. Nothing was changed."""

    def __init__(self, code: str, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def has_permission(user, permission: str) -> bool:
    """Only a role that EXPLICITLY holds the permission (same rule as Finance & Payments)."""
    return payment_config.has_permission(user, permission)


def is_administrator(user) -> bool:
    """The is_admin flag or the 'admin' role (what admin.check_admin accepts)."""
    if user is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    role = getattr(user, "role", None)
    return role is not None and getattr(role, "name", None) == ADMIN_ROLE_NAME


def role_has_protected_permission(role) -> bool:
    """Does this role hold a protected permission, itself or by inheritance?
    The Super Admin role holds them all."""
    seen = set()
    while role is not None and getattr(role, "id", None) not in seen:
        seen.add(getattr(role, "id", None))
        if getattr(role, "name", None) == super_admin.SUPER_ADMIN_ROLE_NAME:
            return True
        if {p.name for p in (role.permissions or [])} & PROTECTED_PERMISSIONS:
            return True
        role = getattr(role, "inherit_from", None)
    return False


def role_is_privileged(role) -> bool:
    """Does holding this role make somebody an administrator, or give them a
    protected permission (directly or by inheritance)?"""
    seen = set()
    while role is not None and getattr(role, "id", None) not in seen:
        seen.add(getattr(role, "id", None))
        if getattr(role, "name", None) in (ADMIN_ROLE_NAME, super_admin.SUPER_ADMIN_ROLE_NAME):
            return True
        names = {p.name for p in (role.permissions or [])}
        if WILDCARD_PERMISSION in names or names & PROTECTED_PERMISSIONS:
            return True
        role = getattr(role, "inherit_from", None)
    return False


UPLINE_MAX_DEPTH = 64


def upline_ids(db: Session, user_id: int) -> set:
    """Every account above this one in the referral structure: the sponsor,
    the sponsor's sponsor and so on, by BOTH records the platform keeps
    (users.sponsor_id and the affiliate tree), which can disagree.

    Safe on bad data: a sponsor that does not exist ends that branch, an
    account that sponsors itself is ignored, a cycle is walked once, and the
    walk is bounded. The account itself is never in the result unless a cycle
    leads back to it."""
    from app.models.affiliate import AffiliateTree

    found: set = set()
    frontier = [int(user_id)]
    for _depth in range(UPLINE_MAX_DEPTH):
        if not frontier:
            break
        parents: set = set()
        for row in db.query(User.sponsor_id).filter(User.id.in_(frontier)).all():
            parents.add(row[0])
        for row in db.query(AffiliateTree.sponsor_id).filter(AffiliateTree.user_id.in_(frontier)).all():
            parents.add(row[0])
        fresh = {int(p) for p in parents if p is not None} - found
        found |= fresh
        frontier = [p for p in fresh if p != int(user_id)]
    return found


def earns_from_payment_by(db: Session, actor_id: int, payer_id: int) -> bool:
    """Is the actor anywhere above the payer in the referral structure? Then a
    payment recorded for the payer can pay the actor a commission, directly
    or, under a multi-level rule, indirectly."""
    return int(actor_id) in upline_ids(db, payer_id)


def audit(db: Session, *, actor_id: Optional[int], record_id: int, action: str, old: Optional[dict] = None,
          new: Optional[dict] = None, ip: Optional[str] = None, user_agent: Optional[str] = None) -> None:
    """Add an audit row to the current transaction. Never a password or a token."""
    db.add(AuditTrail(table_name="users", record_id=int(record_id), action=action, old_values=old or None,
                      new_values=new or None, user_id=actor_id, ip_address=(ip or None),
                      user_agent=(user_agent or None)[:255] if user_agent else None, timestamp=datetime.utcnow()))


def record_denial(db: Session, *, actor, target_id: int, attempted: str, code: str, ip: Optional[str] = None) -> None:
    """A refused privileged action is kept, on its own: whatever the request
    had started is rolled back first, and a failure to write the record never
    turns the refusal into anything else."""
    try:
        db.rollback()
        audit(db, actor_id=getattr(actor, "id", None), record_id=target_id, action=AUDIT_DENIED,
              new={"attempted": attempted, "reason": code}, ip=ip)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("Could not record a refused administrator action (%s)", type(exc).__name__)


def authorize(db: Session, actor, *, permission: Optional[str], password: Optional[str], target_id: int,
              attempted: str, ip: Optional[str] = None, super_admin_only: bool = False) -> None:
    """The four conditions of a privileged action, in this order: an active
    administrator, the explicit permission (or, with super_admin_only, being a
    Super Admin), not the administrator's own account, and the current
    password. A refusal is recorded and raised."""
    def refuse(code: str, message: str, status_code: int = 403) -> AdminSecurityError:
        record_denial(db, actor=actor, target_id=target_id, attempted=attempted, code=code, ip=ip)
        return AdminSecurityError(code, message, status_code=status_code)

    if (actor is None or not getattr(actor, "is_active", False) or getattr(actor, "is_deleted", False) is True
            or not is_administrator(actor)):
        raise refuse("FORBIDDEN", "An active administrator is required.")
    if super_admin_only:
        if not super_admin.is_super_admin(actor):
            raise refuse(SUPER_ADMIN_REQUIRED, "Only a Super Admin can do this.")
    elif not permission or not has_permission(actor, permission):
        raise refuse("PERMISSION_REQUIRED", f"The {permission} permission is required.")
    if int(target_id) == int(actor.id):
        raise refuse("SELF_ACTION_FORBIDDEN", "An administrator cannot perform this action on their own account.")
    try:
        # Counted per administrator across every endpoint that asks for the password.
        reauth.verify(db, actor, password, ip=ip, audit=False)      # the refusal below is the audit record
    except reauth.ReauthError as exc:
        raise refuse(exc.code, str(exc), 429 if exc.code == reauth.LOCKED else 403) from None


# ---------------------------------------------------------------------------
# Super Admin (app.services.super_admin)
# ---------------------------------------------------------------------------

def role_is_super_admin_role(role) -> bool:
    """For the protections: any role by that name counts (stricter than
    super_admin.is_super_admin_role, which also wants the system flag)."""
    return role is not None and getattr(role, "name", None) == super_admin.SUPER_ADMIN_ROLE_NAME


def super_admin_role(db: Session):
    """The system role `super_admin` (migration c4d5e6f7a8b9), or None."""
    from app.models.user import Role

    return (db.query(Role).filter(Role.name == super_admin.SUPER_ADMIN_ROLE_NAME, Role.is_system.is_(True))
            .first())


def _on_super_role(user, role_id: Optional[int]) -> bool:
    """Read from the columns, so it is right straight after a locking read."""
    return bool(user is not None and role_id is not None and user.role_id == role_id)


def _counts_as_super_admin(user, role_id: Optional[int]) -> bool:
    return bool(_on_super_role(user, role_id) and user.is_active and user.is_deleted is not True and user.is_admin)


def active_super_admin_ids(db: Session, role_id: Optional[int] = None) -> list:
    """The accounts that are Super Admins now (active, not deleted, administrator)."""
    if role_id is None:
        role = super_admin_role(db)
        if role is None:
            return []
        role_id = role.id
    rows = (db.query(User.id).filter(User.role_id == role_id, User.is_active.is_(True), User.is_deleted.is_(False),
                                     User.is_admin.is_(True)).order_by(User.id).all())
    return [int(r[0]) for r in rows]


def _lock_super_admins(db: Session, role_id: int, *also: int) -> dict:
    """Lock every account on the Super Admin role, and the ones named, in id
    order (two Super Admins acting on each other at the same moment wait for
    one another instead of both succeeding), and re-read them."""
    ids = {int(r[0]) for r in db.query(User.id).filter(User.role_id == role_id).all()} | {int(i) for i in also}
    rows = (db.query(User).filter(User.id.in_(ids)).order_by(User.id).with_for_update().populate_existing().all())
    return {row.id: row for row in rows}


def eligible_for_super_admin(user) -> bool:
    """Only an active administrator whose email address is verified."""
    from app.services.auth_security import must_verify_email

    return bool(user is not None and user.is_active and user.is_deleted is not True and user.is_admin
                and (getattr(user, "email_verified", False) or getattr(user, "is_verified", False))
                and not must_verify_email(user))


def role_grants_super_admin(db: Session, role_id: Optional[int]) -> bool:
    """Would holding this role make (or keep) somebody a Super Admin: the
    Super Admin role itself, or a role inheriting from it at any depth?
    A broken or cyclic chain counts as yes: it is never a safe replacement."""
    from app.models.user import Role

    seen: set = set()
    current = role_id
    while current is not None:
        if current in seen or len(seen) >= 64:
            return True
        seen.add(current)
        row = db.query(Role.name, Role.inherit_from_id).filter(Role.id == current).first()
        if row is None:
            return False
        if row[0] == super_admin.SUPER_ADMIN_ROLE_NAME:
            return True
        current = row[1]
    return False


def replacement_role_problem(db: Session, role_id: Optional[int]) -> Optional[str]:
    """Why this role cannot be what a revoked Super Admin is moved to, or None."""
    from app.models.user import Role

    if role_id is None:
        return "REPLACEMENT_ROLE_REQUIRED"
    if db.query(Role.id).filter(Role.id == role_id).first() is None:
        return "REPLACEMENT_ROLE_NOT_FOUND"
    if role_grants_super_admin(db, role_id):
        return "REPLACEMENT_ROLE_GRANTS_SUPER_ADMIN"
    return None


def demotion_options(db: Session, target) -> dict:
    """What revoking this account's Super Admin role would move it to: its
    previous role when that is still a valid one, and every role that may be
    chosen instead (none of which leads back to Super Admin)."""
    from app.models.user import Role

    previous_id = getattr(target, "role_before_super_admin_id", None)
    previous = db.get(Role, previous_id) if previous_id else None
    roles = [r for r in db.query(Role).order_by(Role.name).all() if not role_grants_super_admin(db, r.id)]
    return {
        "previous_role": ({"id": previous.id, "name": previous.name} if previous is not None else None),
        "previous_role_valid": previous is not None and replacement_role_problem(db, previous.id) is None,
        "roles": [{"id": r.id, "name": r.name, "description": r.description} for r in roles],
    }


REPLACEMENT_MESSAGES = {
    "REPLACEMENT_ROLE_REQUIRED": "This account has no previous role to go back to. Choose the role it should "
                                 "have instead.",
    "REPLACEMENT_ROLE_NOT_FOUND": "The chosen role does not exist.",
    "REPLACEMENT_ROLE_GRANTS_SUPER_ADMIN": "The chosen role is, or inherits from, the Super Admin role.",
}


def set_super_admin(db: Session, actor, *, target_id: int, grant: bool, password: Optional[str],
                    ip: Optional[str] = None, replacement_role_id: Optional[int] = None) -> dict:
    """Grant or revoke the Super Admin role. Commits, or raises AdminSecurityError
    with nothing changed and the refusal audited.

    Needs: an active Super Admin, never on their own account (so nobody
    demotes themselves), their current password, and, for a revocation, at
    least one other active Super Admin left afterwards. A granted account must
    be an active administrator with a verified email address; the role it had
    is kept aside. A revoked account goes back to that previous role, or to
    the role the acting Super Admin chose (`replacement_role_id`); without a
    valid previous role a choice is required. Neither may be, or inherit
    from, the Super Admin role. The revoked account stays an administrator
    and its sessions end."""
    from app.models.user import Role

    attempted = "grant super admin" if grant else "revoke super admin"

    def refuse(code: str, message: str, status_code: int = 409) -> AdminSecurityError:
        record_denial(db, actor=actor, target_id=target_id, attempted=attempted, code=code, ip=ip)
        return AdminSecurityError(code, message, status_code=status_code)

    if grant and replacement_role_id is not None:
        raise refuse("INVALID_REQUEST", "A replacement role is chosen only when revoking.", 422)
    authorize(db, actor, permission=None, password=password, target_id=target_id, attempted=attempted, ip=ip,
              super_admin_only=True)
    role = super_admin_role(db)
    if role is None:
        raise refuse("SUPER_ADMIN_ROLE_MISSING", "The Super Admin role does not exist. Run the migrations first.")

    locked = _lock_super_admins(db, role.id, actor.id, target_id)
    me, target = locked.get(int(actor.id)), locked.get(int(target_id))
    # Re-checked under the lock: the actor may have been revoked meanwhile.
    if not _counts_as_super_admin(me, role.id):
        raise refuse(SUPER_ADMIN_REQUIRED, "Only a Super Admin can do this.", 403)
    if target is None:
        raise refuse("NOT_FOUND", "No such account.", 404)

    # By id, from the row as it is under the lock (the loaded relationship may be older).
    def role_name(role_id):
        return db.query(Role.name).filter(Role.id == role_id).scalar() if role_id else None

    old = {"role_id": target.role_id, "role": role_name(target.role_id)}
    if grant:
        if _on_super_role(target, role.id):
            raise refuse("ALREADY_SUPER_ADMIN", "This account is already a Super Admin.")
        if not eligible_for_super_admin(target):
            raise refuse("TARGET_NOT_ELIGIBLE", "Only an active administrator with a verified email address can "
                                                "be made a Super Admin.")
        target.role_before_super_admin_id = target.role_id      # restored when the role is revoked
        target.role_id = role.id
        new = {"role_id": role.id, "role": role.name}
        action = AUDIT_SUPER_ADMIN_GRANTED
    else:
        if not _on_super_role(target, role.id):
            raise refuse("NOT_SUPER_ADMIN", "This account is not a Super Admin.")
        others = [i for i in active_super_admin_ids(db, role.id) if i != int(target.id)]
        if not others:
            raise refuse("LAST_SUPER_ADMIN", "The last active Super Admin cannot be removed.")
        restored = replacement_role_id is None
        chosen = target.role_before_super_admin_id if restored else int(replacement_role_id)
        # Held (FOR SHARE) until the commit: the role cannot be deleted or changed underneath.
        if chosen is not None:
            db.query(Role.id).filter(Role.id == chosen).with_for_update(read=True).first()
        problem = replacement_role_problem(db, chosen)
        if problem is not None:
            if restored and problem != "REPLACEMENT_ROLE_REQUIRED":
                problem = "REPLACEMENT_ROLE_REQUIRED"               # the previous role is no longer usable
            raise refuse(problem, REPLACEMENT_MESSAGES[problem], 422 if problem != "REPLACEMENT_ROLE_REQUIRED"
                         else 409)
        target.role_id = chosen
        target.role_before_super_admin_id = None
        # The powers end now, not when the token runs out.
        target.security_version = int(target.security_version or 0) + 1
        new = {"role_id": chosen, "role": role_name(chosen), "restored_previous_role": restored}
        action = AUDIT_SUPER_ADMIN_REVOKED
    audit(db, actor_id=actor.id, record_id=target.id, action=action, old=old, new=new, ip=ip)
    db.commit()
    db.refresh(target)
    logger.info("%s: account %s by account %s", action, target.id, actor.id)
    return {"id": target.id, "is_super_admin": super_admin.is_super_admin(target), "role_id": target.role_id,
            "role": role_name(target.role_id)}


def refuse_removing_last_super_admin(db: Session, actor, *, target, attempted: str, ip: Optional[str] = None) -> None:
    """Switching off a Super Admin account must leave another active one."""
    role = super_admin_role(db)
    if role is None or not _counts_as_super_admin(target, role.id):
        return
    _lock_super_admins(db, role.id, actor.id, target.id)
    if not [i for i in active_super_admin_ids(db, role.id) if i != int(target.id)]:
        record_denial(db, actor=actor, target_id=target.id, attempted=attempted, code="LAST_SUPER_ADMIN", ip=ip)
        raise AdminSecurityError("LAST_SUPER_ADMIN", "The last active Super Admin cannot be switched off.",
                                 status_code=409)
