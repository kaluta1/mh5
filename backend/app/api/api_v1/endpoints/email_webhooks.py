"""Provider delivery webhook endpoint (EMAIL-5).

POST /api/v1/webhooks/resend

No user authentication: the provider's signature over the RAW request body is
the authentication boundary. Nothing is parsed, stored or acted on before the
signature has been verified with the dedicated signing secret
(RESEND_WEBHOOK_SECRET; never the API key).

Answers
-------
200  authenticated and handled: applied, recorded, a duplicate, an unknown
     event type or an unknown message. The provider must not retry these.
400  authenticated but not an event object.
401  missing, invalid or expired signature, or a body that was altered.
413  body larger than the limit.
503  no signing secret is configured: nothing can be authenticated, so
     nothing is accepted (the provider will retry later).

Neither the body nor any header value is logged.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services import email_webhooks
from app.services.email_providers import WebhookVerificationError, verify_resend_webhook

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_BODY_BYTES = 256 * 1024


@router.post("/resend", include_in_schema=False)
async def resend_webhook(request: Request, db: Session = Depends(get_db)):
    secret = (settings.RESEND_WEBHOOK_SECRET or "").strip()
    if not secret:
        logger.warning("Resend webhook received but RESEND_WEBHOOK_SECRET is not configured: refused")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Email webhooks are not configured.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large.")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large.")

    event_id = request.headers.get("svix-id") or ""
    try:
        verify_resend_webhook(raw, event_id=event_id, timestamp=request.headers.get("svix-timestamp") or "",
                              signature=request.headers.get("svix-signature") or "", secret=secret)
    except WebhookVerificationError:
        # One answer for every reason (missing header, bad signature, altered body, old timestamp).
        logger.warning("Resend webhook rejected: signature verification failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")

    try:
        payload = json.loads(raw.decode("utf-8"))
        result = email_webhooks.process_event(db, provider=email_webhooks.PROVIDER_RESEND, event_id=event_id,
                                              payload=payload)
    except (ValueError, UnicodeDecodeError):
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload.")
    return {"ok": True, "result": result.outcome}
