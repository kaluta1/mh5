"""Multi-Unit Referral Pool: owner-approved conversion of a historical single-seat membership into
ONE unit (P9 rules; P10 implementation). Nothing runs unless an operator calls it with the ids the
owner approved, record by record.

A converted unit is `source=HISTORICAL_CONVERSION`, `legacy_membership_id=<membership>`, no
purchase, $100.00 nominal. Its money was received and recognized under the old model, so the
conversion posts NO journal entry and NO commission, and `recognize_unit` never earns on it
(it only recognizes PAID units). Historical assignments and the membership row are not touched.

Idempotent and restart-safe: the database allows one unit per legacy membership
(uq_referral_pool_unit_legacy_membership); a repeat, or a concurrent run, returns the existing
unit. Lock order as everywhere: member row (NO KEY UPDATE) -> pool mutex.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.business_model import ReferralPoolMembership, ReferralPoolUnit
from app.models.user import User
from app.services import referral_pool_units as units

logger = logging.getLogger(__name__)

SOURCE = "HISTORICAL_CONVERSION"
AUDIT_ACTION = "REFERRAL_POOL_HISTORICAL_CONVERSION"
CONVERTIBLE_SOURCES = ("LEGACY_FOUNDING_MIGRATION", "PAID")
CONVERTIBLE_STATUSES = ("ACTIVE",)
CREATED, ALREADY_CONVERTED, WOULD_CREATE = "CREATED", "ALREADY_CONVERTED", "WOULD_CREATE"


class ConversionRefused(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ConversionResult:
    membership_id: int
    outcome: str
    unit_id: Optional[int]
    unit_status: Optional[str]
    user_id: Optional[int]


def _existing(db: Session, membership_id: int) -> Optional[ReferralPoolUnit]:
    return db.query(ReferralPoolUnit).filter(ReferralPoolUnit.legacy_membership_id == membership_id).first()


def _checked(db: Session, membership_id: int, approved: set) -> ReferralPoolMembership:
    if membership_id not in approved:
        raise ConversionRefused("NOT_APPROVED", f"Membership {membership_id} is not on the owner-approved list.")
    membership = db.get(ReferralPoolMembership, membership_id)
    if membership is None:
        raise ConversionRefused("NOT_FOUND", f"Membership {membership_id} does not exist.")
    if membership.status not in CONVERTIBLE_STATUSES:
        raise ConversionRefused("NOT_A_SEAT", f"Membership {membership_id} is {membership.status}, not an active seat.")
    if membership.entitlement_source not in CONVERTIBLE_SOURCES:
        raise ConversionRefused("SOURCE_NOT_CONVERTIBLE",
                                f"Membership {membership_id} has source {membership.entitlement_source}.")
    holder = db.get(User, membership.user_id)
    if holder is None or holder.is_deleted:
        raise ConversionRefused("HOLDER_MISSING", f"The holder of membership {membership_id} is missing or deleted.")
    return membership


def plan(db: Session, membership_ids: Iterable[int], *, approved: Iterable[int]) -> List[ConversionResult]:
    """Dry run: what a conversion would do. Reads only; refusals raise as they would for real."""
    approved_set = {int(i) for i in approved}
    out = []
    for membership_id in sorted({int(i) for i in membership_ids}):
        membership = _checked(db, membership_id, approved_set)
        existing = _existing(db, membership_id)
        if existing is not None:
            out.append(ConversionResult(membership_id, ALREADY_CONVERTED, existing.id, existing.status, existing.user_id))
            continue
        holder = db.get(User, membership.user_id)
        status = units.ACTIVE if units.member_eligibility(db, holder).eligible else units.SUSPENDED
        out.append(ConversionResult(membership_id, WOULD_CREATE, None, status, membership.user_id))
    return out


def convert(db: Session, membership_id: int, *, approved: Iterable[int], run_id: str,
            operator_id: Optional[int] = None, now: Optional[datetime] = None) -> ConversionResult:
    """Convert ONE approved membership into one unit and commit. A repeat changes nothing."""
    from app.models.accounting import AuditTrail

    now = now or datetime.utcnow()
    run_id = str(run_id or "").strip()[:64]
    if not run_id:
        raise ConversionRefused("RUN_ID_REQUIRED", "A conversion run id is required for the audit trail.")
    membership = _checked(db, int(membership_id), {int(i) for i in approved})
    existing = _existing(db, membership.id)
    if existing is not None:
        db.rollback()
        return ConversionResult(membership.id, ALREADY_CONVERTED, existing.id, existing.status, existing.user_id)

    holder = (db.query(User).filter(User.id == membership.user_id)
              .with_for_update(key_share=True).populate_existing().one())
    units.lock_pool(db)
    existing = _existing(db, membership.id)                       # re-check under the locks
    if existing is not None:
        db.rollback()
        return ConversionResult(membership.id, ALREADY_CONVERTED, existing.id, existing.status, existing.user_id)
    eligibility = units.member_eligibility(db, holder)
    unit = ReferralPoolUnit(user_id=holder.id, purchase_id=None, unit_index=None, source=SOURCE,
                            amount=units.UNIT_PRICE, currency="USD", legacy_membership_id=membership.id)
    if eligibility.eligible:
        unit.status, unit.activated_at = units.ACTIVE, now
    else:
        unit.status, unit.suspended_at = units.SUSPENDED, now
        unit.status_reason = f"{units.ELIGIBILITY}{eligibility.reason}"
    savepoint = db.begin_nested()
    try:
        db.add(unit)
        db.flush()
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        db.rollback()
        existing = _existing(db, membership.id)
        if existing is None:
            raise
        return ConversionResult(membership.id, ALREADY_CONVERTED, existing.id, existing.status, existing.user_id)
    db.add(AuditTrail(table_name="referral_pool_units", record_id=unit.id, action=AUDIT_ACTION, user_id=operator_id,
                      new_values={"legacy_membership_id": membership.id, "source_deposit_id": membership.source_deposit_id,
                                  "run_id": run_id, "unit_status": unit.status, "revenue": "0.00", "commission": "0.00"}))
    db.commit()
    logger.info("Historical membership %s converted into unit %s (%s), run %s", membership.id, unit.id, unit.status, run_id)
    return ConversionResult(membership.id, CREATED, unit.id, unit.status, unit.user_id)
