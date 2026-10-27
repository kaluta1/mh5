"""Multi-Unit Referral Pool: quota rounds and the random draw (P4). Gated by allocation_enabled.

A round opens with ONE slot per ACTIVE unit whose holder is eligible at that moment (a snapshot:
units bought or restored later join the next round). A KYC-approved referral without a valid
personal inviter waits in referral_pool_pending; each assignment takes one OPEN slot chosen
uniformly at random (``secrets``) among the slots it may take, fills it, and makes the slot's
holder the referral's sponsor, once. A round completes when every slot is FILLED or VOID; the
next one opens only when a waiting referral needs a slot, and never empty. Nobody is allocated
while fewer than MIN_ALLOCATION_HOLDERS eligible holders hold MIN_ALLOCATION_UNITS eligible ACTIVE
units (1 and 1: the pool works from its first eligible unit): referrals keep waiting
(POOL_BELOW_MINIMUM), an OPEN round included. DSM-imported members are never pool-assigned: their
sponsor is the one the import resolved, or deliberately none.

Fairness: every OPEN slot is equally likely; a unit holds one slot per round, so a holder of N
continuously eligible units receives exactly N referrals per completed round. Slots a referral
may not take (its own, or its downline's: no self-referral, no cycle) are left for the next
referral, not voided. A drawn slot whose holder is no longer eligible is not used: the holder's
units are suspended (their open slots become VOID) and the draw is repeated, which keeps the
choice uniform among eligible slots.

Locking (P3 order): the referred member's row FOR NO KEY UPDATE, then the pool mutex, the OPEN
round, units, slots, then the queue row. One short transaction per assignment, run AFTER the
KYC approval has committed; no KYC verification row is locked here. The database enforces one
OPEN round, one assignment per referral and one assignment per slot.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.business_model import (
    ReferralPoolAssignment,
    ReferralPoolPending,
    ReferralPoolRound,
    ReferralPoolRoundSlot,
    ReferralPoolUnit,
)
from app.models.user import User
from app.services import referral_pool_units as units

logger = logging.getLogger(__name__)

METHOD = "QUOTA_ROUND_V1"
POOL_SOURCE = "REFERRAL_POOL"
_PERSONAL_SOURCES = ("PERSONAL_REFERRAL", "JOIN_CODE")
_MAX_REDRAWS = 1000
# Minimum pool before anyone is allocated: no round opens and no slot is drawn unless at least this
# many distinct eligible holders hold at least this many eligible ACTIVE units. Owner rule (Shafi
# Abeid, 2026-10-26) replaces the P15 D4-C 5/10: the pool runs from the first eligible holder with
# one eligible ACTIVE unit, who then receives every pool referral. Fixed in code on purpose.
MIN_ALLOCATION_HOLDERS = 1
MIN_ALLOCATION_UNITS = 1
BELOW_MINIMUM = "POOL_BELOW_MINIMUM"

# outcomes
ASSIGNED, ALREADY_ASSIGNED, WAITING, CANCELLED, DISABLED, NOT_QUEUED, ERROR = (
    "ASSIGNED", "ALREADY_ASSIGNED", "WAITING", "CANCELLED", "DISABLED", "NOT_QUEUED", "ERROR")


@dataclass(frozen=True)
class Result:
    outcome: str
    reason: Optional[str] = None
    assignment_id: Optional[int] = None
    round_id: Optional[int] = None
    sponsor_id: Optional[int] = None


# ---------------------------------------------------------------- who may enter the pool

def valid_personal_inviter(db: Session, user: User) -> bool:
    """The member already has a personal sponsor who is active, not deleted and KYC-approved."""
    if user.sponsor_id is None or user.sponsor_source not in _PERSONAL_SOURCES:
        return False
    from app.services.sponsor_assignment import inviter_eligible

    inviter = db.query(User).filter(User.id == user.sponsor_id).first()
    return inviter_eligible(db, inviter)                    # the one inviter rule (registration, codes, pool)


def dsm_imported(db: Session, user_id: int) -> bool:
    """The account came from (or was matched by) the DSM member import (legacy_import.dsm_members,
    written by MH5/reports/dsm-import, not an ORM table: absent outside production)."""
    if db.get_bind().dialect.name != "postgresql" or db.execute(
            text("SELECT to_regclass('legacy_import.dsm_members')")).scalar() is None:
        return False
    return db.execute(text("SELECT 1 FROM legacy_import.dsm_members WHERE mh5_user_id = :u LIMIT 1"),
                      {"u": int(user_id)}).first() is not None


def _entry_refusal(db: Session, user: Optional[User]) -> Optional[str]:
    """Why this member may not wait for a pool sponsor now (None: they may)."""
    if user is None or not user.is_active or user.is_deleted:
        return "ACCOUNT_UNAVAILABLE"
    if db.query(ReferralPoolAssignment.id).filter(ReferralPoolAssignment.referred_user_id == user.id).first():
        return "ALREADY_POOL_ASSIGNED"
    if dsm_imported(db, user.id):
        return "DSM_IMPORTED"                                 # the import decided the sponsor (or none)
    if user.sponsor_id is not None:
        # A sponsor is never replaced, whatever its source: a valid personal invitation takes
        # precedence, and any other existing sponsor relationship is left exactly as it is.
        return "PERSONAL_INVITATION" if valid_personal_inviter(db, user) else "SPONSOR_PRESENT"
    eligibility = units.member_eligibility(db, user)
    if not eligibility.eligible:
        return eligibility.reason or "NOT_ELIGIBLE"           # e.g. KYC_REQUIRED: the pool waits for KYC approval
    return None


def enqueue_after_kyc(db: Session, user_id: int, *, kyc_verification_id: Optional[int] = None,
                      now: Optional[datetime] = None) -> Result:
    """Called in its own transaction after a KYC approval commits. Idempotent: one queue row per
    member; a row cancelled for a reason that no longer holds waits again. Queuing is allowed
    while allocation is switched off (nothing is assigned until it is on)."""
    now = now or datetime.utcnow()
    user = db.query(User).filter(User.id == user_id).with_for_update(key_share=True).first()
    refusal = _entry_refusal(db, user)
    existing = (db.query(ReferralPoolPending).filter(ReferralPoolPending.referred_user_id == user_id)
                .with_for_update().first())
    if refusal is not None:
        return Result(NOT_QUEUED, refusal)
    if existing is not None:
        if existing.status == "CANCELLED":
            existing.status, existing.resolved_at, existing.resolution_reason = "WAITING", None, None
            existing.enqueued_at, existing.kyc_verification_id = now, kyc_verification_id
            db.flush()
        return Result(WAITING if existing.status == "WAITING" else ALREADY_ASSIGNED)
    db.execute(text("INSERT INTO referral_pool_pending (referred_user_id, status, trigger_event, kyc_verification_id, "
                    "enqueued_at, attempts, created_at, updated_at) VALUES (:u, 'WAITING', 'KYC_APPROVED', :k, :t, 0, "
                    ":t, :t) ON CONFLICT (referred_user_id) DO NOTHING"),
               {"u": user_id, "k": kyc_verification_id, "t": now})
    return Result(WAITING)


# ---------------------------------------------------------------- rounds

def _open_round(db: Session) -> Optional[ReferralPoolRound]:
    return (db.query(ReferralPoolRound).filter(ReferralPoolRound.status == "OPEN")
            .with_for_update().populate_existing().first())


def eligible_active_units(db: Session) -> List[tuple]:
    """(unit id, holder id) of every ACTIVE unit whose holder is eligible now, in unit-id order."""
    rows = (db.query(ReferralPoolUnit.id, ReferralPoolUnit.user_id).filter(ReferralPoolUnit.status == units.ACTIVE)
            .order_by(ReferralPoolUnit.id).all())
    holders: Dict[int, bool] = {}
    for _uid, holder_id in rows:
        if holder_id not in holders:
            holder = db.query(User).filter(User.id == holder_id).first()
            holders[holder_id] = units.member_eligibility(db, holder).eligible
    return [(uid, holder_id) for uid, holder_id in rows if holders[holder_id]]


def meets_minimum(snapshot: List[tuple]) -> bool:
    return (len({holder_id for _uid, holder_id in snapshot}) >= MIN_ALLOCATION_HOLDERS
            and len(snapshot) >= MIN_ALLOCATION_UNITS)


def open_round_if_needed(db: Session, *, now: Optional[datetime] = None) -> Optional[ReferralPoolRound]:
    """The OPEN round, or a new one from a snapshot of eligible ACTIVE units. None when allocation
    is off or the pool is below the minimum (no empty or undersized round is ever created).
    Caller holds the pool mutex or this takes it."""
    now = now or datetime.utcnow()
    cfg = units.lock_pool(db)
    if not cfg.allocation_enabled:
        return None
    current = _open_round(db)
    if current is not None:
        return current
    snapshot = eligible_active_units(db)
    if not meets_minimum(snapshot):
        return None
    number = int(db.query(func.coalesce(func.max(ReferralPoolRound.round_number), 0)).scalar()) + 1
    digest = hashlib.sha256(",".join(f"{u}:{h}" for u, h in snapshot).encode()).hexdigest()
    round_ = ReferralPoolRound(round_number=number, status="OPEN", method=METHOD, opened_at=now,
                               total_slots=len(snapshot), filled_slots=0, void_slots=0, snapshot_sha256=digest)
    db.add(round_)
    db.flush()
    db.bulk_insert_mappings(ReferralPoolRoundSlot, [
        {"round_id": round_.id, "unit_id": uid, "member_user_id": holder_id, "status": "OPEN",
         "created_at": now, "updated_at": now} for uid, holder_id in snapshot])
    db.flush()
    logger.info("Referral Pool round %s opened with %s slots", number, len(snapshot))
    return round_


def _complete_if_done(round_: ReferralPoolRound, now: datetime) -> None:
    if round_.status == "OPEN" and round_.filled_slots + round_.void_slots == round_.total_slots:
        round_.status, round_.completed_at = "COMPLETED", now


def _downline(db: Session, user_id: int) -> Set[int]:
    """Everyone whose sponsor chain leads to `user_id` (terminates on existing data cycles)."""
    rows = db.execute(text(
        "WITH RECURSIVE d(id) AS (SELECT id FROM users WHERE sponsor_id = :u "
        "UNION SELECT x.id FROM users x JOIN d ON x.sponsor_id = d.id) SELECT id FROM d"), {"u": user_id})
    return {r[0] for r in rows}


# ---------------------------------------------------------------- the draw

def assign(db: Session, referred_user_id: int, *, now: Optional[datetime] = None) -> Result:
    """One assignment attempt for one waiting referral, in the caller's (short) transaction.
    Idempotent: an assigned referral returns its assignment; nothing is ever re-assigned."""
    now = now or datetime.utcnow()
    referred = (db.query(User).filter(User.id == referred_user_id)
                .with_for_update(key_share=True).populate_existing().first())       # member before the mutex
    cfg = units.lock_pool(db)
    pending = (db.query(ReferralPoolPending).filter(ReferralPoolPending.referred_user_id == referred_user_id)
               .with_for_update().populate_existing().first())
    done = (db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.referred_user_id == referred_user_id)
            .first())
    if done is not None:
        return Result(ALREADY_ASSIGNED, assignment_id=done.id, round_id=done.round_id,
                      sponsor_id=done.pool_member_user_id)
    if pending is None or pending.status != "WAITING":
        return Result(NOT_QUEUED, "NOT_WAITING")
    if not cfg.allocation_enabled:
        return Result(DISABLED)

    refusal = _entry_refusal(db, referred)
    if refusal is not None:
        # The sponsor came from elsewhere meanwhile (a personal invitation), or the member can no
        # longer take part: the wait ends without an assignment (it can be queued again later).
        pending.status, pending.resolved_at, pending.resolution_reason = "CANCELLED", now, refusal
        db.flush()
        return Result(CANCELLED, refusal)

    snapshot = eligible_active_units(db)
    if not snapshot:
        return _wait(pending, "NO_ELIGIBLE_UNIT", now)
    if not meets_minimum(snapshot):
        return _wait(pending, BELOW_MINIMUM, now)           # also holds an OPEN round if the pool shrank
    excluded = _downline(db, referred_user_id) | {referred_user_id}
    eligible_cache: Dict[int, bool] = {}
    for _ in range(_MAX_REDRAWS):
        round_ = open_round_if_needed(db, now=now)
        if round_ is None:
            return _wait(pending, "NO_ELIGIBLE_UNIT", now)
        open_slots = (db.query(ReferralPoolRoundSlot.id, ReferralPoolRoundSlot.unit_id, ReferralPoolRoundSlot.member_user_id)
                      .filter(ReferralPoolRoundSlot.round_id == round_.id, ReferralPoolRoundSlot.status == "OPEN",
                              ~ReferralPoolRoundSlot.member_user_id.in_(excluded)))
        candidate_count = open_slots.count()
        if candidate_count == 0:
            if round_.filled_slots + round_.void_slots < round_.total_slots:
                return _wait(pending, "NO_ELIGIBLE_SLOT", now)       # only slots this referral may not take
            _complete_if_done(round_, now)                           # defensive: counters said full
            db.flush()
            continue
        # Uniform among the candidates: a secure random position in a fixed (id) order. The order
        # only numbers the slots; the choice is entirely secrets.randbelow. No slot changes under
        # us: every writer of slots holds the pool mutex we hold.
        slot_id, unit_id, holder_id = (open_slots.order_by(ReferralPoolRoundSlot.id)
                                       .offset(secrets.randbelow(candidate_count)).limit(1).one())
        if holder_id not in eligible_cache:
            holder = db.query(User).filter(User.id == holder_id).first()
            eligible_cache[holder_id] = units.member_eligibility(db, holder).eligible
        if not eligible_cache[holder_id]:
            units.suspend_member_units(db, holder_id, "NOT_ELIGIBLE_AT_DRAW", now=now)   # voids their open slots
            continue
        unit = (db.query(ReferralPoolUnit).filter(ReferralPoolUnit.id == unit_id)
                .with_for_update().populate_existing().one())
        slot = (db.query(ReferralPoolRoundSlot).filter(ReferralPoolRoundSlot.id == slot_id)
                .with_for_update().populate_existing().one())
        if unit.status != units.ACTIVE or slot.status != "OPEN":
            if slot.status == "OPEN":                                # stale: the unit left the pool
                slot.status, slot.voided_at, slot.void_reason = "VOID", now, "UNIT_NOT_ACTIVE"
                round_.void_slots += 1
                _complete_if_done(round_, now)
                db.flush()
            continue
        return _fill(db, referred, pending, round_, slot, unit, candidate_count, now)
    raise RuntimeError("Referral Pool draw did not settle")


def _wait(pending: ReferralPoolPending, reason: str, now: datetime) -> Result:
    pending.attempts = int(pending.attempts or 0) + 1
    pending.last_attempt_at, pending.last_error = now, reason
    return Result(WAITING, reason)


def _fill(db: Session, referred: User, pending: ReferralPoolPending, round_: ReferralPoolRound,
          slot: ReferralPoolRoundSlot, unit: ReferralPoolUnit, candidate_count: int, now: datetime) -> Result:
    assignment = ReferralPoolAssignment(referred_user_id=referred.id, pool_member_user_id=slot.member_user_id,
                                        method=METHOD, candidate_count=candidate_count, assigned_at=now,
                                        round_id=round_.id, slot_id=slot.id, unit_id=unit.id)
    db.add(assignment)
    slot.status, slot.filled_at = "FILLED", now
    round_.filled_slots += 1
    _complete_if_done(round_, now)
    referred.sponsor_id, referred.sponsor_source, referred.sponsor_assigned_at = slot.member_user_id, POOL_SOURCE, now
    db.flush()
    pending.status, pending.resolved_at, pending.resolution_reason = "ASSIGNED", now, "ASSIGNED"
    pending.assignment_id = assignment.id
    pending.attempts = int(pending.attempts or 0) + 1
    pending.last_attempt_at, pending.last_error = now, None
    db.flush()
    return Result(ASSIGNED, assignment_id=assignment.id, round_id=round_.id, sponsor_id=slot.member_user_id)


# ---------------------------------------------------------------- the queue worker

def waiting_in_order(db: Session, limit: int = 100) -> List[int]:
    """Waiting referrals, oldest first (enqueued_at, then id): the deterministic FIFO order."""
    return [r for (r,) in db.query(ReferralPoolPending.referred_user_id)
            .filter(ReferralPoolPending.status == "WAITING")
            .order_by(ReferralPoolPending.enqueued_at, ReferralPoolPending.id).limit(limit)]


def process_pending(session_factory, *, limit: int = 100, now: Optional[datetime] = None) -> List[Result]:
    """Work the queue in FIFO order, one short transaction per referral. Safe with several
    workers at once: each referral is decided under its own row lock, once."""
    with session_factory() as db:
        order = waiting_in_order(db, limit)
    results = []
    for referred_user_id in order:
        with session_factory() as db:
            try:
                result = assign(db, referred_user_id, now=now)
                db.commit()
            except Exception as exc:  # noqa: BLE001 - recorded on the queue row; the next referral goes on
                db.rollback()
                result = Result(ERROR, f"{type(exc).__name__}"[:60])
                _record_error(session_factory, referred_user_id, f"{type(exc).__name__}: {exc}"[:200], now)
        results.append(result)
        if result.outcome == DISABLED:
            break
    return results


def _record_error(session_factory, referred_user_id: int, error: str, now: Optional[datetime]) -> None:
    """A failed attempt stays WAITING (it is retried on the next pass, not in a loop) and is visible."""
    with session_factory() as db:
        row = (db.query(ReferralPoolPending).filter(ReferralPoolPending.referred_user_id == referred_user_id,
                                                    ReferralPoolPending.status == "WAITING")
               .with_for_update().first())
        if row is not None:
            row.attempts = int(row.attempts or 0) + 1
            row.last_attempt_at, row.last_error = now or datetime.utcnow(), error
            db.commit()
    logger.error("Referral Pool assignment of %s failed: %s", referred_user_id, error)
