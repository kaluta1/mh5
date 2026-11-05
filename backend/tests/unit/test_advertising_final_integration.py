"""Advertising final integration (owner-approved decisions 2026-11-05): contest-entry sharing of CPC and Engagement
revenue, general inventory exclusion, coexistence with the advertiser's direct-sponsor commission, and the
fixed-price earned-revenue allocation foundation (Daily City stays NOT READY; the fixture marks it ready for the
test only). SYNTHETIC data only."""
from __future__ import annotations

import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.advertising_v2 import AdvAllocation, AdvCampaignDay, AdvFixedAllocation, AdvImpressionEvent
from app.models.affiliate import AffiliateCommission, CommissionType
from app.models.contests import SeasonLevel
from app.services import ad_delivery as dl, ad_fixed_allocation as fa, ad_packages as pk
from app.services import ad_revenue_sharing as sharing
from tests.unit.test_advertising_phase_a import _live, _settings, _viewer, city_ready  # noqa: F401
from tests.unit.test_advertising_phase_a_remediation import _earned_day, _viewables
from tests.unit.test_advertising_program import T0, UA, _entry, _fund, _ledger_balanced, _season
from tests.unit.test_new_business_model import _user, world  # noqa: F401

pytestmark = pytest.mark.unit
D = Decimal
PERIOD, CLOSE = "2026-10", datetime(2026, 11, 5)


def _clicks(db, contestant, n, *, page="CONTEST_ENTRY", slot="IN_CONTENT"):
    """n valid clicks (signed redirect path: SERVED then CLICK after > 1 s) on the given page."""
    for _ in range(n):
        v = _viewer()
        d = dl.decide(db, page_type=page, slot_kind=slot, slot_key="k", now=T0, viewer=v,
                      contestant_id=contestant.id if contestant else None, allowed_sources={"myhigh5_ads"})
        assert d["fill"], d
        dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="SERVED",
                        visible_ms=None, visible_ratio=None, page_visible=True, user_agent=UA, viewer=v,
                        now=T0 + timedelta(milliseconds=100))
        assert dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="CLICK",
                               visible_ms=None, visible_ratio=None, page_visible=True, user_agent=UA, viewer=v,
                               now=T0 + timedelta(seconds=3), allow_click=True, action="CTA_CLICK") == "RECORDED"
    dl.validate_pending(db, now=T0 + timedelta(seconds=10))


def _paid(db):
    out = {}
    for x in db.query(AffiliateCommission).filter(AffiliateCommission.commission_type == CommissionType.AD_REVENUE):
        out[x.user_id] = out.get(x.user_id, D(0)) + D(str(x.commission_amount))
    return out


@pytest.mark.parametrize("package", ["cpc", "engagement"])
def test_click_revenue_on_a_personal_entry_shares_20_plus_1_and_keeps_the_rate_at_later_levels(world, package):
    db = world
    cfg = _settings(db, package)
    cfg.frequency_cap_per_day = cfg.max_viewable_per_viewer_hour = 10000
    sponsor = _user(db, f"{package}-s@t.com")
    creative = _user(db, f"{package}-c@t.com", sponsor=sponsor)
    entry = _entry(db, creative)                                       # personal: starts at City
    adv = _user(db, f"{package}-a@t.com")
    _fund(db, adv, "100.00")
    _live(db, adv, package, rate="1.00", budget="100.00")
    _clicks(db, entry, 5)                                              # 5.00 at City
    _season(db, entry, SeasonLevel.COUNTRY)
    _clicks(db, entry, 5)                                              # 5.00 at Country, still personal
    charged = db.query(AdvImpressionEvent).filter(AdvImpressionEvent.event_type == "CLICK",
                                                  AdvImpressionEvent.charged_amount > 0).all()
    assert len(charged) == 10 and all(e.contestant_id == entry.id for e in charged)
    sharing.finalize_period(db, period=PERIOD, source="MYHIGH5", now=CLOSE)
    lines = db.query(AdvAllocation).filter(AdvAllocation.status == "RELEASED").all()
    assert {(l.role, l.contest_level, l.rate, l.amount) for l in lines} >= {
        ("CREATIVE", "city", D("0.2000"), D("1.00")), ("CREATIVE", "country", D("0.2000"), D("1.00"))}
    assert _paid(db) == {creative.id: D("2.00"), sponsor.id: D("0.10")}
    _ledger_balanced(db)


def test_click_revenue_on_a_nominated_entry_shares_10_plus_1(world):
    db = world
    cfg = _settings(db, "cpc")
    cfg.frequency_cap_per_day = cfg.max_viewable_per_viewer_hour = 10000
    nsponsor = _user(db, "nm-ns@t.com")
    nominee = _user(db, "nm-n@t.com", sponsor=nsponsor)
    nominator = _user(db, "nm-r@t.com", sponsor=_user(db, "nm-rs@t.com"))
    entry = _entry(db, nominator, "NOMINATION", nominee=nominee)        # nominated: starts at Country
    adv = _user(db, "nm-a@t.com")
    _fund(db, adv, "100.00")
    _live(db, adv, "cpc", rate="1.00", budget="100.00")
    _clicks(db, entry, 20)
    sharing.finalize_period(db, period=PERIOD, source="MYHIGH5", now=CLOSE)
    assert _paid(db) == {nominee.id: D("2.00"), nsponsor.id: D("0.20")}


def test_clicks_on_general_inventory_create_no_creator_share(world):
    db = world
    cfg = _settings(db, "cpc")
    cfg.frequency_cap_per_day = cfg.max_viewable_per_viewer_hour = 10000
    entry = _entry(db, _user(db, "gi-c@t.com"))
    adv = _user(db, "gi-a@t.com")
    _fund(db, adv, "100.00")
    _live(db, adv, "cpc", rate="1.00", budget="100.00")
    _clicks(db, entry, 3, page="CONTEST_LISTING", slot="IN_FEED")      # a listing showing the entry
    _clicks(db, None, 3, page="FEED", slot="IN_FEED")
    assert all(e.contestant_id is None for e in db.query(AdvImpressionEvent).all())
    assert sharing.finalize_period(db, period=PERIOD, source="MYHIGH5", now=CLOSE)["lines"] == 0


def test_advertiser_sponsor_commission_coexists_with_contest_entry_sharing(world):
    db = world
    cfg = _settings(db, "cpc")
    cfg.frequency_cap_per_day = cfg.max_viewable_per_viewer_hour = 10000
    cfg.advertiser_sponsor_commission_enabled = True
    creative = _user(db, "co-c@t.com")
    entry = _entry(db, creative)
    adv_sponsor = _user(db, "co-as@t.com")
    adv = _user(db, "co-a@t.com", sponsor=adv_sponsor)
    _fund(db, adv, "100.00")
    _live(db, adv, "cpc", rate="1.00", budget="100.00")
    _clicks(db, entry, 10)
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    sharing.finalize_period(db, period=PERIOD, source="MYHIGH5", now=CLOSE)
    day = db.query(AdvCampaignDay).one()
    assert (day.sponsor_commission_status, day.sponsor_commission_amount) == ("RECORDED", D("2.00"))   # 20% of 10
    assert _paid(db) == {creative.id: D("2.00")}                                                      # 20% of 10
    _ledger_balanced(db)


# ---------------------------------------------------------------- fixed-price allocation foundation

def test_split_is_exact_and_deterministic():
    shares = fa.split(D("5.00"), OrderedDict([("a", 1), ("b", 1), ("c", 1)]))
    assert shares == {"a": D("1.666667"), "b": D("1.666667"), "c": D("1.666666")}
    assert sum(shares.values()) == D("5.00")
    assert fa.split(D("5.00"), OrderedDict([("a", 1), ("b", 1), ("c", 1)])) == shares
    uneven = fa.split(D("0.000005"), OrderedDict([("x", 3), ("y", 2), ("z", 7)]))
    assert sum(uneven.values()) == D("0.000005") and all(v >= 0 for v in uneven.values())


def test_daily_city_is_still_not_ready_in_code():
    assert pk.PACKAGES["daily_city"].not_ready and pk.PACKAGES["daily_local"].not_ready


def test_earned_booked_day_is_allocated_exactly_once_reweighted_and_reversed(world, city_ready):
    db = world
    admin = _user(db, "fx-adm@t.com")
    c, booking, adv, at = _earned_day(db, threshold=2, residents=3)
    lines = db.query(AdvFixedAllocation).filter_by(booking_id=booking.id, status="ACTIVE").all()
    assert sum(D(str(l.amount)) for l in lines) == D(str(booking.charged_amount))
    assert fa.check(db, booking)["ok"]
    assert fa.allocate(db, booking) == lines                                   # rerun: no new version
    assert db.query(AdvFixedAllocation).count() == len(lines)
    events = _viewables(db, c)
    dl.reverse_invalid_activity(db, event_ids=[events[0].id], reason="farm", actor_id=admin.id)
    db.refresh(booking)
    assert booking.status == "EARNED"
    active = db.query(AdvFixedAllocation).filter_by(booking_id=booking.id, status="ACTIVE").all()
    assert {l.version for l in active} == {2} and sum(l.weight for l in active) == 2
    assert fa.check(db, booking)["ok"]
    db.refresh(events[0])
    assert events[0].allocated_amount == 0                                     # a reversed event keeps no share
    dl.reverse_invalid_activity(db, event_ids=[events[1].id], reason="farm", actor_id=admin.id)
    db.refresh(booking)
    assert booking.status == "REVERSED"
    assert db.query(AdvFixedAllocation).filter_by(booking_id=booking.id, status="ACTIVE").count() == 0
    assert db.query(AdvFixedAllocation).filter_by(booking_id=booking.id).count() == 2   # history kept
    assert fa.check(db, booking)["ok"]
    _ledger_balanced(db)
