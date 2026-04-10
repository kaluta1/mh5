"""Month-end Founding Members pool allocation (2104 -> 2105) audit trail."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.accounting import JournalEntry


class FoundingPoolSnapshot(Base):
    """
    One row per calendar month. Workflow: draft (prepare) -> approved -> posted (journal).
    """

    __tablename__ = "founding_pool_snapshots"
    __table_args__ = (
        UniqueConstraint("period_year", "period_month", name="uq_founding_pool_calendar_month"),
    )

    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    accrued_pool_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    prepared_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[List["FoundingPoolSnapshotLine"]] = relationship(
        "FoundingPoolSnapshotLine", back_populates="snapshot", cascade="all, delete-orphan"
    )
    journal_entry: Mapped[Optional["JournalEntry"]] = relationship("JournalEntry", foreign_keys=[journal_entry_id])


class FoundingPoolSnapshotLine(Base):
    """Per-member share for a snapshot (subledger; GL uses aggregate 2105)."""

    __tablename__ = "founding_pool_snapshot_lines"
    __table_args__ = (UniqueConstraint("snapshot_id", "user_id", name="uq_founding_pool_line_user"),)

    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("founding_pool_snapshots.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    share_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    weight_ratio: Mapped[Optional[float]] = mapped_column(Numeric(12, 8), nullable=True)

    snapshot: Mapped["FoundingPoolSnapshot"] = relationship("FoundingPoolSnapshot", back_populates="lines")
