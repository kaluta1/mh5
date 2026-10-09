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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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

_UNPROCESSABLE = ("INVALID_OUTCOME", "REFERENCE_REQUIRED")


def _error(exc: service.CashoutError) -> HTTPException:
    code = (status.HTTP_403_FORBIDDEN if exc.code == "FORBIDDEN"
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
        "member": {"id": cashout.user_id, "username": member.username if member else None,
                   "cashout_method": member.cashout_method if member else None,
                   "wallet": service.mask_address(wallet.address) if wallet else None,
                   "wallet_status": wallet.status if wallet else None},
        "commissions": [{"id": c.id, "amount": float(c.commission_amount), "status": c.status.value,
                         "level": c.level,
                         "transaction_date": c.transaction_date.isoformat() if c.transaction_date else None}
                        for c in commissions],
        "attempts": [service.cashout_dict(a, admin=True) for a in attempts],
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
