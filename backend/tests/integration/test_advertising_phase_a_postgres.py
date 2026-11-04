"""Advertising Phase A on REAL PostgreSQL: concurrent serving, click validation, booking settlement, lead
acceptance and campaign completion can never overspend a budget or take money twice; migration d4f6a8b0c2e5
upgrades, downgrades and refuses to downgrade over Phase A data. Same safety rules as test_payments_postgres:
a DISPOSABLE local database per test, synthetic rows. Opt-in: RUN_POSTGRES_TESTS=1."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.advertising_v2 import (AdvBooking, AdvCampaign, AdvCreditMovement, AdvImpressionEvent, AdvLead,
                                       AdvServeDecision)
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_leads
from tests.integration.test_payments_postgres import _settings, in_threads, migrate, pg, seed_ledger  # noqa: F401
from tests.unit.test_advertising_phase_a import _city, _inventory, _resident
from tests.unit.test_advertising_program import UA, T0, _fund
from tests.unit.test_new_business_model import _user

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]
D = Decimal
MIGRATION = "d4f6a8b0c2e5_advertising_phase_a_packages.py"


def _setup(Session, *packages):
    with Session() as db:
        seed_ledger(db)
        cfg = camp.get_settings(db)
        cfg.cpm_rate_usd, cfg.min_campaign_budget_usd = D("0.50"), D("10.00")
        cfg.campaigns_enabled = cfg.funding_enabled = True
        cfg.enabled_packages = list(packages)
        cfg.daily_city_min_impressions = 1 if "daily_city" in packages else None
        db.commit()


def _cpc_campaign(Session, budget="0.10"):
    with Session() as db:
        adv = _user(db, f"a-{uuid.uuid4().hex[:6]}@t.com")
        _fund(db, adv, "10.00")
        c = camp.create_campaign(db, adv, name="C", budget=budget, start_at=T0 - timedelta(days=1),
                                 end_at=T0 + timedelta(days=30), placements=["IN_FEED"], package="cpc")
        cr = camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://example.com/")
        camp.submit_campaign(db, adv, c)
        admin = _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")
        camp.review_creative(db, admin, cr, approve=True, note="ok")
        camp.review_campaign(db, admin, c, approve=True, note="ok")
        db.commit()
        return c.id, adv.id


def _serve(Session, viewer=None):
    viewer = viewer or dl.viewer_hash(None, f"10.2.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}", UA)
    with Session() as db:
        d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer=viewer,
                      now=T0, allowed_sources={"myhigh5_ads"})
        db.commit()
        return d, viewer


def _campaign(Session, campaign_id):
    with Session() as db:
        c = db.get(AdvCampaign, campaign_id)
        return D(str(c.spent)), D(str(c.reserved)), D(str(c.budget_total))


def test_concurrent_cpc_serving_never_reserves_beyond_the_budget(pg):
    _e, Session = pg
    _setup(Session, "cpc")
    cid, _ = _cpc_campaign(Session, budget="0.10")                 # room for exactly two clicks
    results = in_threads(8, lambda i: _serve(Session)[0])
    assert not any(isinstance(r, Exception) for r in results), results
    assert sum(1 for r in results if r["fill"]) == 2
    spent, reserved, budget = _campaign(Session, cid)
    assert (spent, reserved) == (0, D("0.100000")) and spent + reserved <= budget


def test_concurrent_validation_and_replays_charge_a_click_once(pg):
    _e, Session = pg
    _setup(Session, "cpc")
    cid, _ = _cpc_campaign(Session, budget="1.00")
    d, viewer = _serve(Session)

    def beacon(kind, seconds):
        with Session() as db:
            out = dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type=kind,
                                  visible_ms=1500, visible_ratio=0.8, page_visible=True, user_agent=UA, viewer=viewer,
                                  now=T0 + timedelta(seconds=seconds), allow_click=True)
            db.commit()
            return out

    beacon("SERVED", 0.2)
    replays = in_threads(5, lambda i: beacon("CLICK", 3))          # one click, delivered five times at once
    assert sorted(replays).count("RECORDED") == 1 and set(replays) <= {"RECORDED", "DUPLICATE"}, replays

    def validate(_i):
        with Session() as db:
            out = dl.validate_pending(db, now=T0 + timedelta(seconds=10))
            db.commit()
            return out

    assert not any(isinstance(r, Exception) for r in in_threads(4, validate))
    spent, reserved, _budget = _campaign(Session, cid)
    assert (spent, reserved) == (D("0.050000"), 0)


def test_completion_racing_charging_never_overspends_or_leaves_a_reservation(pg):
    _e, Session = pg
    _setup(Session, "cpc")
    cid, _ = _cpc_campaign(Session, budget="0.10")
    pairs = [_serve(Session) for _ in range(2)]
    with Session() as db:
        for d, viewer in pairs:
            for kind, s in (("SERVED", 0.2), ("CLICK", 3)):
                dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type=kind,
                                visible_ms=None, visible_ratio=None, page_visible=None, user_agent=UA, viewer=viewer,
                                now=T0 + timedelta(seconds=s), allow_click=True)
        db.commit()

    def work(i):
        with Session() as db:
            if i == 0:
                c = db.query(AdvCampaign).filter(AdvCampaign.id == cid).with_for_update().one()
                camp.complete_campaign(db, c, reason="ENDED")
            else:
                dl.validate_pending(db, now=T0 + timedelta(seconds=10))
            db.commit()
            return "ok"

    assert in_threads(2, work) == ["ok", "ok"]
    with Session() as db:
        dl.validate_pending(db, now=T0 + timedelta(seconds=10))
        db.commit()
    spent, reserved, budget = _campaign(Session, cid)
    assert spent == D("0.100000") and reserved == 0 and spent <= budget


def test_concurrent_booking_settlement_charges_or_returns_once(pg):
    _e, Session = pg
    _setup(Session, "daily_city")
    day1 = datetime.utcnow().date() + timedelta(days=1)
    with Session() as db:
        city = _city(db)
        _inventory(db, city, 30)
        adv = _user(db, f"d-{uuid.uuid4().hex[:6]}@t.com")
        _fund(db, adv, "20.00")
        c = camp.create_campaign(db, adv, name="D", package="daily_city", placements=["IN_FEED"],
                                 bookings={"city_id": city.id, "days": [day1, day1 + timedelta(days=1)]})
        cr = camp.add_creative(db, c, headline="h", body=None, image_url=None, destination_url="https://example.com/")
        camp.submit_campaign(db, adv, c)
        admin = _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")
        camp.review_creative(db, admin, cr, approve=True, note="ok")
        camp.review_campaign(db, admin, c, approve=True, note="ok")
        resident = _resident(db, city)
        db.commit()
        cid, adv_id, resident_id, city_id = c.id, adv.id, resident.id, city.id
    at = datetime.combine(day1, datetime.min.time()) + timedelta(hours=9)
    viewer = dl.viewer_hash_for_user(resident_id)
    with Session() as db:
        d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer=viewer,
                      now=at, allowed_sources={"myhigh5_ads"}, viewer_user_id=resident_id)
        dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="VIEWABLE",
                        visible_ms=1500, visible_ratio=0.8, page_visible=True, user_agent=UA, viewer=viewer,
                        now=at + timedelta(seconds=2))
        dl.validate_pending(db, now=at + timedelta(seconds=5))
        db.commit()
        assert db.get(AdvServeDecision, d["decision_id"]).viewer_city_id == city_id
    after = datetime.combine(day1 + timedelta(days=2), datetime.min.time()) + timedelta(hours=3)

    def settle(_i):
        with Session() as db:
            n = dl.settle_bookings(db, now=after)
            db.commit()
            return n

    results = in_threads(4, settle)
    assert not any(isinstance(r, Exception) for r in results), results
    assert sum(results) == 2                                         # two days, each settled once in total
    with Session() as db:
        statuses = sorted(b.status for b in db.query(AdvBooking).filter_by(campaign_id=cid))
        returns = db.query(AdvCreditMovement).filter(AdvCreditMovement.idempotency_key.like("booking:%")).count()
        assert statuses == ["EARNED", "RETURNED"] and returns == 1
        assert camp.credit_balance(db, adv_id) == D("15.00")        # 20 - 10 booked + 5 returned, once
    spent, reserved, budget = _campaign(Session, cid)
    assert (spent, reserved, budget) == (D("5.000000"), 0, D("5.000000"))


def test_concurrent_lead_acceptance_charges_once_and_never_beyond_budget(pg):
    _e, Session = pg
    _setup(Session)
    with Session() as db:
        adv = _user(db, f"l-{uuid.uuid4().hex[:6]}@t.com")
        c = AdvCampaign(advertiser_user_id=adv.id, name="L", status="ACTIVE", pricing_model="LEAD",
                        unit_rate_usd=D("0.25"), budget_total=D("0.25"), spent=0, reserved=0, placements=["IN_FEED"])
        db.add(c)
        db.flush()
        leads = [ad_leads._record(db, campaign_id=c.id, name="N", contact=f"p{i}@example.com", consent=True,
                                  consent_version="v1", decision_id=None, now=T0).id for i in range(2)]
        db.commit()
        cid = c.id

    def accept(i):
        with Session() as db:
            try:
                ad_leads.accept(db, leads[i % 2], now=T0 + timedelta(days=1))
                db.commit()
                return "accepted"
            except ad_leads.LeadError as exc:
                db.rollback()
                return exc.code

    results = in_threads(6, accept)                                  # the same two leads, three times each
    assert results.count("accepted") == 1, results                  # the budget pays exactly one lead
    assert set(results) <= {"accepted", "ALREADY_DECIDED", "BUDGET_EXHAUSTED"}
    spent, reserved, budget = _campaign(Session, cid)
    assert spent == D("0.250000") and spent <= budget


def _adv_columns(engine):
    with engine.connect() as c:
        return c.execute(text(
            "select table_name, column_name, data_type, is_nullable from information_schema.columns "
            "where table_schema = 'public' and table_name like 'adv_%' order by 1, 2")).fetchall()


def test_migration_upgrade_downgrade_upgrade_and_refusal_over_phase_a_data(pg):
    engine, Session = pg
    _setup(Session)
    built = _adv_columns(engine)
    migrate(engine, MIGRATION, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("select to_regclass('public.adv_bookings')")).scalar() is None
        assert c.execute(text("select count(*) from information_schema.columns where table_name = 'adv_campaigns' "
                              "and column_name = 'unit_rate_usd'")).scalar() == 0
    migrate(engine, MIGRATION, "upgrade")
    assert _adv_columns(engine) == built                             # the migration builds what the models describe
    with Session() as db:
        adv = _user(db, "m@t.com")
        db.add(AdvCampaign(advertiser_user_id=adv.id, name="X", status="DRAFT", pricing_model="CPC",
                           unit_rate_usd=D("0.05"), budget_total=D("1"), spent=0, reserved=0, placements=["IN_FEED"]))
        db.commit()
    with pytest.raises(Exception, match="Advertising Phase A data exists"):
        migrate(engine, MIGRATION, "downgrade")
    with Session() as db:
        assert db.query(AdvCampaign).filter_by(pricing_model="CPC").count() == 1   # nothing lost
        assert db.query(AdvLead).count() == 0 and db.query(AdvImpressionEvent).count() == 0
