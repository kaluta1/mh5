"""Marketplace listings (physical, service, digital), disclosures, order snapshot, stock, payment
initiation and the e-book download that finalises a purchase. SYNTHETIC; the custodian is a recorder."""
from __future__ import annotations

import io
from decimal import Decimal

import pytest

import main

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.business_model import MarketListing, MarketOrderEvent
from app.services import marketplace_listings as ml
from app.services import marketplace_service as m
from tests.unit.test_email2_auth_security import PW, bearer, ip, login  # noqa: F401  (ip is a fixture)
from tests.unit.test_new_business_model import (  # noqa: F401  (fixtures)
    FakeCustodian, _assert_all_journals_balance, _user, custodian, world,
)

pytestmark = pytest.mark.unit
API = "/api/v1/marketplace"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_STORAGE_DIR", str(tmp_path / "private"))
    return tmp_path / "private"


def physical(**over):
    data = {"kind": "PHYSICAL", "title": "Hand-made basket", "description": "Woven sisal basket, 40 cm.",
            "price_usd": "25.00", "quantity_available": 2, "handover_details": "Collection in Arusha or courier."}
    data.update(over)
    return data


def ebook(**over):
    data = {"kind": "DIGITAL", "title": "Swahili for beginners", "description": "A 120-page PDF course book.",
            "price_usd": "10.00"}
    data.update(over)
    return data


def published(db, seller, data, *, file=b"%PDF-1.4 test"):
    listing = ml.create_listing(db, seller_user_id=seller.id, data=data)
    if listing.kind == ml.DIGITAL:
        ml.store_file(db, listing, seller_user_id=seller.id, filename="book.pdf", stream=io.BytesIO(file))
    return ml.publish(db, listing, seller_user_id=seller.id)


def test_listing_validation_and_disclosures(world, storage):
    db = world
    seller = _user(db, "ls@t.com")
    with pytest.raises(ml.ListingError, match="warranty_terms"):
        ml.create_listing(db, seller_user_id=seller.id, data=physical(warranty_available=True))
    with pytest.raises(ml.ListingError, match="Only a physical product"):
        ml.create_listing(db, seller_user_id=seller.id, data=ebook(quantity_available=3))
    with pytest.raises(ml.ListingError, match="price_usd"):
        ml.create_listing(db, seller_user_id=seller.id, data=physical(price_usd="0"))
    plain = ml.create_listing(db, seller_user_id=seller.id, data=physical(insurance_terms="ignored when not offered"))
    assert plain.status == ml.DRAFT and plain.insurance_terms is None
    d = ml.disclosures(plain)
    assert d["warranty"] == ml.WARRANTY_NONE and d["insurance"] == ml.INSURANCE_NONE and "statutory" in d["consumer_rights"]
    covered = ml.create_listing(db, seller_user_id=seller.id, data=physical(
        warranty_available=True, warranty_terms="12 months against weaving defects",
        insurance_available=True, insurance_terms="Courier insurance up to the price paid"))
    d = ml.disclosures(covered)
    assert d["warranty"].startswith("Warranty available: 12 months") and d["insurance"].startswith("Insurance available:")


def test_only_the_seller_edits_and_publishing_needs_handover_or_file(world, storage):
    db = world
    seller, other = _user(db, "ps@t.com"), _user(db, "po@t.com")
    service = ml.create_listing(db, seller_user_id=seller.id, data={
        "kind": "SERVICE", "title": "Logo design", "description": "Three logo concepts in two days.", "price_usd": "40"})
    with pytest.raises(LookupError):
        ml.update_listing(db, service, seller_user_id=other.id, data={"price_usd": "1"})
    with pytest.raises(LookupError):
        ml.publish(db, service, seller_user_id=other.id)
    with pytest.raises(ml.ListingError, match="handed over"):
        ml.publish(db, service, seller_user_id=seller.id)
    ml.update_listing(db, service, seller_user_id=seller.id, data={"handover_details": "Files sent by message."})
    assert ml.publish(db, service, seller_user_id=seller.id).status == ml.PUBLISHED
    book = ml.create_listing(db, seller_user_id=seller.id, data=ebook())
    with pytest.raises(ml.ListingError, match="Upload the digital file"):
        ml.publish(db, book, seller_user_id=seller.id)
    with pytest.raises(ml.ListingError, match="must be one of"):
        ml.store_file(db, book, seller_user_id=seller.id, filename="book.exe", stream=io.BytesIO(b"x"))
    ml.store_file(db, book, seller_user_id=seller.id, filename="../../book.pdf", stream=io.BytesIO(b"%PDF"))
    assert book.file_name == "book.pdf" and len(book.file_sha256) == 64 and book.file_size == 4
    assert ml.file_path(book).startswith(str(storage))
    with pytest.raises(ml.ListingError, match="cannot be published"):
        ml.update_listing(db, book, seller_user_id=seller.id, data={"description": "Buy cocaine here, cheap."})
        ml.publish(db, book, seller_user_id=seller.id)
    ml.unpublish(db, service, seller_user_id=seller.id)
    assert service.status == ml.UNPUBLISHED and not ml.is_buyable(service)


def test_an_order_keeps_its_snapshot_and_reserves_physical_stock(world, custodian, storage):
    db = world
    seller, buyer = _user(db, "ss@t.com"), _user(db, "sb@t.com")
    listing = published(db, seller, physical(quantity_available=1))
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=listing.id)
    assert (order.seller_base_amount, order.markup_amount, order.buyer_total_amount) == (
        Decimal("25.00"), Decimal("5.00"), Decimal("30.00"))
    assert order.listing_snapshot["warranty"] == ml.WARRANTY_NONE and order.listing_snapshot["title"] == "Hand-made basket"
    assert listing.quantity_available == 0 and not ml.is_buyable(listing)
    with pytest.raises(m.MarketplaceError, match="not available"):
        m.create_order(db, buyer_user_id=_user(db, "sb2@t.com").id, item_type="listing", item_id=listing.id)
    ml.update_listing(db, listing, seller_user_id=seller.id, data={"title": "Renamed basket"})
    assert order.listing_snapshot["title"] == "Hand-made basket"          # edits never change an order
    m.cancel_unpaid(db, order, actor_user_id=buyer.id)
    assert listing.quantity_available == 1                                # unit given back
    with pytest.raises(m.MarketplaceError, match="cannot buy your own"):
        m.create_order(db, buyer_user_id=seller.id, item_type="listing", item_id=listing.id)


def test_payment_initiation_is_not_payment(world, custodian, storage):
    db = world
    seller, buyer = _user(db, "is@t.com"), _user(db, "ib@t.com")
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=published(db, seller, physical()).id)
    with pytest.raises(m.MarketplaceError, match="Only the buyer"):
        m.initiate_payment(db, order, buyer_user_id=seller.id)
    m.initiate_payment(db, order, buyer_user_id=buyer.id)
    assert order.state == m.PAYMENT_PENDING and ("hold", order.id) in custodian.calls
    with pytest.raises(m.MarketplaceError, match="cannot be confirmed"):
        m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=m.ACCEPTANCE_POLICY_VERSION)


def test_without_a_custodian_payment_initiation_refuses(world, storage):
    db = world
    seller, buyer = _user(db, "ns@t.com"), _user(db, "nb@t.com")
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=published(db, seller, physical()).id)
    with pytest.raises(m.CustodianNotConfigured):
        m.initiate_payment(db, order, buyer_user_id=buyer.id)
    assert order.state == m.PAYMENT_PENDING


def test_a_complete_download_finalises_the_ebook_once(world, custodian, storage):
    db = world
    seller, buyer, stranger = _user(db, "es@t.com"), _user(db, "eb@t.com"), _user(db, "ex@t.com")
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="listing", item_id=published(db, seller, ebook()).id)
    assert not m.can_download(order, buyer.id)                            # unpaid
    m.apply_custodian_event(db, order, event_type="FUNDED", external_event_id="eb-1", custodian_reference="EB-1")
    assert m.can_download(order, buyer.id) and not m.can_download(order, stranger.id) and not m.can_download(order, seller.id)
    assert m.record_digital_download(db, order, buyer_user_id=buyer.id) is True
    assert order.state == m.RELEASE_PENDING and order.acceptance_reference.startswith(f"DLV-{order.id}-")
    assert order.acceptance_policy_version == m.DIGITAL_DELIVERY_POLICY and order.digital_delivered_at
    assert m.record_digital_download(db, order, buyer_user_id=buyer.id) is False      # idempotent
    assert custodian.calls.count(("release", order.id)) == 1
    assert db.query(MarketOrderEvent).filter_by(order_id=order.id, to_state=m.BUYER_CONFIRMED).count() == 1
    assert m.can_download(order, buyer.id)                                # re-download stays available
    m.apply_custodian_event(db, order, event_type="RELEASED", external_event_id="eb-2")
    _assert_all_journals_balance(db)


def _api_users(db, client):
    seller, buyer = _user(db, "api-ls@t.com"), _user(db, "api-lb@t.com")
    for u in (seller, buyer):
        u.hashed_password, u.email_verified = get_password_hash(PW), True
    db.commit()
    return (seller, bearer(login(client, seller).json()["access_token"]),
            buyer, bearer(login(client, buyer).json()["access_token"]))


def test_api_is_closed_while_the_marketplace_is_off(client, world, ip, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", False)
    assert client.get(f"{API}/status").json() == {
        "enabled": False, "checkout_available": False, "acceptance_policy_version": m.ACCEPTANCE_POLICY_VERSION}
    closed = {"code": "MARKETPLACE_CLOSED", "message": "The marketplace is not open yet."}
    monkeypatch.setattr(main, "IS_PRODUCTION", True)               # production masks every other 5xx detail
    for path in ("/listings", "/listings/1"):                       # public; /my-listings needs sign-in (401) first
        answer = client.get(f"{API}{path}")
        assert answer.status_code == 503 and answer.json()["detail"] == closed, path
    seller, s, _buyer, b = _api_users(world, client)
    for headers in (s, b):                                         # signed-in seller and buyer get the same answer
        assert client.get(f"{API}/listings", headers=headers).json()["detail"] == closed
        assert client.post(f"{API}/listings", headers=headers, json=ebook()).json()["detail"] == closed
        assert client.get(f"{API}/my-listings", headers=headers).json()["detail"] == closed


def test_api_listing_lifecycle_checkout_gate_and_download(client, world, custodian, storage, ip, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", True)
    seller, s, buyer, b = _api_users(db, client)
    assert client.post(f"{API}/listings", json=ebook()).status_code == 401
    created = client.post(f"{API}/listings", headers=s, json=ebook())
    assert created.status_code == 201 and created.json()["status"] == "DRAFT"
    lid = created.json()["id"]
    assert client.get(f"{API}/listings/{lid}").status_code == 404                       # drafts are private
    assert client.patch(f"{API}/listings/{lid}", headers=b, json={"price_usd": "1"}).status_code == 404
    assert client.post(f"{API}/listings/{lid}/publish", headers=s).status_code == 422     # no file yet
    up = client.put(f"{API}/listings/{lid}/file", headers=s, files={"file": ("course.pdf", b"%PDF-1.4 book", "application/pdf")})
    assert up.status_code == 200 and up.json()["file_name"] == "course.pdf"
    assert client.put(f"{API}/listings/{lid}/file", headers=b, files={"file": ("x.pdf", b"x")}).status_code == 404
    assert client.post(f"{API}/listings/{lid}/publish", headers=s).json()["status"] == "PUBLISHED"
    public = client.get(f"{API}/listings/{lid}").json()
    assert public["buyer_price_usd"] == "12.00" and "file_name" not in public and "status" not in public
    assert public["disclosures"]["warranty"] == ml.WARRANTY_NONE
    assert [x["id"] for x in client.get(f"{API}/listings", params={"kind": "DIGITAL", "q": "swahili"}).json()] == [lid]
    assert client.get(f"{API}/listings/{lid}/file", headers=s).content == b"%PDF-1.4 book"   # seller check, finalises nothing

    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", "")                            # no custodian: no checkout
    assert client.post(f"{API}/orders", headers=b, json={"item_type": "listing", "item_id": lid}).status_code == 503
    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", custodian.name)
    order = client.post(f"{API}/orders", headers=b, json={"item_type": "listing", "item_id": lid}).json()
    assert order["state"] == "PAYMENT_PENDING" and order["listing"]["title"] == "Swahili for beginners"
    assert client.get(f"{API}/orders/{order['id']}/download", headers=b).status_code == 404   # unpaid
    assert client.post(f"{API}/orders/{order['id']}/pay", headers=b).json()["state"] == "PAYMENT_PENDING"

    row = db.get(m.MarketOrder, order["id"])
    m.apply_custodian_event(db, row, event_type="FUNDED", external_event_id="api-eb", custodian_reference="API-EB")
    db.commit()
    assert client.get(f"{API}/orders/{order['id']}/download", headers=s).status_code == 404   # the seller is not the buyer
    got = client.get(f"{API}/orders/{order['id']}/download", headers=b)
    assert got.status_code == 200 and got.content == b"%PDF-1.4 book" and got.headers["cache-control"] == "no-store"
    db.expire_all()
    row = db.get(m.MarketOrder, order["id"])
    assert row.state == m.RELEASE_PENDING and row.acceptance_reference.startswith("DLV-") and row.digital_delivered_at
    assert custodian.calls.count(("release", row.id)) == 1
    client.get(f"{API}/orders/{order['id']}/download", headers=b)
    assert custodian.calls.count(("release", row.id)) == 1
    mine = {o["id"]: o for o in client.get(f"{API}/orders", headers=s).json()}[row.id]
    assert mine["acceptance_status"] == "ACCEPTED" and mine["settlement_status"] == "SETTLEMENT_PENDING"
    assert db.query(MarketListing).count() == 1
