"""MyHigh5 Referral Pool: $100 seats (max capacity from referral_pool_config) and the
fair assignment of organic signups to pool members.

Capacity is enforced by the database (unique seat_number over seat-holding statuses),
not only by application checks: two concurrent purchases cannot both hold the last seat.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.business_model import ReferralPoolAssignment, ReferralPoolConfig, ReferralPoolMembership
from app.models.user import User

RESERVED = "RESERVED"
ACTIVE = "ACTIVE"
CAPACITY_REVIEW = "CAPACITY_REVIEW"  # paid after the reservation lapsed and the pool was full
EXPIRED = "EXPIRED"
CANCELLED = "CANCELLED"
REFUNDED = "REFUNDED"
REVOKED = "REVOKED"
SEAT_STATUSES = (RESERVED, ACTIVE, CAPACITY_REVIEW)

SOURCE_PAID = "PAID"
SOURCE_LEGACY = "LEGACY_FOUNDING_MIGRATION"
SOURCE_ADMIN = "ADMIN_ADJUSTMENT"

_SEAT_RETRIES = 5


class ReferralPoolError(ValueError):
    pass


class PoolFull(ReferralPoolError):
    pass


class AlreadyMember(ReferralPoolError):
    pass


def get_config(db: Session, *, lock: bool = False) -> ReferralPoolConfig:
    q = db.query(ReferralPoolConfig).order_by(ReferralPoolConfig.id.asc())
    if lock:
        q = q.with_for_update()
    cfg = q.first()
    if cfg is None:
        raise ReferralPoolError("Referral Pool is not configured")
    return cfg


def expire_stale_reservations(db: Session, now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    stale = (
        db.query(ReferralPoolMembership)
        .filter(ReferralPoolMembership.status == RESERVED, ReferralPoolMembership.reservation_expires_at <= now)
        .all()
    )
    for row in stale:
        row.status = EXPIRED
        row.ended_at = now
        row.seat_number = None
    db.flush()
    return len(stale)


def seats_in_use(db: Session) -> int:
    """Numbered seats held (unexpired reservations + active members). Never exceeds capacity."""
    return (
        db.query(func.count(ReferralPoolMembership.id))
        .filter(ReferralPoolMembership.status.in_(SEAT_STATUSES), ReferralPoolMembership.seat_number.isnot(None))
        .scalar()
        or 0
    )


def active_members(db: Session) -> int:
    return db.query(func.count(ReferralPoolMembership.id)).filter(ReferralPoolMembership.status == ACTIVE).scalar() or 0


def open_membership_for_user(db: Session, user_id: int) -> Optional[ReferralPoolMembership]:
    return (
        db.query(ReferralPoolMembership)
        .filter(ReferralPoolMembership.user_id == user_id, ReferralPoolMembership.status.in_(SEAT_STATUSES))
        .first()
    )


def _lowest_free_seat(db: Session, capacity: int) -> Optional[int]:
    used = {
        n for (n,) in db.query(ReferralPoolMembership.seat_number)
        .filter(ReferralPoolMembership.status.in_(SEAT_STATUSES), ReferralPoolMembership.seat_number.isnot(None))
        .all()
    }
    for n in range(1, capacity + 1):
        if n not in used:
            return n
    return None


def _take_seat(db: Session, build) -> Optional[ReferralPoolMembership]:
    """Insert a seat-holding row on the lowest free seat; retry on a concurrent seat collision."""
    cfg = get_config(db, lock=True)
    for _ in range(_SEAT_RETRIES):
        seat = _lowest_free_seat(db, int(cfg.capacity))
        if seat is None:
            return None
        savepoint = db.begin_nested()
        try:
            row = build(seat)
            db.add(row)
            db.flush()
            savepoint.commit()
            return row
        except IntegrityError:
            savepoint.rollback()
            if open_membership_for_user(db, build(0).user_id) is not None:
                raise AlreadyMember("User already holds a Referral Pool seat")
    raise ReferralPoolError("Could not allocate a Referral Pool seat; please retry")


def reserve_for_purchase(db: Session, user: User, now: Optional[datetime] = None) -> ReferralPoolMembership:
    """Hold a seat for the lifetime of a payment invoice. Idempotent for the same user."""
    now = now or datetime.utcnow()
    cfg = get_config(db, lock=True)
    expire_stale_reservations(db, now)
    existing = open_membership_for_user(db, user.id)
    if existing is not None:
        if existing.status == RESERVED and existing.source_deposit_id is None:
            return existing
        raise AlreadyMember("You already hold a Referral Pool seat or a pending purchase")
    if not cfg.is_open:
        raise PoolFull("The Referral Pool is closed")

    def build(seat: int) -> ReferralPoolMembership:
        return ReferralPoolMembership(
            user_id=user.id, status=RESERVED, seat_number=seat, entitlement_source=SOURCE_PAID,
            reserved_at=now, reservation_expires_at=now + timedelta(minutes=int(cfg.reservation_minutes)),
            assignment_eligible=True,
        )

    row = _take_seat(db, build)
    if row is None:
        raise PoolFull("The Referral Pool is full (maximum membership reached)")
    return row


def attach_deposit(db: Session, membership: ReferralPoolMembership, deposit_id: int) -> None:
    membership.source_deposit_id = int(deposit_id)
    db.flush()


def release_reservation(db: Session, membership: ReferralPoolMembership, note: str) -> None:
    if membership.status == RESERVED:
        membership.status = CANCELLED
        membership.ended_at = datetime.utcnow()
        membership.seat_number = None
        membership.notes = note
        db.flush()


def activate_from_deposit(db: Session, deposit, now: Optional[datetime] = None) -> ReferralPoolMembership:
    """Called once a $100 pool deposit is confirmed. Never exceeds capacity.

    If the reservation lapsed and no seat is left, the paid entry is parked as
    CAPACITY_REVIEW without a seat (capacity is never exceeded) for manual refund review.
    """
    now = now or datetime.utcnow()
    get_config(db, lock=True)
    row = db.query(ReferralPoolMembership).filter(ReferralPoolMembership.source_deposit_id == deposit.id).first()
    if row is not None and row.status in (ACTIVE, CAPACITY_REVIEW):
        return row
    if row is not None and row.status == RESERVED:
        row.status = ACTIVE
        row.joined_at = now
        row.reservation_expires_at = None
        db.flush()
        return row
    # Reservation missing or lapsed: try to take a fresh seat for the paid deposit.
    expire_stale_reservations(db, now)
    if row is not None:
        # The lapsed row keeps its history; the new seat carries the payment evidence.
        row.notes = f"Reservation lapsed before payment of deposit #{deposit.id} was confirmed"
        row.source_deposit_id = None
        db.flush()
    other = open_membership_for_user(db, deposit.user_id)
    if other is not None and other.status == ACTIVE:
        # Already a member (e.g. paid twice): keep the payment as evidence for review, no second seat.
        dup = ReferralPoolMembership(
            user_id=deposit.user_id, status=REVOKED, entitlement_source=SOURCE_PAID,
            source_deposit_id=deposit.id, ended_at=now, assignment_eligible=False,
            notes="Duplicate paid entry for an existing member; refund review required",
        )
        db.add(dup)
        db.flush()
        return dup
    if other is not None:
        release_reservation(db, other, "Superseded by confirmed payment")

    def build(seat: int) -> ReferralPoolMembership:
        return ReferralPoolMembership(
            user_id=deposit.user_id, status=ACTIVE, seat_number=seat, entitlement_source=SOURCE_PAID,
            source_deposit_id=deposit.id, joined_at=now, assignment_eligible=True,
        )

    new_row = _take_seat(db, build)
    if new_row is None:
        new_row = ReferralPoolMembership(
            user_id=deposit.user_id, status=CAPACITY_REVIEW, seat_number=None, entitlement_source=SOURCE_PAID,
            source_deposit_id=deposit.id, assignment_eligible=False,
            notes="Paid after reservation lapsed and the pool was full; manual refund review",
        )
        db.add(new_row)
        db.flush()
    return new_row


def mark_refunded(db: Session, deposit_id: int) -> Optional[ReferralPoolMembership]:
    row = db.query(ReferralPoolMembership).filter(ReferralPoolMembership.source_deposit_id == deposit_id).first()
    if row is not None and row.status not in (REFUNDED,):
        row.status = REFUNDED
        row.ended_at = datetime.utcnow()
        row.seat_number = None
        row.assignment_eligible = False
        db.flush()
    return row


def grant_legacy_seat(db: Session, *, user_id: int, deposit_id: int, run_id: str) -> Optional[ReferralPoolMembership]:
    """Migration path: free seat for a verified legacy $100 Founding payment. Idempotent."""
    existing = db.query(ReferralPoolMembership).filter(ReferralPoolMembership.source_deposit_id == deposit_id).first()
    if existing is not None:
        return None
    if open_membership_for_user(db, user_id) is not None:
        return None
    now = datetime.utcnow()

    def build(seat: int) -> ReferralPoolMembership:
        return ReferralPoolMembership(
            user_id=user_id, status=ACTIVE, seat_number=seat, entitlement_source=SOURCE_LEGACY,
            source_deposit_id=deposit_id, migration_run_id=run_id, joined_at=now, assignment_eligible=True,
            notes="Migrated from legacy $100 Founding membership; no new charge",
        )

    row = _take_seat(db, build)
    if row is None:
        raise PoolFull("Legacy migration would exceed Referral Pool capacity")
    return row


# ---------------------------------------------------------------- assignment

@dataclass(frozen=True)
class PoolPick:
    membership: ReferralPoolMembership
    candidate_count: int
    min_assignment_count: int
    method: str


def pick_pool_member(db: Session, *, exclude_user_id: int) -> Optional[PoolPick]:
    """Fair random: uniformly random among eligible members with the fewest assignments.

    Randomness comes from ``secrets`` (server-side, unpredictable); nothing is client-controlled.
    """
    base = (
        db.query(ReferralPoolMembership)
        .join(User, User.id == ReferralPoolMembership.user_id)
        .filter(
            ReferralPoolMembership.status == ACTIVE,
            ReferralPoolMembership.assignment_eligible == True,  # noqa: E712
            ReferralPoolMembership.user_id != exclude_user_id,
            User.is_active == True,  # noqa: E712
            or_(User.is_deleted == False, User.is_deleted.is_(None)),  # noqa: E712
        )
    )
    candidate_count = base.count()
    if candidate_count == 0:
        return None
    min_count = min(r.assignments_count for r in base.with_entities(ReferralPoolMembership.assignments_count).all())
    tier = base.filter(ReferralPoolMembership.assignments_count == min_count).order_by(ReferralPoolMembership.id).all()
    chosen = tier[secrets.randbelow(len(tier))]
    locked = (
        db.query(ReferralPoolMembership).filter(ReferralPoolMembership.id == chosen.id).with_for_update().one()
    )
    return PoolPick(membership=locked, candidate_count=candidate_count, min_assignment_count=min_count,
                    method=get_config(db).assignment_method)


def record_assignment(db: Session, *, referred_user_id: int, pick: PoolPick) -> ReferralPoolAssignment:
    now = datetime.utcnow()
    pick.membership.assignments_count = int(pick.membership.assignments_count or 0) + 1
    pick.membership.last_assigned_at = now
    row = ReferralPoolAssignment(
        referred_user_id=referred_user_id,
        pool_member_user_id=pick.membership.user_id,
        membership_id=pick.membership.id,
        method=pick.method,
        candidate_count=pick.candidate_count,
        min_assignment_count=pick.min_assignment_count,
        assigned_at=now,
    )
    db.add(row)
    db.flush()
    return row
