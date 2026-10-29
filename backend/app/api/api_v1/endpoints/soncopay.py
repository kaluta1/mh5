"""SoncoPay: the Admin Panel settings and the payment webhook.

Admin (mounted at /admin/finance/soncopay, administrators only):
  GET   the settings as the Admin Panel shows them; never a key or a secret.
        Needs a Super Admin or the manage_payment_settings permission.
  PUT   save the form; a Super Admin and the current password
        (app.services.soncopay_settings).
  POST  /connection-test  a Super Admin: GET /v1/methods with the saved key of
        one environment (no side effect); the key is never shown.

Webhook (mounted at /webhooks/soncopay): app.services.soncopay_payments.
handle_webhook verifies the timestamped signature over the raw body (5 minute
window), processes each delivery id once and credits nothing from the body:
the payment is read from SoncoPay before the deposit changes. The body is never
logged.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.client_ip import client_ip
from app.db.session import get_db
from app.models.user import User
from app.core.rate_limit import _is_rate_limited
from app.services import soncopay_payments, soncopay_settings

logger = logging.getLogger(__name__)

admin_router = APIRouter()
webhook_router = APIRouter()


class SoncoPaySettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Absent or null = keep. Keys and secrets are write-only: blank keeps the saved one.
    enabled: Optional[bool] = None
    environment: Optional[str] = Field(default=None, max_length=10)
    default_provider: Optional[str] = Field(default=None, max_length=30)
    test_api_key: Optional[str] = Field(default=None, max_length=512)
    test_webhook_secret: Optional[str] = Field(default=None, max_length=512)
    live_api_key: Optional[str] = Field(default=None, max_length=512)
    live_webhook_secret: Optional[str] = Field(default=None, max_length=512)
    # Required to switch to the Live environment.
    confirmation: Optional[str] = Field(default=None, max_length=60)
    current_password: str = Field(default="", max_length=256)
    # What the administrator was shown; the change is refused if it has moved since.
    expected_version: Optional[int] = Field(default=None, ge=0)


def _http_error(exc: soncopay_settings.SoncoPaySettingsError) -> HTTPException:
    code = {"SUPER_ADMIN_REQUIRED": status.HTTP_403_FORBIDDEN, "FORBIDDEN": status.HTTP_403_FORBIDDEN,
            "REAUTH_REQUIRED": status.HTTP_403_FORBIDDEN, "REAUTH_LOCKED": status.HTTP_429_TOO_MANY_REQUESTS,
            "INVALID_VALUE": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_FIELD": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "NOTHING_TO_CHANGE": status.HTTP_422_UNPROCESSABLE_ENTITY}.get(exc.code, status.HTTP_409_CONFLICT)
    detail = {"code": exc.code, "message": str(exc)}
    if exc.field:
        detail["field"] = exc.field
    return HTTPException(status_code=code, detail=detail)


@admin_router.get("")
def get_soncopay_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """The SoncoPay settings: on/off, environment, default checkout, whether each
    key and secret is saved (never its value), the webhook URL."""
    if not soncopay_settings.can_view(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "FORBIDDEN",
            "message": f"A Super Admin or the {soncopay_settings.VIEW_PERMISSION} permission is required."})
    return soncopay_settings.view(db, current_user)


@admin_router.put("")
def set_soncopay_settings(body: SoncoPaySettingsBody, request: Request, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_active_user)):
    """Save the SoncoPay settings form (a Super Admin + the current password;
    keys and secrets stored encrypted, audited without their values; one
    commit, nothing changed on any refusal)."""
    try:
        return soncopay_settings.update(
            db, current_user, password=body.current_password, enabled=body.enabled,
            environment=body.environment, default_provider=body.default_provider,
            credentials={"TEST_API_KEY": body.test_api_key, "TEST_WEBHOOK_SECRET": body.test_webhook_secret,
                         "LIVE_API_KEY": body.live_api_key, "LIVE_WEBHOOK_SECRET": body.live_webhook_secret},
            confirmation=body.confirmation, expected_version=body.expected_version, ip=client_ip(request))
    except soncopay_settings.SoncoPaySettingsError as exc:
        db.rollback()
        raise _http_error(exc) from None


class ConnectionTestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Literal["test", "live"]


CONNECTION_TEST_LIMIT, CONNECTION_TEST_WINDOW = 10, 600        # per administrator per 10 minutes


@admin_router.post("/connection-test")
async def soncopay_connection_test(body: ConnectionTestBody, db: Session = Depends(get_db),
                                   current_user: User = Depends(get_current_active_user)):
    """Read GET /v1/methods with the saved key of one environment. Nothing is created or changed."""
    if not soncopay_settings.can_change(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "SUPER_ADMIN_REQUIRED", "message": "Only a Super Admin can test the SoncoPay connection."})
    if _is_rate_limited(f"soncopay-connection-test:{current_user.id}", CONNECTION_TEST_LIMIT,
                        CONNECTION_TEST_WINDOW):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={"code": "RATE_LIMITED", "message": "Too many tests. Try again in a few minutes."})
    return await soncopay_payments.connection_test(db, body.environment)


# ---------------------------------------------------------------------------
# SoncoPay payouts (app.services.soncopay_payouts)
# ---------------------------------------------------------------------------

def _require_payout_viewer(user: User) -> None:
    from app.services import payment_config, super_admin

    if not (super_admin.is_super_admin(user) or payment_config.has_permission(user, payment_config.PERMISSION_PROCESS)
            or soncopay_settings.can_view(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "FORBIDDEN", "message": "A Super Admin or a finance permission is required."})


@admin_router.get("/payouts")
def soncopay_payouts_view(provider: bool = False, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_active_user)):
    """Readiness, the owner's authorization, every member destination (address masked) and, with
    ?provider=true, SoncoPay's balance, USDT:BSC fee, minimum and destination settings (read-only calls)."""
    from app.services import soncopay_payouts

    _require_payout_viewer(current_user)
    if provider and _is_rate_limited(f"soncopay-payouts-read:{current_user.id}", 20, 600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={"code": "RATE_LIMITED", "message": "Too many reads. Try again in a few minutes."})
    return soncopay_payouts.admin_view(db, read_provider=provider)


class PayoutAuthorizationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=500)
    current_password: str = Field(default="", max_length=256)


class PasswordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(default="", max_length=256)


def _payout_error(exc: Exception) -> HTTPException:
    from app.services import payment_config

    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail={"code": "SUPER_ADMIN_REQUIRED", "message": str(exc)})
    if isinstance(exc, payment_config.PaymentConfigError):
        code = 429 if exc.code == "REAUTH_LOCKED" else 403
        return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})
    return HTTPException(status_code=422, detail={"code": "INVALID_VALUE", "message": str(exc)})


@admin_router.post("/payouts/authorization")
def soncopay_payouts_authorize(body: PayoutAuthorizationBody, db: Session = Depends(get_db),
                               current_user: User = Depends(get_current_active_user)):
    """Record that SoncoPay allows member commission payouts from this merchant account. Changes no
    payout switch: the server activation stays a separate operator step."""
    from app.services import soncopay_payouts

    try:
        return soncopay_payouts.authorize(db, current_user, password=body.current_password,
                                          confirmation=body.confirmation, note=body.note)
    except Exception as exc:  # noqa: BLE001 - mapped below
        db.rollback()
        if not isinstance(exc, (PermissionError, ValueError)) and type(exc).__name__ != "PaymentConfigError":
            raise
        raise _payout_error(exc) from None


@admin_router.post("/payouts/authorization/revoke")
def soncopay_payouts_revoke(body: PasswordBody, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_active_user)):
    from app.services import soncopay_payouts

    try:
        soncopay_payouts.revoke(db, current_user, password=body.current_password)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if not isinstance(exc, (PermissionError, ValueError)) and type(exc).__name__ != "PaymentConfigError":
            raise
        raise _payout_error(exc) from None
    return {"ok": True}


@admin_router.post("/payouts/sync")
def soncopay_payouts_sync(current_user: User = Depends(get_current_active_user)):
    """Ask the payout cycle to run now (destinations are read back, open payouts reconciled). It pays
    only what the cycle would pay anyway."""
    from app.services import cashout_engine, payment_config, super_admin

    if not (super_admin.is_super_admin(current_user)
            or payment_config.has_permission(current_user, payment_config.PERMISSION_PROCESS)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "FORBIDDEN", "message": "A Super Admin or the process_cashouts permission is required."})
    if _is_rate_limited(f"soncopay-payouts-sync:{current_user.id}", 10, 600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={"code": "RATE_LIMITED", "message": "Too many requests. Try again later."})
    return {"requested": cashout_engine.request_cycle()}


# Rejected deliveries per sender address (a correctly signed delivery is never counted).
BAD_WEBHOOK_LIMIT, BAD_WEBHOOK_WINDOW = 30, 60
_bad_webhooks: dict = defaultdict(deque)


def _too_many_bad(address: str, now: float) -> bool:
    hits = _bad_webhooks.get(address)
    while hits and hits[0] <= now - BAD_WEBHOOK_WINDOW:
        hits.popleft()
    if hits is not None and not hits:
        _bad_webhooks.pop(address, None)
    return bool(hits) and len(hits) >= BAD_WEBHOOK_LIMIT


@webhook_router.post("/soncopay")
async def soncopay_webhook(request: Request, db: Session = Depends(get_db)):
    """SoncoPay payment notification. Verified, processed once, never trusted on its own."""
    sender, now = client_ip(request), time.monotonic()
    throttled = _too_many_bad(sender, now)
    raw = await request.body()
    result = await soncopay_payments.handle_webhook(db, raw, request.headers)
    if result.status_code in (400, 413):
        if throttled:
            return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                content={"detail": "Too many rejected callbacks"})
        if len(_bad_webhooks) < 10_000 or sender in _bad_webhooks:
            _bad_webhooks[sender].append(now)
        logger.warning("SoncoPay webhook rejected from %s: %s", sender, result.body.get("detail"))
    return JSONResponse(status_code=result.status_code, content=result.body)
