"""Prompt 7 marketplace completion: categories and conditions, archive, administrator moderation, listing
images, discovery, checkout idempotency, the signed custodian webhook (mocked provider), buyer support
requests, finance authorisation, seller-verification guards and the read-only reconciliation.
SYNTHETIC data only; the custodian is a test double; nothing is paid."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
from decimal import Decimal

import pytest
from PIL import Image

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.business_model import MarketListing, MarketListingEvent, MarketOrder, MarketOrderRequest
from app.models.notification import Notification
from app.services import marketplace_listings as ml
from app.services import marketplace_reconciliation as recon
from app.services import marketplace_service as m
from app.services import seller_verification as sv
from tests.unit.test_admin_security_hardening import PASSWORD, bearer, person
from tests.unit.test_marketplace_listings import physical, published, storage  # noqa: F401  (fixture)
from tests.unit.test_new_business_model import (  # noqa: F401  (fixtures)
    FakeCustodian, _assert_all_journals_balance, _user, custodian, world,
)

pytestmark = pytest.mark.unit
API = "/api/v1/marketplace"
ADMIN = "/api/v1/admin/marketplace"
BM = "/api/v1/admin/business-model/marketplace"
SECRET = b"synthetic-custodian-secret"


@pytest.fixture
def market(world, storage, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", True)
    return world


class SignedCustodian(FakeCustodian):
    """A mocked custodian whose webhook is an HMAC-SHA256 of the raw body (X-Test-Signature)."""

    name = "SIGNED_TEST_CUSTODIAN"

    def parse_webhook(self, headers, body):
        expected = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, headers.get("x-test-signature", "")):
            raise m.CustodianSignatureInvalid("bad signature")
        return json.loads(body)["events"]


@pytest.fixture
def signed(monkeypatch):
    fake = SignedCustodian()
    m.register_custodian(fake)
    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", fake.name)
    return fake


def deliver(client, events, *, provider=SignedCustodian.name, secret=SECRET):
    body = json.dumps({"events": events}).encode()
    sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return client.post(f"{API}/custodian/webhook/{provider}", content=body,
                       headers={"X-Test-Signature": sig, "Content-Type": "application/json"})


def png(size=(40, 30), color=(200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (32, 32), (10, 120, 10))
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"            # Make
    out = io.BytesIO()
    img.save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()



def _member(db, name, **kw):
    user = person(db, name, **kw)
    from app.models.kyc import KYCStatus, KYCVerification

    db.add(KYCVerification(user_id=user.id, status=KYCStatus.APPROVED))
    db.commit()
    return user


# ---------------------------------------------------------------- listings

def test_category_condition_archive_and_history(market):
    db = market
    seller = _user(db, "cat@t.com")
    with pytest.raises(ml.ListingError, match="category"):
        ml.create_listing(db, seller_user_id=seller.id, data=physical(category="SPACESHIPS"))
    with pytest.raises(ml.ListingError, match="item_condition"):
        ml.create_listing(db, seller_user_id=seller.id, data={**physical(), "kind": "SERVICE", "quantity_available": None,
                                                              "item_condition": "NEW"})
    listing = published(db, seller, physical(category="handmade", item_condition="used"))
    assert (listing.category, listing.item_condition) == ("HANDMADE", "USED")
    assert ml.snapshot(listing)["category"] == "HANDMADE"
    ml.archive(db, listing, seller_user_id=seller.id)
    assert listing.status == ml.ARCHIVED and not ml.is_buyable(listing)
    with pytest.raises(ml.ListingError, match="archived"):
        ml.publish(db, listing, seller_user_id=seller.id)
    with pytest.raises(ml.ListingError, match="cannot be edited"):
        ml.update_listing(db, listing, seller_user_id=seller.id, data={"price_usd": "1"})
    assert [e["action"] for e in ml.history(db, listing)] == ["CREATED", "PUBLISHED", "ARCHIVED"]


def test_regulated_category_needs_a_seller_registration_that_declared_it(market, monkeypatch):
    db = market
    seller = _user(db, "reg@t.com")
    listing = ml.create_listing(db, seller_user_id=seller.id, data=physical(category="FOOD"))
    published(db, seller, physical(category="FOOD"))                    # enforcement off: unchanged behaviour
    monkeypatch.setattr(settings, "MARKETPLACE_SELLER_VERIFICATION_ENABLED", True)
    from app.models.seller_verification import SellerApplication, SellerProfile

    app = SellerApplication(user_id=seller.id, status="APPROVED", seller_category="PRIVATE", product_categories=["HOME"])
    db.add(app)
    db.flush()
    db.add(SellerProfile(user_id=seller.id, status="APPROVED", approved_application_id=app.id))
    db.flush()
    with pytest.raises(sv.SellerCategoryNotApproved):
        ml.publish(db, listing, seller_user_id=seller.id)
    home = ml.create_listing(db, seller_user_id=seller.id, data=physical(category="HOME"))
    assert ml.publish(db, home, seller_user_id=seller.id).status == ml.PUBLISHED    # not regulated: allowed


def test_moderation_needs_the_permission_the_password_and_never_publishes(client, market):
    db = market
    seller = _member(db, "modseller")
    moderator = _member(db, "moderator", admin=True, permissions=("moderate_content",))
    plain_admin = _member(db, "plainadmin", admin=True)
    listing = published(db, seller, physical())
    db.commit()
    url = f"{ADMIN}/listings/{listing.id}/moderation"
    body = {"action": "suspend", "reason": "Counterfeit report", "seller_message": "Please contact support.",
            "current_password": PASSWORD}
    assert client.post(url, json=body, headers=bearer(plain_admin)).status_code == 403
    assert client.post(url, json={**body, "current_password": "wrong"}, headers=bearer(moderator)).status_code == 403
    assert client.post(url, json=body, headers=bearer(seller)).status_code == 403          # not an administrator
    r = client.post(url, json=body, headers=bearer(moderator))
    assert r.status_code == 200 and r.json()["status"] == "SUSPENDED"
    db.refresh(listing)
    assert listing.moderation_note == "Please contact support."
    assert client.get(f"{API}/listings/{listing.id}").status_code == 404                # gone from the marketplace
    with pytest.raises(ml.ListingError, match="suspended"):
        ml.publish(db, listing, seller_user_id=seller.id)
    assert client.post(f"{API}/listings/{listing.id}/publish", headers=bearer(seller)).status_code == 422
    r = client.post(url, json={**body, "action": "restore", "reason": "Report unfounded"}, headers=bearer(moderator))
    assert r.status_code == 200 and r.json()["status"] == "UNPUBLISHED"                 # never auto-published
    actions = [h["action"] for h in r.json()["history"]]
    assert actions[-2:] == ["SUSPEND", "RESTORE"]
    assert db.query(AuditTrail).filter(AuditTrail.action.in_(["MARKET_LISTING_SUSPEND", "MARKET_LISTING_RESTORE"])).count() == 2
    assert db.query(Notification).filter(Notification.user_id == seller.id).count() >= 2
    own = published(db, moderator, physical(title="Moderator's own basket"))
    db.commit()
    r = client.post(f"{ADMIN}/listings/{own.id}/moderation", json=body, headers=bearer(moderator))
    assert r.status_code == 403                                                          # not on one's own listing


# ---------------------------------------------------------------- images

def test_images_are_checked_by_content_reencoded_and_private_until_published(client, market):
    db = market
    seller, other = _member(db, "imgseller"), _member(db, "imgother")
    listing = ml.create_listing(db, seller_user_id=seller.id, data=physical())
    db.commit()
    up = f"{API}/listings/{listing.id}/images"
    fake = client.post(up, files={"file": ("photo.jpg", b"%PDF-1.4 not an image", "image/jpeg")}, headers=bearer(seller))
    assert fake.status_code == 422
    assert client.post(up, files={"file": ("a.png", png(), "image/png")}, headers=bearer(other)).status_code == 404
    r = client.post(up, files={"file": ("cam.jpg", jpeg_with_exif(), "image/jpeg")}, headers=bearer(seller))
    assert r.status_code == 201, r.text
    image = r.json()["images"][0]
    stored = open(ml.image_path(ml.images(db, listing)[0]), "rb").read()
    assert b"SecretCameraMaker" not in stored                                            # metadata stripped
    public = f"{API}/listings/{listing.id}/images/{image['id']}"
    assert client.get(public).status_code == 404                                         # draft: not public
    assert client.get(image["url"], headers=bearer(seller)).status_code == 200           # owner preview
    assert client.get(image["url"], headers=bearer(other)).status_code == 404
    ml.publish(db, listing, seller_user_id=seller.id)
    db.commit()
    got = client.get(public)
    assert got.status_code == 200 and got.headers["x-content-type-options"] == "nosniff"
    for _ in range(ml.MAX_IMAGES - 1):
        assert client.post(up, files={"file": ("a.png", png(), "image/png")}, headers=bearer(seller)).status_code == 201
    assert client.post(up, files={"file": ("a.png", png(), "image/png")}, headers=bearer(seller)).status_code == 422
    assert client.delete(f"{up}/{image['id']}", headers=bearer(seller)).status_code == 200
    assert len(ml.images(db, listing)) == ml.MAX_IMAGES - 1


# ---------------------------------------------------------------- discovery

def test_browse_sorts_filters_counts_and_escapes_the_search(client, market):
    db = market
    seller = _user(db, "browse@t.com")
    published(db, seller, physical(title="Cheap basket", price_usd="10.00", category="HOME"))
    published(db, seller, physical(title="Dear basket", price_usd="90.00", category="HANDMADE"))
    hidden = published(db, seller, physical(title="Hidden basket 100% wool", price_usd="50.00"))
    ml.moderate(db, hidden, admin_user_id=_user(db, "adm@t.com").id, action="suspend", reason="Review",
                seller_message="Under review")
    db.commit()
    r = client.get(f"{API}/listings", params={"sort": "price_desc"})
    assert [x["title"] for x in r.json()] == ["Dear basket", "Cheap basket"] and r.headers["x-total-count"] == "2"
    assert [x["title"] for x in client.get(f"{API}/listings", params={"category": "home"}).json()] == ["Cheap basket"]
    assert [x["title"] for x in client.get(f"{API}/listings", params={"max_price": "20"}).json()] == ["Cheap basket"]
    assert client.get(f"{API}/listings", params={"q": "%"}).json() == []                 # wildcard is literal
    assert "seller_price_usd" not in client.get(f"{API}/listings").json()[0]              # owner-only field
    assert {c["code"] for c in client.get(f"{API}/categories").json()} >= {"HOME", "FOOD"}


def test_new_routes_are_closed_while_the_marketplace_is_off(client, world, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", False)
    user = _member(world, "closed")
    assert client.get(f"{API}/categories").status_code == 200                            # vocabulary only
    assert client.get(f"{API}/listings/1/images/1").status_code == 503
    assert client.get(f"{API}/seller/summary", headers=bearer(user)).status_code == 503
    assert client.post(f"{API}/orders/1/requests", json={"kind": "REFUND", "reason": "x" * 20},
                       headers=bearer(user)).status_code == 503


# ---------------------------------------------------------------- checkout and custodian

def test_a_repeated_checkout_returns_the_same_order_and_reserves_once(market, custodian):
    db = market
    seller, buyer = _user(db, "idem-s@t.com"), _user(db, "idem-b@t.com")
    listing = published(db, seller, physical(quantity_available=3))
    first = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id, client_reference="chk-0001")
    again = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id, client_reference="chk-0001")
    assert first.id == again.id and listing.quantity_available == 2
    other = published(db, seller, physical(title="Another basket"))
    with pytest.raises(m.MarketplaceError, match="another item"):
        m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=other.id, client_reference="chk-0001")
    assert first.buyer_total_amount == Decimal("30.00")                                   # 25 + 20% markup, server-side


def test_the_custodian_webhook_is_signed_idempotent_and_checks_the_amount(client, market, signed):
    db = market
    seller, buyer = _user(db, "wh-s@t.com"), _user(db, "wh-b@t.com")
    listing = published(db, seller, physical(quantity_available=2))
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id)
    failing = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id)
    db.commit()
    assert listing.quantity_available == 0
    funded = {"event_type": "FUNDED", "event_id": "ev-1", "order_id": order.id, "custodian_reference": "CUS-1",
              "amount": "30.00", "currency": "USD"}
    assert deliver(client, [funded], secret=b"wrong").status_code == 401
    assert deliver(client, [funded], provider="SOMEONE_ELSE").status_code == 503
    bad = deliver(client, [{**funded, "event_id": "ev-0", "amount": "29.99"}]).json()["events"][0]
    assert bad["result"] == "REJECTED" and "does not match" in bad["detail"]
    db.refresh(order)
    assert order.state == m.PAYMENT_PENDING                                               # nothing booked
    assert deliver(client, [funded]).json()["events"][0]["result"] == "APPLIED"
    assert deliver(client, [funded]).json()["events"][0]["result"] == "DUPLICATE"
    db.refresh(order)
    assert order.state == m.FUNDS_HELD and order.custodian_reference == "CUS-1"
    r = deliver(client, [{"event_type": "PAYMENT_FAILED", "event_id": "ev-2", "order_id": failing.id}])
    assert r.json()["events"][0]["result"] == "APPLIED"
    db.refresh(failing)
    db.refresh(listing)
    assert failing.state == m.CANCELLED and listing.quantity_available == 1               # unit given back
    _assert_all_journals_balance(db)


def test_without_a_custodian_the_webhook_is_closed(client, market, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", "")
    assert deliver(client, [], provider="UNCONFIGURED").status_code == 503


# ---------------------------------------------------------------- buyer requests and finance authorisation

def _paid_order(db, seller, buyer):
    listing = published(db, seller, physical())
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id)
    m.apply_custodian_event(db, order, event_type="FUNDED", external_event_id=f"f-{order.id}", custodian_reference=f"C-{order.id}")
    db.commit()
    return order


def test_buyer_requests_go_to_support_and_money_actions_need_process_cashouts(client, market, custodian):
    db = market
    seller, buyer, stranger = _member(db, "rq-seller"), _member(db, "rq-buyer"), _member(db, "rq-stranger")
    finance = _member(db, "rq-finance", admin=True, permissions=("process_cashouts",))
    moderator = _member(db, "rq-mod", admin=True, permissions=("moderate_content",))
    order = _paid_order(db, seller, buyer)
    url = f"{API}/orders/{order.id}/requests"
    body = {"kind": "REFUND", "reason": "The seller stopped answering my messages."}
    assert client.post(url, json=body, headers=bearer(stranger)).status_code == 404
    assert client.post(url, json=body, headers=bearer(seller)).status_code == 409        # buyer only
    r = client.post(url, json=body, headers=bearer(buyer))
    assert r.status_code == 201 and r.json()["open_request"]["status"] == "OPEN"
    assert client.post(url, json=body, headers=bearer(buyer)).status_code == 409         # one open request
    listed = client.get(f"{ADMIN}/requests", headers=bearer(moderator)).json()
    assert [x["order_id"] for x in listed] == [order.id]
    decline = f"{BM}/orders/{order.id}/requests/decline"
    assert client.post(decline, json={"note": "Seller confirmed shipping", "current_password": PASSWORD},
                       headers=bearer(moderator)).status_code == 403                      # not a finance permission
    refund = f"{BM}/orders/{order.id}/refund"
    rbody = {"reason": "NON_HANDOVER", "note": "Seller did not hand over", "current_password": "wrong"}
    assert client.post(refund, json=rbody, headers=bearer(finance)).status_code == 403
    r = client.post(refund, json={**rbody, "current_password": PASSWORD}, headers=bearer(finance))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == m.REFUND_PENDING and r.json()["open_request"] is None
    req = db.query(MarketOrderRequest).one()
    assert (req.status, req.resolution) == ("RESOLVED", "REFUNDED")
    assert ("refund", order.id) in custodian.calls                                        # asked, never booked here
    # a second refund is refused by the order state
    assert client.post(refund, json={**rbody, "current_password": PASSWORD}, headers=bearer(finance)).status_code == 409
    # an administrator who is party to an order cannot act on it
    own = _paid_order(db, finance, buyer)
    assert client.post(f"{BM}/orders/{own.id}/refund", json={**rbody, "current_password": PASSWORD},
                       headers=bearer(finance)).status_code == 403


def test_a_declined_request_is_recorded_and_unpaid_orders_are_cancelled_directly(client, market, custodian):
    db = market
    seller, buyer = _member(db, "dc-seller"), _member(db, "dc-buyer")
    finance = _member(db, "dc-finance", admin=True, permissions=("process_cashouts",))
    order = _paid_order(db, seller, buyer)
    m.open_request(db, order, buyer_user_id=buyer.id, kind="CANCELLATION", reason="I ordered the wrong size, sorry.")
    db.commit()
    r = client.post(f"{BM}/orders/{order.id}/requests/decline",
                    json={"note": "Already handed over to the courier", "current_password": PASSWORD}, headers=bearer(finance))
    assert r.status_code == 200 and r.json()["state"] == m.FUNDS_HELD                    # nothing moved
    assert db.query(MarketOrderRequest).one().resolution == "DECLINED"
    listing = published(db, seller, physical(title="Unpaid"))
    unpaid = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id)
    with pytest.raises(m.MarketplaceError, match="cancel it directly"):
        m.open_request(db, unpaid, buyer_user_id=buyer.id, kind="CANCELLATION", reason="Changed my mind entirely.")


# ---------------------------------------------------------------- seller verification and summary

def test_a_reviewer_cannot_decide_their_own_seller_application(market):
    db = market
    user = _user(db, "self@t.com")
    from app.models.seller_verification import SellerApplication

    app = SellerApplication(user_id=user.id, status="MANUAL_REVIEW_REQUIRED", seller_category="PRIVATE")
    db.add(app)
    db.flush()
    with pytest.raises(sv.SellerError, match="own seller application"):
        sv.admin_decide(db, app, admin_user_id=user.id, action="approve", reason="Looks fine to me")
    assert app.status == "MANUAL_REVIEW_REQUIRED"


def test_seller_summary_is_custodian_held_never_a_balance(client, market, custodian):
    db = market
    seller, buyer = _member(db, "sum-seller"), _member(db, "sum-buyer")
    _paid_order(db, seller, buyer)
    r = client.get(f"{API}/seller/summary", headers=bearer(seller)).json()
    assert r["held_by_custodian_usd"] == "25.00" and r["paid_by_custodian_usd"] == "0.00"
    assert "not part of your MyHigh5 balance" in r["note"]
    assert client.get(f"{API}/seller/summary", headers=bearer(buyer)).json()["held_by_custodian_usd"] == "0.00"


# ---------------------------------------------------------------- reconciliation

def test_reconciliation_is_read_only_clean_then_finds_a_tampered_order(market, custodian):
    db = market
    seller, buyer = _user(db, "rc-s@t.com"), _user(db, "rc-b@t.com")
    order = _paid_order(db, seller, buyer)
    first = recon.report(db)
    assert first["ok"] and first["read_only"] and first["counts"]["orders_by_state"] == {"FUNDS_HELD": 1}
    assert recon.report(db)["fingerprint"] == first["fingerprint"]
    order.buyer_total_amount = Decimal("31.00")                                            # tamper (synthetic)
    db.flush()
    types = {i["type"] for i in recon.report(db)["issues"]}
    assert {"ORDER_TOTAL_MISMATCH", "FUNDED_ENTRY_MISMATCH"} <= types
    assert all(not i["auto_fix_safe"] for i in recon.report(db)["issues"])
