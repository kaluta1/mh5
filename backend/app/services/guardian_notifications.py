"""Guardian-consent emails, recorded through the central email service.

Links carry the single-use token in the URL fragment (#token=...), which
browsers never send to servers, so it cannot appear in web-server or proxy
logs. The emails never include a password, DOB, age or other minor PII beyond
the chosen username.

The raw token travels only inside the delivery's encrypted payload, which is
deleted once the email is sent (or finally fails). The idempotency key is
derived from the token's hash, never from the token itself.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from app.services.email import email_service
from app.services.email_events import EmailEvent


def _token_ref(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()[:32]


def send_guardian_request_email(db: Session, guardian_email: str, raw_token: str,
                                minor_username: Optional[str]) -> bool:
    row = email_service.enqueue(
        db, event=EmailEvent.GUARDIAN_CONSENT_REQUEST, recipient=guardian_email,
        context={"token": raw_token, "username": minor_username},
        idempotency_key=f"guardian.consent_request:{_token_ref(raw_token)}",
    )
    return row is not None and row.status == "QUEUED"


def send_completion_email(db: Session, minor_email: str, raw_token: str) -> bool:
    row = email_service.enqueue(
        db, event=EmailEvent.GUARDIAN_REGISTRATION_COMPLETION, recipient=minor_email,
        context={"token": raw_token},
        idempotency_key=f"guardian.registration_completion:{_token_ref(raw_token)}",
    )
    return row is not None and row.status == "QUEUED"
