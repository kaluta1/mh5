"""Advertising campaign & creative workflow (2026-11-05): drafts, text limits, call-to-action, HTTPS destination,
revisions that keep the approved version serving, media checks (image fit per placement, server-verified video),
package catalog and per-package estimates, explicit targeting without implicit widening, time zones, display
status and non-delivery reasons, structured moderation issues, daily report reconciliation, members' daily
estimates, and the advertiser's direct-sponsor commission on recognized charges (switch OFF by default).
SYNTHETIC data only."""
from __future__ import annotations

import struct
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.advertising_v2 import AdvCampaignDay, AdvCreative, AdvImpressionEvent
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.business_model import AffiliateRateQualification
from app.models.contests import SeasonLevel
from app.models.geography import Continent, Country, Region
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_video, ad_workflow as wf
from tests.unit.test_advertising_program import (T0, _balance, _configure, _entry, _fund, _ledger_balanced, _season,
                                                 _validate, _view)
from tests.unit.test_new_business_model import _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit
D = Decimal
COMPLETE = {"headline": "Fresh coffee daily", "body": "Roasted this morning.", "display_name": "Acme Coffee",
            "cta_code": "SHOP_NOW", "destination_url": "https://www.acme.example/coffee"}


def _admin(db):
    return _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")


def _draft_campaign(db, adv, **kw):
    args = dict(name="W", budget="10.00", start_at=T0 - timedelta(days=1), end_at=T0 + timedelta(days=30),
                placements=["IN_FEED", "SIDEBAR", "IN_CONTENT"])
    args.update(kw)
    return camp.create_campaign(db, adv, **args)


def _live(db, adv, *, budget="10.00", **kw):
    c = _draft_campaign(db, adv, budget=budget, **kw)
    cr = wf.create_creative(db, c, dict(COMPLETE), actor_id=adv.id, draft=False)
    camp.submit_campaign(db, adv, c)
    admin = _admin(db)
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    camp.review_campaign(db, admin, c, approve=True, note="ok")
    return c, cr


# ---------------------------------------------------------------- creatives: drafts, limits, destination

def test_incomplete_draft_is_saved_reopened_and_needs_completion_before_review(world):
    db = world
    _configure(db, "0.50")
    adv = _user(db, "wf1@t.com")
    c = _draft_campaign(db, adv)
    cr = wf.create_creative(db, c, {"headline": "Half done"}, actor_id=adv.id)
    assert cr.review_status == "DRAFT"
    view = wf.creative_view(db, db.get(AdvCreative, cr.id))                 # reopened
    assert view["headline"] == "Half done"
    assert set(view["missing_for_review"]) == {"display_name", "cta_code", "destination_url"}
    with pytest.raises(camp.AdError) as e:
        wf.submit_creative(db, c, cr, actor_id=adv.id)
    assert e.value.code == "CREATIVE_INCOMPLETE"
    _fund(db, adv, "20.00")
    with pytest.raises(camp.AdError) as e:                                  # an incomplete draft blocks submission
        camp.submit_campaign(db, adv, c)
    assert e.value.code == "CREATIVE_INCOMPLETE"
    wf.edit_creative(db, c, cr, {k: v for k, v in COMPLETE.items() if k != "headline"}, actor_id=adv.id)
    camp.submit_campaign(db, adv, c)
    assert (cr.review_status, c.status) == ("PENDING", "PENDING_REVIEW")


@pytest.mark.parametrize("field,value,code", [
    ("headline", "x" * 41, "TEXT_TOO_LONG"), ("body", "x" * 126, "TEXT_TOO_LONG"),
    ("display_name", "x" * 61, "TEXT_TOO_LONG"), ("cta_code", "CLICK_HERE", "INVALID_CTA"),
    ("destination_url", "http://acme.example/", "HTTPS_REQUIRED"),
    ("destination_url", "https://127.0.0.1/x", "INVALID_URL"),
])
def test_text_limits_cta_and_https_are_enforced_on_the_server(world, field, value, code):
    db = world
    _configure(db, "0.50")
    adv = _user(db, f"wf2-{uuid.uuid4().hex[:5]}@t.com")
    c = _draft_campaign(db, adv)
    with pytest.raises(camp.AdError) as e:
        wf.create_creative(db, c, {**COMPLETE, field: value}, actor_id=adv.id)
    assert e.value.code == code


def test_limits_are_exact_and_domain_is_displayed(world):
    db = world
    _configure(db, "0.50")
    adv = _user(db, "wf3@t.com")
    c = _draft_campaign(db, adv)
    cr = wf.create_creative(db, c, {**COMPLETE, "headline": "h" * 40, "body": "b" * 125, "display_name": "d" * 60},
                            actor_id=adv.id, draft=False)
    view = wf.creative_view(db, cr)
    assert (cr.review_status, view["destination_domain"], view["cta_label"]) == ("PENDING", "acme.example", "Shop now")
    assert view["sponsored_label"] == "Sponsored"


def test_creative_images_must_belong_to_the_advertiser(world):
    db = world
    _configure(db, "0.50")
    adv, other = _user(db, "wf4@t.com"), _user(db, "wf4o@t.com")
    c = _draft_campaign(db, adv)
    with pytest.raises(camp.AdError) as e:
        wf.create_creative(db, c, {**COMPLETE, "image_url": f"/api/v1/media/file/{other.id}/{uuid.uuid4()}.png"},
                           actor_id=adv.id)
    assert e.value.code == "IMAGE_NOT_OWNED"
    ok = wf.create_creative(db, c, {**COMPLETE, "image_url": f"/api/v1/media/file/{adv.id}/{uuid.uuid4()}.png"},
                            actor_id=adv.id)
    assert ok.image_url.startswith(f"/api/v1/media/file/{adv.id}/")


# ---------------------------------------------------------------- revisions: fresh approval, approved keeps serving

def test_changing_an_approved_creative_needs_fresh_approval_and_the_approved_one_keeps_serving(world):
    db = world
    _configure(db, "4.00")
    adv = _user(db, "wf5@t.com")
    _fund(db, adv, "50.00")
    c, cr = _live(db, adv)
    revision = wf.edit_creative(db, c, cr, {"headline": "New headline"}, actor_id=adv.id)
    assert revision.id != cr.id and revision.supersedes_creative_id == cr.id and revision.review_status == "DRAFT"
    assert cr.review_status == "APPROVED" and cr.headline == "Fresh coffee daily"
    again = wf.edit_creative(db, c, cr, {"body": "Second edit"}, actor_id=adv.id)
    assert again.id == revision.id                                          # one open revision at a time
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer="v1", now=T0,
                  allowed_sources={"myhigh5_ads"})
    assert d["creative"]["headline"] == "Fresh coffee daily"                # only approved content is served
    wf.submit_creative(db, c, revision, actor_id=adv.id)
    admin = _admin(db)
    camp.review_creative(db, admin, revision, approve=False, note="", issues=[{"category": "COPY", "note": "typo"}])
    assert cr.review_status == "APPROVED" and revision.review_issues == [{"category": "COPY", "note": "typo"}]
    wf.edit_creative(db, c, revision, {"headline": "Fixed headline"}, actor_id=adv.id)
    assert revision.review_status == "DRAFT"
    wf.submit_creative(db, c, revision, actor_id=adv.id)
    camp.review_creative(db, admin, revision, approve=True, note="ok")
    assert (cr.review_status, revision.review_status) == ("ARCHIVED", "APPROVED")
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer="v2", now=T0,
                  allowed_sources={"myhigh5_ads"})
    assert d["creative"]["headline"] == "Fixed headline"
    assert d["creative"]["cta_code"] == "SHOP_NOW" and d["creative"]["display_name"] == "Acme Coffee"
    with pytest.raises(camp.AdError):
        wf.edit_creative(db, c, cr, {"headline": "x"}, actor_id=adv.id)    # an archived version is read-only


def test_new_media_on_an_approved_creative_creates_a_revision(world):
    db = world
    _configure(db, "4.00")
    adv = _user(db, "wf6@t.com")
    _fund(db, adv, "50.00")
    c, cr = _live(db, adv)
    url = f"/api/v1/media/file/{adv.id}/{uuid.uuid4()}.png"
    rev = wf.attach_media(db, c, cr, actor_id=adv.id, image_url=url, image_mime="image/png", image_width=1200,
                          image_height=1200, image_bytes=1000)
    assert rev.id != cr.id and cr.review_status == "APPROVED" and cr.image_url is None and rev.image_url == url


# ---------------------------------------------------------------- media

def test_image_fit_is_reported_per_rendered_placement():
    square = wf.image_compatibility(1200, 1200, "image/jpeg", 100_000)
    assert square["IN_FEED"]["compatible"] and square["IN_CONTENT"]["compatible"]
    assert not square["SIDEBAR"]["compatible"] and "600x500" in square["SIDEBAR"]["message"]
    assert wf.image_compatibility(1200, 1500)["IN_FEED"]["compatible"]
    assert wf.image_compatibility(600, 500)["SIDEBAR"]["compatible"]
    small = wf.image_compatibility(200, 200, "image/png", 1000)
    assert not any(v["compatible"] for v in small.values())
    ok = {"media_type": "image", "content_type": "image/webp", "file_size": 4 * 1024 * 1024, "width": 1200, "height": 1500}
    camp.check_creative_image(ok)
    for bad in ({**ok, "content_type": "image/gif"}, {**ok, "file_size": 5 * 1024 * 1024 + 1}, {**ok, "width": 299}):
        with pytest.raises(camp.AdError):
            camp.check_creative_image(bad)


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _mp4(seconds=15, size=(1080, 1920), vcodec=b"avc1", acodec=b"mp4a", audio=True, pad=0) -> bytes:
    def trak(handler, codec, w=0, h=0):
        tkhd = _box(b"tkhd", b"\0" * 76 + struct.pack(">II", w << 16, h << 16))
        hdlr = _box(b"hdlr", b"\0" * 8 + handler + b"\0" * 13)
        stsd = _box(b"stsd", b"\0" * 4 + struct.pack(">I", 1) + struct.pack(">I", 16) + codec + b"\0" * 8)
        minf = _box(b"minf", _box(b"stbl", stsd))
        return _box(b"trak", tkhd + _box(b"mdia", hdlr + minf))
    mvhd = _box(b"mvhd", b"\0" * 12 + struct.pack(">II", 1000, int(seconds * 1000)) + b"\0" * 80)
    tracks = trak(b"vide", vcodec, *size) + (trak(b"soun", acodec) if audio else b"")
    return (_box(b"ftyp", b"isom" + b"\0\0\0\0" + b"isomavc1") + _box(b"moov", mvhd + tracks)
            + (_box(b"free", b"\0" * pad) if pad else b""))


def test_ad_video_is_verified_from_the_file_on_the_server():
    info = ad_video.inspect_ad_video("video/mp4", _mp4())
    assert (info.width, info.height, info.duration_ms, info.video_codec, info.audio_codec) == (
        1080, 1920, 15000, "H.264", "AAC")
    assert ad_video.inspect_ad_video("video/mp4", _mp4(size=(1080, 1080), audio=False)).audio_codec is None
    for content, code in ((_mp4(seconds=5), "VIDEO_DURATION"), (_mp4(seconds=31), "VIDEO_DURATION"),
                          (_mp4(size=(720, 1280)), "UNSUPPORTED_SIZE"), (_mp4(vcodec=b"hvc1"), "UNSUPPORTED_CODEC"),
                          (_mp4(acodec=b"ac-3"), "UNSUPPORTED_CODEC"), (b"\0" * 64, "UNSUPPORTED_VIDEO")):
        with pytest.raises(ad_video.VideoError) as e:
            ad_video.inspect_ad_video("video/mp4", content)
        assert e.value.code == code
    with pytest.raises(ad_video.VideoError) as e:
        ad_video.inspect_ad_video("video/quicktime", _mp4())
    assert e.value.code == "UNSUPPORTED_VIDEO"
    with pytest.raises(ad_video.VideoError) as e:
        ad_video.inspect_ad_video("video/mp4", _mp4(pad=ad_video.AD_VIDEO_MAX_BYTES))
    assert e.value.code == "VIDEO_TOO_LARGE"
    assert ad_video.AD_VIDEO_MAX_BYTES <= ad_video.AD_VIDEO_SPEC_MAX_BYTES
    assert ad_video.rules()["delivery"].startswith("Not delivered yet")


# ---------------------------------------------------------------- packages and estimates

def test_catalog_shows_package_terms_and_keeps_unready_packages_disabled_with_reasons(world):
    db = world
    cfg = _configure(db, "0.50")
    cfg.min_campaign_budget_usd = D("10.00")
    cat = {p["code"]: p for p in wf.package_catalog(cfg)}
    assert list(cat) == ["cpm", "cpm_video", "cpc", "cpv", "engagement", "lead", "daily_local", "daily_city"]
    assert (cat["cpm"]["price"], cat["cpm"]["minimum_budget"], cat["cpm"]["purchasable"]) == ("0.50", "10.00", True)
    assert cat["cpc"]["price_label"] == "0.05 USD per one valid click" and cat["cpc"]["state"] == "PACKAGE_DISABLED"
    for code in ("cpm_video", "cpv", "lead", "daily_local", "daily_city"):
        assert cat[code]["state"] == "NOT_READY" and cat[code]["disabled_reason"] and not cat[code]["can_draft"]
    assert cat["cpv"]["supported_media"] == ["VIDEO"] and "10 seconds" in cat["cpv"]["billable_event"]


def test_estimates_are_per_package_never_cpm_for_other_packages(world):
    db = world
    cfg = _configure(db, "0.50")
    cpm = wf.package_estimate(cfg, "cpm", "10.00")
    assert (cpm["units"], cpm["unit"]) == (20000, "valid viewable impressions")
    cpc = wf.package_estimate(cfg, "cpc", "1.00")
    assert (cpc["units"], cpc["unit"], cpc["rate"]) == (20, "valid clicks", "0.050000")
    assert wf.package_estimate(cfg, "engagement", "1.00", "0.04")["units"] == 25
    assert wf.package_estimate(cfg, "daily_city", "15.00")["units"] == 3
    with pytest.raises(camp.AdError):
        wf.package_estimate(cfg, "cpc", "1.00", "0.01")                    # below the approved floor


# ---------------------------------------------------------------- targeting and schedule

def _kenya(db):
    cont = Continent(name=f"Africa-{uuid.uuid4().hex[:4]}")
    db.add(cont)
    db.flush()
    reg = Region(name="East", continent_id=cont.id)
    db.add(reg)
    db.flush()
    for name, code in (("Kenya", "KE"), ("Uganda", "UG")):
        db.add(Country(name=name, region_id=reg.id, code=code))
    db.flush()


def test_targeting_is_explicit_and_clearing_never_widens(world):
    db = world
    _configure(db, "0.50")
    _kenya(db)
    adv = _user(db, "wf7@t.com")
    with pytest.raises(camp.AdError) as e:
        _draft_campaign(db, adv, targeting={"countries_mode": "LIST", "countries": []})
    assert e.value.code == "TARGETING_EMPTY"
    with pytest.raises(camp.AdError) as e:
        _draft_campaign(db, adv, targeting={"countries": ["ZZ"]})
    assert e.value.code == "UNKNOWN_COUNTRY"
    c = _draft_campaign(db, adv, placements=["IN_FEED", "SIDEBAR"], targeting={"countries": ["ke"], "page_types": ["FEED"]})
    assert c.targeting == {"countries": ["KE"], "countries_mode": "LIST", "page_types": ["FEED"],
                           "page_types_mode": "LIST"}
    with pytest.raises(camp.AdError) as e:
        camp.update_campaign(db, adv, c, {"countries": []})                # cleared list: refused, not "everywhere"
    assert e.value.code == "TARGETING_EMPTY"
    camp.update_campaign(db, adv, c, {"countries_mode": "ALL"})
    assert (c.targeting["countries_mode"], c.targeting["countries"]) == ("ALL", [])
    assert c.targeting["page_types"] == ["FEED"]                            # untouched selection is preserved
    with pytest.raises(camp.AdError) as e:
        _draft_campaign(db, adv, placements=["IN_FEED"], targeting={"page_types": ["CONTEST_ENTRY"]})
    assert e.value.code == "PLACEMENT_PAGE_MISMATCH"
    catalog_names = dict(wf.known_countries(db))
    assert catalog_names["KE"] == "Kenya"


def test_legacy_targeting_is_preserved_and_still_serves(world):
    db = world
    _configure(db, "4.00")
    adv = _user(db, "wf8@t.com")
    _fund(db, adv, "50.00")
    c, _ = _live(db, adv)
    c.targeting = {"countries": [], "page_types": []}                       # a campaign written before the workflow
    db.flush()
    view = wf.campaign_view(db, c)
    assert view["targeting"]["countries_mode"] == "ALL" and view["targeting"]["page_types_mode"] == "ALL"
    assert dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer="v", now=T0,
                     allowed_sources={"myhigh5_ads"})["fill"]


def test_time_zones_are_converted_to_utc_and_never_dropped():
    assert wf.to_utc(datetime(2026, 11, 10, 9, 0), "Africa/Nairobi") == datetime(2026, 11, 10, 6, 0)
    aware = datetime(2026, 11, 10, 9, 0, tzinfo=timezone(timedelta(hours=3)))
    assert wf.to_utc(aware, None) == datetime(2026, 11, 10, 6, 0)          # the offset is honoured
    assert wf.to_utc(aware, "America/New_York") == datetime(2026, 11, 10, 6, 0)
    assert wf.to_utc(datetime(2026, 11, 10, 9, 0), None) == datetime(2026, 11, 10, 9, 0)
    with pytest.raises(camp.AdError) as e:
        wf.check_timezone("Mars/Base")
    assert e.value.code == "INVALID_TIMEZONE"


def test_start_after_approval_scheduled_status_and_reasons(world):
    db = world
    cfg = _configure(db, "4.00")
    adv = _user(db, "wf9@t.com")
    _fund(db, adv, "50.00")
    c = _draft_campaign(db, adv, start_at=None, end_at=datetime.utcnow() + timedelta(days=10), timezone="Africa/Nairobi")
    assert c.start_at is None and wf.schedule_view(c)["starts_after_approval"]
    cr = wf.create_creative(db, c, dict(COMPLETE), actor_id=adv.id, draft=False)
    camp.submit_campaign(db, adv, c)
    assert wf.display_status(c) == "SUBMITTED"
    admin = _admin(db)
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    before = datetime.utcnow()
    camp.review_campaign(db, admin, c, approve=True, note="ok")
    assert c.start_at is not None and c.start_at >= before - timedelta(seconds=1)
    assert wf.display_status(c) == "ACTIVE" and wf.non_delivery_reasons(db, c, cfg) == []
    view = wf.schedule_view(c)
    assert view["timezone"] == "Africa/Nairobi" and view["end_at_local"].endswith("+03:00")
    c.start_at = datetime.utcnow() + timedelta(days=1)
    assert wf.display_status(c) == "SCHEDULED"
    assert [r["code"] for r in wf.non_delivery_reasons(db, c, cfg)] == ["NOT_STARTED"]
    camp.set_paused(db, adv, c, paused=True)
    assert wf.display_status(c) == "PAUSED"
    cfg.campaigns_enabled = False
    codes = {r["code"] for r in wf.non_delivery_reasons(db, c, cfg)}
    assert {"PAUSED", "CAMPAIGNS_SWITCHED_OFF", "NOT_STARTED"} <= codes
    cfg.campaigns_enabled = True
    c.start_at = datetime.utcnow() - timedelta(hours=1)
    camp.set_paused(db, adv, c, paused=False)
    camp.complete_campaign(db, c, reason="ADVERTISER_STOPPED", actor_id=adv.id)
    assert wf.display_status(c) == "ENDED"


def test_daily_limit_reached_is_explained(world):
    db = world
    cfg = _configure(db, "1000.00")
    cfg.frequency_cap_per_day = 100
    adv = _user(db, "wf10@t.com")
    _fund(db, adv, "50.00")
    now = datetime.utcnow()
    c, _ = _live(db, adv, daily_cap="1.00", start_at=now - timedelta(days=1), end_at=now + timedelta(days=5))
    _view(db, page_type="FEED", slot_kind="IN_FEED", at=now)
    assert "DAILY_LIMIT_REACHED" in {r["code"] for r in wf.non_delivery_reasons(db, c, cfg, now)}


# ---------------------------------------------------------------- moderation

def test_reviewers_flag_issues_by_category_and_advertisers_resubmit(world):
    db = world
    _configure(db, "0.50")
    adv = _user(db, "wf11@t.com")
    _fund(db, adv, "50.00")
    c = _draft_campaign(db, adv)
    cr = wf.create_creative(db, c, dict(COMPLETE), actor_id=adv.id, draft=False)
    camp.submit_campaign(db, adv, c)
    admin = _admin(db)
    with pytest.raises(camp.AdError) as e:
        camp.request_changes(db, admin, c, note="", issues=[{"category": "PRICE", "note": "x"}])
    assert e.value.code == "INVALID_ISSUE"
    camp.request_changes(db, admin, c, note="", issues=[{"category": "DESTINATION", "note": "Page is 404"},
                                                        {"category": "PLACEMENT", "note": "No sidebar image"}])
    assert c.status == "CHANGES_REQUESTED" and [i["category"] for i in c.review_issues] == ["DESTINATION", "PLACEMENT"]
    assert wf.display_status(c) == "CHANGES_REQUIRED"
    wf.edit_creative(db, c, cr, {"destination_url": "https://acme.example/ok"}, actor_id=adv.id)
    camp.submit_campaign(db, adv, c)
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    camp.review_campaign(db, admin, c, approve=True, note="ok")
    assert c.status == "ACTIVE" and c.review_issues is None


# ---------------------------------------------------------------- reporting

def test_daily_report_reconciles_to_charged_days_and_shows_adjustments(world):
    db = world
    _configure(db, "1000.00")
    camp.get_settings(db).frequency_cap_per_day = 100
    adv = _user(db, "wf12@t.com")
    _fund(db, adv, "50.00")
    c, cr = _live(db, adv)
    for slot in ("IN_FEED", "SIDEBAR", "IN_FEED"):
        _view(db, page_type="FEED", slot_kind=slot)
    _validate(db)
    db.refresh(c)
    report = wf.daily_report(db, c, days=4000)
    assert report["reconciliation"]["ok"] and D(report["reconciliation"]["sum_of_days"]) == D("3.000000")
    by_slot = {(a["placement"], a["billing_metric"]): a["events"] for a in report["activity"]}
    assert by_slot == {("IN_FEED", "VIEWABLE"): 2, ("SIDEBAR", "VIEWABLE"): 1}
    assert all(a["creative_id"] == cr.id for a in report["activity"])
    assert report["daily"][0]["spend"] == "3.00" and report["remaining_budget"] == "7.00"
    event = db.query(AdvImpressionEvent).filter(AdvImpressionEvent.event_type == "VIEWABLE").first()
    dl.reverse_invalid_activity(db, event_ids=[event.id], reason="bot farm", actor_id=_admin(db).id)
    db.refresh(c)
    report = wf.daily_report(db, c, days=4000)
    assert report["reconciliation"]["ok"] and D(report["reconciliation"]["sum_of_days"]) == D("2.000000")
    assert report["adjustments"][0]["events"] == 1 and D(report["adjustments"][0]["reversed"]) == D("1")


def test_member_daily_estimates_keep_the_original_rate_across_rounds_and_are_not_withdrawable(world):
    db = world
    sponsor = _user(db, "md-s@t.com")
    creative = _user(db, "md-c@t.com", sponsor=sponsor)
    nominee = _user(db, "md-n@t.com", sponsor=sponsor)
    nominator = _user(db, "md-x@t.com")
    adv = _user(db, "md-a@t.com")
    personal = _entry(db, creative)
    nominated = _entry(db, nominator, "NOMINATION", nominee=nominee)
    _configure(db, "1000.00")
    cfg = camp.get_settings(db)
    cfg.frequency_cap_per_day, cfg.max_viewable_per_viewer_hour = 1000, 1000
    _fund(db, adv, "100.00")
    _live(db, adv, budget="100.00")
    for i in range(3):
        _view(db, contestant=personal, viewer=f"p{i}")
    _season(db, personal, SeasonLevel.COUNTRY)                               # later round: still personal
    _view(db, contestant=personal, viewer="p9")
    for i in range(2):
        _view(db, contestant=nominated, viewer=f"n{i}")
    _validate(db)
    mine = wf.member_daily(db, creative.id, days=4000)["days"]
    assert [(r["role"], r["rate"], r["estimated_amount"], r["withdrawable"]) for r in mine] == [
        ("CREATIVE", "0.20", "0.8000", False)]
    nom = wf.member_daily(db, nominee.id, days=4000)["days"]
    assert [(r["original_submission_type"], r["rate"], r["estimated_amount"]) for r in nom] == [
        ("NOMINATION", "0.10", "0.2000")]
    spons = {r["contest_entry_id"]: r["estimated_amount"] for r in wf.member_daily(db, sponsor.id, days=4000)["days"]}
    assert spons == {personal.id: "0.0400", nominated.id: "0.0200"}
    assert wf.member_daily(db, nominator.id, days=4000)["days"] == []        # the nominator never earns


# ---------------------------------------------------------------- advertiser's direct sponsor (20% / 40%)

def _charged_day(db, adv_email, sponsor, *, n=2):
    adv = _user(db, adv_email, sponsor=sponsor)
    _fund(db, adv, "50.00")
    c, _ = _live(db, adv)
    for _ in range(n):
        _view(db, page_type="FEED", slot_kind="IN_FEED")
    _validate(db)
    return adv, c


def test_sponsor_commission_is_off_by_default_and_never_on_deposits(world):
    db = world
    cfg = _configure(db, "1000.00")
    cfg.frequency_cap_per_day = 100
    sponsor = _user(db, "sc0-s@t.com")
    assert cfg.advertiser_sponsor_commission_enabled is False
    _charged_day(db, "sc0@t.com", sponsor)
    assert db.query(AffiliateCommission).count() == 0                     # the deposit earned nobody anything
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    assert db.query(AffiliateCommission).count() == 0                     # switch off
    assert db.query(AdvCampaignDay).one().sponsor_commission_status is None


def test_sponsor_earns_20_percent_of_recognized_charges_once(world):
    db = world
    cfg = _configure(db, "1000.00")
    cfg.frequency_cap_per_day = 100
    cfg.advertiser_sponsor_commission_enabled = True
    sponsor = _user(db, "sc1-s@t.com")
    adv, c = _charged_day(db, "sc1@t.com", sponsor)
    assert db.query(AffiliateCommission).count() == 0                     # nothing before recognition
    assert dl.recognize_closed_days(db, now=T0 + timedelta(days=1)) == 1
    comm = db.query(AffiliateCommission).one()
    assert (comm.user_id, comm.source_user_id, comm.source_type) == (sponsor.id, adv.id, wf.SPONSOR_SOURCE)
    assert (comm.base_amount, comm.commission_rate, comm.commission_amount) == (D("2.00"), D("0.2000"), D("0.40"))
    day = db.query(AdvCampaignDay).one()
    assert (day.sponsor_commission_status, day.sponsor_commission_amount) == ("RECORDED", D("0.40"))
    dl.recognize_closed_days(db, now=T0 + timedelta(days=2))
    assert wf.decide_sponsor_commission(db, day, c, D("2.00")) == "RECORDED"
    assert db.query(AffiliateCommission).count() == 1                     # idempotent
    _ledger_balanced(db)


def test_qualified_sponsor_earns_40_and_unverified_sponsor_misses(world):
    db = world
    cfg = _configure(db, "1000.00")
    cfg.frequency_cap_per_day = 100
    cfg.advertiser_sponsor_commission_enabled = True
    q = _user(db, "sc2-q@t.com")
    db.add(AffiliateRateQualification(user_id=q.id, qualified_at=datetime.utcnow(), qualifying_referral_count=10000,
                                      required_referral_count=10000, qualified_rate=D("0.40"),
                                      rule_version="DIRECT_40_AFTER_10K_KYC_IN_6M_V1",
                                      window_start=datetime(2026, 1, 1), window_deadline=datetime(2026, 7, 1)))
    db.flush()
    _charged_day(db, "sc2a@t.com", q)
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    assert db.query(AffiliateCommission).one().commission_amount == D("0.80")
    nokyc = _user(db, "sc2-n@t.com", kyc=False)
    _, c2 = _charged_day(db, "sc2b@t.com", nokyc)
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == c2.id).one()
    assert day.sponsor_commission_status == "MISSED_KYC" and db.query(AffiliateCommission).count() == 1
    nobody = _user(db, "sc2-none@t.com")
    adv3 = _user(db, "sc2c@t.com")
    _fund(db, adv3, "50.00")
    c3, _ = _live(db, adv3)
    _view(db, page_type="FEED", slot_kind="IN_FEED")
    _validate(db)
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    assert db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == c3.id).one().sponsor_commission_status in (
        "NO_SPONSOR", None)
    assert nobody.id


def test_reversed_charges_reverse_an_unpaid_commission_or_go_to_finance_review(world):
    db = world
    cfg = _configure(db, "1000.00")
    cfg.frequency_cap_per_day = 100
    cfg.advertiser_sponsor_commission_enabled = True
    sponsor = _user(db, "sc3-s@t.com")
    _, c = _charged_day(db, "sc3@t.com", sponsor, n=2)
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    events = db.query(AdvImpressionEvent).filter(AdvImpressionEvent.event_type == "VIEWABLE",
                                                 AdvImpressionEvent.campaign_id == c.id).all()
    admin = _admin(db)
    dl.reverse_invalid_activity(db, event_ids=[events[0].id], reason="partial", actor_id=admin.id)
    day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == c.id).one()
    assert day.sponsor_commission_status == "FINANCE_REVIEW"                 # partial: finance decides
    sponsor2 = _user(db, "sc4-s@t.com")
    _, c2 = _charged_day(db, "sc4@t.com", sponsor2, n=1)
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    ev = db.query(AdvImpressionEvent).filter(AdvImpressionEvent.event_type == "VIEWABLE",
                                             AdvImpressionEvent.campaign_id == c2.id).all()
    dl.reverse_invalid_activity(db, event_ids=[e.id for e in ev], reason="all invalid", actor_id=admin.id)
    day2 = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == c2.id).one()
    assert day2.sponsor_commission_status == "REVERSED"
    comm = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor2.id).one()
    assert comm.status == CommissionStatus.CANCELLED
    _ledger_balanced(db)
    assert _balance(db, "4020") <= 0


# ---------------------------------------------------------------- API

def test_api_draft_creative_edit_submit_catalog_estimate_report_and_daily_earnings(world, client):
    from tests.unit.test_admin_security_hardening import bearer

    db = world
    _configure(db, "0.50")
    camp.get_settings(db).min_campaign_budget_usd = D("10.00")
    adv, other = _user(db, "api1@t.com"), _user(db, "api1o@t.com")
    db.commit()
    h = bearer(adv)
    base = "/api/v1/advertising/advertiser"
    r = client.post(f"{base}/campaigns", json={"name": "Draft only"}, headers=h)   # incomplete draft is allowed
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert r.json()["display_status"] == "DRAFT" and r.json()["schedule"]["starts_after_approval"]
    r = client.patch(f"{base}/campaigns/{cid}", json={"budget": "10.00", "timezone": "Africa/Nairobi",
                                                       "end_at": "2027-01-10T18:00:00", "placements": ["IN_FEED"],
                                                       "page_types_mode": "LIST", "page_types": ["FEED"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["schedule"]["end_at_utc"] == "2027-01-10T15:00:00Z"
    r = client.post(f"{base}/campaigns/{cid}/creatives", json={"headline": "x" * 41}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "TEXT_TOO_LONG"
    r = client.post(f"{base}/campaigns/{cid}/creatives", json={"headline": "Hello"}, headers=h)
    assert r.status_code == 200 and r.json()["review_status"] == "DRAFT"
    crid = r.json()["id"]
    assert client.patch(f"{base}/campaigns/{cid}/creatives/{crid}", json={"headline": "x"},
                        headers=bearer(other)).status_code == 404                  # someone else's campaign
    r = client.patch(f"{base}/campaigns/{cid}/creatives/{crid}",
                     json={"description": "Fresh", "display_name": "Acme", "cta_code": "LEARN_MORE",
                           "destination_url": "https://acme.example/"}, headers=h)
    assert r.status_code == 200 and r.json()["missing_for_review"] == []
    r = client.post(f"{base}/campaigns/{cid}/creatives/{crid}/submit", headers=h)
    assert r.status_code == 200 and r.json()["review_status"] == "PENDING"
    cat = client.get(f"{base}/catalog", headers=h).json()
    assert len(cat["packages"]) == 8 and {c["code"] for c in cat["cta_presets"]} >= {"LEARN_MORE", "SHOP_NOW"}
    assert {p["code"]: p["rendered"] for p in cat["page_types"]}["DISCOVERY"] is False
    est = client.get(f"{base}/estimate", params={"package": "cpc", "budget": "1.00"}, headers=h).json()
    assert (est["units"], est["unit"]) == (20, "valid clicks")
    rep = client.get(f"{base}/campaigns/{cid}/daily-report", headers=h)
    assert rep.status_code == 200 and rep.json()["reconciliation"]["ok"]
    assert client.get(f"{base}/campaigns/{cid}/daily-report", headers=bearer(other)).status_code == 404
    daily = client.get("/api/v1/advertising/earnings/daily", headers=h)
    assert daily.status_code == 200 and daily.json()["days"] == []


def test_api_submit_refuses_a_past_end_and_admin_issues(world, client):
    from tests.unit.test_admin_security_hardening import bearer
    from tests.unit.test_super_admin import superadmin

    db = world
    _configure(db, "0.50")
    adv = _user(db, "api2@t.com")
    _fund(db, adv, "50.00")
    c = _draft_campaign(db, adv, start_at=datetime.utcnow() - timedelta(days=3),
                        end_at=datetime.utcnow() - timedelta(days=1))           # already ended
    wf.create_creative(db, c, dict(COMPLETE), actor_id=adv.id, draft=False)
    boss = superadmin(db, "boss-wf")
    db.commit()
    r = client.post(f"/api/v1/advertising/advertiser/campaigns/{c.id}/submit", headers=bearer(adv))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "INVALID_SCHEDULE"
    c.end_at = datetime.utcnow() + timedelta(days=5)
    db.commit()
    assert client.post(f"/api/v1/advertising/advertiser/campaigns/{c.id}/submit", headers=bearer(adv)).status_code == 200
    r = client.post(f"/api/v1/admin/advertising/campaigns/{c.id}/request-changes",
                    json={"issues": [{"category": "MEDIA", "note": "Image is blurry"}]}, headers=bearer(boss))
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.status == "CHANGES_REQUESTED" and c.review_issues[0]["category"] == "MEDIA"
    camp_list = client.get("/api/v1/admin/advertising/campaigns", headers=bearer(boss)).json()["campaigns"]
    mine = next(x for x in camp_list if x["id"] == c.id)
    assert mine["display_status"] == "CHANGES_REQUIRED" and mine["creatives"][0]["cta_label"] == "Shop now"
