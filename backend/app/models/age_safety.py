"""Phase 3 age-safety state (Child/Teen Safety requirement, s.2-6, s.32).

- UserAgeProfile: provenance and assurance of a user's date of birth, jurisdiction
  resolved at registration, the registration gate decision and escalation state.
  The DOB itself stays in users.date_of_birth (single source); age and tier are
  always computed on demand, never stored. A user without a row is a legacy user:
  DOB (if any) = LEGACY_PROFILE, SELF_DECLARED at most.
- DobChangeRecord: restricted history of every DOB change or change request
  (previous/requested values), including pending reviews.
- AgeSafetyEvent: append-only safety event log for the age gate and DOB changes.
  Identifiers are HMAC hashes (email, IP). It holds no raw DOB, email, IP or
  device fingerprint.
- ChildSafetyEnforcement: explicit, auditable switch deciding whether an
  operation's age policy is enforced for a jurisdiction ('*' = all).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class UserAgeProfile(Base):
    __tablename__ = "user_age_profiles"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('NONE', 'AGE_VERIFICATION_REQUIRED', 'AGE_REVIEW_REQUIRED')",
            name="ck_user_age_profiles_review_status",
        ),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    dob_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    assurance_level: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    jurisdiction_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    registration_decision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    registration_policy_outcome: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    registration_enforced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    registration_policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("age_policies.id"), nullable=True)
    registration_policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="NONE")
    review_reason: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    review_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # When the user accepted the Terms of Service and Privacy Notice at registration
    # (backend-enforced accept_terms=true). LIMITATION: MyHigh5 has no versioned
    # Terms/Privacy documents yet, so this proves THAT and WHEN acceptance happened,
    # not WHICH document version. No version is invented. Guardian consent is a
    # separate concept (Phase 4) and never recorded here.
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DobChangeRecord(Base):
    __tablename__ = "dob_change_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AUTO_APPLIED', 'PENDING', 'APPROVED', 'REJECTED', 'ADMIN_APPLIED')",
            name="ck_dob_change_records_status",
        ),
        # At most one pending review per user.
        Index(
            "uq_dob_change_records_one_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
            sqlite_where=text("status = 'PENDING'"),
        ),
        Index("ix_dob_change_records_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    previous_dob: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    requested_dob: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    requested_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AgeSafetyEvent(Base):
    __tablename__ = "age_safety_events"
    __table_args__ = (
        Index("ix_age_safety_events_email_hash_created", "email_hash", "created_at"),
        Index("ix_age_safety_events_ip_hash_created", "ip_hash", "created_at"),
        Index("ix_age_safety_events_user_created", "user_id", "created_at"),
        Index("ix_age_safety_events_type_created", "event_type", "created_at"),
    )

    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    age_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    enforced: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)


class ChildSafetyEnforcement(Base):
    __tablename__ = "child_safety_enforcement"
    __table_args__ = (
        UniqueConstraint("operation", "jurisdiction", name="uq_child_safety_enforcement_operation_jurisdiction"),
    )

    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
