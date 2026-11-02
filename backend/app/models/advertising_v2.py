"""MyHigh5 advertising: controlled placements, CPM campaigns, advertiser credit and contest-entry
ad revenue sharing (2026-11-01).

Separate from the legacy, never-mounted ``ad_*`` tables in ``advertising.py`` (kept untouched; they
encode an unapproved 40/10/1x10 sharing design). Every table here is ``adv_``-prefixed.

Products are kept apart everywhere: ORDINARY (MyHigh5 campaigns), ADSENSE (Google) and ANNUAL_ADS
(Annual Ads platform). Only ORDINARY and ADSENSE revenue earned on an individual contest-entry page
can ever enter contest-entry revenue sharing; ANNUAL_ADS never does.

Money: Numeric with fixed scale; per-impression amounts keep 6-8 decimals, payable lines 2.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

PRODUCTS = ("ORDINARY", "ADSENSE", "ANNUAL_ADS")
SOURCES = ("MYHIGH5", "ADSENSE")


class AdvSettings(Base):
    """One row. NULL prices = pending business approval: no campaign can be funded or served."""
    __tablename__ = "adv_settings"
    cpm_rate_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    min_campaign_budget_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    min_daily_cap_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    campaigns_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    funding_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    adsense_fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adsense_sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contest_sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reservation_ttl_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    frequency_cap_per_day: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    max_viewable_per_viewer_hour: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)


class AdvCreditMovement(Base):
    """Advertiser credit sub-ledger of liability 2320 (one row per movement, never updated)."""
    __tablename__ = "adv_credit_movements"
    __table_args__ = (
        CheckConstraint("movement_type IN ('DEPOSIT', 'ALLOCATE', 'RELEASE', 'REFUND', 'DEPOSIT_REVERSAL')",
                        name="ck_adv_credit_type"),
        UniqueConstraint("idempotency_key", name="uq_adv_credit_idem"),
        Index("ix_adv_credit_advertiser", "advertiser_user_id"),
    )
    advertiser_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Signed effect on the advertiser's UNALLOCATED credit (+ deposit/release, - allocate/refund/reversal).
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    campaign_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("adv_campaigns.id"), nullable=True)
    deposit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("deposits.id"), nullable=True)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)


class AdvCampaign(Base):
    __tablename__ = "adv_campaigns"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'PAUSED', 'COMPLETED', 'REJECTED', "
                        "'CHANGES_REQUESTED', 'CANCELLED')", name="ck_adv_campaign_status"),
        CheckConstraint("pricing_model = 'CPM'", name="ck_adv_campaign_pricing"),
        CheckConstraint("spent >= 0 AND reserved >= 0 AND spent + reserved <= budget_total",
                        name="ck_adv_campaign_budget"),
        Index("ix_adv_campaign_status", "status"),
    )
    advertiser_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    pricing_model: Mapped[str] = mapped_column(String(10), default="CPM", nullable=False)
    # Price fixed when the campaign is submitted (from adv_settings); later price changes never reprice it.
    cpm_rate_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    budget_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    spent: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    daily_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    start_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # {"countries": ["KE"], "page_types": ["CONTEST_ENTRY", ...]}; empty = everywhere eligible.
    targeting: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    placements: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # slot kinds: SIDEBAR, IN_FEED, IN_CONTENT
    review_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completion_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AdvCampaignDay(Base):
    """Daily cap enforcement (UTC day)."""
    __tablename__ = "adv_campaign_days"
    __table_args__ = (UniqueConstraint("campaign_id", "day", name="uq_adv_campaign_day"),
                      CheckConstraint("spent >= 0 AND reserved >= 0", name="ck_adv_campaign_day_amounts"))
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("adv_campaigns.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    spent: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    recognized_journal_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    recognized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)   # day closed


class AdvCreative(Base):
    __tablename__ = "adv_creatives"
    __table_args__ = (
        CheckConstraint("review_status IN ('PENDING', 'APPROVED', 'REJECTED')", name="ck_adv_creative_review"),
    )
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("adv_campaigns.id"), nullable=False)
    headline: Mapped[str] = mapped_column(String(90), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    destination_url: Mapped[str] = mapped_column(String(500), nullable=False)
    review_status: Mapped[str] = mapped_column(String(10), default="PENDING", nullable=False)
    review_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Uploaded image (Prompt 4): validated content type, size and pixel dimensions; NULL for an image URL.
    image_mime: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    image_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class AdvEntryOrigin(Base):
    """Immutable original submission type of a contest entry, decided once from verified evidence.
    RESOLVED rows are never changed; REVIEW rows hold every allocation until an admin resolves them."""
    __tablename__ = "adv_entry_origins"
    __table_args__ = (
        UniqueConstraint("contestant_id", name="uq_adv_entry_origin"),
        CheckConstraint("status IN ('RESOLVED', 'REVIEW')", name="ck_adv_origin_status"),
        CheckConstraint("origin_kind IS NULL OR origin_kind IN ('PERSONAL_SUBMISSION', 'NOMINATION')",
                        name="ck_adv_origin_kind"),
    )
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    origin_kind: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AdvServeDecision(Base):
    """One per slot fill. A MyHigh5 decision holds the reservation of exactly one impression."""
    __tablename__ = "adv_serve_decisions"
    __table_args__ = (
        CheckConstraint("source IN ('MYHIGH5', 'ADSENSE')", name="ck_adv_decision_source"),
        CheckConstraint("product IN ('ORDINARY', 'ADSENSE')", name="ck_adv_decision_product"),
        CheckConstraint("state IN ('RESERVED', 'CHARGED', 'RELEASED', 'UNPAID')", name="ck_adv_decision_state"),
        Index("ix_adv_decision_expiry", "state", "expires_at"),
        Index("ix_adv_decision_created", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # type: ignore[assignment]
    slot_kind: Mapped[str] = mapped_column(String(12), nullable=False)       # SIDEBAR | IN_FEED | IN_CONTENT
    page_type: Mapped[str] = mapped_column(String(24), nullable=False)
    slot_key: Mapped[str] = mapped_column(String(80), nullable=False)        # e.g. contests:in_feed:2
    contestant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    product: Mapped[str] = mapped_column(String(10), nullable=False)
    campaign_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("adv_campaigns.id"), nullable=True)
    creative_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("adv_creatives.id"), nullable=True)
    adsense_slot: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    reserved_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    state: Mapped[str] = mapped_column(String(10), nullable=False)
    viewer_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AdvImpressionEvent(Base):
    """Raw beacon (SERVED / VIEWABLE) plus, once validated, the attribution snapshot of the earning event.
    The snapshot (entry, original type, creative, level, sponsor, rule version) is never rewritten."""
    __tablename__ = "adv_impression_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_adv_event_id"),
        UniqueConstraint("decision_id", "event_type", name="uq_adv_event_decision_type"),
        CheckConstraint("event_type IN ('SERVED', 'VIEWABLE')", name="ck_adv_event_type"),
        CheckConstraint("validation_status IN ('PENDING', 'VALID', 'INVALID')", name="ck_adv_event_validation"),
        Index("ix_adv_event_pending", "validation_status", "received_at"),
        Index("ix_adv_event_day", "earning_day", "source"),
        Index("ix_adv_event_contestant", "contestant_id", "earning_day"),
    )
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(36), ForeignKey("adv_serve_decisions.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(10), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    visible_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visible_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3), nullable=True)
    page_visible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ua_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    viewer_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_bot_ua: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(10), default="PENDING", nullable=False)
    invalid_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # ---- attribution snapshot (VIEWABLE + VALID only)
    earning_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)            # UTC
    source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    product: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    adsense_slot: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    charged_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    contestant_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    origin_kind: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    creative_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sponsor_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sponsor_status: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)   # VALID|NONE|INELIGIBLE|UNRESOLVED
    contest_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    season_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rule_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # KYC of the creative / sponsor AT the earning event (owner rule 2026-11-02: only APPROVED earns).
    # None = no identifiable member at the event, or an event recorded before the rule.
    creative_kyc_approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    sponsor_kyc_approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # Invalid activity found after charging: credited back once.
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reversal_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class AdvAdsenseImport(Base):
    __tablename__ = "adv_adsense_imports"
    status: Mapped[str] = mapped_column(String(20), nullable=False)      # OK | NO_CREDENTIALS | ERROR
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)


class AdvAdsenseBucket(Base):
    """Google publisher earnings (after Google's share) for one reporting bucket: day x ad unit x currency."""
    __tablename__ = "adv_adsense_buckets"
    __table_args__ = (
        UniqueConstraint("day", "ad_unit", "currency", name="uq_adv_adsense_bucket"),
        CheckConstraint("status IN ('ESTIMATED', 'FINALIZED')", name="ck_adv_adsense_status"),
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    ad_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    estimated_earnings: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    finalized_earnings: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    google_impressions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="ESTIMATED", nullable=False)
    import_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("adv_adsense_imports.id"), nullable=True)
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AdvAdsenseMonth(Base):
    """Finalized Google earnings for a month (the reconciliation anchor), entered from the AdSense
    Payments report or imported. Revenue is booked once per month: Dr 1240 / Cr 4021."""
    __tablename__ = "adv_adsense_months"
    __table_args__ = (UniqueConstraint("period", "currency", name="uq_adv_adsense_month"),)
    period: Mapped[str] = mapped_column(String(7), nullable=False)          # YYYY-MM
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    finalized_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    estimated_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0, nullable=False)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    recorded_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    evidence_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class AdvAllocation(Base):
    """Monthly contest-entry revenue share line (one beneficiary role per entry, period, source, level).

    status: ESTIMATED (daily view, never payable) -> RELEASED (commission row created, wallet rules apply)
            or HELD_UNCLAIMED (nominee has no linked account) / HELD_SPONSOR (sponsor eligibility unresolved)
            / HELD_REVIEW (original type not provable) -> RELEASED when resolved; REVERSED (auditable)."""
    __tablename__ = "adv_allocations"
    __table_args__ = (
        UniqueConstraint("period", "contestant_id", "role", "source", "season_key", "beneficiary_key", "version",
                         name="uq_adv_allocation_line"),
        CheckConstraint("role IN ('CREATIVE', 'SPONSOR')", name="ck_adv_alloc_role"),
        CheckConstraint("status IN ('ESTIMATED', 'HELD_UNCLAIMED', 'HELD_SPONSOR', 'HELD_REVIEW', 'RELEASED', "
                        "'REVERSED', 'SUPERSEDED', 'MISSED_KYC')", name="ck_adv_alloc_status"),
        CheckConstraint("amount >= 0 AND amount <= base_amount", name="ck_adv_alloc_amount"),
        CheckConstraint("rate >= 0 AND rate <= 0.20", name="ck_adv_alloc_rate"),
        Index("ix_adv_alloc_beneficiary", "beneficiary_user_id", "status"),
        Index("ix_adv_alloc_period", "period", "status"),
    )
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    product: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_kind: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contest_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    season_key: Mapped[int] = mapped_column(Integer, default=0, nullable=False)       # season id, 0 = none
    beneficiary_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    beneficiary_key: Mapped[int] = mapped_column(Integer, default=0, nullable=False)   # user id, 0 = none yet
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    valid_impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    commission_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("affiliate_commissions.id"), nullable=True)
    hold_journal_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)


class AdvAnnualAdsPayment(Base):
    """Audit record of every Annual Ads payment webhook (the journal stays the authoritative posting).
    Buyer identity only from a signed field matching the SSO subject we issued; entitlement fields are
    copied verbatim from the Annual Ads payload (they belong to the Annual Ads platform)."""
    __tablename__ = "adv_annualads_payments"
    __table_args__ = (
        UniqueConstraint("tx_hash", name="uq_adv_annualads_tx"),
        CheckConstraint("buyer_match IN ('MATCHED', 'UNMATCHED', 'ABSENT')", name="ck_adv_annualads_buyer"),
    )
    tx_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    buyer_reference: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    buyer_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    buyer_match: Mapped[str] = mapped_column(String(10), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    entitlement_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    journal_entry_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    # The Type 1 sponsor commission base (gross vs net) is not approved: never posted automatically.
    sponsor_commission_status: Mapped[str] = mapped_column(String(20), default="PENDING_POLICY", nullable=False)
    raw_payload_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Prompt 6 (2026-11-03): the buyer's direct-sponsor commission (20% / qualified 40% of GROSS), decided once.
    sponsor_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sponsor_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    sponsor_rule_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    sponsor_commission_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sponsor_commission_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    sponsor_decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sponsor_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Refund / cancellation reported by a signed Annual Ads event.
    refund_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    refund_event: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    refund_payload_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class AdvAnnualAdsEvent(Base):
    """One processed signed Annual Ads webhook delivery (idempotency and outcome)."""
    __tablename__ = "adv_annualads_events"
    __table_args__ = (UniqueConstraint("event", "tx_hash", "payload_sha256", name="uq_adv_annualads_event"),
                      Index("ix_adv_annualads_events_tx", "tx_hash"))
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("adv_annualads_payments.id"), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
