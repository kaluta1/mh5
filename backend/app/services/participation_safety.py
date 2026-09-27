"""Participation safety for voting, TopHigh5 ranking and progression
(Child/Teen Safety Phase 8).

ONE backend place answers "may this contest entry take part right now?" for
the three lifecycle operations. It adds no new safety rules: it reads the
authoritative Phase 5 participation record (contest_entry_safety: HOLD,
nomination claim, guardian consent, age/jurisdiction policy - all recomputed by
the existing re-evaluation) and the Phase 6 content record (content_moderation:
approval, rating, PROHIBITED, child-safety escalation), plus the contestant's
own business state (deleted / inactive).

Four distinct concepts (never merged):
    VISIBLE_TO_STAFF           Phase 7 entry_access MODERATION / CHILD_SAFETY_REVIEW.
                               Review only: it never makes an entry eligible.
    ELIGIBLE_FOR_PUBLIC_VOTING participation_decision() AND the voter may receive
                               the entry publicly (Phase 7 PUBLIC mode), checked
                               again inside the vote transaction on locked rows.
    ELIGIBLE_FOR_RANKING       participation_decision() (viewer independent). Which
                               profile/media fields a viewer receives is Phase 7.
    ELIGIBLE_FOR_PROGRESSION   participation_decision() after a fresh Phase 5
                               re-evaluation (current age/policy/consent).

Ranking mathematics are never touched here: points, totals, tie-breaks and the
TopHigh5 cohort/month selection are computed by the unchanged services and only
the final eligible set is filtered. A contestant who competed publicly and was
later held keeps their place in the ranking pool (competed_hold_clause), so the
next contestant is never moved up into a held slot and no substitute winner is
created. Historical votes and ranking rows are never modified.

Historical entries (no Phase 5 / Phase 6 record) keep their historical
treatment: they are eligible unless deleted or inactive (nothing is invented
for them). UNKNOWN age is never treated as adult (Phase 2-7 rules, unchanged).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.core.child_safety import AgeSafetyEventType, ContentRating, EntryExposureStatus
from app.models.age_safety import AgeSafetyEvent
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant
from app.models.progression_safety import ProgressionSafetyHold

logger = logging.getLogger(__name__)


class Reason:
    """Machine-readable participation reason codes (never shown to the public)."""

    NOT_FOUND = "ENTRY_NOT_FOUND"
    INACTIVE = "ENTRY_INACTIVE"
    HELD = "ENTRY_HELD"
    BLOCKED = "ENTRY_BLOCKED"
    CHILD_SAFETY = "CHILD_SAFETY_BLOCK"
    CONTENT_NOT_APPROVED = "CONTENT_NOT_APPROVED"
    CONTENT_PROHIBITED = "CONTENT_PROHIBITED"
    VIEWER_RESTRICTED = "VIEWER_RESTRICTED"
    EVALUATION_FAILED = "EVALUATION_FAILED"


class Eligibility:
    VISIBLE_TO_STAFF = "VISIBLE_TO_STAFF"
    ELIGIBLE_FOR_PUBLIC_VOTING = "ELIGIBLE_FOR_PUBLIC_VOTING"
    ELIGIBLE_FOR_RANKING = "ELIGIBLE_FOR_RANKING"
    ELIGIBLE_FOR_PROGRESSION = "ELIGIBLE_FOR_PROGRESSION"


@dataclass(frozen=True)
class ParticipationDecision:
    eligible: bool
    reasons: Tuple[str, ...] = ()


ELIGIBLE = ParticipationDecision(True)


class VoteUnavailable(Exception):
    """The entry cannot receive a vote now. Public responses stay generic;
    `reasons` is for the audit trail only."""

    def __init__(self, reasons: Sequence[str]):
        super().__init__("Submission not found")
        self.reasons = tuple(reasons)


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------

def decide(contestant: Optional[Contestant], safety: Optional[ContestEntrySafety],
           moderation: Optional[ContentModeration]) -> ParticipationDecision:
    """Pure decision from the entry's authoritative records (no I/O)."""
    if contestant is None or getattr(contestant, "is_deleted", False):
        return ParticipationDecision(False, (Reason.NOT_FOUND,))
    reasons: List[str] = []
    exposure = safety.exposure_status if safety is not None else None
    if (exposure == EntryExposureStatus.CHILD_SAFETY_ESCALATED.value
            or (moderation is not None and (moderation.child_safety_escalated
                                            or moderation.child_safety_resolution == "CONFIRMED"))):
        reasons.append(Reason.CHILD_SAFETY)
    if exposure == EntryExposureStatus.BLOCKED.value:
        reasons.append(Reason.BLOCKED)
    elif exposure == EntryExposureStatus.HELD.value:
        reasons.append(Reason.HELD)
        # Phase 5 requirement codes (e.g. GUARDIAN_CONSENT_REQUIRED, NOMINEE_UNCLAIMED):
        # codes only, never values.
        reasons.extend(str(c) for c in (safety.reason_codes or ()) if isinstance(c, str))
    elif exposure is not None and exposure != EntryExposureStatus.PUBLIC.value:
        reasons.append(Reason.HELD)  # unknown state: fail closed
    if moderation is not None:
        if moderation.rating == ContentRating.PROHIBITED.value or moderation.state == "PROHIBITED":
            reasons.append(Reason.CONTENT_PROHIBITED)
        elif moderation.state != "APPROVED" or not moderation.rating:
            reasons.append(Reason.CONTENT_NOT_APPROVED)
    if not reasons and not getattr(contestant, "is_active", True):
        reasons.append(Reason.INACTIVE)   # existing business deactivation
    return ParticipationDecision(not reasons, tuple(dict.fromkeys(reasons)))


class Records:
    """Batch-loaded Phase 5/6 records for many entries (no N+1)."""

    def __init__(self, db: Session, contestant_ids: Iterable[int]):
        ids = sorted({int(i) for i in contestant_ids if i is not None}) or [-1]
        self.safety = {r.contestant_id: r for r in
                       db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id.in_(ids)).all()}
        self.moderation = {r.contestant_id: r for r in
                           db.query(ContentModeration).filter(ContentModeration.contestant_id.in_(ids)).all()}

    def decide(self, contestant: Optional[Contestant]) -> ParticipationDecision:
        if contestant is None:
            return ParticipationDecision(False, (Reason.NOT_FOUND,))
        return decide(contestant, self.safety.get(contestant.id), self.moderation.get(contestant.id))


def participation_decision(db: Session, contestant: Optional[Contestant]) -> ParticipationDecision:
    if contestant is None:
        return ParticipationDecision(False, (Reason.NOT_FOUND,))
    return Records(db, [contestant.id]).decide(contestant)


def can_appear_in_ranking(db: Session, contestant: Optional[Contestant]) -> ParticipationDecision:
    return participation_decision(db, contestant)


def rankable_ids(db: Session, contestant_ids: Iterable[int]) -> set:
    """Ids (of the given ones) currently ELIGIBLE_FOR_RANKING."""
    ids = sorted({int(i) for i in contestant_ids if i is not None})
    if not ids:
        return set()
    rows = db.query(Contestant).filter(Contestant.id.in_(ids)).all()
    records = Records(db, ids)
    return {c.id for c in rows if records.decide(c).eligible}


# ---------------------------------------------------------------------------
# Ranking pool (SQL)
# ---------------------------------------------------------------------------

def competed_hold_clause():
    """TRUE for an entry that was publicly active at some point (activated) and
    is now held/blocked/escalated by safety. Phase 5 mirrors such a hold into
    Contestant.is_active = False; for RANKING that must not look like the entry
    never competed, otherwise the next contestant would silently move up into
    its slot (a substitute winner). The entry itself stays ineligible."""
    return exists().where(and_(ContestEntrySafety.contestant_id == Contestant.id,
                               ContestEntrySafety.activated_at.isnot(None),
                               ContestEntrySafety.exposure_status != EntryExposureStatus.PUBLIC.value))


def ranking_pool_clause():
    """Replaces a plain `Contestant.is_active == True` in the ranking/promotion
    POOL queries only. Output is always filtered by the participation decision."""
    return or_(Contestant.is_active == True, competed_hold_clause())  # noqa: E712


# ---------------------------------------------------------------------------
# Voting
# ---------------------------------------------------------------------------

def _vote_decision(db: Session, contestant: Optional[Contestant], voter, safety, moderation) -> ParticipationDecision:
    from app.services import viewer_access as va

    decision = decide(contestant, safety, moderation)
    if not decision.eligible:
        return decision
    governance = va.Governance.of({contestant.id: safety} if safety is not None else {},
                                  {contestant.id: moderation} if moderation is not None else {})
    access = va.entry_access(db, va.viewer_for(db, voter), contestant, governance)
    if not access.allowed or access.mode != va.Mode.PUBLIC:
        return ParticipationDecision(False, (Reason.VIEWER_RESTRICTED,))
    return ELIGIBLE


def can_receive_vote(db: Session, contestant: Optional[Contestant], voter) -> ParticipationDecision:
    """ELIGIBLE_FOR_PUBLIC_VOTING (read-only pre-check; the authoritative check
    is lock_and_check_vote inside the vote transaction)."""
    if contestant is None:
        return ParticipationDecision(False, (Reason.NOT_FOUND,))
    records = Records(db, [contestant.id])
    return _vote_decision(db, contestant, voter, records.safety.get(contestant.id),
                          records.moderation.get(contestant.id))


def lock_and_check_vote(db: Session, *, contestant_id: int, voter_id: int) -> None:
    """Authoritative vote gate, run in the vote transaction right before the
    vote row is written. The entry's contestant / participation / moderation
    rows are read FOR SHARE (PostgreSQL) with fresh values, so a concurrent
    safety change either commits first (and is seen here) or waits until this
    vote is committed - never "checked, then changed, then written anyway".
    Raises VoteUnavailable."""
    from app.models.user import User

    contestant = (db.query(Contestant).filter(Contestant.id == contestant_id)
                  .populate_existing().with_for_update(read=True).one_or_none())
    safety = (db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant_id)
              .populate_existing().with_for_update(read=True).one_or_none())
    moderation = (db.query(ContentModeration).filter(ContentModeration.contestant_id == contestant_id)
                  .populate_existing().with_for_update(read=True).one_or_none())
    voter = db.query(User).filter(User.id == voter_id).one_or_none()
    if voter is None or not voter.is_active:
        raise VoteUnavailable((Reason.VIEWER_RESTRICTED,))
    decision = _vote_decision(db, contestant, voter, safety, moderation)
    if not decision.eligible:
        raise VoteUnavailable(decision.reasons)


def record_vote_blocked(db: Session, *, contestant_id: int, voter_id: Optional[int], reasons: Sequence[str]) -> None:
    """Audit a refused vote (codes only). Own small transaction; never raises."""
    try:
        now = datetime.utcnow()
        db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=AgeSafetyEventType.VOTE_BLOCKED_SAFETY.value,
                              user_id=voter_id, decision="BLOCKED", risk_flag=Reason.CHILD_SAFETY in reasons,
                              details={"contestant_id": int(contestant_id), "reason_codes": list(reasons)}))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - auditing must not turn a refusal into a 500
        db.rollback()
        logger.warning("Phase 8 vote audit failed: %s", type(exc).__name__)


def reorder_guard(db: Session, current_votes: Sequence, requested_ids: Sequence[int]) -> None:
    """A voter may reorder their own MyHigh5 list, but points must never move
    toward an entry that is not currently eligible: such a vote keeps its
    position (and therefore its points) unchanged."""
    from app.services.voting_ranking import VotingValidationError

    ids = [int(v.contestant_id) for v in current_votes]
    eligible = rankable_ids(db, ids)
    current_position = {int(v.contestant_id): v.position for v in current_votes}
    for position, contestant_id in enumerate(requested_ids, start=1):
        if contestant_id not in eligible and current_position.get(contestant_id) != position:
            raise VotingValidationError(
                "One of these entries is not currently available, so its position can't be changed.")


# ---------------------------------------------------------------------------
# Progression
# ---------------------------------------------------------------------------

def _fresh_reevaluation(db: Session, contestant_id: int, *, today: date) -> None:
    """Run the EXISTING Phase 5 re-evaluation for an open entry so the
    progression decision uses current age / policy / consent / review state
    (never a cached "minor forever" or "adult once" conclusion)."""
    from app.services import contest_eligibility as ce

    row = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant_id).first()
    if row is None or row.exposure_status not in (EntryExposureStatus.PUBLIC.value, EntryExposureStatus.HELD.value):
        return  # historical entry, or BLOCKED / escalated (administrator-only states)
    ce.reevaluate_entry(db, row, actor_id=None, trigger="PROGRESSION_GATE", today=today, commit=False)


def can_progress(db: Session, contestant: Optional[Contestant], *, today: Optional[date] = None,
                 reevaluate: bool = True) -> ParticipationDecision:
    """ELIGIBLE_FOR_PROGRESSION. Fails closed on any evaluation error."""
    if contestant is None:
        return ParticipationDecision(False, (Reason.NOT_FOUND,))
    from app.services.age_policy_engine import utc_today

    if reevaluate:
        try:
            with db.begin_nested():
                _fresh_reevaluation(db, contestant.id, today=today or utc_today())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Phase 8 progression re-evaluation failed for %s: %s", contestant.id, type(exc).__name__)
            return ParticipationDecision(False, (Reason.EVALUATION_FAILED,))
    return participation_decision(db, contestant)


def _event(db: Session, event: AgeSafetyEventType, hold: ProgressionSafetyHold, *, actor_id: Optional[int],
           now: datetime) -> None:
    db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=event.value, user_id=actor_id,
                          decision=hold.status, risk_flag=Reason.CHILD_SAFETY in (hold.reason_codes or ()),
                          details={"contestant_id": hold.contestant_id, "hold_id": hold.id,
                                   "from_season_id": hold.from_season_id, "to_season_id": hold.to_season_id,
                                   "to_level": hold.to_level, "reason_codes": list(hold.reason_codes or ())}))


def _level_value(level) -> Optional[str]:
    if level is None:
        return None
    return str(getattr(level, "value", level)).lower()


def record_progression_hold(db: Session, contestant: Contestant, *, to_season, from_season=None,
                            contest_id: Optional[int], reasons: Sequence[str],
                            now: Optional[datetime] = None) -> ProgressionSafetyHold:
    """Idempotent upsert of the hold for (contestant, destination season).
    Nothing else is changed: no deletion, no demotion, no is_qualified=False."""
    now = now or datetime.utcnow()
    hold = (db.query(ProgressionSafetyHold)
            .filter(ProgressionSafetyHold.contestant_id == contestant.id,
                    ProgressionSafetyHold.to_season_id == to_season.id).first())
    if hold is None:
        for pending in db.new:   # same-session pending row (autoflush is off)
            if (isinstance(pending, ProgressionSafetyHold) and pending.contestant_id == contestant.id
                    and pending.to_season_id == to_season.id):
                hold = pending
    codes = list(dict.fromkeys(str(r) for r in reasons))
    if hold is None:
        hold = ProgressionSafetyHold(
            created_at=now, updated_at=now, contestant_id=contestant.id, contest_id=contest_id,
            round_id=getattr(to_season, "round_id", None),
            from_season_id=getattr(from_season, "id", None), to_season_id=to_season.id,
            from_level=_level_value(getattr(from_season, "level", None)),
            to_level=_level_value(to_season.level) or "unknown", status="HELD", reason_codes=codes,
            held_at=now, last_checked_at=now)
        db.add(hold)
        db.flush()
        _event(db, AgeSafetyEventType.PROGRESSION_HELD_SAFETY, hold, actor_id=None, now=now)
        return hold
    hold.last_checked_at, hold.updated_at = now, now
    if hold.status == "HELD" and hold.reason_codes != codes:
        hold.reason_codes = codes
    return hold


def gate_progression(db: Session, contestant: Contestant, *, to_season, from_season=None,
                     contest_id: Optional[int], today: Optional[date] = None, reevaluate: bool = True) -> bool:
    """The ONE progression gate every lifecycle writer calls before it activates
    a destination membership. True -> proceed exactly as before. False -> the
    hold is recorded and the caller must leave the contestant untouched.

    reevaluate=False (entry-stage syncs that run for a whole cohort on every
    pass) reads the current stored decision; ranked promotions re-evaluate."""
    decision = can_progress(db, contestant, today=today, reevaluate=reevaluate)
    if decision.eligible:
        return True
    record_progression_hold(db, contestant, to_season=to_season, from_season=from_season,
                            contest_id=contest_id, reasons=decision.reasons)
    return False


def _stage_still_running(db: Session, hold: ProgressionSafetyHold, contest, today: date) -> bool:
    """Is the destination stage of the held advancement still in progress for
    this cohort? Unknown timing -> False (administrator review, never a guess)."""
    from app.models.contests import ContestSeason, SeasonLevel
    from app.models.round import Round
    from app.services.top_high5_live import _level_close_date_for_mode

    season = db.query(ContestSeason).filter(ContestSeason.id == hold.to_season_id).first()
    rnd = db.query(Round).filter(Round.id == season.round_id).first() if season and season.round_id else None
    if season is None or rnd is None or season.level is None:
        return False
    level = season.level if isinstance(season.level, SeasonLevel) else SeasonLevel(str(season.level).lower())
    close = _level_close_date_for_mode(rnd, level, getattr(contest, "contest_mode", "") or "")
    if close is None:
        return False
    close_day = close.date() if isinstance(close, datetime) else close
    return today <= close_day


def release_holds(db: Session, *, contestant_ids: Optional[Iterable[int]] = None, actor_id: Optional[int] = None,
                  today: Optional[date] = None, limit: int = 500) -> dict:
    """Re-evaluate open (HELD) progression holds. Resolved + stage still running
    -> the SAME destination membership is activated through the same lifecycle
    helper (source membership closed, is_qualified set) exactly as the
    original promotion would have done. Resolved but stage timing passed ->
    REVIEW_REQUIRED for an administrator (no month skipped or invented).
    Still unresolved -> stays HELD. Caller commits."""
    from app.models.contest import Contest
    from app.models.contests import ContestantSeason
    from app.services.age_policy_engine import utc_today
    from app.services.season_migration import ForeignRoundActivationError, SeasonMigrationService

    today = today or utc_today()
    now = datetime.utcnow()
    q = db.query(ProgressionSafetyHold).filter(ProgressionSafetyHold.status == "HELD")
    if contestant_ids is not None:
        q = q.filter(ProgressionSafetyHold.contestant_id.in_(list(contestant_ids) or [-1]))
    out = {"checked": 0, "released": 0, "review_required": 0, "still_held": 0}
    for hold in q.order_by(ProgressionSafetyHold.id).limit(limit).all():
        out["checked"] += 1
        contestant = db.query(Contestant).filter(Contestant.id == hold.contestant_id).first()
        decision = can_progress(db, contestant, today=today)
        hold.last_checked_at, hold.updated_at = now, now
        if not decision.eligible:
            hold.reason_codes = list(decision.reasons)
            out["still_held"] += 1
            continue
        contest = db.query(Contest).filter(Contest.id == hold.contest_id).first() if hold.contest_id else None
        already = db.query(ContestantSeason.id).filter(ContestantSeason.contestant_id == contestant.id,
                                                       ContestantSeason.season_id == hold.to_season_id,
                                                       ContestantSeason.is_active == True).first()  # noqa: E712
        if already is None and not _stage_still_running(db, hold, contest, today):
            hold.status, hold.resolution = "REVIEW_REQUIRED", "STAGE_TIMING_PASSED"
            _event(db, AgeSafetyEventType.PROGRESSION_REVIEW_REQUIRED, hold, actor_id=actor_id, now=now)
            out["review_required"] += 1
            continue
        if already is None:
            try:
                SeasonMigrationService._activate_contestant_season_link(db, contestant.id, hold.to_season_id)
            except (ForeignRoundActivationError, ValueError):
                hold.status, hold.resolution = "REVIEW_REQUIRED", "ACTIVATION_REFUSED"
                _event(db, AgeSafetyEventType.PROGRESSION_REVIEW_REQUIRED, hold, actor_id=actor_id, now=now)
                out["review_required"] += 1
                continue
            if hold.from_season_id is not None:
                old = db.query(ContestantSeason).filter(ContestantSeason.contestant_id == contestant.id,
                                                        ContestantSeason.season_id == hold.from_season_id,
                                                        ContestantSeason.is_active == True).first()  # noqa: E712
                if old is not None:
                    old.is_active = False
            contestant.is_qualified = True
        hold.status = "RELEASED"
        hold.resolution = "RELEASED_AFTER_REEVALUATION"
        hold.resolved_at, hold.resolved_by_user_id = now, actor_id
        _event(db, AgeSafetyEventType.PROGRESSION_RELEASED_AFTER_REEVALUATION, hold, actor_id=actor_id, now=now)
        out["released"] += 1
    db.flush()
    return out


def safe_release_holds_for(db: Session, contestant_id: Optional[int], *, actor_id: Optional[int] = None) -> None:
    """Hook after a Phase 5 re-evaluation made an entry public again. Never raises."""
    if not contestant_id:
        return
    try:
        if db.query(ProgressionSafetyHold.id).filter(ProgressionSafetyHold.contestant_id == contestant_id,
                                                     ProgressionSafetyHold.status == "HELD").first() is None:
            return
        release_holds(db, contestant_ids=[contestant_id], actor_id=actor_id)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the caller's own change is already committed
        db.rollback()
        logger.warning("Phase 8 hold release failed: %s", type(exc).__name__)


# ---------------------------------------------------------------------------
# Staff view (codes only; never a public-eligibility decision)
# ---------------------------------------------------------------------------

def staff_hold_view(hold: ProgressionSafetyHold) -> Dict[str, object]:
    return {
        "id": hold.id, "contestant_id": hold.contestant_id, "contest_id": hold.contest_id, "round_id": hold.round_id,
        "from_season_id": hold.from_season_id, "to_season_id": hold.to_season_id, "from_level": hold.from_level,
        "to_level": hold.to_level, "status": hold.status, "reason_codes": list(hold.reason_codes or ()),
        "held_at": hold.held_at.isoformat() if hold.held_at else None,
        "last_checked_at": hold.last_checked_at.isoformat() if hold.last_checked_at else None,
        "resolved_at": hold.resolved_at.isoformat() if hold.resolved_at else None,
        "resolution": hold.resolution,
        # Staff visibility is not participation: the public flags stay the live decision.
        "visibility": Eligibility.VISIBLE_TO_STAFF,
    }
