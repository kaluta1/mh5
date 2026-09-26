"""Phase 5 contest age eligibility state (Child/Teen Safety s.9-12, s.14, s.17, s.19).

- ContestAgeEligibility (s.9): versioned age rules for one contest, optionally
  per jurisdiction ('*' = every jurisdiction).
- CategoryAgePolicy (s.17, s.19): versioned age rules for one category
  (categories.id, the table Contest.category_id points at). A row with a
  specific jurisdiction is that jurisdiction's override ("jurisdiction_overrides").
  ADULT_ONLY_CATEGORY is the adult_only flag.
- ContestEntrySafety: one row per contest entry created after Phase 5. It keeps
  the entry's actors apart (s.12: nominator, nominee, creative owner, account
  holder, guardian), the eligibility decision that was made, the open
  requirements, and the workflow-level public-exposure status. Entries created
  before Phase 5 have no row and are left exactly as they are.

Nothing here stores a date of birth or an exact age. An age tier is stored only
as the tier seen at decision time, for audit. It is never read back as truth:
eligibility is always recomputed from the current DOB, policy and consent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

_RULE_STATUS_CHECK = "status IN ('DRAFT', 'ACTIVE', 'WITHDRAWN')"
_RATING_CHECK = ("content_age_rating IS NULL OR content_age_rating IN "
                 "('GENERAL', 'TEEN_13_PLUS', 'TEEN_16_PLUS', 'ADULT_18_PLUS')")
_AGES_CHECK = ("(minimum_age IS NULL OR (minimum_age >= 0 AND minimum_age <= 120)) AND "
               "(maximum_age IS NULL OR (maximum_age >= 0 AND maximum_age <= 120)) AND "
               "(minimum_age IS NULL OR maximum_age IS NULL OR minimum_age <= maximum_age)")


class _AgeRuleColumns:
    """Columns shared by contest and category age rules."""

    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, default="*")
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    minimum_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    maximum_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eligible_age_tiers: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)  # None = every tier
    minor_participation_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    adult_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parental_consent_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    publicity_consent_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_age_rating: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Stored for Phase 10 (prize/financial eligibility). Phase 5 never evaluates them.
    prize_restrictions: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)
    financial_restrictions: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    changed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ContestAgeEligibility(_AgeRuleColumns, Base):
    __tablename__ = "contest_age_eligibility"
    __table_args__ = (
        CheckConstraint(_RULE_STATUS_CHECK, name="ck_contest_age_eligibility_status"),
        CheckConstraint(_RATING_CHECK, name="ck_contest_age_eligibility_rating"),
        CheckConstraint(_AGES_CHECK, name="ck_contest_age_eligibility_ages"),
        # At most one ACTIVE rule per contest and jurisdiction.
        Index("uq_contest_age_eligibility_active", "contest_id", "jurisdiction", unique=True,
              postgresql_where=text("status = 'ACTIVE'"), sqlite_where=text("status = 'ACTIVE'")),
        Index("ix_contest_age_eligibility_contest", "contest_id"),
    )

    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id", ondelete="CASCADE"), nullable=False)


class CategoryAgePolicy(_AgeRuleColumns, Base):
    __tablename__ = "category_age_policies"
    __table_args__ = (
        CheckConstraint(_RULE_STATUS_CHECK, name="ck_category_age_policies_status"),
        CheckConstraint(_RATING_CHECK, name="ck_category_age_policies_rating"),
        CheckConstraint(_AGES_CHECK, name="ck_category_age_policies_ages"),
        Index("uq_category_age_policies_active", "category_id", "jurisdiction", unique=True,
              postgresql_where=text("status = 'ACTIVE'"), sqlite_where=text("status = 'ACTIVE'")),
        Index("ix_category_age_policies_category", "category_id"),
    )

    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)


class ContestEntrySafety(Base):
    __tablename__ = "contest_entry_safety"
    __table_args__ = (
        CheckConstraint("entry_kind IN ('PERSONAL_SUBMISSION', 'NOMINATION')", name="ck_contest_entry_safety_kind"),
        CheckConstraint("exposure_status IN ('PUBLIC', 'HELD', 'BLOCKED', 'CHILD_SAFETY_ESCALATED')",
                        name="ck_contest_entry_safety_exposure"),
        CheckConstraint("nominee_age_declaration IS NULL OR nominee_age_declaration IN ('ADULT', 'MINOR', 'UNKNOWN')",
                        name="ck_contest_entry_safety_declaration"),
        CheckConstraint("creative_owner_type IN ('SELF', 'NOMINEE', 'THIRD_PARTY', 'UNKNOWN')",
                        name="ck_contest_entry_safety_owner"),
        CheckConstraint("rights_status IN ('NOT_REQUIRED', 'PENDING', 'CONFIRMED', 'DISPUTED')",
                        name="ck_contest_entry_safety_rights"),
        CheckConstraint("safety_status IN ('CLEAR', 'REVIEW_REQUIRED', 'REVIEWED_CLEAR', 'BLOCKED', "
                        "'CHILD_SAFETY_ESCALATED')", name="ck_contest_entry_safety_safety"),
        CheckConstraint("metadata_status IN ('NOT_REQUIRED', 'SANITIZED', 'UNRESOLVED')",
                        name="ck_contest_entry_safety_metadata"),
        Index("ix_contest_entry_safety_exposure", "exposure_status"),
        Index("ix_contest_entry_safety_submitted_by", "submitted_by_user_id"),
        Index("ix_contest_entry_safety_nominee", "nominee_user_id"),
        Index("uq_contest_entry_safety_claim_token", "claim_token_hash", unique=True),
    )

    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id", ondelete="CASCADE"),
                                               nullable=False, unique=True)
    contest_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest.id", ondelete="SET NULL"),
                                                      nullable=True)
    entry_kind: Mapped[str] = mapped_column(String(30), nullable=False)

    # s.12 actors. None of them is ever inferred from another.
    # submitted_by: the person who submitted (personal submitter, or the NOMINATOR).
    submitted_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # account_holder: the account that holds the entry row (contestants.user_id).
    account_holder_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # nominee: only an independently confirmed nominee account (set by an
    # administrator), never from the nominator's input.
    nominee_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    creative_owner_type: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN")
    creative_owner_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # guardian: the VERIFIED relationship whose consent currently satisfies the
    # entry (from the Phase 4 consent service), never a claim by the nominator.
    guardian_relationship_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("guardian_relationships.id", ondelete="SET NULL"), nullable=True)

    # The nominator's attestation about the nominee (not verification).
    nominee_age_declaration: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Nominee claim (s.12 "Nominee notified"): a single-use, expiring claim link
    # the nominator passes to the nominee. Only the SHA-256 hash is stored and it
    # is cleared once used. Claiming links the nominee's own account; it never
    # makes anyone a guardian.
    claim_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    claim_token_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    claim_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    claim_declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Current workflow state.
    exposure_status: Mapped[str] = mapped_column(String(30), nullable=False, default="HELD")
    workflow_step: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    rights_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_REQUIRED")
    safety_status: Mapped[str] = mapped_column(String(30), nullable=False, default="CLEAR")
    safety_concerns: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)
    metadata_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_REQUIRED")
    # Result of the contest min/max age check. The window is checked on every
    # evaluation until the entry is first activated, then no longer (a birthday
    # never removes an active participant). See the service docstring.
    age_window_ok_at_entry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Last decision (codes only; no DOB, age, threshold or guardian identity).
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_codes: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)
    missing_consent_scopes: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)
    decision_basis: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    enforced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subject_age_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("age_policies.id"), nullable=True)
    policy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
