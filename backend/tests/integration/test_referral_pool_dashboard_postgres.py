"""Multi-Unit Referral Pool, P8: member dashboard and administrator views on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC: units come from the
real checkout and the real SoncoPay handler (P7 fixtures), rounds and assignments from the real
allocation engine (P4), refunds from the real signed-event and two-person paths.

What is proved: the totals a member sees are their own and add up; slots are shown apart from
referrals actually received; every list is paginated; financial views need a finance permission
and anti-abuse cases manage_kyc_settings (also through the mounted routes with real tokens); an
administrator-entered refund reference is never labelled provider-verified; nothing switches a
feature on.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.api_v1.endpoints import referral_pool as pool_api
from app.api.deps import get_db
from app.models.accounting import AuditTrail
from app.models.business_model import (
    ReferralPoolConfig, ReferralPoolEvent, ReferralPoolRiskReview, ReferralPoolUnit,
)
from app.models.user import User
from app.services import payment_config
from app.services import referral_pool_allocation as alloc
from app.services import referral_pool_units as units
from tests.integration.test_payments_postgres import pg  # noqa: F401
from tests.integration.test_referral_pool_accounting_postgres import sponsored_buyer
from tests.integration.test_referral_pool_allocation_postgres import NOW, assign, holder, referral, set_allocation
from tests.integration.test_referral_pool_checkout_postgres import (  # noqa: F401  (fixtures)
    checkout, provider_event, purchase_of, set_config, shop,
)
from tests.integration.test_referral_pool_units_postgres import member, world  # noqa: F401
from tests.unit.test_age_gate_registration import auth

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

D = Decimal
REQUEST = type("R", (), {"client": None})()
FINANCE = payment_config.PERMISSION_PROCESS
KYC = "manage_kyc_settings"


@pytest.fixture
def grants(monkeypatch):
    """Explicit permissions per administrator id (nothing implied); re-authentication passes."""
    held: dict = {}
    monkeypatch.setattr(payment_config, "has_permission",
                        lambda user, permission: permission in held.get(getattr(user, "id", None), ()))
    monkeypatch.setattr(payment_config, "require_reauth", lambda actor, password: None)
    return held


def admin(Session) -> int:
    user_id = member(Session)
    with Session() as db:
        db.get(User, user_id).is_admin = True
        db.commit()
    return user_id


def paid(Session, user_id: int, quantity: int) -> int:
    _c, r = checkout(Session, user_id, quantity)
    assert provider_event(Session, r.deposit_id, "paid") == "SYNCED"
    return r.deposit_id


def dashboard(Session, user_id: int) -> dict:
    with Session() as db:
        return pool_api.my_dashboard(db=db, current_user=db.get(User, user_id))


def as_admin(Session, user_id: int, view, **params):
    with Session() as db:
        return view(db=db, current_user=db.get(User, user_id), **params)


# ---------------------------------------------------------------------------
# 1-6, 14. The member dashboard
# ---------------------------------------------------------------------------

def test_member_totals_add_up_and_cover_every_unit_state(shop):
    Session = shop
    buyer, _ = sponsored_buyer(Session)
    first = paid(Session, buyer, 3)
    paid(Session, buyer, 2)
    checkout(Session, buyer, 4)                                                   # started, never paid
    provider_event(Session, first, "partially_refunded", refunded_amount="100.00")  # one unit refunded
    with Session() as db:                                                         # one unit suspended
        unit = db.query(ReferralPoolUnit).filter_by(user_id=buyer, status=units.ACTIVE).first()
        unit.status, unit.suspended_at, unit.status_reason = units.SUSPENDED, NOW, "ADMIN:TEST"
        db.commit()
    view = dashboard(Session, buyer)
    assert view["units"] == {"purchased": 5, "active": 3, "suspended": 1, "refunded": 1, "revoked": 0,
                                  "pending": 0, "waiting_for_next_round": 3}
    assert view["pending_purchases"] == {"count": 1, "units": 4}
    assert view["amounts"] == {"paid": "500.00", "refunded": "100.00", "net_spent": "400.00", "currency": "USD"}
    assert (view["sales_enabled"], view["allocation_enabled"]) == (True, False)
    assert view["current_round"] is None and view["assignments"] == {"round_based": 0, "historical": 0}


def test_slots_in_the_current_round_are_shown_apart_from_referrals_received(shop):
    Session = shop
    set_allocation(Session, True)
    mine, other = holder(Session, 2), holder(Session, 1)
    assign(Session, referral(Session))
    with Session() as db:
        received = db.query(pool_api.ReferralPoolAssignment).filter_by(pool_member_user_id=mine).count()
    view = dashboard(Session, mine)
    current = view["current_round"]
    assert (current["round_number"], current["status"], current["total_slots"]) == (1, "OPEN", 3)
    assert current["filled_slots"] == 1 and current["remaining_slots"] == 2
    assert view["my_slots"]["open"] + view["my_slots"]["filled"] == 2               # one per unit, not promised
    assert view["my_slots"]["filled"] == view["assignments"]["round_based"] == received
    if received:
        assert view["recent_assignments"][0]["round_number"] == 1
        assert set(view["recent_assignments"][0]) == {"id", "assigned_at", "round_number", "kind", "method"}
    add = holder(Session, 1)                                                      # bought during the round
    assert dashboard(Session, add)["units"]["waiting_for_next_round"] == 1
    assert dashboard(Session, other)["units"]["waiting_for_next_round"] == 0


def test_assignment_history_is_paginated_and_holds_no_personal_data(shop):
    Session = shop
    set_allocation(Session, True)
    mine = holder(Session, 1)
    for _ in range(3):                                         # each round of one slot completes and rolls over
        assert assign(Session, referral(Session)).outcome == alloc.ASSIGNED
    with Session() as db:
        first = pool_api.my_assignments(db=db, current_user=db.get(User, mine), page=1, page_size=2)
        second = pool_api.my_assignments(db=db, current_user=db.get(User, mine), page=2, page_size=2)
    assert (first["total"], len(first["items"]), len(second["items"])) == (3, 2, 1)
    assert [a["round_number"] for a in first["items"] + second["items"]] == [3, 2, 1]
    assert all(a["kind"] == "ROUND" and "referred_user_id" not in a for a in first["items"])


def test_a_member_sees_only_their_own_purchases_assignments_and_queue_entry(shop):
    Session = shop
    set_allocation(Session, True)
    mine, theirs = member(Session), holder(Session, 1)
    paid(Session, mine, 1)
    waiting = referral(Session)
    assign(Session, referral(Session))
    view = dashboard(Session, mine)
    assert view["units"]["purchased"] == 1 and view["assignments"]["round_based"] in (0, 1)
    with Session() as db:
        purchases = pool_api.my_purchases(db=db, current_user=db.get(User, mine), page=1, page_size=20)
        assert purchases["total"] == 1 and all(p["quantity"] == 1 for p in purchases["purchases"])
        assert db.query(pool_api.ReferralPoolPurchase).filter_by(user_id=theirs).count() == 1
        theirs_id = db.query(pool_api.ReferralPoolPurchase).filter_by(user_id=theirs).one().id
        with pytest.raises(HTTPException) as info:
            pool_api.my_purchase(theirs_id, db=db, current_user=db.get(User, mine))
        assert info.value.status_code == 404
    assert dashboard(Session, waiting)["my_queue_entry"]["status"] == "WAITING"
    assert dashboard(Session, mine)["my_queue_entry"] is None
    theirs_view = dashboard(Session, theirs)
    assert theirs_view["units"]["purchased"] == 1 and theirs_view["amounts"]["paid"] == "100.00"


def test_purchases_are_paginated_and_show_payment_and_refund_status(shop, grants):
    Session = shop
    buyer, _ = sponsored_buyer(Session)
    deposits = [paid(Session, buyer, 1) for _ in range(3)]
    proposer = admin(Session)
    grants[proposer] = {FINANCE}
    pid = purchase_of(Session, deposits[0])[0]
    with Session() as db:
        units.propose_manual_refund(db, db.get(User, proposer), purchase_id=pid, quantity=1, amount=D("100"),
                                    provider_reference="np-member-view", evidence_note="Seen at the provider",
                                    password="x")
    with Session() as db:
        page1 = pool_api.my_purchases(db=db, current_user=db.get(User, buyer), page=1, page_size=2)
        page2 = pool_api.my_purchases(db=db, current_user=db.get(User, buyer), page=2, page_size=2)
    assert (page1["total"], len(page1["purchases"]), len(page2["purchases"])) == (3, 2, 1)
    oldest = page2["purchases"][0]
    assert oldest["payment"]["status"] == "validated" and oldest["status"] == "PAID"
    assert oldest["refund"] == {"refunded_units": 0, "in_review_units": 1}
    assert "provider_reference" not in str(oldest) and "evidence" not in str(oldest)


def test_disabled_sales_and_kyc_restrictions_reach_the_member(shop):
    Session = shop
    set_config(Session, multiunit_sales_enabled=False)
    unverified = member(Session, kyc=False)
    with Session() as db:
        e = pool_api.unit_eligibility(db=db, current_user=db.get(User, unverified))
        status = pool_api.public_status(db=db)
    assert (e["sales_enabled"], e["eligible"], e["reason"], e["kyc_approved"]) == (False, False, "KYC_REQUIRED", False)
    assert status == {"sales_enabled": False, "allocation_enabled": False, "unit_price": "100.00", "currency": "USD"}
    assert checkout(Session, member(Session), 1)[0] == 410


# ---------------------------------------------------------------------------
# 8-13, 15. Administrator views
# ---------------------------------------------------------------------------

def test_financial_views_need_a_finance_permission_and_overview_hides_money_without_it(shop, grants):
    Session = shop
    paid(Session, sponsored_buyer(Session)[0], 2)
    plain, finance = admin(Session), admin(Session)
    grants[finance] = {FINANCE}
    for view in (pool_api.admin_purchases, pool_api.admin_units, pool_api.admin_reconciliation,
                 pool_api.list_refunds, pool_api.admin_audit):
        with pytest.raises(HTTPException) as info:
            as_admin(Session, plain, view, page=1, page_size=10)
        assert info.value.status_code == 403
    with pytest.raises(HTTPException) as info:
        as_admin(Session, finance, pool_api.admin_risk_reviews, page=1, page_size=10)
    assert info.value.status_code == 403                                  # finance is not manage_kyc_settings
    overview = as_admin(Session, plain, pool_api.admin_overview)
    assert overview["amounts"] is None and overview["units"] == {"ACTIVE": 2}
    assert overview["permissions"] == {"finance": False, "kyc": False, "operations": False}
    overview = as_admin(Session, finance, pool_api.admin_overview)
    assert overview["amounts"] == {"paid": "200.00", "refunded": "0.00", "currency": "USD"}
    purchases = as_admin(Session, finance, pool_api.admin_purchases, page=1, page_size=10)
    assert purchases["total"] == 1 and purchases["items"][0]["payment"]["status"] == "validated"


def test_refund_evidence_never_labels_an_administrator_claim_as_provider_verified(shop, grants):
    Session = shop
    proposer, approver = admin(Session), admin(Session)
    grants[proposer] = grants[approver] = {FINANCE}
    buyer, _ = sponsored_buyer(Session)
    signed = paid(Session, buyer, 2)
    manual = paid(Session, buyer, 1)
    provider_event(Session, signed, "partially_refunded", refunded_amount="100.00")
    pid = purchase_of(Session, manual)[0]
    with Session() as db:
        record = units.propose_manual_refund(db, db.get(User, proposer), purchase_id=pid, quantity=1,
                                             amount=D("100"), provider_reference="np-claim-1",
                                             evidence_note="Seen in the NOWPayments dashboard", password="x")
        record_id = record.id
    listed = as_admin(Session, proposer, pool_api.list_refunds, page=1, page_size=10)["items"][0]
    assert (listed["status"], listed["evidence"], listed["provider_verified"]) == ("PROPOSED", "ADMIN_ENTERED_CLAIM", False)
    assert "not independently verified" in listed["evidence_label"]
    with Session() as db:
        with pytest.raises(HTTPException) as info:                    # the proposer cannot approve
            pool_api.decide_refund(record_id, pool_api.RefundDecision(approve=True, note="self check", password="x"),
                                   request=REQUEST, db=db, current_user=db.get(User, proposer))
        assert info.value.status_code == 403
    with Session() as db:
        decided = pool_api.decide_refund(record_id, pool_api.RefundDecision(approve=True, note="Checked again",
                                                                            password="x"),
                                         request=REQUEST, db=db, current_user=db.get(User, approver))
    assert decided["status"] == "APPROVED"
    refunded = as_admin(Session, approver, pool_api.admin_units, status=units.REFUNDED, page=1, page_size=10)["items"]
    evidence = {u["refund_reference"].split(":")[0] if ":" in u["refund_reference"] else u["refund_reference"]:
                u["refund_evidence"] for u in refunded}
    assert evidence["soncopay-refund"]["provider_verified"] is True
    assert evidence["np-claim-1"] == {
        "evidence": "ADMIN_ENTERED_CLAIM", "provider_verified": False,
        "label": "Administrator-entered claim, approved by a second administrator (not provider-verified)"}
    summary = as_admin(Session, approver, pool_api.admin_reconciliation, page=1, page_size=10)
    assert summary["summary"]["refunded_units"] == {"PROVIDER_EVENT": 1, "ADMIN_ENTERED_CLAIM": 1,
                                                    "DEPOSIT_REVERSAL": 0, "UNCLASSIFIED": 0}
    assert summary["summary"]["page_purchases_with_problems"] == 0
    assert all(item["problems"] == [] for item in summary["items"])
    actions = [a["action"] for a in as_admin(Session, approver, pool_api.admin_audit, page=1, page_size=10)["items"]]
    assert actions == [units.AUDIT_REFUND_DECIDED, units.AUDIT_REFUND_PROPOSED]


def test_anti_abuse_cases_need_manage_kyc_settings_and_show_no_raw_evidence(shop, grants):
    Session = shop
    a, b = member(Session), member(Session)
    reviewer = admin(Session)
    grants[reviewer] = {KYC}
    with Session() as db:
        db.add(ReferralPoolRiskReview(user_id=a, signal="DUPLICATE_KYC_IDENTITY", evidence_hash="ab" * 32,
                                      related_user_ids=str(b), blocking=True, status="OPEN"))
        db.commit()
    cases = as_admin(Session, reviewer, pool_api.admin_risk_reviews, page=1, page_size=10)
    case = cases["items"][0]
    assert (case["user_id"], case["related_user_ids"], case["blocking"], case["status"]) == (a, [b], True, "OPEN")
    assert case["evidence_fingerprint"] == "ab" * 6 and "evidence_hash" not in case
    assert not {"first_name", "last_name", "date_of_birth", "wallet", "ip_address"} & set(case)
    with Session() as db:
        decided = pool_api.decide_risk_review(case["id"], pool_api.RiskDecision(decision="CLEARED", note="Twins, checked",
                                                                                 password="x"),
                                              request=REQUEST, db=db, current_user=db.get(User, reviewer))
    assert decided["status"] == "CLEARED"
    assert as_admin(Session, reviewer, pool_api.admin_overview)["risk_reviews"] == {"open": 0, "open_blocking": 0}
    grants[reviewer] = set()
    with Session() as db:
        with pytest.raises(HTTPException) as info:
            pool_api.decide_risk_review(case["id"], pool_api.RiskDecision(decision="CONFIRMED", note="No permission",
                                                                           password="x"),
                                        request=REQUEST, db=db, current_user=db.get(User, reviewer))
    assert info.value.status_code == 403


def test_rounds_slots_queue_and_events_are_paginated_and_need_an_operations_permission(shop, grants):
    Session = shop
    plain, operator, sponsor_reviewer = admin(Session), admin(Session), admin(Session)
    grants[operator], grants[sponsor_reviewer] = {KYC}, {FINANCE}
    set_allocation(Session, True)
    holders = [holder(Session, 1) for _ in range(5)]
    for _ in range(3):
        referral(Session)
    assign(Session, referral(Session))
    with Session() as db:
        for i in range(3):
            db.add(ReferralPoolEvent(user_id=holders[i], event_type="KYC_APPROVED", dedupe_key=f"t:{i}",
                                     status="FAILED", attempts=5, last_error="synthetic failure", processed_at=NOW))
        db.commit()
        me, nobody, finance_only = db.get(User, operator), db.get(User, plain), db.get(User, sponsor_reviewer)
        for view, args in ((pool_api.admin_rounds, ()), (pool_api.admin_queue, ()), (pool_api.admin_events, ()),
                           (pool_api.admin_assignments, ()), (pool_api.admin_round_slots, (1,)),
                           (pool_api.admin_invalid_sponsors, ())):
            with pytest.raises(HTTPException) as info:
                view(*args, db=db, current_user=nobody, page=1, page_size=10)
            assert info.value.status_code == 403
        with pytest.raises(HTTPException) as info:                       # sponsors are KYC-derived
            pool_api.admin_invalid_sponsors(db=db, current_user=finance_only, page=1, page_size=10)
        assert info.value.status_code == 403
        assert pool_api.admin_invalid_sponsors(db=db, current_user=me, page=1, page_size=10)["items"] == []
        assert pool_api.admin_rounds(db=db, current_user=finance_only, page=1, page_size=10)["total"] == 1
        rounds = pool_api.admin_rounds(db=db, current_user=me, page=1, page_size=10)
        round_id = rounds["items"][0]["id"]
        slots1 = pool_api.admin_round_slots(round_id, db=db, current_user=me, page=1, page_size=2)
        slots3 = pool_api.admin_round_slots(round_id, db=db, current_user=me, page=3, page_size=2)
        filled = pool_api.admin_round_slots(round_id, db=db, current_user=me, status="FILLED", page=1, page_size=10)
        queue = pool_api.admin_queue(db=db, current_user=me, page=1, page_size=2)
        events = pool_api.admin_events(db=db, current_user=me, page=2, page_size=2)
        assignments = pool_api.admin_assignments(db=db, current_user=me, round_id=round_id, page=1, page_size=10)
        with pytest.raises(HTTPException):
            pool_api.admin_round_slots(999999, db=db, current_user=me, page=1, page_size=10)
    assert rounds["total"] == 1 and rounds["items"][0]["total_slots"] == 5
    assert (slots1["total"], len(slots1["items"]), len(slots3["items"])) == (5, 2, 1)
    assert filled["total"] == 1 and filled["items"][0]["referred_user_id"] == assignments["items"][0]["referred_user_id"]
    assert (queue["total"], len(queue["items"])) == (3, 2)
    assert (events["total"], len(events["items"])) == (3, 1) and events["items"][0]["last_error"] == "synthetic failure"


def test_sponsors_view_lists_every_sponsored_member_with_usernames_and_the_recorded_type(shop, grants):
    Session = shop
    reviewer, finance_only = admin(Session), admin(Session)
    grants[reviewer], grants[finance_only] = {KYC}, {FINANCE}
    buyer, sponsor = sponsored_buyer(Session)                                # PERSONAL_REFERRAL
    legacy, orphan_sponsor = member(Session), member(Session)
    with Session() as db:
        db.get(User, legacy).sponsor_id, db.get(User, legacy).sponsor_source = sponsor, None    # recorded before sources
        db.commit()
        names = {u.id: u.username for u in db.query(User).filter(User.id.in_((buyer, sponsor, legacy)))}
        before = [(u.id, u.sponsor_id, u.sponsor_source) for u in db.query(User).order_by(User.id)]
        with pytest.raises(HTTPException) as info:                           # same permission as invalid sponsors
            pool_api.admin_sponsors(db=db, current_user=db.get(User, finance_only), page=1, page_size=10)
        assert info.value.status_code == 403
        listed = pool_api.admin_sponsors(db=db, current_user=db.get(User, reviewer), page=1, page_size=10)
        page2 = pool_api.admin_sponsors(db=db, current_user=db.get(User, reviewer), page=2, page_size=1)
        assert [(u.id, u.sponsor_id, u.sponsor_source) for u in db.query(User).order_by(User.id)] == before    # read only
    assert listed["total"] == 2 and page2["total"] == 2 and len(page2["items"]) == 1
    assert listed["items"] == [
        {"user_id": buyer, "username": names[buyer], "sponsor_id": sponsor, "sponsor_username": names[sponsor],
         "sponsor_source": "PERSONAL_REFERRAL"},
        {"user_id": legacy, "username": names[legacy], "sponsor_id": sponsor, "sponsor_username": names[sponsor],
         "sponsor_source": None},
    ]
    assert orphan_sponsor not in {i["user_id"] for i in listed["items"]}     # unsponsored members are not listed


def test_optional_limits_show_in_the_overview_and_need_permission_to_change(shop, grants):
    Session = shop
    operator = admin(Session)
    body = pool_api.LimitsBody(max_units_per_purchase=3, max_units_per_member=None, max_active_units=50, password="x")
    with Session() as db:
        with pytest.raises(HTTPException) as info:
            pool_api.set_limits(body, request=REQUEST, db=db, current_user=db.get(User, operator))
        assert info.value.status_code == 403
    grants[operator] = {payment_config.PERMISSION_MANAGE}
    with Session() as db:
        pool_api.set_limits(body, request=REQUEST, db=db, current_user=db.get(User, operator))
    overview = as_admin(Session, operator, pool_api.admin_overview)
    assert overview["limits"] == {"max_units_per_purchase": 3, "max_units_per_member": None, "max_active_units": 50}
    assert as_admin(Session, operator, pool_api.admin_audit, page=1, page_size=5)["items"][0]["action"] == \
        "REFERRAL_POOL_LIMITS_CHANGED"
    assert checkout(Session, member(Session), 4)[0] == 409                       # the limit applies to checkout


def test_no_route_or_view_turns_a_feature_on(shop, grants):
    Session = shop
    set_config(Session, multiunit_sales_enabled=False)
    everyone = admin(Session)
    grants[everyone] = {FINANCE, payment_config.PERMISSION_MANAGE, payment_config.PERMISSION_ACTIVATE, KYC}
    overview = as_admin(Session, everyone, pool_api.admin_overview)
    assert overview["features"] == {"multiunit_sales_enabled": False, "allocation_enabled": False,
                                    "worker_enabled": False, "activation_available": False}
    writes = sorted((r.path, sorted(r.methods)) for r in pool_api.admin_router.routes
                    if set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"})
    assert writes == [("/limits", ["PUT"]), ("/refunds", ["POST"]), ("/refunds/{record_id}/decision", ["POST"]),
                      ("/risk-reviews/{review_id}/decision", ["POST"])]
    assert not [r for r in pool_api.router.routes if set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"}]
    assert "multiunit_sales_enabled" not in pool_api.LimitsBody.model_fields
    with Session() as db:
        cfg = db.query(ReferralPoolConfig).one()
        assert (cfg.multiunit_sales_enabled, cfg.allocation_enabled) == (False, False)


# ---------------------------------------------------------------------------
# Through the mounted routes, with real tokens (no browser-side gate to rely on)
# ---------------------------------------------------------------------------

def test_mounted_routes_enforce_member_admin_and_permission_checks(world, app, monkeypatch):
    engine, Session = world
    import app.db.session as session_module

    granted: dict = {}
    monkeypatch.setattr(payment_config, "has_permission",
                        lambda user, permission: permission in granted.get(getattr(user, "id", None), ()))
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    original = (session_module.engine, session_module.SessionLocal)
    session_module.engine, session_module.SessionLocal = engine, factory

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        plain_member, plain_admin, finance = member(Session), admin(Session), admin(Session)
        granted[finance] = {FINANCE}
        with Session() as db:
            tokens = {k: auth(db.get(User, v)) for k, v in
                      (("member", plain_member), ("admin", plain_admin), ("finance", finance))}
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/v1/referral-pool/status").status_code == 200          # public launch state
            assert client.get("/api/v1/referral-pool/units/dashboard").status_code == 401
            assert client.get("/api/v1/referral-pool/units/dashboard", headers=tokens["member"]).status_code == 200
            assert client.get("/api/v1/admin/referral-pool/overview", headers=tokens["member"]).status_code == 403
            assert client.get("/api/v1/admin/referral-pool/overview", headers=tokens["admin"]).status_code == 200
            assert client.get("/api/v1/admin/referral-pool/purchases", headers=tokens["admin"]).status_code == 403
            assert client.get("/api/v1/admin/referral-pool/purchases", headers=tokens["finance"]).status_code == 200
            assert client.get("/api/v1/admin/referral-pool/risk-reviews", headers=tokens["finance"]).status_code == 403
            assert client.get("/api/v1/admin/referral-pool/units?page_size=101",
                              headers=tokens["finance"]).status_code == 422
            assert client.get("/api/v1/admin/referral-pool/rounds?page=0", headers=tokens["admin"]).status_code == 422
            assert client.get("/api/v1/admin/referral-pool/rounds", headers=tokens["admin"]).status_code == 403
            assert client.get("/api/v1/admin/referral-pool/rounds", headers=tokens["finance"]).status_code == 200
            assert client.get("/api/v1/admin/referral-pool/invalid-sponsors", headers=tokens["finance"]).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        session_module.engine, session_module.SessionLocal = original
    with Session() as db:
        assert db.query(AuditTrail).count() == 0                                 # reads write nothing
