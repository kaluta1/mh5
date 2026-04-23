"""Founding Membership Points (FMP) ledger for FMR (Founding Membership Ratio) pool splits."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class MemberFmpLedger(Base):
    """
    Immutable accrual rows: +1 FMP for founding join fee, +1 per direct referral KYC complete.
    """

    __tablename__ = "member_fmp_ledger"
    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_id", "user_id", name="uq_member_fmp_ledger_source_user"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)  # FOUNDING_JOIN | REFERRAL_VERIFIED
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemberFmpBalance(Base):
    """Cached total FMP per user (FMR denominator uses global sum of these totals)."""

    __tablename__ = "member_fmp_balances"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    total_fmp: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
