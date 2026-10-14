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
from app.services import payment_config, reauth

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
    """Does this role hold a protected permission, itself or by inheritance?"""
    seen = set()
    while role is not None and getattr(role, "id", None) not in seen:
        seen.add(getattr(role, "id", None))
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
        if getattr(role, "name", None) == ADMIN_ROLE_NAME:
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


def authorize(db: Session, actor, *, permission: str, password: Optional[str], target_id: int, attempted: str,
              ip: Optional[str] = None) -> None:
    """The four conditions of a privileged action, in this order: an active
    administrator, the explicit permission, not the administrator's own
    account, and the current password. A refusal is recorded and raised."""
    def refuse(code: str, message: str, status_code: int = 403) -> AdminSecurityError:
        record_denial(db, actor=actor, target_id=target_id, attempted=attempted, code=code, ip=ip)
        return AdminSecurityError(code, message, status_code=status_code)

    if (actor is None or not getattr(actor, "is_active", False) or getattr(actor, "is_deleted", False) is True
            or not is_administrator(actor)):
        raise refuse("FORBIDDEN", "An active administrator is required.")
    if not has_permission(actor, permission):
        raise refuse("PERMISSION_REQUIRED", f"The {permission} permission is required.")
    if int(target_id) == int(actor.id):
        raise refuse("SELF_ACTION_FORBIDDEN", "An administrator cannot perform this action on their own account.")
    try:
        # Counted per administrator across every endpoint that asks for the password.
        reauth.verify(db, actor, password, ip=ip, audit=False)      # the refusal below is the audit record
    except reauth.ReauthError as exc:
        raise refuse(exc.code, str(exc), 429 if exc.code == reauth.LOCKED else 403) from None
