"""NEW_V2 business model API: Direct Affiliate summary, Referral Pool, MyHigh5 Leaders,
marketplace orders/disputes (member) and their admin controls."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.business_model import (
    BusinessModelVersion,
    LeadersAllocationLine,
    LeadersPeriod,
    MarketDispute,
    MarketOrder,
    MarketOrderEvent,
    ReferralPoolAssignment,
    ReferralPoolMembership,
    ReferralPoolMigrationRun,
    RevenuePolicy,
)
from app.models.user import User
from app.services import leaders_service, legacy_pool_migration, marketplace_service
from app.services import referral_pool_service as pool
from app.services.new_model_reference_data import (
    LEADERS_MAX_MEMBERS,
    LEADERS_POOL_RATE,
    MARKETPLACE_MARKUP_RATE,
    NEW_MODEL_VERSION,
    REFERRAL_POOL_PRICE,
)

router = APIRouter()
admin_router = APIRouter()


def _num(v: Any) -> float:
    return float(Decimal(str(v or 0)))


def _audit(db: Session, *, actor_id: int, table: str, record_id: int, action: str, new: dict) -> None:
    db.add(AuditTrail(table_name=table, record_id=int(record_id), action=action, old_values=None,
                      new_values={k: (str(v) if isinstance(v, (Decimal, datetime)) else v) for k, v in new.items()},
                      user_id=actor_id))


# ================================================================ public / member

@router.get("/business-model/summary")
def business_model_summary(db: Session = Depends(get_db)):
    """Public figures for the website copy (no personal data)."""
    version = db.query(BusinessModelVersion).filter(BusinessModelVersion.version == NEW_MODEL_VERSION).first()
    cfg = pool.get_config(db)
    return {
        "business_model_version": NEW_MODEL_VERSION if version else None,
        "effective_at": version.effective_at.isoformat() + "Z" if version else None,
        "direct_commission_rate": 0.20,
        "affiliate_levels": 1,
        "referral_pool": {
            "price_usd": _num(REFERRAL_POOL_PRICE),
            "capacity": int(cfg.capacity),
            "seats_in_use": pool.seats_in_use(db),
            "active_members": pool.active_members(db),
            "is_open": bool(cfg.is_open) and pool.seats_in_use(db) < int(cfg.capacity),
        },
        "leaders": {"pool_rate": _num(LEADERS_POOL_RATE), "max_members": LEADERS_MAX_MEMBERS},
        "marketplace": {"markup_rate": _num(MARKETPLACE_MARKUP_RATE), "enabled": bool(settings.MARKETPLACE_ENABLED)},
    }


@router.get("/referral-pool/me")
def my_referral_pool(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(ReferralPoolMembership)
        .filter(ReferralPoolMembership.user_id == current_user.id)
        .order_by(ReferralPoolMembership.id.desc())
        .all()
    )
    current = next((r for r in rows if r.status in pool.SEAT_STATUSES), None)
    return {
        "membership": None if current is None else {
            "status": current.status,
            "entitlement_source": current.entitlement_source,
            "joined_at": current.joined_at.isoformat() + "Z" if current.joined_at else None,
            "reservation_expires_at": current.reservation_expires_at.isoformat() + "Z" if current.reservation_expires_at else None,
            "assignments_received": int(current.assignments_count or 0),
        },
        "assigned_referrals": db.query(func.count(ReferralPoolAssignment.id))
        .filter(ReferralPoolAssignment.pool_member_user_id == current_user.id).scalar(),
        "history": [{"status": r.status, "source": r.entitlement_source, "created_at": r.created_at.isoformat() + "Z"} for r in rows],
    }


@router.get("/leaders/me")
def my_leaders_rewards(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (
        db.query(LeadersAllocationLine, LeadersPeriod)
        .join(LeadersPeriod, LeadersPeriod.id == LeadersAllocationLine.period_id)
        .filter(LeadersAllocationLine.user_id == current_user.id, LeadersPeriod.status == "POSTED")
        .order_by(LeadersPeriod.period_year.desc(), LeadersPeriod.period_month.desc())
        .all()
    )
    now = datetime.utcnow()
    start, end = leaders_service.month_bounds(now.year, now.month)
    month_direct = (
        db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0))
        .filter(
            AffiliateCommission.user_id == current_user.id,
            AffiliateCommission.business_model_version == NEW_MODEL_VERSION,
            AffiliateCommission.level == 1,
            AffiliateCommission.status != CommissionStatus.CANCELLED,
            AffiliateCommission.transaction_date >= start,
            AffiliateCommission.transaction_date < end,
        ).scalar()
    )
    return {
        "current_month_direct_commission": _num(month_direct),
        "rewards": [
            {"period": f"{p.period_year:04d}-{p.period_month:02d}", "rank": l.rank,
             "direct_commission": _num(l.direct_commission_amount), "ratio": _num(l.ratio),
             "reward": _num(l.reward_amount), "payout_status": l.payout_status}
            for l, p in rows
        ],
    }


@router.get("/leaders/periods")
def posted_leaders_periods(db: Session = Depends(get_db)):
    rows = db.query(LeadersPeriod).filter(LeadersPeriod.status == "POSTED").order_by(
        LeadersPeriod.period_year.desc(), LeadersPeriod.period_month.desc()).limit(24).all()
    return [{"period": f"{p.period_year:04d}-{p.period_month:02d}", "eligible_company_revenue": _num(p.eligible_company_revenue),
             "pool_amount": _num(p.pool_amount), "qualifying_members": p.qualifying_count} for p in rows]


# ---------------------------------------------------------------- marketplace (member)

class OrderCreate(BaseModel):
    item_type: Literal["digital_product", "club_subscription"]
    item_id: int = Field(gt=0)


class DisputeCreate(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


def _require_marketplace() -> None:
    if not settings.MARKETPLACE_ENABLED:
        raise HTTPException(status_code=503, detail="The marketplace is not open yet (no authorised custodian configured)")


def _order_for(db: Session, order_id: int, user: User) -> MarketOrder:
    order = db.query(MarketOrder).filter(MarketOrder.id == order_id).with_for_update().first()
    if order is None or user.id not in (order.buyer_user_id, order.seller_user_id):
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def _order_out(db: Session, o: MarketOrder) -> dict:
    events = db.query(MarketOrderEvent).filter(MarketOrderEvent.order_id == o.id).order_by(MarketOrderEvent.id).all()
    return {
        "id": o.id, "state": o.state, "item_type": o.item_type, "item_id": o.item_id,
        "seller_base_amount": _num(o.seller_base_amount), "markup_amount": _num(o.markup_amount),
        "buyer_total_amount": _num(o.buyer_total_amount), "custodian": o.custodian_provider,
        "events": [{"from": e.from_state, "to": e.to_state, "by": e.actor_role, "at": e.created_at.isoformat() + "Z", "note": e.note}
                   for e in events],
    }


def _run(db: Session, fn):
    try:
        result = fn()
        db.commit()
        return result
    except (marketplace_service.MarketplaceError, leaders_service.LeadersError, pool.ReferralPoolError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/marketplace/orders", status_code=status.HTTP_201_CREATED)
def create_market_order(body: OrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    order = _run(db, lambda: marketplace_service.create_order(db, buyer_user_id=current_user.id,
                                                              item_type=body.item_type, item_id=body.item_id))
    return _order_out(db, order)


@router.get("/marketplace/orders")
def my_market_orders(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.query(MarketOrder).filter((MarketOrder.buyer_user_id == current_user.id) | (MarketOrder.seller_user_id == current_user.id)) \
        .order_by(MarketOrder.id.desc()).limit(100).all()
    return [_order_out(db, o) for o in rows]


@router.post("/marketplace/orders/{order_id}/dispute", status_code=status.HTTP_201_CREATED)
def dispute_market_order(order_id: int, body: DisputeCreate, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    _require_marketplace()
    order = _order_for(db, order_id, current_user)
    _run(db, lambda: marketplace_service.open_dispute(db, order, user_id=current_user.id, reason=body.reason))
    return _order_out(db, order)


@router.post("/marketplace/orders/{order_id}/{action}")
def market_order_action(order_id: int, action: Literal["fulfill", "confirm", "cancel"],
                        db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    order = _order_for(db, order_id, current_user)
    fn = {
        "fulfill": lambda: marketplace_service.mark_fulfilled(db, order, seller_user_id=current_user.id),
        "confirm": lambda: marketplace_service.confirm_receipt(db, order, buyer_user_id=current_user.id),
        "cancel": lambda: marketplace_service.cancel_unpaid(db, order, actor_user_id=current_user.id),
    }[action]
    try:
        _run(db, fn)
    except marketplace_service.CustodianNotConfigured as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _order_out(db, order)


# ================================================================ admin

@admin_router.get("/overview")
def admin_overview(db: Session = Depends(get_db)):
    version = db.query(BusinessModelVersion).filter(BusinessModelVersion.version == NEW_MODEL_VERSION).first()
    cfg = pool.get_config(db)
    by_status = dict(db.query(ReferralPoolMembership.status, func.count(ReferralPoolMembership.id))
                     .group_by(ReferralPoolMembership.status).all())
    by_source = dict(db.query(ReferralPoolMembership.entitlement_source, func.count(ReferralPoolMembership.id))
                     .filter(ReferralPoolMembership.status == pool.ACTIVE).group_by(ReferralPoolMembership.entitlement_source).all())
    return {
        "version": NEW_MODEL_VERSION if version else None,
        "effective_at": version.effective_at.isoformat() + "Z" if version else None,
        "legacy_business_model_enabled": bool(settings.LEGACY_BUSINESS_MODEL_ENABLED),
        "referral_pool": {"capacity": int(cfg.capacity), "seats_in_use": pool.seats_in_use(db), "by_status": by_status,
                          "active_by_source": by_source, "assignments": db.query(func.count(ReferralPoolAssignment.id)).scalar(),
                          "assignment_method": cfg.assignment_method},
        "marketplace": marketplace_service.reconciliation(db) | {"enabled": bool(settings.MARKETPLACE_ENABLED)},
        "revenue_policies": [
            {"product_code": p.product_code, "category": p.revenue_category, "revenue_account": p.revenue_account_code,
             "provider_cost_rate": _num(p.provider_cost_rate), "commission_eligible": p.commission_eligible,
             "commission_rate": _num(p.commission_rate), "leaders_revenue_eligible": p.leaders_revenue_eligible,
             "is_active": p.is_active, "notes": p.notes}
            for p in db.query(RevenuePolicy).filter(RevenuePolicy.model_version == NEW_MODEL_VERSION).order_by(RevenuePolicy.product_code)
        ],
    }


class PolicyUpdate(BaseModel):
    commission_eligible: Optional[bool] = None
    leaders_revenue_eligible: Optional[bool] = None
    reason: str = Field(min_length=5, max_length=500)


@admin_router.patch("/revenue-policies/{product_code}")
def update_revenue_policy(product_code: str, body: PolicyUpdate, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Audited switch of the two provisional business decisions per product (applies to future events only)."""
    policy = db.query(RevenuePolicy).filter(RevenuePolicy.model_version == NEW_MODEL_VERSION,
                                            RevenuePolicy.product_code == product_code).with_for_update().first()
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    old = {"commission_eligible": policy.commission_eligible, "leaders_revenue_eligible": policy.leaders_revenue_eligible}
    if body.commission_eligible is not None:
        policy.commission_eligible = body.commission_eligible
    if body.leaders_revenue_eligible is not None:
        policy.leaders_revenue_eligible = body.leaders_revenue_eligible
    db.add(AuditTrail(table_name="revenue_policies", record_id=policy.id, action="POLICY_UPDATE", old_values=old,
                      new_values={"commission_eligible": policy.commission_eligible,
                                  "leaders_revenue_eligible": policy.leaders_revenue_eligible, "reason": body.reason},
                      user_id=current_user.id))
    db.commit()
    return {"product_code": product_code, "commission_eligible": policy.commission_eligible,
            "leaders_revenue_eligible": policy.leaders_revenue_eligible}


@admin_router.get("/referral-pool/members")
def admin_pool_members(status_filter: Optional[str] = Query(None, alias="status"), skip: int = Query(0, ge=0),
                       limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    q = db.query(ReferralPoolMembership, User.email, User.username).join(User, User.id == ReferralPoolMembership.user_id)
    if status_filter:
        q = q.filter(ReferralPoolMembership.status == status_filter)
    rows = q.order_by(ReferralPoolMembership.id.desc()).offset(skip).limit(limit).all()
    return [{"id": m.id, "user_id": m.user_id, "email": email, "username": username, "status": m.status,
             "seat_number": m.seat_number, "source": m.entitlement_source, "source_deposit_id": m.source_deposit_id,
             "migration_run_id": m.migration_run_id, "joined_at": m.joined_at.isoformat() + "Z" if m.joined_at else None,
             "assignments_count": m.assignments_count, "notes": m.notes} for m, email, username in rows]


@admin_router.get("/referral-pool/assignments")
def admin_pool_assignments(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(ReferralPoolAssignment).order_by(ReferralPoolAssignment.id.desc()).offset(skip).limit(limit).all()
    return [{"referred_user_id": a.referred_user_id, "pool_member_user_id": a.pool_member_user_id, "method": a.method,
             "candidate_count": a.candidate_count, "min_assignment_count": a.min_assignment_count,
             "assigned_at": a.assigned_at.isoformat() + "Z"} for a in rows]


@admin_router.get("/referral-pool/legacy-migration/preview")
def admin_legacy_migration_preview(db: Session = Depends(get_db)):
    """Read-only dry run: classification of every legacy Founding payment + manifest SHA-256."""
    built = legacy_pool_migration.build_manifest(db)
    db.rollback()
    return built


@admin_router.get("/referral-pool/legacy-migration/runs")
def admin_legacy_migration_runs(db: Session = Depends(get_db)):
    return [{"run_id": r.run_id, "manifest_sha256": r.manifest_sha256, "operator": r.operator, "inserted": r.inserted,
             "automatic_eligible": r.automatic_eligible, "manual_review": r.manual_review, "not_eligible": r.not_eligible,
             "created_at": r.created_at.isoformat() + "Z"}
            for r in db.query(ReferralPoolMigrationRun).order_by(ReferralPoolMigrationRun.id.desc()).all()]


class PeriodRequest(BaseModel):
    year: int = Field(ge=2026, le=2100)
    month: int = Field(ge=1, le=12)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class PayoutRequest(BaseModel):
    reference: str = Field(min_length=3, max_length=200)


def _period_out(db: Session, p: LeadersPeriod, with_lines: bool = False) -> dict:
    out = {"id": p.id, "period": f"{p.period_year:04d}-{p.period_month:02d}", "status": p.status,
           "revenue_definition": p.revenue_definition, "eligible_company_revenue": _num(p.eligible_company_revenue),
           "pool_rate": _num(p.pool_rate), "pool_amount": _num(p.pool_amount), "qualifying_count": p.qualifying_count,
           "total_qualifying_commission": _num(p.total_qualifying_commission), "allocated_amount": _num(p.allocated_amount),
           "snapshot_sha256": p.snapshot_sha256, "prepared_by": p.prepared_by_user_id, "approved_by": p.approved_by_user_id,
           "journal_entry_id": p.journal_entry_id, "reversal_journal_entry_id": p.reversal_journal_entry_id,
           "posted_at": p.posted_at.isoformat() + "Z" if p.posted_at else None, "notes": p.notes}
    if with_lines:
        out["lines"] = [{"id": l.id, "rank": l.rank, "user_id": l.user_id, "direct_commission": _num(l.direct_commission_amount),
                         "ratio": _num(l.ratio), "reward": _num(l.reward_amount), "payout_status": l.payout_status}
                        for l in db.query(LeadersAllocationLine).filter(LeadersAllocationLine.period_id == p.id)
                        .order_by(LeadersAllocationLine.rank).all()]
    return out


@admin_router.get("/leaders/preview")
def admin_leaders_preview(year: int = Query(..., ge=2026), month: int = Query(..., ge=1, le=12), db: Session = Depends(get_db)):
    data = leaders_service.preview(db, year, month)
    return {k: (_num(v) if isinstance(v, Decimal) else v) for k, v in data.items() if k != "lines"} | {
        "lines": [{k: (_num(v) if isinstance(v, Decimal) else v) for k, v in l.items()} for l in data["lines"][:500]]}


@admin_router.get("/leaders/periods")
def admin_leaders_periods(db: Session = Depends(get_db)):
    rows = db.query(LeadersPeriod).order_by(LeadersPeriod.id.desc()).limit(60).all()
    return [_period_out(db, p) for p in rows]


@admin_router.get("/leaders/periods/{period_id}")
def admin_leaders_period(period_id: int, db: Session = Depends(get_db)):
    p = db.query(LeadersPeriod).filter(LeadersPeriod.id == period_id).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Period not found")
    return _period_out(db, p, with_lines=True)


@admin_router.post("/leaders/prepare")
def admin_leaders_prepare(body: PeriodRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    def go():
        p = leaders_service.prepare(db, year=body.year, month=body.month, preparer_user_id=current_user.id)
        _audit(db, actor_id=current_user.id, table="leaders_periods", record_id=p.id, action="LEADERS_PREPARE",
               new={"period": f"{body.year}-{body.month:02d}", "pool": p.pool_amount, "sha256": p.snapshot_sha256})
        return p
    return _period_out(db, _run(db, go), with_lines=True)


@admin_router.post("/leaders/periods/{period_id}/reverse")
def admin_leaders_reverse(period_id: int, body: ReasonRequest, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    def go():
        p = leaders_service.reverse(db, period_id=period_id, reason=body.reason)
        _audit(db, actor_id=current_user.id, table="leaders_periods", record_id=p.id, action="LEADERS_REVERSE",
               new={"reason": body.reason, "reversal_journal_entry_id": p.reversal_journal_entry_id})
        return p
    return _period_out(db, _run(db, go))


@admin_router.post("/leaders/periods/{period_id}/{action}")
def admin_leaders_action(period_id: int, action: Literal["approve", "post"], db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    def go():
        p = (leaders_service.approve(db, period_id=period_id, approver_user_id=current_user.id) if action == "approve"
             else leaders_service.post(db, period_id=period_id))
        _audit(db, actor_id=current_user.id, table="leaders_periods", record_id=p.id, action=f"LEADERS_{action.upper()}",
               new={"status": p.status, "journal_entry_id": p.journal_entry_id})
        return p
    return _period_out(db, _run(db, go))


@admin_router.post("/leaders/lines/{line_id}/record-payout")
def admin_leaders_record_payout(line_id: int, body: PayoutRequest, db: Session = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    def go():
        line = leaders_service.record_external_payout(db, line_id=line_id, reference=body.reference)
        _audit(db, actor_id=current_user.id, table="leaders_allocation_lines", record_id=line.id, action="LEADERS_PAYOUT",
               new={"reference": body.reference, "amount": line.reward_amount})
        return line
    line = _run(db, go)
    return {"id": line.id, "payout_status": line.payout_status}


@admin_router.get("/marketplace/orders")
def admin_market_orders(state: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(MarketOrder)
    if state:
        q = q.filter(MarketOrder.state == state)
    out = []
    for o in q.order_by(MarketOrder.id.desc()).limit(200).all():
        row = _order_out(db, o)
        row["disputes"] = [{"id": d.id, "status": d.status, "reason": d.reason, "resolution": d.resolution_note}
                           for d in db.query(MarketDispute).filter(MarketDispute.order_id == o.id).all()]
        out.append(row)
    return out


class ResolveRequest(BaseModel):
    outcome: Literal["RELEASE", "REFUND"]
    note: str = Field(min_length=5, max_length=2000)


@admin_router.post("/marketplace/orders/{order_id}/resolve-dispute")
def admin_resolve_dispute(order_id: int, body: ResolveRequest, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    order = db.query(MarketOrder).filter(MarketOrder.id == order_id).with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    def go():
        d = marketplace_service.resolve_dispute(db, order, admin_user_id=current_user.id, outcome=body.outcome, note=body.note)
        _audit(db, actor_id=current_user.id, table="market_disputes", record_id=d.id, action="DISPUTE_RESOLVE",
               new={"outcome": body.outcome, "note": body.note})
        return d
    try:
        _run(db, go)
    except marketplace_service.CustodianNotConfigured as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _order_out(db, order)


@admin_router.get("/marketplace/reconciliation")
def admin_market_reconciliation(db: Session = Depends(get_db)):
    return marketplace_service.reconciliation(db)
