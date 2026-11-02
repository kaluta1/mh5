"""Owner rule 2026-11-02: only KYC-approved members earn commissions or advertising revenue shares.
SYNTHETIC members only. An unverified earner gets no commission and no liability; the amount stays MyHigh5
revenue, reclassified apart (Dr <source revenue> / Cr 4030, never recognized twice), and one missed earning
is recorded (never payable, never in a balance). The KYC decision is taken at the earning event, once."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.models.advertising_v2 import AdvAllocation
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.contest_eligibility import ContestEntrySafety
from app.models.kyc import KYCStatus, KYCVerification
from app.models.missed_earning import MissedEarning
from app.services import ad_revenue_sharing as sharing
from app.services import missed_earnings
from app.services.commission_distribution import process_payment_validation
from app.services.financial_balances import get_commission_balance
from app.services.financial_reversal import reverse_provider_refund
from app.services.new_model_payments import recognize_deferred_deposit
from app.services.new_model_revenue import accrue_direct_commission, compute_breakdown, get_policy
from tests.unit.test_advertising_program import _campaign, _configure, _entry, _fund, _ordinary_month
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_new_business_model import (  # noqa: F401  (fixtures)
    _assert_all_journals_balance,
    _balance,
    _deposit,
    _retired_legacy,
    _user,
    world,
)

pytestmark = pytest.mark.unit

NOT_APPROVED = [None, KYCStatus.PENDING, KYCStatus.IN_PROGRESS, KYCStatus.PENDING_PROOF_OF_ADDRESS,
                KYCStatus.REJECTED, KYCStatus.EXPIRED, KYCStatus.REQUIRES_REVIEW]


def set_kyc(db, user, status):
    """status None = no verification at all."""
    db.query(KYCVerification).filter(KYCVerification.user_id == user.id).delete()
    if status is not None:
        db.add(KYCVerification(user_id=user.id, status=status, submitted_at=datetime.utcnow()))
    db.flush()


def unverified(db, email, status=None, **kw):
    u = _user(db, email, kyc=False, **kw)
    set_kyc(db, u, status)
    return u


def pay(db, deposit):
    assert process_payment_validation(db, deposit, defer_commit=True) is True
    db.commit()


def missed(db, user=None):
    q = db.query(MissedEarning)
    return q.filter(MissedEarning.user_id == user.id).all() if user is not None else q.all()


# ---------------------------------------------------------------- referral commissions

def test_an_approved_sponsor_earns_the_usual_20_percent(world):
    db = world
    sponsor = _user(db, "ok-s@t.com")
    pay(db, _deposit(db, _user(db, "ok-p@t.com", sponsor=sponsor), "annual_membership"))
    c = db.query(AffiliateCommission).one()
    assert (c.user_id, c.commission_amount, c.status) == (sponsor.id, Decimal("10.00"), CommissionStatus.APPROVED)
    assert missed(db) == [] and _balance(db, "4030") == 0
    assert _balance(db, "5001") == Decimal("10.00") and _balance(db, "2001") == Decimal("-10.00")


@pytest.mark.parametrize("status", NOT_APPROVED, ids=lambda s: s.value if s else "no-kyc")
def test_an_unverified_sponsor_earns_nothing_and_myhigh5_keeps_it(world, status):
    db = world
    sponsor = unverified(db, "un-s@t.com", status)
    sponsor.is_verified = sponsor.email_verified = True                 # email verification is no substitute
    payer = _user(db, "un-p@t.com", sponsor=sponsor)
    deposit = _deposit(db, payer, "annual_membership")
    pay(db, deposit)
    assert db.query(AffiliateCommission).count() == 0                   # no payable commission
    [m] = missed(db, sponsor)
    assert (m.amount, m.category, m.source_type, m.source_id) == (Decimal("10.00"), "REFERRAL_COMMISSION",
                                                                  "DEPOSIT", deposit.id)
    assert m.rate == Decimal("0.2000") and m.kyc_status == (status.value if status else "none")
    assert m.source_product == "MEMBERSHIP" and m.status == "RECORDED"
    # Revenue recognized once ($50); $10 of it classified as retained; no expense, no liability.
    assert _balance(db, "4002") + _balance(db, "4030") == Decimal("-50.00")
    assert (_balance(db, "4002"), _balance(db, "4030")) == (Decimal("-40.00"), Decimal("-10.00"))
    assert _balance(db, "5001") == 0 and _balance(db, "2001") == 0
    assert get_commission_balance(db, sponsor.id).available == 0         # never withdrawable
    _assert_all_journals_balance(db)


def test_duplicate_webhooks_record_one_missed_earning_and_one_reclassification(world):
    db = world
    sponsor = unverified(db, "dup-s@t.com")
    deposit = _deposit(db, _user(db, "dup-p@t.com", sponsor=sponsor), "annual_membership")
    for _ in range(3):
        pay(db, deposit)
    assert len(missed(db)) == 1 and db.query(AffiliateCommission).count() == 0
    assert _balance(db, "4030") == Decimal("-10.00")
    _assert_all_journals_balance(db)


def test_kyc_fee_missed_at_payment_is_reclassified_only_when_revenue_is_recognized(world):
    db = world
    sponsor = unverified(db, "kf-s@t.com", KYCStatus.PENDING)
    deposit = _deposit(db, _user(db, "kf-p@t.com", sponsor=sponsor), "kyc")
    pay(db, deposit)
    [m] = missed(db)
    assert m.amount == Decimal("2.00") and m.journal_entry_id is None    # revenue still deferred
    assert _balance(db, "2113") == Decimal("-10.00") and _balance(db, "4030") == 0
    assert _balance(db, "1230") == 0 and _balance(db, "2001") == 0
    set_kyc(db, sponsor, KYCStatus.APPROVED)                             # approved later: does not change it
    assert recognize_deferred_deposit(db, deposit) is True
    db.commit()
    assert db.query(AffiliateCommission).count() == 0
    assert (_balance(db, "4001"), _balance(db, "4030")) == (Decimal("-6.00"), Decimal("-2.00"))
    assert _balance(db, "5001") == 0 and _balance(db, "1230") == 0 and _balance(db, "2113") == 0
    _assert_all_journals_balance(db)


def test_the_decision_taken_at_payment_survives_a_later_kyc_change(world):
    db = world
    sponsor = _user(db, "dc-s@t.com")                                    # approved when the fee is paid
    deposit = _deposit(db, _user(db, "dc-p@t.com", sponsor=sponsor), "kyc")
    pay(db, deposit)
    set_kyc(db, sponsor, KYCStatus.REJECTED)                             # revoked before recognition
    recognize_deferred_deposit(db, deposit)
    db.commit()
    c = db.query(AffiliateCommission).one()
    assert c.user_id == sponsor.id and c.status == CommissionStatus.APPROVED and missed(db) == []


def test_later_kyc_approval_keeps_missed_history_and_only_future_events_earn(world, client):
    db = world
    sponsor = unverified(db, "la-s@t.com", KYCStatus.IN_PROGRESS)
    payer = _user(db, "la-p@t.com", sponsor=sponsor)
    first = _deposit(db, payer, "annual_membership", tag="1")
    pay(db, first)
    set_kyc(db, sponsor, KYCStatus.APPROVED)
    pay(db, first)                                                       # a retry of the old event
    assert db.query(AffiliateCommission).count() == 0                    # never recreated as payable
    second = _deposit(db, payer, "annual_membership", tag="2", deposit_id=9002)
    pay(db, second)
    c = db.query(AffiliateCommission).one()
    assert (c.source_id, c.commission_amount) == (second.id, Decimal("10.00"))
    assert [m.source_id for m in missed(db, sponsor)] == [first.id]      # history kept after verification
    body = client.get("/api/v1/affiliates/commissions/missed", headers=auth(sponsor)).json()
    assert body["total"] == "10.00" and body["count"] == 1 and body["kyc_status"] == "approved"
    assert body["items"][0]["payable"] is False and body["items"][0]["percentage"] == "20.00"
    assert get_commission_balance(db, sponsor.id).available == Decimal("10.00")   # only the earned one


def test_refund_of_a_missed_source_reverses_the_reclassification(world):
    db = world
    sponsor = unverified(db, "rf-s@t.com")
    deposit = _deposit(db, _user(db, "rf-p@t.com", sponsor=sponsor), "annual_membership")
    pay(db, deposit)
    assert reverse_provider_refund(db, deposit, {"refund_amount": "50.00"}) is True
    assert reverse_provider_refund(db, deposit, {"refund_amount": "50.00"}) is True   # idempotent
    db.commit()
    [m] = missed(db)
    assert m.status == "REVERSED" and m.reversed_at is not None
    assert _balance(db, "4030") == 0 and _balance(db, "4002") == 0
    _assert_all_journals_balance(db)


@pytest.mark.parametrize("product,category,revenue", [("referral_pool_entry", "REFERRAL_POOL_ENTRY", "4008"),
                                                      ("marketplace_markup", "MARKETPLACE_MARKUP", "4007")])
def test_every_commission_source_uses_the_same_rule(world, product, category, revenue):
    db = world
    sponsor = unverified(db, f"src-{product}-s@t.com")
    payer = _user(db, f"src-{product}-p@t.com", sponsor=sponsor)
    breakdown = compute_breakdown(get_policy(db, product), Decimal("100.00"))
    for _ in range(2):
        assert accrue_direct_commission(db, source_type="TEST_SOURCE", source_id=77, payer_user_id=payer.id,
                                        breakdown=breakdown) is None
    [m] = missed(db)
    assert (m.source_product, m.revenue_account, m.amount) == (category, revenue, breakdown.direct_commission)
    assert db.query(AffiliateCommission).count() == 0 and _balance(db, "4030") == -breakdown.direct_commission


def test_historical_commissions_are_never_touched(world):
    db = world
    sponsor = unverified(db, "hist-s@t.com")
    old = AffiliateCommission(user_id=sponsor.id, source_user_id=sponsor.id, commission_type=CommissionType.KYC_PAYMENT,
                              level=1, base_amount=Decimal("10.00"), commission_amount=Decimal("2.00"),
                              status=CommissionStatus.APPROVED, transaction_date=datetime(2026, 10, 20),
                              business_model_version="NEW_V2", source_type="DEPOSIT", source_id=999999)
    db.add(old)
    db.commit()
    pay(db, _deposit(db, _user(db, "hist-p@t.com", sponsor=sponsor), "annual_membership"))
    db.refresh(old)
    assert (old.status, old.commission_amount) == (CommissionStatus.APPROVED, Decimal("2.00"))
    assert len(missed(db)) == 1                                          # only the new event


# ---------------------------------------------------------------- member and admin API

def test_members_see_only_their_own_missed_earnings(world, client):
    db = world
    a = unverified(db, "api-a@t.com")
    b = unverified(db, "api-b@t.com")
    pay(db, _deposit(db, _user(db, "api-p@t.com", sponsor=a), "annual_membership"))
    assert client.get("/api/v1/affiliates/commissions/missed").status_code == 401
    mine = client.get("/api/v1/affiliates/commissions/missed", headers=auth(a)).json()
    theirs = client.get("/api/v1/affiliates/commissions/missed", headers=auth(b)).json()
    assert (mine["count"], mine["total"]) == (1, "10.00") and (theirs["count"], theirs["total"]) == (0, "0.00")
    assert "Complete KYC" in mine["message"] and mine["kyc_url"] == "/dashboard/kyc"
    page = client.get("/api/v1/affiliates/commissions/missed?skip=1&limit=1", headers=auth(a)).json()
    assert page["items"] == [] and page["count"] == 1
    assert client.post("/api/v1/affiliates/commissions/missed", headers=auth(a), json={}).status_code == 405
    assert client.get("/api/v1/admin/finance/missed-earnings", headers=auth(a)).status_code == 403
    admin = _user(db, "api-admin@t.com")
    admin.is_admin = True
    db.commit()
    report = client.get("/api/v1/admin/finance/missed-earnings", headers=auth(admin)).json()
    assert report["by_category"]["REFERRAL_COMMISSION"] == {"count": 1, "amount": "10.00"}


# ---------------------------------------------------------------- advertising revenue shares

def _month(db, creative_entry, n=100):
    adv = _user(db, f"adv-{creative_entry.id}@t.com")
    _configure(db, "1000.00")
    _fund(db, adv, "1000.00")
    _campaign(db, adv, budget="1000.00")
    _ordinary_month(db, creative_entry, n=n)                            # n x $1.00 eligible revenue


def _finalize(db):
    return sharing.finalize_period(db, period="2026-10", source="MYHIGH5", now=datetime(2026, 11, 5))


def _paid(db):
    out = {}
    for x in db.query(AffiliateCommission).filter(AffiliateCommission.commission_type == CommissionType.AD_REVENUE):
        out[x.user_id] = out.get(x.user_id, Decimal(0)) + Decimal(str(x.commission_amount))
    return out


def test_verified_creative_and_unverified_sponsor(world):
    db = world
    sponsor = unverified(db, "a1-s@t.com", KYCStatus.PENDING)
    creative = _user(db, "a1-c@t.com", sponsor=sponsor)
    _month(db, _entry(db, creative))                                     # personal entry, $100
    _finalize(db)
    assert _paid(db) == {creative.id: Decimal("20.00")}                  # creative 20, sponsor 0
    [m] = missed(db, sponsor)
    assert (m.category, m.amount, m.revenue_account) == ("AD_SPONSOR_SHARE", Decimal("1.00"), "4020")
    assert _balance(db, "4030") == Decimal("-1.00")                      # MyHigh5 keeps 80 (79 + 1)
    assert _balance(db, "5006") == Decimal("20.00")
    _assert_all_journals_balance(db)


def test_unverified_creative_and_verified_sponsor(world):
    db = world
    sponsor = _user(db, "a2-s@t.com")
    creative = unverified(db, "a2-c@t.com", sponsor=sponsor)
    entry = _entry(db, creative)
    _month(db, entry)
    _finalize(db)
    assert _paid(db) == {sponsor.id: Decimal("1.00")}                    # the sponsor's 1% is independent
    [m] = missed(db, creative)
    assert (m.category, m.amount, m.contestant_id, m.origin_kind) == ("AD_CREATIVE_SHARE", Decimal("20.00"), entry.id,
                                                                      "PERSONAL_SUBMISSION")
    assert _balance(db, "4030") == Decimal("-20.00") and _balance(db, "5006") == Decimal("1.00")   # MyHigh5 99
    line = db.query(AdvAllocation).filter(AdvAllocation.role == "CREATIVE").one()
    assert line.status == "MISSED_KYC" and line.commission_id is None and line.beneficiary_key == -creative.id
    _assert_all_journals_balance(db)


def test_unverified_nominee_misses_10_and_the_nominator_never_gets_it(world):
    db = world
    nominee = unverified(db, "a3-n@t.com")
    nominator = _user(db, "a3-r@t.com")
    _month(db, _entry(db, nominator, "NOMINATION", nominee=nominee))
    _finalize(db)
    assert _paid(db) == {}
    [m] = missed(db, nominee)
    assert (m.amount, m.rate) == (Decimal("10.00"), Decimal("0.1000"))
    assert missed(db, nominator) == []


def test_kyc_is_taken_at_the_impression_not_at_the_monthly_release(world):
    db = world
    early = _user(db, "a4-e@t.com")                                      # approved at the event
    late = unverified(db, "a4-l@t.com")                                  # not approved at the event
    _month(db, _entry(db, early))
    _month(db, _entry(db, late))
    set_kyc(db, early, KYCStatus.EXPIRED)
    set_kyc(db, late, KYCStatus.APPROVED)
    _finalize(db)
    assert _paid(db) == {early.id: Decimal("20.00")}
    assert [m.amount for m in missed(db, late)] == [Decimal("20.00")] and missed(db, early) == []


def test_finalizing_twice_duplicates_nothing(world):
    db = world
    creative = unverified(db, "a5-c@t.com")
    _month(db, _entry(db, creative))
    _finalize(db)
    assert _finalize(db)["status"] == "ALREADY_FINALIZED"
    assert len(missed(db)) == 1 and _balance(db, "4030") == Decimal("-20.00")


def test_a_nominee_claiming_without_kyc_misses_the_held_share(world):
    db = world
    nominator = _user(db, "a6-r@t.com")
    entry = _entry(db, nominator, "NOMINATION")                          # no nominee account yet
    _month(db, entry)
    _finalize(db)
    assert _balance(db, "2322") == Decimal("-11.00")                     # held, as before
    nominee = unverified(db, "a6-n@t.com", KYCStatus.REJECTED)
    db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == entry.id).update(
        {"nominee_user_id": nominee.id})
    assert sharing.release_claimed(db) == 1
    line = db.query(AdvAllocation).filter(AdvAllocation.role == "CREATIVE").one()
    assert line.status == "MISSED_KYC" and _paid(db) == {}
    [m] = missed(db, nominee)
    assert (m.amount, m.kyc_status) == (Decimal("10.00"), "rejected")
    assert _balance(db, "2322") == Decimal("-1.00")                      # the sponsor's 1% stays held
    assert _balance(db, "4030") == Decimal("-10.00")
    _assert_all_journals_balance(db)


def test_member_summary_shows_missed_amounts_apart_from_available(world, client):
    db = world
    sponsor = _user(db, "a7-s@t.com")
    creative = unverified(db, "a7-c@t.com", sponsor=sponsor)
    _month(db, _entry(db, creative))
    _finalize(db)
    db.commit()
    s = client.get("/api/v1/advertising/earnings/summary", headers=auth(creative)).json()
    assert s["creative"]["missed"] == "20.00" and s["creative"]["available"] == "0.00"
    assert s["kyc_status"] == "none" and "not payable" in s["missed_note"]
    m = client.get("/api/v1/advertising/earnings/missed", headers=auth(creative)).json()
    assert m["total"] == "20.00" and m["items"][0]["category"] == "AD_CREATIVE_SHARE"
    other = client.get("/api/v1/advertising/earnings/missed", headers=auth(sponsor)).json()
    assert other["count"] == 0
    assert client.get("/api/v1/advertising/earnings/summary", headers=auth(sponsor)).json()["sponsor"]["available"] == "1.00"
