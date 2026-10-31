"""Marketplace seller registration and verification. SYNTHETIC accounts, documents and providers.

Covers private sellers, sole traders (registered and exempt), organisations, jurisdiction rule selection,
private seller review thresholds (boundaries, currency conversion, commercial activity), provider
failures, signed and duplicate callbacks, automatic approval and manual review, admin permissions,
server-side selling restrictions, document security, existing order continuity, separation from member
KYC / commissions / Referral Pool, and the disabled feature flag."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.affiliate import AffiliateCommission
from app.models.business_model import MarketListing, MarketOrder, ReferralPoolMembership
from app.models.payment import Deposit
from app.models.kyc import KYCStatus, KYCVerification
from app.models.notification import Notification
from app.models.seller_verification import (SellerApplication, SellerClassificationReview, SellerDocument, SellerFxRate,
                                            SellerJurisdictionRule, SellerVerificationCheck)
from app.services import marketplace_listings as ml
from app.services import marketplace_service as m
from app.services import seller_verification as sv
from app.services import seller_verification_providers as prov
from app.services import seller_verification_rules as rules
from tests.unit.test_admin_security_hardening import bearer, person
from tests.unit.test_new_business_model import _user, custodian, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit
API = "/api/v1/marketplace/seller"
ADMIN = "/api/v1/admin/seller-verification"


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_STORAGE_DIR", str(tmp_path / "market"))
    monkeypatch.setattr(settings, "SELLER_DOCUMENT_STORAGE_DIR", str(tmp_path / "seller_docs"))
    monkeypatch.setattr(settings, "SELLER_DOCUMENT_ENCRYPTION_KEY", "synthetic-test-key-" + "x" * 32)
    monkeypatch.setattr(settings, "MARKETPLACE_SELLER_VERIFICATION_ENABLED", False)
    monkeypatch.setattr(settings, "SELLER_PRIVATE_REVIEW_SALES_USD", "1000.00")
    monkeypatch.setattr(settings, "SELLER_PRIVATE_REVIEW_ORDER_COUNT", 20)
    return tmp_path / "seller_docs"


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_SELLER_VERIFICATION_ENABLED", True)


@pytest.fixture
def providers():
    """Restore the real provider registry after a test registers a fake one."""
    saved = dict(prov._PROVIDERS)
    yield prov
    prov._PROVIDERS.clear()
    prov._PROVIDERS.update(saved)


def kyc(db, user, first="Amina", last="Juma", status=KYCStatus.APPROVED):
    db.add(KYCVerification(user_id=user.id, status=status, verified_first_name=first, verified_last_name=last))
    db.flush()


def seller(db, email, *, approved_kyc=True, wallet=True):
    user = _user(db, email)
    if wallet:
        user.payout_wallet_verified_at = datetime.utcnow()
    if approved_kyc:
        kyc(db, user)
    return user


def submit(db, user, data):
    sv.save_draft(db, user_id=user.id, data=data)
    return sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)


PRIVATE = {"seller_category": "PRIVATE", "legal_name": "Amina Juma", "residence_country": "TZ"}


def sole_trader(**over):
    data = {"seller_category": "SOLE_TRADER", "business_structure": "REGISTERED", "legal_name": "Amina Juma",
            "trading_name": "Amina Crafts", "residence_country": "SG", "establishment_country": "SG",
            "business_address": "1 Synthetic Road, Singapore", "contact_phone": "+6500000000",
            "product_categories": ["HANDMADE"], "registration_authority": "ACRA", "registration_number": "53000000X",
            "tax_registered": False}
    data.update(over)
    return data


def organisation(**over):
    data = sole_trader(seller_category="ORGANISATION", business_structure="COMPANY", trading_name="Juma Trading Pte",
                       representative={"full_name": "Amina Juma", "role": "Director"},
                       ownership=[{"full_name": "Amina Juma", "percent": "60"}, {"full_name": "B Synthetic", "percent": "40"}])
    data.update(over)
    return data


class FakeRegistry:
    name, check_type, callback_secret = "FAKE_REGISTRY", prov.BUSINESS_REGISTRY, "synthetic-callback-secret"

    def __init__(self, result="PASSED", fail=False, asynchronous=False):
        self.result, self.fail, self.asynchronous, self.calls = result, fail, asynchronous, 0

    def run(self, db, app):
        self.calls += 1
        if self.fail:
            raise TimeoutError("synthetic timeout")
        if self.asynchronous:
            return prov.ProviderResult(prov.PENDING, "SUBMITTED", f"reg-{app.id}")
        return prov.ProviderResult(self.result, "UEN_MATCHED" if self.result == "PASSED" else "UEN_NAME_MISMATCH")


def activate_sg(db):
    rules.seed_defaults(db)
    for code in ("SG_ACRA_BUSINESS_REGISTRATION", "SG_ACRA_FULL_NAME_EXEMPTION"):
        rule = db.query(SellerJurisdictionRule).filter_by(rule_code=code).one()
        rules.activate(db, rule, actor_user_id=None, official_source_url="https://www.acra.gov.sg/",
                       last_reviewed_on=date.today(), effective_from=date.today(), note="Reviewed (synthetic test)")


# ---------------------------------------------------------------- categories

def test_private_seller_with_member_kyc_is_approved_automatically_without_a_fee(world):
    db = world
    user = seller(db, "pv@t.com")
    deposits, kyc_row = db.query(Deposit).count(), db.query(KYCVerification).filter_by(user_id=user.id).one()
    app = submit(db, user, PRIVATE)
    assert app.status == sv.APPROVED and app.decided_by_user_id is None
    profile = sv.get_profile(db, user.id)
    assert profile.status == sv.APPROVED and profile.public_label == sv.LABEL_PRIVATE
    assert db.query(Deposit).count() == deposits                         # no second KYC fee
    assert kyc_row.status == KYCStatus.APPROVED                          # member KYC untouched
    assert "Government" not in profile.public_label


def test_private_seller_without_member_kyc_must_act_and_is_never_approved(world):
    db = world
    user = seller(db, "pn@t.com", approved_kyc=False)
    app = submit(db, user, PRIVATE)
    assert app.status == sv.ACTION_REQUIRED and "member identity verification" in app.correction_request
    kyc(db, user)
    app = sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)
    assert app.status == sv.APPROVED


def test_private_seller_name_mismatch_and_commercial_indicators_go_to_a_person(world):
    db = world
    user = seller(db, "pm@t.com")
    app = submit(db, user, {**PRIVATE, "legal_name": "Someone Else"})
    assert app.status == sv.MANUAL_REVIEW_REQUIRED and "IDENTITY_NAME_MISMATCH" in app.review_reasons
    other = seller(db, "pc@t.com")
    app = submit(db, other, {**PRIVATE, "commercial_indicators": {"buys_for_resale": True}})
    assert app.status == sv.MANUAL_REVIEW_REQUIRED and "COMMERCIAL_ACTIVITY_INDICATED" in app.review_reasons


def test_registered_sole_trader_needs_a_supported_jurisdiction_and_a_real_registry_check(world, providers):
    db = world
    rules.seed_defaults(db)                                              # SG legal rules seeded as DRAFT
    user = seller(db, "st@t.com")
    app = submit(db, user, sole_trader())
    assert app.status == sv.MANUAL_REVIEW_REQUIRED
    assert {"JURISDICTION_NOT_SUPPORTED", "BUSINESS_REGISTRY_NOT_AUTOMATED"} <= set(app.review_reasons)
    assert sv.get_profile(db, user.id).status == sv.MANUAL_REVIEW_REQUIRED

    activate_sg(db)
    providers.register(FakeRegistry())
    other = seller(db, "st2@t.com")
    app = submit(db, other, sole_trader())
    assert app.status == sv.APPROVED, app.review_reasons
    assert "SG_ACRA_BUSINESS_REGISTRATION@v1" in app.applicable_rules and "SG_GST_STATUS@v1" not in app.applicable_rules
    assert sv.get_profile(db, other.id).public_label == sv.LABEL_BUSINESS


def test_exempt_sole_trader_needs_no_registration_number_and_is_always_reviewed(world):
    db = world
    activate_sg(db)
    user = seller(db, "ex@t.com")
    data = sole_trader(business_structure="EXEMPT", registration_authority=None, registration_number=None,
                       exemption_basis="Business carried on under my full legal name only.")
    sv.save_draft(db, user_id=user.id, data=data)
    assert sv.missing_fields(sv.latest_application(db, user.id)) == []    # no registration number demanded
    app = sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)
    assert app.status == sv.ACTION_REQUIRED and "EXEMPTION_EVIDENCE_MISSING" in app.review_reasons
    sv.store_document(db, user_id=user.id, doc_type="EXEMPTION_EVIDENCE", filename="basis.pdf",
                      stream=io.BytesIO(b"%PDF synthetic"))
    app = sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)
    assert app.status == sv.MANUAL_REVIEW_REQUIRED and "EXEMPTION_CLAIM" in app.review_reasons
    sv.admin_decide(db, app, admin_user_id=user.id, action="approve", reason="Exemption basis reviewed")
    assert sv.get_profile(db, user.id).public_label == sv.LABEL_EXEMPT


def test_organisation_needs_a_representative_and_conflicting_ownership_is_reviewed(world, providers):
    db = world
    activate_sg(db)
    providers.register(FakeRegistry())
    user = seller(db, "org@t.com")
    sv.save_draft(db, user_id=user.id, data=organisation(representative=None))
    with pytest.raises(sv.SellerError, match="representative"):
        sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)
    sv.save_draft(db, user_id=user.id, data=organisation(
        ownership=[{"full_name": "Amina Juma", "percent": "70"}, {"full_name": "B Synthetic", "percent": "40"}]))
    app = sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)
    assert "OWNERSHIP_CONFLICT" in app.review_reasons and "REPRESENTATIVE_NOT_AUTOMATED" in app.review_reasons
    assert app.status == sv.MANUAL_REVIEW_REQUIRED


def test_regulated_activity_and_licences_need_documents_and_a_person(world, providers):
    db = world
    activate_sg(db)
    providers.register(FakeRegistry())
    user = seller(db, "rg@t.com")
    app = submit(db, user, sole_trader(product_categories=["FOOD"], licences=[
        {"type": "Food shop", "authority": "SFA", "number": "FS-1", "expires_on": "2030-01-01"}]))
    assert app.status == sv.ACTION_REQUIRED and "LICENCE_DOCUMENT_MISSING" in app.review_reasons
    sv.store_document(db, user_id=user.id, doc_type="LICENCE", filename="licence.png", stream=io.BytesIO(b"\x89PNG"))
    app = sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)
    assert app.status == sv.MANUAL_REVIEW_REQUIRED
    assert {"REGULATED_ACTIVITY", "DOCUMENTS_REQUIRE_REVIEW", "LICENCE_NOT_AUTOMATED"} <= set(app.review_reasons)


# ---------------------------------------------------------------- jurisdiction rules

def test_jurisdiction_rule_selection(world):
    db = world
    rules.seed_defaults(db)
    assert rules.seed_defaults(db) == 0                                  # idempotent
    for rule in db.query(SellerJurisdictionRule).filter_by(rule_kind=rules.LEGAL).all():
        assert rule.status == rules.DRAFT and rule.official_source_url.startswith("https://")
        rules.activate(db, rule, actor_user_id=None, official_source_url=rule.official_source_url,
                       last_reviewed_on=date.today(), effective_from=date.today(), note="Reviewed (synthetic)")

    def codes(**fields):
        app = SellerApplication(**{"seller_category": "SOLE_TRADER", "business_structure": "REGISTERED", **fields})
        return {r.rule_code for r in rules.applicable_rules(db, app)}

    sg = codes(residence_country="SG", establishment_country="SG")
    assert {"SG_ACRA_BUSINESS_REGISTRATION", "SG_GST_STATUS"} <= sg and "SG_ACRA_FULL_NAME_EXEMPTION" not in sg
    assert "SG_ACRA_FULL_NAME_EXEMPTION" in codes(establishment_country="SG", business_structure="EXEMPT")
    kenyan = codes(residence_country="KE", establishment_country="KE")
    assert not any(c.startswith("SG_") for c in kenyan)                 # never Singapore rules by default
    assert "US_INFORM_CONSUMERS_ACT" in codes(establishment_country="KE", customer_markets=["US"])
    assert "US_INFORM_CONSUMERS_ACT" not in kenyan
    assert {"EU_DSA_TRADER_TRACEABILITY", "EU_DAC7_PLATFORM_REPORTING"} <= codes(establishment_country="DE")
    assert "EU_DSA_TRADER_TRACEABILITY" not in codes(seller_category="PRIVATE", business_structure=None,
                                                    establishment_country="DE")
    assert not rules.establishment_supported(rules.applicable_rules(db, SellerApplication(
        seller_category="SOLE_TRADER", business_structure="REGISTERED", establishment_country="KE")),
        SellerApplication(seller_category="SOLE_TRADER", establishment_country="KE"))
    with pytest.raises(rules.RuleError, match="https"):
        rules.activate(db, db.query(SellerJurisdictionRule).first(), actor_user_id=None, official_source_url="",
                       last_reviewed_on=date.today(), effective_from=date.today(), note="x" * 10)


# ---------------------------------------------------------------- monitoring

def _sale(db, seller_user, buyer, amount, *, state="RELEASED", currency="USD", days_ago=1, item_type="listing", **kw):
    order = MarketOrder(buyer_user_id=buyer.id, seller_user_id=seller_user.id, item_type=item_type, item_id=1,
                        currency=currency, seller_base_amount=Decimal(amount), markup_rate=Decimal("0.2"),
                        markup_amount=Decimal(amount) * Decimal("0.2"), buyer_total_amount=Decimal(amount) * Decimal("1.2"),
                        state=state, business_model_version="NEW_V2",
                        confirmed_at=datetime.utcnow() - timedelta(days=days_ago), **kw)
    db.add(order)
    db.flush()
    return order


def test_sales_threshold_boundaries_exclusions_and_idempotency(world):
    db = world
    user, buyer = seller(db, "th@t.com"), _user(db, "thb@t.com")
    submit(db, user, PRIVATE)
    _sale(db, user, buyer, "999.99")
    _sale(db, user, buyer, "500", state="REFUNDED", refunded_at=datetime.utcnow())
    _sale(db, user, buyer, "500", state="CANCELLED")
    _sale(db, user, buyer, "500", item_type="club_subscription")         # a subscription is not a seller sale
    _sale(db, user, buyer, "500", days_ago=366)                          # outside the rolling window
    sales = sv.rolling_sales(db, user.id)
    assert sales["sales_usd"] == Decimal("999.99") and sales["order_count"] == 1
    assert sv.monitor_private_seller(db, user.id) is None
    _sale(db, user, buyer, "0.01")
    review = sv.monitor_private_seller(db, user.id)
    assert review.trigger == "SALES_AMOUNT" and review.qualifying_sales_usd == Decimal("1000.00")
    assert "not a statutory" in review.detail["note"]
    assert sv.monitor_private_seller(db, user.id) is None                # idempotent while open
    sv.resolve_classification_review(db, review, admin_user_id=buyer.id, resolution="REMAINS_PRIVATE", note="Personal items")
    assert sv.monitor_private_seller(db, user.id) is None                # same level never re-opens
    assert sv.get_profile(db, user.id).status == sv.APPROVED             # a review never restricts selling


def test_order_count_boundary_and_currency_conversion(world):
    db = world
    user, buyer = seller(db, "oc@t.com"), _user(db, "ocb@t.com")
    submit(db, user, PRIVATE)
    for _ in range(19):
        _sale(db, user, buyer, "1.00")
    assert sv.monitor_private_seller(db, user.id) is None
    _sale(db, user, buyer, "10.00", currency="EUR")                      # no recorded rate: not counted, reported
    sales = sv.rolling_sales(db, user.id)
    assert sales["order_count"] == 19 and len(sales["unconverted_order_ids"]) == 1
    db.add(SellerFxRate(currency="EUR", as_of=date.today() - timedelta(days=10), usd_per_unit=Decimal("1.10"),
                        source="Synthetic reference rate"))
    db.flush()
    sales = sv.rolling_sales(db, user.id)
    assert sales["order_count"] == 20 and sales["sales_usd"] == Decimal("30.00") and "EUR" in sales["fx_rates"]
    review = sv.monitor_private_seller(db, user.id)
    assert review.trigger == "ORDER_COUNT" and review.fx_rates_used["EUR"].startswith("EUR@")


def test_commercial_activity_below_thresholds_opens_a_review(world):
    db = world
    user = seller(db, "ca@t.com")
    submit(db, user, PRIVATE)
    listing = ml.create_listing(db, seller_user_id=user.id, data={
        "kind": "PHYSICAL", "title": "New phone cases", "description": "Brand new phone cases in stock.",
        "price_usd": "5", "quantity_available": 50, "handover_details": "Courier"})
    ml.publish(db, listing, seller_user_id=user.id)
    review = sv.monitor_private_seller(db, user.id)
    assert review.trigger == "COMMERCIAL_INDICATOR" and review.detail["signal"] == "STOCK_QUANTITY"
    assert review.qualifying_sales_usd == Decimal("0.00")


# ---------------------------------------------------------------- providers and callbacks

def test_provider_failures_are_retried_then_reviewed_and_never_approve(world, providers):
    db = world
    activate_sg(db)
    failing = FakeRegistry(fail=True)
    providers.register(failing)
    user = seller(db, "pf@t.com")
    app = submit(db, user, sole_trader())
    check = db.query(SellerVerificationCheck).filter_by(application_id=app.id, check_type="BUSINESS_REGISTRY").one()
    assert app.status == sv.CHECKS_IN_PROGRESS and check.status == "UNAVAILABLE" and check.last_error == "TimeoutError"
    sv.retry_in_progress(db)
    sv.retry_in_progress(db)
    assert failing.calls == 3 and app.status == sv.MANUAL_REVIEW_REQUIRED and "PROVIDER_UNAVAILABLE" in app.review_reasons
    assert sv.get_profile(db, user.id).status != sv.APPROVED


def _signed(body: dict, secret="synthetic-callback-secret"):
    raw = json.dumps(body).encode()
    return raw, {"X-Signature": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
                 "Content-Type": "application/json"}


def test_signed_callbacks_apply_once_and_bad_signatures_are_refused(client, world, providers):
    db = world
    activate_sg(db)
    providers.register(FakeRegistry(asynchronous=True))
    user = seller(db, "cb@t.com")
    app = submit(db, user, sole_trader())
    db.commit()
    assert app.status == sv.CHECKS_IN_PROGRESS
    payload = {"event_id": "evt-1", "reference": f"reg-{app.id}", "outcome": "PASSED", "result_code": "UEN_MATCHED"}
    raw, headers = _signed(payload)
    url = f"{API}/provider-callback/FAKE_REGISTRY"
    bad = client.post(url, content=raw, headers={**headers, "X-Signature": "0" * 64})
    assert bad.status_code == 404
    assert client.post(f"{API}/provider-callback/UNKNOWN", content=raw, headers=headers).status_code == 404
    first = client.post(url, content=raw, headers=headers)
    assert first.status_code == 200 and first.json() == {"duplicate": False, "applied": True}
    again = client.post(url, content=raw, headers=headers)
    assert again.json() == {"duplicate": True}
    db.expire_all()
    assert db.get(SellerApplication, app.id).status == sv.APPROVED
    assert db.query(Notification).filter(Notification.user_id == user.id,
                                         Notification.title == "Seller registration approved").count() == 1


# ---------------------------------------------------------------- admin

def test_admin_routes_need_the_explicit_permission_and_decisions_need_reasons(client, world):
    db = world
    reviewer = person(db, "sv_reviewer", admin=True, permissions=["review_seller_verification"])
    plain_admin = person(db, "sv_admin", admin=True)
    member = person(db, "sv_member")
    user = seller(db, "ad@t.com")
    app = submit(db, user, {**PRIVATE, "commercial_indicators": {"manufactures_for_sale": True}})
    db.commit()
    assert client.get(f"{ADMIN}/applications", headers=bearer(member)).status_code == 403
    assert client.get(f"{ADMIN}/applications", headers=bearer(plain_admin)).status_code == 403
    listed = client.get(f"{ADMIN}/applications", headers=bearer(reviewer))
    assert listed.status_code == 200 and listed.json()[0]["id"] == app.id
    detail = client.get(f"{ADMIN}/applications/{app.id}", headers=bearer(reviewer)).json()
    assert "COMMERCIAL_ACTIVITY_INDICATED" in detail["review_reasons"] and detail["checks"][0]["check_type"] == "IDENTITY"
    url = f"{ADMIN}/applications/{app.id}/decision"
    assert client.post(url, headers=bearer(reviewer), json={"action": "reject", "reason": "x"}).status_code == 422
    no_msg = client.post(url, headers=bearer(reviewer), json={"action": "reject", "reason": "Commercial seller"})
    assert no_msg.status_code == 422
    done = client.post(url, headers=bearer(reviewer), json={
        "action": "reject", "reason": "Manufactures goods: business onboarding needed",
        "seller_message": "Please register as a business seller."})
    assert done.status_code == 200 and done.json()["status"] == sv.REJECTED
    db.expire_all()
    audit = db.query(AuditTrail).filter_by(action="SELLER_REJECT").one()
    assert audit.user_id == reviewer.id and audit.new_values["reason"].startswith("Manufactures")
    # the seller sees the message but not the internal reason
    note = db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.id.desc()).first()
    assert "business seller" in note.message and "Manufactures goods" not in note.message
    sv.appeal(db, user_id=user.id, text="I make these for family; I sold a few spares only.")
    assert db.get(SellerApplication, app.id).status == sv.MANUAL_REVIEW_REQUIRED
    preview = client.get(f"{ADMIN}/migration-preview", headers=bearer(reviewer))
    assert preview.status_code == 200 and preview.json()["read_only"] is True


# ---------------------------------------------------------------- enforcement

def _physical(**over):
    return {"kind": "PHYSICAL", "title": "Hand-made basket", "description": "Woven sisal basket, 40 cm.",
            "price_usd": "25.00", "quantity_available": 2, "handover_details": "Collection or courier.", **over}


def test_flag_off_changes_nothing(world, custodian):
    db = world
    user, buyer = _user(db, "off@t.com"), _user(db, "offb@t.com")
    listing = ml.publish(db, ml.create_listing(db, seller_user_id=user.id, data=_physical()), seller_user_id=user.id)
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id)
    assert listing.status == ml.PUBLISHED and order.state == m.PAYMENT_PENDING and sv.can_sell(db, user.id)


def test_enforcement_keeps_drafts_and_blocks_publishing_live_edits_and_new_orders(world, custodian, enforced):
    db = world
    user, buyer = seller(db, "en@t.com"), _user(db, "enb@t.com")
    draft = ml.create_listing(db, seller_user_id=user.id, data=_physical())
    ml.update_listing(db, draft, seller_user_id=user.id, data={"title": "Renamed basket"})   # drafts always
    with pytest.raises(sv.SellerNotEligible):
        ml.publish(db, draft, seller_user_id=user.id)
    assert draft.status == ml.DRAFT
    submit(db, user, PRIVATE)
    ml.publish(db, draft, seller_user_id=user.id)
    held = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=draft.id)
    m.apply_custodian_event(db, held, event_type="FUNDED", external_event_id="sv-1", custodian_reference="SV-1")

    approved = db.get(SellerApplication, sv.get_profile(db, user.id).approved_application_id)
    sv.admin_decide(db, approved, admin_user_id=buyer.id, action="restrict", reason="Policy breach under review",
                    seller_message="Selling is paused while we review your account.")
    with pytest.raises(m.MarketplaceError, match="not available"):
        m.create_order(db, buyer_user_id=_user(db, "enc@t.com").id, item_type="listing", item_id=draft.id)
    with pytest.raises(sv.SellerNotEligible):
        ml.update_listing(db, draft, seller_user_id=user.id, data={"price_usd": "30"})
    ml.unpublish(db, draft, seller_user_id=user.id)
    with pytest.raises(sv.SellerNotEligible):                            # relisting
        ml.publish(db, draft, seller_user_id=user.id)
    # existing order continuity: the paid order still completes; nothing is deleted
    m.confirm_receipt(db, held, buyer_user_id=buyer.id, policy_version=m.ACCEPTANCE_POLICY_VERSION)
    assert held.state in (m.BUYER_CONFIRMED, m.RELEASE_PENDING)
    assert db.query(MarketListing).filter_by(id=draft.id).count() == 1


def test_api_returns_403_for_unapproved_publish_and_hides_listings_of_restricted_sellers(client, world, enforced, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", True)
    user = person(db, "api_sv_seller")
    created = client.post("/api/v1/marketplace/listings", headers=bearer(user), json=_physical())
    assert created.status_code == 201 and created.json()["status"] == "DRAFT"
    refused = client.post(f"/api/v1/marketplace/listings/{created.json()['id']}/publish", headers=bearer(user))
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SELLER_NOT_APPROVED"
    status = client.get(f"{API}/status", headers=bearer(user)).json()
    assert status["can_sell"] is False and status["enforcement_enabled"] is True
    # a published listing of a seller who is not approved is kept but not shown
    other = _user(db, "hidden@t.com")
    db.add(MarketListing(seller_user_id=other.id, kind="SERVICE", title="Hidden", description="Not approved seller",
                         price_usd=Decimal("10"), status="PUBLISHED", published_at=datetime.utcnow(),
                         warranty_available=False, insurance_available=False))
    db.commit()
    assert client.get("/api/v1/marketplace/listings").json() == []


# ---------------------------------------------------------------- documents and privacy

def test_documents_are_encrypted_private_and_audited(client, world, storage, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", True)
    user = person(db, "doc_seller")
    reviewer = person(db, "doc_reviewer", admin=True, permissions=["review_seller_verification"])
    saved = client.put(f"{API}/application", headers=bearer(user), json=sole_trader(
        business_structure="EXEMPT", tax_registered=True, tax_identifier="T12345678Z"))
    assert saved.status_code == 200
    app_out = saved.json()["application"]
    assert app_out["tax_identifier_masked"] == "****678Z" and "T12345678Z" not in saved.text
    secret = b"%PDF synthetic identity evidence 0042"
    up = client.post(f"{API}/application/documents", headers=bearer(user), data={"doc_type": "EXEMPTION_EVIDENCE"},
                     files={"file": ("evidence.pdf", secret, "application/pdf")})
    assert up.status_code == 201
    doc = db.query(SellerDocument).one()
    raw = open(os.path.join(storage, doc.storage_key), "rb").read()
    assert secret not in raw and doc.sha256 == hashlib.sha256(secret).hexdigest()   # encrypted at rest
    assert client.get(f"{ADMIN}/documents/{doc.id}", headers=bearer(user)).status_code == 403
    got = client.get(f"{ADMIN}/documents/{doc.id}", headers=bearer(reviewer))
    assert got.content == secret and got.headers["cache-control"] == "no-store"
    assert db.query(AuditTrail).filter_by(action="SELLER_DOCUMENT_VIEWED").count() == 1
    app = db.query(SellerApplication).one()
    assert app.tax_identifier_encrypted and "T12345678Z" not in app.tax_identifier_encrypted
    monkeypatch.setattr(settings, "SELLER_DOCUMENT_ENCRYPTION_KEY", "")
    with pytest.raises(sv.SellerError, match="not available"):
        sv.store_document(db, user_id=user.id, doc_type="OTHER", filename="a.pdf", stream=io.BytesIO(b"x"))


def test_public_listing_shows_only_the_label_never_compliance_data(world, custodian):
    db = world
    user = seller(db, "pub@t.com")
    submit(db, user, PRIVATE)
    profile = sv.get_profile(db, user.id)
    assert sv.public_label(profile) == "Private Seller"
    out = sv.status_out(db, user.id)
    assert "review_reasons" not in out["application"] and "checks" not in out["application"]


# ---------------------------------------------------------------- separation and continuing compliance

def test_separation_from_kyc_commissions_and_referral_pool(world):
    db = world
    user = seller(db, "sep@t.com")
    before = (db.query(AffiliateCommission).count(), db.query(ReferralPoolMembership).count(), db.query(Deposit).count())
    submit(db, user, PRIVATE)
    sv.run_private_seller_monitoring(db)
    sv.run_compliance_sweep(db)
    assert (db.query(AffiliateCommission).count(), db.query(ReferralPoolMembership).count(),
            db.query(Deposit).count()) == before
    assert db.query(KYCVerification).filter_by(user_id=user.id).one().status == KYCStatus.APPROVED


def test_changes_after_approval_and_expiry_trigger_reassessment(world, providers):
    db = world
    activate_sg(db)
    providers.register(FakeRegistry())
    user = seller(db, "cc@t.com")
    first = submit(db, user, sole_trader(licences=[{"type": "Trade", "authority": "X", "number": "1",
                                                    "expires_on": (date.today() + timedelta(days=10)).isoformat()}]))
    sv.store_document(db, user_id=user.id, doc_type="LICENCE", filename="l.pdf", stream=io.BytesIO(b"%PDF"))
    first = sv.submit(db, user_id=user.id, declaration_version=sv.DECLARATION_VERSION, accept_declaration=True)
    sv.admin_decide(db, first, admin_user_id=user.id, action="approve", reason="Licence document checked")
    assert sv.run_compliance_sweep(db)["reminders"] == 1 and sv.run_compliance_sweep(db)["reminders"] == 0
    # a change after approval is a new application; the approval stands meanwhile
    change = sv.save_draft(db, user_id=user.id, data={"trading_name": "Amina Crafts & Co"})
    assert change.id != first.id and change.supersedes_application_id == first.id
    assert sv.get_profile(db, user.id).status == sv.APPROVED
    # payout destination change: reverification with a grace period
    user.usdt_wallet_address = "0x" + "2" * 40
    db.flush()
    assert sv.run_compliance_sweep(db)["reverification"] == 1
    profile = sv.get_profile(db, user.id)
    assert profile.status == sv.REVERIFICATION_REQUIRED and sv.profile_can_sell(profile)
    # expired licence: reverification without grace
    profile.status = sv.APPROVED
    db.flush()
    assert sv.run_compliance_sweep(db, today=date.today() + timedelta(days=11))["reverification"] == 1
    assert not sv.profile_can_sell(sv.get_profile(db, user.id))


def test_migration_preview_is_read_only(world):
    db = world
    user, buyer = _user(db, "mp@t.com"), _user(db, "mpb@t.com")
    ml.publish(db, ml.create_listing(db, seller_user_id=user.id, data=_physical()), seller_user_id=user.id)
    _sale(db, user, buyer, "10", state="FUNDS_HELD")
    counts = (db.query(SellerApplication).count(), db.query(SellerClassificationReview).count())
    preview = sv.migration_preview(db)
    row = preview["sellers"][0]
    assert preview["existing_seller_count"] == 1 and row["open_orders_protected"] == 1
    assert "MEMBER_KYC_APPROVED" in row["missing"] and row["proposed_restriction"].startswith("When enforcement")
    assert (db.query(SellerApplication).count(), db.query(SellerClassificationReview).count()) == counts
    assert sv.get_profile(db, user.id) is None
