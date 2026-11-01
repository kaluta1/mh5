"""Advertising program (2026-11-01): placements decision, CPM budgets and reservations, viewability and
invalid traffic, advertiser credit (liability until delivery), contest-entry revenue sharing (20/10 + 1,
original type, nominee beneficiary, held earnings), AdSense reconciliation, Annual Ads exclusion and
ledger balance. SYNTHETIC data only; no provider is contacted."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.advertising_v2 import (AdvAdsenseBucket, AdvAllocation, AdvAnnualAdsPayment, AdvCampaign,
                                       AdvCampaignDay, AdvCreditMovement, AdvEntryOrigin, AdvImpressionEvent,
                                       AdvServeDecision)
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.contest import Contest
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant, ContestantSeason, ContestSeason, SeasonLevel
from app.models.payment import Deposit, DepositStatus, ProductType
from app.services import ad_attribution, ad_campaigns as camp, ad_delivery as dl, ad_revenue_sharing as sharing
from app.services import annualads_records
from app.services.new_model_payments import process_new_model_deposit, reverse_new_model_deposit
from tests.unit.test_new_business_model import _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit
UA = "Mozilla/5.0 (Windows NT 10.0) Chrome/120"
T0 = datetime(2026, 10, 10, 12, 0, 0)


# ---------------------------------------------------------------- helpers

def _balance(db, code) -> Decimal:
    acc = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).one()
    d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0)).filter(JournalLine.account_id == acc.id).one()
    return Decimal(str(d)) - Decimal(str(c))


def _ledger_balanced(db):
    d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0)).one()
    assert Decimal(str(d)) == Decimal(str(c))


def _configure(db, cpm="4.00", *, campaigns=True, funding=True, sharing_on=True, adsense_sharing=True):
    cfg = camp.get_settings(db)
    cfg.cpm_rate_usd = Decimal(cpm) if cpm else None
    cfg.campaigns_enabled, cfg.funding_enabled = campaigns, funding
    cfg.contest_sharing_enabled, cfg.adsense_sharing_enabled = sharing_on, adsense_sharing
    db.flush()
    return cfg


def _fund(db, advertiser, amount="100.00"):
    product = db.query(ProductType).filter(ProductType.code == camp.AD_CREDIT_PRODUCT_CODE).one()
    dep = Deposit(user_id=advertiser.id, product_type_id=product.id, amount=Decimal(amount), currency="USD",
                  status=DepositStatus.VALIDATED, order_id=f"ad-{uuid.uuid4().hex[:10]}", business_model_version="NEW_V2")
    db.add(dep)
    db.flush()
    process_new_model_deposit(db, dep)
    return dep


def _campaign(db, advertiser, *, budget="10.00", daily_cap=None, placements=("IN_CONTENT", "IN_FEED", "SIDEBAR"),
              start=T0 - timedelta(days=1), end=T0 + timedelta(days=30), targeting=None, approve=True):
    c = camp.create_campaign(db, advertiser, name="C", budget=budget, daily_cap=daily_cap, start_at=start, end_at=end,
                             placements=list(placements), targeting=targeting)
    cr = camp.add_creative(db, c, headline="Buy", body=None, image_url=None, destination_url="https://example.com/x")
    camp.submit_campaign(db, advertiser, c)
    if approve:
        admin = _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")
        camp.review_creative(db, admin, cr, approve=True, note="ok")
        camp.review_campaign(db, admin, c, approve=True, note="ok")
    return c


def _season(db, contestant, level):
    s = ContestSeason(title=level.value, level=level)
    db.add(s)
    db.flush()
    db.query(ContestantSeason).filter(ContestantSeason.contestant_id == contestant.id).update({"is_active": False})
    db.add(ContestantSeason(contestant_id=contestant.id, season_id=s.id, is_active=True))
    db.flush()
    return s


def _entry(db, owner, kind="PERSONAL_SUBMISSION", *, nominee=None, safety=True, contest_mode=None, entry_type=None):
    contest = None
    if contest_mode:
        contest = Contest(name="K", contest_type="beauty", level="city", contest_mode=contest_mode)
        db.add(contest)
        db.flush()
    c = Contestant(user_id=owner.id, title="t", is_active=True, contest_id=contest.id if contest else None,
                   entry_type=entry_type or ("nomination" if kind == "NOMINATION" else "participation"))
    db.add(c)
    db.flush()
    if safety:
        db.add(ContestEntrySafety(
            contestant_id=c.id, entry_kind=kind, submitted_by_user_id=owner.id, account_holder_user_id=owner.id,
            nominee_user_id=nominee.id if nominee else None,
            creative_owner_type="SELF" if kind == "PERSONAL_SUBMISSION" else ("NOMINEE" if nominee else "UNKNOWN"),
            creative_owner_user_id=owner.id if kind == "PERSONAL_SUBMISSION" else (nominee.id if nominee else None),
            exposure_status="PUBLIC", rights_status="NOT_REQUIRED", safety_status="CLEAR",
            metadata_status="NOT_REQUIRED", outcome="ALLOWED", last_evaluated_at=datetime.utcnow()))
        db.flush()
    _season(db, c, SeasonLevel.COUNTRY if kind == "NOMINATION" else SeasonLevel.CITY)
    return c


def _view(db, *, page_type="CONTEST_ENTRY", slot_kind="IN_CONTENT", contestant=None, viewer=None, at=T0,
          ms=1500, ratio=0.8, visible=True, ua=UA, allowed=None, source_check=None):
    viewer = viewer or dl.viewer_hash(None, f"10.0.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}", ua)
    d = dl.decide(db, page_type=page_type, slot_kind=slot_kind, slot_key="k", now=at,
                  contestant_id=contestant.id if contestant else None, viewer=viewer, allowed_sources=allowed)
    if not d["fill"]:
        return d, None
    if source_check:
        assert d["source"] == source_check
    status = dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="VIEWABLE",
                             visible_ms=ms, visible_ratio=ratio, page_visible=visible, user_agent=ua, viewer=viewer,
                             now=at + timedelta(seconds=2))
    return d, status


def _validate(db, at=T0):
    return dl.validate_pending(db, now=at + timedelta(seconds=5))


# ---------------------------------------------------------------- pricing / settings

def test_pricing_pending_blocks_campaigns_funding_and_paid_serving(world):
    db = world
    cfg = camp.get_settings(db)
    assert camp.pricing_state(cfg) == "PENDING_APPROVAL" and not cfg.campaigns_enabled and not cfg.funding_enabled
    admin = _user(db, "pa@t.com")
    with pytest.raises(camp.AdError) as e:
        camp.update_settings(db, admin, {"campaigns_enabled": True})
    assert e.value.code == "PRICING_PENDING"
    adv = _user(db, "pa-adv@t.com")
    c = camp.create_campaign(db, adv, name="x", budget="10", start_at=T0, end_at=T0 + timedelta(days=1),
                             placements=["IN_FEED"])
    camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://ex.com")
    with pytest.raises(camp.AdError) as e:
        camp.submit_campaign(db, adv, c)
    assert e.value.code == "PRICING_PENDING"
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, viewer="v", now=T0)
    assert d["source"] == "ADSENSE"       # no paid campaign can be served without a price


def test_settings_are_audited_and_validated(world):
    db = world
    admin = _user(db, "sa@t.com")
    camp.update_settings(db, admin, {"cpm_rate_usd": "4.50", "campaigns_enabled": True})
    cfg = camp.get_settings(db)
    assert cfg.cpm_rate_usd == Decimal("4.5000") and cfg.campaigns_enabled
    with pytest.raises(camp.AdError):
        camp.update_settings(db, admin, {"cpm_rate_usd": "-1"})
    with pytest.raises(camp.AdError):
        camp.update_settings(db, admin, {"unknown": 1})


# ---------------------------------------------------------------- advertiser credit (liability)

def test_deposit_is_a_liability_not_revenue_and_no_commission(world):
    db = world
    _configure(db)
    sponsor = _user(db, "dep-s@t.com")
    adv = _user(db, "dep-a@t.com", sponsor=sponsor)
    _fund(db, adv, "100.00")
    assert camp.credit_balance(db, adv.id) == Decimal("100.00")
    assert _balance(db, "2320") == Decimal("-100.00")          # credit balance (liability)
    assert _balance(db, "4020") == Decimal("0")
    assert db.query(AffiliateCommission).count() == 0           # no affiliate commission on ad credit
    _ledger_balanced(db)


def test_submit_needs_credit_and_fixes_the_price(world):
    db = world
    _configure(db, "4.00")
    adv = _user(db, "sub@t.com")
    c = camp.create_campaign(db, adv, name="x", budget="50", start_at=T0, end_at=T0 + timedelta(days=2),
                             placements=["IN_FEED"])
    camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://ex.com")
    with pytest.raises(camp.AdError) as e:
        camp.submit_campaign(db, adv, c)
    assert e.value.code == "INSUFFICIENT_CREDIT"
    _fund(db, adv, "60.00")
    camp.submit_campaign(db, adv, c)
    assert camp.credit_balance(db, adv.id) == Decimal("10.00")
    camp.get_settings(db).cpm_rate_usd = Decimal("9.00")         # a later price change never reprices it
    assert c.cpm_rate_usd == Decimal("4.00")


def test_provider_refund_of_credit_reverses_and_pauses_campaigns(world):
    db = world
    _configure(db)
    adv = _user(db, "ref@t.com")
    dep = _fund(db, adv, "10.00")
    c = _campaign(db, adv, budget="10.00")
    assert c.status == "ACTIVE"
    reverse_new_model_deposit(db, dep, reason="provider refund")
    assert camp.credit_balance(db, adv.id) == Decimal("-10.00")
    assert c.status == "PAUSED"
    _ledger_balanced(db)


# ---------------------------------------------------------------- serving, reservation, charging

def test_paid_campaign_first_adsense_fallback_and_eligibility(world):
    db = world
    _configure(db)
    adv = _user(db, "pr@t.com")
    _fund(db, adv, "10.00")
    _campaign(db, adv)
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, viewer="v", now=T0)
    assert d["source"] == "MYHIGH5" and d["sponsored_label"] == "Sponsored"
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, viewer="v", now=T0,
                  allowed_sources={"adsense"})
    assert d["source"] == "ADSENSE"
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, viewer="v", now=T0,
                  allowed_sources=set())
    assert d == {"fill": False, "reason": "NO_FILL"}


def test_excluded_or_wrong_placements_get_nothing(world):
    db = world
    for page, slot in (("MARKETPLACE", "SIDEBAR"), ("CONTEST_ENTRY", "IN_FEED"), ("SETTINGS", "IN_FEED"),
                       ("MESSAGES", "SIDEBAR")):
        assert dl.decide(db, page_type=page, slot_kind=slot, slot_key="x", contestant_id=None, viewer="v",
                         now=T0)["fill"] is False


def test_entry_page_requires_a_public_entry(world):
    db = world
    owner = _user(db, "pub@t.com")
    c = _entry(db, owner)
    db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == c.id).update({"exposure_status": "HELD"})
    assert dl.decide(db, page_type="CONTEST_ENTRY", slot_kind="IN_CONTENT", slot_key="e", contestant_id=c.id,
                     viewer="v", now=T0) == {"fill": False, "reason": "ENTRY_NOT_ELIGIBLE"}


def test_valid_viewable_impression_is_charged_once_at_cpm(world):
    db = world
    _configure(db, "4.00")
    adv = _user(db, "ch@t.com")
    _fund(db, adv, "10.00")
    c = _campaign(db, adv)
    _, status = _view(db, page_type="FEED", slot_kind="IN_FEED", source_check="MYHIGH5")
    assert status == "RECORDED"
    assert c.reserved == Decimal("0.004")
    assert _validate(db) == {"valid": 1, "invalid": 0}
    db.refresh(c)
    assert (c.spent, c.reserved) == (Decimal("0.004000"), Decimal("0.000000"))


@pytest.mark.parametrize("kw,reason", [
    (dict(ms=900), "NOT_VIEWABLE"), (dict(ratio=0.4), "NOT_VIEWABLE"), (dict(visible=False), "HIDDEN"),
    (dict(ua="Googlebot/2.1"), "BOT"),
])
def test_nonqualifying_views_are_never_charged(world, kw, reason):
    db = world
    _configure(db)
    adv = _user(db, f"nq{uuid.uuid4().hex[:5]}@t.com")
    _fund(db, adv, "10.00")
    c = _campaign(db, adv)
    _view(db, page_type="FEED", slot_kind="IN_FEED", **kw)
    _validate(db)
    ev = db.query(AdvImpressionEvent).one()
    db.refresh(c)
    assert (ev.validation_status, ev.invalid_reason) == ("INVALID", reason)
    assert (c.spent, c.reserved) == (Decimal("0"), Decimal("0"))


def test_duplicate_events_and_replays_are_refused(world):
    db = world
    _configure(db)
    adv = _user(db, "dup@t.com")
    _fund(db, adv, "10.00")
    c = _campaign(db, adv)
    d, _ = _view(db, page_type="FEED", slot_kind="IN_FEED", viewer="vv")
    ev = db.query(AdvImpressionEvent).one()
    assert dl.record_event(db, decision_id=d["decision_id"], event_id=ev.event_id, event_type="VIEWABLE", visible_ms=2000,
                           visible_ratio=1, page_visible=True, user_agent=UA, viewer="vv") == "DUPLICATE"
    assert dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="VIEWABLE",
                           visible_ms=2000, visible_ratio=1, page_visible=True, user_agent=UA, viewer="vv") == "DUPLICATE"
    _validate(db)
    db.refresh(c)
    assert c.spent == Decimal("0.004")


def test_viewer_mismatch_and_self_view_are_invalid(world):
    db = world
    _configure(db)
    adv = _user(db, "self@t.com")
    _fund(db, adv, "10.00")
    _campaign(db, adv)
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, now=T0,
                  viewer=dl.viewer_hash_for_user(adv.id))
    dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="VIEWABLE",
                    visible_ms=1500, visible_ratio=1, page_visible=True, user_agent=UA,
                    viewer=dl.viewer_hash_for_user(adv.id), now=T0)
    d2 = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, now=T0, viewer="a")
    dl.record_event(db, decision_id=d2["decision_id"], event_id=str(uuid.uuid4()), event_type="VIEWABLE",
                    visible_ms=1500, visible_ratio=1, page_visible=True, user_agent=UA, viewer="b", now=T0)
    _validate(db)
    reasons = sorted(e.invalid_reason for e in db.query(AdvImpressionEvent).all())
    assert reasons == ["SELF_VIEW", "VIEWER_MISMATCH"]


def test_budget_and_daily_cap_can_never_be_overspent(world):
    db = world
    _configure(db, "1000.00")                                     # 1.00 per impression
    adv = _user(db, "cap@t.com")
    _fund(db, adv, "5.00")
    c = _campaign(db, adv, budget="5.00", daily_cap="3.00")
    camp.get_settings(db).frequency_cap_per_day = 1000
    late = datetime.combine(T0.date(), datetime.max.time()) - timedelta(minutes=1)   # pacing allows the full cap
    fills = [dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None,
                       viewer=f"v{i}", now=late)["source"] for i in range(10)]
    assert fills.count("MYHIGH5") == 3                            # daily cap
    db.refresh(c)
    assert c.reserved == Decimal("3")
    nxt = late + timedelta(days=1)
    fills = [dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None,
                       viewer=f"w{i}", now=nxt)["source"] for i in range(10)]
    assert fills.count("MYHIGH5") == 2                            # total budget (5 = 3 + 2)
    db.refresh(c)
    assert c.spent + c.reserved <= c.budget_total


def test_expired_reservations_are_released_and_late_views_not_charged(world):
    db = world
    _configure(db)
    adv = _user(db, "exp@t.com")
    _fund(db, adv, "10.00")
    c = _campaign(db, adv)
    d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, viewer="v", now=T0)
    assert dl.expire_reservations(db, now=T0 + timedelta(hours=1)) == 1
    db.refresh(c)
    assert c.reserved == 0
    dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="VIEWABLE", visible_ms=2000,
                    visible_ratio=1, page_visible=True, user_agent=UA, viewer="v", now=T0 + timedelta(hours=1))
    dl.validate_pending(db, now=T0 + timedelta(hours=1))
    assert db.query(AdvImpressionEvent).one().invalid_reason == "EXPIRED"
    db.refresh(c)
    assert c.spent == 0


def test_no_charge_after_campaign_end_and_completion_settles_unspent_credit(world):
    db = world
    _configure(db, "4.00")
    adv = _user(db, "end@t.com")
    _fund(db, adv, "10.00")
    c = _campaign(db, adv, budget="10.00", end=T0 + timedelta(hours=1))
    assert dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="f", contestant_id=None, viewer="v",
                     now=T0 + timedelta(hours=2))["source"] == "ADSENSE"
    for i in range(3):
        _view(db, page_type="FEED", slot_kind="IN_FEED")
    _validate(db)
    dl.complete_due_campaigns(db, now=T0 + timedelta(hours=2))
    assert c.status == "COMPLETED" and c.settled_at is None       # waits for the day's recognition
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    dl.complete_due_campaigns(db, now=T0 + timedelta(days=1))
    assert c.settled_at is not None
    # 3 x 0.004 = 0.012 -> recognized 0.01 (rounded down); the advertiser gets 9.99 back.
    assert _balance(db, "4020") == Decimal("-0.01")
    assert camp.credit_balance(db, adv.id) == Decimal("9.99")
    assert _balance(db, "2320") == Decimal("-9.99")                # liability == unspent credit
    _ledger_balanced(db)


def test_daily_recognition_is_idempotent_and_cumulative(world):
    db = world
    _configure(db, "1000.00")
    adv = _user(db, "rec@t.com")
    _fund(db, adv, "10.00")
    _campaign(db, adv)
    camp.get_settings(db).frequency_cap_per_day = 100
    for _ in range(2):
        _view(db, page_type="FEED", slot_kind="IN_FEED")
    _validate(db)
    assert dl.recognize_closed_days(db, now=T0 + timedelta(days=1)) == 1
    assert dl.recognize_closed_days(db, now=T0 + timedelta(days=2)) == 0
    assert _balance(db, "4020") == Decimal("-2.00")
    _ledger_balanced(db)


# ---------------------------------------------------------------- original type and attribution

def test_origin_from_safety_record_and_immutable_across_levels(world):
    db = world
    owner = _user(db, "org@t.com")
    c = _entry(db, owner)
    o = ad_attribution.origin_for(db, c)
    assert (o.status, o.origin_kind) == ("RESOLVED", "PERSONAL_SUBMISSION")
    db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == c.id).update({"entry_kind": "NOMINATION"})
    assert ad_attribution.origin_for(db, c).origin_kind == "PERSONAL_SUBMISSION"     # never re-derived


def test_legacy_admin_nomination_with_default_entry_type_is_held_for_review(world):
    db = world
    owner = _user(db, "leg@t.com")
    c = _entry(db, owner, "NOMINATION", safety=False, contest_mode="nomination", entry_type="participation")
    o = ad_attribution.origin_for(db, c)
    assert (o.status, o.origin_kind) == ("REVIEW", None)
    assert ad_attribution.attribute(db, c).origin_kind is None
    ok = _entry(db, owner, "NOMINATION", safety=False, contest_mode="nomination", entry_type="nomination")
    assert ad_attribution.origin_for(db, ok).origin_kind == "NOMINATION"
    none = _entry(db, owner, safety=False)
    assert ad_attribution.origin_for(db, none).status == "REVIEW"   # no contest link: not guessed


# ---------------------------------------------------------------- revenue sharing

def _ordinary_month(db, contestant, n=1000, cpm="1000.00", at=T0, viewer_prefix="x"):
    """n valid charged impressions of 1.00 each on the entry page."""
    _configure(db, cpm)
    camp.get_settings(db).frequency_cap_per_day = 100000
    camp.get_settings(db).max_viewable_per_viewer_hour = 100000
    for i in range(n):
        _view(db, contestant=contestant, viewer=f"{viewer_prefix}{i}", at=at)
    _validate(db, at)


def test_personal_submission_20_plus_sponsor_1_through_every_level(world):
    db = world
    sponsor = _user(db, "ps-s@t.com")
    creative = _user(db, "ps-c@t.com", sponsor=sponsor)
    adv = _user(db, "ps-a@t.com")
    c = _entry(db, creative)
    _configure(db, "1000.00")
    _fund(db, adv, "1000.00")
    _campaign(db, adv, budget="1000.00")
    _ordinary_month(db, c, n=50)                                    # City: $50
    _season(db, c, SeasonLevel.COUNTRY)
    _ordinary_month(db, c, n=50, viewer_prefix="y")                 # Country: $50 (still personal)
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    lines = db.query(AdvAllocation).filter(AdvAllocation.status == "RELEASED").all()
    by = {(l.role, l.contest_level): (l.rate, l.amount) for l in lines}
    assert by[("CREATIVE", "city")] == (Decimal("0.2000"), Decimal("10.00"))
    assert by[("CREATIVE", "country")] == (Decimal("0.2000"), Decimal("10.00"))      # NOT 10% at Country
    assert by[("SPONSOR", "city")] == (Decimal("0.0100"), Decimal("0.50"))
    comms = db.query(AffiliateCommission).filter(AffiliateCommission.commission_type == CommissionType.AD_REVENUE).all()
    assert sum(Decimal(str(x.commission_amount)) for x in comms if x.user_id == creative.id) == Decimal("20.00")
    assert sum(Decimal(str(x.commission_amount)) for x in comms if x.user_id == sponsor.id) == Decimal("1.00")
    assert all(x.status == CommissionStatus.APPROVED and x.level == 1 for x in comms)
    _ledger_balanced(db)


def test_nomination_pays_the_confirmed_nominee_10_never_the_nominator(world):
    db = world
    nsponsor = _user(db, "nm-ns@t.com")
    nominee = _user(db, "nm-n@t.com", sponsor=nsponsor)
    nominator_sponsor = _user(db, "nm-rs@t.com")
    nominator = _user(db, "nm-r@t.com", sponsor=nominator_sponsor)
    c = _entry(db, nominator, "NOMINATION", nominee=nominee)
    adv = _user(db, "nm-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "1000.00")
    _campaign(db, adv, budget="1000.00")
    _ordinary_month(db, c, n=100)                                   # $100
    _season(db, c, SeasonLevel.CONTINENT)
    _ordinary_month(db, c, n=100, viewer_prefix="z")                # still 10% at Continental
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    paid = {}
    for x in db.query(AffiliateCommission).all():
        paid[x.user_id] = paid.get(x.user_id, Decimal(0)) + Decimal(str(x.commission_amount))
    assert paid == {nominee.id: Decimal("20.00"), nsponsor.id: Decimal("2.00")}      # 10%+1% of $200
    assert nominator.id not in paid and nominator_sponsor.id not in paid


def test_same_creative_two_entries_keep_their_own_original_type(world):
    db = world
    creative = _user(db, "two@t.com")
    other = _user(db, "two-n@t.com")
    personal = _entry(db, creative)
    nominated = _entry(db, other, "NOMINATION", nominee=creative)
    adv = _user(db, "two-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "1000.00")
    _campaign(db, adv, budget="1000.00")
    _ordinary_month(db, personal, n=10)
    _ordinary_month(db, nominated, n=10, viewer_prefix="q")
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    rates = {l.contestant_id: l.rate for l in db.query(AdvAllocation).filter(AdvAllocation.role == "CREATIVE")}
    assert rates == {personal.id: Decimal("0.2000"), nominated.id: Decimal("0.1000")}


def test_unclaimed_nominee_is_held_then_released_after_claim(world):
    db = world
    nominator = _user(db, "un-r@t.com")
    c = _entry(db, nominator, "NOMINATION")                         # no nominee account yet
    adv = _user(db, "un-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "1000.00")
    _campaign(db, adv, budget="1000.00")
    _ordinary_month(db, c, n=100)
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    lines = {l.role: l for l in db.query(AdvAllocation).all()}
    assert (lines["CREATIVE"].status, lines["CREATIVE"].amount, lines["CREATIVE"].beneficiary_user_id) == \
           ("HELD_UNCLAIMED", Decimal("10.00"), None)
    assert (lines["SPONSOR"].status, lines["SPONSOR"].amount) == ("HELD_SPONSOR", Decimal("1.00"))
    assert db.query(AffiliateCommission).count() == 0               # nominator never paid
    assert _balance(db, "2322") == Decimal("-11.00")                # preserved as a liability
    nsponsor = _user(db, "un-ns@t.com")
    nominee = _user(db, "un-n@t.com", sponsor=nsponsor)
    db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == c.id).update(
        {"nominee_user_id": nominee.id})
    assert sharing.release_claimed(db) == 1
    assert lines["CREATIVE"].status == "RELEASED" and lines["CREATIVE"].beneficiary_user_id == nominee.id
    assert lines["SPONSOR"].status == "HELD_SPONSOR"                 # not invented; admin applies policy
    sharing.release_held_sponsor(db, line_id=lines["SPONSOR"].id, actor_id=nominator.id, note="policy approved")
    paid = {x.user_id: Decimal(str(x.commission_amount)) for x in db.query(AffiliateCommission).all()}
    assert paid == {nominee.id: Decimal("10.00"), nsponsor.id: Decimal("1.00")}
    assert _balance(db, "2322") == Decimal("0")
    _ledger_balanced(db)


def test_missing_or_ineligible_sponsor_never_reduces_the_creative_share(world):
    db = world
    inactive = _user(db, "ms-i@t.com", active=False)
    creative = _user(db, "ms-c@t.com", sponsor=inactive)
    c = _entry(db, creative)
    adv = _user(db, "ms-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "1000.00")
    _campaign(db, adv, budget="1000.00")
    _ordinary_month(db, c, n=100)
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    lines = db.query(AdvAllocation).all()
    assert [(l.role, l.amount) for l in lines] == [("CREATIVE", Decimal("20.00"))]


def test_sponsor_change_after_earning_does_not_rewrite_history(world):
    db = world
    s1 = _user(db, "sc-1@t.com")
    s2 = _user(db, "sc-2@t.com")
    creative = _user(db, "sc-c@t.com", sponsor=s1)
    c = _entry(db, creative)
    adv = _user(db, "sc-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "1000.00")
    _campaign(db, adv, budget="1000.00")
    _ordinary_month(db, c, n=100)
    creative.sponsor_id = s2.id
    db.flush()
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    sponsor_line = db.query(AdvAllocation).filter(AdvAllocation.role == "SPONSOR").one()
    assert sponsor_line.beneficiary_user_id == s1.id


def test_feeds_and_listings_are_platform_revenue(world):
    db = world
    creative = _user(db, "fd-c@t.com")
    c = _entry(db, creative)
    adv = _user(db, "fd-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "100.00")
    _campaign(db, adv, budget="100.00")
    camp.get_settings(db).frequency_cap_per_day = 1000
    for i in range(5):
        # a listing page that shows entry c: never attributed to it
        _view(db, page_type="CONTEST_LISTING", slot_kind="IN_FEED", contestant=c, viewer=f"l{i}")
    _validate(db)
    assert all(e.contestant_id is None for e in db.query(AdvImpressionEvent).all())
    out = sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    assert out["lines"] == 0


def test_period_cannot_finalize_early_or_without_activation(world):
    db = world
    _configure(db, sharing_on=False)
    with pytest.raises(camp.AdError) as e:
        sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    assert e.value.code == "SHARING_NOT_ACTIVATED"
    _configure(db)
    with pytest.raises(camp.AdError) as e:
        sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 2))
    assert e.value.code == "PERIOD_OPEN"


def test_finalize_is_idempotent(world):
    db = world
    creative = _user(db, "id-c@t.com")
    c = _entry(db, creative)
    adv = _user(db, "id-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "100.00")
    _campaign(db, adv, budget="100.00")
    _ordinary_month(db, c, n=10)
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    assert sharing.finalize_period(db, period="2026-10", source="MYHIGH5",
                                   now=datetime(2026, 11, 6))["status"] == "ALREADY_FINALIZED"
    assert db.query(AffiliateCommission).count() == 1


def test_review_origin_resolution_prices_held_lines(world):
    db = world
    creative = _user(db, "rv-c@t.com")
    c = _entry(db, creative, safety=False)                           # no evidence -> REVIEW
    adv = _user(db, "rv-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "100.00")
    _campaign(db, adv, budget="100.00")
    _ordinary_month(db, c, n=10)
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    lines = {l.role: l for l in db.query(AdvAllocation).all()}
    assert {(r, l.status, l.amount) for r, l in lines.items()} == {("CREATIVE", "HELD_REVIEW", Decimal("0.00")),
                                                                    ("SPONSOR", "HELD_REVIEW", Decimal("0.00"))}
    assert db.query(AffiliateCommission).count() == 0
    ad_attribution.resolve_review(db, contestant_id=c.id, origin_kind="PERSONAL_SUBMISSION", actor_id=creative.id,
                                  note="contest records")
    assert sharing.apply_origin_resolution(db, contestant_id=c.id) == 2
    assert (lines["CREATIVE"].status, lines["CREATIVE"].amount) == ("RELEASED", Decimal("2.00"))
    assert lines["SPONSOR"].status == "REVERSED"                      # creative has no sponsor: none invented


def test_invalid_activity_after_release_is_reversed_auditably(world):
    db = world
    creative = _user(db, "rvr-c@t.com")
    c = _entry(db, creative)
    adv = _user(db, "rvr-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "100.00")
    campaign = _campaign(db, adv, budget="100.00")
    _ordinary_month(db, c, n=10)                                    # $10 -> creative $2.00
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    bad = [e.id for e in db.query(AdvImpressionEvent).limit(5).all()]
    out = dl.reverse_invalid_activity(db, event_ids=bad, reason="invalid traffic", actor_id=creative.id)
    assert out["credited"] == "5.00"
    sharing.adjust_after_reversal(db, period="2026-10", source="MYHIGH5", reason="invalid traffic", actor_id=creative.id)
    live = db.query(AdvAllocation).filter(AdvAllocation.status == "RELEASED").one()
    assert (live.amount, live.version) == (Decimal("1.00"), 2)
    old = db.query(AdvAllocation).filter(AdvAllocation.status == "SUPERSEDED").one()
    assert db.query(AffiliateCommission).filter(AffiliateCommission.id == old.commission_id).one().status == \
           CommissionStatus.CANCELLED
    assert _balance(db, "4020") == Decimal("-5.00")
    db.refresh(campaign)
    assert campaign.spent == Decimal("5")
    _ledger_balanced(db)


# ---------------------------------------------------------------- AdSense

def test_adsense_proportional_estimate_then_finalized_reconciliation(world):
    db = world
    _configure(db, None, campaigns=False, funding=False)
    sponsor = _user(db, "as-s@t.com")
    creative = _user(db, "as-c@t.com", sponsor=sponsor)
    c = _entry(db, creative)
    camp.get_settings(db).max_viewable_per_viewer_hour = 100000
    for i in range(40):
        _view(db, contestant=c, viewer=f"e{i}", source_check="ADSENSE")          # entry page
    for i in range(60):
        _view(db, page_type="FEED", slot_kind="IN_FEED", viewer=f"f{i}")        # platform
    _validate(db)
    db.add(AdvAdsenseBucket(day=T0.date(), ad_unit="ca-pub-5582556318526474:8189486989", currency="USD",
                            estimated_earnings=Decimal("10.00"), status="ESTIMATED"))
    db.flush()
    est = sharing.plan_lines(db, "2026-10", "ADSENSE", finalized=False)
    creative_est = next(l for l in est if l["role"] == "CREATIVE")
    assert creative_est["base_amount"] == Decimal("4.00000000") and creative_est["amount"] == Decimal("0.80")
    with pytest.raises(camp.AdError) as e:
        sharing.finalize_period(db, period="2026-10", source="ADSENSE", now=datetime(2026, 11, 5))
    assert e.value.code == "ADSENSE_NOT_FINALIZED"                  # estimates are never released
    assert db.query(AffiliateCommission).count() == 0
    sharing.record_finalized_month(db, period="2026-10", finalized_total="9.00", actor_id=creative.id,
                                   evidence_note="AdSense payments report Oct", now=datetime(2026, 11, 5))
    sharing.finalize_period(db, period="2026-10", source="ADSENSE", now=datetime(2026, 11, 5))
    lines = {l.role: l for l in db.query(AdvAllocation).all()}
    assert lines["CREATIVE"].amount == Decimal("0.72") and lines["SPONSOR"].amount == Decimal("0.03")
    assert _balance(db, "4021") == Decimal("-9.00") and _balance(db, "1240") == Decimal("9.00")
    _ledger_balanced(db)


def test_adsense_import_without_credentials_fabricates_nothing(world, monkeypatch):
    db = world
    for k in ("ADSENSE_ACCOUNT_ID", "ADSENSE_OAUTH_CLIENT_ID", "ADSENSE_OAUTH_CLIENT_SECRET", "ADSENSE_OAUTH_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    run = sharing.import_adsense(db, start=date(2026, 10, 1), end=date(2026, 10, 31))
    assert run.status == "NO_CREDENTIALS" and "ADSENSE_OAUTH_REFRESH_TOKEN" in run.detail
    assert db.query(AdvAdsenseBucket).count() == 0


def test_adsense_import_parses_report_and_keeps_finalized_buckets(world, monkeypatch):
    db = world
    for k, v in {"ADSENSE_ACCOUNT_ID": "pub-1", "ADSENSE_OAUTH_CLIENT_ID": "c", "ADSENSE_OAUTH_CLIENT_SECRET": "s",
                 "ADSENSE_OAUTH_REFRESH_TOKEN": "r"}.items():
        monkeypatch.setenv(k, v)

    class Resp:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self.body

    class Transport:
        def post(self, url, data):
            return Resp({"access_token": "t"})

        def get(self, url, params, headers):
            assert "accounts/pub-1/reports:generate" in url
            return Resp({"headers": [{"name": "DATE"}, {"name": "AD_UNIT_ID"},
                                     {"name": "ESTIMATED_EARNINGS", "currencyCode": "USD"}, {"name": "IMPRESSIONS"}],
                         "rows": [{"cells": [{"value": "2026-10-10"}, {"value": "ca-pub-1:111"}, {"value": "3.21"},
                                             {"value": "500"}]}]})

    run = sharing.import_adsense(db, start=date(2026, 10, 1), end=date(2026, 10, 31), transport=Transport())
    assert (run.status, run.rows) == ("OK", 1)
    b = db.query(AdvAdsenseBucket).one()
    assert (b.ad_unit, b.estimated_earnings, b.status) == ("ca-pub-1:111", Decimal("3.210000"), "ESTIMATED")
    b.status, b.finalized_earnings = "FINALIZED", Decimal("3.00")
    sharing.import_adsense(db, start=date(2026, 10, 1), end=date(2026, 10, 31), transport=Transport())
    assert b.finalized_earnings == Decimal("3.00")


# ---------------------------------------------------------------- Annual Ads

def test_annual_ads_never_enter_contest_sharing_and_record_buyer_only_when_signed(world):
    db = world
    buyer = _user(db, "aa-b@t.com")
    row = annualads_records.record_payment(
        db, tx_hash="0xabc", event="sponsor_payment_confirmed",
        payment={"amount": "100", "buyer_external_id": str(buyer.id), "slot_id": "S1", "end_date": "2027-10-01"},
        data={}, raw=b"{}", gross=Decimal("100"), fee=Decimal("30"), net=Decimal("70"), journal_entry_id=None)
    assert (row.buyer_match, row.buyer_user_id, row.sponsor_commission_status) == ("MATCHED", buyer.id, "PENDING_POLICY")
    assert row.entitlement_snapshot == {"slot_id": "S1", "end_date": "2027-10-01"}
    again = annualads_records.record_payment(db, tx_hash="0xabc", event="x", payment={}, data={}, raw=b"",
                                             gross=Decimal("1"), fee=Decimal("0"), net=Decimal("1"), journal_entry_id=None)
    assert again.id == row.id
    other = annualads_records.record_payment(db, tx_hash="0xdef", event="e", payment={"buyer_external_id": "abc"},
                                             data={}, raw=b"", gross=Decimal("1"), fee=Decimal("0"), net=Decimal("1"),
                                             journal_entry_id=None)
    assert other.buyer_match == "UNMATCHED" and other.buyer_user_id is None
    # The decision engine has no Annual Ads product, and the sharing calculator refuses it.
    from app.services import ad_revenue_policy as policy

    assert policy.contest_page_split(db, contestant=_entry(db, buyer), revenue_amount="100", is_annual_ad=True).applicable is False
    assert "ANNUAL_ADS" not in str(AdvServeDecision.__table__.c.product.type)


def test_annual_ads_recognition_scheduler_is_a_noop_when_disabled(monkeypatch):
    import asyncio

    from app.core.config import settings

    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", False)
    called = []
    monkeypatch.setattr("app.scripts.annualads_daily_recognition.run_daily_recognition", lambda db: called.append(1))
    asyncio.run(annualads_records.AnnualAdsRecognitionScheduler()._run_pass())
    assert called == []


# ---------------------------------------------------------------- member reporting

def test_member_summary_separates_creative_and_sponsor_and_estimates_are_not_available(world):
    db = world
    sponsor = _user(db, "ms2-s@t.com")
    creative = _user(db, "ms2-c@t.com", sponsor=sponsor)
    c = _entry(db, creative)
    adv = _user(db, "ms2-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "100.00")
    _campaign(db, adv, budget="100.00")
    _ordinary_month(db, c, n=10)
    s = sharing.member_summary(db, creative.id)
    assert s["creative"]["estimated"] == "2.00" and s["creative"]["available"] == "0.00"
    assert sharing.member_summary(db, sponsor.id)["sponsor"]["estimated"] == "0.10"
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    s = sharing.member_summary(db, creative.id)
    assert s["creative"]["estimated"] == "0.00" and s["creative"]["available"] == "2.00"
    lines = sharing.member_lines(db, creative.id)
    assert lines[0]["original_submission_type"] == "PERSONAL_SUBMISSION" and lines[0]["applied_percentage"] == "20.00"


def test_released_shares_use_the_existing_wallet_balance(world):
    db = world
    from app.services.financial_balances import get_commission_balance

    creative = _user(db, "wb-c@t.com")
    c = _entry(db, creative)
    adv = _user(db, "wb-a@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "100.00")
    _campaign(db, adv, budget="100.00")
    _ordinary_month(db, c, n=50)
    sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))
    bal = get_commission_balance(db, creative.id)
    earned = bal.get("earned_lifetime") if isinstance(bal, dict) else getattr(bal, "earned_lifetime", None)
    assert Decimal(str(earned)) == Decimal("10.00")
