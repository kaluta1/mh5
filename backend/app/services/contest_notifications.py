"""Contest entry status emails (EMAIL-3).

Email follows the application's state; it is never the source of truth.

Every function here is called AFTER the business transaction has committed and
decides what to send by reading the entry's COMMITTED state again
(contest_entry_safety.exposure_status, contestants.verification_status). So:

* a transition that rolled back sends nothing (there is no committed state to
  read, and the call is never reached);
* a caller that is wrong about the state sends nothing (the state decides);
* a repeat (scheduler rerun, admin retry, double request, lazy re-evaluation)
  sends nothing new: one logical transition has one deterministic
  idempotency key, enforced by EMAIL-1's unique index.

Nothing here changes an entry, a vote, a ranking, a stage membership or a
moderation decision. Every function swallows its own errors: the business
action has already succeeded and must stay that way.

Recipient: the member who submitted the entry (the nominator of a nomination,
the entrant of a participation), taken from the entry's own records. A
nominee who is not that member is never emailed here, no address typed by a
client is ever used, and an inactive or deleted account receives nothing.

Deliberately NOT emailed: child-safety escalation, a published entry going
back to "held" (guardian consent withdrawn, policy change), nominee claim /
decline, progression, results (see the status list in email_events.py). An
entry that becomes public inside a progression pass (the lazy re-evaluation in
participation_safety) is not announced either: that code is left untouched.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant
from app.models.user import User
from app.services.email import email_service
from app.services.email_events import EmailEvent

logger = logging.getLogger(__name__)

PUBLIC, HELD, BLOCKED = "PUBLIC", "HELD", "BLOCKED"
NOMINATION = "NOMINATION"
REJECTED_STATUS = "rejected"
CREATIVE_UNAVAILABLE_STATUS = "creative_unavailable"


def is_nomination(contestant: Optional[Contestant], row: Optional[ContestEntrySafety]) -> bool:
    """Nomination and participation are different lifecycles; never guessed
    from the route. The safety record's kind wins; a pre-Phase-5 entry without
    one falls back to the contestant's own entry_type."""
    if row is not None:
        return row.entry_kind == NOMINATION
    return (getattr(contestant, "entry_type", "") or "").strip().lower() == "nomination"


def _load(db: Session, contestant_id: int) -> Tuple[Optional[Contestant], Optional[ContestEntrySafety]]:
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    row = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant_id).first()
    return contestant, row


def _recipient(db: Session, contestant: Contestant, row: Optional[ContestEntrySafety]) -> Optional[User]:
    user_id = (row.submitted_by_user_id if row is not None else None) or contestant.user_id
    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user is None or not user.is_active or getattr(user, "is_deleted", False) or not (user.email or "").strip():
        return None
    return user


def _enqueue(db: Session, contestant: Contestant, row: Optional[ContestEntrySafety], *, nomination_event: EmailEvent,
             participation_event: EmailEvent, key: str) -> None:
    user = _recipient(db, contestant, row)
    if user is None:
        return
    event = nomination_event if is_nomination(contestant, row) else participation_event
    email_service.enqueue(
        db,
        event=event,
        recipient=user.email,
        user_id=user.id,
        lang=getattr(user, "preferred_language", None),
        # Only the entry id travels with the email: title and contest name are
        # read again when it is sent.
        context={"contestant_id": int(contestant.id)},
        idempotency_key=key,
    )


def _published(db: Session, contestant: Contestant, row: ContestEntrySafety) -> None:
    _enqueue(db, contestant, row, nomination_event=EmailEvent.CONTEST_NOMINATION_PUBLISHED,
             participation_event=EmailEvent.CONTEST_PARTICIPATION_PUBLISHED,
             key=f"contest.entry.published:{contestant.id}")


def entry_created(db: Session, contestant_id: int) -> None:
    """After a new entry (and its safety record) has been committed.

    PUBLIC  -> "published" (a valid nomination is public as soon as it is
               submitted: there is no "waiting for approval" email for it).
    HELD    -> a participation gets "received, being checked"; a nomination
               held at submission gets nothing (its status is in the member's
               entries; no approval step is announced that may not exist).
    Anything else (blocked / escalated at submission) -> nothing.
    """
    def work():
        contestant, row = _load(db, contestant_id)
        if contestant is None or row is None or getattr(contestant, "is_deleted", False):
            return
        if row.exposure_status == PUBLIC:
            _published(db, contestant, row)
        elif row.exposure_status == HELD and not is_nomination(contestant, row):
            _enqueue(db, contestant, row, nomination_event=EmailEvent.CONTEST_PARTICIPATION_PENDING_REVIEW,
                     participation_event=EmailEvent.CONTEST_PARTICIPATION_PENDING_REVIEW,
                     key=f"contest.entry.pending_review:{contestant.id}")
    _guard(db, "created", contestant_id, work)


def entries_published(db: Session, contestant_ids: Iterable[int]) -> None:
    """After a re-evaluation that moved entries from private to PUBLIC has been
    committed. Each entry is announced as published at most once in its life
    (a later suspension and return does not announce it again)."""
    for contestant_id in list(contestant_ids):
        def work(cid=contestant_id):
            contestant, row = _load(db, cid)
            if contestant is None or row is None or getattr(contestant, "is_deleted", False):
                return
            if row.exposure_status == PUBLIC:
                _published(db, contestant, row)
        _guard(db, "published", contestant_id, work)


def entry_removed(db: Session, contestant_id: int) -> None:
    """After an administrator blocked or rejected an entry (committed)."""
    def work():
        contestant, row = _load(db, contestant_id)
        if contestant is None:
            return
        blocked = row is not None and row.exposure_status == BLOCKED
        rejected = (contestant.verification_status or "") == REJECTED_STATUS
        if not (blocked or rejected):
            return
        _enqueue(db, contestant, row, nomination_event=EmailEvent.CONTEST_NOMINATION_REMOVED,
                 participation_event=EmailEvent.CONTEST_PARTICIPATION_REJECTED,
                 key=f"contest.entry.removed:{contestant.id}")
    _guard(db, "removed", contestant_id, work)


def entry_update_requested(db: Session, contestant_id: int) -> None:
    """After a moderator's REQUEST_UPDATE has been committed. One email per
    request: the key carries the moment of that moderation decision."""
    def work():
        from app.models.content_moderation import ContentModeration

        contestant, row = _load(db, contestant_id)
        moderation = db.query(ContentModeration).filter(ContentModeration.contestant_id == contestant_id).first()
        if contestant is None or moderation is None or not moderation.update_required \
                or getattr(contestant, "is_deleted", False):
            return
        if row is not None and row.exposure_status not in (PUBLIC, HELD):
            return                                  # blocked / escalated: nothing the member can update
        stamp = int(moderation.decided_at.timestamp()) if moderation.decided_at else 0
        _enqueue(db, contestant, row, nomination_event=EmailEvent.CONTEST_NOMINATION_ACTION_REQUIRED,
                 participation_event=EmailEvent.CONTEST_PARTICIPATION_ACTION_REQUIRED,
                 key=f"contest.entry.update_requested:{contestant.id}:{stamp}")
    _guard(db, "update_requested", contestant_id, work)


def creative_unavailable(db: Session, contestant_ids: Iterable[int]) -> None:
    """After the dead-link checker removed entries (committed). One email per
    entry, whatever the number of later scheduler passes."""
    for contestant_id in list(contestant_ids):
        def work(cid=contestant_id):
            contestant, row = _load(db, cid)
            if contestant is None or getattr(contestant, "is_deleted", False):
                return
            if (contestant.verification_status or "") != CREATIVE_UNAVAILABLE_STATUS:
                return
            _enqueue(db, contestant, row, nomination_event=EmailEvent.CONTEST_CREATIVE_UNAVAILABLE,
                     participation_event=EmailEvent.CONTEST_CREATIVE_UNAVAILABLE,
                     key=f"contest.entry.creative_unavailable:{contestant.id}")
        _guard(db, "creative_unavailable", contestant_id, work)


def _guard(db: Session, what: str, contestant_id, work) -> None:
    try:
        work()
    except Exception as exc:  # noqa: BLE001 - the business action is committed; email never undoes it
        logger.error("Contest email (%s) for entry %s could not be queued: %s", what, contestant_id, type(exc).__name__)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
