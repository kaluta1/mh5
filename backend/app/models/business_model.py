"""New MyHigh5 business model (NEW_V2): versioning, revenue policy, Referral Pool,
MyHigh5 Leaders and the marketplace/custody order state.

Statuses are plain strings (no PostgreSQL enum types) so that adding a state never
needs an ``ALTER TYPE`` in production.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
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
    """Audit record: organic user -> pool member. A user can be assigned at most once."""

    __tablename__ = "referral_pool_assignments"

    referred_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    pool_member_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    membership_id: Mapped[int] = mapped_column(Integer, ForeignKey("referral_pool_memberships.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    min_assignment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


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
