"""Multi-Unit Referral Pool: member and administrator endpoints (P7).

Checkout itself is POST /payments/create with product_code "referral_pool_entry" and a quantity:
the one provider-independent payment path (idempotency key, gateway choice, provider call).

Public:  GET /referral-pool/status (launch state only).
Member:  GET /referral-pool/units/eligibility, /referral-pool/units/purchases[/{id}],
         /referral-pool/units/dashboard, /referral-pool/units/assignments (own data only).
Admin:   GET /admin/referral-pool/settings (feature state, read only), PUT /admin/referral-pool/limits,
         GET/POST /admin/referral-pool/refunds, POST /admin/referral-pool/refunds/{id}/decision,
         P8 read views (overview, rounds, slots, queue, purchases, units, reconciliation, events,
         risk reviews, invalid sponsors, audit) and POST /admin/referral-pool/risk-reviews/{id}/decision.
Every list is paginated (at most 100 rows a page). Financial views need a finance permission,
operations views (rounds, slots, allocations, queue, events) a finance permission or
manage_kyc_settings, and anti-abuse cases and invalid sponsors manage_kyc_settings: checked here,
never only in the browser. The overview (counts, no money without finance) is open to every admin.
No endpoint switches sales, allocation or the worker on: activation is a separate, later decision.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import deps
from app.models.business_model import (
    ReferralPoolAssignment, ReferralPoolConfig, ReferralPoolEvent, ReferralPoolPending, ReferralPoolPurchase,
    ReferralPoolRefundRecord, ReferralPoolRiskReview, ReferralPoolRound, ReferralPoolRoundSlot, ReferralPoolUnit,
)
from app.models.payment import Deposit
from app.models.user import User
from app.services import referral_pool_units as units

router = APIRouter()
admin_router = APIRouter()


def _num(value) -> str:
    return f"{Decimal(str(value)):.2f}"


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


Page = Annotated[int, Query(ge=1, le=100000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def _paged(query, page: int, page_size: int, view) -> dict:
    """One page of a query: never more than `page_size` rows in memory."""
    total = query.order_by(None).count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [view(r) for r in rows], "page": page, "page_size": page_size, "total": total}


def _config(db: Session) -> Optional[ReferralPoolConfig]:
    return db.query(ReferralPoolConfig).order_by(ReferralPoolConfig.id.asc()).first()


def _status_counts(db: Session, column, *filters) -> dict:
    return {status: n for status, n in db.query(column, func.count()).filter(*filters).group_by(column)}


# Where a refunded unit's evidence came from. Only a provider's signed callback is verification;
# an administrator-entered reference stays a claim, even after a second administrator approved it.
PROVIDER_EVENT, MANUAL_CLAIM, DEPOSIT_REVERSAL, UNCLASSIFIED = (
    "PROVIDER_EVENT", "ADMIN_ENTERED_CLAIM", "DEPOSIT_REVERSAL", "UNCLASSIFIED")


def refund_evidence(reference: Optional[str], manual_references: Iterable[str] = ()) -> dict:
    ref = reference or ""
    if ref in set(manual_references):          # an administrator's record always reads as a claim, whatever its text
        return {"evidence": MANUAL_CLAIM, "provider_verified": False,
                "label": "Administrator-entered claim, approved by a second administrator (not provider-verified)"}
    if ref.startswith(("provider-refund:", "soncopay-refund:")):
        return {"evidence": PROVIDER_EVENT, "provider_verified": True,
                "label": "Confirmed by the payment provider's signed refund notification"}
    if ref.startswith("deposit-refund:"):
        return {"evidence": DEPOSIT_REVERSAL, "provider_verified": False,
                "label": "Recorded by the full reversal of the payment"}
    return {"evidence": UNCLASSIFIED, "provider_verified": False, "label": "No evidence classification"}


def _manual_references(db: Session, references: Iterable[Optional[str]]) -> set:
    refs = {r for r in references if r}
    if not refs:
        return set()
    return {r for (r,) in db.query(ReferralPoolRefundRecord.provider_reference).filter(
        ReferralPoolRefundRecord.provider_reference.in_(refs), ReferralPoolRefundRecord.status == "APPROVED")}


# ---------------------------------------------------------------- public

@router.get("/referral-pool/status")
def public_status(db: Session = Depends(deps.get_db)):
    """Launch state for the public page: whether purchases and allocation are running. Nothing personal."""
    from app.services.referral_pool_integration import worker_enabled

    cfg = _config(db)
    return {
        "sales_enabled": bool(cfg and cfg.multiunit_sales_enabled),
        "allocation_enabled": bool(cfg and cfg.allocation_enabled and worker_enabled()),
        "unit_price": _num(units.UNIT_PRICE),
        "currency": "USD",
    }


# ---------------------------------------------------------------- member

@router.get("/referral-pool/units/eligibility")
def unit_eligibility(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_user)):
    """What the purchase card shows: whether sales are open, the unit price, whether THIS member
    may buy now (and why not), and the limits that apply (null = unlimited)."""
    cfg = db.query(ReferralPoolConfig).order_by(ReferralPoolConfig.id.asc()).first()
    eligibility = units.member_eligibility(db, current_user)
    return {
        "sales_enabled": bool(cfg and cfg.multiunit_sales_enabled),
        "unit_price": _num(units.UNIT_PRICE),
        "currency": "USD",
        "eligible": eligibility.eligible,
        "reason": None if eligibility.eligible else eligibility.reason,
        "max_units_per_purchase": cfg.max_units_per_purchase if cfg else None,
        "max_units_per_member": cfg.max_units_per_member if cfg else None,
        "units_reserved": units._reserved_units(db, current_user.id),
        "kyc_approved": _kyc_approved(db, current_user),
    }


def _kyc_approved(db: Session, user: User) -> bool:
    """Shown on its own because eligibility reports only the first reason it fails. Fails closed."""
    from app.crud import crud_kyc
    from app.models.kyc import KYCStatus

    try:
        verification = crud_kyc.kyc_verification.get_by_user(db, user_id=user.id)
        return bool(verification is not None and verification.status == KYCStatus.APPROVED and user.identity_verified)
    except Exception:  # noqa: BLE001 - never report approval on an error
        return False


def _purchase_view(db: Session, purchase: ReferralPoolPurchase) -> dict:
    deposit = db.get(Deposit, purchase.deposit_id)
    counts = _status_counts(db, ReferralPoolUnit.status, ReferralPoolUnit.purchase_id == purchase.id)
    in_review = db.query(func.coalesce(func.sum(ReferralPoolRefundRecord.quantity), 0)).filter(
        ReferralPoolRefundRecord.purchase_id == purchase.id, ReferralPoolRefundRecord.status == "PROPOSED").scalar()
    return {
        "id": purchase.id, "quantity": purchase.quantity, "unit_price": _num(purchase.unit_price),
        "total_amount": _num(purchase.total_amount), "currency": purchase.currency, "status": purchase.status,
        "refunded_quantity": purchase.refunded_quantity,
        "payment": {"deposit_id": purchase.deposit_id,
                    "status": getattr(deposit.status, "value", deposit.status) if deposit else None},
        "units": counts,
        "refund": {"refunded_units": int(counts.get(units.REFUNDED, 0)), "in_review_units": int(in_review or 0)},
        "created_at": purchase.created_at.isoformat() if purchase.created_at else None,
        "paid_at": purchase.paid_at.isoformat() if purchase.paid_at else None,
    }


@router.get("/referral-pool/units/purchases")
def my_purchases(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_user),
                 page: Page = 1, page_size: PageSize = 20):
    query = (db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.user_id == current_user.id)
             .order_by(ReferralPoolPurchase.id.desc()))
    active = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.user_id == current_user.id,
                                               ReferralPoolUnit.status == units.ACTIVE).count()
    paged = _paged(query, page, page_size, lambda p: _purchase_view(db, p))
    return {"active_units": active, "purchases": paged["items"], "page": page, "page_size": page_size,
            "total": paged["total"]}


@router.get("/referral-pool/units/purchases/{purchase_id}")
def my_purchase(purchase_id: int, db: Session = Depends(deps.get_db),
                current_user: User = Depends(deps.get_current_user)):
    purchase = db.get(ReferralPoolPurchase, purchase_id)
    if purchase is None or purchase.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Purchase not found")   # another member's: not found
    return _purchase_view(db, purchase)


def _open_round(db: Session) -> Optional[ReferralPoolRound]:
    return db.query(ReferralPoolRound).filter(ReferralPoolRound.status == "OPEN").first()


def _round_view(r: ReferralPoolRound) -> dict:
    return {"id": r.id, "round_number": r.round_number, "status": r.status, "method": r.method,
            "opened_at": _iso(r.opened_at), "completed_at": _iso(r.completed_at), "closed_reason": r.closed_reason,
            "total_slots": r.total_slots, "filled_slots": r.filled_slots, "void_slots": r.void_slots,
            "remaining_slots": max(r.total_slots - r.filled_slots - r.void_slots, 0)}


def _units_waiting_for_next_round(db: Session, round_: Optional[ReferralPoolRound], user_id: Optional[int] = None) -> int:
    """ACTIVE units without a slot in the open round: they take part from the next round."""
    query = db.query(func.count(ReferralPoolUnit.id)).filter(ReferralPoolUnit.status == units.ACTIVE)
    if user_id is not None:
        query = query.filter(ReferralPoolUnit.user_id == user_id)
    if round_ is not None:
        query = query.filter(~ReferralPoolUnit.id.in_(
            db.query(ReferralPoolRoundSlot.unit_id).filter(ReferralPoolRoundSlot.round_id == round_.id)))
    return int(query.scalar() or 0)


@router.get("/referral-pool/units/dashboard")
def my_dashboard(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_user)):
    """The member's own Referral Pool totals. Slots are allocation opportunities, never promised
    referrals: only `assignments` are referrals actually received."""
    from app.models.payment import DepositStatus
    from app.services.referral_pool_integration import worker_enabled

    uid = current_user.id
    cfg = _config(db)
    unit_counts = _status_counts(db, ReferralPoolUnit.status, ReferralPoolUnit.user_id == uid)
    paid = (units.P_PAID, units.P_PARTIAL, units.P_REFUNDED)
    paid_total = db.query(func.coalesce(func.sum(ReferralPoolPurchase.total_amount), 0)).filter(
        ReferralPoolPurchase.user_id == uid, ReferralPoolPurchase.status.in_(paid)).scalar()
    refunded_total = db.query(func.coalesce(func.sum(ReferralPoolUnit.amount), 0)).filter(
        ReferralPoolUnit.user_id == uid, ReferralPoolUnit.status == units.REFUNDED).scalar()
    pending = (db.query(func.count(ReferralPoolPurchase.id), func.coalesce(func.sum(ReferralPoolPurchase.quantity), 0))
               .join(Deposit, Deposit.id == ReferralPoolPurchase.deposit_id)
               .filter(ReferralPoolPurchase.user_id == uid, ReferralPoolPurchase.status == units.P_PENDING,
                       Deposit.status.in_((DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID))).one())
    round_ = _open_round(db)
    my_slots = (_status_counts(db, ReferralPoolRoundSlot.status, ReferralPoolRoundSlot.round_id == round_.id,
                               ReferralPoolRoundSlot.member_user_id == uid) if round_ else {})
    mine = db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.pool_member_user_id == uid)
    recent = (db.query(ReferralPoolAssignment, ReferralPoolRound.round_number)
              .outerjoin(ReferralPoolRound, ReferralPoolRound.id == ReferralPoolAssignment.round_id)
              .filter(ReferralPoolAssignment.pool_member_user_id == uid)
              .order_by(ReferralPoolAssignment.assigned_at.desc(), ReferralPoolAssignment.id.desc()).limit(5).all())
    own_queue = db.query(ReferralPoolPending).filter(ReferralPoolPending.referred_user_id == uid).first()
    return {
        "sales_enabled": bool(cfg and cfg.multiunit_sales_enabled),
        "allocation_enabled": bool(cfg and cfg.allocation_enabled and worker_enabled()),
        "units": {
            "purchased": sum(unit_counts.values()),
            "active": int(unit_counts.get(units.ACTIVE, 0)),
            "suspended": int(unit_counts.get(units.SUSPENDED, 0)),
            "refunded": int(unit_counts.get(units.REFUNDED, 0)),
            "revoked": int(unit_counts.get(units.REVOKED, 0)),
            "pending": int(unit_counts.get(units.PENDING, 0)),
            "waiting_for_next_round": _units_waiting_for_next_round(db, round_, uid),
        },
        "pending_purchases": {"count": int(pending[0] or 0), "units": int(pending[1] or 0)},
        "amounts": {"paid": _num(paid_total), "refunded": _num(refunded_total),
                    "net_spent": _num(Decimal(str(paid_total)) - Decimal(str(refunded_total))), "currency": "USD"},
        "current_round": _round_view(round_) if round_ else None,
        "my_slots": {"open": int(my_slots.get("OPEN", 0)), "filled": int(my_slots.get("FILLED", 0)),
                     "void": int(my_slots.get("VOID", 0))},
        "assignments": {"round_based": mine.filter(ReferralPoolAssignment.slot_id.isnot(None)).count(),
                        "historical": mine.filter(ReferralPoolAssignment.slot_id.is_(None)).count()},
        "recent_assignments": [_assignment_view(a, number) for a, number in recent],
        "waiting_referrals": db.query(ReferralPoolPending).filter(ReferralPoolPending.status == "WAITING").count(),
        "my_queue_entry": None if own_queue is None else {
            "status": own_queue.status, "enqueued_at": _iso(own_queue.enqueued_at),
            "resolved_at": _iso(own_queue.resolved_at), "resolution_reason": own_queue.resolution_reason},
    }


def _assignment_view(a: ReferralPoolAssignment, round_number: Optional[int]) -> dict:
    """What a member sees of a referral assigned to them: when and through which round (no
    personal data of the referred member)."""
    return {"id": a.id, "assigned_at": _iso(a.assigned_at), "round_number": round_number,
            "kind": "ROUND" if a.slot_id is not None else "HISTORICAL", "method": a.method}


@router.get("/referral-pool/units/assignments")
def my_assignments(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_user),
                   page: Page = 1, page_size: PageSize = 20):
    query = (db.query(ReferralPoolAssignment, ReferralPoolRound.round_number)
             .outerjoin(ReferralPoolRound, ReferralPoolRound.id == ReferralPoolAssignment.round_id)
             .filter(ReferralPoolAssignment.pool_member_user_id == current_user.id)
             .order_by(ReferralPoolAssignment.assigned_at.desc(), ReferralPoolAssignment.id.desc()))
    return _paged(query, page, page_size, lambda row: _assignment_view(row[0], row[1]))


# ---------------------------------------------------------------- administrators

def _finance() -> tuple:
    from app.services import payment_config

    return (payment_config.PERMISSION_PROCESS, payment_config.PERMISSION_MANAGE)


def _kyc() -> tuple:
    from app.services import admin_security

    return (admin_security.PERMISSION_MANAGE_KYC,)


def _operations() -> tuple:
    """Pool operations data (rounds, slots, allocations, queue, events): finance or KYC administrators."""
    return _finance() + _kyc()


def _has_any(user: User, permissions: Iterable[str]) -> bool:
    from app.services import payment_config

    return any(payment_config.has_permission(user, p) for p in permissions)


def _require_any(user: User, permissions: Iterable[str], what: str) -> None:
    permissions = tuple(permissions)
    if not _has_any(user, permissions):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN", "message": f"The {' or '.join(permissions)} permission is required to view {what}."})


def _usernames(db: Session, ids: Iterable[Optional[int]]) -> dict:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {i: name for i, name in db.query(User.id, User.username).filter(User.id.in_(wanted))}

@admin_router.get("/settings")
def pool_settings(db: Session = Depends(deps.get_db)):
    """Feature state and limits, read only."""
    from app.services.referral_pool_integration import worker_enabled

    cfg = db.query(ReferralPoolConfig).order_by(ReferralPoolConfig.id.asc()).first()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Referral Pool is not configured")
    return {
        "multiunit_sales_enabled": cfg.multiunit_sales_enabled,
        "allocation_enabled": cfg.allocation_enabled,
        "worker_enabled": worker_enabled(),
        "unit_price": _num(units.UNIT_PRICE),
        "limits": {"max_units_per_purchase": cfg.max_units_per_purchase,
                   "max_units_per_member": cfg.max_units_per_member, "max_active_units": cfg.max_active_units},
        "units": {"reserved_total": units._reserved_units(db)},
    }


class LimitsBody(BaseModel):
    max_units_per_purchase: Optional[int] = Field(default=None, ge=1)
    max_units_per_member: Optional[int] = Field(default=None, ge=1)
    max_active_units: Optional[int] = Field(default=None, ge=1)
    password: str = Field(min_length=1, max_length=256)


@admin_router.put("/limits")
def set_limits(body: LimitsBody, request: Request, db: Session = Depends(deps.get_db),
               current_user: User = Depends(deps.get_current_admin_user)):
    """Optional limits (null = unlimited). manage_payment_settings + the administrator's password.
    Limits apply to NEW checkouts; purchases already paid or being paid keep their units."""
    from app.models.accounting import AuditTrail
    from app.services import payment_config

    if not payment_config.has_permission(current_user, payment_config.PERMISSION_MANAGE):
        raise HTTPException(status_code=403, detail=f"The {payment_config.PERMISSION_MANAGE} permission is required.")
    try:
        payment_config.require_reauth(current_user, body.password)
    except payment_config.PaymentConfigError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from None
    cfg = units.lock_pool(db)
    old = {"max_units_per_purchase": cfg.max_units_per_purchase, "max_units_per_member": cfg.max_units_per_member,
           "max_active_units": cfg.max_active_units}
    cfg.max_units_per_purchase = body.max_units_per_purchase
    cfg.max_units_per_member = body.max_units_per_member
    cfg.max_active_units = body.max_active_units
    new = {"max_units_per_purchase": cfg.max_units_per_purchase, "max_units_per_member": cfg.max_units_per_member,
           "max_active_units": cfg.max_active_units}
    db.add(AuditTrail(table_name="referral_pool_config", record_id=cfg.id, action="REFERRAL_POOL_LIMITS_CHANGED",
                      user_id=current_user.id, ip_address=_client_ip(request), old_values=old, new_values=new))
    db.commit()
    return {"limits": new}


class RefundProposal(BaseModel):
    purchase_id: int
    quantity: int = Field(ge=1)
    amount: Decimal = Field(gt=0)
    provider_reference: str = Field(min_length=1, max_length=120)
    evidence_note: str = Field(min_length=10, max_length=4000)
    password: str = Field(min_length=1, max_length=256)


class RefundDecision(BaseModel):
    approve: bool
    note: str = Field(min_length=5, max_length=500)
    password: str = Field(min_length=1, max_length=256)


def _refund_view(r: ReferralPoolRefundRecord) -> dict:
    return {"id": r.id, "purchase_id": r.purchase_id, "quantity": r.quantity, "amount": _num(r.amount),
            "provider_reference": r.provider_reference, "status": r.status, "proposed_by": r.proposed_by,
            "decided_by": r.decided_by, "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            "verification": "MANUAL_TWO_PERSON"}


def _units_error(exc: units.UnitsError) -> HTTPException:
    code = 403 if exc.code in ("FORBIDDEN", "REAUTH_REQUIRED", "REAUTH_LOCKED", "SAME_ADMINISTRATOR") else 409
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})


def _refund_detail(r: ReferralPoolRefundRecord) -> dict:
    view = _refund_view(r)
    view.update({"evidence_note": r.evidence_note, "decision_note": r.decision_note,
                 "proposed_at": _iso(r.created_at), "executed_unit_ids": r.executed_unit_ids,
                 "evidence": MANUAL_CLAIM, "provider_verified": False,
                 "evidence_label": "Administrator-entered claim: the provider reference is not independently verified"})
    return view


@admin_router.get("/refunds")
def list_refunds(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                 status: Optional[str] = None, page: Page = 1, page_size: PageSize = 25):
    _require_any(current_user, _finance(), "refunds")
    query = db.query(ReferralPoolRefundRecord).order_by(ReferralPoolRefundRecord.id.desc())
    if status:
        query = query.filter(ReferralPoolRefundRecord.status == status)
    return _paged(query, page, page_size, _refund_detail)


@admin_router.post("/refunds")
def propose_refund(body: RefundProposal, request: Request, db: Session = Depends(deps.get_db),
                   current_user: User = Depends(deps.get_current_admin_user)):
    try:
        record = units.propose_manual_refund(db, current_user, purchase_id=body.purchase_id, quantity=body.quantity,
                                             amount=body.amount, provider_reference=body.provider_reference,
                                             evidence_note=body.evidence_note, password=body.password,
                                             ip=_client_ip(request))
    except units.UnitsError as exc:
        raise _units_error(exc) from None
    return _refund_view(record)


@admin_router.post("/refunds/{record_id}/decision")
def decide_refund(record_id: int, body: RefundDecision, request: Request, db: Session = Depends(deps.get_db),
                  current_user: User = Depends(deps.get_current_admin_user)):
    from app.services.financial_integrity import FinancialIntegrityError

    try:
        record = units.decide_manual_refund(db, current_user, record_id, approve=body.approve, note=body.note,
                                            password=body.password, ip=_client_ip(request))
    except units.UnitsError as exc:
        raise _units_error(exc) from None
    except FinancialIntegrityError as exc:
        raise HTTPException(status_code=409, detail={"code": "FINANCIAL_EXCEPTION", "message": str(exc)}) from None
    return _refund_view(record)


# ---------------------------------------------------------------- P8 administrator views (read only)

@admin_router.get("/overview")
def admin_overview(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user)):
    """Counts for every administrator; money only with a finance permission."""
    from app.services.referral_pool_integration import worker_enabled

    cfg = _config(db)
    finance, kyc = _has_any(current_user, _finance()), _has_any(current_user, _kyc())
    round_ = _open_round(db)
    view = {
        "features": {"multiunit_sales_enabled": bool(cfg and cfg.multiunit_sales_enabled),
                     "allocation_enabled": bool(cfg and cfg.allocation_enabled),
                     "worker_enabled": worker_enabled(), "activation_available": False},
        "limits": {"max_units_per_purchase": cfg.max_units_per_purchase if cfg else None,
                   "max_units_per_member": cfg.max_units_per_member if cfg else None,
                   "max_active_units": cfg.max_active_units if cfg else None},
        "units": _status_counts(db, ReferralPoolUnit.status),
        "eligible_units": db.query(ReferralPoolUnit).filter(ReferralPoolUnit.status == units.ACTIVE).count(),
        "units_waiting_for_next_round": _units_waiting_for_next_round(db, round_),
        "unit_holders": db.query(func.count(func.distinct(ReferralPoolUnit.user_id))).scalar() or 0,
        "purchases": _status_counts(db, ReferralPoolPurchase.status),
        "rounds": _status_counts(db, ReferralPoolRound.status),
        "current_round": _round_view(round_) if round_ else None,
        "queue": _status_counts(db, ReferralPoolPending.status),
        "events": _status_counts(db, ReferralPoolEvent.status),
        "refunds": _status_counts(db, ReferralPoolRefundRecord.status),
        "risk_reviews": {"open": db.query(ReferralPoolRiskReview).filter(ReferralPoolRiskReview.status == "OPEN").count(),
                         "open_blocking": db.query(ReferralPoolRiskReview).filter(
                             ReferralPoolRiskReview.status == "OPEN", ReferralPoolRiskReview.blocking.is_(True)).count()},
        "round_assignments": db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.slot_id.isnot(None)).count(),
        "permissions": {"finance": finance, "kyc": kyc, "operations": finance or kyc},
        "amounts": None,
    }
    if finance:
        paid = (units.P_PAID, units.P_PARTIAL, units.P_REFUNDED)
        paid_total = db.query(func.coalesce(func.sum(ReferralPoolPurchase.total_amount), 0)).filter(
            ReferralPoolPurchase.status.in_(paid)).scalar()
        refunded_total = db.query(func.coalesce(func.sum(ReferralPoolUnit.amount), 0)).filter(
            ReferralPoolUnit.status == units.REFUNDED).scalar()
        view["amounts"] = {"paid": _num(paid_total), "refunded": _num(refunded_total), "currency": "USD"}
    return view


@admin_router.get("/rounds")
def admin_rounds(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                 status: Optional[str] = None, page: Page = 1, page_size: PageSize = 25):
    _require_any(current_user, _operations(), "rounds")
    query = db.query(ReferralPoolRound).order_by(ReferralPoolRound.round_number.desc())
    if status:
        query = query.filter(ReferralPoolRound.status == status)
    return _paged(query, page, page_size, _round_view)


@admin_router.get("/rounds/{round_id}/slots")
def admin_round_slots(round_id: int, db: Session = Depends(deps.get_db),
                      current_user: User = Depends(deps.get_current_admin_user), status: Optional[str] = None,
                      page: Page = 1, page_size: PageSize = 50):
    _require_any(current_user, _operations(), "round slots")
    if db.get(ReferralPoolRound, round_id) is None:
        raise HTTPException(status_code=404, detail="Round not found")
    query = (db.query(ReferralPoolRoundSlot).filter(ReferralPoolRoundSlot.round_id == round_id)
             .order_by(ReferralPoolRoundSlot.id.asc()))
    if status:
        query = query.filter(ReferralPoolRoundSlot.status == status)
    paged = _paged(query, page, page_size, lambda slot: slot)
    slots = paged["items"]
    filled = {slot_id: referred for slot_id, referred in db.query(
        ReferralPoolAssignment.slot_id, ReferralPoolAssignment.referred_user_id).filter(
        ReferralPoolAssignment.slot_id.in_([s.id for s in slots] or [-1]))}
    names = _usernames(db, [s.member_user_id for s in slots])
    paged["items"] = [{"id": s.id, "unit_id": s.unit_id, "member_user_id": s.member_user_id,
                       "member_username": names.get(s.member_user_id), "status": s.status,
                       "filled_at": _iso(s.filled_at), "voided_at": _iso(s.voided_at), "void_reason": s.void_reason,
                       "referred_user_id": filled.get(s.id)} for s in slots]
    return paged


@admin_router.get("/assignments")
def admin_assignments(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                      round_id: Optional[int] = None, member_user_id: Optional[int] = None,
                      page: Page = 1, page_size: PageSize = 25):
    _require_any(current_user, _operations(), "allocations")
    query = (db.query(ReferralPoolAssignment, ReferralPoolRound.round_number)
             .outerjoin(ReferralPoolRound, ReferralPoolRound.id == ReferralPoolAssignment.round_id)
             .order_by(ReferralPoolAssignment.id.desc()))
    if round_id is not None:
        query = query.filter(ReferralPoolAssignment.round_id == round_id)
    if member_user_id is not None:
        query = query.filter(ReferralPoolAssignment.pool_member_user_id == member_user_id)
    return _paged(query, page, page_size, lambda row: {
        **_assignment_view(row[0], row[1]), "referred_user_id": row[0].referred_user_id,
        "pool_member_user_id": row[0].pool_member_user_id, "slot_id": row[0].slot_id, "unit_id": row[0].unit_id})


@admin_router.get("/queue")
def admin_queue(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                status: Optional[str] = "WAITING", page: Page = 1, page_size: PageSize = 25):
    _require_any(current_user, _operations(), "the pending referral queue")
    query = db.query(ReferralPoolPending).order_by(ReferralPoolPending.enqueued_at.asc(), ReferralPoolPending.id.asc())
    if status:
        query = query.filter(ReferralPoolPending.status == status)
    return _paged(query, page, page_size, lambda q: {
        "id": q.id, "referred_user_id": q.referred_user_id, "status": q.status, "trigger_event": q.trigger_event,
        "enqueued_at": _iso(q.enqueued_at), "attempts": q.attempts, "last_attempt_at": _iso(q.last_attempt_at),
        "last_error": (q.last_error or "")[:500] or None, "resolved_at": _iso(q.resolved_at),
        "resolution_reason": q.resolution_reason, "assignment_id": q.assignment_id})


@admin_router.get("/purchases")
def admin_purchases(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                    status: Optional[str] = None, user_id: Optional[int] = None,
                    page: Page = 1, page_size: PageSize = 25):
    _require_any(current_user, _finance(), "purchases")
    query = db.query(ReferralPoolPurchase).order_by(ReferralPoolPurchase.id.desc())
    if status:
        query = query.filter(ReferralPoolPurchase.status == status)
    if user_id is not None:
        query = query.filter(ReferralPoolPurchase.user_id == user_id)
    paged = _paged(query, page, page_size, lambda p: p)
    names = _usernames(db, [p.user_id for p in paged["items"]])
    paged["items"] = [{**_purchase_view(db, p), "user_id": p.user_id, "username": names.get(p.user_id)}
                      for p in paged["items"]]
    return paged


@admin_router.get("/units")
def admin_units(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                status: Optional[str] = None, user_id: Optional[int] = None,
                page: Page = 1, page_size: PageSize = 50):
    _require_any(current_user, _finance(), "units")
    query = db.query(ReferralPoolUnit).order_by(ReferralPoolUnit.id.desc())
    if status:
        query = query.filter(ReferralPoolUnit.status == status)
    if user_id is not None:
        query = query.filter(ReferralPoolUnit.user_id == user_id)
    paged = _paged(query, page, page_size, lambda u: u)
    rows = paged["items"]
    manual = _manual_references(db, [u.refund_reference for u in rows])
    names = _usernames(db, [u.user_id for u in rows])
    paged["items"] = [{
        "id": u.id, "user_id": u.user_id, "username": names.get(u.user_id), "purchase_id": u.purchase_id,
        "unit_index": u.unit_index, "source": u.source, "status": u.status, "amount": _num(u.amount),
        "activated_at": _iso(u.activated_at), "suspended_at": _iso(u.suspended_at), "ended_at": _iso(u.ended_at),
        "status_reason": u.status_reason, "refunded_at": _iso(u.refunded_at), "refund_reference": u.refund_reference,
        "refund_evidence": refund_evidence(u.refund_reference, manual) if u.status == units.REFUNDED else None,
    } for u in rows]
    return paged


@admin_router.get("/reconciliation")
def admin_reconciliation(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                         page: Page = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 25):
    """Ledger against units, one page of purchases at a time, plus how every refunded unit was evidenced."""
    from app.services import referral_pool_accounting as accounting

    _require_any(current_user, _finance(), "reconciliation")
    query = (db.query(ReferralPoolPurchase)
             .filter(ReferralPoolPurchase.status.in_((units.P_PAID, units.P_PARTIAL, units.P_REFUNDED)))
             .order_by(ReferralPoolPurchase.id.desc()))
    paged = _paged(query, page, page_size, lambda p: {
        "purchase_id": p.id, "user_id": p.user_id, "status": p.status, "total_amount": _num(p.total_amount),
        "problems": [[str(part) if part is not None else None for part in problem]
                     for problem in accounting.reconcile_purchase(db, p.id)]})
    refunded = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.status == units.REFUNDED)
    manual_refs = db.query(ReferralPoolRefundRecord.provider_reference).filter(
        ReferralPoolRefundRecord.status == "APPROVED")
    manual = refunded.filter(ReferralPoolUnit.refund_reference.in_(manual_refs)).count()
    not_manual = refunded.filter(~ReferralPoolUnit.refund_reference.in_(manual_refs))
    provider = not_manual.filter(ReferralPoolUnit.refund_reference.like("provider-refund:%")
                                 | ReferralPoolUnit.refund_reference.like("soncopay-refund:%")).count()
    reversal = not_manual.filter(ReferralPoolUnit.refund_reference.like("deposit-refund:%")).count()
    paged["summary"] = {
        "refunded_units": {PROVIDER_EVENT: provider, MANUAL_CLAIM: manual, DEPOSIT_REVERSAL: reversal,
                           UNCLASSIFIED: max(refunded.count() - provider - manual - reversal, 0)},
        "held_for_review_purchases": db.query(ReferralPoolPurchase).filter(
            ReferralPoolPurchase.status == units.P_HELD).count(),
        "refund_proposals_awaiting_decision": db.query(ReferralPoolRefundRecord).filter(
            ReferralPoolRefundRecord.status == "PROPOSED").count(),
        "page_purchases_with_problems": sum(1 for item in paged["items"] if item["problems"]),
    }
    return paged


@admin_router.get("/events")
def admin_events(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                 status: Optional[str] = "FAILED", page: Page = 1, page_size: PageSize = 25):
    _require_any(current_user, _operations(), "pool events")
    query = db.query(ReferralPoolEvent).order_by(ReferralPoolEvent.id.desc())
    if status:
        query = query.filter(ReferralPoolEvent.status == status)
    return _paged(query, page, page_size, lambda e: {
        "id": e.id, "user_id": e.user_id, "event_type": e.event_type, "status": e.status, "attempts": e.attempts,
        "last_error": (e.last_error or "")[:500] or None, "created_at": _iso(e.created_at),
        "processed_at": _iso(e.processed_at)})


@admin_router.get("/risk-reviews")
def admin_risk_reviews(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                       status: Optional[str] = "OPEN", page: Page = 1, page_size: PageSize = 25):
    """Anti-abuse cases. Only account ids and a short fingerprint of the evidence hash: no names,
    birth dates, documents, wallet addresses or IP addresses."""
    _require_any(current_user, _kyc(), "anti-abuse reviews")
    query = db.query(ReferralPoolRiskReview).order_by(ReferralPoolRiskReview.id.desc())
    if status:
        query = query.filter(ReferralPoolRiskReview.status == status)
    return _paged(query, page, page_size, lambda r: {
        "id": r.id, "user_id": r.user_id, "signal": r.signal, "blocking": r.blocking, "status": r.status,
        "related_user_ids": [int(i) for i in (r.related_user_ids or "").split(",") if i.strip().isdigit()],
        "evidence_fingerprint": (r.evidence_hash or "")[:12], "created_at": _iso(r.created_at),
        "decided_by": r.decided_by, "decided_at": _iso(r.decided_at), "decision_note": r.decision_note})


class RiskDecision(BaseModel):
    decision: str = Field(pattern="^(CLEARED|CONFIRMED)$")
    note: str = Field(min_length=5, max_length=500)
    password: str = Field(min_length=1, max_length=256)


@admin_router.post("/risk-reviews/{review_id}/decision")
def decide_risk_review(review_id: int, body: RiskDecision, request: Request, db: Session = Depends(deps.get_db),
                       current_user: User = Depends(deps.get_current_admin_user)):
    """manage_kyc_settings + the administrator's password; audited (P6 rules, unchanged)."""
    from app.services import referral_pool_risk as risk

    try:
        review = risk.decide(db, current_user, review_id, body.decision, note=body.note, password=body.password,
                             ip=_client_ip(request))
    except risk.RiskError as exc:
        code = 403 if exc.code in ("FORBIDDEN", "REAUTH_REQUIRED", "REAUTH_LOCKED") else (
            404 if exc.code == "NOT_FOUND" else 409)
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)}) from None
    return {"id": review.id, "status": review.status, "decided_by": review.decided_by,
            "decided_at": _iso(review.decided_at)}


@admin_router.get("/invalid-sponsors")
def admin_invalid_sponsors(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                           page: Page = 1, page_size: PageSize = 50):
    """Historical personal sponsors that would not be valid inviters today (read only; never changed).
    Each page checks `page_size` personally sponsored members, in id order. Derived from KYC
    status: manage_kyc_settings."""
    _require_any(current_user, _kyc(), "invalid sponsor records")
    from app.services.referral_pool_integration import invalid_personal_sponsors

    candidates = db.query(User).filter(User.sponsor_id.isnot(None),
                                       User.sponsor_source.in_(("PERSONAL_REFERRAL", "JOIN_CODE"))).count()
    items = invalid_personal_sponsors(db, limit=page_size, offset=(page - 1) * page_size)
    return {"items": items, "page": page, "page_size": page_size, "checked_total": candidates,
            "note": "Each page checks the next personally sponsored members; sponsors are never changed."}


POOL_AUDIT_TABLES = ("referral_pool_config", "referral_pool_refund_records", "referral_pool_risk_reviews")


@admin_router.get("/audit")
def admin_audit(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_admin_user),
                page: Page = 1, page_size: PageSize = 25):
    from app.models.accounting import AuditTrail

    _require_any(current_user, _finance() + _kyc(), "the Referral Pool audit trail")
    query = (db.query(AuditTrail).filter(AuditTrail.table_name.in_(POOL_AUDIT_TABLES),
                                         AuditTrail.action.like("REFERRAL_POOL_%"))
             .order_by(AuditTrail.id.desc()))
    return _paged(query, page, page_size, lambda a: {
        "id": a.id, "table_name": a.table_name, "record_id": a.record_id, "action": a.action, "user_id": a.user_id,
        "old_values": a.old_values, "new_values": a.new_values, "timestamp": _iso(a.timestamp)})
