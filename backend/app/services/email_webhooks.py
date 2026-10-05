"""Provider delivery webhooks (EMAIL-5).

The provider reports what happened to a message AFTER it accepted it:
delivered, delayed, bounced, complained, failed. This module turns one
authenticated provider event into (a) a durable event row and (b) a safe
update of the delivery it belongs to.

Authentication is the provider's signature, verified by the provider layer
(app.services.email_providers) against the raw request body BEFORE anything
here runs. No user session is involved.

Durable identity / replay
-------------------------
Webhook delivery is at-least-once. The provider's own event id (the `svix-id`
header, identical on every redelivery of the same event) is stored under a
UNIQUE constraint. The first arrival inserts the row and applies the state;
any later arrival, sequential or concurrent, hits the constraint and changes
nothing. Nothing is deduplicated in memory.

Delivery state model
--------------------
`email_deliveries.status` is ONE value and only ever moves forward on this
ladder; an event never moves a delivery backwards:

    SENT < DELAYED < DELIVERED < FAILED < BOUNCED < COMPLAINED

* `email.sent` after DELIVERED, or `email.delivered` after BOUNCED, arrives
  late (the provider does not guarantee order): it is recorded, the status
  stays.
* A bounce or a complaint that follows a delivery is meaningful and DOES take
  over the status; `delivered_at` keeps the earlier fact.
* The full, ordered history of what the provider said is the event rows
  themselves (email_webhook_events), never lost to the single status.
BOUNCED, COMPLAINED and FAILED are terminal for the outbox: it only ever picks
up QUEUED rows, so a bounced delivery is never retried.

Association
-----------
Events carry the provider's message id; the delivery row stores it once the
send has been recorded. An event that arrives first (the provider can be
faster than our own commit), or for a message we do not know, is still stored
with outcome "unmatched" and applied later by `apply_pending` when the
delivery records that message id.

What this module never does
---------------------------
It does not deactivate or suppress an account, change an email address or
`email_verified`, or touch KYC, contests, payments or any business table. A
bounce or a complaint is recorded and shown; acting on it is a product
decision that has not been made. It stores no recipient address, subject,
body or raw payload: only event type, ids, timestamps and, for a bounce, the
provider's bounce classification.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.email import EmailDelivery, EmailWebhookEvent

logger = logging.getLogger(__name__)

PROVIDER_RESEND = "resend"

# provider event type -> delivery status it supports
STATE_EVENTS: Dict[str, str] = {
    "email.sent": "SENT",
    "email.delivery_delayed": "DELAYED",
    "email.delivered": "DELIVERED",
    "email.failed": "FAILED",
    "email.bounced": "BOUNCED",
    "email.complained": "COMPLAINED",
}
# Acknowledged and NOT stored: engagement tracking and inbound mail are not
# part of transactional delivery state, and opens/clicks are personal data
# this system has no use for.
IGNORED_EVENTS = frozenset({"email.opened", "email.clicked", "email.received", "email.scheduled"})

RANK = {"SENT": 1, "DELAYED": 2, "DELIVERED": 3, "FAILED": 4, "BOUNCED": 5, "COMPLAINED": 6}
# A delivery that was never handed to the provider cannot be moved by a webhook.
_PRE_SEND = ("QUEUED", "PROCESSING", "SUPPRESSED")

OUTCOME_APPLIED = "applied"          # the delivery's status moved
OUTCOME_RECORDED = "recorded"        # stored; the status was already at or beyond it
OUTCOME_UNMATCHED = "unmatched"      # stored; no delivery with this message id (yet)
OUTCOME_UNKNOWN_TYPE = "unknown_type"  # stored; an event type this code does not know
OUTCOME_IGNORED = "ignored"          # acknowledged, not stored
OUTCOME_DUPLICATE = "duplicate"      # this event id was already processed

MAX_ID_LENGTH = 160
MAX_MESSAGE_ID_LENGTH = 120


@dataclass(frozen=True)
class WebhookResult:
    outcome: str
    event_type: str = ""
    delivery_id: Optional[int] = None


class MalformedWebhook(ValueError):
    """An authenticated payload that is not an event object."""


def _clean(value: Any, limit: int) -> Optional[str]:
    if not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:                    # stored as naive UTC, like every other timestamp here
        parsed = (parsed - parsed.utcoffset()).replace(tzinfo=None)
    return parsed


def _safe_meta(event_type: str, data: Dict[str, Any]) -> Optional[dict]:
    """The only payload detail kept: how the provider classified a bounce.
    (The provider's free-text bounce message can contain the address: not kept.)"""
    if event_type != "email.bounced":
        return None
    bounce = data.get("bounce") if isinstance(data.get("bounce"), dict) else {}
    meta = {"bounce_type": _clean(bounce.get("type"), 40), "bounce_subtype": _clean(bounce.get("subType"), 40)}
    meta = {k: v for k, v in meta.items() if v}
    return meta or None


def _apply(row: EmailDelivery, event_type: str, occurred_at: Optional[datetime], meta: Optional[dict],
           now: datetime) -> str:
    """Move the delivery forward if the event supports a later state. Returns the outcome."""
    target = STATE_EVENTS[event_type]
    when = occurred_at or now
    if row.status in _PRE_SEND:
        return OUTCOME_RECORDED
    if target == "DELIVERED" and row.delivered_at is None:
        row.delivered_at = when                      # a fact worth keeping whatever the status is by now
    current = RANK.get(row.status, 0)
    if RANK[target] <= current:
        return OUTCOME_RECORDED
    row.status = target
    row.updated_at = now
    if target == "SENT" and row.sent_at is None:
        row.sent_at = when
    if target in ("FAILED", "BOUNCED", "COMPLAINED"):
        row.failed_at = row.failed_at or when
        row.failure_category = {"FAILED": "provider_failed", "BOUNCED": "bounced", "COMPLAINED": "complained"}[target]
        row.failure_code = (meta or {}).get("bounce_type") if target == "BOUNCED" else None
        row.next_attempt_at = None                   # terminal: never retried
    else:
        row.failure_category = None
        row.failure_code = None
    return OUTCOME_APPLIED


def process_event(db: Session, *, provider: str, event_id: str, payload: Any,
                  now: Optional[datetime] = None) -> WebhookResult:
    """Record one AUTHENTICATED provider event and apply it. Idempotent on
    (provider event id). Commits. Raises MalformedWebhook for a payload that is
    not an event; never raises for an unknown type or an unknown message."""
    now = now or datetime.utcnow()
    event_id = _clean(event_id, MAX_ID_LENGTH) or ""
    if not event_id or not isinstance(payload, dict):
        raise MalformedWebhook("not an event object")
    event_type = _clean(payload.get("type"), 60) if isinstance(payload.get("type"), str) else None
    if not event_type:
        raise MalformedWebhook("missing event type")
    if event_type in IGNORED_EVENTS:
        return WebhookResult(OUTCOME_IGNORED, event_type)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    message_id = _clean(data.get("email_id") or data.get("id"), MAX_MESSAGE_ID_LENGTH)
    occurred_at = _parse_time(payload.get("created_at")) or _parse_time(data.get("created_at"))
    known = event_type in STATE_EVENTS
    meta = _safe_meta(event_type, data) if known else None

    event = EmailWebhookEvent(provider=provider, provider_event_id=event_id, event_type=event_type,
                              provider_message_id=message_id, occurred_at=occurred_at, received_at=now,
                              meta=meta, created_at=now, updated_at=now)
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        # Already processed (a redelivery, or a concurrent copy that committed first).
        db.rollback()
        return WebhookResult(OUTCOME_DUPLICATE, event_type)

    outcome, delivery_id = OUTCOME_UNKNOWN_TYPE, None
    if known:
        outcome = OUTCOME_UNMATCHED
        if message_id:
            row = (db.query(EmailDelivery).filter(EmailDelivery.provider_message_id == message_id)
                   .order_by(EmailDelivery.id).with_for_update().first())
            if row is not None:
                delivery_id = row.id
                event.email_delivery_id = row.id
                outcome = _apply(row, event_type, occurred_at, meta, now)
    event.outcome = outcome
    event.processed_at = now if outcome != OUTCOME_UNMATCHED else None
    db.commit()
    if outcome in (OUTCOME_UNMATCHED, OUTCOME_UNKNOWN_TYPE):
        logger.info("Email webhook %s stored as %s", event_type, outcome)
    elif event_type in ("email.bounced", "email.complained", "email.failed"):
        logger.warning("Email delivery %s: provider reported %s", delivery_id, event_type)
    return WebhookResult(outcome, event_type, delivery_id)


def apply_pending(db: Session, row: EmailDelivery, *, now: Optional[datetime] = None) -> int:
    """Events that arrived before this delivery had recorded its provider
    message id: apply them now, oldest first. Called by the outbox right after
    it stores the id, inside the same transaction (no commit here)."""
    if not row.provider_message_id:
        return 0
    now = now or datetime.utcnow()
    pending = (db.query(EmailWebhookEvent)
               .filter(EmailWebhookEvent.provider_message_id == row.provider_message_id,
                       EmailWebhookEvent.email_delivery_id.is_(None),
                       EmailWebhookEvent.outcome == OUTCOME_UNMATCHED)
               .order_by(EmailWebhookEvent.occurred_at, EmailWebhookEvent.id).all())
    for event in pending:
        event.email_delivery_id = row.id
        event.outcome = (_apply(row, event.event_type, event.occurred_at, event.meta, now)
                         if event.event_type in STATE_EVENTS else OUTCOME_UNKNOWN_TYPE)
        event.processed_at = now
        event.updated_at = now
    return len(pending)
