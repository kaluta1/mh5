"""Workflow-level public-exposure gate for contest entries (Child/Teen Safety Phase 5).

Kept dependency-free (models only) so read paths such as the contestant CRUD
can use it without importing the eligibility service. This answers "may this
entry be listed/active at all?"; whether a given viewer may receive its media
is Phase 7.
"""
from sqlalchemy import and_, exists
from sqlalchemy.orm import Session

from app.core.child_safety import EntryExposureStatus
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant


def not_publicly_exposable_clause():
    """TRUE for entries with a Phase 5 record that is not PUBLIC. Entries created
    before Phase 5 have no record and are unaffected."""
    return exists().where(and_(ContestEntrySafety.contestant_id == Contestant.id,
                               ContestEntrySafety.exposure_status != EntryExposureStatus.PUBLIC.value))


def public_entry_clause():
    return ~not_publicly_exposable_clause()


def entry_publicly_visible(db: Session, contestant_id: int) -> bool:
    row = (db.query(ContestEntrySafety.exposure_status)
           .filter(ContestEntrySafety.contestant_id == contestant_id).first())
    return row is None or row[0] == EntryExposureStatus.PUBLIC.value
