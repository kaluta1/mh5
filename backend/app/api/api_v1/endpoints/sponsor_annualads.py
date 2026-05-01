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

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from jose import jwt
from pydantic import BaseModel
from app.api import deps
from app.core.config import settings
from app.services.accounting_service import accounting_service, AccountingError
from app.models.accounting import ChartOfAccounts, AccountType, JournalEntry
from app.models.user import User

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
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Sign a short-lived HS256 JWT for Annual Ads iframe SSO (same shape as their docs)."""
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

    if effective_event != "sponsor_payment_confirmed":
        return {"ok": True, "received": True, "event": effective_event}

    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    payment = (
        payload.get("payment")
        or data_block.get("payment")
        or data_block
        or {}
    )
    tx_hash = str(
        payment.get("tx_hash")
        or payment.get("transaction_hash")
        or data_block.get("tx_hash")
        or ""
    ).strip().lower()
    if not tx_hash:
        raise HTTPException(status_code=400, detail="Missing payment.tx_hash")

    # CoA accounts from AnnualAds integration spec:
    # 1030 Crypto Wallet USDT, 2310 Deferred Sponsor Revenue, 4010 Sponsor Revenue Net, 7110 FX loss.
    def _ensure_account(code: str, name: str, account_type: AccountType, parent_code: str | None = None) -> None:
        existing = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).first()
        if existing:
            return
        parent_id = None
        if parent_code:
            parent = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == parent_code).first()
            if parent:
                parent_id = parent.id
        db.add(
            ChartOfAccounts(
                account_code=code,
                account_name=name,
                account_type=account_type,
                parent_id=parent_id,
                is_active=True,
                description="Auto-created by AnnualAds sponsor payment integration.",
            )
        )
        db.flush()

    _ensure_account("1030", "Crypto Wallet — USDT (BSC)", AccountType.ASSET, "1000")
    _ensure_account("1210", "Receivable from AnnualAds", AccountType.ASSET, "1000")
    _ensure_account("2310", "Deferred Sponsor Revenue", AccountType.LIABILITY, "2000")
    _ensure_account("4010", "Sponsor Advertising Revenue — Net", AccountType.REVENUE, "4000")
    _ensure_account("7110", "FX / Crypto Conversion Loss", AccountType.EXPENSE, "5000")

    def _to_decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    gross = _to_decimal(payment.get("amount") or payment.get("gross_amount"))
    platform_fee = _to_decimal(payment.get("platform_fee"))
    client_revenue = _to_decimal(
        payment.get("client_revenue")
        or payment.get("net_amount")
        or data_block.get("client_revenue")
    )
    if client_revenue <= 0:
        client_revenue = gross - platform_fee
    if client_revenue <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amounts for sponsor accounting")

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
                    "debit": float(client_revenue),
                    "credit": 0.0,
                    "description": f"AnnualAds net sponsor inflow tx:{tx_hash}",
                },
                {
                    "account_code": "2310",
                    "debit": 0.0,
                    "credit": float(client_revenue),
                    "description": f"AnnualAds deferred sponsor revenue tx:{tx_hash}",
                },
            ],
            commit=True,
        )
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
        "gross_amount": float(gross),
        "platform_fee": float(platform_fee),
        "client_revenue": float(client_revenue),
        "journal_entry_id": je.id,
        "entry_number": je.entry_number,
    }
