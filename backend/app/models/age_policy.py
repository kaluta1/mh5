"""Versioned jurisdiction age policy (Child/Teen Safety requirement, section 3).

Rows are data, not code: administrators manage them without source changes.
History is preserved: an ACTIVE row is never edited in place. A change is a new
policy_version. Determinism is guarded in the database by a partial unique index:
at most one ACTIVE policy per (jurisdiction, effective_date).

The structured rule columns are validated by app.schemas.age_policy before they
are written.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")

AGE_THRESHOLD_COLUMNS = (
    "minimum_account_age",
    "minimum_independent_participation_age",
    "parental_consent_age",
    "adult_age",
    "voting_minimum_age",
    "nomination_minimum_age",
    "personal_submission_minimum_age",
    "livestream_minimum_age",
    "prize_contract_age",
    "payment_minimum_age",
)


class AgePolicy(Base):
    __tablename__ = "age_policies"
    __table_args__ = (
        UniqueConstraint("jurisdiction", "policy_version", name="uq_age_policies_jurisdiction_version"),
        Index(
            "uq_age_policies_active_jurisdiction_effective",
            "jurisdiction",
            "effective_date",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'WITHDRAWN')", name="ck_age_policies_status"),
        CheckConstraint("policy_version >= 1", name="ck_age_policies_version_positive"),
        CheckConstraint("nomination_age_applies_to IS NULL OR nomination_age_applies_to IN "
                        "('NOMINATOR', 'NOMINEE', 'BOTH')", name="ck_age_policies_nomination_scope"),
        *(
            CheckConstraint(f"{col} BETWEEN 0 AND 120", name=f"ck_age_policies_{col}_range")
            for col in AGE_THRESHOLD_COLUMNS
        ),
    )

    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    minimum_account_age: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_independent_participation_age: Mapped[int] = mapped_column(Integer, nullable=False)
    parental_consent_age: Mapped[int] = mapped_column(Integer, nullable=False)
    adult_age: Mapped[int] = mapped_column(Integer, nullable=False)
    voting_minimum_age: Mapped[int] = mapped_column(Integer, nullable=False)
    nomination_minimum_age: Mapped[int] = mapped_column(Integer, nullable=False)
    personal_submission_minimum_age: Mapped[int] = mapped_column(Integer, nullable=False)
    livestream_minimum_age: Mapped[int] = mapped_column(Integer, nullable=False)
    prize_contract_age: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_minimum_age: Mapped[int] = mapped_column(Integer, nullable=False)

    kyc_requirement: Mapped[dict] = mapped_column(_JSON, nullable=False)
    age_assurance_level: Mapped[dict] = mapped_column(_JSON, nullable=False)
    parental_consent_requirement: Mapped[dict] = mapped_column(_JSON, nullable=False)
    permitted_content_ratings: Mapped[dict] = mapped_column(_JSON, nullable=False)
    advertising_restrictions: Mapped[dict] = mapped_column(_JSON, nullable=False)
    profile_visibility_rules: Mapped[dict] = mapped_column(_JSON, nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Phase 5: which nomination actor nomination_minimum_age applies to. The source
    # (s.3) does not say; the policy author must state it. NULL = not stated, and
    # NOMINATION cannot then be enforced under this policy (entries are held).
    nomination_age_applies_to: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    status_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status_changed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
