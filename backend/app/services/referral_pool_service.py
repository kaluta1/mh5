"""MyHigh5 Referral Pool: RETIRED for all future activity (client decision, 2026-09-28).

No new $100 enrollment, no seat allocation, no legacy seat grants and no random assignment
of organic signups. Every writer that could create one of those raises ``ReferralPoolRetired``.

What remains is history: the read helpers (seats, members, membership lookup) and the
state-closing writers for rows that already exist (releasing a stale reservation when its
invoice expires, fails or is paid after retirement; marking a membership refunded after a
provider refund). Those never create a seat, a payment, revenue or a commission. Historical
memberships, assignments, payments and journals are never deleted or rewritten here.

Capacity was enforced by the database (unique seat_number over seat-holding statuses); that
constraint stays in place and still protects the historical rows.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.business_model import ReferralPoolConfig, ReferralPoolMembership

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

RETIRED_MESSAGE = (
    "The MyHigh5 Referral Pool has been retired. New enrollment and referral assignment are no longer available."
)


class ReferralPoolError(ValueError):
    pass


class ReferralPoolRetired(ReferralPoolError):
    """Raised by every retired writer. Historical records are kept unchanged."""

    def __init__(self, message: str = RETIRED_MESSAGE):
        super().__init__(message)


# ---------------------------------------------------------------- history reads

def get_config(db: Session) -> ReferralPoolConfig:
    cfg = db.query(ReferralPoolConfig).order_by(ReferralPoolConfig.id.asc()).first()
    if cfg is None:
        raise ReferralPoolError("Referral Pool is not configured")
    return cfg


def seats_in_use(db: Session) -> int:
    """Numbered seats still held by historical rows (unexpired reservations + active members)."""
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


# ---------------------------------------------------------------- state-closing writers (existing rows only)

def release_reservation(db: Session, membership: ReferralPoolMembership, note: str) -> None:
    """Close a historical RESERVED row (its invoice expired, failed or was paid after retirement)."""
    if membership.status == RESERVED:
        membership.status = CANCELLED
        membership.ended_at = datetime.utcnow()
        membership.seat_number = None
        membership.notes = note
        db.flush()


def release_reservation_for_deposit(db: Session, deposit_id: int, note: str) -> Optional[ReferralPoolMembership]:
    row = db.query(ReferralPoolMembership).filter(ReferralPoolMembership.source_deposit_id == deposit_id).first()
    if row is not None:
        release_reservation(db, row, note)
    return row


def mark_refunded(db: Session, deposit_id: int) -> Optional[ReferralPoolMembership]:
    """A provider refund of a historical pool deposit: the membership record reflects it."""
    row = db.query(ReferralPoolMembership).filter(ReferralPoolMembership.source_deposit_id == deposit_id).first()
    if row is not None and row.status not in (REFUNDED,):
        row.status = REFUNDED
        row.ended_at = datetime.utcnow()
        row.seat_number = None
        row.assignment_eligible = False
        db.flush()
    return row


# ---------------------------------------------------------------- retired writers

def reserve_for_purchase(db: Session, user, now: Optional[datetime] = None) -> ReferralPoolMembership:
    """Retired: no new $100 enrollment."""
    raise ReferralPoolRetired()


def activate_from_deposit(db: Session, deposit, now: Optional[datetime] = None) -> ReferralPoolMembership:
    """Retired: a pool payment confirmed after retirement never activates a seat."""
    raise ReferralPoolRetired()


def grant_legacy_seat(db: Session, *, user_id: int, deposit_id: int, run_id: str) -> Optional[ReferralPoolMembership]:
    """Retired: the one-time legacy Founding migration has run; no further seats are granted."""
    raise ReferralPoolRetired()


def pick_pool_member(db: Session, *, exclude_user_id: int):
    """Retired: organic signups are never assigned to a pool member."""
    raise ReferralPoolRetired()


def record_assignment(db: Session, *, referred_user_id: int, pick) -> None:
    """Retired: no new pool assignment rows."""
    raise ReferralPoolRetired()
