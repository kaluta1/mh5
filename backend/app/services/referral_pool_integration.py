"""Multi-Unit Referral Pool: KYC, account and risk changes reach the pool (P6).

Reliability: a KYC decision writes ONE referral_pool_events row in its own transaction (an
outbox): the event commits with the decision or not at all, so nothing is lost after a commit
and nothing is acted on for a decision that rolled back. The KYC transaction takes no pool
lock (an insert into this table is not one). The worker later handles each event in its own
short transaction, member row first (NO KEY UPDATE, the KYC mode), then the pool:

  KYC_APPROVED   risk scan (identity, wallet, login IP); units brought in line with eligibility
                 (suspended or restored); queued for a pool sponsor when the member has none.
  KYC_REJECTED / ACCOUNT_CHANGED   units brought in line (suspended: open slots VOID).
  RISK_CLEARED   as KYC_APPROVED, without a new scan.
  SIGNED_UP      a new member without a sponsor is queued for a pool sponsor (no KYC needed).

A failing event is retried up to MAX_ATTEMPTS times, then FAILED (visible, retried on request).
A sweep also re-checks unit holders whose eligibility changed by any other path (an account
deactivated or deleted, an age review opened). The worker never runs unless
REFERRAL_POOL_WORKER_ENABLED is set; allocation additionally needs allocation_enabled.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.business_model import ReferralPoolEvent, ReferralPoolUnit
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
KYC_APPROVED, KYC_REJECTED, ACCOUNT_CHANGED, RISK_CLEARED, SIGNED_UP = (
    "KYC_APPROVED", "KYC_REJECTED", "ACCOUNT_CHANGED", "RISK_CLEARED", "SIGNED_UP")


# ---------------------------------------------------------------- the outbox (inside the decision's transaction)

def record_event(db: Session, *, user_id: int, event_type: str, dedupe_key: str,
                 kyc_verification_id: Optional[int] = None, now: Optional[datetime] = None) -> None:
    """Insert once (dedupe_key), in the CALLER's transaction. Never commits, never locks a pool row."""
    now = now or datetime.utcnow()
    db.execute(text(
        "INSERT INTO referral_pool_events (user_id, event_type, kyc_verification_id, dedupe_key, status, attempts, "
        "created_at, updated_at) VALUES (:u, :e, :k, :d, 'PENDING', 0, :t, :t) ON CONFLICT (dedupe_key) DO NOTHING"),
        {"u": user_id, "e": event_type, "k": kyc_verification_id, "d": dedupe_key[:160], "t": now})


def record_signup(db: Session, user: User) -> None:
    """Called by registration, before its commit, when the new member has no sponsor. One event
    per member: the worker queues them for a pool sponsor after the sign-up has committed."""
    record_event(db, user_id=int(user.id), event_type=SIGNED_UP, dedupe_key=f"{SIGNED_UP}:{user.id}")


def record_kyc_decision(db: Session, verification, *, approved: bool) -> None:
    """Called by the KYC decision itself, before its commit. One event per decision and attempt:
    a repeated approval callback of the same attempt adds nothing."""
    kind = KYC_APPROVED if approved else KYC_REJECTED
    record_event(db, user_id=int(verification.user_id), event_type=kind, kyc_verification_id=int(verification.id),
                 dedupe_key=f"{kind}:{verification.id}:{int(verification.attempts_count or 0)}")


# ---------------------------------------------------------------- the worker

def handle_event(db: Session, event: ReferralPoolEvent, *, now: Optional[datetime] = None) -> str:
    """Bring the member's pool state in line with what is true NOW (not with what the event says:
    events of one member may be handled in any order and still end right)."""
    from app.services import referral_pool_allocation as alloc
    from app.services import referral_pool_risk as risk
    from app.services import referral_pool_units as units

    now = now or datetime.utcnow()
    member = (db.query(User).filter(User.id == event.user_id)
              .with_for_update(key_share=True).populate_existing().first())         # member before the pool
    if member is None:
        return "NO_MEMBER"
    if event.event_type == KYC_APPROVED:
        risk.scan_member(db, member.id, now=now)
    suspended, restored = units.sync_member_eligibility(db, member.id, now=now)
    outcome = f"units:-{suspended}/+{restored}"
    if event.event_type == SIGNED_UP:
        queued = alloc.enqueue(db, member.id, trigger=alloc.SIGNED_UP, now=now)
        return f"queue:{queued.outcome}:{queued.reason or ''}"
    if event.event_type in (KYC_APPROVED, RISK_CLEARED):
        queued = alloc.enqueue_after_kyc(db, member.id, kyc_verification_id=event.kyc_verification_id, now=now)
        outcome += f";queue:{queued.outcome}:{queued.reason or ''}"
    return outcome


def process_events(session_factory, *, limit: int = 100, now: Optional[datetime] = None) -> list:
    """Handle PENDING events oldest first, each in its own transaction. Several workers at once
    never handle the same event (FOR UPDATE SKIP LOCKED)."""
    results = []
    for _ in range(limit):
        with session_factory() as db:
            event = (db.query(ReferralPoolEvent).filter(ReferralPoolEvent.status == "PENDING")
                     .order_by(ReferralPoolEvent.id).with_for_update(skip_locked=True).first())
            if event is None:
                break
            event_id = event.id
            try:
                outcome = handle_event(db, event, now=now)
                event.status, event.processed_at, event.last_error = "DONE", now or datetime.utcnow(), None
                event.attempts = int(event.attempts or 0) + 1
                db.commit()
                results.append((event_id, "DONE", outcome))
                continue
            except Exception as exc:  # noqa: BLE001 - recorded, retried, then FAILED
                db.rollback()
                error = f"{type(exc).__name__}: {exc}"[:200]
        with session_factory() as db:
            event = db.query(ReferralPoolEvent).filter(ReferralPoolEvent.id == event_id).with_for_update().one()
            event.attempts = int(event.attempts or 0) + 1
            event.last_error = error
            if event.attempts >= MAX_ATTEMPTS:
                event.status, event.processed_at = "FAILED", now or datetime.utcnow()
                logger.error("Referral Pool event %s FAILED after %s attempts", event_id, event.attempts)
            db.commit()
            results.append((event_id, event.status, error))
            if event.status == "PENDING":
                break                                 # retried on the next pass, not in a tight loop
    return results


def retry_failed_event(db: Session, event_id: int) -> ReferralPoolEvent:
    """Put a FAILED event back in line (an operator's recovery). Does not commit."""
    event = db.query(ReferralPoolEvent).filter(ReferralPoolEvent.id == event_id).with_for_update().one()
    if event.status == "FAILED":
        event.status, event.processed_at, event.attempts = "PENDING", None, 0
        db.flush()
    return event


def sweep_eligibility(session_factory, *, limit: int = 500, now: Optional[datetime] = None) -> int:
    """Unit holders whose eligibility no longer matches their units (changed by a path that writes
    no event: deactivation, deletion, an age review). One short transaction per holder. Every holder
    is visited, `limit` at a time in user-id order; a holder that fails is logged and skipped, so
    one bad record never stops the sweep or the queue after it."""
    from app.services import referral_pool_units as units

    changed, last_id = 0, 0
    while True:
        with session_factory() as db:
            holders = [u for (u,) in db.query(ReferralPoolUnit.user_id).filter(
                ReferralPoolUnit.status.in_((units.ACTIVE, units.SUSPENDED)), ReferralPoolUnit.user_id > last_id
            ).distinct().order_by(ReferralPoolUnit.user_id).limit(limit)]
        if not holders:
            return changed
        for holder_id in holders:
            with session_factory() as db:
                try:
                    db.query(User).filter(User.id == holder_id).with_for_update(key_share=True).first()
                    suspended, restored = units.sync_member_eligibility(db, holder_id, now=now)
                    db.commit()
                    changed += suspended + restored
                except Exception as exc:  # noqa: BLE001 - one holder never blocks the others
                    db.rollback()
                    logger.error("Referral Pool eligibility sweep failed for holder %s: %s", holder_id,
                                 type(exc).__name__)
        last_id = holders[-1]


def run_once(session_factory, *, now: Optional[datetime] = None) -> dict:
    """One worker pass: events, the eligibility sweep, then the queue (allocation switch inside)."""
    from app.services import referral_pool_allocation as alloc

    events = process_events(session_factory, now=now)
    swept = sweep_eligibility(session_factory, now=now)
    queue = alloc.process_pending(session_factory, now=now)
    return {"events": events, "swept": swept, "queue": queue}


def worker_enabled() -> bool:
    return os.getenv("REFERRAL_POOL_WORKER_ENABLED", "false").strip().lower() in ("1", "true", "yes")


class ReferralPoolScheduler:
    """The pool worker as one of the application's schedulers. Each tick is a no-op unless
    REFERRAL_POOL_WORKER_ENABLED=true (off by default: nothing runs in production unasked)."""

    def __init__(self, interval_seconds: Optional[int] = None):
        self.interval = max(int(interval_seconds or os.getenv("REFERRAL_POOL_WORKER_INTERVAL_SECONDS", "60")), 10)
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Referral Pool worker scheduler started (interval: %ss, enabled: %s)", self.interval,
                    worker_enabled())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        await asyncio.sleep(20)                       # let the application finish starting
        while self.running:
            try:
                await self._run_pass()
            except Exception as exc:  # noqa: BLE001 - the scheduler must never die
                logger.error("Referral Pool worker pass failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval)

    async def _run_pass(self):
        if not worker_enabled():
            return
        from app.db.session import SessionLocal

        await asyncio.to_thread(run_once, SessionLocal)


# ---------------------------------------------------------------- read-only audit

def invalid_personal_sponsors(db: Session, limit: int = 1000, offset: int = 0) -> list:
    """Members whose PERSONAL/JOIN_CODE sponsor would not be a valid inviter today (not active,
    deleted, or under a duplicate-identity review). Read-only: such sponsors are kept exactly as they are.
    `limit`/`offset` page over the personally sponsored members checked (in id order)."""
    from app.services.sponsor_assignment import inviter_eligible

    rows = (db.query(User.id, User.sponsor_id, User.sponsor_source)
            .filter(User.sponsor_id.isnot(None), User.sponsor_source.in_(("PERSONAL_REFERRAL", "JOIN_CODE")))
            .order_by(User.id).offset(offset).limit(limit).all())
    out = []
    for user_id, sponsor_id, source in rows:
        sponsor = db.query(User).filter(User.id == sponsor_id).first()
        if not inviter_eligible(db, sponsor):
            out.append({"user_id": user_id, "sponsor_id": sponsor_id, "source": source})
    return out
