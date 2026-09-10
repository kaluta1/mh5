"""
Annual Ads — sponsor embed SSO + payment webhooks.

Configure secrets in env (never commit real values):
  ANNUALADS_SSO_SECRET, ANNUALADS_TENANT_ID, ANNUALADS_TENANT_API_KEY, ANNUALADS_WEBHOOK_SECRET

Webhook URL to register in Annual Ads tenant:
  https://api.myhigh5.com/api/v1/webhooks/sponsor-payment
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from jose import jwt
from pydantic import BaseModel
from app.api import deps
from app.core.config import settings
from app.services.accounting_service import accounting_service, AccountingError
from app.models.accounting import ChartOfAccounts, AccountType, JournalEntry
from app.models.user import User
from app.services.financial_integrity import FinancialIntegrityError, money, positive_money
from app.services.nowpayments_service import normalize_pay_currency

logger = logging.getLogger(__name__)

webhook_router = APIRouter()
sso_router = APIRouter()


def _sso_configured() -> bool:
    return bool(
        getattr(settings, "ANNUALADS_SSO_SECRET", None)
        and getattr(settings, "ANNUALADS_TENANT_ID", None)
    )


class SsoTokenResponse(BaseModel):
    token: str
    tenant_api_key: str
    tenant_id: str
    expires_in_seconds: int = 3600


@sso_router.get("/sso-token", response_model=SsoTokenResponse)
def get_sponsor_sso_token(
    response: Response,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Sign a short-lived HS256 JWT for Annual Ads iframe SSO (same shape as their docs)."""
    if not getattr(settings, "ANNUALADS_ENABLED", True):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Annual Ads integration is temporarily disabled.",
        )
    if not _sso_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Annual Ads SSO is not configured (set ANNUALADS_SSO_SECRET and ANNUALADS_TENANT_ID).",
        )
    secret = settings.ANNUALADS_SSO_SECRET
    tenant_id = settings.ANNUALADS_TENANT_ID
    api_key = getattr(settings, "ANNUALADS_TENANT_API_KEY", "") or ""

    display = (current_user.full_name or current_user.username or "").strip() or current_user.email or "Member"
    payload = {
        "sub": str(current_user.id),
        "email": current_user.email or "",
        "name": display,
        "tenant_id": tenant_id,
        "exp": int(time.time()) + 3600,
    }
    token = str(jwt.encode(payload, secret, algorithm="HS256"))
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return SsoTokenResponse(
        token=token,
        tenant_api_key=api_key,
        tenant_id=tenant_id,
        expires_in_seconds=3600,
    )


def _verify_webhook_signature(
    secret: str,
    timestamp: str,
    raw_body: bytes,
    signature_hex: str,
) -> bool:
    # Docs: HMAC-SHA256( secret, timestamp + '.' + body_string )
    try:
        body_str = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        return False
    message = f"{timestamp}.{body_str}"
    expected = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_hex.strip().lower())


@webhook_router.post("/sponsor-payment")
async def sponsor_payment_webhook(
    request: Request,
    db: Session = Depends(deps.get_db),
) -> dict[str, Any]:
    """
    Receives POST from Annual Ads when a sponsor payment is confirmed.
    Register this URL in the tenant: .../api/v1/webhooks/sponsor-payment
    """
    if not getattr(settings, "ANNUALADS_ENABLED", True):
        logger.warning("AnnualAds webhook received while ANNUALADS_ENABLED=false — rejecting")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Annual Ads integration is temporarily disabled.",
        )
    secret = getattr(settings, "ANNUALADS_WEBHOOK_SECRET", None) or ""
    if not secret:
        logger.error("ANNUALADS_WEBHOOK_SECRET is not set; refusing webhook")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook endpoint not configured.",
        )

    raw = await request.body()
    sig = request.headers.get("x-webhook-signature") or request.headers.get("X-Webhook-Signature") or ""
    ts = request.headers.get("x-webhook-timestamp") or request.headers.get("X-Webhook-Timestamp") or ""
    event = request.headers.get("x-webhook-event") or request.headers.get("X-Webhook-Event") or ""

    if not sig or not ts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature headers")

    # Replay protection: reject requests older/newer than 5 minutes.
    try:
        timestamp = int(ts)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook timestamp")
    if abs(time.time() - timestamp) > 300:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Stale timestamp")

    if not _verify_webhook_signature(secret, ts, raw, sig):
        logger.warning("Invalid sponsor payment webhook signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload: dict[str, Any] = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    effective_event = event or payload.get("event")
    logger.info(
        "sponsor_payment_webhook: event=%s payload_keys=%s",
        effective_event,
        list(payload.keys()),
    )

    if not isinstance(effective_event, str) or len(effective_event) > 100:
        raise HTTPException(status_code=400, detail="Invalid webhook event")
    if effective_event != "sponsor_payment_confirmed":
        if any(word in effective_event.lower() for word in ("refund", "reverse", "cancel", "chargeback")):
            # Never acknowledge an unsupported compensating financial event as applied.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sponsor reversal events are not configured",
            )
        return {"ok": True, "received": True, "event": effective_event}

    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    payment = (
        payload.get("payment")
        or data_block.get("payment")
        or data_block
        or {}
    )
    payload_tenant = str(
        payload.get("tenant_id") or data_block.get("tenant_id") or payment.get("tenant_id") or ""
    ).strip()
    configured_tenant = str(getattr(settings, "ANNUALADS_TENANT_ID", "") or "").strip()
    if payload_tenant and configured_tenant and payload_tenant != configured_tenant:
        raise HTTPException(status_code=401, detail="Webhook tenant does not match")
    tx_hash = str(
        payment.get("tx_hash")
        or payment.get("transaction_hash")
        or data_block.get("tx_hash")
        or ""
    ).strip().lower()
    if not tx_hash or len(tx_hash) > 255 or any(ch.isspace() for ch in tx_hash):
        raise HTTPException(status_code=400, detail="Missing payment.tx_hash")

    if db.get_bind().dialect.name == "postgresql":
        # Serialize identical provider events even before a dedicated event table exists.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:event_key))"), {"event_key": f"annualads:{tx_hash}"})

    # CoA accounts from AnnualAds integration spec:
    # 1030 Crypto Wallet USDT, 2310 Deferred Sponsor Revenue, 4010 Sponsor Revenue Net, 7110 FX loss.
    def _ensure_account(code: str, name: str, account_type: AccountType, parent_code: str | None = None) -> None:
        existing = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).first()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Sponsor accounting account {code} is not configured",
            )

    _ensure_account("1030", "Crypto Wallet — USDT (BSC)", AccountType.ASSET, "1000")
    _ensure_account("1210", "Receivable from AnnualAds", AccountType.ASSET, "1000")
    _ensure_account("2310", "Deferred Sponsor Revenue", AccountType.LIABILITY, "2000")
    _ensure_account("4010", "Sponsor Advertising Revenue — Net", AccountType.REVENUE, "4000")
    _ensure_account("7110", "FX / Crypto Conversion Loss", AccountType.EXPENSE, "5000")

    try:
        gross = positive_money(payment.get("amount") or payment.get("gross_amount"))
        platform_fee = money(payment.get("platform_fee") or 0)
        if platform_fee < 0 or platform_fee >= gross:
            raise FinancialIntegrityError("Invalid sponsor platform fee")
        expected_client_revenue = money(gross - platform_fee)
        submitted_client_revenue = (
            payment.get("client_revenue")
            or payment.get("net_amount")
            or data_block.get("client_revenue")
        )
        client_revenue = (
            money(submitted_client_revenue)
            if submitted_client_revenue is not None
            else expected_client_revenue
        )
        if client_revenue != expected_client_revenue:
            raise FinancialIntegrityError("Sponsor net amount does not equal gross minus fee")
        asset = normalize_pay_currency(payment.get("currency") or payment.get("pay_currency") or "usdtbsc")
        if asset != "usdtbsc":
            raise FinancialIntegrityError("Sponsor settlement must be USDT on BSC")
    except FinancialIntegrityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    entry_description = f"AnnualAds sponsor payment received (deferred) tx:{tx_hash}"
    existing_entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.description == entry_description)
        .first()
    )
    if existing_entry:
        return {
            "ok": True,
            "received": True,
            "event": effective_event,
            "status": "already_recorded",
            "tx_hash": tx_hash,
            "journal_entry_id": existing_entry.id,
        }

    # Entry A (IFRS/ASC net-agent treatment):
    # Dr 1030 (USDT wallet, net 70%) / Cr 2310 (deferred sponsor revenue)
    try:
        je = accounting_service.create_journal_entry(
            db=db,
            description=entry_description,
            lines=[
                {
                    "account_code": "1030",
                    "debit": client_revenue,
                    "credit": 0,
                    "description": f"AnnualAds net sponsor inflow tx:{tx_hash}",
                },
                {
                    "account_code": "2310",
                    "debit": 0,
                    "credit": client_revenue,
                    "description": f"AnnualAds deferred sponsor revenue tx:{tx_hash}",
                },
            ],
            commit=False,
        )
        db.commit()
    except AccountingError as e:
        logger.error("AnnualAds accounting posting failed for tx=%s: %s", tx_hash, e)
        raise HTTPException(status_code=500, detail=f"Accounting posting failed: {str(e)}")
    except Exception as e:
        logger.exception("Unexpected error posting AnnualAds accounting for tx=%s", tx_hash)
        raise HTTPException(status_code=500, detail=f"Accounting posting failed: {str(e)}")

    return {
        "ok": True,
        "received": True,
        "event": effective_event,
        "status": "recorded",
        "tx_hash": tx_hash,
        "gross_amount": str(gross),
        "platform_fee": str(platform_fee),
        "client_revenue": str(client_revenue),
        "journal_entry_id": je.id,
        "entry_number": je.entry_number,
    }
