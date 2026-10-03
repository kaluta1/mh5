"""Workflow-level public-exposure gate for contest entries (Child/Teen Safety Phase 5).

Kept dependency-free (models only) so read paths such as the contestant CRUD
can use it without importing the eligibility service. This answers "may this
entry be listed/active at all?"; whether a given viewer may receive its media
is Phase 7.
"""
from typing import Optional

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session

from app.core.child_safety import ContentRating, ContestEntryKind, EntryExposureStatus, ModerationState
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant


# An administrator's "reject" decision is stored on the entry itself.
REJECTED_VERIFICATION_STATUS = "rejected"
# Set automatically when the entry's external creative (e.g. a YouTube video) is
# confirmed to no longer exist. Logical removal only: the row, its votes and its
# history are kept, and an administrator can restore it by approving the entry.
CREATIVE_UNAVAILABLE_STATUS = "creative_unavailable"
REMOVED_VERIFICATION_STATUSES = (REJECTED_VERIFICATION_STATUS, CREATIVE_UNAVAILABLE_STATUS)


def _status(contestant) -> str:
    status = getattr(contestant, "verification_status", None)
    return status.strip().lower() if isinstance(status, str) else ""


def is_rejected(contestant) -> bool:
    return _status(contestant) == REJECTED_VERIFICATION_STATUS


def is_creative_unavailable(contestant) -> bool:
    return _status(contestant) == CREATIVE_UNAVAILABLE_STATUS


def is_removed(contestant) -> bool:
    """Rejected by an administrator, or removed because its creative is gone."""
    return _status(contestant) in REMOVED_VERIFICATION_STATUSES


def rejected_entry_clause():
    """TRUE for entries an administrator rejected."""
    return func.lower(func.coalesce(Contestant.verification_status, "")) == REJECTED_VERIFICATION_STATUS


def removed_entry_clause():
    """TRUE for entries taken out of the contest (rejected, or creative unavailable)."""
    return func.lower(func.coalesce(Contestant.verification_status, "")).in_(REMOVED_VERIFICATION_STATUSES)


def not_publicly_exposable_clause():
    """TRUE for entries that must not be listed: a Phase 5 record that is not
    PUBLIC, an administrator's rejection, or a creative that no longer exists.
    Entries created before Phase 5 have no record and are otherwise unaffected."""
    return or_(
        exists().where(and_(ContestEntrySafety.contestant_id == Contestant.id,
                            ContestEntrySafety.exposure_status != EntryExposureStatus.PUBLIC.value)),
        removed_entry_clause(),
    )


def public_entry_clause():
    return ~not_publicly_exposable_clause()


def entry_publicly_visible(db: Session, contestant_id: int) -> bool:
    if db.query(Contestant.id).filter(Contestant.id == contestant_id, removed_entry_clause()).first() is not None:
        return False
    row = (db.query(ContestEntrySafety.exposure_status)
           .filter(ContestEntrySafety.contestant_id == contestant_id).first())
    return row is None or row[0] == EntryExposureStatus.PUBLIC.value


def owner_entry_status(db: Session, contestant) -> str:
    """What the entry's OWNER is told: PUBLIC, PENDING_REVIEW, REJECTED or
    CREATIVE_UNAVAILABLE."""
    if is_rejected(contestant):
        return "REJECTED"
    if is_creative_unavailable(contestant):
        return "CREATIVE_UNAVAILABLE"
    return "PUBLIC" if entry_publicly_visible(db, contestant.id) else "PENDING_REVIEW"


# ---------------------------------------------------------------------------
# Nomination publication policy: published while content awaits its first review
# ---------------------------------------------------------------------------
#
# Management rule (2026-10-04): a NOMINATION is published as soon as it is
# submitted. Its content may still be waiting for its first human review (an
# external video cannot be classified automatically). Publication and moderation
# are separate facts: the moderation record stays REVIEW_REQUIRED - it is never
# written as approved - and the entry is public "provisionally".
#
# The eligibility service remains the only place that decides exposure. These
# helpers only let the publication rule recognise that decision: they apply to a
# NOMINATION whose exposure the service set to PUBLIC, and only while no
# moderator has acted. Any moderator decision (hold, request update, prohibit,
# escalate) ends the provisional state at once. Personal participation entries
# are never provisional.

def provisional_rating(moderation) -> str:
    """Rating used to decide who may receive a provisionally published entry:
    the classifier's proposal (never a human rating), GENERAL when it has none."""
    return getattr(moderation, "proposed_rating", None) or ContentRating.GENERAL.value


def awaiting_first_review(moderation) -> bool:
    """A moderation record nobody has decided yet (no hold, update request,
    prohibition or escalation)."""
    return bool(
        moderation is not None
        and moderation.state == ModerationState.REVIEW_REQUIRED.value
        and getattr(moderation, "decided_by_user_id", None) is None
        and not getattr(moderation, "update_required", False)
        and not getattr(moderation, "child_safety_escalated", False)
        and getattr(moderation, "child_safety_resolution", None) != "CONFIRMED"
    )


def provisionally_published(safety, moderation) -> bool:
    """True for a NOMINATION the eligibility service made PUBLIC while its
    content still awaits its first review."""
    return bool(
        safety is not None
        and safety.entry_kind == ContestEntryKind.NOMINATION.value
        and safety.exposure_status == EntryExposureStatus.PUBLIC.value
        and awaiting_first_review(moderation)
    )


def provisional_nomination_moderation_clause(allowed_ratings: Optional[list] = None):
    """SQL twin of provisionally_published() for a ContentModeration row joined to
    the current Contestant. With allowed_ratings, the provisional rating must be
    one the viewer may receive."""
    conditions = [
        ContentModeration.state == ModerationState.REVIEW_REQUIRED.value,
        ContentModeration.decided_by_user_id.is_(None),
        func.coalesce(ContentModeration.update_required, False).is_(False),
        func.coalesce(ContentModeration.child_safety_escalated, False).is_(False),
        func.coalesce(ContentModeration.child_safety_resolution, "") != "CONFIRMED",
        exists().where(and_(
            ContestEntrySafety.contestant_id == ContentModeration.contestant_id,
            ContestEntrySafety.entry_kind == ContestEntryKind.NOMINATION.value,
            ContestEntrySafety.exposure_status == EntryExposureStatus.PUBLIC.value,
        )),
    ]
    if allowed_ratings is not None:
        conditions.append(
            func.coalesce(ContentModeration.proposed_rating, ContentRating.GENERAL.value).in_(allowed_ratings)
        )
    return and_(*conditions)
