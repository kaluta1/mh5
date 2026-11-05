"""Advertising workflow on REAL PostgreSQL: migration f1a3c5e7b9d2 upgrades, downgrades and refuses to downgrade
over workflow data; concurrent edits of an approved creative open one revision only; concurrent serving under a
daily limit never exceeds it; concurrent day recognition decides the advertiser's sponsor commission once;
concurrent reversals reverse it once. DISPOSABLE local database per test, synthetic rows.
Opt-in: RUN_POSTGRES_TESTS=1."""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, text

from app.models.advertising_v2 import AdvCampaign, AdvCampaignDay, AdvCreative, AdvImpressionEvent
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_workflow as wf
from tests.integration.test_payments_postgres import in_threads, migrate, pg, seed_ledger  # noqa: F401
from tests.unit.test_advertising_program import UA, T0, _fund
from tests.unit.test_new_business_model import _user

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]
D = Decimal
MIGRATION = "f1a3c5e7b9d2_advertising_workflow.py"
COMPLETE = {"headline": "Fresh coffee", "body": "Today", "display_name": "Acme", "cta_code": "SHOP_NOW",
            "destination_url": "https://acme.example/"}


def _setup(Session, cpm="0.50", *, commission=False):
    with Session() as db:
        seed_ledger(db)
        cfg = camp.get_settings(db)
        cfg.cpm_rate_usd, cfg.min_campaign_budget_usd = D(cpm), D("10.00")
        cfg.campaigns_enabled = cfg.funding_enabled = True
        cfg.frequency_cap_per_day = cfg.max_viewable_per_viewer_hour = 10000
        cfg.advertiser_sponsor_commission_enabled = commission
        db.commit()


def _live(Session, *, sponsor_email=None, budget="10.00", daily_cap=None):
    with Session() as db:
        sponsor = _user(db, sponsor_email) if sponsor_email else None
        adv = _user(db, f"a-{uuid.uuid4().hex[:6]}@t.com", sponsor=sponsor)
        _fund(db, adv, "50.00")
        c = camp.create_campaign(db, adv, name="W", budget=budget, daily_cap=daily_cap,
                                 start_at=T0 - timedelta(days=1), end_at=T0 + timedelta(days=30),
                                 placements=["IN_FEED"])
        cr = wf.create_creative(db, c, dict(COMPLETE), actor_id=adv.id, draft=False)
        camp.submit_campaign(db, adv, c)
        admin = _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")
        camp.review_creative(db, admin, cr, approve=True, note="ok")
        camp.review_campaign(db, admin, c, approve=True, note="ok")
        db.commit()
        return c.id, cr.id, adv.id, sponsor.id if sponsor else None


def _view(Session, i):
    viewer = f"v{i}-{uuid.uuid4().hex[:6]}"
    with Session() as db:
        d = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None, viewer=viewer,
                      now=T0, allowed_sources={"myhigh5_ads"})
        db.commit()
        if not d["fill"]:
            return d
        dl.record_event(db, decision_id=d["decision_id"], event_id=str(uuid.uuid4()), event_type="VIEWABLE",
                        visible_ms=1500, visible_ratio=0.8, page_visible=True, user_agent=UA, viewer=viewer,
                        now=T0 + timedelta(seconds=2))
        db.commit()
        return d


def _charge(Session, n):
    for i in range(n):
        _view(Session, i)
    with Session() as db:
        dl.validate_pending(db, now=T0 + timedelta(seconds=5))
        db.commit()


def _columns(engine):
    with engine.connect() as c:
        return c.execute(text(
            "select table_name, column_name, data_type, is_nullable from information_schema.columns "
            "where table_schema = 'public' and table_name like 'adv_%' order by 1, 2")).fetchall()


def test_migration_upgrade_downgrade_upgrade_and_refusal_over_workflow_data(pg):
    engine, Session = pg
    _setup(Session)
    built = _columns(engine)
    migrate(engine, MIGRATION, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("select count(*) from information_schema.columns where table_name = 'adv_creatives' "
                              "and column_name in ('display_name', 'cta_code', 'supersedes_creative_id')")).scalar() == 0
        assert c.execute(text("select is_nullable from information_schema.columns where table_name = 'adv_creatives' "
                              "and column_name = 'headline'")).scalar() == "NO"
    migrate(engine, MIGRATION, "upgrade")
    assert _columns(engine) == built                                  # the migration builds what the models describe
    cid, crid, _, _ = _live(Session)
    with Session() as db:                                             # legacy-shaped rows only: still downgradable?
        assert db.get(AdvCreative, crid).display_name == "Acme"       # no: workflow data exists
    with pytest.raises(Exception, match="Advertising workflow data exists"):
        migrate(engine, MIGRATION, "downgrade")
    with Session() as db:
        assert db.get(AdvCampaign, cid).status == "ACTIVE"             # nothing lost
        db.execute(text("insert into adv_creatives (campaign_id, review_status, destination_url, created_at, "
                        "updated_at) values (:c, 'DRAFT', '', now(), now())"), {"c": cid})
        db.commit()
        assert db.query(AdvCreative).filter(AdvCreative.headline.is_(None)).count() == 1


def test_concurrent_edits_of_an_approved_creative_open_one_revision(pg):
    engine, Session = pg
    _setup(Session)
    cid, crid, adv_id, _ = _live(Session)

    def work(i):
        with Session() as db:
            c, cr = db.get(AdvCampaign, cid), db.get(AdvCreative, crid)
            out = wf.edit_creative(db, c, cr, {"headline": f"Edit {i}"}, actor_id=adv_id)
            db.commit()
            return out.id

    results = in_threads(6, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert len(set(results)) == 1
    with Session() as db:
        assert db.query(AdvCreative).filter(AdvCreative.supersedes_creative_id == crid).count() == 1
        assert db.get(AdvCreative, crid).review_status == "APPROVED"  # the approved version keeps serving


def test_concurrent_serving_never_exceeds_the_daily_limit(pg):
    engine, Session = pg
    _setup(Session, "1000.00")
    cid, _, _, _ = _live(Session, budget="50.00", daily_cap="3.00")
    results = in_threads(12, lambda i: _view(Session, i))
    assert not [r for r in results if isinstance(r, Exception)], results
    with Session() as db:
        day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == cid).one()
        assert D(str(day.spent)) + D(str(day.reserved)) <= D("3.00")
        c = db.get(AdvCampaign, cid)
        assert D(str(c.spent)) + D(str(c.reserved)) <= D(str(c.budget_total))


def test_concurrent_recognition_decides_the_sponsor_commission_once(pg):
    engine, Session = pg
    _setup(Session, "1000.00", commission=True)
    cid, _, adv_id, sponsor_id = _live(Session, sponsor_email=f"s-{uuid.uuid4().hex[:6]}@t.com")
    _charge(Session, 3)

    def work(i):
        with Session() as db:
            n = dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
            db.commit()
            return n

    results = in_threads(5, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sum(results) == 1
    with Session() as db:
        comm = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor_id).all()
        assert len(comm) == 1 and D(str(comm[0].commission_amount)) == D("0.60")
        assert (comm[0].source_type, comm[0].source_user_id) == (wf.SPONSOR_SOURCE, adv_id)


def test_concurrent_full_reversals_reverse_the_commission_once(pg):
    engine, Session = pg
    _setup(Session, "1000.00", commission=True)
    cid, _, _, sponsor_id = _live(Session, sponsor_email=f"s-{uuid.uuid4().hex[:6]}@t.com")
    _charge(Session, 2)
    with Session() as db:
        dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
        admin = _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")
        db.commit()
        admin_id = admin.id
        ids = [e.id for e in db.query(AdvImpressionEvent).filter(AdvImpressionEvent.campaign_id == cid,
                                                                  AdvImpressionEvent.event_type == "VIEWABLE")]

    def work(i):
        with Session() as db:
            out = dl.reverse_invalid_activity(db, event_ids=ids, reason="bots", actor_id=admin_id)
            db.commit()
            return out["reversed"]

    results = in_threads(4, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sum(results) == 2
    with Session() as db:
        day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == cid).one()
        assert day.sponsor_commission_status == "REVERSED" and D(str(day.spent)) == 0
        comm = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor_id).one()
        assert comm.status == CommissionStatus.CANCELLED
        assert db.query(func.count(AffiliateCommission.id)).scalar() == 1
