"""Customer checkout gateways (Admin-managed): which gateway collects member
payments, and the SoncoPay collection settings.

CheckoutGatewaySettings    one row (id = 1). No row = the defaults:
                           NOWPayments is the default checkout, SoncoPay is
                           off, in the Test environment.

SoncoPay API keys and webhook signing secrets are NOT here: they are kept as
AES-256-GCM ciphertext in payment_credentials (provider "soncopay"), one set
per environment. app.services.soncopay_settings is the only module that reads
or writes them.

SoncoPayWebhookEvent       one row per processed SoncoPay webhook delivery
                           (X-SoncoPay-Delivery-Id, unique). Written in the
                           same transaction as the deposit it changed, so a
                           retried delivery is never processed twice.

Nothing here is read by the NOWPayments payout engine (payment_settings): a
change to these settings can never change automatic commission payouts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class CheckoutGatewaySettings(Base):
    __tablename__ = "checkout_gateway_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_checkout_gateway_settings_single_row"),
        CheckConstraint("default_provider IN ('nowpayments', 'soncopay')",
                        name="ck_checkout_gateway_settings_default_provider"),
        CheckConstraint("soncopay_environment IN ('test', 'live')",
                        name="ck_checkout_gateway_settings_soncopay_environment"),
    )

    default_provider: Mapped[str] = mapped_column(String(30), nullable=False, default="nowpayments",
                                                  server_default="nowpayments")
    soncopay_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    soncopay_environment: Mapped[str] = mapped_column(String(10), nullable=False, default="test",
                                                      server_default="test")
    # Incremented by every accepted change: a change made on a stale page is refused.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                      nullable=True)
    # The owner's recorded confirmation that SoncoPay allows member commission payouts from this
    # merchant account (third-party payouts). Without it no member wallet is registered and nothing is paid.
    payouts_authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payouts_authorized_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                                 nullable=True)
    payouts_authorization_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class SoncoPayWebhookEvent(Base):
    __tablename__ = "soncopay_webhook_events"
    __table_args__ = (
        UniqueConstraint("delivery_id", name="uq_soncopay_webhook_events_delivery"),
        CheckConstraint("environment IN ('test', 'live')", name="ck_soncopay_webhook_events_environment"),
    )

    delivery_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(10), nullable=False)
    payment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    deposit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("deposits.id", ondelete="SET NULL"),
                                                      nullable=True, index=True)
    # PROCESSED | ACKNOWLEDGED (not a payment event) | UNKNOWN_PAYMENT
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)


class SoncoPayPayoutDestination(Base):
    """One approved member wallet as a SoncoPay payout destination (app.services.soncopay_payouts).

    Bound to exactly one wallet approval: a wallet change gives a new approval and a new row; the old
    row becomes SUPERSEDED and is never paid to. Status:
      QUEUED                approved in MyHigh5, not registered at SoncoPay yet (no free slot, or waiting)
      PENDING_CONFIRMATION  registered; a SoncoPay operator must confirm it in the dashboard
      ACTIVE                confirmed; payable only while `usable` (after the security waiting period)
      DISABLED / REJECTED   disabled or refused at SoncoPay: never paid to
      SUPERSEDED            the member's approval changed: disabled at SoncoPay, history only
    """
    __tablename__ = "soncopay_payout_destinations"
    __table_args__ = (
        UniqueConstraint("wallet_approval_id", name="uq_soncopay_destinations_approval"),
        UniqueConstraint("destination_id", name="uq_soncopay_destinations_destination"),
        CheckConstraint("environment IN ('test', 'live')", name="ck_soncopay_destinations_environment"),
        CheckConstraint("status IN ('QUEUED', 'PENDING_CONFIRMATION', 'ACTIVE', 'DISABLED', 'REJECTED', 'SUPERSEDED')",
                        name="ck_soncopay_destinations_status"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    wallet_approval_id: Mapped[int] = mapped_column(Integer, ForeignKey("payout_wallet_approvals.id"), nullable=False)
    address: Mapped[str] = mapped_column(String(100), nullable=False)
    environment: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", index=True)
    destination_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    usable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    usable_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    registered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
