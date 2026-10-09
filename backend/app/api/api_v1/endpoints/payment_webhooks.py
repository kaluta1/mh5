"""
Payment provider webhooks (NOWPayments IPN).
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.crud import crud_deposit
from app.db.session import get_db
from app.models.payment import Deposit
from app.services.nowpayments_service import (
    finalize_deposit_from_nowpayments,
    verify_ipn_signature,
)
from app.services.financial_integrity import FinancialIntegrityError
from app.services import payment_config

logger = logging.getLogger(__name__)
router = APIRouter()


def _count(db: Session, outcome: str, *, commit: bool = True) -> None:
    """Webhook health counter (Admin > Finance & Payments). Never raises and
    never changes what the callback answers."""
    try:
        payment_config.record_webhook(db, outcome)
        if commit:
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


@router.post("/nowpayments")
async def nowpayments_ipn(request: Request, db: Session = Depends(get_db)):
    """
    NOWPayments instant payment notification callback.
    Validates HMAC SHA-512 signature (sorted JSON keys) and finalizes deposits.

    The signature is checked against the body exactly as it was received. A
    callback is only ever a reason to look: a payment is credited through the
    same idempotent path as the status poll, and a payout notification never
    pays or releases anything (the cashout engine asks the provider itself).
    """
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        _count(db, "INVALID_JSON")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
    except (UnicodeDecodeError, RecursionError) as exc:
        _count(db, "INVALID_JSON")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
    if not isinstance(body, dict):
        _count(db, "INVALID_JSON")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    signature = request.headers.get("x-nowpayments-sig", "")
    if not verify_ipn_signature(body, signature, secret=payment_config.ipn_secret(db) or "", raw=raw):
        logger.warning("NOWPayments IPN rejected: invalid signature")
        _count(db, "REJECTED_SIGNATURE")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    order_id = body.get("order_id")
    payment_id = str(body.get("payment_id") or "")

    if not payment_id and not order_id and body.get("batch_withdrawal_id"):
        # A payout (withdrawal) notification. It is acknowledged and counted,
        # never acted on: the engine reads the payout status from the provider.
        _count(db, "PAYOUT_NOTICE")
        return {"ok": True}

    deposit = None
    if order_id:
        deposit = (
            db.query(Deposit)
            .filter(Deposit.order_id == str(order_id))
            .with_for_update()
            .first()
        )
    if not deposit and payment_id:
        deposit = (
            db.query(Deposit)
            .filter(Deposit.external_payment_id == payment_id)
            .with_for_update()
            .first()
        )

    if not deposit:
        logger.warning("NOWPayments IPN for unknown order=%s payment=%s", order_id, payment_id)
        _count(db, "UNKNOWN_ORDER")
        return {"ok": True}

    try:
        ok = finalize_deposit_from_nowpayments(db, deposit, body, defer_commit=True)
    except FinancialIntegrityError as exc:
        db.rollback()
        logger.error("NOWPayments IPN financial identity rejected for deposit %s", deposit.id)
        _count(db, "IDENTITY_REJECTED")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not ok:
        db.rollback()
        _count(db, "ERROR")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment notification",
        )

    _count(db, "ACCEPTED", commit=False)
    db.commit()
    logger.info(
        "NOWPayments IPN processed deposit=%s status=%s payment_status=%s",
        deposit.id,
        deposit.status.value,
        body.get("payment_status"),
    )
    return {"ok": True}
