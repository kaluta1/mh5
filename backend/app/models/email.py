"""Email system (EMAIL-1): settings, event overrides, outbox/delivery log.

EmailSettings        one configuration row (id = 1).
EmailEventSetting    Admin OVERRIDES of an event's enabled state; the default
                     lives in the source-controlled registry (email_events).
EmailDelivery        the persistent outbox AND the delivery history.
EmailWebhookEvent    provider webhook events (EMAIL-5): one row per provider
                     event id; the ordered history of what the provider said.

Privacy: a delivery row never stores an email body. The recipient address and
the template values travel only inside `payload_ciphertext` (AES-256-GCM) and
that column is cleared when the delivery reaches a terminal state. What remains
is a masked recipient for display and a keyed hash for counting/lookup.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

DELIVERY_STATUSES = ("QUEUED", "PROCESSING", "SENT", "DELIVERED", "DELAYED", "FAILED", "BOUNCED", "COMPLAINED",
                     "SUPPRESSED")


class EmailSettings(Base):
    __tablename__ = "email_settings"

    # Normal master switch: non-critical application email.
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Emergency stop: no application email at all, critical ones included.
    emergency_stop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # May the Resend provider be used?
    resend_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    from_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    from_address: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    reply_to: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    support_address: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    admin_alert_recipients: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)
    # Admin override of the Resend API key: AES-256-GCM ciphertext only.
    resend_api_key_ciphertext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resend_api_key_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    resend_api_key_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resend_api_key_updated_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Reserved for EMAIL-5 (same encrypted-secret pattern).
    webhook_secret_ciphertext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                      nullable=True)


class EmailEventSetting(Base):
    __tablename__ = "email_event_settings"

    event_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                      nullable=True)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED', 'PROCESSING', 'SENT', 'DELIVERED', 'DELAYED', 'FAILED', 'BOUNCED', "
                        "'COMPLAINED', 'SUPPRESSED')", name="ck_email_deliveries_status"),
        Index("ix_email_deliveries_status_next", "status", "next_attempt_at"),
        Index("ix_email_deliveries_event_key", "event_key"),
        Index("ix_email_deliveries_recipient_hash", "recipient_hash", "created_at"),
        Index("ix_email_deliveries_created_at", "created_at"),
    )

    event_key: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                   nullable=True)
    recipient_masked: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    # Recipient + template values, encrypted; cleared at a terminal state.
    payload_ciphertext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    failure_category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class EmailWebhookEvent(Base):
    __tablename__ = "email_webhook_events"

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    email_delivery_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("email_deliveries.id", ondelete="SET NULL"), nullable=True, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # Safe metadata only (never the raw webhook body).
    meta: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)
    # EMAIL-5. The provider's message id, kept on the event itself so an event
    # that arrives before its delivery is known can be matched later.
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    # When the provider says it happened (events can arrive out of order).
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # When it was applied to a delivery (NULL while unmatched), and how.
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
