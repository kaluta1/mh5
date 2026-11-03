"""Prompt 7 marketplace on real PostgreSQL: concurrent orders on the last unit, a repeated checkout from
several threads, duplicate custodian confirmations, concurrent moderation, concurrent buyer requests,
concurrent refunds, a seller approval race, rollback, and migration c2e4a6b8d0f1.

Opt-in: RUN_POSTGRES_TESTS=1. One disposable database per test. Everything is SYNTHETIC; the custodian is a
recorder that never moves money."""
from __future__ import annotations

import io
import os
import uuid

import pytest
from sqlalchemy import func, text

from app.core.config import settings
from app.models.accounting import JournalEntry
from app.models.business_model import MarketListing, MarketOrder, MarketOrderRequest
from app.models.seller_verification import SellerApplication
from app.services import marketplace_listings as ml
from app.services import marketplace_reconciliation as recon
from app.services import marketplace_service as m
from app.services import seller_verification as sv
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401
from tests.integration.test_referral_pool_units_postgres import member, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]


class Recorder:
    name = "PG_TEST_CUSTODIAN"

    def create_hold(self, order):
        return {}

    def request_release(self, order):
        return None

    def request_refund(self, order):
        return None


@pytest.fixture(autouse=True)
def custodian(monkeypatch, tmp_path):
    m.register_custodian(Recorder())
    monkeypatch.setattr(settings, "MARKETPLACE_CUSTODIAN", Recorder.name)
    monkeypatch.setattr(settings, "MARKETPLACE_STORAGE_DIR", str(tmp_path / "private"))


def listing(Session, seller_id: int, quantity=1) -> int:
    with Session() as db:
        row = ml.create_listing(db, seller_user_id=seller_id, data={
            "kind": "PHYSICAL", "title": "Hand-made basket", "description": "Woven sisal basket, 40 cm.",
            "price_usd": "25.00", "quantity_available": quantity, "handover_details": "Courier."})
        ml.publish(db, row, seller_user_id=seller_id)
        db.commit()
        return row.id


def order(Session, buyer_id: int, listing_id: int, ref=None):
    with Session() as db:
        try:
            o = m.create_order(db, buyer_user_id=buyer_id, item_type="listing", item_id=listing_id, client_reference=ref)
            db.commit()
            return ("ok", o.id)
        except m.MarketplaceError as exc:
            db.rollback()
            return ("refused", str(exc))


def funded(Session, order_id: int, event_id: str):
    with Session() as db:
        o = db.query(MarketOrder).filter(MarketOrder.id == order_id).with_for_update().first()
        try:
            applied = m.apply_custodian_event(db, o, event_type="FUNDED", external_event_id=event_id,
                                              custodian_reference=f"C-{order_id}", amount="30.00", currency="USD")
            db.commit()
            return applied
        except Exception as exc:  # noqa: BLE001 - unique-index loser
            db.rollback()
            return type(exc).__name__


def test_concurrent_buyers_cannot_oversell_the_last_unit(world):
    _engine, Session = world
    seller = member(Session)
    item = listing(Session, seller, quantity=1)
    buyers = [member(Session) for _ in range(6)]
    results = in_threads(6, lambda i: order(Session, buyers[i], item))
    assert sum(1 for r in results if r[0] == "ok") == 1
    with Session() as db:
        assert db.get(MarketListing, item).quantity_available == 0
        assert db.query(func.count(MarketOrder.id)).scalar() == 1


def test_a_checkout_repeated_from_many_threads_makes_one_order(world):
    _engine, Session = world
    seller, buyer = member(Session), member(Session)
    item = listing(Session, seller, quantity=10)
    results = in_threads(5, lambda i: order(Session, buyer, item, ref="dbl-click-01"))
    ids = {r[1] for r in results if isinstance(r, tuple) and r[0] == "ok"}
    with Session() as db:
        count = db.query(func.count(MarketOrder.id)).scalar()
        quantity = db.get(MarketListing, item).quantity_available
    assert count == 1 and quantity == 9 and len(ids) <= 1
    # a loser may hit the unique index (the API returns the winner's order); none created a second order
    assert all(isinstance(r, tuple) or "IntegrityError" in type(r).__name__ for r in results)


def test_duplicate_custodian_confirmations_book_once(world):
    _engine, Session = world
    seller, buyer = member(Session), member(Session)
    _, oid = order(Session, buyer, listing(Session, seller))
    results = in_threads(5, lambda i: funded(Session, oid, "ev-dup-1"))
    assert results.count(True) == 1
    with Session() as db:
        assert db.get(MarketOrder, oid).state == m.FUNDS_HELD
        assert db.query(func.count(JournalEntry.id)).filter(JournalEntry.description.like(f"%order {oid} funded%")).scalar() == 1
        assert recon.report(db, check_files=False)["ok"]


def test_concurrent_moderation_suspends_once(world):
    _engine, Session = world
    seller = member(Session)
    item = listing(Session, seller)
    admins = [member(Session) for _ in range(4)]

    def suspend(i):
        with Session() as db:
            row = db.query(MarketListing).filter(MarketListing.id == item).with_for_update().first()
            try:
                ml.moderate(db, row, admin_user_id=admins[i], action="suspend", reason="Report received",
                            seller_message="Please contact support")
                db.commit()
                return "ok"
            except ml.ListingError:
                db.rollback()
                return "refused"
    assert sorted(in_threads(4, suspend)) == ["ok", "refused", "refused", "refused"]
    with Session() as db:
        assert db.execute(text("SELECT count(*) FROM market_listing_events WHERE action = 'SUSPEND'")).scalar() == 1


def test_concurrent_buyer_requests_and_refunds_happen_once(world):
    _engine, Session = world
    seller, buyer = member(Session), member(Session)
    _, oid = order(Session, buyer, listing(Session, seller))
    assert funded(Session, oid, "ev-paid") is True

    def ask(i):
        with Session() as db:
            o = db.query(MarketOrder).filter(MarketOrder.id == oid).with_for_update().first()
            try:
                m.open_request(db, o, buyer_user_id=buyer, kind="REFUND", reason="Not handed over after a week.")
                db.commit()
                return "ok"
            except Exception:  # noqa: BLE001
                db.rollback()
                return "refused"
    assert in_threads(4, ask).count("ok") == 1
    admins = [member(Session) for _ in range(3)]

    def refund(i):
        with Session() as db:
            o = db.query(MarketOrder).filter(MarketOrder.id == oid).with_for_update().first()
            try:
                m.support_refund(db, o, admin_user_id=admins[i], reason="NON_HANDOVER", note="Seller unreachable")
                db.commit()
                return "ok"
            except m.MarketplaceError:
                db.rollback()
                return "refused"
    assert in_threads(3, refund).count("ok") == 1
    with Session() as db:
        assert db.get(MarketOrder, oid).state == m.REFUND_PENDING
        assert [(r.status, r.resolution) for r in db.query(MarketOrderRequest).all()] == [("RESOLVED", "REFUNDED")]


def test_seller_approval_race_approves_once(world):
    _engine, Session = world
    applicant = member(Session)
    reviewers = [member(Session) for _ in range(3)]
    with Session() as db:
        app = SellerApplication(user_id=applicant, status="MANUAL_REVIEW_REQUIRED", seller_category="PRIVATE")
        db.add(app)
        db.commit()
        app_id = app.id

    def approve(i):
        with Session() as db:
            row = db.query(SellerApplication).filter(SellerApplication.id == app_id).with_for_update().first()
            try:
                sv.admin_decide(db, row, admin_user_id=reviewers[i], action="approve", reason="Documents checked")
                db.commit()
                return "ok"
            except sv.SellerError:
                db.rollback()
                return "refused"
    assert sorted(in_threads(3, approve)) == ["ok", "refused", "refused"]
    with Session() as db:
        assert db.execute(text("SELECT count(*) FROM seller_application_events WHERE to_status = 'APPROVED'")).scalar() == 1


def test_a_failed_transaction_leaves_nothing_behind(world):
    _engine, Session = world
    seller, buyer = member(Session), member(Session)
    item = listing(Session, seller, quantity=2)
    with Session() as db:
        m.create_order(db, buyer_user_id=buyer, item_type="listing", item_id=item)
        db.rollback()                                   # e.g. the request failed after creating the order
    with Session() as db:
        assert db.query(func.count(MarketOrder.id)).scalar() == 0
        assert db.get(MarketListing, item).quantity_available == 2


def test_migration_is_additive_and_reversible(world):
    engine, Session = world
    migration = "c2e4a6b8d0f1_marketplace_completion.py"
    with engine.begin() as c:
        for table in ("market_order_requests", "market_listing_images", "market_listing_events"):
            c.execute(text(f"DROP TABLE {table}"))
        c.execute(text("ALTER TABLE market_orders DROP CONSTRAINT uq_market_orders_buyer_client_ref"))
        c.execute(text("ALTER TABLE market_orders DROP COLUMN client_reference"))
        c.execute(text("ALTER TABLE market_listings DROP CONSTRAINT ck_market_listings_condition"))
        c.execute(text("ALTER TABLE market_listings DROP CONSTRAINT ck_market_listings_status"))
        c.execute(text("ALTER TABLE market_listings ADD CONSTRAINT ck_market_listings_status "
                       "CHECK (status IN ('DRAFT', 'PUBLISHED', 'UNPUBLISHED'))"))
        for col in ("category", "item_condition", "moderation_note"):
            c.execute(text(f"ALTER TABLE market_listings DROP COLUMN {col}"))
    seller, buyer = member(Session), member(Session)
    with engine.begin() as c:                            # an existing listing and order (old shape)
        lid = c.execute(text("INSERT INTO market_listings (created_at, updated_at, seller_user_id, kind, title, description, "
                             "price_usd, status, warranty_available, insurance_available) VALUES (now(), now(), :s, "
                             "'SERVICE', 'Old', 'Old service listing', 10, 'PUBLISHED', false, false) RETURNING id"),
                        {"s": seller}).scalar()
    migrate(engine, migration, "upgrade")
    migrate(engine, migration, "downgrade")
    migrate(engine, migration, "upgrade")
    with engine.connect() as c:
        row = c.execute(text("SELECT status, category, item_condition, moderation_note FROM market_listings WHERE id = :i"),
                        {"i": lid}).one()
        assert tuple(row) == ("PUBLISHED", None, None, None)                    # untouched, never re-published
        for table in ("market_order_requests", "market_listing_images", "market_listing_events"):
            assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0
    item = listing(Session, seller)                     # writes a listing event: the downgrade must refuse now
    assert order(Session, buyer, item, ref="after-migration")[0] == "ok"
    with pytest.raises(Exception, match="cannot be dropped"):
        migrate(engine, migration, "downgrade")
