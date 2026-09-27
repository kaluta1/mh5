"""Phase 8 progression safety holds (Child/Teen Safety: voting, TopHigh5 and progression).

ProgressionSafetyHold: one row per (contestant, destination season) where the
normal lifecycle would have advanced the contestant (they qualified by the
unchanged ranking, or an entry-stage sync would have added them) but the
centralized participation decision refused it at that moment.

The row is the durable, machine-readable record of that refusal. It never
deletes, demotes or re-ranks anything: the contestant's votes, ranking position
and source-season membership stay exactly as they were, and nobody else is
promoted into the held slot. When the safety requirement is later resolved,
the hold is released through the same lifecycle (same destination season) if
that stage is still running, or flagged REVIEW_REQUIRED for an administrator
when its timing has passed (no month is skipped or invented).

Stored: ids, levels, status and reason CODES only. No DOB, age, guardian
evidence, moderation text, content or media.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

HOLD_STATUSES = ("HELD", "RELEASED", "REVIEW_REQUIRED")


class ProgressionSafetyHold(Base):
    __tablename__ = "progression_safety_holds"
    __table_args__ = (
        UniqueConstraint("contestant_id", "to_season_id", name="uq_progression_safety_holds_contestant_to_season"),
        CheckConstraint("status IN ('HELD', 'RELEASED', 'REVIEW_REQUIRED')", name="ck_progression_safety_holds_status"),
        Index("ix_progression_safety_holds_status", "status"),
        Index("ix_progression_safety_holds_contestant", "contestant_id"),
    )

    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id", ondelete="CASCADE"),
                                               nullable=False)
    contest_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest.id", ondelete="SET NULL"),
                                                      nullable=True)
    round_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # NULL for an entry-stage hold (submission/nomination -> first voting season).
    from_season_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("contest_seasons.id", ondelete="SET NULL"), nullable=True)
    to_season_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_seasons.id", ondelete="CASCADE"),
                                              nullable=False)
    from_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_level: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="HELD")
    reason_codes: Mapped[Optional[list]] = mapped_column(_JSON, nullable=True)
    held_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
