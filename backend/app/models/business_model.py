"""New MyHigh5 business model (NEW_V2): versioning, revenue policy, Referral Pool,
MyHigh5 Leaders and the marketplace/custody order state.

Statuses are plain strings (no PostgreSQL enum types) so that adding a state never
needs an ``ALTER TYPE`` in production.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class BusinessModelVersion(Base):
    """One row per business-model version. A row is immutable once activated."""

    __tablename__ = "business_model_versions"

    version: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RevenuePolicy(Base):
    """Explicit, auditable rule for how a product/category produces website revenue.

    website_revenue = gross - seller_base (marketplace) - provider cost
    direct commission = website_revenue * commission_rate   (if commission_eligible)
    """

    __tablename__ = "revenue_policies"
    __table_args__ = (UniqueConstraint("model_version", "product_code", name="uq_revenue_policy_version_product"),)

    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False)
    revenue_category: Mapped[str] = mapped_column(String(50), nullable=False)
    revenue_account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    # Set when revenue is earned later than cash is received (e.g. KYC on verification).
    deferred_account_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    provider_cost_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, default=0)
    provider_cost_fixed: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    provider_payable_account_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    commission_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, default=0)
    leaders_revenue_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class RevenueRecognition(Base):
    """Website-revenue subledger. One signed row per recognition or reversal.

    This is the single source for the direct-commission base and the Leaders revenue base.
    """

    __tablename__ = "revenue_recognitions"

    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False)
    revenue_category: Mapped[str] = mapped_column(String(50), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    seller_base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    provider_cost_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    website_revenue_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    commission_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    leaders_revenue_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recognized_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    reverses_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("revenue_recognitions.id"), nullable=True)


class ReferralPoolConfig(Base):
    __tablename__ = "referral_pool_config"

    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    price_product_code: Mapped[str] = mapped_column(String(50), nullable=False, default="referral_pool_entry")
    reservation_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    assignment_method: Mapped[str] = mapped_column(String(40), nullable=False, default="FAIR_RANDOM_V1")
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Multi-Unit pool (migration a7c9e1f3b5d2). Both switches stay off until the owner releases
    # the feature. A limit of NULL means unlimited (the default); `capacity` above belongs to the
    # retired seat model and does not bound units.
    multiunit_sales_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                          server_default=text("false"))
    allocation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                     server_default=text("false"))
    max_units_per_member: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_units_per_purchase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_active_units: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint("(max_units_per_member IS NULL OR max_units_per_member >= 1) "
                        "AND (max_units_per_purchase IS NULL OR max_units_per_purchase >= 1) "
                        "AND (max_active_units IS NULL OR max_active_units >= 1)",
                        name="ck_referral_pool_config_limits"),
    )


class ReferralPoolMembership(Base):
    """One pool seat. Seat-holding statuses: RESERVED (unexpired), ACTIVE, CAPACITY_REVIEW."""

    __tablename__ = "referral_pool_memberships"
    __table_args__ = (
        # Capacity is enforced by the database: a seat number (1..capacity) can be held once.
        Index("uq_referral_pool_seat", "seat_number", unique=True,
              postgresql_where=text("status IN ('RESERVED','ACTIVE','CAPACITY_REVIEW')"),
              sqlite_where=text("status IN ('RESERVED','ACTIVE','CAPACITY_REVIEW')")),
        Index("uq_referral_pool_one_open_seat_per_user", "user_id", unique=True,
              postgresql_where=text("status IN ('RESERVED','ACTIVE','CAPACITY_REVIEW')"),
              sqlite_where=text("status IN ('RESERVED','ACTIVE','CAPACITY_REVIEW')")),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    seat_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # PAID | LEGACY_FOUNDING_MIGRATION | ADMIN_ADJUSTMENT
    entitlement_source: Mapped[str] = mapped_column(String(40), nullable=False)
    # Evidence: the $100 deposit (new purchase or legacy Founding payment). Never a new charge.
    source_deposit_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("deposits.id"), nullable=True, unique=True
    )
    migration_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reserved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reservation_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    assignment_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    assignments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ReferralPoolAssignment(Base):
    """Audit record: organic user -> pool member. A user can be assigned at most once.

    Historical rows (retired seat model) carry membership_id; Multi-Unit rows carry
    round_id + slot_id + unit_id instead. A slot is filled by at most one assignment."""

    __tablename__ = "referral_pool_assignments"
    __table_args__ = (
        UniqueConstraint("slot_id", name="uq_referral_pool_assignment_slot"),
        CheckConstraint("(round_id IS NULL) = (slot_id IS NULL) AND (slot_id IS NULL) = (unit_id IS NULL)",
                        name="ck_referral_pool_assignment_round_refs"),
        CheckConstraint("(slot_id IS NULL AND membership_id IS NOT NULL AND min_assignment_count IS NOT NULL) "
                        "OR (slot_id IS NOT NULL AND membership_id IS NULL)",
                        name="ck_referral_pool_assignment_kind"),
        # NOT VALID in the migration: enforced for new rows; historical rows are not re-judged.
        CheckConstraint("referred_user_id <> pool_member_user_id", name="ck_referral_pool_assignment_not_self"),
        Index("ix_referral_pool_assignments_round", "round_id"),
    )

    referred_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    pool_member_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    membership_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("referral_pool_memberships.id"),
                                                         nullable=True)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    min_assignment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    round_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("referral_pool_rounds.id"), nullable=True)
    slot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("referral_pool_round_slots.id"), nullable=True)
    unit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("referral_pool_units.id"), nullable=True)


# ---------------------------------------------------------------- Multi-Unit Referral Pool (schema only)
# Migration a7c9e1f3b5d2. No service writes these tables yet: sales and allocation stay off
# (referral_pool_config switches) and the retired seat model keeps refusing every write.

class ReferralPoolPurchase(Base):
    """One pool deposit split into N units of unit_price. The deposit stays the payment record."""

    __tablename__ = "referral_pool_purchases"
    __table_args__ = (
        UniqueConstraint("deposit_id", name="uq_referral_pool_purchase_deposit"),
        CheckConstraint("quantity >= 1", name="ck_referral_pool_purchase_quantity"),
        CheckConstraint("unit_price > 0", name="ck_referral_pool_purchase_price"),
        CheckConstraint("total_amount = quantity * unit_price", name="ck_referral_pool_purchase_total"),
        CheckConstraint("refunded_quantity >= 0 AND refunded_quantity <= quantity",
                        name="ck_referral_pool_purchase_refunded"),
        CheckConstraint("status IN ('PENDING_PAYMENT','PAID','PARTIALLY_REFUNDED','REFUNDED','CANCELLED',"
                        "'HELD_FOR_REVIEW')", name="ck_referral_pool_purchase_status"),
        Index("ix_referral_pool_purchases_user_id", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    deposit_id: Mapped[int] = mapped_column(Integer, ForeignKey("deposits.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD", server_default=text("'USD'"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_PAYMENT",
                                        server_default=text("'PENDING_PAYMENT'"))
    refunded_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    units_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ReferralPoolUnit(Base):
    """One $100 participation unit. Never consumed by assignments; ends only by refund or revocation."""

    __tablename__ = "referral_pool_units"
    __table_args__ = (
        UniqueConstraint("purchase_id", "unit_index", name="uq_referral_pool_unit_purchase_index"),
        UniqueConstraint("legacy_membership_id", name="uq_referral_pool_unit_legacy_membership"),
        UniqueConstraint("revenue_recognition_id", name="uq_referral_pool_unit_recognition"),
        UniqueConstraint("direct_commission_id", name="uq_referral_pool_unit_commission"),
        CheckConstraint("(purchase_id IS NULL) = (unit_index IS NULL) AND (unit_index IS NULL OR unit_index >= 1)",
                        name="ck_referral_pool_unit_index"),
        CheckConstraint("source IN ('PAID','HISTORICAL_CONVERSION','ADMIN_GRANT')", name="ck_referral_pool_unit_source"),
        CheckConstraint("source <> 'PAID' OR purchase_id IS NOT NULL", name="ck_referral_pool_unit_paid_has_purchase"),
        CheckConstraint("source <> 'HISTORICAL_CONVERSION' OR legacy_membership_id IS NOT NULL",
                        name="ck_referral_pool_unit_historical_has_membership"),
        CheckConstraint("status IN ('PENDING','ACTIVE','SUSPENDED','REFUNDED','REVOKED')",
                        name="ck_referral_pool_unit_status"),
        CheckConstraint("amount >= 0", name="ck_referral_pool_unit_amount"),
        CheckConstraint("status <> 'ACTIVE' OR activated_at IS NOT NULL", name="ck_referral_pool_unit_active_dated"),
        CheckConstraint("status <> 'REFUNDED' OR refunded_at IS NOT NULL", name="ck_referral_pool_unit_refund_dated"),
        Index("ix_referral_pool_units_user_status", "user_id", "status"),
        Index("ix_referral_pool_units_active", "id", postgresql_where=text("status = 'ACTIVE'"),
              sqlite_where=text("status = 'ACTIVE'")),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    purchase_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("referral_pool_purchases.id"), nullable=True)
    unit_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # PAID | HISTORICAL_CONVERSION | ADMIN_GRANT
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    # PENDING | ACTIVE | SUSPENDED (eligibility lost, may return) | REFUNDED | REVOKED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default=text("'PENDING'"))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD", server_default=text("'USD'"))
    legacy_membership_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("referral_pool_memberships.id"),
                                                                nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refund_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    refund_journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"),
                                                                   nullable=True)
    revenue_recognition_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("revenue_recognitions.id"),
                                                                  nullable=True)
    direct_commission_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("affiliate_commissions.id"),
                                                                nullable=True)


class ReferralPoolRound(Base):
    """A quota round: one slot per eligible unit at opening. At most one round is OPEN."""

    __tablename__ = "referral_pool_rounds"
    __table_args__ = (
        UniqueConstraint("round_number", name="uq_referral_pool_round_number"),
        CheckConstraint("round_number >= 1", name="ck_referral_pool_round_number"),
        CheckConstraint("status IN ('OPEN','COMPLETED','CLOSED')", name="ck_referral_pool_round_status"),
        CheckConstraint("total_slots >= 1 AND filled_slots >= 0 AND void_slots >= 0 "
                        "AND filled_slots + void_slots <= total_slots", name="ck_referral_pool_round_counts"),
        CheckConstraint("status <> 'COMPLETED' OR filled_slots + void_slots = total_slots",
                        name="ck_referral_pool_round_completed"),
        CheckConstraint("(status = 'OPEN') = (completed_at IS NULL)", name="ck_referral_pool_round_ended"),
        Index("uq_referral_pool_one_open_round", "status", unique=True,
              postgresql_where=text("status = 'OPEN'"), sqlite_where=text("status = 'OPEN'")),
    )

    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default=text("'OPEN'"))
    method: Mapped[str] = mapped_column(String(40), nullable=False, default="QUOTA_ROUND_V1",
                                        server_default=text("'QUOTA_ROUND_V1'"))
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_slots: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    void_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ReferralPoolRoundSlot(Base):
    """One unit's quota in one round: OPEN until a referral fills it, VOID if the unit leaves."""

    __tablename__ = "referral_pool_round_slots"
    __table_args__ = (
        UniqueConstraint("round_id", "unit_id", name="uq_referral_pool_slot_round_unit"),
        CheckConstraint("status IN ('OPEN','FILLED','VOID')", name="ck_referral_pool_slot_status"),
        CheckConstraint("(status = 'FILLED') = (filled_at IS NOT NULL)", name="ck_referral_pool_slot_filled_dated"),
        CheckConstraint("(status = 'VOID') = (voided_at IS NOT NULL)", name="ck_referral_pool_slot_void_dated"),
        Index("ix_referral_pool_slots_round_status", "round_id", "status"),
        Index("ix_referral_pool_slots_unit", "unit_id"),
        Index("ix_referral_pool_slots_member", "member_user_id"),
    )

    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("referral_pool_rounds.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(Integer, ForeignKey("referral_pool_units.id"), nullable=False)
    member_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default=text("'OPEN'"))
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)


class ReferralPoolEvent(Base):
    """Durable outbox (migration c1e3a5b7d9f2): written inside a KYC decision's transaction,
    processed afterwards by the pool worker in its own transaction. One row per decision."""

    __tablename__ = "referral_pool_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_referral_pool_event_dedupe"),
        CheckConstraint("event_type IN ('KYC_APPROVED','KYC_REJECTED','ACCOUNT_CHANGED','RISK_CLEARED')",
                        name="ck_referral_pool_event_type"),
        CheckConstraint("status IN ('PENDING','DONE','FAILED')", name="ck_referral_pool_event_status"),
        CheckConstraint("attempts >= 0", name="ck_referral_pool_event_attempts"),
        CheckConstraint("(status = 'PENDING') = (processed_at IS NULL)", name="ck_referral_pool_event_processed"),
        Index("ix_referral_pool_events_pending", "id", postgresql_where=text("status = 'PENDING'"),
              sqlite_where=text("status = 'PENDING'")),
        Index("ix_referral_pool_events_user", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    kyc_verification_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kyc_verifications.id"),
                                                               nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default=text("'PENDING'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_error: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ReferralPoolRiskReview(Base):
    """An anti-abuse signal for manual review. Evidence is a SHA-256 of the normalized signal;
    only a duplicate verified identity may block (enforced by the database)."""

    __tablename__ = "referral_pool_risk_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "signal", "evidence_hash", name="uq_referral_pool_risk_review"),
        CheckConstraint("signal IN ('DUPLICATE_KYC_IDENTITY','SHARED_PAYOUT_WALLET','SHARED_LOGIN_IP')",
                        name="ck_referral_pool_risk_signal"),
        CheckConstraint("status IN ('OPEN','CLEARED','CONFIRMED')", name="ck_referral_pool_risk_status"),
        CheckConstraint("(status = 'OPEN') = (decided_at IS NULL)", name="ck_referral_pool_risk_decided"),
        CheckConstraint("NOT blocking OR signal = 'DUPLICATE_KYC_IDENTITY'", name="ck_referral_pool_risk_blocking"),
        Index("ix_referral_pool_risk_blocking", "user_id",
              postgresql_where=text("blocking AND status IN ('OPEN','CONFIRMED')"),
              sqlite_where=text("blocking AND status IN ('OPEN','CONFIRMED')")),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    signal: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    related_user_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default=text("'OPEN'"))
    decided_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class ReferralPoolRefundRecord(Base):
    """A manual (not provider-verified) refund (migration d2f4b6c8e0a1): proposed by one finance
    administrator, approved by a different one; executed only on approval."""

    __tablename__ = "referral_pool_refund_records"
    __table_args__ = (
        UniqueConstraint("provider_reference", name="uq_referral_pool_refund_reference"),
        CheckConstraint("quantity >= 1", name="ck_referral_pool_refund_quantity"),
        CheckConstraint("amount > 0", name="ck_referral_pool_refund_amount"),
        CheckConstraint("status IN ('PROPOSED','APPROVED','REJECTED')", name="ck_referral_pool_refund_status"),
        CheckConstraint("(status = 'PROPOSED') = (decided_at IS NULL)", name="ck_referral_pool_refund_decided"),
        CheckConstraint("decided_by IS NULL OR decided_by <> proposed_by", name="ck_referral_pool_refund_four_eyes"),
        Index("ix_referral_pool_refund_records_purchase", "purchase_id"),
    )

    purchase_id: Mapped[int] = mapped_column(Integer, ForeignKey("referral_pool_purchases.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    evidence_note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROPOSED", server_default=text("'PROPOSED'"))
    proposed_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    decided_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    executed_unit_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ReferralPoolPending(Base):
    """A KYC-approved referral without a valid personal inviter, waiting for a slot. One row per user."""

    __tablename__ = "referral_pool_pending"
    __table_args__ = (
        UniqueConstraint("referred_user_id", name="uq_referral_pool_pending_user"),
        UniqueConstraint("assignment_id", name="uq_referral_pool_pending_assignment"),
        CheckConstraint("status IN ('WAITING','ASSIGNED','CANCELLED')", name="ck_referral_pool_pending_status"),
        CheckConstraint("trigger_event IN ('KYC_APPROVED')", name="ck_referral_pool_pending_trigger"),
        CheckConstraint("attempts >= 0", name="ck_referral_pool_pending_attempts"),
        CheckConstraint("(status = 'ASSIGNED') = (assignment_id IS NOT NULL)", name="ck_referral_pool_pending_assigned"),
        CheckConstraint("(status = 'WAITING') = (resolved_at IS NULL)", name="ck_referral_pool_pending_resolved"),
        Index("ix_referral_pool_pending_waiting", "enqueued_at", "id",
              postgresql_where=text("status = 'WAITING'"), sqlite_where=text("status = 'WAITING'")),
    )

    referred_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="WAITING", server_default=text("'WAITING'"))
    trigger_event: Mapped[str] = mapped_column(String(30), nullable=False, default="KYC_APPROVED",
                                               server_default=text("'KYC_APPROVED'"))
    kyc_verification_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kyc_verifications.id"),
                                                               nullable=True)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_reason: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    assignment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("referral_pool_assignments.id"),
                                                         nullable=True)


class ReferralPoolMigrationRun(Base):
    """Legacy Founding -> Referral Pool migration execution record (hash-locked manifest)."""

    __tablename__ = "referral_pool_migration_runs"

    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    automatic_eligible: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manual_review: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_eligible: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)


class LeadersPeriod(Base):
    """MyHigh5 Leaders month: DRAFT -> APPROVED -> POSTED (-> REVERSED). SUPERSEDED drafts are kept."""

    __tablename__ = "leaders_periods"
    __table_args__ = (
        Index("uq_leaders_one_live_period", "period_year", "period_month", unique=True,
              postgresql_where=text("status IN ('DRAFT','APPROVED','POSTED')"),
              sqlite_where=text("status IN ('DRAFT','APPROVED','POSTED')")),
    )

    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    revenue_definition: Mapped[str] = mapped_column(String(60), nullable=False)
    eligible_company_revenue: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    pool_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    pool_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    max_members: Mapped[int] = mapped_column(Integer, nullable=False)
    qualifying_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_qualifying_commission: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prepared_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    reversal_journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class LeadersAllocationLine(Base):
    __tablename__ = "leaders_allocation_lines"
    __table_args__ = (UniqueConstraint("period_id", "user_id", name="uq_leaders_line_period_user"),)

    period_id: Mapped[int] = mapped_column(Integer, ForeignKey("leaders_periods.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    direct_commission_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    ratio: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    payout_status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNPAID")


class MarketOrder(Base):
    """Marketplace order where MyHigh5 acts as agent; buyer funds are held by an EXTERNAL custodian.

    buyer_total = seller_base_amount + markup_amount; markup is MyHigh5 website revenue.
    """

    __tablename__ = "market_orders"

    buyer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    seller_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    seller_base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    markup_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    markup_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    buyer_total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    custodian_provider: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    custodian_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, unique=True)
    business_model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    funded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fulfilled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    markup_settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Buyer acceptance (server-recorded, buyer only): its unique reference and the policy text version
    # the buyer acknowledged. confirmed_at is the acceptance time.
    acceptance_reference: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, unique=True)
    acceptance_policy_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # The seller checked the acceptance on their dashboard before handing over.
    seller_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Settlement initiation, separate from acceptance: asked of the custodian when, and the last failure
    # (cleared on a successful request). A failure never undoes the acceptance.
    release_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    release_request_error: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # Why support refunded the order (non-handover, duplicate charge, fraud, ...).
    support_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class MarketOrderEvent(Base):
    """Append-only audit trail of order state changes and custodian confirmations."""

    __tablename__ = "market_order_events"

    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("market_orders.id"), nullable=False, index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Custodian event id makes provider confirmations idempotent.
    external_event_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, unique=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class MarketDispute(Base):
    __tablename__ = "market_disputes"

    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("market_orders.id"), nullable=False, index=True)
    opened_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # OPEN | RESOLVED_RELEASE | RESOLVED_REFUND
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AffiliateRateQualification(Base):
    """Permanent qualified direct-affiliate rate (client rule confirmed 2026-09-28).

    Written once, at the moment the rule was first met; the application never updates or
    deletes it, so a later change to the referrals (KYC revoked, account closed, sponsor
    edited) cannot take back a rate that was legitimately earned. The derivation that
    produced it is kept alongside for audit.
    """

    __tablename__ = "affiliate_rate_qualifications"
    __table_args__ = (UniqueConstraint("user_id", name="uq_affiliate_rate_qualification_user"),)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    qualified_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    qualified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    qualifying_referral_count: Mapped[int] = mapped_column(Integer, nullable=False)
    required_referral_count: Mapped[int] = mapped_column(Integer, nullable=False)
