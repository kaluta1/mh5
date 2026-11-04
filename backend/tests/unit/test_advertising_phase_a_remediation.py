"""Advertising Phase A integration-review remediation (2026-11-04): D2 verified-city trust, D3 lead and booking
reversals, D4 package switch enforcement, D5 fair Daily City rotation and capacity. D1 (signed clicks) is in
test_advertising_phase_a.py. SYNTHETIC data only; real concurrency is in
tests/integration/test_advertising_phase_a_postgres.py. Daily City and Lead stay NOT READY in code: the
tests that exercise their mechanics mark them ready for the test only (fixture city_ready / _ready)."""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.advertising_v2 import (AdvBooking, AdvCampaign, AdvCreditMovement, AdvGeoAttestation,
                                       AdvImpressionEvent, AdvLead, AdvServeDecision)
from app.models.kyc import KYCStatus, KYCVerification
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_geo, ad_leads, ad_packages as pk
from tests.unit.test_advertising_phase_a import (_admin, _city, _event, _inventory, _live, _ready, _resident,
                                                 _serve, _settings, _viewer, city_ready)  # noqa: F401
from tests.unit.test_advertising_program import UA, T0, _balance, _fund, _ledger_balanced  # noqa: F401
from tests.unit.test_new_business_model import _user, world  # noqa: F401

pytestmark = pytest.mark.unit
D = Decimal


def _book(db, adv, city, days, *, approve=True):
    c = camp.create_campaign(db, adv, name="D", package="daily_city", placements=["IN_FEED"],
                             bookings={"city_id": city.id, "days": days})
    cr = camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://example.com/")
    camp.submit_campaign(db, adv, c)
    if approve:
        admin = _admin(db)
        camp.review_creative(db, admin, cr, approve=True, note="ok")
        camp.review_campaign(db, admin, c, approve=True, note="ok")
    return c


# ---------------------------------------------------------------- D2 verified-city trust

def test_d2_city_counts_only_with_a_current_attestation_for_the_unchanged_profile_city(world, client):
    from tests.unit.test_admin_security_hardening import bearer

    db = world
    city, other = _city(db), _city(db, "Kisumu")
    legacy = _user(db, "legacy@t.com")                         # verified before attestations existed
    legacy.city_id, legacy.address_verified = city.id, True
    db.flush()
    assert dl.verified_city(db, legacy.id) is None              # nothing is backfilled: no evidence
    m = _resident(db, city)
    assert dl.verified_city(db, m.id) == city.id
    db.commit()
    r = client.put("/api/v1/users/me", json={"city_id": other.id}, headers=bearer(m))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert dl.verified_city(db, m.id) is None                   # changed city: re-verification needed
    r = client.put("/api/v1/users/me", json={"city_id": city.id}, headers=bearer(m))
    assert r.status_code == 200
    db.expire_all()
    assert dl.verified_city(db, m.id) is None                   # moving back does not revive the old evidence
    assert db.query(AdvGeoAttestation).filter_by(user_id=m.id, revoke_reason="CITY_CHANGED").count() == 1
    m.address_verified = False
    ad_geo.attest_on_address_approval(db, m, None)
    assert dl.verified_city(db, m.id) is None                   # an address no longer verified never counts


def _pending_kyc(db, user):
    v = db.query(KYCVerification).filter_by(user_id=user.id).first()
    if v is None:
        v = KYCVerification(user_id=user.id)
        db.add(v)
    v.status, v.address_verified = KYCStatus.REQUIRES_REVIEW, False
    user.address_verified = False
    db.commit()
    return v


def test_d2_a_proof_of_address_approval_records_the_city_and_never_blocks_kyc(world, monkeypatch):
    from app.crud.crud_kyc import kyc_verification as crud_kyc_verification

    db = world
    city = _city(db)
    u = _user(db, "kyc-geo@t.com")
    u.city_id = city.id
    v = _pending_kyc(db, u)
    crud_kyc_verification.approve_verification(db, verification_id=v.id, admin_user_id=None)
    db.expire_all()
    row = db.query(AdvGeoAttestation).filter_by(user_id=u.id).one()
    assert (row.city_id, row.kyc_verification_id, row.revoked_at) == (city.id, v.id, None)
    assert dl.verified_city(db, u.id) == city.id

    w = _user(db, "kyc-geo2@t.com")
    w.city_id = city.id
    v2 = _pending_kyc(db, w)

    def boom(*_a, **_k):
        raise RuntimeError("simulated")

    monkeypatch.setattr(ad_geo, "revoke", boom)
    crud_kyc_verification.approve_verification(db, verification_id=v2.id, admin_user_id=None)
    db.expire_all()
    assert db.get(KYCVerification, v2.id).status == KYCStatus.APPROVED          # KYC decision unaffected
    assert db.query(AdvGeoAttestation).filter_by(user_id=w.id).count() == 0     # just no evidence


def test_d2_stale_evidence_never_creates_billable_city_inventory(world, city_ready):
    db = world
    _settings(db, "daily_city")
    city = _city(db)
    _inventory(db, city, 30)
    adv = _user(db, "stale@t.com")
    _fund(db, adv, "10.00")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    c = _book(db, adv, city, [day1])
    at = datetime.combine(day1, datetime.min.time()) + timedelta(hours=10)
    m = _resident(db, city)
    ad_geo.on_profile_city_change(db, m, _city(db, "Nakuru").id)               # evidence revoked
    v = dl.viewer_hash_for_user(m.id)
    assert not _serve(db, v, at=at, user_id=m.id)["fill"]
    assert db.query(AdvServeDecision).filter(AdvServeDecision.viewer_city_id == city.id,
                                             AdvServeDecision.campaign_id == c.id).count() == 0


# ---------------------------------------------------------------- D3 reversals

def _lead_campaign(db, monkeypatch, adv, budget="1.00"):
    _ready(monkeypatch, "lead")
    _settings(db, "lead")
    c = AdvCampaign(advertiser_user_id=adv.id, name="L", status="ACTIVE", pricing_model="LEAD",
                    unit_rate_usd=D("0.25"), budget_total=D(budget), spent=0, reserved=0, placements=["IN_FEED"],
                    start_at=T0 - timedelta(days=1), end_at=T0 + timedelta(days=30))
    db.add(c)
    db.flush()
    return c


def _accepted(db, c, contact):
    lead = ad_leads._record(db, campaign_id=c.id, name="N", contact=contact, consent=True, consent_version="v1",
                            decision_id=None, now=T0)
    return ad_leads.accept(db, lead.id, actor_id=None, now=T0 + timedelta(hours=1))


def test_d3_an_accepted_lead_is_reversed_once_and_audited(world, monkeypatch):
    db = world
    adv, admin = _user(db, "lr@t.com"), _user(db, "lra@t.com")
    c = _lead_campaign(db, monkeypatch, adv)
    lead = _accepted(db, c, "a@example.com")
    db.refresh(c)
    assert c.spent == D("0.250000")
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.reverse(db, lead.id, actor_id=admin.id, reason="")
    assert e.value.code == "NOTE_REQUIRED"
    ad_leads.reverse(db, lead.id, actor_id=admin.id, reason="Advertiser proved duplicate")
    db.refresh(c)
    assert (lead.status, c.spent, lead.reversed_by_user_id) == ("REVERSED", D("0"), admin.id)
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.reverse(db, lead.id, actor_id=admin.id, reason="again")
    assert e.value.code == "NOT_REVERSIBLE"                                    # never twice
    pending = ad_leads._record(db, campaign_id=c.id, name="N", contact="b@example.com", consent=True,
                               consent_version="v1", decision_id=None, now=T0)
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.reverse(db, pending.id, actor_id=admin.id, reason="not charged")
    assert e.value.code == "NOT_REVERSIBLE"                                    # nothing was charged


def test_d3_lead_reversal_after_recognition_and_settlement_restores_credit_and_balances(world, monkeypatch):
    db = world
    adv, admin = _user(db, "lr2@t.com"), _user(db, "lr2a@t.com")
    _fund(db, adv, "5.00")
    c = _lead_campaign(db, monkeypatch, adv)
    c.status = "PENDING_REVIEW"
    camp._movement(db, advertiser_id=adv.id, kind="ALLOCATE", amount=D("-1.00"), key=f"campaign:{c.id}:allocate",
                   campaign_id=c.id, note="test")
    c.status = "ACTIVE"
    lead = _accepted(db, c, "c@example.com")
    dl.recognize_closed_days(db, now=T0 + timedelta(days=2))
    assert _balance(db, "4020") == D("-0.25")
    c.end_at = T0 + timedelta(days=1)
    dl.complete_due_campaigns(db, now=T0 + timedelta(days=2))
    db.refresh(c)
    assert c.settled_at is not None and camp.credit_balance(db, adv.id) == D("4.75")
    ad_leads.reverse(db, lead.id, actor_id=admin.id, reason="Chargeback on the lead")
    assert camp.credit_balance(db, adv.id) == D("5.00")                         # restored to the advertiser
    assert _balance(db, "4020") == D("0.00")                                    # revenue reversed
    assert db.query(AdvCreditMovement).filter_by(idempotency_key=f"lead:{lead.id}:reversal").count() == 1
    _ledger_balanced(db)


def _earned_day(db, *, threshold, residents):
    """A Daily City day earned with `residents` valid views at the given threshold."""
    _settings(db, "daily_city", threshold=threshold)
    city = _city(db)
    _inventory(db, city, 30 * threshold)
    adv = _user(db, f"e-{uuid.uuid4().hex[:6]}@t.com")
    _fund(db, adv, "10.00")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    c = _book(db, adv, city, [day1])
    at = datetime.combine(day1, datetime.min.time()) + timedelta(hours=10)
    for _ in range(residents):
        m = _resident(db, city)
        v = dl.viewer_hash_for_user(m.id)
        d = _serve(db, v, at=at, user_id=m.id)
        assert d["fill"]
        _event(db, d, v, "VIEWABLE", at=at + timedelta(seconds=2))
    dl.validate_pending(db, now=at + timedelta(seconds=5))
    dl.settle_bookings(db, now=at + timedelta(days=1))
    booking = db.query(AdvBooking).filter_by(campaign_id=c.id).one()
    assert booking.status == "EARNED"
    return c, booking, adv, at


def _viewables(db, c):
    return (db.query(AdvImpressionEvent).join(AdvServeDecision, AdvServeDecision.id == AdvImpressionEvent.decision_id)
            .filter(AdvServeDecision.campaign_id == c.id, AdvImpressionEvent.event_type == "VIEWABLE")
            .order_by(AdvImpressionEvent.id).all())


def test_d3_invalid_activity_below_the_threshold_reverses_an_earned_day_once(world, city_ready):
    db = world
    admin = _user(db, "rev@t.com")
    c, booking, adv, at = _earned_day(db, threshold=2, residents=3)
    events = _viewables(db, c)
    assert camp.credit_balance(db, adv.id) == D("5.00")
    out = dl.reverse_invalid_activity(db, event_ids=[events[0].id], reason="click farm", actor_id=admin.id)
    db.refresh(booking)
    assert (out["bookings_reversed"], booking.status) == (0, "EARNED")         # 2 left: still at the threshold
    out = dl.reverse_invalid_activity(db, event_ids=[events[1].id], reason="click farm", actor_id=admin.id)
    db.refresh(booking)
    db.refresh(c)
    assert (out["bookings_reversed"], booking.status, booking.valid_impressions) == (1, "REVERSED", 1)
    assert camp.credit_balance(db, adv.id) == D("10.00") and c.spent == D("0")
    out = dl.reverse_invalid_activity(db, event_ids=[events[2].id, events[1].id], reason="again", actor_id=admin.id)
    assert out["bookings_reversed"] == 0 and camp.credit_balance(db, adv.id) == D("10.00")     # never twice
    assert db.query(AdvCreditMovement).filter_by(idempotency_key=f"booking:{booking.id}:reversal").count() == 1


def test_d3_booking_reversal_after_recognition_and_settlement_balances_the_ledger(world, city_ready):
    db = world
    admin = _user(db, "rev2@t.com")
    c, booking, adv, at = _earned_day(db, threshold=1, residents=1)
    later = at + timedelta(days=2)
    dl.recognize_closed_days(db, now=later)
    dl.complete_due_campaigns(db, now=later)
    db.refresh(c)
    assert c.settled_at is not None and _balance(db, "4020") == D("-5.00")
    dl.reverse_invalid_activity(db, event_ids=[_viewables(db, c)[0].id], reason="fraud", actor_id=admin.id)
    db.refresh(booking)
    assert booking.status == "REVERSED" and camp.credit_balance(db, adv.id) == D("10.00")
    assert _balance(db, "4020") == D("0.00")
    _ledger_balanced(db)


# ---------------------------------------------------------------- D4 package switch enforcement

def test_d4_a_switched_off_package_stops_approval_serving_and_billing(world):
    db = world
    cfg = _settings(db, "cpc")
    adv = _user(db, "off@t.com")
    _fund(db, adv, "10.00")
    running, _ = _live(db, adv, "cpc", budget="1.00")
    pending, pending_cr = _live(db, adv, "cpc", budget="1.00", approve=False)
    camp.review_creative(db, _admin(db), pending_cr, approve=True, note="ok")
    v = _viewer()
    d = _serve(db, v)                                                           # reserved while on
    assert d["fill"]
    _event(db, d, v, "SERVED", at=T0 + timedelta(milliseconds=100))
    camp.update_settings(db, _admin(db), {"enabled_packages": []})             # switched off
    assert not _serve(db, _viewer())["fill"]                                    # no new serving
    with pytest.raises(camp.AdError) as e:
        camp.review_campaign(db, _admin(db), pending, approve=True, note="ok")
    assert e.value.code == "PACKAGE_DISABLED"                                   # never approved
    dl.record_click(db, decision_id=d["decision_id"], token=d["creative"]["click_url"].split("?t=")[1],
                    user_agent=UA, now=T0 + timedelta(seconds=3))
    dl.validate_pending(db, now=T0 + timedelta(seconds=5))
    ev = db.query(AdvImpressionEvent).filter_by(decision_id=d["decision_id"], event_type="CLICK").one()
    db.refresh(running)
    assert (ev.validation_status, ev.invalid_reason) == ("INVALID", "PACKAGE_DISABLED")
    assert (running.spent, running.reserved) == (D("0"), D("0"))                # reservation released
    assert running.status == "ACTIVE" and camp.campaign_report(db, running)["clicks"] == 0   # history kept
    cfg.enabled_packages = ["cpc"]
    db.flush()
    camp.review_campaign(db, _admin(db), pending, approve=True, note="ok")      # back on: normal again


def test_d4_the_global_switch_stays_authoritative_for_every_package(world):
    db = world
    cfg = _settings(db, "cpc")
    adv = _user(db, "glob@t.com")
    _fund(db, adv, "20.00")
    cpm, _ = _live(db, adv, "cpm", budget="10.00")
    v = _viewer()
    d = _serve(db, v)
    assert d["fill"]
    cfg.campaigns_enabled = False
    db.flush()
    assert not _serve(db, _viewer())["fill"]
    _event(db, d, v, "VIEWABLE", at=T0 + timedelta(seconds=2))
    dl.validate_pending(db, now=T0 + timedelta(seconds=5))
    db.refresh(cpm)
    assert (cpm.spent, cpm.reserved) == (D("0"), D("0"))


# ---------------------------------------------------------------- D5 fair rotation and capacity

def test_d5_overlapping_bookings_share_the_city_fairly(world, city_ready):
    db = world
    _settings(db, "daily_city", threshold=1)
    city = _city(db)
    _inventory(db, city, 120)                                                    # 4 verified views a day
    day1 = datetime.utcnow().date() + timedelta(days=1)
    campaigns = []
    for i in range(3):
        adv = _user(db, f"fair{i}-{uuid.uuid4().hex[:4]}@t.com")
        _fund(db, adv, "10.00")
        campaigns.append(_book(db, adv, city, [day1]).id)
    at = datetime.combine(day1, datetime.min.time()) + timedelta(hours=10)
    served = Counter()
    for _ in range(9):
        m = _resident(db, city)
        d = _serve(db, dl.viewer_hash_for_user(m.id), at=at, user_id=m.id)
        served[db.get(AdvServeDecision, d["decision_id"]).campaign_id] += 1
    assert set(served) == set(campaigns) and max(served.values()) - min(served.values()) <= 1
    assert sum(served.values()) == 9                                              # each view counted once


def test_d5_capacity_counts_overlapping_bookings_and_drafts_hold_none(world, city_ready):
    db = world
    _settings(db, "daily_city", threshold=2)
    city = _city(db)
    _inventory(db, city, 120)                                                    # 4/day = 2 bookings of 2
    day1 = datetime.utcnow().date() + timedelta(days=1)
    advs = []
    for i in range(4):
        a = _user(db, f"cap{i}-{uuid.uuid4().hex[:4]}@t.com")
        _fund(db, a, "20.00")
        advs.append(a)
    draft = camp.create_campaign(db, advs[3], name="D", package="daily_city", placements=["IN_FEED"],
                                 bookings={"city_id": city.id, "days": [day1]})      # a draft holds nothing
    _book(db, advs[0], city, [day1])
    second = _book(db, advs[1], city, [day1, day1 + timedelta(days=1)], approve=False)   # pending holds too
    with pytest.raises(camp.AdError) as e:
        _book(db, advs[2], city, [day1])
    assert e.value.code == "CITY_FULLY_BOOKED"
    _book(db, advs[2], city, [day1 + timedelta(days=1)])                           # the next day has room
    camp.cancel_campaign(db, advs[1], second)                                       # cancelled frees capacity
    cr = camp.add_creative(db, draft, headline="h", body=None, image_url=None, destination_url="https://example.com/")
    camp.submit_campaign(db, advs[3], draft)
    assert draft.status == "PENDING_REVIEW" and cr is not None


def test_d5_insufficient_inventory_refuses_and_nothing_is_invented(world, city_ready):
    db = world
    _settings(db, "daily_city", threshold=3)
    city = _city(db)
    _inventory(db, city, 60)                                                     # 2/day < 3
    adv = _user(db, "inv5@t.com")
    with pytest.raises(camp.AdError) as e:
        camp.create_campaign(db, adv, name="D", package="daily_city", placements=["IN_FEED"],
                             bookings={"city_id": city.id, "days": [datetime.utcnow().date() + timedelta(days=1)]})
    assert e.value.code == "INSUFFICIENT_INVENTORY"
    assert camp.city_inventory(db, _city(db, "Empty").id)["valid_impressions"] == 0


def test_flags_stay_off_by_default(world):
    db = world
    cfg = camp.get_settings(db)
    assert not cfg.campaigns_enabled and not cfg.funding_enabled and not cfg.enabled_packages
    assert cfg.daily_city_min_impressions is None
    assert {c for c, p in pk.PACKAGES.items() if p.not_ready} == {"cpm_video", "cpv", "lead", "daily_local",
                                                                   "daily_city"}
