"""The one place that sets ``users.sponsor_id`` under the NEW_V2 model.

Priority at registration: valid personal referral -> no sponsor.
The Referral Pool is retired (2026-09-28): an organic signup (no code, or a code that does
not resolve to an eligible member) is never given an invented sponsor.
Assignment is one-time: an existing sponsor is never overwritten (row lock + NULL check).

``REFERRAL_POOL`` stays defined only to read historical rows whose sponsor came from the pool.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User

PERSONAL_REFERRAL = "PERSONAL_REFERRAL"
JOIN_CODE = "JOIN_CODE"
REFERRAL_POOL = "REFERRAL_POOL"  # historical provenance only; never assigned any more
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
    locked.sponsor_source = NONE
    locked.sponsor_assigned_at = now
    db.flush()
    return NONE


def mark_join_code_assignment(db: Session, user: User) -> None:
    """Provenance for the legacy POST /affiliates/join/{code} path (which already refuses reassignment)."""
    user.sponsor_source = JOIN_CODE
    user.sponsor_assigned_at = datetime.utcnow()
    db.flush()
