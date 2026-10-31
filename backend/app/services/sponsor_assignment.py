"""The one place that sets ``users.sponsor_id`` under the NEW_V2 model.

Priority at registration: valid personal referral -> no sponsor (NONE). An organic signup (no
code, or a code that does not resolve to an eligible member) gets no sponsor here; it is queued
for the Multi-Unit Referral Pool at once (owner rule 2026-10-31: no e-mail confirmation or KYC
needed), which assigns one drawn per eligible ACTIVE unit (referral_pool_allocation, sponsor_source
REFERRAL_POOL). A valid personal referral is the link of any active member, KYC or not (owner
rule 2026-10-31). DSM-imported members keep the sponsor the import resolved. Assignment is one-time: an existing sponsor is never overwritten (row lock
+ NULL check, here and in the pool).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User

PERSONAL_REFERRAL = "PERSONAL_REFERRAL"
JOIN_CODE = "JOIN_CODE"
REFERRAL_POOL = "REFERRAL_POOL"  # set by referral_pool_allocation, never here
NONE = "NONE"


def inviter_eligible(db: Session, sponsor: Optional[User]) -> bool:
    """May this member be a personal inviter now? Owner rule 2026-10-31 (replaces 2026-10-23): any
    active, not deleted member, KYC or not, unless held by an open or confirmed duplicate-identity
    review. Sponsor attribution only: KYC still governs the sponsor's commissions, revenue share and
    cash-out. The same rule for a code at registration and later."""
    if sponsor is None or sponsor.is_active is False or sponsor.is_deleted is True:
        return False
    from app.services.referral_pool_risk import is_blocked

    return not is_blocked(db, sponsor.id)


def _eligible_personal_sponsor(db: Session, sponsor: Optional[User], user_id: int) -> bool:
    return sponsor is not None and int(sponsor.id) != int(user_id) and inviter_eligible(db, sponsor)


def assign_at_registration(db: Session, user: User, personal_sponsor: Optional[User]) -> str:
    """Run inside the registration transaction, before commit. Returns the sponsor_source used.
    A code whose owner is not a valid inviter creates no sponsor relationship."""
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    if locked.sponsor_id is not None:
        return locked.sponsor_source or PERSONAL_REFERRAL
    now = datetime.utcnow()
    if _eligible_personal_sponsor(db, personal_sponsor, locked.id):
        locked.sponsor_id = personal_sponsor.id
        locked.sponsor_source = PERSONAL_REFERRAL
        locked.sponsor_assigned_at = now
        db.flush()
        return PERSONAL_REFERRAL
    locked.sponsor_source = NONE
    locked.sponsor_assigned_at = now
    db.flush()
    from app.services.referral_pool_integration import record_signup

    record_signup(db, locked)                     # the pool worker queues them after the commit
    return NONE


def mark_join_code_assignment(db: Session, user: User) -> None:
    """Provenance for the legacy POST /affiliates/join/{code} path (which already refuses reassignment)."""
    user.sponsor_source = JOIN_CODE
    user.sponsor_assigned_at = datetime.utcnow()
    db.flush()
