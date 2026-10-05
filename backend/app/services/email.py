"""Central application email service (EMAIL-1).

Business code calls ONE thing:

    email_service.enqueue(db, event=EmailEvent.X, recipient=..., context={...},
                          idempotency_key="...")

It knows nothing about Resend. `enqueue` validates the event against the
registry, applies the send policy, enforces idempotency and a durable
per-recipient limit, and records the email in the outbox (email_deliveries).
The outbox worker (app.services.email_outbox) renders and sends it.

Contract with callers:
* Call it AFTER the business transaction has committed. The outbox row is
  written in its own savepoint and committed here; a failure to record an email
  is logged and swallowed, so it can never roll back or undo business state.
* It never raises for an operational problem. Only an unknown event key (a
  programming error) raises.
* A switched-off email is recorded as SUPPRESSED and never queued: turning a
  switch back on does not release a backlog.
* Idempotency: one logical email = one delivery row, whatever the number of
  retries of the business operation. Transient send failures are retried by
  the worker ON THAT ROW. A row that failed before any attempt purely because
  of configuration (no provider key, no encryption key) is re-armed, in
  place, if the same logical email is triggered again once the configuration
  is fixed. A second row is never created.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.redaction import mask_email
from app.models.email import EmailDelivery
from app.services import email_crypto, email_settings_service as policy
from app.services.email_events import EmailCategory, EmailEvent, get_event
from app.services.email_render import has_renderer

logger = logging.getLogger(__name__)

# Durable per-recipient limits (count, window seconds), enforced against the
# delivery log itself, so they survive restarts and hold across processes.
DEFAULT_RECIPIENT_LIMIT: Tuple[int, int] = (10, 3600)
RECIPIENT_LIMITS: Dict[str, Tuple[int, int]] = {
    EmailEvent.AUTH_EMAIL_VERIFICATION.value: (5, 3600),
    EmailEvent.AUTH_PASSWORD_RESET.value: (5, 3600),
    EmailEvent.GUARDIAN_CONSENT_REQUEST.value: (5, 3600),
    EmailEvent.AFFILIATE_INVITATION.value: (3, 86400),
    EmailEvent.SUPPORT_CONTACT_CONFIRMATION.value: (3, 3600),
    EmailEvent.SUPPORT_NEWSLETTER_CONFIRMATION.value: (2, 86400),
}
ADMIN_RECIPIENT_LIMIT: Tuple[int, int] = (60, 3600)
# Referral invitations a single member may send per 24 hours.
INVITATIONS_PER_DAY = 50
# Platform-wide ceilings (count, window seconds) for email that an ANONYMOUS
# visitor can cause to be sent to an address of their choosing. They bound the
# damage of a distributed abuse that stays under the per-IP and per-recipient
# limits, so the verified sending domain cannot be used as a relay.
GLOBAL_EVENT_LIMITS: Dict[str, Tuple[int, int]] = {
    EmailEvent.SUPPORT_CONTACT_CONFIRMATION.value: (100, 3600),
    EmailEvent.SUPPORT_NEWSLETTER_CONFIRMATION.value: (200, 3600),
}

MAX_IDEMPOTENCY_KEY_LENGTH = 200


def recipient_limit(event_key: str, category: str) -> Tuple[int, int]:
    if event_key in RECIPIENT_LIMITS:
        return RECIPIENT_LIMITS[event_key]
    if category == EmailCategory.ADMIN.value:
        return ADMIN_RECIPIENT_LIMIT
    return DEFAULT_RECIPIENT_LIMIT


class NotificationEmailService:
    """The application-level email entry point."""

    def enqueue(self, db: Session, *, event: EmailEvent, recipient: str, idempotency_key: str,
                context: Optional[dict] = None, user_id: Optional[int] = None, lang: Optional[str] = None,
                now: Optional[datetime] = None) -> Optional[EmailDelivery]:
        definition = get_event(event)          # unknown event: programming error, raises
        try:
            return self._enqueue(db, definition, recipient, idempotency_key, context or {}, user_id, lang,
                                 now or datetime.utcnow())
        except Exception as exc:  # noqa: BLE001 - email must never break the caller
            logger.error("Email %s could not be recorded: %s", definition.key, type(exc).__name__)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return None

    # ------------------------------------------------------------------
    def _enqueue(self, db: Session, definition, recipient: str, idempotency_key: str, context: dict,
                 user_id: Optional[int], lang: Optional[str], now: datetime) -> Optional[EmailDelivery]:
        from app.services.email_templates import normalize_lang

        if not has_renderer(definition.key):
            logger.error("Email %s has no template yet; nothing recorded", definition.key)
            return None
        key = str(idempotency_key or "").strip()
        if not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError("idempotency_key is required (max 200 characters)")
        existing = db.query(EmailDelivery).filter(EmailDelivery.idempotency_key == key).first()
        rearm = (existing is not None and existing.status == "FAILED" and int(existing.attempt_count or 0) == 0
                 and existing.failure_category in policy.CONFIGURATION_FAILURES)
        if existing is not None and not rearm:
            return existing

        address = str(recipient or "").strip()
        decision = policy.evaluate(db, definition)
        status, reason = ("QUEUED", None) if decision.allowed else (decision.status, decision.reason)
        if status == "QUEUED" and not policy.valid_email(address):
            status, reason = "SUPPRESSED", policy.REASON_INVALID_RECIPIENT
        if status == "QUEUED" and not email_crypto.settings_key_configured():
            # Configuration required: without the dedicated key the payload
            # cannot be encrypted, and it is never stored in plaintext.
            status, reason = "FAILED", policy.REASON_ENCRYPTION_UNCONFIGURED
        rhash = email_crypto.recipient_hash(address)
        if status == "QUEUED" and self._over_limit(db, definition, rhash, now):
            status, reason = "SUPPRESSED", policy.REASON_RATE_LIMITED
        if status == "QUEUED" and self._over_global_limit(db, definition, now):
            status, reason = "SUPPRESSED", policy.REASON_RATE_LIMITED_GLOBAL

        if rearm:
            if status != "QUEUED":
                return existing                       # still not sendable: the row stays as it is
            row = existing
            row.user_id, row.recipient_masked, row.recipient_hash = user_id, mask_email(address), rhash
            row.lang, row.status, row.failure_category, row.failed_at = normalize_lang(lang), "QUEUED", None, None
            row.updated_at = now
        else:
            row = EmailDelivery(
                event_key=definition.key, category=definition.category.value, user_id=user_id,
                recipient_masked=mask_email(address), recipient_hash=rhash, lang=normalize_lang(lang),
                status=status, attempt_count=0, idempotency_key=key, failure_category=reason,
                created_at=now, updated_at=now,
            )
        if status == "QUEUED":
            row.payload_ciphertext = email_crypto.encrypt_payload({"to": address, "context": context})
            row.queued_at = now
            row.next_attempt_at = now
        elif status == "FAILED":
            row.failed_at = now
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            # A concurrent request recorded the same event first: the unique
            # idempotency key is the authority.
            return db.query(EmailDelivery).filter(EmailDelivery.idempotency_key == key).first()
        db.commit()
        if status != "QUEUED":
            logger.info("Email %s not queued (%s) for %s", definition.key, reason, row.recipient_masked)
        return row

    @staticmethod
    def count_recent(db: Session, event: EmailEvent, *, user_id: int, seconds: int = 86400,
                     now: Optional[datetime] = None) -> int:
        """Emails of one event recorded for one member in the window (durable:
        counted from the delivery log)."""
        now = now or datetime.utcnow()
        return int(db.query(func.count(EmailDelivery.id)).filter(
            EmailDelivery.event_key == get_event(event).key,
            EmailDelivery.user_id == user_id,
            EmailDelivery.created_at >= now - timedelta(seconds=seconds),
        ).scalar() or 0)

    @staticmethod
    def _over_global_limit(db: Session, definition, now: datetime) -> bool:
        limit = GLOBAL_EVENT_LIMITS.get(definition.key)
        if not limit:
            return False
        count = db.query(func.count(EmailDelivery.id)).filter(
            EmailDelivery.event_key == definition.key,
            EmailDelivery.created_at >= now - timedelta(seconds=limit[1]),
            EmailDelivery.status != "SUPPRESSED",
        ).scalar() or 0
        return count >= limit[0]

    @staticmethod
    def _over_limit(db: Session, definition, rhash: Optional[str], now: datetime) -> bool:
        if not rhash:
            return False
        limit, window = recipient_limit(definition.key, definition.category.value)
        count = db.query(func.count(EmailDelivery.id)).filter(
            EmailDelivery.recipient_hash == rhash,
            EmailDelivery.event_key == definition.key,
            EmailDelivery.created_at >= now - timedelta(seconds=window),
            EmailDelivery.status.notin_(("SUPPRESSED",)),
        ).scalar() or 0
        return count >= limit


# Singleton used by the application.
email_service = NotificationEmailService()
