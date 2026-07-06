"""
NOWPayments integration — create payments, poll status, verify IPN callbacks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import Deposit, DepositStatus
from app.services.commission_distribution import process_payment_validation

logger = logging.getLogger(__name__)

NOWPAYMENTS_API_BASE = "https://api.nowpayments.io/v1"
NOWPAYMENTS_SANDBOX_BASE = "https://api-sandbox.nowpayments.io/v1"

FINISHED_STATUSES = {"finished", "confirmed"}
PENDING_STATUSES = {"waiting", "confirming", "sending"}
PARTIAL_STATUSES = {"partially_paid"}
FAILED_STATUSES = {"failed", "refunded"}
EXPIRED_STATUSES = {"expired"}


class NowPaymentsError(Exception):
    """Raised when NOWPayments API calls fail."""


def api_base() -> str:
    if settings.NOWPAYMENTS_SANDBOX:
        return NOWPAYMENTS_SANDBOX_BASE
    return NOWPAYMENTS_API_BASE


def _headers() -> Dict[str, str]:
    key = (settings.NOWPAYMENTS_API_KEY or "").strip()
    if not key:
        raise NowPaymentsError("NOWPAYMENTS_API_KEY is not configured")
    return {"x-api-key": key, "Content-Type": "application/json"}


def build_order_id() -> str:
    return f"mh5-{uuid.uuid4().hex}"


def ipn_callback_url() -> str:
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    return f"{base}/api/v1/webhooks/nowpayments"


def map_nowpayments_status(payment_status: str) -> DepositStatus:
    status = (payment_status or "").lower()
    if status in FINISHED_STATUSES:
        return DepositStatus.VALIDATED
    if status in PARTIAL_STATUSES:
        return DepositStatus.PARTIALLY_PAID
    if status in EXPIRED_STATUSES:
        return DepositStatus.EXPIRED
    if status in FAILED_STATUSES:
        return DepositStatus.FAILED
    return DepositStatus.PENDING


def verify_ipn_signature(body: Dict[str, Any], signature: str) -> bool:
    secret = (settings.NOWPAYMENTS_IPN_SECRET or "").strip()
    if not secret or not signature:
        return False
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    computed = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature)


def apply_nowpayments_payload_to_deposit(deposit: Deposit, payload: Dict[str, Any]) -> DepositStatus:
    payment_status = str(payload.get("payment_status") or payload.get("status") or "")
    new_status = map_nowpayments_status(payment_status)

    pay_address = payload.get("pay_address")
    if pay_address:
        deposit.payment_address = str(pay_address)

    pay_amount = payload.get("pay_amount")
    if pay_amount is not None:
        deposit.crypto_amount = str(pay_amount)

    pay_currency = payload.get("pay_currency")
    if pay_currency:
        deposit.crypto_currency = str(pay_currency).upper()

    payment_id = payload.get("payment_id")
    if payment_id:
        deposit.external_payment_id = str(payment_id)

    payin_hash = payload.get("payin_hash") or payload.get("outcome_hash")
    if payin_hash:
        deposit.tx_hash = str(payin_hash)

    return new_status


def finalize_deposit_from_nowpayments(
    db: Session,
    deposit: Deposit,
    payload: Dict[str, Any],
    *,
    defer_commit: bool = False,
) -> bool:
    """Apply provider payload and run business validation when payment is finished."""
    if deposit.status == DepositStatus.VALIDATED:
        return True

    new_status = apply_nowpayments_payload_to_deposit(deposit, payload)

    if new_status == DepositStatus.VALIDATED:
        deposit.status = DepositStatus.VALIDATED
        deposit.validated_at = datetime.utcnow()
        ok = process_payment_validation(db, deposit, defer_commit=defer_commit)
        if not ok:
            return False
        return True

    if new_status != deposit.status:
        deposit.status = new_status
    return True


async def get_available_currencies() -> list[str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{api_base()}/currencies", headers=_headers())
        if response.status_code >= 400:
            raise NowPaymentsError(response.text or "Failed to fetch currencies")
        data = response.json()
        currencies = data.get("currencies") if isinstance(data, dict) else data
        if isinstance(currencies, list):
            return [str(item).lower() for item in currencies]
        return []


async def create_payment(
    *,
    price_amount: float,
    price_currency: str,
    order_id: str,
    order_description: str,
    pay_currency: Optional[str] = None,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "price_amount": price_amount,
        "price_currency": price_currency.lower(),
        "order_id": order_id,
        "order_description": order_description,
        "ipn_callback_url": ipn_callback_url(),
    }
    if pay_currency:
        payload["pay_currency"] = pay_currency.lower()
    if success_url:
        payload["success_url"] = success_url
    if cancel_url:
        payload["cancel_url"] = cancel_url

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{api_base()}/payment", headers=_headers(), json=payload)
        if response.status_code >= 400:
            logger.error("NOWPayments create failed: %s %s", response.status_code, response.text)
            raise NowPaymentsError(response.text or "NOWPayments payment creation failed")
        return response.json()


async def get_payment_status(payment_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{api_base()}/payment/{payment_id}", headers=_headers())
        if response.status_code >= 400:
            raise NowPaymentsError(response.text or "Failed to fetch payment status")
        return response.json()


def deposit_status_payload(deposit: Deposit, provider_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    provider = provider_payload or {}
    payment_status = str(
        provider.get("payment_status")
        or provider.get("status")
        or deposit.status.value
    )
    return {
        "deposit_id": deposit.id,
        "status": deposit.status.value,
        "payment_status": payment_status,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
        "order_id": deposit.order_id,
        "payment_id": deposit.external_payment_id,
        "pay_address": deposit.payment_address or provider.get("pay_address"),
        "pay_amount": deposit.crypto_amount or provider.get("pay_amount"),
        "pay_currency": (deposit.crypto_currency or provider.get("pay_currency") or "").lower(),
        "price_amount": float(deposit.amount) if deposit.amount else 0,
        "price_currency": (deposit.currency or "usd").lower(),
        "tx_hash": deposit.tx_hash,
        "invoice_url": provider.get("invoice_url"),
    }


async def sync_deposit_with_provider(db: Session, deposit: Deposit) -> Dict[str, Any]:
    if not deposit.external_payment_id:
        return deposit_status_payload(deposit)

    payload = await get_payment_status(deposit.external_payment_id)
    ok = finalize_deposit_from_nowpayments(db, deposit, payload, defer_commit=True)
    if not ok:
        db.rollback()
        raise NowPaymentsError("Failed to finalize deposit after provider sync")
    return deposit_status_payload(deposit, payload)
