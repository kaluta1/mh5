"""Seller jurisdiction rules: a versioned catalogue, kept apart from MyHigh5 platform policy.

LEGAL rules describe a government requirement (business registration, a registration exemption, tax,
trader traceability, platform tax reporting). They are seeded as DRAFT and are used for automatic
decisions only after an administrator ACTIVATES them, recording the official source and the date it
was reviewed. PLATFORM rules are MyHigh5's own policy and are seeded ACTIVE.

A business seller whose establishment country has no ACTIVE legal registration rule is a seller MyHigh5
cannot assess automatically: the application goes to manual review, never to automatic approval.
Nothing here assumes that a seller must register in Singapore because MyHigh5's operator may be there,
or that a lawful business must be an incorporated company.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.seller_verification import SellerApplication, SellerJurisdictionRule

LEGAL, PLATFORM = "LEGAL", "PLATFORM"
DRAFT, ACTIVE, RETIRED = "DRAFT", "ACTIVE", "RETIRED"

EU_COUNTRIES = frozenset({"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
                          "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"})

PRODUCT_CATEGORIES = ("GENERAL_GOODS", "CLOTHING", "ELECTRONICS", "HOME", "HANDMADE", "BOOKS_MEDIA", "DIGITAL_PRODUCTS",
                      "SERVICES", "FOOD", "ALCOHOL", "TOBACCO", "HEALTH_MEDICAL", "COSMETICS", "WEAPONS",
                      "FINANCIAL_SERVICES", "PROFESSIONAL_SERVICES", "OTHER")
# Activities that commonly need a product-specific licence or carry legal risk: always a person looks.
REGULATED_CATEGORIES = frozenset({"FOOD", "ALCOHOL", "TOBACCO", "HEALTH_MEDICAL", "COSMETICS", "WEAPONS",
                                  "FINANCIAL_SERVICES", "PROFESSIONAL_SERVICES"})

_BUSINESS = ["SOLE_TRADER", "ORGANISATION"]

# The default catalogue. Sources are the official authorities; the LEGAL rules stay DRAFT until a person
# confirms the current law against them.
DEFAULT_RULES: tuple[dict, ...] = (
    dict(rule_code="PLATFORM_MEMBER_IDENTITY", jurisdiction="*", scope="PLATFORM_POLICY", rule_kind=PLATFORM,
         requirement="MEMBER_IDENTITY", title="Verified MyHigh5 member identity",
         description="The seller's existing MyHigh5 member identity verification is reused. No second fee is charged."),
    dict(rule_code="PLATFORM_ACCURACY_DECLARATION", jurisdiction="*", scope="PLATFORM_POLICY", rule_kind=PLATFORM,
         requirement="ACCURACY_DECLARATION", title="Accuracy declaration",
         description="The seller declares that the information given is true and will be kept up to date."),
    dict(rule_code="PLATFORM_PRIVATE_SELLER_REVIEW", jurisdiction="*", scope="PLATFORM_POLICY", rule_kind=PLATFORM,
         seller_categories=["PRIVATE"], requirement="CLASSIFICATION_REVIEW_TRIGGERS",
         title="Private seller classification review (internal)",
         description="MyHigh5 reviews a private seller's classification after USD 1,000 in completed sales or 20 "
                     "completed sales in a rolling 12 months, or earlier when sales look commercial. These are "
                     "internal MyHigh5 review triggers, not legal registration thresholds."),
    dict(rule_code="PLATFORM_BUSINESS_DETAILS", jurisdiction="*", scope="PLATFORM_POLICY", rule_kind=PLATFORM,
         seller_categories=_BUSINESS, requirement="BUSINESS_DETAILS",
         title="Business seller details",
         description="Legal name, trading name, business establishment, business address and contact details."),
    dict(rule_code="PLATFORM_REGISTRATION_OR_EXEMPTION", jurisdiction="*", scope="PLATFORM_POLICY", rule_kind=PLATFORM,
         seller_categories=_BUSINESS, requirement="REGISTRATION_OR_EXEMPTION",
         title="Registration details or recorded exemption",
         description="Registration authority and number where the seller is registered; for a sole trader exempt "
                     "from registration, the legal basis of the exemption and supporting evidence."),
    dict(rule_code="PLATFORM_AUTHORISED_REPRESENTATIVE", jurisdiction="*", scope="PLATFORM_POLICY", rule_kind=PLATFORM,
         seller_categories=["ORGANISATION"], requirement="AUTHORISED_REPRESENTATIVE",
         title="Authorised representative",
         description="The person applying is authorised to act for the organisation."),
    dict(rule_code="PLATFORM_PAYOUT_BENEFICIARY", jurisdiction="*", scope="PLATFORM_POLICY", rule_kind=PLATFORM,
         seller_categories=_BUSINESS, requirement="PAYOUT_BENEFICIARY",
         title="Payout destination on file",
         description="The member's own password-confirmed payout destination (the existing MyHigh5 mechanism)."),
    dict(rule_code="PLATFORM_REGULATED_PRODUCTS", jurisdiction="*", scope="LICENCE", rule_kind=PLATFORM,
         product_categories=sorted(REGULATED_CATEGORIES), requirement="LICENCE_EVIDENCE",
         title="Regulated products or services",
         description="Regulated activities need the applicable licence and are always reviewed by a person."),
    # ---- legal rules (DRAFT until reviewed against the official source)
    dict(rule_code="SG_ACRA_BUSINESS_REGISTRATION", jurisdiction="SG", scope="BUSINESS_REGISTRATION", rule_kind=LEGAL,
         seller_categories=_BUSINESS, business_structures=["REGISTERED", "COMPANY", "PARTNERSHIP", "LLP"],
         requirement="REGISTRATION_NUMBER", title="Singapore: ACRA registration (UEN)",
         description="A business established in Singapore that must register with ACRA gives its UEN. A UEN is "
                     "checked against ACRA only through an authorised integration; until then a person reviews it.",
         official_source_url="https://www.acra.gov.sg/"),
    dict(rule_code="SG_ACRA_FULL_NAME_EXEMPTION", jurisdiction="SG", scope="REGISTRATION_EXEMPTION", rule_kind=LEGAL,
         seller_categories=["SOLE_TRADER"], business_structures=["EXEMPT"], requirement="EXEMPTION_BASIS",
         title="Singapore: business carried on under the owner's full name",
         description="An individual carrying on business under their full legal name may be exempt from business "
                     "name registration. The basis is recorded and reviewed; MyHigh5 does not decide the exemption.",
         official_source_url="https://www.acra.gov.sg/"),
    dict(rule_code="SG_GST_STATUS", jurisdiction="SG", scope="TAX", rule_kind=LEGAL, seller_categories=_BUSINESS,
         requirement="TAX_REGISTRATION_STATUS", title="Singapore: GST registration status (separate from ACRA)",
         description="GST registration is a separate tax matter from business registration. The seller states "
                     "whether they are GST-registered.",
         official_source_url="https://www.iras.gov.sg/taxes/goods-services-tax-(gst)"),
    dict(rule_code="US_INFORM_CONSUMERS_ACT", jurisdiction="US", scope="TRADER_TRACEABILITY", rule_kind=LEGAL,
         applies_by_customer_market=True, requirement="HIGH_VOLUME_SELLER_INFORMATION",
         title="United States: INFORM Consumers Act (high-volume third-party sellers)",
         description="An online-marketplace obligation to collect and verify information from high-volume "
                     "third-party sellers. It is not business registration.",
         official_source_url="https://www.ftc.gov/business-guidance/resources/informing-businesses-about-inform-consumers-act"),
    dict(rule_code="EU_DSA_TRADER_TRACEABILITY", jurisdiction="EU", scope="TRADER_TRACEABILITY", rule_kind=LEGAL,
         seller_categories=_BUSINESS, applies_by_customer_market=True, requirement="TRADER_INFORMATION",
         title="European Union: trader traceability (Digital Services Act, Article 30)",
         description="Platforms let consumers in the EU deal with traders only after obtaining traceability "
                     "information. It is not business registration.",
         official_source_url="https://eur-lex.europa.eu/eli/reg/2022/2065/oj"),
    dict(rule_code="EU_DAC7_PLATFORM_REPORTING", jurisdiction="EU", scope="PLATFORM_TAX_REPORTING", rule_kind=LEGAL,
         requirement="PLATFORM_TAX_REPORTING", title="European Union: platform tax reporting (DAC7)",
         description="Platform operators may have to report certain seller data to tax authorities. Recorded for "
                     "awareness only: MyHigh5 does not file tax reports from this module.",
         official_source_url="https://eur-lex.europa.eu/eli/dir/2021/514/oj"),
)


def seed_defaults(db: Session) -> int:
    """Insert the default catalogue (version 1) where missing. Never changes an existing rule."""
    added = 0
    existing = {code for (code,) in db.query(SellerJurisdictionRule.rule_code).all()}
    for spec in DEFAULT_RULES:
        if spec["rule_code"] in existing:
            continue
        db.add(SellerJurisdictionRule(version=1, status=ACTIVE if spec["rule_kind"] == PLATFORM else DRAFT,
                                      effective_from=date(2026, 10, 31) if spec["rule_kind"] == PLATFORM else None,
                                      **spec))
        added += 1
    db.flush()
    return added


class RuleError(ValueError):
    pass


def activate(db: Session, rule: SellerJurisdictionRule, *, actor_user_id: int, official_source_url: str,
             last_reviewed_on: date, effective_from: date, note: str) -> SellerJurisdictionRule:
    """A legal rule is activated only with its official source and the date a person reviewed it."""
    if rule.status == RETIRED:
        raise RuleError("A retired rule cannot be activated; create a new version")
    if not (official_source_url or "").startswith("https://"):
        raise RuleError("An official https source is required")
    if last_reviewed_on > date.today():
        raise RuleError("The review date cannot be in the future")
    rule.official_source_url, rule.last_reviewed_on, rule.effective_from = official_source_url, last_reviewed_on, effective_from
    rule.status, rule.activated_by_user_id, rule.activated_at, rule.review_note = ACTIVE, actor_user_id, datetime.utcnow(), note
    db.flush()
    return rule


def retire(db: Session, rule: SellerJurisdictionRule, *, note: str) -> SellerJurisdictionRule:
    rule.status, rule.review_note = RETIRED, note
    db.flush()
    return rule


def _matches(values: Optional[Iterable], wanted: Iterable) -> bool:
    if not values:
        return True
    return bool(set(values) & {w for w in wanted if w})


def _jurisdictions(app: SellerApplication) -> set[str]:
    codes = {c for c in (app.residence_country, app.establishment_country) if c}
    return codes | ({"EU"} if codes & EU_COUNTRIES else set())


def _markets(app: SellerApplication) -> set[str]:
    codes = {c for c in (app.customer_markets or []) if c}
    return codes | ({"EU"} if codes & EU_COUNTRIES else set())


def applicable_rules(db: Session, app: SellerApplication, *, today: Optional[date] = None) -> list[SellerJurisdictionRule]:
    """Every ACTIVE rule for this seller: by residence/establishment, or by customer market for rules that
    apply where customers are; then by seller category, business structure and product category."""
    today = today or date.today()
    places, markets = _jurisdictions(app), _markets(app)
    out = []
    for rule in db.query(SellerJurisdictionRule).filter(SellerJurisdictionRule.status == ACTIVE) \
            .order_by(SellerJurisdictionRule.rule_code, SellerJurisdictionRule.version.desc()).all():
        if rule.effective_from and rule.effective_from > today:
            continue
        if any(r.rule_code == rule.rule_code for r in out):        # newest active version only
            continue
        where = places | (markets if rule.applies_by_customer_market else set())
        if rule.jurisdiction != "*" and rule.jurisdiction not in where:
            continue
        if rule.subdivision and rule.subdivision != app.establishment_subdivision:
            continue
        if not _matches(rule.seller_categories, [app.seller_category]):
            continue
        if not _matches(rule.business_structures, [app.business_structure]):
            continue
        if rule.product_categories and not _matches(rule.product_categories, app.product_categories or []):
            continue
        out.append(rule)
    return out


def establishment_supported(rules: list[SellerJurisdictionRule], app: SellerApplication) -> bool:
    """Can a business seller's registration position be assessed automatically? Only with an ACTIVE legal
    registration (or exemption) rule for the country where the business is established."""
    if app.seller_category == "PRIVATE":
        return True
    return any(r.rule_kind == LEGAL and r.scope in ("BUSINESS_REGISTRATION", "REGISTRATION_EXEMPTION")
               and r.jurisdiction == app.establishment_country for r in rules)


def rule_out(rule: SellerJurisdictionRule) -> dict:
    return {"id": rule.id, "rule_code": rule.rule_code, "version": rule.version, "jurisdiction": rule.jurisdiction,
            "subdivision": rule.subdivision, "scope": rule.scope, "rule_kind": rule.rule_kind,
            "requirement": rule.requirement, "title": rule.title, "description": rule.description,
            "seller_categories": rule.seller_categories, "business_structures": rule.business_structures,
            "product_categories": rule.product_categories, "applies_by_customer_market": bool(rule.applies_by_customer_market),
            "official_source_url": rule.official_source_url, "status": rule.status,
            "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
            "last_reviewed_on": rule.last_reviewed_on.isoformat() if rule.last_reviewed_on else None,
            "review_note": rule.review_note}
