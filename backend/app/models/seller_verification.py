"""Marketplace seller registration and verification (separate from member KYC).

MyHigh5 seller approval is permission to sell on MyHigh5 only. It is never government business
registration, tax registration, incorporation or a product licence, and never proof of full legal
compliance.

Statuses are plain strings (no PostgreSQL enum types) so that adding a state never needs an
``ALTER TYPE`` in production. Private compliance evidence (addresses, tax identifiers, documents)
lives only in these tables and in encrypted private storage; it never appears on a public profile.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

APPLICATION_STATUSES = ("DRAFT", "SUBMITTED", "CHECKS_IN_PROGRESS", "ACTION_REQUIRED", "MANUAL_REVIEW_REQUIRED",
                        "APPROVED", "REJECTED", "RESTRICTED", "REVERIFICATION_REQUIRED", "SUPERSEDED")
_STATUS_SQL = ", ".join(f"'{s}'" for s in APPLICATION_STATUSES)


class SellerJurisdictionRule(Base):
    """A versioned requirement for a jurisdiction. LEGAL rules describe a government requirement and are
    activated only after review against their official source; PLATFORM rules are MyHigh5 policy."""

    __tablename__ = "seller_jurisdiction_rules"
    __table_args__ = (
        CheckConstraint("rule_kind IN ('LEGAL', 'PLATFORM')", name="ck_seller_rule_kind"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_seller_rule_status"),
        UniqueConstraint("rule_code", "version", name="uq_seller_rule_code_version"),
    )

    rule_code: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # ISO country code, "EU", or "*" for every jurisdiction (platform policy).
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    subdivision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # BUSINESS_REGISTRATION | REGISTRATION_EXEMPTION | TAX | LICENCE | TRADER_TRACEABILITY | PLATFORM_TAX_REPORTING
    # | PLATFORM_POLICY
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    rule_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    # Which sellers it applies to (lists; empty = all).
    seller_categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    business_structures: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    product_categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Applies where the seller's customers are (US INFORM, EU traceability), not where the seller lives.
    applies_by_customer_market: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # What the seller must provide or what is checked (e.g. REGISTRATION_NUMBER, EXEMPTION_BASIS).
    requirement: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    official_source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_reviewed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="DRAFT")
    activated_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SellerProfile(Base):
    """One per member: their current seller standing and public label (the only public part)."""

    __tablename__ = "seller_profiles"
    __table_args__ = (
        CheckConstraint(f"status IN ('NONE', {_STATUS_SQL})", name="ck_seller_profile_status"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    # PRIVATE | SOLE_TRADER | ORGANISATION (NULL until a first application)
    seller_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NONE")
    public_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    public_trading_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    approved_application_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    restricted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # A seller asked to reverify may keep selling until this time (NULL = must reverify before selling).
    reverify_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Hash of the payout destination at approval: a change triggers reverification (never the address).
    beneficiary_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class SellerApplication(Base):
    """A seller application (draft, submitted, decided). A change after approval is a NEW application."""

    __tablename__ = "seller_applications"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_seller_application_status"),
        CheckConstraint("seller_category IN ('PRIVATE', 'SOLE_TRADER', 'ORGANISATION')", name="ck_seller_application_category"),
        Index("ix_seller_applications_user_status", "user_id", "status"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT")
    seller_category: Mapped[str] = mapped_column(String(20), nullable=False)
    # SOLE_TRADER: REGISTERED | EXEMPT. ORGANISATION: COMPANY | PARTNERSHIP | LLP | ORGANISATION | OTHER.
    business_structure: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    legal_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    trading_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    residence_country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    establishment_country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    establishment_subdivision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    customer_markets: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Private: never on a public profile, never logged.
    business_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    product_categories: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    products_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Private seller: answers that may indicate commercial activity.
    commercial_indicators: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    registration_authority: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    registration_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    exemption_basis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tax_registered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # Tax identifier: encrypted; only the last four characters are kept readable.
    tax_identifier_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tax_identifier_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    licences: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    representative: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ownership: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    declaration_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    declaration_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Evaluation results (rule codes that applied, reasons a person must look at).
    applicable_rules: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    review_reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # What the seller must correct (shown to them; never fraud indicators).
    correction_request: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    appeal_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supersedes_application_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class SellerApplicationEvent(Base):
    """Append-only history of an application (status changes, corrections, decisions)."""

    __tablename__ = "seller_application_events"

    application_id: Mapped[int] = mapped_column(Integer, ForeignKey("seller_applications.id"), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    # Internal reason (admin only) and the message the seller sees.
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seller_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class SellerVerificationCheck(Base):
    """One automated check of an application. PASSED is recorded only from verified evidence."""

    __tablename__ = "seller_verification_checks"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'PASSED', 'FAILED', 'UNAVAILABLE', 'MANUAL')", name="ck_seller_check_status"),
        UniqueConstraint("application_id", "check_type", name="uq_seller_check_application_type"),
    )

    application_id: Mapped[int] = mapped_column(Integer, ForeignKey("seller_applications.id"), nullable=False, index=True)
    # IDENTITY | BUSINESS_REGISTRY | REPRESENTATIVE | LICENCE | PAYOUT_BENEFICIARY
    check_type: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="PENDING")
    external_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Non-sensitive outcome (codes, matched/not matched); never document data.
    result_code: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SellerProviderEvent(Base):
    """A verified provider callback, recorded once (idempotency by provider + event id)."""

    __tablename__ = "seller_provider_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_seller_provider_event"),)

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    check_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("seller_verification_checks.id"), nullable=True)
    outcome: Mapped[str] = mapped_column(String(15), nullable=False)


class SellerDocument(Base):
    """An encrypted compliance document in private storage (never a public URL)."""

    __tablename__ = "seller_documents"

    application_id: Mapped[int] = mapped_column(Integer, ForeignKey("seller_applications.id"), nullable=False, index=True)
    # REGISTRATION_CERTIFICATE | EXEMPTION_EVIDENCE | LICENCE | AUTHORITY_LETTER | OWNERSHIP | ADDRESS | OTHER
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # Retention: when the file was erased (the row stays as a record that it existed).
    erased_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SellerClassificationReview(Base):
    """A private seller crossed an internal review trigger or showed commercial activity. Idempotent per
    seller, trigger and window bucket. Opening one never restricts selling by itself."""

    __tablename__ = "seller_classification_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_seller_classification_status"),
        UniqueConstraint("idempotency_key", name="uq_seller_classification_key"),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # SALES_AMOUNT | ORDER_COUNT | COMMERCIAL_INDICATOR
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Seller's gross item sales (seller base, excluding MyHigh5 markup), in USD.
    qualifying_sales_usd: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    qualifying_order_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fx_rates_used: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="OPEN")
    resolution: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SellerFxRate(Base):
    """USD value of one unit of a currency, as recorded for sales monitoring."""

    __tablename__ = "seller_fx_rates"
    __table_args__ = (UniqueConstraint("currency", "as_of", name="uq_seller_fx_currency_date"),)

    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    usd_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
