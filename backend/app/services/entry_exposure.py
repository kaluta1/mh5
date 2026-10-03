"""Workflow-level public-exposure gate for contest entries (Child/Teen Safety Phase 5).

Kept dependency-free (models only) so read paths such as the contestant CRUD
can use it without importing the eligibility service. This answers "may this
entry be listed/active at all?"; whether a given viewer may receive its media
is Phase 7.
"""
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session

from app.core.child_safety import EntryExposureStatus
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant


# An administrator's "reject" decision is stored on the entry itself.
REJECTED_VERIFICATION_STATUS = "rejected"


def is_rejected(contestant) -> bool:
    status = getattr(contestant, "verification_status", None)
    return isinstance(status, str) and status.strip().lower() == REJECTED_VERIFICATION_STATUS


def rejected_entry_clause():
    """TRUE for entries an administrator rejected."""
    return func.lower(func.coalesce(Contestant.verification_status, "")) == REJECTED_VERIFICATION_STATUS


def not_publicly_exposable_clause():
    """TRUE for entries that must not be listed: a Phase 5 record that is not
    PUBLIC, or an administrator's rejection. Entries created before Phase 5
    have no record and are otherwise unaffected."""
    return or_(
        exists().where(and_(ContestEntrySafety.contestant_id == Contestant.id,
                            ContestEntrySafety.exposure_status != EntryExposureStatus.PUBLIC.value)),
        rejected_entry_clause(),
    )


def public_entry_clause():
    return ~not_publicly_exposable_clause()


def entry_publicly_visible(db: Session, contestant_id: int) -> bool:
    if db.query(Contestant.id).filter(Contestant.id == contestant_id, rejected_entry_clause()).first() is not None:
        return False
    row = (db.query(ContestEntrySafety.exposure_status)
           .filter(ContestEntrySafety.contestant_id == contestant_id).first())
    return row is None or row[0] == EntryExposureStatus.PUBLIC.value


def owner_entry_status(db: Session, contestant) -> str:
    """What the entry's OWNER is told: PUBLIC, PENDING_REVIEW or REJECTED."""
    if is_rejected(contestant):
        return "REJECTED"
    return "PUBLIC" if entry_publicly_visible(db, contestant.id) else "PENDING_REVIEW"
