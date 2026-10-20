"""SoncoPay: the Admin Panel settings and the (not yet operational) webhook.

Admin (mounted at /admin/finance/soncopay, administrators only):
  GET   the settings as the Admin Panel shows them; never a key or a secret.
        Needs a Super Admin or the manage_payment_settings permission.
  PUT   save the form; a Super Admin and the current password
        (app.services.soncopay_settings).

Webhook (mounted at /webhooks/soncopay): REFUSES every callback with 503 until
SoncoPay's webhook signature specification is confirmed and implemented. The
request body is never read, stored or logged, and no payment event is
processed.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.client_ip import client_ip
from app.db.session import get_db
from app.models.user import User
from app.services import soncopay_settings

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


@webhook_router.post("/soncopay")
async def soncopay_webhook(request: Request):
    """Not operational: refused until SoncoPay's webhook specification is
    confirmed and its signature check implemented. Nothing is processed."""
    if not soncopay_settings.WEBHOOK_OPERATIONAL:
        logger.warning("SoncoPay webhook refused (not operational yet) from %s", client_ip(request))
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={
            "code": "SONCOPAY_WEBHOOK_NOT_OPERATIONAL",
            "message": "SoncoPay webhooks are not accepted yet."})
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)    # unreachable until implemented
