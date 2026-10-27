"""Marketplace buyer acceptance, seller verification, settlement initiation, retired disputes and
support refunds (client requirements 2026-10-28). SYNTHETIC; the custodian is a recorder (no money)."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.affiliate import AffiliateCommission
from app.models.business_model import MarketOrder, MarketOrderEvent
from app.services import marketplace_service as m
from tests.unit.test_email2_auth_security import PW, bearer, ip, login  # noqa: F401  (ip is a fixture)
from tests.unit.test_new_business_model import (  # noqa: F401  (fixtures)
    FakeCustodian, _assert_all_journals_balance, _balance, _listing, _user, custodian, world,
)

pytestmark = pytest.mark.unit
POLICY = m.ACCEPTANCE_POLICY_VERSION


def funded(db, *, sponsor=None, tag="a"):
    buyer = _user(db, f"buyer-{tag}@t.com", sponsor=sponsor)
    seller = _user(db, f"seller-{tag}@t.com")
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="digital_product", item_id=_listing(db, seller).id)
    m.apply_custodian_event(db, order, event_type="FUNDED", external_event_id=f"fund-{tag}", custodian_reference=f"C-{tag}")
    return buyer, seller, order


def events(db, order, to_state):
    return db.query(MarketOrderEvent).filter_by(order_id=order.id, to_state=to_state).count()


def test_only_the_buyer_accepts_and_only_deliberately(world, custodian):
    db = world
    buyer, seller, order = funded(db)
    admin = _user(db, "admin-x@t.com")
    admin.is_admin = True
    for someone in (seller, admin):                                  # seller, courier/admin: never
        with pytest.raises(m.MarketplaceError, match="Only the buyer"):
            m.confirm_receipt(db, order, buyer_user_id=someone.id, policy_version=POLICY)
    for wrong in (None, "", "OLD-POLICY"):                           # the current terms, acknowledged
        with pytest.raises(m.MarketplaceError, match="acknowledge"):
            m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=wrong)
    assert order.state == m.FUNDS_HELD and order.acceptance_reference is None
    ref = m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=POLICY)   # product in hand
    assert ref.startswith(f"ACC-{order.id}-") and order.acceptance_reference == ref
    assert order.confirmed_at is not None and order.acceptance_policy_version == POLICY
    assert order.state == m.RELEASE_PENDING and custodian.calls.count(("release", order.id)) == 1


def test_a_repeated_acceptance_changes_nothing(world, custodian):
    db = world
    buyer, _seller, order = funded(db)
    first = m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=POLICY)
    again = m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=POLICY)
    assert first == again and events(db, order, m.BUYER_CONFIRMED) == 1
    assert custodian.calls.count(("release", order.id)) == 1


def test_unpaid_or_cancelled_orders_cannot_be_accepted(world, custodian):
    db = world
    buyer, seller = _user(db, "ub@t.com"), _user(db, "us@t.com")
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="digital_product", item_id=_listing(db, seller).id)
    with pytest.raises(m.MarketplaceError, match="cannot be confirmed"):
        m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=POLICY)
    m.cancel_unpaid(db, order, actor_user_id=buyer.id)
    with pytest.raises(m.MarketplaceError, match="cannot be confirmed"):
        m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=POLICY)


def test_a_sellers_delivered_mark_is_not_an_acceptance_and_the_seller_verifies_before_handover(world, custodian):
    db = world
    buyer, seller, order = funded(db)
    m.mark_fulfilled(db, order, seller_user_id=seller.id)
    status = m.handover_status(order)
    assert status["acceptance_status"] == "NOT_ACCEPTED" and status["handover_instruction"] == m.AWAITING_ACCEPTANCE
    assert status["settlement_status"] == "NOT_STARTED" and ("release", order.id) not in custodian.calls
    with pytest.raises(m.MarketplaceError, match="Awaiting buyer confirmation"):
        m.seller_verify_acceptance(db, order, seller_user_id=seller.id)
    ref = m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=POLICY)
    with pytest.raises(m.MarketplaceError, match="Only the seller"):
        m.seller_verify_acceptance(db, order, seller_user_id=buyer.id)
    verified = m.seller_verify_acceptance(db, order, seller_user_id=seller.id)
    assert m.seller_verify_acceptance(db, order, seller_user_id=seller.id) == verified      # once
    status = m.handover_status(order)
    assert (status["acceptance_reference"], status["handover_instruction"]) == (ref, m.ACCEPTANCE_VERIFIED)
    assert status["seller_verified_at"] and status["settlement_status"] == "SETTLEMENT_PENDING"


def test_a_provider_failure_never_undoes_the_acceptance_and_money_moves_once(world, custodian, monkeypatch):
    db = world
    sponsor = _user(db, "sp-r@t.com")
    buyer, _seller, order = funded(db, sponsor=sponsor, tag="r")

    def timeout(order):
        raise TimeoutError("custodian did not answer")
    answering = custodian.request_release
    custodian.request_release = timeout
    ref = m.confirm_receipt(db, order, buyer_user_id=buyer.id, policy_version=POLICY)
    db.commit()
    assert order.acceptance_reference == ref and order.state == m.RELEASE_PENDING
    assert m.handover_status(order)["settlement_status"] == "SETTLEMENT_RETRY_NEEDED"
    assert _balance(db, "2121") != 0 and db.query(AffiliateCommission).count() == 0          # nobody paid yet

    custodian.request_release = answering                             # the custodian answers again
    assert m.request_settlement(db, order) is True and order.release_request_error is None
    assert m.apply_custodian_event(db, order, event_type="RELEASED", external_event_id="rel-r") is True
    assert m.apply_custodian_event(db, order, event_type="RELEASED", external_event_id="rel-r") is False   # duplicate
    db.commit()
    assert m.handover_status(order)["settlement_status"] == "SETTLED"
    assert db.query(AffiliateCommission).count() == 1 and _balance(db, "2121") == 0
    _assert_all_journals_balance(db)
    with pytest.raises(m.MarketplaceError):
        m.request_settlement(db, order)                               # a settled order is never asked again


def test_disputes_are_retired_and_support_refunds_only_before_acceptance(world, custodian):
    db = world
    buyer, seller, order = funded(db, tag="d")
    with pytest.raises(m.MarketplaceError, match="no longer available"):
        m.open_dispute(db, order, user_id=buyer.id, reason="Not as described")
    with pytest.raises(m.MarketplaceError, match="reason must be"):
        m.support_refund(db, order, admin_user_id=seller.id, reason="CHANGED_MIND", note="x" * 6)
    accepted_buyer, accepted_seller, accepted = funded(db, tag="d2")
    m.confirm_receipt(db, accepted, buyer_user_id=accepted_buyer.id, policy_version=POLICY)
    with pytest.raises(m.MarketplaceError, match="not accepted or released"):
        m.support_refund(db, accepted, admin_user_id=accepted_seller.id, reason="NON_HANDOVER", note="claim")
    m.support_refund(db, order, admin_user_id=seller.id, reason="DUPLICATE_CHARGE", note="Charged twice")
    assert order.state == m.REFUND_PENDING and order.support_reason == "DUPLICATE_CHARGE"
    assert ("refund", order.id) in custodian.calls and ("release", order.id) not in custodian.calls
    assert not hasattr(m, "resolve_dispute")                          # no admin release on the buyer's behalf


def test_the_api_requires_an_explicit_acknowledgement_and_shows_separate_statuses(client, world, custodian, ip, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "MARKETPLACE_ENABLED", True)
    from app.core.security import get_password_hash

    buyer, seller = _user(db, "api-buyer@t.com"), _user(db, "api-seller@t.com")
    for u in (buyer, seller):
        u.hashed_password, u.email_verified = get_password_hash(PW), True
    order = m.create_order(db, buyer_user_id=buyer.id, item_type="digital_product", item_id=_listing(db, seller).id)
    m.apply_custodian_event(db, order, event_type="FUNDED", external_event_id="api-1", custodian_reference="API-1")
    db.commit()
    b = bearer(login(client, buyer).json()["access_token"])
    s = bearer(login(client, seller).json()["access_token"])
    base = "/api/v1/marketplace"
    policy = client.get(f"{base}/acceptance-policy").json()["policy_version"]
    assert policy == POLICY
    assert client.post(f"{base}/orders/{order.id}/accept", headers=b, json={"policy_version": policy}).status_code == 422
    assert client.post(f"{base}/orders/{order.id}/accept", headers=s,
                       json={"policy_version": policy, "acknowledge": True}).status_code == 409   # seller refused
    seller_view = client.post(f"{base}/orders/{order.id}/verify", headers=s)
    assert seller_view.status_code == 409 and "Awaiting buyer confirmation" in seller_view.text
    r = client.post(f"{base}/orders/{order.id}/accept", headers=b, json={"policy_version": policy, "acknowledge": True})
    assert r.status_code == 200 and r.json()["acceptance_status"] == "ACCEPTED"
    listed = {o["id"]: o for o in client.get(f"{base}/orders", headers=s).json()}[order.id]
    assert listed["acceptance_reference"] == r.json()["acceptance_reference"]
    assert listed["handover_instruction"] == m.ACCEPTANCE_VERIFIED and listed["settlement_status"] == "SETTLEMENT_PENDING"
    assert client.post(f"{base}/orders/{order.id}/verify", headers=s).json()["seller_verified_at"]
    for gone in (f"{base}/orders/{order.id}/dispute", f"{base}/orders/{order.id}/confirm"):
        assert client.post(gone, headers=b, json={"reason": "something wrong"}).status_code in (404, 405, 422)
