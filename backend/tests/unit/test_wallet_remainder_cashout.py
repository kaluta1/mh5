"""Partly spent commissions stay cashable (2026-11-04 financial fix).

Before: a commission used in part by an internal wallet payment kept payout_reference 'iwp-rem' and every
cashout path took only rows with NO reference, so the unused part could be spent but never cashed out.
Now each row is worth its OPEN amount (amount - ACTIVE wallet lines, commission_usage) everywhere: wallet,
USD Cashout, Crypto Cashout (individual and combined payouts), balances, reconciliation and the ledger.
The same money is never available twice: a cashout reserves a row's whole open amount (its reference
becomes the cashout's intent, which the wallet never takes) and gives back exactly what it reserved.

Existing rules are unchanged and tested here only as they meet remainders: USD Cashout pays the WHOLE
available balance (minimum $100, fee 1% min $20); Crypto Cashout pays one commission per payout (small ones
combined); KYC; the wallet switch (default OFF); the automatic payout activation guard.
SYNTHETIC data and a FAKE payout provider only; real concurrency is in
tests/integration/test_wallet_remainder_cashout_postgres.py."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.internal_wallet import InternalWalletPayment, InternalWalletPaymentLine
from app.services import ad_campaigns as camp
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services import commission_usage as cu
from app.services import internal_wallet as iw
from app.services.financial_balances import get_commission_balance
from tests.unit.test_dual_cashout import (  # noqa: F401  (fixtures and helpers)
    NOW,
    FakeProvider,
    cashouts,
    commission,
    configure,
    engine_on,
    ledger,
    member,
    no_network,
    run,
)
from tests.unit.test_new_business_model import _assert_all_journals_balance, _balance, world  # noqa: F401

pytestmark = pytest.mark.unit
D = Decimal


@pytest.fixture
def shop(ledger, monkeypatch):
    """Internal wallet on and advertiser credit on sale (1 unit = 1.00 USD), for these tests only."""
    monkeypatch.setattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", True)
    cfg = camp.get_settings(ledger)
    cfg.cpm_rate_usd, cfg.min_campaign_budget_usd, cfg.funding_enabled = D("0.50"), D("10.00"), True
    ledger.commit()
    return ledger


def spend(db, user, dollars: int, *, key: str | None = None):
    payment, replayed = iw.pay(db, user, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=dollars,
                               idempotency_key=key or uuid.uuid4().hex)
    db.commit()
    return payment, replayed


def state(db, user):
    """(cashable available, reserved, spendable) - the three numbers a member sees."""
    db.expire_all()
    bal = get_commission_balance(db, user.id)
    return bal.available, bal.reserved, iw.spendable_balance(db, user.id)


def usd(db, user, key="usd-1"):
    return cs.request_usd_cashout(db, user, idempotency_key=key, now=NOW)


# ---------------------------------------------------------------- 1-4 the balance model

def test_1_a_fully_available_commission(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "100.00")
    assert state(db, m) == (D("100.00"), D("0.00"), D("100.00"))
    assert cs.available_rows(db, m.id) == [row] and cs.rows_total([row]) == D("100.00")
    db.rollback()


def test_2_a_partly_spent_commission_stays_spendable_and_cashable(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "100.00")
    spend(db, m, 30)
    db.refresh(row)
    assert (row.status, row.commission_amount, row.payout_reference) == (
        CommissionStatus.APPROVED, D("100.00"), cu.REMAINDER_MARK)          # the original row is never resized
    assert state(db, m) == (D("70.00"), D("0.00"), D("70.00"))              # the same 70, shown in both places
    bal = get_commission_balance(db, m.id)
    assert (bal.paid_lifetime, bal.earned_lifetime) == (D("30.00"), D("100.00"))
    assert cs.available_rows(db, m.id) == [row] and cs.rows_total([row]) == D("70.00")
    db.rollback()


def test_3_a_fully_spent_commission_is_closed(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "100.00")
    spend(db, m, 100)
    db.refresh(row)
    assert row.status == CommissionStatus.PAID and row.payout_reference.startswith(iw.PAID_PREFIX)
    assert state(db, m) == (D("0.00"), D("0.00"), D("0.00"))
    assert cs.available_rows(db, m.id) == []
    db.rollback()


def test_4_multiple_partial_purchases_and_a_later_purchase_after_a_cashout_attempt(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "100.00")
    spend(db, m, 20)
    spend(db, m, 10)
    used = sorted(a for (a,) in db.query(InternalWalletPaymentLine.amount)
                  .filter(InternalWalletPaymentLine.commission_id == row.id))
    assert used == [D("10.00"), D("20.00")] and state(db, m) == (D("70.00"), D("0.00"), D("70.00"))
    with pytest.raises(cs.CashoutError) as e:                              # 70 < the $100 USD minimum
        usd(db, m)
    assert e.value.code == "BELOW_MINIMUM"
    spend(db, m, 15)
    assert state(db, m) == (D("55.00"), D("0.00"), D("55.00"))
    db.rollback()


# ---------------------------------------------------------------- 5-8 spending and cashouts together

def test_5_partial_spending_then_usd_cashout_settles_exactly_the_rest(shop, monkeypatch):
    db = shop
    m, admin = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True)
    row = commission(db, m, "150.00")
    spend(db, m, 30)
    out = usd(db, m)
    assert (out.gross_amount, out.fee, out.net_amount) == (D("120.00"), D("20.00"), D("100.00"))
    assert state(db, m) == (D("0.00"), D("120.00"), D("0.00"))             # reserved: neither spendable nor cashable
    with pytest.raises(iw.WalletError) as e:
        spend(db, m, 1)
    assert e.value.code == "INSUFFICIENT_BALANCE"
    db.rollback()
    monkeypatch.setattr(settings, "USD_CASHOUT_SETTLEMENT_ENABLED", True)
    configure(db, usd_settlement_enabled=True, usd_settlement_account="1010")
    cs.settle_usd_cashout(db, out, admin=admin, reference="wire-1", now=NOW)
    db.refresh(row)
    assert row.status == CommissionStatus.PAID and row.payout_reference == "wire-1"
    journal = db.query(JournalEntry).filter_by(description=f"Affiliate Cashout #{out.id}").one()
    assert journal.total_debit == journal.total_credit == D("120.00")      # never the original 150
    assert _balance(db, "2001") == D("150.00")                              # 30 spent + 120 paid out = the commission
    assert _balance(db, "1010") == D("-100.00") and _balance(db, "4005") == D("-20.00")
    bal = get_commission_balance(db, m.id)
    assert (bal.available, bal.reserved, bal.paid_lifetime) == (D("0.00"), D("0.00"), D("150.00"))
    assert iw.spendable_balance(db, m.id) == D("0.00")
    _assert_all_journals_balance(db)


def test_6_an_individual_crypto_payout_then_wallet_spending_use_different_money(shop, engine_on):
    db = shop
    m = member(db, "m1", method="CRYPTO")
    a, b = commission(db, m, "5.00", when=NOW - timedelta(days=3)), commission(db, m, "10.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 2}                # one payout per commission (unchanged)
    assert state(db, m) == (D("0.00"), D("15.00"), D("0.00"))
    with pytest.raises(iw.WalletError):
        spend(db, m, 1)                                                     # everything is reserved
    db.rollback()
    provider.statuses["batch-2"] = "REJECTED"                              # b's payout definitively failed
    run(db, provider)
    assert state(db, m) == (D("10.00"), D("5.00"), D("10.00"))            # b is back: cashable AND spendable
    spend(db, m, 4)                                                         # b is now partly spent
    db.refresh(b)
    assert (b.status, b.payout_reference) == (CommissionStatus.APPROVED, cu.REMAINDER_MARK)
    assert state(db, m) == (D("6.00"), D("5.00"), D("6.00"))


def test_7_several_commissions_with_cents_fund_one_purchase(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    r1 = commission(db, m, "0.10", when=NOW - timedelta(days=5))
    r2 = commission(db, m, "0.05", when=NOW - timedelta(days=4))
    r3 = commission(db, m, "10.01", when=NOW - timedelta(days=3))
    spend(db, m, 3)
    for r in (r1, r2, r3):
        db.refresh(r)
    assert (r1.status, r2.status, r3.payout_reference) == (CommissionStatus.PAID, CommissionStatus.PAID,
                                                            cu.REMAINDER_MARK)
    assert cs.rows_total([r3]) == D("7.16")                                 # 10.01 - 2.85, exact cents
    assert state(db, m) == (D("7.16"), D("0.00"), D("7.16"))
    db.rollback()


def test_8_several_commissions_one_partly_spent_fund_one_cashout(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    a = commission(db, m, "100.00", when=NOW - timedelta(days=5))
    b = commission(db, m, "50.00", when=NOW - timedelta(days=4))
    spend(db, m, 30)
    out = usd(db, m)
    assert out.gross_amount == D("120.00")                                  # 70 left of a + 50 of b
    assert {r.id for r in cs.reserved_rows(db, out)} == {a.id, b.id}
    assert not engine.discrepancies(db, now=NOW)                            # reservation == cashout amount
    db.rollback()


# ---------------------------------------------------------------- 9-12 what never becomes available

def test_9_to_12_pending_held_cancelled_and_reversed_commissions_stay_out(shop):
    from app.services.financial_integrity import FinancialIntegrityError
    from app.services.new_model_revenue import reverse_direct_commissions

    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    commission(db, m, "50.00", status=CommissionStatus.PENDING)             # 9: pending
    held = commission(db, m, "60.00")
    held.business_model_version = None                                      # 10: historical, held for review
    commission(db, m, "70.00", status=CommissionStatus.CANCELLED)           # 11: cancelled / reversed
    row = commission(db, m, "100.00")
    row.source_type, row.source_id = "DEPOSIT", 4242
    db.commit()
    assert state(db, m) == (D("100.00"), D("0.00"), D("100.00"))
    spend(db, m, 30)
    assert state(db, m) == (D("70.00"), D("0.00"), D("70.00"))
    assert [r.id for r in cs.available_rows(db, m.id)] == [row.id]
    db.rollback()
    with pytest.raises(FinancialIntegrityError):                            # 12: a partly spent row is never
        reverse_direct_commissions(db, source_type="DEPOSIT", source_id=4242, reason="provider refund")
    db.rollback()                                                           #     cancelled silently


# ---------------------------------------------------------------- 13-17 unchanged rules

def test_13_the_usd_minimum_counts_the_open_amount_only(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "120.00")
    spend(db, m, 30)
    with pytest.raises(cs.CashoutError) as e:
        usd(db, m)                                                          # 90 < 100
    assert e.value.code == "BELOW_MINIMUM" and cashouts(db, m) == []
    db.refresh(row)
    assert row.payout_reference == cu.REMAINDER_MARK and state(db, m) == (D("90.00"), D("0.00"), D("90.00"))
    with pytest.raises(cs.CashoutError) as e:
        cs.request_usd_cashout(db, m, idempotency_key="amt", amount=D("120.00"), now=NOW)
    assert e.value.code in ("BELOW_MINIMUM", "AMOUNT_MISMATCH")
    db.rollback()


def test_14_the_wallet_switch_still_blocks_spending_but_a_remainder_stays_cashable(shop, monkeypatch):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    commission(db, m, "150.00")
    spend(db, m, 30)
    monkeypatch.setattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", False)
    with pytest.raises(iw.WalletError) as e:
        spend(db, m, 1)
    assert e.value.code == "WALLET_PAYMENTS_DISABLED"
    db.rollback()
    assert usd(db, m).gross_amount == D("120.00")                           # cashouts never depended on the switch


def test_15_no_automatic_payout_of_a_remainder_without_the_activation_guard(shop, monkeypatch):
    db = shop
    m = member(db, "m1", method="CRYPTO")
    commission(db, m, "10.00")
    spend(db, m, 3)
    monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", False)
    provider = FakeProvider()
    run(db, provider)
    assert provider.created == [] and cashouts(db, m) == [] and not engine.engine_enabled(db)
    assert state(db, m) == (D("7.00"), D("0.00"), D("7.00"))


def test_16_repeated_requests_with_the_same_key_take_the_money_once(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    commission(db, m, "200.00")
    p1, r1 = spend(db, m, 40, key="same-wallet-key")
    p2, r2 = spend(db, m, 40, key="same-wallet-key")
    assert (r1, r2, p1.id) == (False, True, p2.id) and state(db, m) == (D("160.00"), D("0.00"), D("160.00"))
    c1, c2 = usd(db, m, key="same-cashout-key"), usd(db, m, key="same-cashout-key")
    assert c1.id == c2.id and len(cashouts(db, m)) == 1
    assert state(db, m) == (D("0.00"), D("160.00"), D("0.00"))


def test_17_a_payment_that_fails_after_reserving_leaves_nothing(shop, monkeypatch):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "100.00")
    monkeypatch.setattr(iw, "_fulfilled", lambda *_a, **_k: False)
    with pytest.raises(iw.WalletError) as e:
        iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=30, idempotency_key=uuid.uuid4().hex)
    db.rollback()
    assert e.value.code == "FULFILMENT_FAILED"
    db.refresh(row)
    assert row.payout_reference is None and db.query(InternalWalletPaymentLine).count() == 0
    assert db.query(InternalWalletPayment).count() == 0 and state(db, m) == (D("100.00"), D("0.00"), D("100.00"))
    _assert_all_journals_balance(db)


# ---------------------------------------------------------------- 18-21 releases, settlements, refunds

def test_18_a_cancelled_or_rejected_cashout_gives_back_the_remainder_exactly_once(shop, engine_on):
    db = shop
    m, admin = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True)
    row = commission(db, m, "150.00")
    spend(db, m, 30)
    out = usd(db, m)
    cs.cancel_request(db, out, actor=admin, reason="member asked", now=NOW)
    db.refresh(row)
    assert row.payout_reference == cu.REMAINDER_MARK                       # back to "partly spent", not "unused"
    assert state(db, m) == (D("120.00"), D("0.00"), D("120.00"))
    with pytest.raises(cs.CashoutError):
        cs.cancel_request(db, cashouts(db, m)[0], actor=admin, reason="again", now=NOW)
    assert state(db, m) == (D("120.00"), D("0.00"), D("120.00"))           # never above what is left

    c = member(db, "m2", method="CRYPTO")
    crow = commission(db, c, "10.00")
    spend(db, c, 3)
    provider = FakeProvider(statuses={"batch-1": "REJECTED"})
    run(db, provider)
    assert [p["amount"] for p in provider.created] == [D("7.00")]
    run(db, provider)
    run(db, provider)                                                       # repeated final status: no effect
    db.refresh(crow)
    assert crow.payout_reference == cu.REMAINDER_MARK and state(db, c) == (D("7.00"), D("0.00"), D("7.00"))


def test_19_a_confirmed_crypto_payout_of_a_remainder_is_settled_once_at_the_open_amount(shop, engine_on):
    db = shop
    m = member(db, "m1", method="CRYPTO")
    row = commission(db, m, "10.01")
    spend(db, m, 3)
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 1}
    assert [p["amount"] for p in provider.created] == [D("7.01")]
    assert state(db, m) == (D("0.00"), D("7.01"), D("0.00"))
    provider.statuses["batch-1"] = "FINISHED"
    run(db, provider)
    run(db, provider)
    out = cashouts(db, m)[0]
    db.refresh(row)
    assert (out.status, out.gross_amount, row.status) == ("completed", D("7.01"), CommissionStatus.PAID)
    journal = db.query(JournalEntry).filter_by(description=f"Affiliate Cashout #{out.id}").one()
    assert journal.total_debit == D("7.01")
    assert _balance(db, "2001") == D("10.01") and _balance(db, "1001") == D("-7.01")
    bal = get_commission_balance(db, m.id)
    assert (bal.available, bal.reserved, bal.paid_lifetime) == (D("0.00"), D("0.00"), D("10.01"))
    recon = engine.commission_payout_reconciliation(db)                    # 7.01 paid == 10.01 - 3.00 spent
    assert not [p for p in recon["problems"] if "AMOUNT_MISMATCH" in p["problems"]]
    assert not engine.discrepancies(db, now=NOW)
    _assert_all_journals_balance(db)
    assert provider.created == provider.created[:1]                          # paid once


def test_20_21_a_refund_restores_the_rows_once_and_never_money_that_left(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "150.00")
    payment, _ = spend(db, m, 30)
    assert iw._restore_rows(db, payment) == 1                               # refund core: lines reversed
    db.commit()
    db.refresh(row)
    assert row.payout_reference is None and state(db, m) == (D("150.00"), D("0.00"), D("150.00"))
    assert iw._restore_rows(db, payment) == 0                               # a second refund restores nothing
    db.commit()
    assert state(db, m) == (D("150.00"), D("0.00"), D("150.00"))

    p2, _ = spend(db, m, 30)
    usd(db, m)                                                              # the remainder is now reserved
    with pytest.raises(iw.WalletError) as e:
        iw._restore_rows(db, p2)
    assert e.value.code == "REFUND_REVIEW_REQUIRED"                         # manual finance review, nothing written
    db.rollback()


# ---------------------------------------------------------------- 22-25 ledger, KYC, ownership, precision

def test_22_the_ledger_balances_and_reconciliations_agree_after_mixed_use(shop, engine_on):
    db = shop
    m = member(db, "m1", method="CRYPTO")
    commission(db, m, "10.00")
    commission(db, m, "4.00")
    spend(db, m, 12)                                                        # 10 used up, 2 of 4 used
    provider = FakeProvider()
    run(db, provider)
    assert [p["amount"] for p in provider.created] == [D("2.00")]
    report = engine.reconciliation_report(db)
    assert report["owed"]["reserved"] == 2.0 and report["owed"]["available"] == 0.0
    provider.statuses["batch-1"] = "FINISHED"
    run(db, provider)
    assert iw.reconciliation(db)["ok"] and not engine.discrepancies(db, now=NOW)
    assert _balance(db, "2001") == D("14.00") and _balance(db, "1050") == D("0")
    _assert_all_journals_balance(db)


def test_23_kyc_is_still_required_for_a_remainder_cashout(shop):
    from app.models.kyc import KYCVerification

    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    commission(db, m, "150.00")
    spend(db, m, 30)
    db.query(KYCVerification).filter(KYCVerification.user_id == m.id).delete()
    db.commit()
    with pytest.raises(cs.CashoutError) as e:
        usd(db, m)
    assert e.value.code == "KYC_NOT_APPROVED" and cashouts(db, m) == []
    with pytest.raises(iw.WalletError) as w:
        spend(db, m, 1)
    assert w.value.code == "KYC_REQUIRED"
    db.rollback()


def test_24_one_members_remainder_is_never_another_members_money(shop):
    db = shop
    a, b = member(db, "ma", method="USD", wallet=None), member(db, "mb", method="USD", wallet=None)
    ra = commission(db, a, "150.00")
    commission(db, b, "100.00")
    spend(db, a, 30)
    assert state(db, b) == (D("100.00"), D("0.00"), D("100.00"))
    out = usd(db, b, key="b-1")
    assert out.gross_amount == D("100.00") and ra.id not in {r.id for r in cs.reserved_rows(db, out)}
    assert state(db, a) == (D("120.00"), D("0.00"), D("120.00"))


def test_25_exact_cents_never_float(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "100.99")
    spend(db, m, 1)
    left = cu.open_amount(row, db)
    assert isinstance(left, Decimal) and left == D("99.99") and str(left) == "99.99"
    assert cu.open_amounts([], db) == {}
    db.rollback()


def test_an_overused_row_is_refused_never_shown_negative(shop):
    from app.services.financial_integrity import FinancialIntegrityError

    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    row = commission(db, m, "10.00")
    p, _ = spend(db, m, 4)
    db.query(InternalWalletPaymentLine).filter_by(payment_id=p.id).update({"amount": D("12.00")})
    with pytest.raises(FinancialIntegrityError):
        cu.open_amount(row, db)
    db.rollback()


def test_member_wallet_summary_no_longer_calls_a_remainder_wallet_only(shop):
    db = shop
    m = member(db, "m1", method="USD", wallet=None)
    commission(db, m, "150.00")
    spend(db, m, 30)
    summary = iw.member_summary(db, m)
    assert (summary["spendable"], summary["partly_spent_remainder"], summary["wallet_only_remainder"]) == (
        "120.00", "120.00", "0.00")
    cashout = cs.summary(db, m, now=NOW)
    assert (cashout["balances"]["available"], cashout["payable_amount"]) == (120.0, 120.0)
