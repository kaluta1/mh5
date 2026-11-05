"""Advertising final integration on REAL PostgreSQL: migration a2c4e6f8b0d3 upgrades, downgrades and refuses to
downgrade over its data; concurrent partial reversals reduce the sponsor commission exactly once each; a replayed
reversal key adjusts once; concurrent offsets for one sponsor never over-recover a receivable.
DISPOSABLE local database per test, synthetic rows. Opt-in: RUN_POSTGRES_TESTS=1."""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, text

from app.models.advertising_v2 import (AdvCampaign, AdvCampaignDay, AdvImpressionEvent, AdvSponsorAdjustment,
                                       AdvSponsorOffset, AdvSponsorReceivable)
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_sponsor_recovery as rec, ad_workflow as wf
from tests.integration.test_advertising_workflow_postgres import COMPLETE, _charge, _columns, _setup
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401
from tests.unit.test_advertising_program import T0, _fund
from tests.unit.test_new_business_model import _user

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]
D = Decimal
MIGRATION = "a2c4e6f8b0d3_advertising_final_integration.py"


def _sponsor(Session):
    with Session() as db:
        s = _user(db, f"s-{uuid.uuid4().hex[:6]}@t.com")
        admin = _user(db, f"adm-{uuid.uuid4().hex[:6]}@t.com")
        db.commit()
        return s.id, admin.id


def _live_for(Session, sponsor_id, admin_id):
    from app.models.user import User

    with Session() as db:
        sponsor = db.get(User, sponsor_id)
        adv = _user(db, f"a-{uuid.uuid4().hex[:6]}@t.com", sponsor=sponsor)
        _fund(db, adv, "50.00")
        c = camp.create_campaign(db, adv, name="W", budget="10.00", start_at=T0 - timedelta(days=1),
                                 end_at=T0 + timedelta(days=30), placements=["IN_FEED"])
        cr = wf.create_creative(db, c, dict(COMPLETE), actor_id=adv.id, draft=False)
        camp.submit_campaign(db, adv, c)
        admin = db.get(User, admin_id)
        camp.review_creative(db, admin, cr, approve=True, note="ok")
        camp.review_campaign(db, admin, c, approve=True, note="ok")
        db.commit()
        return c.id


def _pause(Session, cid, admin_id):
    from app.models.user import User

    with Session() as db:
        camp.set_paused(db, db.get(User, admin_id), db.get(AdvCampaign, cid), paused=True)
        db.commit()


def _recognize(Session):
    with Session() as db:
        dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
        db.commit()


def test_migration_upgrade_downgrade_upgrade_and_refusal_over_its_data(pg):
    engine, Session = pg
    _setup(Session, "1000.00", commission=True)
    built = _columns(engine)
    migrate(engine, MIGRATION, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("select count(*) from information_schema.tables where table_name in "
                              "('adv_sponsor_adjustments', 'adv_sponsor_receivables', 'adv_fixed_allocations', "
                              "'adv_lead_access_log')")).scalar() == 0
    migrate(engine, MIGRATION, "upgrade")
    assert _columns(engine) == built                                  # the migration builds what the models describe
    sponsor_id, admin_id = _sponsor(Session)
    cid = _live_for(Session, sponsor_id, admin_id)
    _charge(Session, 2)
    _recognize(Session)
    with Session() as db:
        day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == cid).one()
        assert D(str(day.sponsor_base_amount)) == D("2.00")
    with pytest.raises(Exception, match="final-integration data exists"):
        migrate(engine, MIGRATION, "downgrade")


def test_concurrent_partial_reversals_reduce_once_each_and_end_at_zero(pg):
    engine, Session = pg
    _setup(Session, "1000.00", commission=True)
    sponsor_id, admin_id = _sponsor(Session)
    cid = _live_for(Session, sponsor_id, admin_id)
    _charge(Session, 4)
    _recognize(Session)
    with Session() as db:
        ids = [e.id for e in db.query(AdvImpressionEvent).filter(AdvImpressionEvent.campaign_id == cid,
                                                                  AdvImpressionEvent.event_type == "VIEWABLE")]
    assert len(ids) == 4

    def work(i):
        with Session() as db:
            out = dl.reverse_invalid_activity(db, event_ids=[ids[i]], reason=f"bot {i}", actor_id=admin_id)
            db.commit()
            return out["reversed"]

    results = in_threads(4, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    with Session() as db:
        day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == cid).one()
        assert day.sponsor_commission_status == "REVERSED" and D(str(day.sponsor_reversed_amount)) == D("4.00")
        assert db.query(AdvSponsorAdjustment).count() == 4
        assert sum(D(str(a.reduction)) for a in db.query(AdvSponsorAdjustment)) == D("0.80")
        live = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor_id,
                                                    AffiliateCommission.status != CommissionStatus.CANCELLED).all()
        assert live == []


def test_replayed_reversal_key_adjusts_once(pg):
    engine, Session = pg
    _setup(Session, "1000.00", commission=True)
    sponsor_id, admin_id = _sponsor(Session)
    cid = _live_for(Session, sponsor_id, admin_id)
    _charge(Session, 4)
    _recognize(Session)
    with Session() as db:
        day_value = db.query(AdvCampaignDay.day).filter(AdvCampaignDay.campaign_id == cid).scalar()

    def work(i):
        with Session() as db:
            out = wf.after_charge_reversed(db, cid, day_value, reason="replay", amount=D("1.00"), key="same-key")
            db.commit()
            return out

    results = in_threads(5, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    with Session() as db:
        assert db.query(AdvSponsorAdjustment).count() == 1
        live = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor_id,
                                                    AffiliateCommission.status == CommissionStatus.APPROVED).all()
        assert [D(str(c.commission_amount)) for c in live] == [D("0.60")]


def test_concurrent_offsets_never_over_recover_a_receivable(pg):
    engine, Session = pg
    _setup(Session, "1000.00", commission=True)
    sponsor_id, admin_id = _sponsor(Session)
    days = []
    for _ in range(2):
        cid = _live_for(Session, sponsor_id, admin_id)
        _charge(Session, 2)
        _pause(Session, cid, admin_id)
        days.append(cid)
    _recognize(Session)                                                # two untouched 0.40 commissions
    with Session() as db:                                              # then a 0.40 receivable appears
        day0 = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == days[0]).one()
        adj = AdvSponsorAdjustment(idempotency_key="synthetic", campaign_day_id=day0.id, campaign_id=days[0],
                                   sponsor_user_id=sponsor_id, reversed_revenue=D("2.00"), base_before=D("2.00"),
                                   base_after=D("0.00"), rate=D("0.20"), entitlement_before=D("0.40"),
                                   entitlement_after=D("0.00"), reduction=D("0.40"), method="RECEIVABLE")
        db.add(adj)
        db.flush()
        db.add(AdvSponsorReceivable(sponsor_user_id=sponsor_id, adjustment_id=adj.id, campaign_day_id=day0.id,
                                    amount=D("0.40"), recovered=D("0"), status="OPEN"))
        db.commit()
        pairs = [(d.id, d.sponsor_commission_id) for d in
                 db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id.in_(days)).all()]

    def work(i):
        day_id, comm_id = pairs[i % 2]
        with Session() as db:
            day = db.query(AdvCampaignDay).filter(AdvCampaignDay.id == day_id).with_for_update().one()
            out = rec.offset_new_commission(db, day, db.get(AffiliateCommission, comm_id))
            db.commit()
            return out

    results = in_threads(4, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sum(results) == D("0.40")
    with Session() as db:
        r = db.query(AdvSponsorReceivable).one()
        assert (D(str(r.recovered)), r.status) == (D("0.40"), "RECOVERED")
        assert db.query(func.sum(AdvSponsorOffset.amount)).scalar() == D("0.40")
        live = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor_id,
                                                    AffiliateCommission.status == CommissionStatus.APPROVED).all()
        assert sum(D(str(c.commission_amount)) for c in live) == D("0.40")       # 0.80 earned - 0.40 recovered
        assert rec.reconciliation(db)["ok"]
