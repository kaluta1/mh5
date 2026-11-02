"""Referral Pool read-only reconciliation (Prompt 6): purchases, units, round slots, assignments, unit
commissions and the purchase ledger, against each other. Never writes; never repairs.

Every issue: type, record ids, expected, actual, suggested resolution, whether an automatic correction would
be safe (always False here: production data is never repaired by this report) and whether the owner must
approve a correction. A fingerprint of the main counts lets two runs be compared for unexpected changes.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.financial_integrity import money


def _issue(kind, expected, actual, suggestion, owner=True, **ids) -> dict:
    return {"type": kind, **ids, "expected": str(expected), "actual": str(actual), "suggestion": suggestion,
            "auto_fix_safe": False, "owner_approval": owner}


def report(db: Session, *, limit: int = 500) -> dict:
    from app.models.affiliate import AffiliateCommission, CommissionStatus
    from app.models.business_model import (ReferralPoolAssignment, ReferralPoolPurchase, ReferralPoolRoundSlot,
                                           ReferralPoolUnit)
    from app.models.payment import Deposit, DepositStatus
    from app.models.user import User
    from app.services import referral_pool_accounting as accounting
    from app.services.kyc_eligibility import is_approved

    issues: list = []
    purchases = db.query(ReferralPoolPurchase).order_by(ReferralPoolPurchase.id.asc()).all()
    units = db.query(ReferralPoolUnit).order_by(ReferralPoolUnit.id.asc()).all()
    units_by_purchase: dict = {}
    for u in units:
        units_by_purchase.setdefault(u.purchase_id, []).append(u)

    for p in purchases:
        dep = db.get(Deposit, p.deposit_id) if p.deposit_id else None
        mine = units_by_purchase.get(p.id, [])
        if dep is None:
            issues.append(_issue("MISSING_PURCHASE_REFERENCE", "a payment record", None,
                                 "Find the payment by hand; never create units without one", purchase_id=p.id))
            continue
        if int(dep.user_id) != int(p.user_id):
            issues.append(_issue("PURCHASE_OWNER_MISMATCH", p.user_id, dep.user_id, "Review ownership",
                                 purchase_id=p.id, deposit_id=dep.id))
        if p.status in ("PAID", "PARTIALLY_REFUNDED") and len(mine) != p.quantity:
            issues.append(_issue("UNIT_COUNT_MISMATCH", p.quantity, len(mine), "Review the purchase activation",
                                 purchase_id=p.id))
        if mine and dep.status != DepositStatus.VALIDATED and p.status not in ("REFUNDED",):
            issues.append(_issue("UNITS_WITHOUT_CONFIRMED_PAYMENT", "validated payment", dep.status.value,
                                 "Units must come from a confirmed payment only", purchase_id=p.id, deposit_id=dep.id))
        if money(p.total_amount) != money(Decimal(str(p.unit_price)) * p.quantity):
            issues.append(_issue("PURCHASE_AMOUNT_MISMATCH", money(Decimal(str(p.unit_price)) * p.quantity),
                                 money(p.total_amount), "Historical amount kept; review", purchase_id=p.id))
        if mine and dep.status == DepositStatus.VALIDATED:
            for problem in accounting.reconcile_purchase(db, p.id):
                issues.append(_issue("LEDGER_MISMATCH", problem[2] if len(problem) > 2 else "", problem[1],
                                     f"Account check {problem[0]} of the purchase ledger", purchase_id=p.id))

    holders_ok: dict = {}
    for u in units:
        if u.purchase_id is not None:
            p = next((x for x in purchases if x.id == u.purchase_id), None)
            if p is not None and int(p.user_id) != int(u.user_id):
                issues.append(_issue("UNIT_OWNER_MISMATCH", p.user_id, u.user_id, "Units are never reassigned "
                                     "without authorization; review", unit_id=u.id, purchase_id=p.id))
        if u.status == "ACTIVE":
            if u.source == "PAID" and u.revenue_recognition_id is None:
                issues.append(_issue("ACTIVE_UNIT_WITHOUT_REVENUE", "revenue recognition", None,
                                     "Review the unit's activation posting", unit_id=u.id))
            if u.user_id not in holders_ok:
                holders_ok[u.user_id] = is_approved(db, u.user_id)
            if not holders_ok[u.user_id]:
                issues.append(_issue("ACTIVE_UNIT_HOLDER_NOT_KYC_APPROVED", "KYC approved", "not approved",
                                     "The eligibility worker should suspend it; review", owner=False,
                                     unit_id=u.id, user_id=u.user_id))
        commissions = (db.query(func.count(AffiliateCommission.id))
                       .filter(AffiliateCommission.source_type == accounting.SOURCE_UNIT,
                               AffiliateCommission.source_id == u.id,
                               AffiliateCommission.status != CommissionStatus.CANCELLED).scalar())
        if int(commissions or 0) > 1:
            issues.append(_issue("DUPLICATE_UNIT_COMMISSION", 1, commissions, "Cancel the duplicate after review",
                                 unit_id=u.id))

    unit_ids = {u.id: u for u in units}
    assignments = db.query(ReferralPoolAssignment).order_by(ReferralPoolAssignment.id.asc()).all()
    for a in assignments:
        if a.referred_user_id == a.pool_member_user_id:
            issues.append(_issue("SELF_ASSIGNMENT", "another member", a.referred_user_id, "Review", assignment_id=a.id))
        referred = db.get(User, a.referred_user_id)
        if referred is None or referred.is_deleted:
            issues.append(_issue("INVALID_MEMBER_REFERENCE", "an existing member", a.referred_user_id,
                                 "Keep the history; review", owner=False, assignment_id=a.id))
        if a.unit_id is not None:
            unit = unit_ids.get(a.unit_id)
            slot = db.get(ReferralPoolRoundSlot, a.slot_id) if a.slot_id else None
            if unit is None:
                issues.append(_issue("ORPHAN_ASSIGNMENT", "an existing unit", a.unit_id, "Review", assignment_id=a.id))
            elif int(unit.user_id) != int(a.pool_member_user_id):
                issues.append(_issue("ASSIGNMENT_HOLDER_MISMATCH", unit.user_id, a.pool_member_user_id, "Review",
                                     assignment_id=a.id, unit_id=unit.id))
            if slot is None or slot.status != "FILLED" or slot.unit_id != a.unit_id:
                issues.append(_issue("ASSIGNMENT_SLOT_MISMATCH", "a FILLED slot of the same unit",
                                     None if slot is None else f"{slot.status} unit {slot.unit_id}", "Review",
                                     assignment_id=a.id))
        if referred is not None and referred.sponsor_id != a.pool_member_user_id:
            issues.append(_issue("ASSIGNED_SPONSOR_CHANGED", a.pool_member_user_id, referred.sponsor_id,
                                 "Informational: the member's sponsor is no longer the pool holder", owner=False,
                                 assignment_id=a.id))
    filled = db.query(ReferralPoolRoundSlot).filter(ReferralPoolRoundSlot.status == "FILLED").all()
    assigned_slots = {a.slot_id for a in assignments if a.slot_id}
    for slot in filled:
        if slot.id not in assigned_slots:
            issues.append(_issue("FILLED_SLOT_WITHOUT_ASSIGNMENT", "an assignment", None, "Review", slot_id=slot.id))

    counts = {
        "purchases_by_status": _count(db, ReferralPoolPurchase.status),
        "units_by_status": _count(db, ReferralPoolUnit.status),
        "units_by_source": _count(db, ReferralPoolUnit.source),
        "holders_with_active_units": int(db.query(func.count(func.distinct(ReferralPoolUnit.user_id)))
                                         .filter(ReferralPoolUnit.status == "ACTIVE").scalar() or 0),
        "assignments": len(assignments),
        "assignments_with_unit": sum(1 for a in assignments if a.unit_id is not None),
        "slots_by_status": _count(db, ReferralPoolRoundSlot.status),
    }
    fingerprint = hashlib.sha256(json.dumps(counts, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return {"read_only": True, "counts": counts, "fingerprint": fingerprint, "issues": issues[:limit],
            "issue_count": len(issues), "ok": not issues}


def _count(db: Session, column) -> dict:
    return {str(k): int(v) for k, v in db.query(column, func.count()).group_by(column).all()}
