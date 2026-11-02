"""Internal wallet payments (Prompt 5, 2026-11-03): a member pays an approved platform product with
commission earnings already recorded in affiliate_commissions. Not a stored-value account and not a new
balance: the spendable amount is always computed from the commission rows themselves.

* internal_wallet_payments: one row per payment attempt that reached the server (COMPLETED / FAILED /
  REFUNDED). The purchase itself is the existing payment record (deposits, payment_provider
  'internal_wallet') so every product fulfilment, revenue and commission rule is reused unchanged.
* internal_wallet_payment_lines: how much of which commission row the payment used. A row used in full
  becomes PAID; a row used in part keeps its remainder for later wallet payments (see the service).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

PAYMENT_STATUSES = ("COMPLETED", "FAILED", "REFUNDED")


class InternalWalletPayment(Base):
    __tablename__ = "internal_wallet_payments"
    __table_args__ = (
        UniqueConstraint("reference", name="uq_iwp_reference"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_iwp_user_idempotency"),
        UniqueConstraint("deposit_id", name="uq_iwp_deposit"),
        CheckConstraint("status IN ('COMPLETED', 'FAILED', 'REFUNDED')", name="ck_iwp_status"),
        CheckConstraint("amount > 0", name="ck_iwp_amount"),
        CheckConstraint("quantity > 0", name="ck_iwp_quantity"),
        Index("ix_iwp_user_created", "user_id", "created_at"),
    )
    reference: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)   # NULL on a failed attempt
    product_code: Mapped[str] = mapped_column(String(50), nullable=False)
    product_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("product_types.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    deposit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("deposits.id"), nullable=True)
    settlement_journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"),
                                                                       nullable=True)
    balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refunded_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    refund_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    refund_journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"),
                                                                   nullable=True)


class InternalWalletPaymentLine(Base):
    __tablename__ = "internal_wallet_payment_lines"
    __table_args__ = (
        UniqueConstraint("payment_id", "commission_id", name="uq_iwp_line"),
        CheckConstraint("amount > 0", name="ck_iwp_line_amount"),
        CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="ck_iwp_line_status"),
        Index("ix_iwp_line_commission", "commission_id", "status"),
    )
    payment_id: Mapped[int] = mapped_column(Integer, ForeignKey("internal_wallet_payments.id"), nullable=False)
    commission_id: Mapped[int] = mapped_column(Integer, ForeignKey("affiliate_commissions.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ACTIVE")
