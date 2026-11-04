"""Advertising Phase A (2026-11-04): the eight packages, their minimum rates, package-aware event qualification,
budget and credit controls, Daily City bookings with once-only settlement, the video and lead foundations,
six-decimal precision. Every new package is OFF by default; nothing here creates any earning.
SYNTHETIC data only; real concurrency is in tests/integration/test_advertising_phase_a_postgres.py."""
from __future__ import annotations

import struct
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.advertising_v2 import (AdvAllocation, AdvBooking, AdvCampaign, AdvCreative, AdvCreditMovement,
                                       AdvImpressionEvent, AdvServeDecision)
from app.models.affiliate import AffiliateCommission
from app.models.geography import City, Continent, Country, Region
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_leads, ad_packages as pk, ad_video
from tests.unit.test_advertising_program import UA, T0, _balance, _configure, _fund, _ledger_balanced
from tests.unit.test_new_business_model import _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit
D = Decimal


def _settings(db, *packages, threshold=None, **kw):
    cfg = _configure(db, cpm="0.50", **kw)
    cfg.min_campaign_budget_usd = D("10.00")
    cfg.enabled_packages = list(packages)
    cfg.daily_city_min_impressions = threshold if threshold is not None else (1 if "daily_city" in packages else None)
    db.flush()
    return cfg


def _admin(db):
    return _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")


def _live(db, adv, package, *, rate=None, budget="1.00", approve=True, **kw):
    c = camp.create_campaign(db, adv, name="P", budget=budget, start_at=T0 - timedelta(days=1),
                             end_at=T0 + timedelta(days=30), placements=["IN_FEED", "SIDEBAR", "IN_CONTENT"],
                             package=package, unit_rate=rate, **kw)
    cr = camp.add_creative(db, c, headline="Buy", body=None, image_url=None, destination_url="https://example.com/x")
    camp.submit_campaign(db, adv, c)
    if approve:
        admin = _admin(db)
        camp.review_creative(db, admin, cr, approve=True, note="ok")
        camp.review_campaign(db, admin, c, approve=True, note="ok")
    return c, cr


def _viewer():
    return dl.viewer_hash(None, f"10.1.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}", UA)


def _serve(db, viewer, at=T0, page="FEED", slot="IN_FEED", user_id=None):
    return dl.decide(db, page_type=page, slot_kind=slot, slot_key="k", contestant_id=None, viewer=viewer, now=at,
                     allowed_sources={"myhigh5_ads"}, viewer_user_id=user_id)


def _event(db, d, viewer, kind, *, at, ms=1500, ratio=0.8, played=None, ua=UA, allow_click=False, action=None):
    return dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type=kind,
                           visible_ms=ms, visible_ratio=ratio, page_visible=True, user_agent=ua, viewer=viewer, now=at,
                           played_ms=played, allow_click=allow_click, action=action)


def _commissions(db):
    return db.query(AffiliateCommission).count()


# ---------------------------------------------------------------- 1-4 package definitions and prices

def test_1_2_the_eight_packages_and_their_approved_minimum_rates():
    assert {c: str(p.floor) for c, p in pk.PACKAGES.items()} == {
        "cpm": "0.50", "cpm_video": "1.00", "cpc": "0.05", "cpv": "0.005", "engagement": "0.02", "lead": "0.25",
        "daily_local": "1.00", "daily_city": "5.00"}
    assert pk.unit_charge(pk.PACKAGES["cpm"], "0.50") == D("0.000500")
    assert pk.unit_charge(pk.PACKAGES["cpm_video"], "1.00") == D("0.001000")
    assert pk.unit_charge(pk.PACKAGES["cpv"], "0.005") == D("0.005000")
    assert pk.unit_charge(pk.PACKAGES["cpc"], "0.050001") == D("0.050001")       # six decimals, exact
    for bad in ("annual_ads", "cpa", "", None, "flat"):
        with pytest.raises(pk.PackageError) as e:
            pk.get(bad)
        assert e.value.code == "UNKNOWN_PACKAGE"
    for code, below in (("cpc", "0.049999"), ("cpv", "0.004"), ("daily_city", "4.99"), ("cpm_video", "0.99")):
        with pytest.raises(pk.PackageError) as e:
            pk.validate_rate(pk.PACKAGES[code], below)
        assert e.value.code == "RATE_BELOW_MINIMUM"
    with pytest.raises(pk.PackageError):
        pk.validate_rate(pk.PACKAGES["cpc"], "0.0500001")                         # 7 decimals
    with pytest.raises(pk.PackageError):
        pk.validate_rate(pk.PACKAGES["cpc"], 0.05)                                # binary float refused


def test_3_standard_cpm_keeps_its_10_dollar_minimum_and_other_packages_one_unit(world):
    db = world
    _settings(db, "cpc")
    adv = _user(db, "a3@t.com")
    with pytest.raises(camp.AdError) as e:
        camp.create_campaign(db, adv, name="x", budget="9.99", start_at=T0, end_at=T0 + timedelta(days=1),
                             placements=["IN_FEED"])
    assert e.value.code == "BUDGET_BELOW_MINIMUM"
    c = camp.create_campaign(db, adv, name="x", budget="0.05", start_at=T0, end_at=T0 + timedelta(days=1),
                             placements=["IN_FEED"], package="cpc")
    assert (c.pricing_model, c.unit_rate_usd) == ("CPC", D("0.050000"))
    with pytest.raises(camp.AdError) as e:
        camp.create_campaign(db, adv, name="x", budget="0.05", start_at=T0, end_at=T0 + timedelta(days=1),
                             placements=["IN_FEED"], package="cpc", unit_rate="0.06")
    assert e.value.code == "BUDGET_BELOW_UNIT"


def test_4_packages_are_off_by_default_and_not_ready_ones_can_never_be_switched_on(world):
    db = world
    cfg = _settings(db)                                   # campaigns + funding on, no package switched on
    adv = _user(db, "a4@t.com")
    for code in ("cpc", "engagement", "daily_city"):
        with pytest.raises(camp.AdError) as e:
            camp.create_campaign(db, adv, name="x", budget="1.00", start_at=T0, end_at=T0 + timedelta(days=1),
                                 placements=["IN_FEED"], package=code)
        assert e.value.code == "PACKAGE_DISABLED"
    for code in ("cpm_video", "cpv", "lead", "daily_local"):
        with pytest.raises(camp.AdError) as e:
            camp.update_settings(db, _admin(db), {"enabled_packages": [code]})
        assert e.value.code == "NOT_READY"
        db.rollback()
    cfg = _settings(db)
    catalog = {p["code"]: p for p in camp.packages(db)}
    assert len(catalog) == 12 and {c for c, p in catalog.items() if p["purchasable"]} == {
        "MYHIGH5_CPM_CAMPAIGN", "ADVERTISER_CREDIT"}
    assert catalog["cpv"]["state"] == "NOT_READY" and catalog["cpc"]["state"] == "PACKAGE_DISABLED"
    with pytest.raises(camp.AdError) as e:                 # no minimum delivery threshold determined yet
        camp.update_settings(db, _admin(db), {"enabled_packages": ["cpc", "daily_city"]})
    assert e.value.code == "THRESHOLD_NOT_SET"
    db.rollback()
    cfg = _settings(db)
    assert {p["code"]: p for p in camp.packages(db)}["daily_city"]["state"] == "PACKAGE_DISABLED"
    camp.update_settings(db, _admin(db), {"enabled_packages": ["cpc", "daily_city"], "daily_city_min_impressions": 25})
    with pytest.raises(camp.AdError) as e:                 # cannot clear the threshold while Daily City is on
        camp.update_settings(db, _admin(db), {"daily_city_min_impressions": None})
    assert e.value.code == "THRESHOLD_NOT_SET"
    db.rollback()
    cfg = _settings(db, "cpc", "daily_city", threshold=25)
    catalog = {p["code"]: p for p in camp.packages(db)}
    assert catalog["cpc"]["purchasable"] and catalog["daily_city"]["purchasable"] and not catalog["cpv"]["purchasable"]
    cfg.campaigns_enabled = False                          # a closed program sells nothing
    assert not {p["code"] for p in camp.packages(db) if p["purchasable"]} & {"cpc", "daily_city"}


def test_4b_submission_is_refused_when_the_package_is_switched_off_after_drafting(world):
    db = world
    cfg = _settings(db, "cpc")
    adv = _user(db, "a4b@t.com")
    _fund(db, adv, "5.00")
    c = camp.create_campaign(db, adv, name="x", budget="1.00", start_at=T0, end_at=T0 + timedelta(days=1),
                             placements=["IN_FEED"], package="cpc")
    camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://example.com/")
    cfg.enabled_packages = []
    with pytest.raises(camp.AdError) as e:
        camp.submit_campaign(db, adv, c)
    assert e.value.code == "PACKAGE_DISABLED"
    assert camp.credit_balance(db, adv.id) == D("5.00")    # nothing allocated


# ---------------------------------------------------------------- 5-12 event qualification

def test_7_standard_cpm_is_unchanged_viewable_charged_once_clicks_are_evidence(world):
    db = world
    _settings(db)
    adv = _user(db, "c7@t.com")
    _fund(db, adv, "20.00")
    c = camp.create_campaign(db, adv, name="C", budget="10.00", start_at=T0 - timedelta(days=1),
                             end_at=T0 + timedelta(days=30), placements=["IN_FEED"])
    cr = camp.add_creative(db, c, headline="B", body=None, image_url=None, destination_url="https://example.com/")
    camp.submit_campaign(db, adv, c)
    admin = _admin(db)
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    camp.review_campaign(db, admin, c, approve=True, note="ok")
    v = _viewer()
    d = _serve(db, v)
    decision = db.get(AdvServeDecision, d["decision_id"])
    assert decision.package is None and decision.reserved_amount == D("0.000500")    # legacy path, as before
    assert _event(db, d, v, "VIEWABLE", at=T0 + timedelta(seconds=2)) == "RECORDED"
    assert _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=3), allow_click=True) == "RECORDED"
    assert dl.validate_pending(db, now=T0 + timedelta(seconds=5)) == {"valid": 2, "invalid": 0}
    db.refresh(c)
    assert (c.spent, c.reserved) == (D("0.000500"), D("0"))                            # one charge only
    click = db.query(AdvImpressionEvent).filter_by(event_type="CLICK").one()
    assert (click.charged_amount, click.package) == (D("0"), "cpm")


def test_5_6_8_10_cpc_bills_one_valid_click_per_decision_and_rejects_the_rest(world):
    db = world
    _settings(db, "cpc")
    adv = _user(db, "c10@t.com")
    _fund(db, adv, "10.00")
    c, _cr = _live(db, adv, "cpc", budget="1.00")
    v = _viewer()
    d = _serve(db, v)
    assert d["fill"] and d["creative"]["click_url"] == f"/api/v1/ads/click/{d['decision_id']}"
    db.refresh(c)
    assert c.reserved == D("0.050000")                                                   # one click reserved
    assert _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=3)) == "INVALID_TYPE"      # never a beacon
    assert _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=3), allow_click=True,
                  action="SHARE") == "UNSUPPORTED_ACTION"
    _event(db, d, v, "SERVED", at=T0 + timedelta(seconds=1))
    _event(db, d, v, "VIEWABLE", at=T0 + timedelta(seconds=2))
    assert _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=4), allow_click=True) == "RECORDED"
    assert _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=5), allow_click=True) == "DUPLICATE"
    dl.validate_pending(db, now=T0 + timedelta(seconds=6))
    db.refresh(c)
    assert (c.spent, c.reserved) == (D("0.050000"), D("0"))
    assert db.query(AdvImpressionEvent).filter_by(event_type="VIEWABLE").one().charged_amount == D("0")

    # Rejected clicks: never rendered, too fast, bot, self-click. Each releases its reservation.
    cases = {"NOT_RENDERED": dict(served=False, after=3), "TOO_FAST": dict(served=True, after=0.5),
             "BOT": dict(served=True, after=3, ua="python-requests/2.31")}
    for reason, case in cases.items():
        vv = _viewer() if reason != "BOT" else dl.viewer_hash(None, "10.9.9.9", case["ua"])
        dd = _serve(db, vv)
        if case["served"]:
            _event(db, dd, vv, "SERVED", at=T0 + timedelta(milliseconds=100), ua=case.get("ua", UA))
        _event(db, dd, vv, "CLICK", at=T0 + timedelta(seconds=case["after"]), allow_click=True, ua=case.get("ua", UA))
        dl.validate_pending(db, now=T0 + timedelta(seconds=10))
        ev = db.query(AdvImpressionEvent).filter_by(decision_id=dd["decision_id"], event_type="CLICK").one()
        assert (ev.validation_status, ev.invalid_reason) == ("INVALID", reason)
        assert db.get(AdvServeDecision, dd["decision_id"]).state == "RELEASED"
    self_viewer = dl.viewer_hash_for_user(adv.id)
    ds = _serve(db, self_viewer, user_id=adv.id)
    _event(db, ds, self_viewer, "SERVED", at=T0 + timedelta(milliseconds=100))
    _event(db, ds, self_viewer, "CLICK", at=T0 + timedelta(seconds=3), allow_click=True)
    dl.validate_pending(db, now=T0 + timedelta(seconds=10))
    assert db.query(AdvImpressionEvent).filter_by(decision_id=ds["decision_id"], event_type="CLICK").one() \
        .invalid_reason == "SELF_VIEW"
    db.refresh(c)
    assert (c.spent, c.reserved) == (D("0.050000"), D("0"))                              # still one charge
    assert _commissions(db) == 0                                                          # Phase A earns nobody


def test_11_engagement_bills_only_the_implemented_call_to_action_once(world):
    db = world
    _settings(db, "engagement")
    adv = _user(db, "e11@t.com")
    _fund(db, adv, "10.00")
    c, _ = _live(db, adv, "engagement", budget="1.00")
    assert pk.ENGAGEMENT_ACTIONS == ("CTA_CLICK",)                                        # save/share/follow: absent
    v = _viewer()
    d = _serve(db, v)
    _event(db, d, v, "VIEWABLE", at=T0 + timedelta(seconds=2))
    _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=3), allow_click=True)
    dl.validate_pending(db, now=T0 + timedelta(seconds=5))
    db.refresh(c)
    assert c.spent == D("0.020000")


def test_8_9_video_and_cpv_qualification_contract_is_server_bounded(world):
    db = world
    _settings(db)
    adv = _user(db, "v8@t.com")
    c = AdvCampaign(advertiser_user_id=adv.id, name="V", status="ACTIVE", pricing_model="CPV",
                    unit_rate_usd=D("0.005"), budget_total=D("1"), spent=0, reserved=0, placements=["IN_FEED"])
    db.add(c)
    db.flush()
    cr = AdvCreative(campaign_id=c.id, headline="v", destination_url="https://example.com/", review_status="APPROVED",
                     creative_format="VIDEO", video_duration_ms=30000)
    db.add(cr)
    db.flush()

    def check(kind, played, *, elapsed=60, ratio="0.8", duration=30000, fmt="VIDEO"):
        cr.video_duration_ms, cr.creative_format = duration, fmt
        dec = AdvServeDecision(id=str(uuid.uuid4()), slot_kind="IN_FEED", page_type="FEED", slot_key="k",
                               source="MYHIGH5", product="ORDINARY", campaign_id=c.id, creative_id=cr.id,
                               reserved_amount=0, state="RESERVED", viewer_hash="v", expires_at=T0 + timedelta(hours=1),
                               created_at=T0, package="cpv")
        ev = AdvImpressionEvent(event_id=str(uuid.uuid4()), decision_id=dec.id, event_type=kind,
                                received_at=T0 + timedelta(seconds=elapsed), visible_ratio=D(ratio), played_ms=played)
        return dl._quality_problem(db, ev, dec, T0)

    assert check("VIDEO_2S", 1999) == "NOT_PLAYED" and check("VIDEO_2S", 2000) is None      # two seconds
    assert check("VIDEO_VIEW", 9999) == "NOT_PLAYED" and check("VIDEO_VIEW", 10000) is None   # ten seconds
    assert check("VIDEO_VIEW", 8000, duration=8000) is None                                   # whole short video
    assert check("VIDEO_VIEW", 2000) == "NOT_PLAYED"            # the 2 s video standard never makes a CPV view
    assert check("VIDEO_2S", 5000, elapsed=3) == "IMPOSSIBLE_PLAYBACK"                        # more than wall clock
    assert check("VIDEO_VIEW", 31500, elapsed=60) == "IMPOSSIBLE_PLAYBACK"                    # more than the video
    assert check("VIDEO_2S", 3000, ratio="0.4") == "NOT_PLAYED"                                # not in view
    assert check("VIDEO_2S", 3000, fmt="IMAGE") == "NOT_A_VIDEO"                               # page load != playback
    # Not ready: video campaigns are never served.
    v = _viewer()
    assert not _serve(db, v)["fill"]


def _mp4(duration_ms=30000, timescale=1000, version=0, brand=b"isom"):
    ftyp = struct.pack(">I4s4sI4s", 20, b"ftyp", brand, 0, brand)
    if version == 0:
        body = bytes([0, 0, 0, 0]) + struct.pack(">IIII", 0, 0, timescale, duration_ms * timescale // 1000) + b"\0" * 80
    else:
        body = bytes([1, 0, 0, 0]) + struct.pack(">QQIQ", 0, 0, timescale, duration_ms * timescale // 1000) + b"\0" * 80
    mvhd = struct.pack(">I4s", 8 + len(body), b"mvhd") + body
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    return ftyp + moov + b"\0" * 64


def test_video_creative_validation_reads_the_duration_server_side(monkeypatch):
    assert ad_video.inspect("video/mp4", _mp4(30000)).duration_ms == 30000
    assert ad_video.inspect("video/mp4", _mp4(45000, timescale=90000, version=1)).duration_ms == 45000
    for content, mime, code in ((_mp4(61000), "video/mp4", "VIDEO_TOO_LONG"), (_mp4(500), "video/mp4", "VIDEO_TOO_SHORT"),
                                (_mp4(), "video/webm", "UNSUPPORTED_VIDEO"), (b"\x1aE\xdf\xa3" + b"\0" * 40, "video/mp4",
                                                                              "UNSUPPORTED_VIDEO"),
                                (_mp4()[:28], "video/mp4", "CORRUPT_VIDEO"),
                                (_mp4()[:20] + b"\0" * 40, "video/mp4", "NO_DURATION"), (b"", "video/mp4", "EMPTY_VIDEO")):
        with pytest.raises(ad_video.VideoError) as e:
            ad_video.inspect(mime, content)
        assert e.value.code == code, (code, e.value.code)
    monkeypatch.setattr(ad_video, "VIDEO_MAX_BYTES", 100)
    with pytest.raises(ad_video.VideoError) as e:
        ad_video.inspect("video/mp4", _mp4())
    assert e.value.code == "VIDEO_TOO_LARGE"
    assert ad_video.cpv_threshold_ms(30000) == 10000 and ad_video.cpv_threshold_ms(7000) == 7000
    assert ad_video.cpv_threshold_ms(None) is None


def test_12_lead_collection_is_closed_and_only_an_accepted_lead_is_billed_once(world):
    db = world
    _settings(db)
    adv = _user(db, "l12@t.com")
    c = AdvCampaign(advertiser_user_id=adv.id, name="L", status="ACTIVE", pricing_model="LEAD",
                    unit_rate_usd=D("0.25"), budget_total=D("0.50"), spent=0, reserved=0, placements=["IN_FEED"])
    db.add(c)
    db.flush()
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.submit(db, campaign_id=c.id, name="N", contact="n@example.com", consent=True, consent_version="v1")
    assert e.value.code == "NOT_READY"
    assert db.query(ad_leads.AdvLead).count() == 0                                            # nothing stored
    rec = lambda contact, **kw: ad_leads._record(db, campaign_id=c.id, name="N", contact=contact, consent=True,  # noqa: E731
                                                 consent_version="v1", decision_id=None, now=T0, **kw)
    lead = rec("Person@Example.com ")
    assert lead.contact_hash != "person@example.com" and len(lead.contact_hash) == 64        # no personal data
    with pytest.raises(ad_leads.LeadError) as e:
        rec("person@example.com")
    assert e.value.code == "DUPLICATE"
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads._record(db, campaign_id=c.id, name="N", contact="x@example.com", consent=False, consent_version="v1",
                         decision_id=None, now=T0)
    assert e.value.code == "CONSENT_REQUIRED"
    ad_leads.accept(db, lead.id, actor_id=adv.id, now=T0 + timedelta(days=1))
    db.refresh(c)
    assert (lead.status, c.spent, lead.charged_amount) == ("ACCEPTED", D("0.250000"), D("0.250000"))
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.accept(db, lead.id, now=T0 + timedelta(days=1))
    assert e.value.code == "ALREADY_DECIDED"
    second, third = rec("b@example.com"), rec("c@example.com")
    ad_leads.reject(db, second.id, reason="TEST_OR_FAKE", now=T0 + timedelta(days=2))
    # Silence is never acceptance (owner decision 5): after 7 days an unanswered lead EXPIRES, unbilled.
    assert ad_leads.expire_unanswered(db, now=T0 + timedelta(days=6)) == 0
    assert ad_leads.expire_unanswered(db, now=T0 + timedelta(days=8)) == 1
    assert ad_leads.expire_unanswered(db, now=T0 + timedelta(days=9)) == 0                  # once
    db.refresh(c)
    assert (third.status, third.charged_amount, c.spent) == ("EXPIRED", D("0"), D("0.250000"))
    for late in (lambda: ad_leads.accept(db, third.id, now=T0 + timedelta(days=8)),
                 lambda: ad_leads.reject(db, third.id, reason="DUPLICATE", now=T0 + timedelta(days=8))):
        with pytest.raises(ad_leads.LeadError) as e:
            late()
        assert e.value.code == "ALREADY_DECIDED"
    fourth = rec("d@example.com")
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.accept(db, fourth.id, now=T0 + timedelta(days=8))
    assert e.value.code == "WINDOW_CLOSED"                                                    # too late, never billed
    fifth, sixth = rec("e@example.com"), rec("f@example.com")
    ad_leads.accept(db, fifth.id, now=T0 + timedelta(days=1))
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.accept(db, sixth.id, now=T0 + timedelta(days=1))
    assert e.value.code == "BUDGET_EXHAUSTED"                                                 # never over budget
    db.refresh(c)
    assert c.spent == D("0.500000") and second.charged_amount == D("0")


# ---------------------------------------------------------------- 13-16 budget controls

def test_13_15_budget_and_daily_cap_are_never_exceeded_for_cpc(world):
    db = world
    _settings(db, "cpc")
    adv = _user(db, "b13@t.com")
    _fund(db, adv, "10.00")
    c, _ = _live(db, adv, "cpc", budget="0.10")
    served = [d for d in (_serve(db, _viewer()) for _ in range(5)) if d["fill"]]
    db.refresh(c)
    assert len(served) == 2 and c.reserved == D("0.100000")                                  # 2 clicks fit, never 3


def test_16_a_completed_campaign_serves_nothing_more_and_open_reservations_settle_once(world):
    db = world
    _settings(db, "cpc")
    adv = _user(db, "b16@t.com")
    _fund(db, adv, "10.00")
    c, _ = _live(db, adv, "cpc", budget="1.00")
    v = _viewer()
    d = _serve(db, v)
    camp.complete_campaign(db, c, reason="ENDED")
    assert not _serve(db, _viewer())["fill"]
    _event(db, d, v, "SERVED", at=T0 + timedelta(milliseconds=100))
    _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=3), allow_click=True)
    dl.validate_pending(db, now=T0 + timedelta(seconds=5))
    db.refresh(c)
    assert (c.spent, c.reserved) == (D("0.050000"), D("0"))         # the reservation made before is consumed once


# ---------------------------------------------------------------- 17-22 Daily City bookings

def _city(db, name="Nairobi"):
    cont = Continent(name=f"Africa-{uuid.uuid4().hex[:4]}")
    db.add(cont)
    db.flush()
    reg = Region(name="East", continent_id=cont.id)
    db.add(reg)
    db.flush()
    country = Country(name="Kenya", region_id=reg.id, code=uuid.uuid4().hex[:3].upper())
    db.add(country)
    db.flush()
    city = City(name=name, country_id=country.id)
    db.add(city)
    db.flush()
    return city


def _inventory(db, city, n, *, days_ago=1, status="VALID"):
    """n measured viewable impressions from verified residents of `city`, `days_ago` UTC days ago (synthetic)."""
    at = datetime.combine(datetime.utcnow().date() - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=9)
    for _ in range(n):
        did = str(uuid.uuid4())
        db.add(AdvServeDecision(id=did, slot_kind="IN_FEED", page_type="FEED", slot_key="k", source="ADSENSE",
                                product="ADSENSE", reserved_amount=0, state="UNPAID", viewer_hash="v" * 64,
                                expires_at=at + timedelta(minutes=15), created_at=at, updated_at=at,
                                viewer_city_id=city.id))
        db.flush()
        db.add(AdvImpressionEvent(event_id=str(uuid.uuid4()), decision_id=did, event_type="VIEWABLE", received_at=at,
                                  validation_status=status))
    db.flush()


def _resident(db, city, *, verified=True):
    u = _user(db, f"r-{uuid.uuid4().hex[:6]}@t.com")
    u.city_id, u.address_verified = city.id, verified
    db.flush()
    return u


def test_17_18_19_booking_rules_daily_city_only_non_exclusive(world):
    db = world
    _settings(db, "daily_city")
    city = _city(db)
    _inventory(db, city, 30)                                   # 1.00 verified impressions per day >= 1
    adv, other = _user(db, "d17@t.com"), _user(db, "d17b@t.com")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    kw = dict(name="D", start_at=None, end_at=None, placements=["IN_FEED"])
    c = camp.create_campaign(db, adv, package="daily_city", bookings={"city_id": city.id, "days": [day1, day1 + timedelta(days=1)]},
                             **kw)
    assert (c.budget_total, c.pricing_model, c.start_at.date(), c.end_at.date()) == (
        D("10.00"), "DAILY_CITY", day1, day1 + timedelta(days=2))
    assert db.query(AdvBooking).filter_by(campaign_id=c.id, status="BOOKED").count() == 2
    camp.create_campaign(db, other, package="daily_city", bookings={"city_id": city.id, "days": [day1]}, **kw)  # same day
    for bookings, code in (({"city_id": city.id, "days": []}, "INVALID_BOOKING"),
                           ({"city_id": city.id, "days": [day1 - timedelta(days=3)]}, "INVALID_BOOKING"),
                           ({"city_id": 999999, "days": [day1]}, "UNKNOWN_CITY")):
        with pytest.raises(camp.AdError) as e:
            camp.create_campaign(db, adv, package="daily_city", bookings=bookings, **kw)
        assert e.value.code == code
    with pytest.raises(camp.AdError) as e:
        camp.create_campaign(db, adv, package="daily_city", budget="9.00",
                             bookings={"city_id": city.id, "days": [day1, day1 + timedelta(days=1)]}, **kw)
    assert e.value.code == "BUDGET_MISMATCH"
    with pytest.raises(camp.AdError) as e:
        camp.create_campaign(db, adv, package="daily_local", bookings={"city_id": city.id, "days": [day1]}, **kw)
    assert e.value.code == "NOT_READY"
    with pytest.raises(camp.AdError) as e:
        camp.update_campaign(db, adv, c, {"budget": D("5.00")})
    assert e.value.code == "BOOKING_FIXED"


def test_20_21_22_city_delivery_needs_verified_location_and_settles_once(world):
    db = world
    _settings(db, "daily_city")
    city, elsewhere = _city(db), _city(db, "Mombasa")
    _inventory(db, city, 30)
    adv = _user(db, "d20@t.com")
    _fund(db, adv, "20.00")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    c = camp.create_campaign(db, adv, name="D", package="daily_city", placements=["IN_FEED", "IN_CONTENT"],
                             bookings={"city_id": city.id, "days": [day1, day1 + timedelta(days=1)]})
    cr = camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://example.com/")
    camp.submit_campaign(db, adv, c)
    admin = _admin(db)
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    camp.review_campaign(db, admin, c, approve=True, note="ok")
    assert camp.credit_balance(db, adv.id) == D("10.00")                                     # 20 - 10 booked
    at = datetime.combine(day1, datetime.min.time()) + timedelta(hours=10)
    resident, unverified, outsider = _resident(db, city), _resident(db, city, verified=False), _resident(db, elsewhere)
    assert not _serve(db, _viewer(), at=at)["fill"]                                           # anonymous: never
    assert not _serve(db, _viewer(), at=at, user_id=unverified.id)["fill"]                   # unverified address
    assert not _serve(db, _viewer(), at=at, user_id=outsider.id)["fill"]                     # another city
    v = dl.viewer_hash_for_user(resident.id)
    d = _serve(db, v, at=at, user_id=resident.id)
    decision = db.get(AdvServeDecision, d["decision_id"])
    assert d["fill"] and (decision.state, decision.reserved_amount, decision.viewer_city_id) == ("UNPAID", D("0"), city.id)
    _event(db, d, v, "VIEWABLE", at=at + timedelta(seconds=2))
    dl.validate_pending(db, now=at + timedelta(seconds=5))
    db.refresh(c)
    assert c.spent == D("0")                                                                   # impressions are free

    after = datetime.combine(day1 + timedelta(days=2), datetime.min.time()) + timedelta(hours=3)
    assert dl.settle_bookings(db, now=after) == 2
    b1, b2 = db.query(AdvBooking).filter_by(campaign_id=c.id).order_by(AdvBooking.day).all()
    assert (b1.status, b1.charged_amount, b1.valid_impressions, b1.entry_impressions) == ("EARNED", D("5"), 1, 0)
    assert b1.evidence["impressions_by_page_type"] == {"FEED": 1}
    assert (b2.status, b2.charged_amount, b2.valid_impressions) == ("RETURNED", D("0"), 0)
    db.refresh(c)
    assert (c.budget_total, c.spent) == (D("5.00"), D("5.000000"))
    assert camp.credit_balance(db, adv.id) == D("15.00")                                      # zero-delivery day back
    assert dl.settle_bookings(db, now=after + timedelta(hours=1)) == 0                        # never twice
    assert db.query(AdvCreditMovement).filter(AdvCreditMovement.idempotency_key.like("booking:%")).count() == 1
    dl.recognize_closed_days(db, now=after)
    assert _balance(db, "4020") == D("-5.00")                                                 # fee earned once
    dl.complete_due_campaigns(db, now=after)
    db.refresh(c)
    assert c.settled_at is not None and camp.credit_balance(db, adv.id) == D("15.00")        # nothing left to return
    assert _commissions(db) == 0 and db.query(AdvAllocation).count() == 0                     # no earning in Phase A
    _ledger_balanced(db)


def test_booking_needs_measured_verified_inventory_in_the_city(world):
    """Owner decision 1: no booking without reliable geographic attribution AND measurable eligible inventory."""
    db = world
    _settings(db, "daily_city", threshold=2)
    city = _city(db)
    adv = _user(db, "inv@t.com")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    book = lambda: camp.create_campaign(db, adv, name="D", package="daily_city", placements=["IN_FEED"],  # noqa: E731
                                        bookings={"city_id": city.id, "days": [day1]})
    with pytest.raises(camp.AdError) as e:
        book()                                                                  # no measured audience at all
    assert e.value.code == "INSUFFICIENT_INVENTORY"
    _inventory(db, city, 59)                                                     # 1.96 per day < 2
    _inventory(db, city, 40, status="INVALID")                                   # invalid views never count
    _inventory(db, city, 40, days_ago=31)                                        # outside the 30-day window
    _inventory(db, city, 40, days_ago=0)                                         # today is not a full day
    assert camp.city_inventory(db, city.id)["daily_average"] == D("1.96")
    with pytest.raises(camp.AdError) as e:
        book()
    assert e.value.code == "INSUFFICIENT_INVENTORY"
    _inventory(db, city, 1)
    c = book()
    assert db.query(AdvBooking).filter_by(campaign_id=c.id).one().min_impressions == 2   # threshold snapshotted


def test_every_decision_records_only_a_verified_city(world):
    db = world
    _settings(db, "cpc")
    city = _city(db)
    adv = _user(db, "vc@t.com")
    _fund(db, adv, "10.00")
    _live(db, adv, "cpc", budget="1.00")
    verified, unverified = _resident(db, city), _resident(db, city, verified=False)
    seen = {}
    for label, uid in (("verified", verified.id), ("unverified", unverified.id), ("anonymous", None)):
        d = _serve(db, _viewer(), user_id=uid)
        seen[label] = db.get(AdvServeDecision, d["decision_id"]).viewer_city_id
    assert seen == {"verified": city.id, "unverified": None, "anonymous": None}


def test_booked_day_below_the_delivery_threshold_is_returned_not_charged(world):
    db = world
    _settings(db, "daily_city", threshold=2)
    city = _city(db)
    _inventory(db, city, 60)
    adv = _user(db, "thr@t.com")
    _fund(db, adv, "10.00")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    c = camp.create_campaign(db, adv, name="D", package="daily_city", placements=["IN_FEED"],
                             bookings={"city_id": city.id, "days": [day1]})
    cr = camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://example.com/")
    camp.submit_campaign(db, adv, c)
    admin = _admin(db)
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    camp.review_campaign(db, admin, c, approve=True, note="ok")
    at = datetime.combine(day1, datetime.min.time()) + timedelta(hours=10)
    resident = _resident(db, city)
    v = dl.viewer_hash_for_user(resident.id)
    d = _serve(db, v, at=at, user_id=resident.id)
    _event(db, d, v, "VIEWABLE", at=at + timedelta(seconds=2))
    dl.validate_pending(db, now=at + timedelta(seconds=5))
    camp.update_settings(db, admin, {"daily_city_min_impressions": 1})        # a later change never reprices it
    assert dl.settle_bookings(db, now=at + timedelta(days=1)) == 1
    b = db.query(AdvBooking).filter_by(campaign_id=c.id).one()
    assert (b.status, b.valid_impressions, b.charged_amount, b.evidence["min_impressions"]) == ("RETURNED", 1, D("0"), 2)
    assert camp.credit_balance(db, adv.id) == D("10.00")
    db.refresh(c)
    assert c.spent == D("0")


def test_cancelled_booking_campaign_returns_everything_and_owes_no_day(world):
    db = world
    _settings(db, "daily_city")
    city = _city(db)
    _inventory(db, city, 30)
    adv = _user(db, "d22@t.com")
    _fund(db, adv, "10.00")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    c = camp.create_campaign(db, adv, name="D", package="daily_city", placements=["IN_FEED"],
                             bookings={"city_id": city.id, "days": [day1]})
    camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://example.com/")
    camp.submit_campaign(db, adv, c)
    camp.cancel_campaign(db, adv, c)
    assert camp.credit_balance(db, adv.id) == D("10.00")
    assert db.query(AdvBooking).filter_by(campaign_id=c.id).one().status == "CANCELLED"


# ---------------------------------------------------------------- 23-30 precision, reversal, provenance

def test_23_24_six_decimal_charges_and_whole_cent_recognition_without_drift(world):
    db = world
    _settings(db, "cpc")
    adv = _user(db, "p23@t.com")
    _fund(db, adv, "10.00")
    c, _ = _live(db, adv, "cpc", rate="0.050001", budget="1.00")
    for i in range(3):
        v = _viewer()
        d = _serve(db, v)
        _event(db, d, v, "SERVED", at=T0 + timedelta(milliseconds=100))
        _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=2 + i), allow_click=True)
    dl.validate_pending(db, now=T0 + timedelta(seconds=10))
    db.refresh(c)
    assert c.spent == D("0.150003")                                                           # exact, not 0.15
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    assert _balance(db, "4020") == D("-0.15")                                                 # floor of the total
    assert camp.floor_cents(c.spent) == D("0.15")                                             # 0.000003 never charged


def test_26_invalid_click_charges_are_reversed_and_credited_back(world):
    db = world
    _settings(db, "cpc")
    adv = _user(db, "r26@t.com")
    _fund(db, adv, "10.00")
    c, _ = _live(db, adv, "cpc", budget="1.00")
    v = _viewer()
    d = _serve(db, v)
    _event(db, d, v, "SERVED", at=T0 + timedelta(milliseconds=100))
    _event(db, d, v, "CLICK", at=T0 + timedelta(seconds=3), allow_click=True)
    dl.validate_pending(db, now=T0 + timedelta(seconds=5))
    click = db.query(AdvImpressionEvent).filter_by(event_type="CLICK").one()
    out = dl.reverse_invalid_activity(db, event_ids=[click.id], reason="click farm", actor_id=_admin(db).id)
    db.refresh(c)
    assert out["reversed"] == 1 and c.spent == D("0")


def test_27_28_credit_provenance_by_funding_route_and_no_commission_on_deposits(world):
    db = world
    _settings(db)
    adv = _user(db, "f27@t.com")
    cash = _fund(db, adv, "30.00")
    cash.payment_provider = "soncopay"
    wallet = _fund(db, adv, "12.50")
    wallet.payment_provider = "internal_wallet"
    db.flush()
    prov = camp.credit_provenance(db, adv.id)
    assert prov["soncopay"]["net"] == D("30.00") and prov["soncopay"]["external_refund_route"] == "MANUAL_FINANCE_SONCOPAY"
    assert prov["internal_wallet"]["net"] == D("12.50")
    assert prov["internal_wallet"]["external_refund_route"] == "RETURN_TO_EARNINGS_ONLY"
    assert _commissions(db) == 0                                                              # deposits earn nobody


# ---------------------------------------------------------------- CPC redirect safety (API)

def test_10b_click_redirect_goes_only_to_the_reviewed_destination(world, client):
    db = world
    _settings(db, "cpc")
    adv = _user(db, "r10@t.com")
    _fund(db, adv, "10.00")
    c, cr = _live(db, adv, "cpc", budget="1.00")
    v = _viewer()
    d = _serve(db, v)
    db.commit()
    unknown = client.get(f"/api/v1/ads/click/{uuid.uuid4()}", follow_redirects=False)
    assert unknown.status_code == 404 and "location" not in unknown.headers                 # redirects nowhere
    assert client.get("/api/v1/ads/click/not-a-uuid", follow_redirects=False).status_code == 404
    hop = client.get(f"/api/v1/ads/click/{d['decision_id']}?next=https://evil.example/", follow_redirects=False)
    assert hop.status_code == 302 and hop.headers["location"] == "https://example.com/x"    # never the query string
    assert db.query(AdvImpressionEvent).filter_by(decision_id=d["decision_id"], event_type="CLICK").count() == 1
    cr.destination_url = "javascript:alert(1)"                                             # tampered row
    db.commit()
    assert client.get(f"/api/v1/ads/click/{d['decision_id']}", follow_redirects=False).status_code == 404
    adsense = AdvServeDecision(id=str(uuid.uuid4()), slot_kind="IN_FEED", page_type="FEED", slot_key="k",
                               source="ADSENSE", product="ADSENSE", reserved_amount=0, state="UNPAID", viewer_hash="v",
                               expires_at=T0 + timedelta(hours=1), created_at=T0)
    db.add(adsense)
    db.commit()
    assert client.get(f"/api/v1/ads/click/{adsense.id}", follow_redirects=False).status_code == 404


def test_click_beacons_cannot_be_posted_by_a_client(world, client):
    db = world
    _settings(db)
    db.commit()
    body = {"decision_id": str(uuid.uuid4()), "event_id": str(uuid.uuid4()), "event_type": "CLICK"}
    assert client.post("/api/v1/ads/events", json=body).status_code == 422                 # not an accepted type
