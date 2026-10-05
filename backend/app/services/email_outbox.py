"""Outbox worker: sends what email_service.enqueue recorded (EMAIL-1).

One pass:
  1. rows stuck in PROCESSING (a worker died mid-send) go back to QUEUED;
  2. a bounded batch of due QUEUED rows is claimed with
     SELECT ... FOR UPDATE SKIP LOCKED and marked PROCESSING in the same
     transaction, so two overlapping passes (or two processes) never take the
     same row;
  3. each claimed row is re-checked against the send policy, rendered, sent
     through the provider abstraction and updated on its own.

Retry: only transient failures (timeout, network, HTTP 429, provider 5xx),
with exponential backoff, up to EMAIL_MAX_ATTEMPTS. Anything else, or the last
attempt, ends in FAILED. Final failures are visible in Admin > Email Settings;
the worker never sends an alert email about a failing email provider.

Retention: when a row reaches a terminal state (SENT, FAILED, SUPPRESSED) its
encrypted payload (recipient address + template values) is deleted. The masked
recipient, the keyed recipient hash, the status and the timestamps remain.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redaction import mask_email
from app.models.email import EmailDelivery
from app.services import email_crypto, email_settings_service as policy
from app.services.email_events import EMAIL_EVENTS, TEST_EMAIL_KEY
from app.services.email_providers import EmailMessage, EmailProvider, ProviderResult, get_provider
from app.services.email_render import RenderError, render

logger = logging.getLogger(__name__)

STALE_PROCESSING_AFTER = timedelta(minutes=15)
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 3600
TERMINAL_STATUSES = ("SENT", "DELIVERED", "FAILED", "BOUNCED", "COMPLAINED", "SUPPRESSED")


def backoff_seconds(attempt: int) -> int:
    """Delay before the next try after `attempt` failed tries: 1m, 2m, 4m, 8m ... capped at 1h."""
    return min(BACKOFF_BASE_SECONDS * (2 ** max(attempt - 1, 0)), BACKOFF_MAX_SECONDS)


def _finish(row: EmailDelivery, status: str, now: datetime, *, category: Optional[str] = None,
            code: Optional[str] = None) -> None:
    row.status = status
    row.failure_category = category
    row.failure_code = code
    row.locked_at = None
    row.next_attempt_at = None
    row.payload_ciphertext = None      # retention: nothing sensitive outlives the delivery
    row.updated_at = now
    if status == "SENT":
        row.sent_at = now
    elif status == "FAILED":
        row.failed_at = now


def _requeue_stale(db: Session, now: datetime) -> int:
    stale = db.query(EmailDelivery).filter(EmailDelivery.status == "PROCESSING",
                                           EmailDelivery.locked_at < now - STALE_PROCESSING_AFTER).all()
    for row in stale:
        row.status = "QUEUED"
        row.locked_at = None
        row.next_attempt_at = now
        row.updated_at = now
    if stale:
        db.commit()
    return len(stale)


def claim_batch(db: Session, *, now: datetime, batch_size: int) -> List[int]:
    """Atomically take up to `batch_size` due rows. Returns their ids."""
    rows = (db.query(EmailDelivery)
            .filter(EmailDelivery.status == "QUEUED",
                    (EmailDelivery.next_attempt_at.is_(None)) | (EmailDelivery.next_attempt_at <= now))
            .order_by(EmailDelivery.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
            .all())
    for row in rows:
        row.status = "PROCESSING"
        row.locked_at = now
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.updated_at = now
    ids = [row.id for row in rows]
    db.commit()
    return ids


def _send_one(db: Session, row: EmailDelivery, provider: EmailProvider, now: datetime) -> str:
    settings_row = policy.get_settings(db)
    definition = EMAIL_EVENTS.get(row.event_key)
    if definition is None and row.event_key != TEST_EMAIL_KEY:
        _finish(row, "FAILED", now, category="unknown_event")
        return row.status
    # The switches are checked again at send time: an email queued before an
    # Emergency Stop or a switch-off is not sent afterwards.
    decision = policy.evaluate(db, definition, row=settings_row)
    if not decision.allowed:
        _finish(row, decision.status, now, category=decision.reason)
        return row.status
    try:
        payload = email_crypto.decrypt_payload(row.payload_ciphertext)
        to = payload["to"]
        subject, html, text = render(db, event_key=row.event_key, to=to, user_id=row.user_id,
                                     context=payload.get("context"), lang=row.lang,
                                     support_email=policy.support_address(settings_row))
    except RenderError as exc:
        _finish(row, "FAILED", now, category="render_error", code=exc.code[:40])
        return row.status
    except Exception as exc:  # noqa: BLE001 - unreadable payload / template failure: not retryable
        logger.error("Email delivery %s could not be rendered: %s", row.id, type(exc).__name__)
        _finish(row, "FAILED", now, category="render_error", code=type(exc).__name__[:40])
        return row.status

    message = EmailMessage(to=to, subject=subject, html=html, text=text,
                           from_header=policy.from_header(settings_row), reply_to=settings_row.reply_to or None)
    try:
        result = provider.send(message, api_key=decision.api_key)
    except Exception as exc:  # noqa: BLE001 - a provider must not raise; treat as transient
        result = ProviderResult(False, retryable=True, error_category="provider_exception",
                                error_code=type(exc).__name__[:40])
    row.provider = provider.name
    if result.success:
        row.provider_message_id = result.provider_message_id
        _finish(row, "SENT", now)
        logger.info("Email %s sent to %s (delivery %s)", row.event_key, row.recipient_masked, row.id)
    elif result.retryable and int(row.attempt_count or 0) < max(int(settings.EMAIL_MAX_ATTEMPTS), 1):
        row.status = "QUEUED"
        row.locked_at = None
        row.failure_category = result.error_category
        row.failure_code = result.error_code
        row.next_attempt_at = now + timedelta(seconds=backoff_seconds(int(row.attempt_count or 1)))
        row.updated_at = now
        logger.warning("Email %s attempt %s failed for %s (delivery %s, %s/%s); will retry", row.event_key,
                       row.attempt_count, row.recipient_masked, row.id, result.error_category, result.error_code)
    else:
        _finish(row, "FAILED", now, category=result.error_category, code=result.error_code)
        logger.warning("Email %s failed for %s (delivery %s, %s)", row.event_key, row.recipient_masked, row.id,
                       result.error_category)
    return row.status


def process_outbox(db: Session, *, now: Optional[datetime] = None, batch_size: Optional[int] = None,
                   provider: Optional[EmailProvider] = None) -> Dict[str, Any]:
    """One worker pass. Safe to run concurrently and never raises for a single
    bad row."""
    now = now or datetime.utcnow()
    summary: Dict[str, Any] = {"requeued": _requeue_stale(db, now), "claimed": 0, "sent": 0, "retry": 0,
                               "failed": 0, "suppressed": 0}
    ids = claim_batch(db, now=now, batch_size=int(batch_size or settings.EMAIL_OUTBOX_BATCH_SIZE))
    summary["claimed"] = len(ids)
    if not ids:
        return summary
    provider = provider or get_provider()
    for delivery_id in ids:
        try:
            row = db.query(EmailDelivery).filter(EmailDelivery.id == delivery_id).first()
            if row is None or row.status != "PROCESSING":
                continue
            status = _send_one(db, row, provider, now)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - one row must not stop the batch
            db.rollback()
            logger.error("Email delivery %s failed unexpectedly: %s", delivery_id, type(exc).__name__)
            status = _fail_after_error(db, delivery_id, now)
        summary[{"SENT": "sent", "QUEUED": "retry", "FAILED": "failed", "SUPPRESSED": "suppressed"}
                .get(status, "failed")] += 1
    return summary


def _fail_after_error(db: Session, delivery_id: int, now: datetime) -> str:
    try:
        row = db.query(EmailDelivery).filter(EmailDelivery.id == delivery_id).first()
        if row is not None and row.status == "PROCESSING":
            _finish(row, "FAILED", now, category="internal_error")
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return "FAILED"


# ---------------------------------------------------------------------------
# Admin test email (a tool, not a business event)
# ---------------------------------------------------------------------------

def send_test_email(db: Session, *, recipient: str, actor_id: Optional[int],
                    provider: Optional[EmailProvider] = None, now: Optional[datetime] = None) -> EmailDelivery:
    """Send ONE clearly labelled test message to ONE address, right away, and
    record it in the delivery log. Returns the delivery row (SENT or FAILED /
    SUPPRESSED with a safe reason)."""
    now = now or datetime.utcnow()
    address = str(recipient or "").strip()
    if not policy.valid_email(address):
        raise ValueError("A single valid recipient address is required.")
    settings_row = policy.get_settings(db)
    decision = policy.evaluate(db, None, row=settings_row)
    row = EmailDelivery(event_key=TEST_EMAIL_KEY, category="SYSTEM", user_id=actor_id,
                        recipient_masked=mask_email(address), recipient_hash=email_crypto.recipient_hash(address),
                        lang="en", status="PROCESSING", attempt_count=1, idempotency_key=f"system.test:{uuid.uuid4().hex}",
                        queued_at=now, locked_at=now, created_at=now, updated_at=now)
    db.add(row)
    db.flush()
    if not decision.allowed:
        _finish(row, decision.status, now, category=decision.reason)
        db.commit()
        return row
    subject, html, text = render(db, event_key=TEST_EMAIL_KEY, to=address, user_id=actor_id, context={}, lang="en",
                                 support_email=policy.support_address(settings_row))
    provider = provider or get_provider()
    try:
        result = provider.send(EmailMessage(to=address, subject=subject, html=html, text=text,
                                            from_header=policy.from_header(settings_row),
                                            reply_to=settings_row.reply_to or None), api_key=decision.api_key)
    except Exception as exc:  # noqa: BLE001
        result = ProviderResult(False, error_category="provider_exception", error_code=type(exc).__name__[:40])
    row.provider = provider.name
    if result.success:
        row.provider_message_id = result.provider_message_id
        _finish(row, "SENT", now)
    else:
        _finish(row, "FAILED", now, category=result.error_category, code=result.error_code)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Health (Admin overview)
# ---------------------------------------------------------------------------

def health(db: Session, *, now: Optional[datetime] = None) -> Dict[str, int]:
    from sqlalchemy import func

    now = now or datetime.utcnow()
    since = now - timedelta(hours=24)
    by_status = dict(db.query(EmailDelivery.status, func.count(EmailDelivery.id))
                     .filter(EmailDelivery.created_at >= since).group_by(EmailDelivery.status).all())
    open_counts = dict(db.query(EmailDelivery.status, func.count(EmailDelivery.id))
                       .filter(EmailDelivery.status.in_(("QUEUED", "PROCESSING")))
                       .group_by(EmailDelivery.status).all())
    return {
        "queued": int(open_counts.get("QUEUED", 0)),
        "processing": int(open_counts.get("PROCESSING", 0)),
        "sent_24h": int(by_status.get("SENT", 0)) + int(by_status.get("DELIVERED", 0)),
        "failed_24h": int(by_status.get("FAILED", 0)) + int(by_status.get("BOUNCED", 0)),
        "suppressed_24h": int(by_status.get("SUPPRESSED", 0)),
    }


# ---------------------------------------------------------------------------
# In-process scheduler (same shape as the other schedulers)
# ---------------------------------------------------------------------------

def run_outbox_once() -> Dict[str, Any]:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        return process_outbox(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class EmailOutboxScheduler:
    """Drains the email outbox. The blocking work runs in a worker thread."""

    def __init__(self, interval_seconds: Optional[int] = None):
        self.interval = max(int(interval_seconds or settings.EMAIL_OUTBOX_INTERVAL_SECONDS), 2)
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Email outbox scheduler started (interval: %ss, enabled: %s)", self.interval,
                    settings.EMAIL_OUTBOX_ENABLED)

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        await asyncio.sleep(15)   # let the application finish starting
        while self.running:
            try:
                await self._drain_outbox()
            except Exception as exc:  # noqa: BLE001 - the scheduler must never die
                logger.error("Email outbox pass failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval)

    async def _drain_outbox(self):
        if not settings.EMAIL_OUTBOX_ENABLED:
            return
        await asyncio.to_thread(run_outbox_once)
