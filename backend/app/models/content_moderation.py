"""Phase 6 content moderation state (Child/Teen Safety s.10, s.11, s.15-18).

ContentModeration: the content-safety state of ONE governed contest entry
(an entry whose publication is decided by Phase 5/6). It is separate from the
Phase 5 participation record (contest_entry_safety): public exposure requires
both. Rows exist only for entries governed from Phase 6 on; historical entries
get no row (no fabricated review, rating or approval).

Stored: codes only. No content text, no matched PII, no media copies. The
action history is kept in the existing audit trail (AuditTrail rows with
table_name='content_moderation').
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class ContentModeration(Base):
    __tablename__ = "content_moderation"
    __table_args__ = (
        CheckConstraint("state IN ('PENDING', 'APPROVED', 'REVIEW_REQUIRED', 'PROHIBITED', 'CHILD_SAFETY_ESCALATED')",
                        name="ck_content_moderation_state"),
        CheckConstraint("rating IS NULL OR rating IN ('GENERAL', 'TEEN_13_PLUS', 'TEEN_16_PLUS', 'ADULT_18_PLUS', "
                        "'PROHIBITED')", name="ck_content_moderation_rating"),
        CheckConstraint("proposed_rating IS NULL OR proposed_rating IN ('GENERAL', 'TEEN_13_PLUS', 'TEEN_16_PLUS', "
                        "'ADULT_18_PLUS', 'PROHIBITED')", name="ck_content_moderation_proposed_rating"),
        CheckConstraint("classifier_status IN ('COMPLETED', 'PARTIAL', 'UNAVAILABLE', 'FAILED', 'NOT_RUN')",
                        name="ck_content_moderation_classifier"),
        CheckConstraint("child_safety_resolution IS NULL OR child_safety_resolution IN "
                        "('CONFIRMED', 'NO_CHILD_SAFETY_CONCERN')", name="ck_content_moderation_cs_resolution"),
        # An approved item always has a final rating, and never PROHIBITED.
        CheckConstraint("state <> 'APPROVED' OR (rating IS NOT NULL AND rating <> 'PROHIBITED')",
                        name="ck_content_moderation_approved_rating"),
        Index("ix_content_moderation_state", "state"),
        Index("ix_content_moderation_child_safety", "child_safety_escalated"),
    )

    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id", ondelete="CASCADE"),
                                               nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    rating: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)            # final (moderator/automated)
    proposed_rating: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)   # automated proposal only
    findings: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)               # SafetyConcern codes
    resolved_findings: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)      # codes resolved by review
    classifier_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_RUN")
    classifier_version: Mapped[str] = mapped_column(String(40), nullable=False)
    # Explicit per-dimension coverage {CoverageDimension: CoverageStatus}: what was
    # actually evaluated, as opposed to what was merely not detected.
    coverage: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    update_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subject_possibly_minor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    child_safety_escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    child_safety_escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    child_safety_resolution: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    child_safety_resolved_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    child_safety_resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    decided_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                                              nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    automated_decision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
