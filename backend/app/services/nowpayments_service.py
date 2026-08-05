"""
NOWPayments integration — create payments, poll status, verify IPN callbacks, and affiliate payouts.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import pyotp
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import Deposit, DepositStatus

logger = logging.getLogger(__name__)

NOWPAYMENTS_API_BASE = "https://api.nowpayments.io/v1"
NOWPAYMENTS_SANDBOX_BASE = "https://api-sandbox.nowpayments.io/v1"

_jwt_cache: dict[str, float | str | None] = {"token": None, "expires_at": 0.0}
_jwt_lock = asyncio.Lock()

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


# NOWPayments tickers (lowercase). BEP20 USDT on BSC is usdtbsc — not usdtbep20.
_PAY_CURRENCY_ALIASES = {
    "usdtbep20": "usdtbsc",
    "usdtbep": "usdtbsc",
    "usdtbsc": "usdtbsc",
    "usdttrc20": "usdttrc20",
    "usdterc20": "usdterc20",
}


def normalize_pay_currency(code: Optional[str]) -> Optional[str]:
    """Map common labels to NOWPayments pay_currency tickers."""
    if not code:
        return None
    compact = code.strip().lower().replace("-", "").replace("_", "")
    return _PAY_CURRENCY_ALIASES.get(compact, code.strip().lower())


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


def _expected_fiat_amount(deposit: Deposit, payload: Dict[str, Any]) -> float:
    if payload.get("price_amount") is not None:
        return float(payload["price_amount"])
    return float(deposit.amount or 0)


def _received_fiat_amount(payload: Dict[str, Any], expected_fiat: float) -> Optional[float]:
    """Estimate fiat received from NOWPayments payload (USD invoice amounts)."""
    price_currency = str(payload.get("price_currency") or "usd").lower()
    outcome_currency = str(payload.get("outcome_currency") or "").lower()

    outcome_amount = payload.get("outcome_amount")
    if outcome_amount is not None and outcome_currency in ("usd", price_currency):
        return float(outcome_amount)

    actually_paid = payload.get("actually_paid")
    pay_amount = payload.get("pay_amount")
    if actually_paid is not None and pay_amount:
        pay_f = float(pay_amount)
        if pay_f > 0:
            price_base = (
                float(payload["price_amount"])
                if payload.get("price_amount") is not None
                else expected_fiat
            )
            return price_base * (float(actually_paid) / pay_f)

    return None


def within_underpayment_tolerance(deposit: Deposit, payload: Dict[str, Any]) -> bool:
    """
    True when user underpaid by at most NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD
    (e.g. $9.50–$9.99 on a $10 invoice). Overpayments always pass.
    """
    expected = _expected_fiat_amount(deposit, payload)
    if expected <= 0:
        return False

    received = _received_fiat_amount(payload, expected)
    if received is None or received <= 0:
        return False

    tolerance = max(0.0, float(settings.NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD))
    shortfall = expected - received
    return shortfall <= tolerance


def resolve_deposit_status_from_provider(deposit: Deposit, payload: Dict[str, Any]) -> DepositStatus:
    """Map provider status, with tolerance acceptance for small underpayments."""
    mapped = map_nowpayments_status(
        str(payload.get("payment_status") or payload.get("status") or "")
    )
    if mapped == DepositStatus.PARTIALLY_PAID and within_underpayment_tolerance(deposit, payload):
        logger.info(
            "Deposit %s accepted as paid: received ~$%.2f on $%.2f invoice (tolerance $%.2f)",
            deposit.id,
            _received_fiat_amount(payload, _expected_fiat_amount(deposit, payload)) or 0,
            _expected_fiat_amount(deposit, payload),
            settings.NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD,
        )
        return DepositStatus.VALIDATED
    return mapped


def verify_ipn_signature(body: Dict[str, Any], signature: str) -> bool:
    secret = (settings.NOWPAYMENTS_IPN_SECRET or "").strip()
    if not secret or not signature:
        return False
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    computed = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed, signature)


def apply_nowpayments_payload_to_deposit(deposit: Deposit, payload: Dict[str, Any]) -> DepositStatus:
    new_status = resolve_deposit_status_from_provider(deposit, payload)

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
        from app.services.commission_distribution import process_payment_validation

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
        payload["pay_currency"] = normalize_pay_currency(pay_currency) or pay_currency.lower()
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


# ---------------------------------------------------------------------------
# Affiliate payouts (NOWPayments Payout API + TOTP verification)
# ---------------------------------------------------------------------------

def _payout_base() -> str:
    return NOWPAYMENTS_SANDBOX_BASE if settings.NOWPAYMENTS_SANDBOX else NOWPAYMENTS_API_BASE


def payouts_configured() -> bool:
    return bool((settings.NOWPAYMENTS_PAYOUT_API_KEY or "").strip())


def _get_payout_jwt_sync() -> str:
    if not settings.NOWPAYMENTS_EMAIL or not settings.NOWPAYMENTS_PASSWORD:
        raise NowPaymentsError("NOWPAYMENTS_EMAIL/NOWPAYMENTS_PASSWORD required for payouts.")

    if _jwt_cache["token"] and time.time() < float(_jwt_cache["expires_at"] or 0):
        return str(_jwt_cache["token"])

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_payout_base()}/auth",
            json={"email": settings.NOWPAYMENTS_EMAIL, "password": settings.NOWPAYMENTS_PASSWORD},
        )
    if resp.status_code >= 400:
        raise NowPaymentsError(f"NowPayments POST /auth -> {resp.status_code}: {resp.text[:300]}")
    token = resp.json().get("token")
    if not token:
        raise NowPaymentsError("NowPayments /v1/auth: token missing from response.")

    _jwt_cache["token"] = token
    _jwt_cache["expires_at"] = time.time() + 4.5 * 60
    return str(token)


async def _get_payout_jwt() -> str:
    if not settings.NOWPAYMENTS_EMAIL or not settings.NOWPAYMENTS_PASSWORD:
        raise NowPaymentsError("NOWPAYMENTS_EMAIL/NOWPAYMENTS_PASSWORD required for payouts.")

    async with _jwt_lock:
        if _jwt_cache["token"] and time.time() < float(_jwt_cache["expires_at"] or 0):
            return str(_jwt_cache["token"])

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_payout_base()}/auth",
                json={"email": settings.NOWPAYMENTS_EMAIL, "password": settings.NOWPAYMENTS_PASSWORD},
            )
        if resp.status_code >= 400:
            raise NowPaymentsError(f"NowPayments POST /auth -> {resp.status_code}: {resp.text[:300]}")
        token = resp.json().get("token")
        if not token:
            raise NowPaymentsError("NowPayments /v1/auth: token missing from response.")

        _jwt_cache["token"] = token
        _jwt_cache["expires_at"] = time.time() + 4.5 * 60
        return str(token)


def _payout_headers_sync() -> Dict[str, str]:
    token = _get_payout_jwt_sync()
    return {
        "x-api-key": settings.NOWPAYMENTS_PAYOUT_API_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _payout_headers() -> Dict[str, str]:
    token = await _get_payout_jwt()
    return {
        "x-api-key": settings.NOWPAYMENTS_PAYOUT_API_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def send_payout_sync(*, withdrawals: List[dict]) -> dict:
    if not payouts_configured():
        raise NowPaymentsError("NOWPAYMENTS_PAYOUT_API_KEY is not configured.")

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{_payout_base()}/payout",
            headers=_payout_headers_sync(),
            json={"withdrawals": withdrawals},
        )
    if resp.status_code >= 400:
        raise NowPaymentsError(f"NowPayments POST /payout -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def send_payout(*, withdrawals: List[dict]) -> dict:
    if not payouts_configured():
        raise NowPaymentsError("NOWPAYMENTS_PAYOUT_API_KEY is not configured.")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_payout_base()}/payout",
            headers=await _payout_headers(),
            json={"withdrawals": withdrawals},
        )
    if resp.status_code >= 400:
        raise NowPaymentsError(f"NowPayments POST /payout -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def verify_payout_sync(batch_withdrawal_id: str) -> dict:
    if not settings.NOWPAYMENTS_PAYOUT_TOTP_SECRET:
        raise NowPaymentsError("NOWPAYMENTS_PAYOUT_TOTP_SECRET is not configured.")

    code = pyotp.TOTP(settings.NOWPAYMENTS_PAYOUT_TOTP_SECRET).now()
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_payout_base()}/payout/{batch_withdrawal_id}/verify",
            headers=_payout_headers_sync(),
            json={"verification_code": code},
        )
    if resp.status_code >= 400:
        raise NowPaymentsError(
            f"NowPayments POST /payout/{batch_withdrawal_id}/verify -> {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


async def verify_payout(batch_withdrawal_id: str) -> dict:
    if not settings.NOWPAYMENTS_PAYOUT_TOTP_SECRET:
        raise NowPaymentsError("NOWPAYMENTS_PAYOUT_TOTP_SECRET is not configured.")

    code = pyotp.TOTP(settings.NOWPAYMENTS_PAYOUT_TOTP_SECRET).now()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_payout_base()}/payout/{batch_withdrawal_id}/verify",
            headers=await _payout_headers(),
            json={"verification_code": code},
        )
    if resp.status_code >= 400:
        raise NowPaymentsError(
            f"NowPayments POST /payout/{batch_withdrawal_id}/verify -> {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def send_single_payout_sync(
    *,
    wallet_address: str,
    amount_usd: float,
    currency: str = "usdtbsc",
) -> dict:
    """
    Create + verify a single USDT payout. Never send extra_id for BEP20 — it causes silent REJECTED.
    """
    pay_currency = normalize_pay_currency(currency) or "usdtbsc"
    withdrawal = {
        "address": wallet_address,
        "amount": round(amount_usd, 2),
        "currency": pay_currency,
    }
    created = send_payout_sync(withdrawals=[withdrawal])
    batch_id = str(created.get("id") or created.get("batch_withdrawal_id") or "")
    if not batch_id:
        raise NowPaymentsError("NowPayments payout: batch id missing from create response.")
    verify_payout_sync(batch_id)
    return created


async def send_single_payout(
    *,
    wallet_address: str,
    amount_usd: float,
    currency: str = "usdtbsc",
) -> dict:
    pay_currency = normalize_pay_currency(currency) or "usdtbsc"
    withdrawal = {
        "address": wallet_address,
        "amount": round(amount_usd, 2),
        "currency": pay_currency,
    }
    created = await send_payout(withdrawals=[withdrawal])
    batch_id = str(created.get("id") or created.get("batch_withdrawal_id") or "")
    if not batch_id:
        raise NowPaymentsError("NowPayments payout: batch id missing from create response.")
    await verify_payout(batch_id)
    return created
