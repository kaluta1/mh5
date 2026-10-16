"""Financial controls: two-administrator confirmation of manually recorded
payments, and the payout review of historical commissions.

* ManualPaymentConfirmation: an administrator RECORDS that a member paid
  outside the payment provider; nothing is credited, posted or commissioned
  until a DIFFERENT authorised administrator CONFIRMS that the money was
  received (with an evidence reference). One row per deposit.
* CommissionPayoutReview: a historical (pre NEW_V2) commission is held from
  every payout path until an authorised administrator records an explicit
  decision for it: RELEASE (may be paid) or CANCEL (to be cancelled by the
  reconciliation procedure). One decision per commission, final.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

MANUAL_PAYMENT_STATUSES = ("REQUESTED", "CONFIRMED", "REJECTED", "CANCELLED")
REVIEW_DECISIONS = ("RELEASE", "CANCEL")


class ManualPaymentConfirmation(Base):
    __tablename__ = "manual_payment_confirmations"
    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED', 'CONFIRMED', 'REJECTED', 'CANCELLED')",
                        name="ck_manual_payment_confirmations_status"),
        # Whoever decides is never whoever recorded it (enforced again in the service).
        CheckConstraint("decided_by IS NULL OR decided_by <> requested_by",
                        name="ck_manual_payment_confirmations_two_people"),
        # At most one open request per member and product.
        Index("uq_manual_payment_open_per_member_product", "member_id", "product_code", unique=True,
              postgresql_where=text("status = 'REQUESTED'"), sqlite_where=text("status = 'REQUESTED'")),
    )

    deposit_id: Mapped[int] = mapped_column(Integer, ForeignKey("deposits.id"), nullable=False, unique=True)
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="REQUESTED", index=True)
    # Did the request create the deposit (True) or attach to an unfinished provider deposit (False)?
    created_new_deposit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verify_identity_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requested_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    request_reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    evidence_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class CommissionPayoutReview(Base):
    __tablename__ = "commission_payout_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('RELEASE', 'CANCEL')", name="ck_commission_payout_reviews_decision"),
    )

    commission_id: Mapped[int] = mapped_column(Integer, ForeignKey("affiliate_commissions.id"), nullable=False,
                                               unique=True)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # Set when the reconciliation procedure carried out a CANCEL decision.
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
