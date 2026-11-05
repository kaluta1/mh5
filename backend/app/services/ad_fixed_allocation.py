"""Fixed-price earned-revenue allocation (Daily Local / Daily City foundation; owner-approved policy 2026-11-05).

Both packages stay NOT READY / switched off (ad_packages). This module only turns an EARNED booked day into
placement-level revenue so contest-entry sharing and reporting work the day they are enabled:

  1. the earned amount of a booked day is the fee charged at settlement (booking.charged_amount);
  2. weights = valid, unreversed VIEWABLE impressions of that booking (same campaign, day and verified area as
     the settlement count), grouped by placement (slot kind x page type x contest entry; 0 = general inventory);
  3. the amount is split by weight with the largest-remainder method at 6 decimals, ties broken by the
     placement key, so the lines sum EXACTLY to the earned amount;
  4. inside a placement, each event receives its share (adv_impression_events.allocated_amount, same method),
     which is what contest-entry sharing reads: only contest-entry events can ever produce creator shares,
     general inventory never does, and the entry's original origin and rate are applied there unchanged;
  5. a reversal of the booking reverses its lines and clears the events' shares; invalid events found later
     cause a new allocation version over the remaining valid events. Lines are never deleted.
No minimum delivery or guaranteed impressions are invented here: the booking's own threshold decides EARNED.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.advertising_v2 import AdvBooking, AdvFixedAllocation, AdvImpressionEvent, AdvServeDecision

SIX = Decimal("0.000001")


def split(amount, weights: "OrderedDict") -> dict:
    """{key: share} summing exactly to `amount` (6 dp). Largest remainder; ties by key order. Weights > 0."""
    total_w = sum(int(w) for w in weights.values())
    amount = Decimal(str(amount)).quantize(SIX)
    if total_w <= 0 or amount <= 0:
        return {k: Decimal("0") for k in weights}
    shares, remainders = {}, []
    for key, w in weights.items():
        exact = amount * Decimal(int(w)) / Decimal(total_w)
        base = exact.quantize(SIX, rounding=ROUND_DOWN)
        shares[key] = base
        remainders.append((exact - base, key))
    left = int(((amount - sum(shares.values())) / SIX).to_integral_value())
    order = sorted(remainders, key=lambda r: (-r[0], list(weights).index(r[1])))
    for _, key in order[:left]:
        shares[key] += SIX
    return shares


def _valid_events(db: Session, booking: AdvBooking) -> list:
    q = (db.query(AdvImpressionEvent, AdvServeDecision.slot_kind, AdvServeDecision.page_type)
         .join(AdvServeDecision, AdvServeDecision.id == AdvImpressionEvent.decision_id)
         .filter(AdvServeDecision.campaign_id == booking.campaign_id, AdvServeDecision.reserved_day == booking.day,
                 AdvImpressionEvent.event_type == "VIEWABLE", AdvImpressionEvent.validation_status == "VALID",
                 AdvImpressionEvent.reversed_at.is_(None)))
    if booking.scope == "CITY":
        q = q.filter(AdvServeDecision.viewer_city_id == booking.area_id)
    else:
        return []                          # no verified local areas exist: Daily Local can never allocate yet
    return q.order_by(AdvImpressionEvent.id.asc()).all()


def _active(db: Session, booking_id: int) -> list:
    return (db.query(AdvFixedAllocation).filter(AdvFixedAllocation.booking_id == booking_id,
                                                AdvFixedAllocation.status == "ACTIVE").all())


def reverse(db: Session, booking: AdvBooking, *, now: Optional[datetime] = None) -> int:
    """Reverse every ACTIVE line of the booking and clear the shares of its events (idempotent)."""
    now = now or datetime.utcnow()
    lines = _active(db, booking.id)
    for line in lines:
        line.status, line.reversed_at = "REVERSED", now
    decisions = db.query(AdvServeDecision.id).filter(AdvServeDecision.campaign_id == booking.campaign_id,
                                                     AdvServeDecision.reserved_day == booking.day)
    (db.query(AdvImpressionEvent).filter(AdvImpressionEvent.allocated_amount != 0,
                                         AdvImpressionEvent.decision_id.in_(decisions))
     .update({AdvImpressionEvent.allocated_amount: 0}, synchronize_session="fetch"))
    db.flush()
    return len(lines)


def allocate(db: Session, booking: AdvBooking, *, now: Optional[datetime] = None) -> list:
    """Allocate an EARNED booking (caller holds the booking lock). Re-running with unchanged delivery is a
    no-op; changed delivery (events reversed since) produces a new version. Returns the ACTIVE lines."""
    if booking.status != "EARNED" or Decimal(str(booking.charged_amount or 0)) <= 0:
        if _active(db, booking.id):
            reverse(db, booking, now=now)
        return []
    events = _valid_events(db, booking)
    groups: "OrderedDict" = OrderedDict()
    for e, slot_kind, page_type in events:
        key = (slot_kind, page_type, int(e.contestant_id or 0))
        groups.setdefault(key, []).append(e)
    groups = OrderedDict(sorted(groups.items()))
    weights = OrderedDict((k, len(v)) for k, v in groups.items())
    current = _active(db, booking.id)
    if current and {(l.slot_kind, l.page_type, l.contestant_key): l.weight for l in current} == dict(weights):
        return current
    version = int(db.query(func.coalesce(func.max(AdvFixedAllocation.version), 0))
                  .filter(AdvFixedAllocation.booking_id == booking.id).scalar() or 0) + 1
    if current:
        reverse(db, booking, now=now)
    if not weights:
        return []
    shares = split(booking.charged_amount, weights)
    lines = []
    for key, share in shares.items():
        slot_kind, page_type, contestant_key = key
        line = AdvFixedAllocation(booking_id=booking.id, version=version, campaign_id=booking.campaign_id,
                                  day=booking.day, slot_kind=slot_kind, page_type=page_type,
                                  contestant_key=contestant_key, weight=weights[key], amount=share, status="ACTIVE")
        db.add(line)
        lines.append(line)
        per_event = split(share, OrderedDict((e.id, 1) for e in groups[key]))
        for e in groups[key]:
            e.allocated_amount = per_event[e.id]
    db.flush()
    return lines


def check(db: Session, booking: AdvBooking) -> dict:
    """Reconciliation: an EARNED booking's ACTIVE lines and its events' shares each equal the earned amount;
    any other booking has neither."""
    earned = Decimal(str(booking.charged_amount or 0)).quantize(SIX) if booking.status == "EARNED" else Decimal("0")
    lines = sum((Decimal(str(l.amount)) for l in _active(db, booking.id)), Decimal("0")).quantize(SIX)
    decisions = db.query(AdvServeDecision.id).filter(AdvServeDecision.campaign_id == booking.campaign_id,
                                                     AdvServeDecision.reserved_day == booking.day)
    shares = Decimal(str(db.query(func.coalesce(func.sum(AdvImpressionEvent.allocated_amount), 0))
                         .filter(AdvImpressionEvent.decision_id.in_(decisions)).scalar() or 0)).quantize(SIX)
    return {"booking_id": booking.id, "earned": str(earned), "allocated": str(lines), "event_shares": str(shares),
            "ok": lines == shares == earned.quantize(SIX)}
