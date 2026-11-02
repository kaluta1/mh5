"""Earnings a member did not receive because their KYC was not APPROVED at the earning event.

Owner rule (Shafi Abeid, 2026-11-02): only KYC-approved members earn commissions or advertising revenue
shares. For any other member the amount stays with MyHigh5 (no payable commission, no member liability)
and one row is kept here, for the member's dashboard and for audit. A row is never payable, is never
counted in any balance, and is kept after the member is verified (verification applies to future events
only). One row per (member, category, source event): retries never duplicate it.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

CATEGORY_REFERRAL = "REFERRAL_COMMISSION"
CATEGORY_AD_CREATIVE = "AD_CREATIVE_SHARE"
CATEGORY_AD_SPONSOR = "AD_SPONSOR_SHARE"
CATEGORIES = (CATEGORY_REFERRAL, CATEGORY_AD_CREATIVE, CATEGORY_AD_SPONSOR)
STATUS_RECORDED, STATUS_REVERSED = "RECORDED", "REVERSED"
RULE_VERSION = "KYC_ONLY_EARNINGS_V1"


class MissedEarning(Base):
    __tablename__ = "missed_earnings"
    __table_args__ = (
        UniqueConstraint("user_id", "category", "source_type", "source_id", name="uq_missed_earning_event"),
        CheckConstraint("category IN ('REFERRAL_COMMISSION', 'AD_CREATIVE_SHARE', 'AD_SPONSOR_SHARE')",
                        name="ck_missed_earning_category"),
        CheckConstraint("status IN ('RECORDED', 'REVERSED')", name="ck_missed_earning_status"),
        CheckConstraint("amount > 0", name="ck_missed_earning_amount"),
        Index("ix_missed_earnings_user_event", "user_id", "event_at"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_product: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)   # revenue category / ad product
    source_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # payer / creative (no PII)
    contestant_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    origin_kind: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    base_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    kyc_status: Mapped[str] = mapped_column(String(30), nullable=False)               # at the earning event
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(40), default=RULE_VERSION, nullable=False)
    revenue_account: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default=STATUS_RECORDED, nullable=False)
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reversal_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
