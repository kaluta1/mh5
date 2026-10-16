"""Administrator monitoring and exception handling for affiliate cashouts.

Every route requires an administrator. Every ACTION (cancel, record a USD
settlement, settle an unknown outcome, view a member's USD destination, run
an engine cycle) additionally requires the explicit `process_cashouts`
permission and is written to the audit trail.

None of them calls the payout provider to SEND anything on request: there is
no manual payout button. An administrator records a settlement that happened
outside the platform, cancels a request, or settles a payout whose outcome the
engine could not determine. `POST /run` runs one engine cycle, which obeys
every rule and limit and is a no-op while the engine is off.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.api_v1.endpoints.admin import require_admin
from app.core.client_ip import client_ip
from app.db.session import get_db
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission
from app.models.user import User
from app.schemas.wallet import CashoutCancel, CashoutResolve, CashoutSettle
from app.services import cashout_engine, payment_config
from app.services import cashout_service as service
from app.services.financial_eligibility import FinancialEligibilityHold, http_error

admin_router = APIRouter()

_UNPROCESSABLE = ("INVALID_OUTCOME", "REFERENCE_REQUIRED", "INVALID_FEE", "CHARGED_TO_REQUIRED", "EVIDENCE_REQUIRED",
                  "RECEIVED_REQUIRED", "AMOUNTS_DO_NOT_ADD_UP", "REVIEW_NOTE_REQUIRED")


def _error(exc: service.CashoutError) -> HTTPException:
    code = (status.HTTP_403_FORBIDDEN if exc.code in ("FORBIDDEN", "REAUTH_REQUIRED")
            else status.HTTP_422_UNPROCESSABLE_ENTITY if exc.code in _UNPROCESSABLE
            else status.HTTP_409_CONFLICT)
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})


def require_processor(current_user: User = Depends(require_admin)) -> User:
    if not payment_config.has_permission(current_user, payment_config.PERMISSION_PROCESS):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"code": "FORBIDDEN",
                                    "message": f"The {payment_config.PERMISSION_PROCESS} permission is required."})
    return current_user


def _get(db: Session, cashout_id: int) -> AffiliateCashoutRequest:
    cashout = db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id).first()
    if cashout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cashout not found")
    return cashout


@admin_router.get("")
def list_cashouts(status_filter: Optional[str] = Query(None, alias="status"), method: Optional[str] = None,
                  user_id: Optional[int] = None, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                  db: Session = Depends(get_db), _: User = Depends(require_admin)):
    query = db.query(AffiliateCashoutRequest)
    if status_filter:
        query = query.filter(AffiliateCashoutRequest.status == status_filter.strip().lower())
    if method:
        query = query.filter(AffiliateCashoutRequest.cashout_method == method.strip().upper())
    if user_id is not None:
        query = query.filter(AffiliateCashoutRequest.user_id == user_id)
    total = query.count()
    rows = query.order_by(AffiliateCashoutRequest.id.desc()).offset(skip).limit(limit).all()
    members = {u.id: u for u in db.query(User).filter(User.id.in_({r.user_id for r in rows})).all()} if rows else {}
    items = []
    for row in rows:
        item = service.cashout_dict(row, admin=True)
        member = members.get(row.user_id)
        item["username"] = member.username if member is not None else None
        items.append(item)
    return {"total": total, "items": items}


@admin_router.get("/overview")
def overview(read_provider: bool = False, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """What is owed, by state, next to the provider's balance. The provider is
    asked only with read_provider=true, by an administrator who may manage
    payments, and only when its credentials exist."""
    if read_provider and not payment_config.has_permission(admin, payment_config.PERMISSION_MANAGE):
        read_provider = False
    report = cashout_engine.reconciliation_report(db, read_provider=read_provider)
    config = payment_config.load(db)
    report["usd_settlement_enabled"] = config.usd_settlement_allowed
    report["minimums"] = {"CRYPTO": float(config.crypto_min_usd), "USD": float(config.usd_min_usd)}
    return report


@admin_router.post("/run")
def run_engine(db: Session = Depends(get_db), _: User = Depends(require_processor)):
    return cashout_engine.run_cycle(db)


@admin_router.get("/fee-exceptions")
def fee_exceptions(state: Optional[str] = Query(None, pattern="^(PENDING|REVIEWED)$"), skip: int = Query(0, ge=0),
                   limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    """Flagged payouts (reconciliation exceptions): what was expected, what the
    provider did, the evidence, and whether an administrator reviewed each."""
    return service.fee_exceptions(db, state=state, skip=skip, limit=limit)


class CommissionReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(..., pattern="^(RELEASE|CANCEL)$")
    reason: str = Field(..., max_length=2000)
    evidence_reference: Optional[str] = Field(default=None, max_length=255)
    current_password: str = Field(default="", max_length=256)


@admin_router.get("/commission-reviews")
def held_commissions(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Historical commissions held from every payout until reviewed, with any decision taken."""
    from app.services import commission_payout_hold as hold

    return {"items": hold.held_view(db)}


@admin_router.post("/commission-reviews/{commission_id}")
def review_held_commission(commission_id: int, body: CommissionReviewBody, request: Request,
                           db: Session = Depends(get_db), current_user: User = Depends(require_processor)):
    """Record THE decision for one held historical commission: RELEASE (may then be paid when payouts
    are enabled) or CANCEL (carried out by the reconciliation procedure). Final, audited, password
    required, never on one's own commission."""
    from app.services import commission_payout_hold as hold

    try:
        record = hold.review(db, current_user, commission_id, decision=body.decision, reason=body.reason,
                             password=body.current_password, evidence_reference=body.evidence_reference,
                             ip=client_ip(request))
    except hold.CommissionReviewError as exc:
        code = {"FORBIDDEN": 403, "REAUTH_REQUIRED": 403, "REAUTH_LOCKED": 429, "SELF_ACTION_FORBIDDEN": 403,
                "NOT_FOUND": 404, "REASON_REQUIRED": 400, "INVALID_DECISION": 400}.get(exc.code, 409)
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)}) from None
    return {"commission_id": record.commission_id, "decision": record.decision, "decided_by": record.decided_by,
            "decided_at": record.decided_at.isoformat()}


@admin_router.get("/{cashout_id}")
def detail(cashout_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """One cashout with the commissions it holds and the member's other
    payout attempts (each attempt is its own cashout; none is ever re-sent)."""
    cashout = _get(db, cashout_id)
    intent = service._intent(cashout)
    references = [intent] + ([cashout.settlement_reference] if cashout.settlement_reference else [])
    commissions = (db.query(AffiliateCommission)
                   .filter(AffiliateCommission.user_id == cashout.user_id,
                           AffiliateCommission.payout_reference.in_(references))
                   .order_by(AffiliateCommission.id).all())
    attempts = (db.query(AffiliateCashoutRequest)
                .filter(AffiliateCashoutRequest.user_id == cashout.user_id)
                .order_by(AffiliateCashoutRequest.id.desc()).limit(20).all())
    member = db.query(User).filter(User.id == cashout.user_id).first()
    wallet = service.wallet_state(member) if member is not None else None
    return {
        "cashout": service.cashout_dict(cashout, admin=True),
        "network_fee_record": service.network_fee_state(db, cashout),
        "member": {"id": cashout.user_id, "username": member.username if member else None,
                   "cashout_method": member.cashout_method if member else None,
                   "wallet": service.mask_address(wallet.address) if wallet else None,
                   "wallet_status": wallet.status if wallet else None},
        "commissions": [{"id": c.id, "amount": float(c.commission_amount), "status": c.status.value,
                         "level": c.level,
                         "transaction_date": c.transaction_date.isoformat() if c.transaction_date else None}
                        for c in commissions],
        "attempts": [service.cashout_dict(a, admin=True) for a in attempts],
        "fee_exception": (service.fee_exception_view(
            cashout, username=member.username if member else None,
            suspended_by=payment_config.load(db).suspended_cashout_id) if cashout.fee_flag else None),
        "fee_events": service.fee_exception_events(db, cashout.id) if cashout.fee_flag else [],
    }


@admin_router.get("/{cashout_id}/destination")
def destination(cashout_id: int, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require_processor)):
    """The member's USD payout destination details. Audited on every view."""
    try:
        return {"destination": service.reveal_usd_destination(db, _get(db, cashout_id), admin=admin,
                                                              ip=client_ip(request))}
    except service.CashoutError as exc:
        db.rollback()
        raise _error(exc) from exc


@admin_router.post("/{cashout_id}/cancel")
def cancel(cashout_id: int, body: CashoutCancel, db: Session = Depends(get_db),
           admin: User = Depends(require_processor)):
    try:
        return service.cashout_dict(service.cancel_request(db, _get(db, cashout_id), actor=admin, reason=body.reason),
                                    admin=True)
    except service.CashoutError as exc:
        raise _error(exc) from exc


@admin_router.post("/{cashout_id}/settle-usd")
def settle_usd(cashout_id: int, body: CashoutSettle, db: Session = Depends(get_db),
               admin: User = Depends(require_processor)):
    """Record that a USD cashout was paid outside the platform. Refused until
    USD settlement is enabled and its ledger account is configured."""
    try:
        return service.cashout_dict(
            service.settle_usd_cashout(db, _get(db, cashout_id), admin=admin, reference=body.reference), admin=True)
    except FinancialEligibilityHold as exc:
        raise http_error(exc) from None
    except service.CashoutError as exc:
        db.rollback()
        raise _error(exc) from exc


@admin_router.post("/{cashout_id}/resolve")
def resolve(cashout_id: int, body: CashoutResolve, db: Session = Depends(get_db),
            admin: User = Depends(require_processor)):
    """Settle a crypto cashout whose provider outcome is unknown, after checking
    the provider by hand: SENT (with its reference) or NOT_SENT."""
    try:
        return service.cashout_dict(
            service.resolve_uncertain(db, _get(db, cashout_id), admin=admin, outcome=body.outcome,
                                      reference=body.reference), admin=True)
    except service.CashoutError as exc:
        db.rollback()
        raise _error(exc) from exc


class NetworkFeeRecord(BaseModel):
    # The fee read from the provider's statement, in the payout currency. Zero = none was charged.
    amount: Decimal = Field(..., ge=0, max_digits=18, decimal_places=8)
    reference: str = Field(..., min_length=3, max_length=200)
    # Beneficiary-paid payouts only: where the provider took the fee from.
    charged_to: Optional[str] = Field(default=None, max_length=20, description="PAYOUT_AMOUNT or PROVIDER_BALANCE")
    # Where the figures were read: PROVIDER_STATEMENT, BLOCKCHAIN_EXPLORER, PROVIDER_SUPPORT or OTHER.
    evidence: Optional[str] = Field(default=None, max_length=30)
    # The administrator checked the fee, who bore it and the amount received against that evidence.
    # Only then does the payout count as reconciled; it needs `received`.
    verified: bool = False
    received: Optional[Decimal] = Field(default=None, ge=0, max_digits=18, decimal_places=8)


@admin_router.post("/{cashout_id}/network-fee")
def network_fee(cashout_id: int, body: NetworkFeeRecord, db: Session = Depends(get_db),
                admin: User = Depends(require_processor)):
    """Record the ACTUAL network fee of a completed crypto payout, read from
    the provider's statement. Never an estimate, once per payout. Sends
    nothing to the provider.

    Beneficiary-paid payout: the fee and the amount received are recorded and
    no journal entry is posted. Legacy company-paid payout: Dr 5005 / Cr the
    treasury account."""
    cashout = _get(db, cashout_id)
    try:
        if cashout.network_fee_policy == payment_config.FEE_MEMBER_PAYS:
            cashout = service.record_member_fee_by_admin(db, cashout, admin=admin, amount=body.amount,
                                                         charged_to=body.charged_to, reference=body.reference,
                                                         evidence=body.evidence, verified=body.verified,
                                                         received=body.received)
        else:
            cashout = service.record_network_fee_by_admin(db, cashout, admin=admin, amount=body.amount,
                                                          reference=body.reference)
    except service.CashoutError as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"cashout": service.cashout_dict(cashout, admin=True),
            "network_fee_record": service.network_fee_state(db, cashout)}


class FeeExceptionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # What the administrator checked and what they found. Kept on the cashout and in the audit trail.
    note: str = Field(default="", max_length=500)
    current_password: str = Field(default="", max_length=256)


@admin_router.post("/{cashout_id}/fee-review")
def fee_review(cashout_id: int, body: FeeExceptionReview, request: Request, db: Session = Depends(get_db),
               admin: User = Depends(require_processor)):
    """Record that an administrator reviewed a flagged payout. Needs the
    process_cashouts permission, the current password and a written note.

    A record only: it does not clear the flag, does not verify the payout's
    actual fee, does not lift a payout suspension and does not allow a new
    payout. Once per flag; the same review sent again changes nothing."""
    try:
        cashout = service.review_fee_exception(db, _get(db, cashout_id), admin=admin,
                                               password=body.current_password, note=body.note,
                                               ip=client_ip(request))
    except service.CashoutError as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"cashout": service.cashout_dict(cashout, admin=True),
            "fee_exception": service.fee_exception_view(
                cashout, suspended_by=payment_config.load(db).suspended_cashout_id)}
