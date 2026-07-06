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

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/nowpayments")
async def nowpayments_ipn(request: Request, db: Session = Depends(get_db)):
    """
    NOWPayments instant payment notification callback.
    Validates HMAC SHA-512 signature (sorted JSON keys) and finalizes deposits.
    """
    raw = await request.body()
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc

    signature = request.headers.get("x-nowpayments-sig", "")
    if not verify_ipn_signature(body, signature):
        logger.warning("NOWPayments IPN rejected: invalid signature")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    order_id = body.get("order_id")
    payment_id = str(body.get("payment_id") or "")

    deposit = None
    if order_id:
        deposit = crud_deposit.deposit.get_by_order_id(db, order_id=str(order_id))
    if not deposit and payment_id:
        deposit = db.query(Deposit).filter(Deposit.external_payment_id == payment_id).first()

    if not deposit:
        logger.warning("NOWPayments IPN for unknown order=%s payment=%s", order_id, payment_id)
        return {"ok": True}

    ok = finalize_deposit_from_nowpayments(db, deposit, body, defer_commit=True)
    if not ok:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment notification",
        )

    db.commit()
    logger.info(
        "NOWPayments IPN processed deposit=%s status=%s payment_status=%s",
        deposit.id,
        deposit.status.value,
        body.get("payment_status"),
    )
    return {"ok": True}
