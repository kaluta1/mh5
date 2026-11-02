"""Advertising completion (Prompt 4, 2026-11-03): approved CPM price and minimum budget, package inventory,
review lifecycle (request changes, resubmit, cancel, admin resume), creative image rules, notifications only
while campaigns are switched on, analytics, read-only reconciliation, historical entry-origin review and the
manage_advertising permission. SYNTHETIC data only; nothing is paid."""
from __future__ import annotations

import io
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.accounting import AuditTrail
from app.models.advertising_v2 import AdvCreative, AdvCreditMovement, AdvEntryOrigin
from app.models.contests import Contestant
from app.models.email import EmailDelivery
from app.services import ad_attribution, ad_campaigns as camp, ad_delivery as dl, admin_security
from tests.unit.test_advertising_program import (T0, _balance, _campaign, _configure, _entry, _fund,
                                                  _ledger_balanced, _validate, _view)
from tests.unit.test_new_business_model import _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit


def _approved(db, **kw):
    cfg = _configure(db, cpm="0.50", **kw)
    cfg.min_campaign_budget_usd = Decimal("10.00")
    db.flush()
    return cfg


def _draft(db, adv, budget="10.00"):
    c = camp.create_campaign(db, adv, name="Spring", budget=budget, start_at=T0 - timedelta(days=1),
                             end_at=T0 + timedelta(days=30), placements=["IN_FEED", "SIDEBAR"])
    cr = camp.add_creative(db, c, headline="Hello", body="b", image_url=None, destination_url="https://example.com/a")
    return c, cr


def _keys(db, prefix):
    return sorted(k for (k,) in db.query(EmailDelivery.idempotency_key).all() if k.startswith(prefix))


# ---------------------------------------------------------------- approved pricing and packages

def test_approved_cpm_gives_20000_theoretical_impressions_for_10_usd():
    assert camp.APPROVED_CPM_USD == Decimal("0.50") and camp.APPROVED_MIN_BUDGET_USD == Decimal("10.00")
    assert camp.unit_price("0.50") == Decimal("0.000500")
    assert camp.estimated_impressions("10.00", "0.50") == 20000
    assert camp.estimated_impressions("10.01", "0.50") == 20020
    assert camp.estimated_impressions("10.00", None) is None


def test_minimum_budget_is_enforced_on_the_server(world):
    db = world
    _approved(db)
    adv = _user(db, "min@t.com")
    with pytest.raises(camp.AdError) as e:
        camp.create_campaign(db, adv, name="x", budget="9.99", start_at=T0, end_at=T0 + timedelta(days=1),
                             placements=["IN_FEED"])
    assert e.value.code == "BUDGET_BELOW_MINIMUM"
    c, _cr = _draft(db, adv, budget="10.00")
    with pytest.raises(camp.AdError) as e:
        camp.update_campaign(db, adv, c, {"budget": Decimal("5.00")})
    assert e.value.code == "BUDGET_BELOW_MINIMUM"


def test_package_inventory_reports_real_terms_and_never_sells_unpriced_products(world):
    db = world
    pk = {p["code"]: p for p in camp.packages(db)}
    assert set(pk) == {"MYHIGH5_CPM_CAMPAIGN", "ADVERTISER_CREDIT", "GOOGLE_ADSENSE", "ANNUAL_ADS", "LEGACY_AD_SYSTEM"}
    assert pk["MYHIGH5_CPM_CAMPAIGN"]["state"] == "PRICE_PENDING_APPROVAL" and not pk["MYHIGH5_CPM_CAMPAIGN"]["purchasable"]
    assert not any(p["purchasable"] for p in pk.values())
    assert pk["LEGACY_AD_SYSTEM"]["state"] == "RETIRED" and pk["ANNUAL_ADS"]["price"] is None
    _approved(db, campaigns=False, funding=False)
    pk = {p["code"]: p for p in camp.packages(db)}
    cpm = pk["MYHIGH5_CPM_CAMPAIGN"]
    assert (cpm["state"], cpm["price"], cpm["minimum_budget"]) == ("PRICED_NOT_ACTIVATED", "0.5000", "10.00")
    assert cpm["estimated_impressions_at_minimum"] == 20000 and not cpm["purchasable"]
    _approved(db)
    assert {p["code"] for p in camp.packages(db) if p["purchasable"]} == {"MYHIGH5_CPM_CAMPAIGN", "ADVERTISER_CREDIT"}


# ---------------------------------------------------------------- lifecycle

def test_request_changes_resubmit_keeps_one_allocation_and_never_serves_in_between(world):
    db = world
    _approved(db)
    adv, admin = _user(db, "lc@t.com"), _user(db, "lc-adm@t.com")
    _fund(db, adv, "50.00")
    c, cr = _draft(db, adv)
    camp.submit_campaign(db, adv, c)
    assert camp.credit_balance(db, adv.id) == Decimal("40.00")
    camp.request_changes(db, admin, c, note="Use a clearer headline")
    assert c.status == "CHANGES_REQUESTED"
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer="v", now=T0,
                  allowed_sources={"myhigh5_ads"})
    assert not d["fill"]                                          # not active: nothing served
    with pytest.raises(camp.AdError) as e:
        camp.update_campaign(db, adv, c, {"budget": Decimal("20.00")})
    assert e.value.code == "BUDGET_LOCKED"
    camp.update_campaign(db, adv, c, {"name": "Spring 2"})
    camp.submit_campaign(db, adv, c)
    assert c.status == "PENDING_REVIEW" and c.name == "Spring 2"
    allocations = db.query(AdvCreditMovement).filter(AdvCreditMovement.campaign_id == c.id,
                                                     AdvCreditMovement.movement_type == "ALLOCATE").count()
    assert allocations == 1 and camp.credit_balance(db, adv.id) == Decimal("40.00")
    actions = [a for (a,) in db.query(AuditTrail.action).filter(AuditTrail.table_name == "adv_campaigns",
                                                                AuditTrail.record_id == c.id)]
    assert actions == ["CREATE", "SUBMIT", "REQUEST_CHANGES", "UPDATE", "RESUBMIT"]


def test_cancel_returns_the_budget_once_and_active_campaigns_cannot_be_cancelled(world):
    db = world
    _approved(db)
    adv = _user(db, "cx@t.com")
    _fund(db, adv, "30.00")
    c, _cr = _draft(db, adv)
    camp.submit_campaign(db, adv, c)
    camp.cancel_campaign(db, adv, c)
    assert c.status == "CANCELLED" and camp.credit_balance(db, adv.id) == Decimal("30.00")
    dl.complete_due_campaigns(db, now=T0)                         # the worker never releases twice
    assert camp.credit_balance(db, adv.id) == Decimal("30.00")
    with pytest.raises(camp.AdError):
        camp.cancel_campaign(db, adv, c)
    active = _campaign(db, adv, budget="10.00")
    with pytest.raises(camp.AdError) as e:
        camp.cancel_campaign(db, adv, active)
    assert e.value.code == "INVALID_STATE"
    _ledger_balanced(db)


def test_invalid_transitions_are_refused(world):
    db = world
    _approved(db)
    adv, admin = _user(db, "it@t.com"), _user(db, "it-adm@t.com")
    _fund(db, adv, "20.00")
    c, cr = _draft(db, adv)
    with pytest.raises(camp.AdError):
        camp.request_changes(db, admin, c, note="x")              # draft is not under review
    with pytest.raises(camp.AdError):
        camp.review_campaign(db, admin, c, approve=True, note="")
    camp.submit_campaign(db, adv, c)
    with pytest.raises(camp.AdError) as e:
        camp.request_changes(db, admin, c, note="  ")
    assert e.value.code == "NOTE_REQUIRED"
    with pytest.raises(camp.AdError) as e:
        camp.review_campaign(db, admin, c, approve=True, note="ok")   # creative not approved yet
    assert e.value.code == "NO_APPROVED_CREATIVE"
    with pytest.raises(camp.AdError):
        camp.set_paused(db, admin, c, paused=False)               # not paused
    camp.review_creative(db, admin, cr, approve=True, note="ok")
    camp.review_campaign(db, admin, c, approve=False, note="Off-topic product")
    assert c.status == "REJECTED"
    with pytest.raises(camp.AdError):
        camp.submit_campaign(db, adv, c)                          # a rejection is final


def test_admin_pause_and_resume_are_audited_and_paused_campaigns_do_not_serve(world):
    db = world
    _approved(db)
    adv, admin = _user(db, "pr@t.com"), _user(db, "pr-adm@t.com")
    _fund(db, adv, "20.00")
    c = _campaign(db, adv, budget="10.00")
    camp.set_paused(db, admin, c, paused=True)
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer="v", now=T0,
                  allowed_sources={"myhigh5_ads"})
    assert not d["fill"]
    camp.set_paused(db, admin, c, paused=False)
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer="v", now=T0,
                  allowed_sources={"myhigh5_ads"})
    assert d["fill"] and d["source"] == "MYHIGH5"
    actions = [a for (a,) in db.query(AuditTrail.action).filter(AuditTrail.table_name == "adv_campaigns",
                                                                AuditTrail.record_id == c.id)]
    assert actions[-2:] == ["PAUSE", "RESUME"]


# ---------------------------------------------------------------- notifications

def test_campaign_emails_only_while_campaigns_are_switched_on(world):
    db = world
    _approved(db, campaigns=False)
    adv = _user(db, "mail-off@t.com")
    _fund(db, adv, "20.00")
    c, _cr = _draft(db, adv)
    cfg = camp.get_settings(db)
    cfg.campaigns_enabled = True                                  # submit needs it; then switch off again
    camp.submit_campaign(db, adv, c)
    first = _keys(db, f"adv-campaign:{c.id}:")
    assert first == [f"adv-campaign:{c.id}:SUBMITTED:2"]
    cfg.campaigns_enabled = False
    admin = _user(db, "mail-adm@t.com")
    camp.request_changes(db, admin, c, note="Fix the image")
    assert _keys(db, f"adv-campaign:{c.id}:") == first           # off: nothing queued
    cfg.campaigns_enabled = True
    camp.submit_campaign(db, adv, c)
    assert len(_keys(db, f"adv-campaign:{c.id}:")) == 2


# ---------------------------------------------------------------- creatives

def test_creative_image_rules_and_ownership():
    ok = {"media_type": "image", "content_type": "image/png", "file_size": 50_000, "width": 600, "height": 300}
    camp.check_creative_image(ok)
    for bad in ({**ok, "media_type": "video", "content_type": "video/mp4"}, {**ok, "file_size": 3 * 1024 * 1024},
                {**ok, "width": 50}, {**ok, "height": 5000}, {**ok, "content_type": "image/svg+xml"}):
        with pytest.raises(camp.AdError):
            camp.check_creative_image(bad)
    url = f"/api/v1/media/file/7/{uuid.uuid4()}.png"
    assert camp.own_upload_url(7, url) == url
    for wrong in (f"/api/v1/media/file/8/{uuid.uuid4()}.png", "/api/v1/media/file/7/../../etc/passwd",
                  f"/api/v1/media/file/7/kyc_{uuid.uuid4()}.png"):
        with pytest.raises(camp.AdError):
            camp.own_upload_url(7, wrong)


def test_add_creative_refuses_unsafe_urls_and_other_members_uploads(world):
    db = world
    _approved(db)
    adv, other = _user(db, "own@t.com"), _user(db, "other@t.com")
    c, _cr = _draft(db, adv)
    with pytest.raises(camp.AdError):
        camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="javascript:alert(1)")
    with pytest.raises(camp.AdError):
        camp.add_creative(db, c, headline="h", body=None, image_url="http://example.com/a.png",
                          destination_url="https://example.com")
    with pytest.raises(camp.AdError) as e:
        camp.add_creative(db, c, headline="h", body=None, image_url=f"/api/v1/media/file/{other.id}/{uuid.uuid4()}.png",
                          destination_url="https://example.com")
    assert e.value.code == "IMAGE_NOT_OWNED"
    cr = camp.add_creative(db, c, headline="h", body=None, image_url=f"/api/v1/media/file/{adv.id}/{uuid.uuid4()}.png",
                           destination_url="https://example.com")
    assert cr.review_status == "PENDING"


def _png(w=600, h=300) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_image_upload_endpoint_validates_and_stores_for_the_owner_only(world, client, monkeypatch):
    from tests.unit.test_admin_security_hardening import bearer

    db = world
    _approved(db)
    adv, other = _user(db, "up@t.com"), _user(db, "up-other@t.com")
    c, cr = _draft(db, adv)
    db.commit()
    stored_name = f"{uuid.uuid4()}.png"

    async def fake_store(file, user_id):
        return {"url": f"/api/v1/media/file/{user_id}/{stored_name}", "path": "x",
                "metadata": {"content_type": "image/png", "file_size": 1234, "width": 600, "height": 300,
                             "media_type": "image"}}

    monkeypatch.setattr("app.core.storage.store_media", fake_store)
    url = f"/api/v1/advertising/advertiser/campaigns/{c.id}/creatives/{cr.id}/image"
    files = {"file": ("ad.png", _png(), "image/png")}
    assert client.post(url, files=files, headers=bearer(other)).status_code == 404
    small = client.post(url, files={"file": ("ad.png", _png(40, 40), "image/png")}, headers=bearer(adv))
    assert small.status_code == 400
    fake = client.post(url, files={"file": ("ad.png", b"<svg></svg>", "image/png")}, headers=bearer(adv))
    assert fake.status_code == 400
    good = client.post(url, files=files, headers=bearer(adv))
    assert good.status_code == 200, good.text
    body = good.json()
    assert body["image_url"].endswith(stored_name) and body["image"]["width"] == 600
    assert body["review_status"] == "PENDING"


# ---------------------------------------------------------------- analytics and reconciliation

def test_campaign_report_analytics_and_reconciliation_balance(world):
    db = world
    _approved(db)
    adv = _user(db, "an@t.com")
    _fund(db, adv, "20.00")
    c = _campaign(db, adv, budget="10.00")
    for _ in range(3):
        _view(db, page_type="FEED", slot_kind="IN_FEED", allowed={"myhigh5_ads"})
    _validate(db)
    report = camp.campaign_report(db, c)
    assert report["valid_impressions"] == 3 and report["estimated_impressions"] == 20000
    assert report["by_placement"] == [{"key": "IN_FEED", "valid_impressions": 3, "spend": "0.00"}]
    assert report["clicks"] is None and report["funding"] == "FUNDED"
    rec = camp.reconciliation(db)
    assert rec["ok"], rec
    dl.recognize_closed_days(db, now=T0 + timedelta(days=2))
    assert camp.reconciliation(db)["ok"]
    _ledger_balanced(db)
    assert _balance(db, "2320") == Decimal("-20.00") + Decimal("0")   # sub-cent spend not yet recognized


def test_reconciliation_flags_a_ledger_mismatch(world):
    db = world
    _approved(db)
    adv = _user(db, "mm@t.com")
    _fund(db, adv, "20.00")
    db.add(AdvCreditMovement(advertiser_user_id=adv.id, movement_type="DEPOSIT", amount=Decimal("5.00"),
                             idempotency_key="forged:1"))
    db.flush()
    rec = camp.reconciliation(db)
    assert not rec["ok"] and [c["check"] for c in rec["checks"] if not c["ok"]] == ["credit_liability"]


def test_suspicious_activity_lists_invalid_events(world):
    db = world
    _approved(db)
    adv = _user(db, "sus@t.com")
    _fund(db, adv, "20.00")
    _campaign(db, adv, budget="10.00")
    _view(db, page_type="FEED", slot_kind="IN_FEED", allowed={"myhigh5_ads"}, ms=200)     # not viewable long enough
    _validate(db)
    out = camp.suspicious_activity(db)
    assert sum(out["invalid_by_reason"].values()) >= 1 and out["recent"]


# ---------------------------------------------------------------- historical entry origins

def test_origin_scan_classifies_from_evidence_and_holds_the_rest(world):
    db = world
    owner = _user(db, "orig@t.com")
    proven = _entry(db, owner, "NOMINATION")                        # safety record: NOMINATION
    unproven = _entry(db, owner, safety=False)                      # no safety record, no contest link
    first = ad_attribution.scan_origins(db)
    assert first["scanned"] == 2 and first["resolved_from_evidence"] == 1 and first["sent_to_review"] == 1
    assert ad_attribution.scan_origins(db)["scanned"] == 0          # never re-derived
    rows = {r.contestant_id: r for r in db.query(AdvEntryOrigin)}
    assert rows[proven.id].origin_kind == "NOMINATION" and rows[unproven.id].status == "REVIEW"
    page = ad_attribution.review_page(db)
    assert [p["contestant_id"] for p in page] == [unproven.id] and page[0]["entry_type"] == "participation"
    overview = ad_attribution.origin_overview(db)
    assert (overview["under_review"], overview["unscanned"], overview["resolved_by_kind"]) == (1, 0, {"NOMINATION": 1})
    ad_attribution.resolve_review(db, contestant_id=unproven.id, origin_kind="PERSONAL_SUBMISSION", actor_id=owner.id,
                                  note="Original upload by the member, confirmed from the support ticket")
    with pytest.raises(ValueError):
        ad_attribution.resolve_review(db, contestant_id=unproven.id, origin_kind="NOMINATION", actor_id=owner.id,
                                      note="change")                # immutable once resolved
    assert ad_attribution.creative_rate("PERSONAL_SUBMISSION") == Decimal("0.20")
    assert ad_attribution.creative_rate("NOMINATION") == Decimal("0.10")
    assert ad_attribution.creative_rate(None) is None                # unresolved: no share priced
    db.query(Contestant).filter(Contestant.id == proven.id).update({"entry_type": "participation"})
    assert ad_attribution.origin_for(db, proven).origin_kind == "NOMINATION"   # later edits never change it


# ---------------------------------------------------------------- permissions and endpoints

def test_manage_advertising_is_protected_and_grantable_by_name():
    from app.scripts import grant_payment_permissions as grants

    assert camp.PERMISSION_MANAGE in admin_security.PROTECTED_PERMISSIONS
    assert camp.PERMISSION_MANAGE in grants.PERMISSIONS
    assert grants.role_name({camp.PERMISSION_MANAGE}, None) == "finance_manager_v"


def test_admin_advertising_routes_need_the_permission(world, client):
    from tests.unit.test_admin_security_hardening import bearer
    from tests.unit.test_super_admin import person, superadmin

    db = world
    member = _user(db, "plain-ad@t.com")
    plain_admin = person(db, "admin-noperm", admin=True)
    boss = superadmin(db, "boss-ad")
    db.commit()
    for path in ("/api/v1/admin/advertising/overview", "/api/v1/admin/advertising/reconciliation",
                 "/api/v1/admin/advertising/suspicious", "/api/v1/admin/advertising/origins"):
        assert client.get(path, headers=bearer(member)).status_code == 403, path
        assert client.get(path, headers=bearer(plain_admin)).status_code == 403, path
        assert client.get(path, headers=bearer(boss)).status_code == 200, path
    assert client.post("/api/v1/admin/advertising/campaigns/1/request-changes", json={"note": "abc"},
                       headers=bearer(member)).status_code == 403
    scan = client.post("/api/v1/admin/advertising/origins/scan", json={"limit": 10, "current_password": "wrong"},
                       headers=bearer(boss))
    assert scan.status_code == 403                                   # current password required


def test_member_packages_and_estimate(world, client):
    from tests.unit.test_admin_security_hardening import bearer

    db = world
    _approved(db, campaigns=False, funding=False)
    member = _user(db, "pk@t.com")
    db.commit()
    pk = client.get("/api/v1/advertising/packages", headers=bearer(member))
    assert pk.status_code == 200 and len(pk.json()["packages"]) == 5
    est = client.get("/api/v1/advertising/estimate?budget=10", headers=bearer(member)).json()
    assert est["estimated_impressions"] == 20000 and not est["below_minimum"]
    assert client.get("/api/v1/advertising/estimate?budget=9.5", headers=bearer(member)).json()["below_minimum"]
    assert client.get("/api/v1/advertising/packages").status_code == 401


def test_email_renderer_is_registered():
    from app.services import email_render
    from app.services.email_events import EmailEvent

    assert EmailEvent.BILLING_ADVERTISING_UPDATE.value in email_render.RENDERERS
