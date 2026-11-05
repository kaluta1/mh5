"""Automated advertiser-sponsor commission recovery (owner-approved policy 2026-11-05). SYNTHETIC data only.

CPM 1000 USD -> every valid viewable impression is 1.00 USD of recognized revenue; 20% sponsor commission."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.advertising_v2 import (AdvCampaignDay, AdvImpressionEvent, AdvSponsorAdjustment, AdvSponsorOffset,
                                       AdvSponsorReceivable)
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_sponsor_recovery as rec, ad_workflow as wf
from tests.unit.test_advertising_program import T0, _balance, _configure, _ledger_balanced, _validate, _view
from tests.unit.test_advertising_workflow import _admin, _charged_day
from tests.unit.test_new_business_model import _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit
D = Decimal


def _on(db):
    cfg = _configure(db, "1000.00")
    cfg.frequency_cap_per_day = 100
    cfg.advertiser_sponsor_commission_enabled = True
    return cfg


def _day(db, c):
    return db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == c.id).one()


def _events(db, c):
    return (db.query(AdvImpressionEvent).filter(AdvImpressionEvent.event_type == "VIEWABLE",
                                                AdvImpressionEvent.campaign_id == c.id)
            .order_by(AdvImpressionEvent.id).all())


def _recognized(db, email, sponsor, n):
    adv, c = _charged_day(db, email, sponsor, n=n)
    dl.recognize_closed_days(db, now=T0 + timedelta(days=1))
    camp.set_paused(db, _admin(db), c, paused=True)          # later views go to the next campaign only
    return adv, c


def _live_commissions(db, sponsor):
    return (db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor.id,
                                                 AffiliateCommission.status != CommissionStatus.CANCELLED).all())


def _pay(db, c):
    c.status, c.payout_reference = CommissionStatus.PAID, "payout:test-1"
    db.flush()


def test_partial_reversal_reduces_unpaid_commission_proportionally_once(world):
    db = world
    _on(db)
    sponsor = _user(db, "r1-s@t.com")
    _, c = _recognized(db, "r1@t.com", sponsor, 4)                 # 4.00 recognized -> 0.80
    original = db.query(AffiliateCommission).one()
    assert original.commission_amount == D("0.80")
    admin = _admin(db)
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c)[0].id], reason="bot", actor_id=admin.id)
    day = _day(db, c)
    assert (day.sponsor_commission_status, day.sponsor_commission_amount) == ("ADJUSTED", D("0.60"))
    assert original.status == CommissionStatus.CANCELLED                     # history kept, row not resized
    assert original.commission_amount == D("0.80")
    live = _live_commissions(db, sponsor)
    assert [x.commission_amount for x in live] == [D("0.60")] and live[0].source_type == rec.ADJ_SOURCE
    adj = db.query(AdvSponsorAdjustment).one()
    assert (adj.reversed_revenue, adj.reduction, adj.method) == (D("1.00"), D("0.20"), "REISSUED")
    # replaying the same reversal (same key) changes nothing
    assert wf.after_charge_reversed(db, c.id, day.day, reason="bot", amount=D("1.00"),
                                    key=adj.idempotency_key.split(":", 2)[2]) == "REISSUED"
    assert db.query(AdvSponsorAdjustment).count() == 1 and len(_live_commissions(db, sponsor)) == 1
    assert db.query(AdvSponsorReceivable).count() == 0
    _ledger_balanced(db)


def test_example_100_dollars_reversing_25_reduces_20_commission_by_5(world):
    db = world
    _on(db)
    sponsor = _user(db, "r2-s@t.com")
    _, c = _recognized(db, "r2@t.com", sponsor, 1)
    day = _day(db, c)
    day.sponsor_base_amount = D("100.00")                          # the policy example, on the real code path
    comm = db.get(AffiliateCommission, day.sponsor_commission_id)
    assert rec.entitlement(D("100.00"), day.sponsor_rate) == D("20.00")
    assert rec.entitlement(D("75.00"), day.sponsor_rate) == D("15.00")
    comm.commission_amount = D("20.00")
    db.flush()
    rec.on_revenue_reversed(db, day, reversed_amount=D("25.00"), key="example", reason="example")
    assert db.query(AdvSponsorAdjustment).one().reduction == D("5.00")
    assert [x.commission_amount for x in _live_commissions(db, sponsor)] == [D("15.00")]


def test_full_reversal_cancels_unpaid_commission(world):
    db = world
    _on(db)
    sponsor = _user(db, "r3-s@t.com")
    _, c = _recognized(db, "r3@t.com", sponsor, 2)
    dl.reverse_invalid_activity(db, event_ids=[e.id for e in _events(db, c)], reason="all", actor_id=_admin(db).id)
    day = _day(db, c)
    assert day.sponsor_commission_status == "REVERSED" and day.sponsor_commission_id is None
    assert _live_commissions(db, sponsor) == []
    assert db.query(AdvSponsorAdjustment).one().method == "CANCELLED"
    _ledger_balanced(db)


def test_paid_commission_becomes_receivable_and_is_offset_from_future_earnings(world):
    db = world
    _on(db)
    sponsor = _user(db, "r4-s@t.com")
    _, c = _recognized(db, "r4@t.com", sponsor, 4)
    paid = db.query(AffiliateCommission).one()
    _pay(db, paid)
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c)[0].id], reason="bot", actor_id=_admin(db).id)
    assert (paid.status, paid.commission_amount, paid.payout_reference) == (CommissionStatus.PAID, D("0.80"),
                                                                            "payout:test-1")   # untouched
    r = db.query(AdvSponsorReceivable).one()
    assert (r.amount, r.recovered, r.status, r.sponsor_user_id) == (D("0.20"), D("0.00"), "OPEN", sponsor.id)
    assert _balance(db, rec.RECEIVABLE_ACCOUNT) == D("0.20")
    # the same sponsor earns again: 2 views -> 0.40 gross, 0.20 recovered, 0.20 net available
    _, c2 = _recognized(db, "r4b@t.com", sponsor, 2)
    day2 = _day(db, c2)
    live = [x for x in _live_commissions(db, sponsor) if x.status == CommissionStatus.APPROVED]
    assert [x.commission_amount for x in live] == [D("0.20")] and live[0].source_type == rec.NET_SOURCE
    assert day2.sponsor_commission_id == live[0].id and day2.sponsor_offset_amount == D("0.20")
    assert (r.recovered, r.status) == (D("0.20"), "RECOVERED")
    assert _balance(db, rec.RECEIVABLE_ACCOUNT) == D("0.00")
    assert db.query(AdvSponsorOffset).count() == 1
    assert rec.reconciliation(db)["ok"]
    _ledger_balanced(db)


def test_receivable_larger_than_new_commission_is_carried_forward_never_negative(world):
    db = world
    _on(db)
    sponsor = _user(db, "r5-s@t.com")
    _, c = _recognized(db, "r5@t.com", sponsor, 4)
    _pay(db, db.query(AffiliateCommission).one())
    dl.reverse_invalid_activity(db, event_ids=[e.id for e in _events(db, c)[:3]], reason="bot",
                                actor_id=_admin(db).id)
    r = db.query(AdvSponsorReceivable).one()
    assert r.amount == D("0.60")
    _, c2 = _recognized(db, "r5b@t.com", sponsor, 2)            # 0.40 earned: all of it recovers the receivable
    approved = [x for x in _live_commissions(db, sponsor) if x.status == CommissionStatus.APPROVED]
    assert approved == []                                          # no zero or negative row
    assert (r.recovered, r.status) == (D("0.40"), "OPEN") and rec.outstanding(db, sponsor.id) == D("0.20")
    assert _day(db, c2).sponsor_commission_status == "RECORDED"
    _ledger_balanced(db)


def test_recovery_never_crosses_members(world):
    db = world
    _on(db)
    s1, s2 = _user(db, "r6-a@t.com"), _user(db, "r6-b@t.com")
    _, c = _recognized(db, "r6@t.com", s1, 2)
    _pay(db, db.query(AffiliateCommission).one())
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c)[0].id], reason="bot", actor_id=_admin(db).id)
    _recognized(db, "r6b@t.com", s2, 2)
    other = [x for x in _live_commissions(db, s2) if x.status == CommissionStatus.APPROVED]
    assert [x.commission_amount for x in other] == [D("0.40")]       # s2 keeps everything
    assert rec.outstanding(db, s1.id) == D("0.20")


def test_partly_spent_or_reserved_commission_is_not_cancelled(world):
    db = world
    _on(db)
    sponsor = _user(db, "r7-s@t.com")
    _, c = _recognized(db, "r7@t.com", sponsor, 4)
    comm = db.query(AffiliateCommission).one()
    comm.payout_reference = "intent:cashout-9"                      # reserved by an in-flight payout
    db.flush()
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c)[0].id], reason="bot", actor_id=_admin(db).id)
    assert comm.status == CommissionStatus.APPROVED and comm.commission_amount == D("0.80")
    assert db.query(AdvSponsorReceivable).one().amount == D("0.20")
    assert _day(db, c).sponsor_commission_status == "ADJUSTED"


def test_missed_kyc_commission_reduces_retained_revenue_only(world):
    db = world
    _on(db)
    nokyc = _user(db, "r8-s@t.com", kyc=False)
    _, c = _recognized(db, "r8@t.com", nokyc, 4)
    assert _day(db, c).sponsor_commission_status == "MISSED_KYC"
    retained = _balance(db, rec.RETAINED_REVENUE_ACCOUNT)
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c)[0].id], reason="bot", actor_id=_admin(db).id)
    assert db.query(AdvSponsorAdjustment).one().method == "MISSED_ADJUSTED"
    assert _balance(db, rec.RETAINED_REVENUE_ACCOUNT) == retained + D("0.20")     # credit balance shrinks
    assert db.query(AffiliateCommission).count() == 0 and db.query(AdvSponsorReceivable).count() == 0
    _ledger_balanced(db)


def test_inconsistent_case_goes_to_finance_review(world):
    db = world
    _on(db)
    sponsor = _user(db, "r9-s@t.com")
    _, c = _recognized(db, "r9@t.com", sponsor, 2)
    comm = db.query(AffiliateCommission).one()
    comm.status = CommissionStatus.CANCELLED                        # cancelled outside this flow
    db.flush()
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c)[0].id], reason="bot", actor_id=_admin(db).id)
    assert _day(db, c).sponsor_commission_status == "FINANCE_REVIEW"
    assert db.query(AdvSponsorAdjustment).one().method == "FINANCE_REVIEW"


def test_finance_can_write_off_a_receivable(world):
    db = world
    _on(db)
    sponsor = _user(db, "r10-s@t.com")
    _, c = _recognized(db, "r10@t.com", sponsor, 2)
    _pay(db, db.query(AffiliateCommission).one())
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c)[0].id], reason="bot", actor_id=_admin(db).id)
    r = db.query(AdvSponsorReceivable).one()
    rec.resolve_receivable(db, r.id, action="WRITTEN_OFF", actor_id=_admin(db).id, note="uncollectable test")
    assert r.status == "WRITTEN_OFF" and _balance(db, rec.RECEIVABLE_ACCOUNT) == D("0.00")
    with pytest.raises(ValueError):
        rec.resolve_receivable(db, r.id, action="OPEN", actor_id=1, note="again")
    _ledger_balanced(db)


def test_switch_off_by_default_and_no_commission_before_recognition(world):
    db = world
    cfg = _configure(db, "1000.00")
    assert cfg.advertiser_sponsor_commission_enabled is False
    cfg.advertiser_sponsor_commission_enabled = True
    cfg.frequency_cap_per_day = 100
    sponsor = _user(db, "r11-s@t.com")
    _charged_day(db, "r11@t.com", sponsor, n=2)                   # deposit, reservation and charge: no commission
    assert db.query(AffiliateCommission).count() == 0
    _view(db, page_type="FEED", slot_kind="IN_FEED")              # reserved, not validated: still none
    _validate(db)
    assert db.query(AffiliateCommission).count() == 0


def test_reversal_after_a_fully_offset_commission_names_the_sponsor(world):
    """Review finding: the day's commission pointer is cleared by a full offset; the receivable must still be
    owed by the sponsor the commission was decided for."""
    db = world
    _on(db)
    sponsor = _user(db, "r12-s@t.com")
    _, c = _recognized(db, "r12@t.com", sponsor, 4)
    _pay(db, db.query(AffiliateCommission).one())
    dl.reverse_invalid_activity(db, event_ids=[e.id for e in _events(db, c)], reason="bot", actor_id=_admin(db).id)
    _, c2 = _recognized(db, "r12b@t.com", sponsor, 2)              # 0.40 gross, all offset: net 0, no live row
    day2 = _day(db, c2)
    assert day2.sponsor_commission_id is None and day2.sponsor_offset_amount == D("0.40")
    dl.reverse_invalid_activity(db, event_ids=[_events(db, c2)[0].id], reason="bot", actor_id=_admin(db).id)
    newest = db.query(AdvSponsorReceivable).order_by(AdvSponsorReceivable.id.desc()).first()
    assert (newest.sponsor_user_id, newest.amount, newest.status) == (sponsor.id, D("0.20"), "OPEN")
    assert _day(db, c2).sponsor_commission_status == "ADJUSTED"
    _ledger_balanced(db)
