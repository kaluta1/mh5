"""
Annual Ads — sponsor embed SSO + payment webhooks.

Configure secrets in env (never commit real values):
  ANNUALADS_SSO_SECRET, ANNUALADS_TENANT_ID, ANNUALADS_TENANT_API_KEY, ANNUALADS_WEBHOOK_SECRET

Webhook URL to register in Annual Ads tenant:
  {BACKEND_PUBLIC_URL or request base}/api/v1/webhooks/sponsor-payment
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt
from pydantic import BaseModel
from app.api import deps
from app.core.config import settings
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
async def sponsor_payment_webhook(request: Request) -> dict[str, Any]:
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

    if not _verify_webhook_signature(secret, ts, raw, sig):
        logger.warning("Invalid sponsor payment webhook signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload: dict[str, Any] = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    logger.info(
        "sponsor_payment_webhook: event=%s payload_keys=%s",
        event or payload.get("event"),
        list(payload.keys()),
    )
    # Hook for fulfillment: extend here (DB, email, etc.)
    return {"ok": True, "received": True, "event": event or payload.get("event")}
