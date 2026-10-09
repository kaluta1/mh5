"""
NOWPayments integration — create payments, poll status, verify IPN callbacks, and affiliate payouts.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
import pyotp
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.payment import Deposit, DepositStatus
from app.services.financial_integrity import (
    FinancialIntegrityError,
    money,
    validate_provider_payment_identity,
)

logger = logging.getLogger(__name__)

NOWPAYMENTS_API_BASE = "https://api.nowpayments.io/v1"
NOWPAYMENTS_SANDBOX_BASE = "https://api-sandbox.nowpayments.io/v1"

PAYMENT_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=5.0, read=45.0, write=10.0, pool=5.0)
STATUS_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=5.0, read=20.0, write=10.0, pool=5.0)
PAYOUT_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=5.0, read=20.0, write=10.0, pool=5.0)
AUTH_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0, read=10.0, write=10.0, pool=5.0)

FINISHED_STATUSES = {"finished", "confirmed"}
PENDING_STATUSES = {"waiting", "confirming", "sending"}
PARTIAL_STATUSES = {"partially_paid"}
FAILED_STATUSES = {"failed", "refunded"}
EXPIRED_STATUSES = {"expired"}


class NowPaymentsError(Exception):
    """Raised when NOWPayments API calls fail. `status_code` is the HTTP status
    the provider answered with (None when there was no answer at all), `code`
    the provider's own error code when it sent one, `stage` the step that
    failed (auth / create / verify / read) and `ip_refused` whether it refused
    this server's IP address. The message never carries a credential or a
    response body."""

    def __init__(self, message: str = "", *, status_code: Optional[int] = None, code: Optional[str] = None,
                 stage: Optional[str] = None, ip_refused: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.stage = stage
        self.ip_refused = ip_refused


def api_base() -> str:
    if settings.NOWPAYMENTS_SANDBOX:
        return NOWPAYMENTS_SANDBOX_BASE
    return NOWPAYMENTS_API_BASE


def _headers() -> Dict[str, str]:
    # The pay-in key comes from the ONE source selected in Finance & Payments
    # (the environment unless an administrator switched it to the database).
    from app.services import payment_config

    key = (payment_config.payin_runtime().api_key or "").strip()
    if not key:
        raise NowPaymentsError("The NOWPayments pay-in API key is not configured")
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


def _expected_fiat_amount(deposit: Deposit, payload: Dict[str, Any]) -> Decimal:
    if payload.get("price_amount") is not None:
        return money(payload["price_amount"])
    return money(deposit.amount or 0)


def _received_fiat_amount(payload: Dict[str, Any], expected_fiat: Decimal) -> Optional[Decimal]:
    """Estimate fiat received from NOWPayments payload (USD invoice amounts)."""
    price_currency = str(payload.get("price_currency") or "usd").lower()
    outcome_currency = str(payload.get("outcome_currency") or "").lower()

    outcome_amount = payload.get("outcome_amount")
    if outcome_amount is not None and outcome_currency in ("usd", price_currency):
        return money(outcome_amount)

    actually_paid = payload.get("actually_paid")
    pay_amount = payload.get("pay_amount")
    if actually_paid is not None and pay_amount:
        pay_f = Decimal(str(pay_amount))
        if pay_f > 0:
            price_base = (
                money(payload["price_amount"])
                if payload.get("price_amount") is not None
                else expected_fiat
            )
            return money(price_base * (Decimal(str(actually_paid)) / pay_f))

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

    tolerance = max(Decimal("0.00"), money(settings.NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD))
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


# ---------------------------------------------------------------------------
# IPN signature
#
# NOWPayments documents: "Sort the POST request by keys and convert it to
# string using JSON.stringify ... Sign a string with an IPN-secret key with
# HMAC and sha-512", and publishes a Node, a PHP and a Python example. The
# examples do NOT produce the same string for every body:
#   * JSON.stringify keeps non-ASCII characters as they are (an em dash stays
#     an em dash); Python's json.dumps writes them as \uXXXX escapes;
#   * JavaScript writes 1e-7 where Python writes 1e-07;
#   * the Node example rebuilds an array as an object keyed by its indexes.
# The provider signs with its own serializer, so a callback is accepted when
# its signature equals the HMAC of ANY of these canonical forms. Each form is
# still an HMAC-SHA512 with the IPN secret over the whole sorted body: nothing
# is accepted unsigned and no field is left out.
# ---------------------------------------------------------------------------

class _JsonNumber(str):
    """A JSON number kept as the exact characters that were received."""


def _reject_constant(_name: str):
    raise ValueError("not a JSON value")


def _js_number(token: str) -> str:
    """The number as JavaScript's JSON.stringify writes it."""
    if re.fullmatch(r"-?(0|[1-9]\d{0,14})", token):
        return "0" if token == "-0" else token
    value = float(token)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("not a JSON number")
    if value == 0:
        return "0"
    sign, digits, exponent = Decimal(repr(value)).as_tuple()
    text = "".join(str(d) for d in digits).rstrip("0") or "0"
    exponent += len(digits) - len(text)
    k, n = len(text), len(text) + exponent            # ECMA-262 Number::toString
    if k <= n <= 21:
        out = text + "0" * (n - k)
    elif 0 < n <= 21:
        out = f"{text[:n]}.{text[n:]}"
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + text
    else:
        e = n - 1
        mantissa = text[0] + ("." + text[1:] if k > 1 else "")
        out = f"{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"
    return ("-" if sign else "") + out


def _canonical(value: Any, *, js_numbers: bool, arrays_as_objects: bool) -> str:
    if isinstance(value, _JsonNumber):
        return _js_number(str(value)) if js_numbers else str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if value is True or value is False:
        return "true" if value else "false"
    if isinstance(value, list):
        items = [_canonical(v, js_numbers=js_numbers, arrays_as_objects=arrays_as_objects) for v in value]
        if arrays_as_objects:
            return "{" + ",".join(f'"{i}":{item}' for i, item in enumerate(items)) + "}"
        return "[" + ",".join(items) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(key, ensure_ascii=False) + ":"
            + _canonical(value[key], js_numbers=js_numbers, arrays_as_objects=arrays_as_objects)
            for key in sorted(value)) + "}"
    raise ValueError("not a JSON value")


def ipn_canonical_forms(body: Dict[str, Any], raw: Optional[bytes] = None) -> List[str]:
    """Every documented canonical string for one callback body, without
    duplicates. `raw` is the request body exactly as received; with it the
    numbers are taken from the bytes on the wire instead of from a float."""
    forms: List[str] = []

    def add(text: str) -> None:
        if text not in forms:
            forms.append(text)

    if raw is not None:
        try:
            exact = json.loads(raw.decode("utf-8"), parse_float=_JsonNumber, parse_int=_JsonNumber,
                               parse_constant=_reject_constant)
            if isinstance(exact, dict):
                for arrays_as_objects in (False, True):
                    for js_numbers in (False, True):
                        add(_canonical(exact, js_numbers=js_numbers, arrays_as_objects=arrays_as_objects))
        except (ValueError, UnicodeDecodeError, RecursionError):
            pass
    try:
        # The provider's Python example (non-ASCII as \uXXXX), then the same with it kept.
        add(json.dumps(body, sort_keys=True, separators=(",", ":")))
        add(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError):
        pass
    return forms


def verify_ipn_signature(body: Dict[str, Any], signature: str, *, secret: Optional[str] = None,
                         raw: Optional[bytes] = None) -> bool:
    """HMAC-SHA512 (hex, header x-nowpayments-sig) over the sorted JSON body,
    compared in constant time. `secret` is the IPN secret in force
    (payment_config.ipn_secret); None means the environment secret. A missing
    secret, a missing or malformed signature, or a body that is not a JSON
    object is refused."""
    secret = (settings.NOWPAYMENTS_IPN_SECRET or "").strip() if secret is None else secret.strip()
    received = str(signature or "").strip().lower()
    if not secret or not re.fullmatch(r"[0-9a-f]{128}", received) or not isinstance(body, dict):
        return False
    key = secret.encode("utf-8")
    matched = False
    for form in ipn_canonical_forms(body, raw):
        computed = hmac.new(key, form.encode("utf-8"), hashlib.sha512).hexdigest()
        matched = hmac.compare_digest(computed, received) or matched
    return matched


def apply_nowpayments_payload_to_deposit(deposit: Deposit, payload: Dict[str, Any]) -> DepositStatus:
    validate_provider_payment_identity(deposit, payload)
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
    provider_status = str(payload.get("payment_status") or payload.get("status") or "").lower()
    validate_provider_payment_identity(deposit, payload)
    if provider_status == "refunded":
        from app.services.financial_reversal import reverse_provider_refund

        return reverse_provider_refund(db, deposit, payload, defer_commit=defer_commit)

    if deposit.status == DepositStatus.VALIDATED:
        return True

    from app.services.financial_reversal import _REFUND_MARKER

    if _REFUND_MARKER in str(deposit.admin_notes or ""):
        # Already refunded and reversed. An older "finished" notification that
        # arrives late (or is replayed) must not validate the deposit again.
        logger.warning("Deposit %s was refunded; ignoring provider status %s", deposit.id, provider_status)
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
    async with httpx.AsyncClient(timeout=STATUS_HTTP_TIMEOUT) as client:
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
    price_amount: Decimal,
    price_currency: str,
    order_id: str,
    order_description: str,
    pay_currency: Optional[str] = None,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> Dict[str, Any]:
    from app.services import payment_config

    if not payment_config.payin_runtime().provider_enabled:
        raise NowPaymentsError("Crypto payments are switched off (Finance & Payments > Payment Providers)")
    payload: Dict[str, Any] = {
        "price_amount": float(money(price_amount)),
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

    async with httpx.AsyncClient(timeout=PAYMENT_HTTP_TIMEOUT) as client:
        response = await client.post(f"{api_base()}/payment", headers=_headers(), json=payload)
        if response.status_code >= 400:
            logger.error("NOWPayments create failed: %s %s", response.status_code, response.text)
            raise NowPaymentsError(response.text or "NOWPayments payment creation failed",
                                   status_code=response.status_code, stage="create")
        try:
            created = response.json()
        except ValueError as exc:
            raise NowPaymentsError("NOWPayments payment creation returned an unreadable answer",
                                   stage="create") from exc
        if not isinstance(created, dict) or not created.get("payment_id"):
            # Without the provider's payment id the deposit could never be polled.
            raise NowPaymentsError("NOWPayments payment creation returned no payment id", stage="create")
        return created


async def get_payment_status(payment_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=STATUS_HTTP_TIMEOUT) as client:
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

    deposit_id = int(deposit.id)
    payment_id = str(deposit.external_payment_id)
    # Release the read transaction before waiting on the remote provider.
    db.rollback()
    payload = await get_payment_status(payment_id)
    deposit = (
        db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
    )
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


def payout_api_key() -> str:
    """Same NOWPayments account can use the pay-in API key for payouts."""
    return (
        (settings.NOWPAYMENTS_PAYOUT_API_KEY or "").strip()
        or (settings.NOWPAYMENTS_API_KEY or "").strip()
    )


def payout_totp_secret() -> str:
    return (settings.NOWPAYMENTS_PAYOUT_TOTP_SECRET or "").replace(" ", "").strip()


def payout_config_status() -> Dict[str, Any]:
    """Which NOWPayments payout credentials are present (no secret values)."""
    has_payin_key = bool((settings.NOWPAYMENTS_API_KEY or "").strip())
    has_ipn = bool((settings.NOWPAYMENTS_IPN_SECRET or "").strip())
    has_payout_key = bool(payout_api_key())
    has_email = bool((settings.NOWPAYMENTS_EMAIL or "").strip())
    has_password = bool((settings.NOWPAYMENTS_PASSWORD or "").strip())
    has_totp = bool(payout_totp_secret())
    missing: List[str] = []
    if not has_payout_key:
        missing.append("NOWPAYMENTS_PAYOUT_API_KEY (or NOWPAYMENTS_API_KEY)")
    if not has_email:
        missing.append("NOWPAYMENTS_EMAIL")
    if not has_password:
        missing.append("NOWPAYMENTS_PASSWORD")
    if not has_totp:
        missing.append("NOWPAYMENTS_PAYOUT_TOTP_SECRET")
    return {
        "payouts_ready": not missing,
        "has_api_key": has_payin_key,
        "has_ipn_secret": has_ipn,
        "has_payout_api_key": has_payout_key,
        "has_email": has_email,
        "has_password": has_password,
        "has_totp_secret": has_totp,
        "missing": missing,
        "hint": (
            "NOWPayments payouts need Authenticator 2FA (not email). "
            "In the NOWPayments dashboard: Settings → 2FA → Authenticator app, "
            "save the secret as NOWPAYMENTS_PAYOUT_TOTP_SECRET, plus account email/password."
        ),
    }


def payouts_configured() -> bool:
    """Ready to create + verify payouts (SmartBlogger: API key + JWT auth + TOTP)."""
    return bool(payout_config_status()["payouts_ready"])


def _retired_payout_path(*_args, **_kwargs):
    """The earlier direct payout senders. They used the environment credentials
    without the Finance & Payments switches, sent no unique reference and let
    the payout key fall back to the pay-in key. They are kept only as names:
    every one of them refuses, so the cashout engine below is the single path
    that can ask the provider to send money."""
    raise NowPaymentsError("This payout path is retired. Crypto cashouts are sent only by the cashout engine.")


_get_payout_jwt_sync = _retired_payout_path
send_payout_sync = _retired_payout_path
verify_payout_sync = _retired_payout_path
send_single_payout_sync = _retired_payout_path


async def send_payout(*_args, **_kwargs) -> dict:
    return _retired_payout_path()


async def verify_payout(*_args, **_kwargs) -> dict:
    return _retired_payout_path()


async def send_single_payout(*_args, **_kwargs) -> dict:
    return _retired_payout_path()


# ---------------------------------------------------------------------------
# Payout engine adapter (dual cashout). Nothing here runs unless the engine is
# enabled, and nothing here decides to pay: the engine does.
#
# What the provider documents (Mass payouts) and this adapter follows:
#   POST /v1/auth                        email + password -> JWT, "JWT tokens
#                                        expire in 5 minutes"
#   GET  /v1/balance                     x-api-key; {ticker: {amount, pendingAmount}}
#   GET  /v1/payout-withdrawal/min-amount/:coin   x-api-key; {success, result}
#   GET  /v1/payout/fee?currency&amount  x-api-key; {currency, fee} (an estimate)
#   POST /v1/payout/validate-address     x-api-key; 200 "OK" / 400
#   POST /v1/payout                      x-api-key + Bearer; {withdrawals: [...]}
#                                        -> {id: <batch>, withdrawals: [{id, status, ...}]}
#   POST /v1/payout/:batch/verify        x-api-key + Bearer; {verification_code}
#                                        10 attempts; an unverified payout is
#                                        rejected automatically after an hour
#   GET  /v1/payout/:id                  x-api-key; {id, withdrawals: [{status, hash, ...}]}
#   GET  /v1/payout                      x-api-key; {payouts: [...]} (list)
# Payout statuses: creating, waiting, processing, sending, finished, failed,
# rejected. ONLY finished and rejected are final; a failed payout may still be
# processed by the provider.
#
# NOT documented, therefore not relied on: whether the provider refuses a
# second payout with the same unique_external_id, and whether GET /v1/payout/:id
# takes the batch id or the single payout id (the engine sends one withdrawal
# per batch and reads the batch it created).
#
# Every helper takes the payout credentials resolved by payment_config for
# that run (`credentials.get(name)`). They are never read from the pay-in key:
# a payout needs its own API key, the account login and the authenticator
# secret. The login only yields a short-lived session token, kept in memory
# for under five minutes; the second factor is a fresh one-time code computed
# for each confirmation and is never stored, logged or reused.
# ---------------------------------------------------------------------------

_engine_session: dict[str, Any] = {"token": None, "expires_at": 0.0, "owner": None}
_SESSION_SECONDS = 4.5 * 60          # the provider's token lives 5 minutes


def forget_payout_session() -> None:
    """Drop the cached provider session (called when credentials change)."""
    _engine_session.update(token=None, expires_at=0.0, owner=None)


def _require(credentials, name: str) -> str:
    value = credentials.get(name) if credentials is not None else None
    if not value:
        raise NowPaymentsError(f"Payout credential {name} is not configured")
    return value


def _provider_code(resp) -> Optional[str]:
    """The provider's own error code (e.g. BAD_CREATE_WITHDRAWAL_REQUEST), never its message."""
    try:
        data = resp.json()
    except ValueError:
        return None
    code = data.get("code") if isinstance(data, dict) else None
    return code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,60}", code) else None


def _refused(resp, action: str, stage: str) -> NowPaymentsError:
    """A sanitized error for a 4xx/5xx answer: status and code only."""
    ip_refused = resp.status_code == 403 and bool(re.search(r"\bip\b", resp.text or "", re.IGNORECASE))
    return NowPaymentsError(f"NowPayments {action} -> {resp.status_code}", status_code=resp.status_code,
                            code=_provider_code(resp), stage=stage, ip_refused=ip_refused)


def _engine_token_sync(credentials, *, fresh: bool = False) -> str:
    email, password = _require(credentials, "PAYOUT_EMAIL"), _require(credentials, "PAYOUT_PASSWORD")
    owner = hashlib.sha256(f"{_payout_base()}|{email}|{password}".encode("utf-8")).hexdigest()
    if (not fresh and _engine_session["token"] and _engine_session["owner"] == owner
            and time.time() < float(_engine_session["expires_at"] or 0)):
        return str(_engine_session["token"])
    with httpx.Client(timeout=AUTH_HTTP_TIMEOUT) as client:
        resp = client.post(f"{_payout_base()}/auth", json={"email": email, "password": password})
    if resp.status_code >= 400:
        forget_payout_session()
        raise _refused(resp, "POST /auth", "auth")
    try:
        token = resp.json().get("token")
    except (ValueError, AttributeError):
        token = None
    if not token:
        raise NowPaymentsError("NowPayments /v1/auth: token missing from response.", stage="auth")
    _engine_session.update(token=token, expires_at=time.time() + _SESSION_SECONDS, owner=owner)
    return str(token)


def payout_login_check_sync(credentials) -> None:
    """Log in with the payout account and discard the session. Creates no
    payout and moves nothing; it proves only that the login is accepted (the
    second factor can be proven only by a real payout confirmation)."""
    try:
        _engine_token_sync(credentials, fresh=True)
    finally:
        forget_payout_session()


def _engine_headers(credentials, *, jwt: bool) -> Dict[str, str]:
    headers = {"x-api-key": _require(credentials, "PAYOUT_API_KEY"), "Content-Type": "application/json"}
    if jwt:
        headers["Authorization"] = f"Bearer {_engine_token_sync(credentials)}"
    return headers


def _payout_get_sync(path: str, credentials, *, jwt: bool = False, params: Optional[dict] = None) -> Any:
    with httpx.Client(timeout=STATUS_HTTP_TIMEOUT) as client:
        resp = client.get(f"{_payout_base()}/{path}", headers=_engine_headers(credentials, jwt=jwt), params=params)
    if resp.status_code >= 400:
        raise _refused(resp, f"GET /{path}", "read")
    try:
        return resp.json()
    except ValueError as exc:
        raise NowPaymentsError(f"NowPayments GET /{path}: unreadable answer", stage="read") from exc


def _decimal(value: Any, what: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise NowPaymentsError(f"NowPayments {what}: not a number", stage="read") from exc
    if not parsed.is_finite() or parsed < 0:
        raise NowPaymentsError(f"NowPayments {what}: not a usable number", stage="read")
    return parsed


def custody_balance_sync(currency: str, credentials) -> Decimal:
    """Spendable (`amount`, not `pendingAmount`) custody balance the provider
    reports for one currency. A currency missing from the answer is a balance
    of zero; an answer that is not the documented object is an error, never
    an assumed balance."""
    data = _payout_get_sync("balance", credentials)
    if not isinstance(data, dict):
        raise NowPaymentsError("NowPayments GET /balance: unexpected answer", stage="read")
    wanted = (normalize_pay_currency(currency) or str(currency)).lower()
    for ticker, entry in data.items():
        if str(ticker).lower() == wanted:
            if not isinstance(entry, dict) or entry.get("amount") is None:
                raise NowPaymentsError("NowPayments GET /balance: unexpected answer", stage="read")
            return _decimal(entry["amount"], "GET /balance")
    return Decimal("0")


def payout_fee_estimate_sync(currency: str, amount: Decimal, credentials) -> Decimal:
    data = _payout_get_sync("payout/fee", credentials,
                            params={"currency": normalize_pay_currency(currency), "amount": str(amount)})
    if not isinstance(data, dict) or data.get("fee") is None:
        raise NowPaymentsError("NowPayments GET /payout/fee: unexpected answer", stage="read")
    return _decimal(data["fee"], "GET /payout/fee")


def payout_min_amount_sync(currency: str, credentials) -> Decimal:
    data = _payout_get_sync(f"payout-withdrawal/min-amount/{normalize_pay_currency(currency)}", credentials)
    if not isinstance(data, dict) or data.get("result") is None:
        raise NowPaymentsError("NowPayments GET /payout-withdrawal/min-amount: unexpected answer", stage="read")
    return _decimal(data["result"], "GET /payout-withdrawal/min-amount")


def validate_payout_address_sync(address: str, currency: str, credentials) -> bool:
    """Ask the provider whether it can pay this address in this currency
    (the step its documentation recommends before creating a payout). True
    when it answers 200, False when it answers 400; anything else raises."""
    body = {"address": address, "currency": normalize_pay_currency(currency) or currency, "extra_id": None}
    with httpx.Client(timeout=STATUS_HTTP_TIMEOUT) as client:
        resp = client.post(f"{_payout_base()}/payout/validate-address",
                           headers=_engine_headers(credentials, jwt=False), json=body)
    if resp.status_code == 400:
        return False
    if resp.status_code >= 400:
        raise _refused(resp, "POST /payout/validate-address", "read")
    return True


def _withdrawal_view(row: Any, batch_id: Optional[str] = None) -> Dict[str, Any]:
    """The documented fields of one withdrawal, nothing else."""
    row = row if isinstance(row, dict) else {}

    def text(name: str) -> Optional[str]:
        value = row.get(name)
        return str(value) if value not in (None, "") else None

    return {"status": str(row.get("status") or "").upper(), "withdrawal_id": text("id"),
            "batch_id": text("batch_withdrawal_id") or batch_id, "address": text("address"),
            "currency": (text("currency") or "").lower() or None, "amount": text("amount"),
            "hash": text("hash"), "unique_external_id": text("unique_external_id"),
            "error": (text("error") or "")[:120] or None}


def payout_details_sync(batch_id: str, credentials) -> Dict[str, Any]:
    """The single withdrawal of one payout batch, as the provider reports it.

    The documentation lists only x-api-key for this request; if the provider
    answers 401 the call is repeated once with the session token as well."""
    try:
        data = _payout_get_sync(f"payout/{batch_id}", credentials)
    except NowPaymentsError as exc:
        if exc.status_code != 401:
            raise
        data = _payout_get_sync(f"payout/{batch_id}", credentials, jwt=True)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("withdrawals") if isinstance(data.get("withdrawals"), list) else [data]
    else:
        rows = []
    if len(rows) != 1:
        # One batch = one withdrawal here. Anything else is not our payout as we created it.
        raise NowPaymentsError("NowPayments GET /payout: unexpected number of withdrawals", stage="read")
    return _withdrawal_view(rows[0], str(batch_id))


def payout_status_sync(batch_id: str, credentials) -> str:
    """Status of the (single) withdrawal of one payout batch, upper case."""
    return payout_details_sync(batch_id, credentials)["status"]


def find_payout_by_external_id_sync(external_id: str, credentials, *, pages: int = 3,
                                    page_size: int = 100) -> Optional[Dict[str, Any]]:
    """Look for a payout carrying our unique reference in the provider's list
    of payouts (newest first). Returns it when exactly one is found, None when
    none is. Finding nothing does NOT prove that no payout exists."""
    found: List[Dict[str, Any]] = []
    for page in range(max(1, pages)):
        data = _payout_get_sync("payout", credentials,
                                params={"limit": page_size, "page": page, "order_by": "id", "order": "desc"})
        rows = data.get("payouts") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise NowPaymentsError("NowPayments GET /payout: unexpected answer", stage="read")
        found += [_withdrawal_view(r) for r in rows
                  if isinstance(r, dict) and str(r.get("unique_external_id") or "") == str(external_id)]
        if len(rows) < page_size:
            break
    if len(found) > 1:
        raise NowPaymentsError("NowPayments GET /payout: more than one payout carries the same reference",
                               stage="read")
    return found[0] if found else None


_TOTP_STEP_SECONDS = 30
_last_code: dict[str, Any] = {"value": None}


def _fresh_code(totp) -> str:
    """A one-time code that this process has not sent before. Two payouts
    confirmed inside the same 30-second step would otherwise carry the same
    code, and a one-time code may be accepted only once."""
    code = totp.now()
    if code == _last_code["value"]:
        _wait_for_next_code()
        code = totp.now()
    _last_code["value"] = code
    return code


def _wait_for_next_code() -> None:
    time.sleep(_TOTP_STEP_SECONDS - (time.time() % _TOTP_STEP_SECONDS) + 0.5)


def _confirm_payout_sync(batch_id: str, credentials) -> None:
    """Confirm a created payout with the second factor. Verifying is not
    sending again: the provider allows 10 attempts per payout, and this makes
    at most two (the second with the next code, only after a 4xx answer)."""
    totp = pyotp.TOTP(_require(credentials, "PAYOUT_TOTP_SECRET"))
    for attempt in (1, 2):
        code = _fresh_code(totp)
        with httpx.Client(timeout=AUTH_HTTP_TIMEOUT) as client:
            resp = client.post(f"{_payout_base()}/payout/{batch_id}/verify",
                               headers=_engine_headers(credentials, jwt=True), json={"verification_code": code})
        if resp.status_code < 400:
            return
        if attempt == 2 or resp.status_code >= 500 or resp.status_code in (401, 403, 404, 429):
            raise _refused(resp, "POST /payout/verify", "verify")


def create_single_payout_sync(*, wallet_address: str, amount: Decimal, currency: str, external_id: str,
                              credentials) -> Dict[str, Any]:
    """Create ONE withdrawal, then confirm it with the second factor.

    Returns {"batch_id", "withdrawal_id", "status", "verified"}. Raises
    NowPaymentsError with a 4xx status_code when the provider refused the
    login or the creation (nothing exists at the provider). When the batch was
    created but its confirmation failed, the batch id is still returned with
    verified=False: the provider then rejects it by itself after an hour, and
    until it reports that the outcome is uncertain and is reconciled, never
    retried."""
    pay_currency = normalize_pay_currency(currency) or "usdtbsc"
    # "amount ... Must not exceed 6 decimals"; a cashout amount has two.
    withdrawal = {"address": wallet_address, "currency": pay_currency, "amount": float(money(amount)),
                  "unique_external_id": external_id}
    _require(credentials, "PAYOUT_TOTP_SECRET")          # refuse before anything is created
    headers = _engine_headers(credentials, jwt=True)
    with httpx.Client(timeout=PAYOUT_HTTP_TIMEOUT) as client:
        resp = client.post(f"{_payout_base()}/payout", headers=headers, json={"withdrawals": [withdrawal]})
    if resp.status_code >= 400:
        raise _refused(resp, "POST /payout", "create")
    try:
        created = resp.json()
    except ValueError:
        created = None
    # A 2xx answer means a payout may exist: from here on nothing may be reported as "refused".
    batch_id = str(created.get("id") or "") if isinstance(created, dict) else ""
    if not batch_id:
        raise NowPaymentsError("NowPayments payout: batch id missing from create response.", stage="create")
    rows = created.get("withdrawals") if isinstance(created.get("withdrawals"), list) else []
    first = _withdrawal_view(rows[0], batch_id) if rows else {"status": "", "withdrawal_id": None}
    result = {"batch_id": batch_id, "withdrawal_id": first["withdrawal_id"], "status": first["status"]}
    try:
        _confirm_payout_sync(batch_id, credentials)
    except Exception:  # noqa: BLE001 - created but not confirmed: the caller reconciles
        logger.error("NOWPayments payout %s created but its confirmation failed", batch_id)
        return {**result, "verified": False}
    return {**result, "verified": True}
