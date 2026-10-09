"""Finance & Payments configuration (Admin-managed).

PaymentSettings            one row (id = 1): every non-secret business setting
                           of the payment provider and of the dual cashout.
PaymentCredential          provider credentials, AES-256-GCM ciphertext only
                           (app.services.payment_crypto). Never a plaintext.
PaymentConfigAudit         append-only, versioned history of configuration
                           changes: who, when, which fields. Never a secret.
PayoutWalletVerification   one pending email confirmation of a payout wallet;
                           only a digest of the one-time token is stored.
PaymentWebhookStat         bounded per-day counters of provider callbacks by
                           outcome (webhook health; never a request body).

The defaults of every setting live in app.services.payment_config, which is
the only module that reads or writes these tables.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
_USER_FK = dict(nullable=True)


class PaymentSettings(Base):
    __tablename__ = "payment_settings"

    # Incremented by every accepted change; the audit rows carry it.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ---- provider -----------------------------------------------------------
    provider_display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Where each credential group is read from: ENVIRONMENT or DATABASE. Never mixed.
    payin_credential_source: Mapped[str] = mapped_column(String(12), nullable=False)
    payout_credential_source: Mapped[str] = mapped_column(String(12), nullable=False)

    # ---- crypto cashout -----------------------------------------------------
    crypto_cashout_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    crypto_auto_payout_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    crypto_min_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    crypto_payout_currency: Mapped[str] = mapped_column(String(20), nullable=False)
    network_fee_policy: Mapped[str] = mapped_column(String(16), nullable=False)
    max_network_fee_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    payout_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_single_payout_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_daily_payout_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    max_daily_payout_count: Mapped[int] = mapped_column(Integer, nullable=False)
    min_hours_between_payouts: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_backoff_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_balance_reserve_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # ---- payout security ----------------------------------------------------
    wallet_email_verification_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    wallet_hold_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    wallet_max_changes_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    wallet_verification_ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    # ---- USD cashout --------------------------------------------------------
    usd_cashout_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usd_min_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    usd_fee_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    usd_fee_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    usd_fee_max: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    usd_settlement_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usd_settlement_account: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    usd_admin_approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usd_processing_policy: Mapped[str] = mapped_column(String(20), nullable=False)
    usd_member_cancellation_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usd_reference_min_length: Mapped[int] = mapped_column(Integer, nullable=False)
    usd_destination_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usd_destination_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ---- last connection test (sanitized: codes and numbers only) -----------
    last_connection_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_connection_test_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_connection_ok_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_connection_test_detail: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)

    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                      **_USER_FK)


class PaymentCredential(Base):
    __tablename__ = "payment_credentials"
    __table_args__ = (Index("uq_payment_credentials_provider_name", "provider", "name", unique=True),)

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    set_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), **_USER_FK)


class PaymentConfigAudit(Base):
    __tablename__ = "payment_config_audit"
    __table_args__ = (Index("ix_payment_config_audit_created_at", "created_at"),)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                    **_USER_FK)
    changed_fields: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)
    old_values: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)


class PayoutWalletVerification(Base):
    __tablename__ = "payout_wallet_verifications"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(20), nullable=False)
    # SHA-256 over the one-time token, the account, the address and the network.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)


class PaymentWebhookStat(Base):
    __tablename__ = "payment_webhook_stats"
    __table_args__ = (Index("uq_payment_webhook_stats", "provider", "day", "outcome", unique=True),)

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
