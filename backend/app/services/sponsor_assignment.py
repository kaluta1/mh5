"""The one place that sets ``users.sponsor_id`` under the NEW_V2 model.

Priority at registration: valid personal referral -> Referral Pool member -> no sponsor.
Assignment is one-time: an existing sponsor is never overwritten (row lock + NULL check),
and a user can receive at most one pool assignment (unique referred_user_id).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import referral_pool_service as pool

PERSONAL_REFERRAL = "PERSONAL_REFERRAL"
JOIN_CODE = "JOIN_CODE"
REFERRAL_POOL = "REFERRAL_POOL"
NONE = "NONE"


def _eligible_personal_sponsor(sponsor: Optional[User], user_id: int) -> bool:
    return (
        sponsor is not None
        and int(sponsor.id) != int(user_id)
        and sponsor.is_active is not False
        and sponsor.is_deleted is not True
    )


def assign_at_registration(db: Session, user: User, personal_sponsor: Optional[User]) -> str:
    """Run inside the registration transaction, before commit. Returns the sponsor_source used."""
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    if locked.sponsor_id is not None:
        return locked.sponsor_source or PERSONAL_REFERRAL
    now = datetime.utcnow()
    if _eligible_personal_sponsor(personal_sponsor, locked.id):
        locked.sponsor_id = personal_sponsor.id
        locked.sponsor_source = PERSONAL_REFERRAL
        locked.sponsor_assigned_at = now
        db.flush()
        return PERSONAL_REFERRAL
    pick = pool.pick_pool_member(db, exclude_user_id=locked.id)
    if pick is not None:
        locked.sponsor_id = pick.membership.user_id
        locked.sponsor_source = REFERRAL_POOL
        locked.sponsor_assigned_at = now
        pool.record_assignment(db, referred_user_id=locked.id, pick=pick)
        db.flush()
        return REFERRAL_POOL
    locked.sponsor_source = NONE
    locked.sponsor_assigned_at = now
    db.flush()
    return NONE


def mark_join_code_assignment(db: Session, user: User) -> None:
    """Provenance for the legacy POST /affiliates/join/{code} path (which already refuses reassignment)."""
    user.sponsor_source = JOIN_CODE
    user.sponsor_assigned_at = datetime.utcnow()
    db.flush()
