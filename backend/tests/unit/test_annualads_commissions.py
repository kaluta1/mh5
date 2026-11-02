"""Annual Ads direct-sponsor commission (Prompt 6): 20% / qualified 40% of the GROSS purchase, direct sponsor
only, KYC-approved sponsor only (otherwise a missed earning kept by MyHigh5), once per payment, signed
refunds reverse an unpaid commission and send anything else to finance review. SYNTHETIC; no provider call."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func

from app.core.config import settings
from app.models.accounting import AccountType, ChartOfAccounts, JournalLine
from app.models.advertising_v2 import AdvAnnualAdsEvent, AdvAnnualAdsPayment
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.business_model import AffiliateRateQualification
from app.models.missed_earning import MissedEarning
from app.services import annualads_commissions as ac
from tests.unit.test_new_business_model import _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit
D = Decimal
SECRET = "annual-secret"


@pytest.fixture
def annual(world, monkeypatch):
    monkeypatch.setattr(settings, "ANNUALADS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "ANNUALADS_TENANT_ID", "tenant-1")
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", True)
    for code, kind in (("1030", AccountType.ASSET), ("1210", AccountType.ASSET), ("2310", AccountType.LIABILITY),
                       ("4010", AccountType.REVENUE), ("7110", AccountType.EXPENSE)):
        if not world.query(ChartOfAccounts).filter_by(account_code=code).first():
            world.add(ChartOfAccounts(account_code=code, account_name=code, account_type=kind, is_active=True))
    world.commit()
    return world


def send(client, event, payment, *, ts=None):
    body = {"event": event, "payment": payment}
    raw = json.dumps(body, separators=(",", ":")).encode()
    ts = ts or str(int(time.time()))
    sig = hmac.new(SECRET.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return client.post("/api/v1/webhooks/sponsor-payment", content=raw,
                       headers={"content-type": "application/json", "x-webhook-timestamp": ts,
                                "x-webhook-signature": sig, "x-webhook-event": event})


def paid(client, buyer_id, gross="100.00", fee="30.00", tx=None):
    tx = tx or f"0x{uuid.uuid4().hex}"
    payment = {"tx_hash": tx, "amount": gross, "platform_fee": fee, "currency": "usdtbsc"}
    if buyer_id is not None:
        payment["buyer_external_id"] = str(buyer_id)
    return tx, send(client, "sponsor_payment_confirmed", payment)


def row(db, tx) -> AdvAnnualAdsPayment:
    db.expire_all()
    return db.query(AdvAnnualAdsPayment).filter_by(tx_hash=tx).one()


def account(db, code) -> Decimal:
    acc = db.query(ChartOfAccounts).filter_by(account_code=code).one()
    d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0)).filter(JournalLine.account_id == acc.id).one()
    return D(str(d)) - D(str(c))


def balanced(db) -> bool:
    d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0)).one()
    return D(str(d)) == D(str(c))


def test_standard_sponsor_earns_20_percent_of_gross_once(annual, client):
    db = annual
    sponsor = _user(db, "sp@t.com")
    buyer = _user(db, "buyer@t.com", sponsor=sponsor)
    db.commit()
    tx, r = paid(client, buyer.id)
    assert r.status_code == 200 and r.json()["sponsor_commission"] == "RECORDED", r.text
    again = send(client, "sponsor_payment_confirmed", {"tx_hash": tx, "amount": "100.00", "platform_fee": "30.00",
                                                       "currency": "usdtbsc", "buyer_external_id": str(buyer.id)})
    assert again.status_code == 200
    rows = db.query(AffiliateCommission).all()
    assert len(rows) == 1
    c = rows[0]
    assert (c.user_id, c.level, c.commission_rate, c.base_amount, c.commission_amount, c.status) == (
        sponsor.id, 1, D("0.2000"), D("100.00"), D("20.00"), CommissionStatus.APPROVED)   # gross, not the 70 net
    p = row(db, tx)
    assert (p.sponsor_commission_status, p.sponsor_rate, p.sponsor_commission_id) == ("RECORDED", D("0.2000"), c.id)
    assert p.sponsor_evidence["base"] == "GROSS" and p.sponsor_evidence["qualified"] is False
    assert account(db, "2001") == D("-20.00") and balanced(db)


def test_qualified_sponsor_earns_40_percent_of_gross(annual, client):
    db = annual
    sponsor = _user(db, "q@t.com")
    buyer = _user(db, "qb@t.com", sponsor=sponsor)
    db.add(AffiliateRateQualification(user_id=sponsor.id, qualified_at=datetime.utcnow(), qualifying_referral_count=10000, required_referral_count=10000, qualified_rate=D("0.40"),
                                      rule_version="DIRECT_40_AFTER_10K_KYC_IN_6M_V1",
                                      window_start=datetime(2026, 1, 1), window_deadline=datetime(2026, 7, 1)))
    db.commit()
    tx, r = paid(client, buyer.id, gross="250.00", fee="75.00")
    assert r.status_code == 200, r.text
    c = db.query(AffiliateCommission).one()
    assert (c.commission_rate, c.commission_amount, c.base_amount) == (D("0.4000"), D("100.00"), D("250.00"))
    assert row(db, tx).sponsor_evidence["qualified"] is True


def test_unverified_sponsor_gets_a_missed_earning_not_a_commission(annual, client):
    db = annual
    sponsor = _user(db, "nokyc@t.com", kyc=False)
    buyer = _user(db, "nb@t.com", sponsor=sponsor)
    db.commit()
    tx, r = paid(client, buyer.id)
    assert r.json()["sponsor_commission"] == "MISSED_KYC"
    assert db.query(AffiliateCommission).count() == 0
    missed = db.query(MissedEarning).one()
    assert (missed.user_id, missed.amount, missed.source_type) == (sponsor.id, D("20.00"), ac.SOURCE_TYPE)
    assert account(db, "4030") == D("-20.00") and account(db, "2001") == 0 and balanced(db)


def test_only_an_identified_buyer_with_a_direct_sponsor_earns_anything(annual, client):
    db = annual
    grand = _user(db, "grand@t.com")
    sponsor = _user(db, "mid@t.com", sponsor=grand)
    loner = _user(db, "loner@t.com")
    db.commit()
    tx1, _ = paid(client, None)                                       # no signed buyer identity
    tx2, _ = paid(client, loner.id)                                   # no sponsor
    tx3, _ = paid(client, sponsor.id)                                 # the buyer's sponsor only
    assert row(db, tx1).sponsor_commission_status == ac.BUYER_NOT_IDENTIFIED
    assert row(db, tx2).sponsor_commission_status == ac.NO_SPONSOR
    commissions = db.query(AffiliateCommission).all()
    assert [(c.user_id, c.level) for c in commissions] == [(grand.id, 1)]    # never level 2 or beyond


def test_full_refund_reverses_an_unpaid_commission_once(annual, client):
    db = annual
    sponsor = _user(db, "rs@t.com")
    buyer = _user(db, "rb@t.com", sponsor=sponsor)
    db.commit()
    tx, _ = paid(client, buyer.id)
    r = send(client, "sponsor_payment_refunded", {"tx_hash": tx, "amount": "100.00"})
    assert r.status_code == 200 and r.json()["status"] == "refund_reversed", r.text
    again = send(client, "sponsor_payment_refunded", {"tx_hash": tx, "amount": "100.00", "retry": 1})
    assert again.json()["status"] == "refund_reversed"                # idempotent per payment
    c = db.query(AffiliateCommission).one()
    db.refresh(c)
    assert c.status == CommissionStatus.CANCELLED and row(db, tx).sponsor_commission_status == ac.REVERSED
    assert account(db, "2001") == 0 and balanced(db)
    assert db.query(AdvAnnualAdsEvent).filter(AdvAnnualAdsEvent.outcome.like("REFUND_%")).count() == 2


def test_paid_commission_or_partial_refund_goes_to_finance_review(annual, client):
    db = annual
    sponsor = _user(db, "ps@t.com")
    b1, b2 = _user(db, "pb1@t.com", sponsor=sponsor), _user(db, "pb2@t.com", sponsor=sponsor)
    db.commit()
    tx1, _ = paid(client, b1.id)
    tx2, _ = paid(client, b2.id)
    c1 = db.query(AffiliateCommission).filter_by(source_id=row(db, tx1).id).one()
    c1.status, c1.paid_date = CommissionStatus.PAID, datetime.utcnow()
    db.commit()
    r1 = send(client, "sponsor_payment_refunded", {"tx_hash": tx1, "amount": "100.00"})
    r2 = send(client, "sponsor_payment_refunded", {"tx_hash": tx2, "amount": "40.00"})
    assert r1.json()["status"] == r2.json()["status"] == "refund_finance_review"
    db.expire_all()
    assert {c.status for c in db.query(AffiliateCommission)} == {CommissionStatus.PAID, CommissionStatus.APPROVED}
    rec = ac.reconciliation(db)
    assert [i["type"] for i in rec["issues"]].count("REFUND_FINANCE_REVIEW") == 2 and not rec["ok"]


def test_unknown_payment_refund_is_refused_and_signatures_are_checked(annual, client):
    r = send(annual and client, "sponsor_payment_refunded", {"tx_hash": "0xunknown", "amount": "10.00"})
    assert r.status_code == 404
    raw = json.dumps({"event": "sponsor_payment_confirmed", "payment": {"tx_hash": "0xa"}}).encode()
    bad = client.post("/api/v1/webhooks/sponsor-payment", content=raw,
                      headers={"x-webhook-timestamp": str(int(time.time())), "x-webhook-signature": "bad",
                               "x-webhook-event": "sponsor_payment_confirmed"})
    assert bad.status_code == 401


def test_disabled_integration_refuses_everything(annual, client, monkeypatch):
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", False)
    _tx, r = paid(client, None)
    assert r.status_code == 503 and annual.query(AdvAnnualAdsPayment).count() == 0


def test_reconciliation_is_clean_and_member_history_is_own_only(annual, client):
    from tests.unit.test_admin_security_hardening import bearer
    from tests.unit.test_super_admin import superadmin

    db = annual
    sponsor = _user(db, "hs@t.com")
    buyer = _user(db, "hb@t.com", sponsor=sponsor)
    other = _user(db, "ho@t.com")
    boss = superadmin(db, "boss-p6")
    db.commit()
    paid(client, buyer.id)
    assert ac.reconciliation(db)["ok"]
    mine = client.get("/api/v1/annual-ads/history", headers=bearer(sponsor)).json()
    assert mine["sponsor_commissions"][0]["rate_percent"].startswith("20") and mine["purchases"] == []
    assert client.get("/api/v1/annual-ads/history", headers=bearer(buyer)).json()["purchases"][0]["gross_amount"] == "100.00"
    assert client.get("/api/v1/annual-ads/history", headers=bearer(other)).json() == {"purchases": [], "sponsor_commissions": []}
    assert client.get("/api/v1/admin/reconciliation/annual-ads", headers=bearer(other)).status_code == 403
    assert client.get("/api/v1/admin/reconciliation/annual-ads", headers=bearer(boss)).json()["ok"]
    assert client.get("/api/v1/admin/reconciliation/dsm", headers=bearer(boss)).json()["source"] == "SOURCE_MISSING"
    assert client.post("/api/v1/admin/reconciliation/dsm/restorations", json={"user_id": buyer.id, "note": "evidence"},
                       headers=bearer(other)).status_code == 403
