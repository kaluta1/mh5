"""
Payment provider webhooks (NOWPayments IPN).
"""
import json
import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip
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

MAX_IPN_BODY_BYTES = 64 * 1024

# Abuse limit for callbacks that FAIL verification. A correctly signed
# notification is never counted and never refused by it, whatever else came
# from the same address, so a provider retry burst cannot be lost here. Once an
# address has sent too many unsigned or wrongly signed requests, each further
# rejected one is answered 429 without a log line or a database write (every
# rejection otherwise costs a counter update); an unsigned one is not even
# compared.
BAD_CALLBACK_LIMIT, BAD_CALLBACK_WINDOW = 30, 60          # rejected callbacks per address per minute
_MAX_TRACKED_ADDRESSES = 10_000
_bad_callbacks: dict[str, deque] = defaultdict(deque)


def _recent_bad_callbacks(address: str, now: float) -> int:
    hits = _bad_callbacks.get(address)
    if not hits:
        return 0
    while hits and hits[0] <= now - BAD_CALLBACK_WINDOW:
        hits.popleft()
    if not hits:
        _bad_callbacks.pop(address, None)
        return 0
    return len(hits)


def _note_bad_callback(address: str, now: float) -> None:
    if len(_bad_callbacks) >= _MAX_TRACKED_ADDRESSES and address not in _bad_callbacks:
        _bad_callbacks.pop(next(iter(_bad_callbacks)), None)
    _bad_callbacks[address].append(now)


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
    sender, started = client_ip(request), time.monotonic()
    # Over the limit, a callback is still VERIFIED (a correctly signed one is
    # always processed); only the bookkeeping of yet another rejected one is
    # skipped, and it is answered 429.
    throttled = _recent_bad_callbacks(sender, started) >= BAD_CALLBACK_LIMIT

    def reject(outcome: str, status_code: int, detail: str) -> HTTPException:
        if throttled:
            return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many rejected callbacks")
        _note_bad_callback(sender, started)
        _count(db, outcome)
        return HTTPException(status_code=status_code, detail=detail)

    raw = await request.body()
    if len(raw) > MAX_IPN_BODY_BYTES:
        # A provider notification is a few hundred bytes. Nothing larger is parsed.
        raise reject("INVALID_JSON", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Payload too large")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise reject("INVALID_JSON", status.HTTP_400_BAD_REQUEST, "Invalid JSON") from exc
    if not isinstance(body, dict):
        raise reject("INVALID_JSON", status.HTTP_400_BAD_REQUEST, "Invalid JSON")

    signature = request.headers.get("x-nowpayments-sig", "")
    secret = "" if throttled and not signature else (payment_config.ipn_secret(db) or "")
    if not verify_ipn_signature(body, signature, secret=secret, raw=raw):
        if not throttled:
            logger.warning("NOWPayments IPN rejected: invalid signature")
        raise reject("REJECTED_SIGNATURE", status.HTTP_403_FORBIDDEN, "Invalid signature")

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
        matches = (
            db.query(Deposit)
            .filter(Deposit.external_payment_id == payment_id)
            .with_for_update()
            .limit(2)
            .all()
        )
        if len(matches) > 1:
            # The column has no unique rule yet; a provider payment that more than
            # one deposit claims is never credited to a guess.
            db.rollback()
            logger.error("NOWPayments IPN payment=%s matches more than one deposit; nothing applied", payment_id)
            _count(db, "IDENTITY_REJECTED")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Provider payment matches more than one deposit")
        deposit = matches[0] if matches else None

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
