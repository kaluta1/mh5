"""Internal wallet payments API (Prompt 5): members pay approved products with available commission
earnings; finance administrators review payments, reconciliation and refunds. Every amount is computed by
the server; INTERNAL_WALLET_PAYMENTS_ENABLED (default off) is enforced on every payment path."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.core.rate_limit import _is_rate_limited
from app.models.internal_wallet import InternalWalletPayment
from app.models.user import User
from app.services import internal_wallet as iw

member_router = APIRouter()
admin_router = APIRouter()


def _err(exc: iw.WalletError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


class PayBody(BaseModel):
    product_code: str = Field(min_length=1, max_length=50)
    quantity: int = Field(default=1, ge=1, le=iw.MAX_QUANTITY)
    idempotency_key: str = Field(min_length=8, max_length=80)
    # Optional: the amount the member saw. Never used as the price; a difference only stops the payment.
    expected_amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class RefundBody(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    current_password: str = Field(default="", max_length=256)


# ---------------------------------------------------------------- member

@member_router.get("/summary")
def wallet_summary(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    out = iw.member_summary(db, user)
    db.rollback()
    return out


@member_router.get("/preview")
def wallet_preview(product_code: str, quantity: int = 1, db: Session = Depends(get_db),
                   user: User = Depends(get_current_active_user)):
    out = iw.preview(db, user, product_code, quantity)
    db.rollback()
    return out


@member_router.post("/pay")
def wallet_pay(body: PayBody, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    if not iw.enabled():
        raise _err(iw.WalletError("WALLET_PAYMENTS_DISABLED", "Paying with MyHigh5 earnings is not available.", 403))
    if _is_rate_limited(f"iwp-pay:{user.id}", 10, 600):
        raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "Too many attempts; try later."})
    try:
        payment, replayed = iw.pay(db, user, product_code=body.product_code, quantity=body.quantity,
                                   idempotency_key=body.idempotency_key, expected_amount=body.expected_amount)
        db.commit()
    except iw.WalletError as exc:
        db.rollback()
        if exc.code not in ("WALLET_PAYMENTS_DISABLED", "IDEMPOTENCY_CONFLICT", "IDEMPOTENCY_KEY_REQUIRED"):
            failed = iw.record_failure(db, user, product_code=body.product_code, quantity=body.quantity, code=exc.code)
            if failed is not None:
                iw.notify(db, failed, "FAILED")
        raise _err(exc) from None
    except Exception:
        db.rollback()
        iw.record_failure(db, user, product_code=body.product_code, quantity=body.quantity, code="INTERNAL_ERROR")
        raise HTTPException(status_code=500, detail={"code": "PAYMENT_FAILED",
                                                     "message": "The payment could not be completed; nothing was charged."})
    if not replayed and iw.notify(db, payment, "COMPLETED"):
        db.commit()
    out = iw.payment_payload(db, payment)
    out["replayed"] = replayed
    out["remaining"] = str(iw.spendable_balance(db, user.id))
    db.rollback()
    return out


@member_router.get("/payments/{payment_id}")
def wallet_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    p = (db.query(InternalWalletPayment)
         .filter(InternalWalletPayment.id == payment_id, InternalWalletPayment.user_id == user.id).first())
    if p is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    out = iw.payment_payload(db, p)
    db.rollback()
    return out


# ---------------------------------------------------------------- administration

def _viewer(user: User) -> None:
    from app.api.api_v1.endpoints.soncopay import _require_payout_viewer

    _require_payout_viewer(user)


@admin_router.get("/overview")
def admin_overview(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _viewer(user)
    out = {"enabled": iw.enabled(), "switch": "INTERNAL_WALLET_PAYMENTS_ENABLED (server setting; owner approval required)",
           "products": iw.policy_overview(db), "reconciliation": iw.reconciliation(db)}
    db.rollback()
    return out


@admin_router.get("/payments")
def admin_payments(user_id: Optional[int] = None, product_code: Optional[str] = None, status: Optional[str] = None,
                   db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _viewer(user)
    out = {"payments": iw.admin_list(db, user_id=user_id, product_code=product_code, status=status)}
    db.rollback()
    return out


@admin_router.get("/payments/{payment_id}")
def admin_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _viewer(user)
    p = db.get(InternalWalletPayment, payment_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    out = iw.payment_payload(db, p, detail=True)
    db.rollback()
    return out


@admin_router.post("/payments/{payment_id}/refund")
def admin_refund(payment_id: int, body: RefundBody, db: Session = Depends(get_db),
                 user: User = Depends(get_current_active_user)):
    """Full refund (existing finance controls: process_cashouts permission + current password, audited)."""
    from app.services import payment_config

    if not payment_config.has_permission(user, payment_config.PERMISSION_PROCESS):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN",
                                                     "message": "The process_cashouts permission is required."})
    try:
        payment_config.require_reauth(user, body.current_password)
    except payment_config.PaymentConfigError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from None
    try:
        payment = iw.refund(db, user, payment_id, reason=body.reason)
        db.commit()
    except iw.WalletError as exc:
        db.rollback()
        if exc.code == "REFUND_REVIEW_REQUIRED":
            p = db.get(InternalWalletPayment, payment_id)
            if p is not None and iw.notify(db, p, "REFUND_REVIEW"):
                db.commit()
        raise _err(exc) from None
    if iw.notify(db, payment, "REFUNDED"):
        db.commit()
    return iw.payment_payload(db, payment, detail=True)
