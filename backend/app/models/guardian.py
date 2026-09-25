"""Guardian consent and teen privacy state (Child/Teen Safety s.2, s.4, s.7, s.12-14, s.24).

The actors are distinct. A guardian is never inferred from the minor, the
sponsor, a nominator, an ordinary adult account, an email owner or KYC status.

- Guardian: the person giving consent. Only a contact email is stored (plus
  its keyed hash for lookups), optionally linked later to a MyHigh5 account.
- GuardianRelationship: that guardian's claimed authority over ONE minor (an
  account, or a pending registration before the account exists), with an
  explicit verification state and method.
- GuardianConsent: one record per consent scope, with the s.13 fields
  (guardian_reference, minor_user_id, jurisdiction, consent_scope,
  verification_method, consent_timestamp, policy_version, withdrawal_status,
  expiry_if_applicable). Withdrawal sets withdrawal fields once; the grant
  facts are never rewritten or deleted.
- PendingRegistration: a single-purpose, expiring registration awaiting
  guardian consent. It is NOT a user, cannot log in, stores NO password
  (the minor sets one at completion) and stores token HASHES only.
- UserPrivacyPreference: optional, more-restrictive-only privacy choices.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class Guardian(Base):
    __tablename__ = "guardians"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PendingRegistration(Base):
    __tablename__ = "pending_registrations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AWAITING_GUARDIAN', 'APPROVED', 'COMPLETED', 'DECLINED', 'EXPIRED', 'CANCELLED')",
            name="ck_pending_registrations_status",
        ),
        # One open pending registration per (normalized) email.
        Index("uq_pending_registrations_open_email", "email_hash", unique=True,
              postgresql_where=text("status IN ('AWAITING_GUARDIAN', 'APPROVED')"),
              sqlite_where=text("status IN ('AWAITING_GUARDIAN', 'APPROVED')")),
        Index("ix_pending_registrations_guardian_token_hash", "guardian_token_hash", unique=True),
        Index("ix_pending_registrations_completion_token_hash", "completion_token_hash", unique=True),
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="AWAITING_GUARDIAN")
    # Minimum data needed to create the account later (purged after retention).
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    continent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sponsor_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("age_policies.id"), nullable=True)
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Single-use tokens: only SHA-256 hashes are stored.
    guardian_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    guardian_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    guardian_token_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completion_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    completion_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completion_token_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    data_purged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class GuardianRelationship(Base):
    __tablename__ = "guardian_relationships"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('PENDING', 'VERIFICATION_REQUIRED', 'VERIFIED', 'REJECTED', 'REVOKED', 'EXPIRED')",
            name="ck_guardian_relationships_status",
        ),
        CheckConstraint("relationship_type IS NULL OR relationship_type IN ('PARENT', 'LEGAL_GUARDIAN')",
                        name="ck_guardian_relationships_type"),
        CheckConstraint("minor_user_id IS NOT NULL OR pending_registration_id IS NOT NULL",
                        name="ck_guardian_relationships_subject"),
        Index("ix_guardian_relationships_minor", "minor_user_id"),
        Index("ix_guardian_relationships_pending", "pending_registration_id"),
    )

    guardian_id: Mapped[int] = mapped_column(Integer, ForeignKey("guardians.id"), nullable=False, index=True)
    minor_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    pending_registration_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("pending_registrations.id"), nullable=True)
    # Stated by the guardian when responding (never taken from the minor).
    relationship_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    verification_method: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verified_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    status_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("age_policies.id"), nullable=True)
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class GuardianConsent(Base):
    __tablename__ = "guardian_consents"
    __table_args__ = (
        CheckConstraint("withdrawal_status IN ('GRANTED', 'WITHDRAWN')", name="ck_guardian_consents_status"),
        # At most one currently-granted record per relationship and scope.
        Index("uq_guardian_consents_active_scope", "relationship_id", "consent_scope", unique=True,
              postgresql_where=text("withdrawal_status = 'GRANTED'"),
              sqlite_where=text("withdrawal_status = 'GRANTED'")),
        Index("ix_guardian_consents_minor_scope", "minor_user_id", "consent_scope"),
    )

    relationship_id: Mapped[int] = mapped_column(Integer, ForeignKey("guardian_relationships.id"), nullable=False)
    guardian_reference: Mapped[int] = mapped_column(Integer, ForeignKey("guardians.id"), nullable=False)
    minor_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    pending_registration_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("pending_registrations.id"), nullable=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    consent_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_method: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    consent_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("age_policies.id"), nullable=True)
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    withdrawal_status: Mapped[str] = mapped_column(String(20), nullable=False, default="GRANTED")
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    withdrawn_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    withdrawal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # expiry_if_applicable


class UserPrivacyPreference(Base):
    __tablename__ = "user_privacy_preferences"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    preferences: Mapped[dict] = mapped_column(_JSON, nullable=False)
