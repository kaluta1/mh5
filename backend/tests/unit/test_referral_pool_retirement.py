"""Referral Pool retirement (client decision, 2026-09-28).

No future pool activity through any entry point; history stays readable and unchanged.
"""
from __future__ import annotations

import inspect
from datetime import datetime

import pytest

from app.api.api_v1.endpoints import business_model as bm_api
from app.models.business_model import ReferralPoolAssignment, ReferralPoolMembership
from app.services import referral_pool_service as pool
from app.services import sponsor_assignment
from tests.unit.test_new_business_model import (  # noqa: F401  (fixtures)
    _pool_member,
    _register,
    _retired_legacy,
    _user,
    world,
)

pytestmark = pytest.mark.unit


def test_public_summary_reports_the_pool_retired_without_price_or_seat_promotion(world):
    body = bm_api.business_model_summary(db=world)
    assert body["referral_pool"] == {"retired": True, "is_open": False}
    assert "referral_pool" not in body["commission_policy"]
    assert body["direct_commission_rate"] == 0.20 and body["affiliate_levels"] == 1  # unchanged
    assert body["leaders"] == {"pool_rate": 0.05, "max_members": 10000}  # unchanged
    assert body["direct_affiliate_rates"] == {
        "standard_rate": 0.20, "qualified_rate": 0.40, "required_kyc_verified_direct_referrals": 10000,
        "window_months_from_registration": 6, "permanent": True, "applies_to": ["AD_SLOT_PURCHASE"]}
    cp = body["ad_revenue"]["contest_page"]
    assert cp["personal_submission"] == {"owner_rate": 0.20, "direct_sponsor_rate": 0.01}
    assert cp["nomination"] == {"owner_rate": 0.10, "direct_sponsor_rate": 0.01}
    assert cp["applies_to_annual_ads"] is False and body["ad_revenue"]["payouts_live"] is False


def test_no_route_can_write_to_the_referral_pool(app):
    assert any("referral-pool" in getattr(r, "path", "") for r in app.routes)  # read-only history routes exist
    writes = [
        (route.path, sorted(route.methods))
        for route in app.routes
        if "referral-pool" in getattr(route, "path", "")
        and set(getattr(route, "methods", set()) or set()) & {"POST", "PUT", "PATCH", "DELETE"}
    ]
    assert writes == []


def test_member_affiliate_rate_endpoint_is_read_only(world):
    from app.models.business_model import AffiliateRateQualification

    db = world
    member = _user(db, "rate@t.com")
    db.commit()
    body = bm_api.my_affiliate_rate(db=db, current_user=member)
    assert (body["rate"], body["permanently_qualified"], body["required_direct_referrals"]) == (0.20, False, 10000)
    assert db.query(AffiliateRateQualification).count() == 0


def test_member_history_stays_readable(world):
    db = world
    member = _pool_member(db, "hist@t.com")
    body = bm_api.my_referral_pool(db=db, current_user=member)
    assert body["retired"] is True
    assert body["membership"]["status"] == pool.ACTIVE and body["membership"]["entitlement_source"] == pool.SOURCE_PAID
    assert len(body["history"]) == 1


def test_admin_overview_shows_history_and_marks_retired(world):
    db = world
    _pool_member(db, "a1@t.com")
    body = bm_api.admin_overview(db=db)
    assert body["referral_pool"]["retired"] is True
    assert body["referral_pool"]["by_status"] == {pool.ACTIVE: 1}


def test_registration_no_longer_depends_on_the_pool_service():
    source = inspect.getsource(sponsor_assignment)
    assert "referral_pool_service" not in source and "pick_pool_member" not in source


def test_organic_registration_leaves_existing_pool_rows_untouched(world):
    db = world
    member = _pool_member(db, "keep@t.com")
    historical = _user(db, "old@t.com", sponsor=member)
    historical.sponsor_source = "REFERRAL_POOL"
    db.add(ReferralPoolAssignment(referred_user_id=historical.id, pool_member_user_id=member.id, membership_id=1,
                                  method="FAIR_RANDOM_V1", candidate_count=1, min_assignment_count=0,
                                  assigned_at=datetime.utcnow()))
    db.commit()
    snapshot = [(m.id, m.status, m.seat_number, m.assignments_count) for m in db.query(ReferralPoolMembership).all()]
    new = _register(db, "fresh@t.com")
    assert (new.sponsor_id, new.sponsor_source) == (None, "NONE")
    assert [(m.id, m.status, m.seat_number, m.assignments_count)
            for m in db.query(ReferralPoolMembership).all()] == snapshot
    assert db.query(ReferralPoolAssignment).count() == 1
    db.refresh(historical)
    assert (historical.sponsor_id, historical.sponsor_source) == (member.id, "REFERRAL_POOL")
