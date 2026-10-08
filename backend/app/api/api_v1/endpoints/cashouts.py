"""Administrator monitoring and exception handling for affiliate cashouts.

Every route requires an administrator. None of them calls the payout provider
to SEND anything: an administrator records a settlement that happened outside
the platform, cancels a request, or settles a payout whose outcome the engine
could not determine. `POST /run` runs one engine cycle, which is a no-op while
the engine is off.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.api_v1.endpoints.admin import require_admin
from app.db.session import get_db
from app.models.affiliate import AffiliateCashoutRequest
from app.models.user import User
from app.schemas.wallet import CashoutCancel, CashoutResolve, CashoutSettle
from app.services import cashout_engine
from app.services import cashout_service as service
from app.services.financial_eligibility import FinancialEligibilityHold, http_error

admin_router = APIRouter()


def _error(exc: service.CashoutError) -> HTTPException:
    code = status.HTTP_403_FORBIDDEN if exc.code == "FORBIDDEN" else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})


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
    return {"total": total, "items": [service.cashout_dict(r, admin=True) for r in rows]}


@admin_router.get("/overview")
def overview(read_provider: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """What is owed, by state, next to the provider's balance. The provider is
    asked only with read_provider=true and only when its credentials exist."""
    report = cashout_engine.reconciliation_report(db, read_provider=read_provider)
    report["usd_settlement_enabled"] = service.usd_settlement_available()
    report["minimums"] = {"CRYPTO": float(service.crypto_minimum()), "USD": float(service.usd_minimum())}
    return report


@admin_router.post("/run")
def run_engine(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return cashout_engine.run_cycle(db)


@admin_router.post("/{cashout_id}/cancel")
def cancel(cashout_id: int, body: CashoutCancel, db: Session = Depends(get_db),
           admin: User = Depends(require_admin)):
    try:
        return service.cashout_dict(service.cancel_request(db, _get(db, cashout_id), actor=admin, reason=body.reason),
                                    admin=True)
    except service.CashoutError as exc:
        raise _error(exc) from exc


@admin_router.post("/{cashout_id}/settle-usd")
def settle_usd(cashout_id: int, body: CashoutSettle, db: Session = Depends(get_db),
               admin: User = Depends(require_admin)):
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
            admin: User = Depends(require_admin)):
    """Settle a crypto cashout whose provider outcome is unknown, after checking
    the provider by hand: SENT (with its reference) or NOT_SENT."""
    try:
        return service.cashout_dict(
            service.resolve_uncertain(db, _get(db, cashout_id), admin=admin, outcome=body.outcome,
                                      reference=body.reference), admin=True)
    except service.CashoutError as exc:
        db.rollback()
        raise _error(exc) from exc
