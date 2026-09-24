"""Reference data for the NEW_V2 business model (accounts, revenue policies, pool config).

Shared by the Alembic migration (production seed) and the test fixtures so the two can
never drift. Every value here is a business policy; changing one in production is done by
updating the row (audited), not by editing code.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

NEW_MODEL_VERSION = "NEW_V2"
LEGACY_MODEL_VERSION = "LEGACY_V1"

REFERRAL_POOL_PRODUCT_CODE = "referral_pool_entry"
REFERRAL_POOL_PRICE = Decimal("100.00")
REFERRAL_POOL_CAPACITY = 10000
MARKETPLACE_PRODUCT_CODE = "marketplace_markup"
MARKETPLACE_MARKUP_RATE = Decimal("0.20")
LEADERS_POOL_RATE = Decimal("0.05")
LEADERS_MAX_MEMBERS = 10000

REFERRAL_POOL_POLICY_NOTES = (
    "CONFIRMED 2026-09-25: a paid $100 pool entry is website revenue, pays the DIRECT sponsor 20% ($20) "
    "and is included in the Leaders revenue base. Legacy Founding entitlements create no payment, "
    "revenue or commission."
)

# (code, name, type, parent code)
NEW_MODEL_ACCOUNTS = [
    ("1220", "Receivable from external custodian (marketplace buyer funds held; not MyHigh5 cash)", "ASSET", "1000"),
    ("2106", "MyHigh5 Leaders rewards payable", "LIABILITY", "2000"),
    ("2114", "Deferred revenue - marketplace markup (order not yet released)", "LIABILITY", "2000"),
    ("2121", "Seller payable - held by external custodian", "LIABILITY", "2000"),
    ("4007", "Marketplace markup revenue (website revenue)", "REVENUE", "4000"),
    ("4008", "Referral Pool entry revenue", "REVENUE", "4000"),
    ("4009", "Other platform service revenue", "REVENUE", "4000"),
    ("5004", "MyHigh5 Leaders program expense", "EXPENSE", "5000"),
]

# Policy values confirmed by the client (Shafi Abeid, 2026-09-25). The direct commission base is
# always gross - seller base (see new_model_revenue.COMMISSION_BASE_DEFINITION); provider cost only
# reduces booked website revenue, never the commission base.
_KYC = dict(
    revenue_category="KYC_VERIFICATION",
    revenue_account_code="4001",
    deferred_account_code="2113",
    provider_cost_rate=Decimal("0.20"),
    provider_cost_fixed=Decimal("0"),
    provider_payable_account_code="2003",
    commission_eligible=True,
    commission_rate=Decimal("0.20"),
    leaders_revenue_eligible=True,
    notes=("CONFIRMED 2026-09-25: direct commission = 20% of the FULL KYC fee ($10 -> $2). The 20% provider cost "
           "is a separate pass-through (2003) and does not reduce the commission base. Recognized when verification is performed."),
)
_PLATFORM = dict(
    deferred_account_code=None,
    provider_cost_rate=Decimal("0"),
    provider_cost_fixed=Decimal("0"),
    provider_payable_account_code=None,
    commission_eligible=True,
    commission_rate=Decimal("0.20"),
    leaders_revenue_eligible=True,
)

NEW_MODEL_REVENUE_POLICIES = {
    "kyc": _KYC,
    "kyc_verification": _KYC,
    "annual_membership": dict(_PLATFORM, revenue_category="MEMBERSHIP", revenue_account_code="4002",
                              notes="Website revenue = gross (no pass-through)."),
    "efm_membership": dict(_PLATFORM, revenue_category="MEMBERSHIP", revenue_account_code="4002",
                           notes="Website revenue = gross (no pass-through). Not a Founding product."),
    "subscription_club": dict(_PLATFORM, revenue_category="PLATFORM_SUBSCRIPTION", revenue_account_code="4002",
                              notes="Platform-sold subscription without a seller; seller-backed clubs use the marketplace."),
    "club_membership": dict(_PLATFORM, revenue_category="PLATFORM_SUBSCRIPTION", revenue_account_code="4002",
                            notes="Platform-sold subscription without a seller; seller-backed clubs use the marketplace."),
    "contest_participation": dict(_PLATFORM, revenue_category="SERVICE_FEE", revenue_account_code="4009",
                                  notes="Website revenue = gross."),
    "shop_purchase": dict(_PLATFORM, revenue_category="SERVICE_FEE", revenue_account_code="4009",
                          notes="Website revenue = gross."),
    REFERRAL_POOL_PRODUCT_CODE: dict(
        _PLATFORM,
        revenue_category="REFERRAL_POOL_ENTRY",
        revenue_account_code="4008",
        notes=REFERRAL_POOL_POLICY_NOTES,
    ),
    MARKETPLACE_PRODUCT_CODE: dict(
        _PLATFORM,
        revenue_category="MARKETPLACE_MARKUP",
        revenue_account_code="4007",
        deferred_account_code="2114",
        notes=(
            "Website revenue = the 20% markup only; the seller base is never MyHigh5 revenue. "
            "CONFIRMED 2026-09-25: direct commission = 20% of the markup ($100 base -> $20 markup -> $4)."
        ),
    ),
}


def seed_new_model_reference_data(db: Session) -> None:
    """Idempotent insert-if-missing (never overwrites an existing, possibly edited, row)."""
    from datetime import datetime

    from app.models.accounting import AccountType, ChartOfAccounts
    from app.models.business_model import BusinessModelVersion, ReferralPoolConfig, RevenuePolicy
    from app.models.payment import ProductType

    for code, name, kind, parent in NEW_MODEL_ACCOUNTS:
        if db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).first():
            continue
        parent_row = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == parent).first()
        db.add(ChartOfAccounts(account_code=code, account_name=name, account_type=AccountType(kind),
                               parent_id=parent_row.id if parent_row else None, is_active=True))
    for product_code, policy in NEW_MODEL_REVENUE_POLICIES.items():
        exists = db.query(RevenuePolicy).filter(
            RevenuePolicy.model_version == NEW_MODEL_VERSION, RevenuePolicy.product_code == product_code
        ).first()
        if not exists:
            db.add(RevenuePolicy(model_version=NEW_MODEL_VERSION, product_code=product_code, is_active=True, **policy))
    if not db.query(ProductType).filter(ProductType.code == REFERRAL_POOL_PRODUCT_CODE).first():
        db.add(ProductType(
            code=REFERRAL_POOL_PRODUCT_CODE,
            name="MyHigh5 Referral Pool",
            description="One-time $100 entry to the MyHigh5 Referral Pool (max 10,000 members).",
            price=REFERRAL_POOL_PRICE, currency="USD", validity_days=0, is_active=True,
            is_consumable=False, has_affiliate_commission=False,
        ))
    if not db.query(ReferralPoolConfig).first():
        db.add(ReferralPoolConfig(capacity=REFERRAL_POOL_CAPACITY, price_product_code=REFERRAL_POOL_PRODUCT_CODE))
    if not db.query(BusinessModelVersion).filter(BusinessModelVersion.version == NEW_MODEL_VERSION).first():
        db.add(BusinessModelVersion(version=NEW_MODEL_VERSION, effective_at=datetime.utcnow(),
                                    notes="Direct affiliate 20% + Referral Pool + Leaders + marketplace agent model"))
    db.flush()
