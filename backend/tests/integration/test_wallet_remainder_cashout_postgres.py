"""Partly spent commissions stay cashable (2026-11-04 fix), on REAL PostgreSQL with concurrent transactions.

Every scenario runs independent sessions (one connection each) released together, and then checks the one
invariant that matters, per member:

    wallet-used + reserved (open cashouts) + still available == the eligible commissions,   never more

and that the ledger balances. Existing rules apply unchanged: USD Cashout reserves the WHOLE available
balance (minimum $100); Crypto Cashout pays one commission per payout. Same safety rules as
test_payments_postgres.py: a DISPOSABLE local database per test, synthetic rows, a FAKE payout provider.
Opt-in: RUN_POSTGRES_TESTS=1."""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func

from app.core.config import settings
from app.models.accounting import JournalEntry, JournalLine
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus
from app.models.internal_wallet import InternalWalletPayment, InternalWalletPaymentLine
from app.models.user import User
from app.services import ad_campaigns as camp
from app.services import cashout_engine as engine_service
from app.services import cashout_service as cs
from app.services import internal_wallet as iw
from app.services.financial_balances import get_commission_balance
from tests.integration.test_payments_postgres import (  # noqa: F401
    _settings,
    engine_on,
    in_threads,
    pg,
    seed_ledger,
    slow_provider,
)
from tests.unit.test_dual_cashout import FEE_RULES, NOW, WALLET, FakeProvider, commission, configure, member

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]
D = Decimal
LIMITS = dict(max_single_payout_usd=D("1000.00"), max_daily_payout_usd=D("10000.00"), max_daily_payout_count=100)


@pytest.fixture
def world(pg, monkeypatch):
    """Ledger + products; the wallet switch and advertiser credit (1 unit = 1.00 USD) on for these tests."""
    engine, Session = pg
    monkeypatch.setattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", True)
    with Session() as db:
        seed_ledger(db)
        cfg = camp.get_settings(db)
        cfg.cpm_rate_usd, cfg.min_campaign_budget_usd, cfg.funding_enabled = D("0.50"), D("10.00"), True
        db.commit()
    return engine, Session


def setup_member(Session, method: str, *amounts: str, crypto: bool = False) -> tuple[int, list[int]]:
    with Session() as db:
        if crypto:
            configure(db, crypto_auto_payout_enabled=True, **FEE_RULES, **LIMITS)
        user = member(db, f"m{uuid.uuid4().hex[:6]}", method=method, wallet=None if method == "USD" else WALLET)
        ids = []
        for i, amount in enumerate(amounts):
            row = commission(db, user, amount, when=NOW - timedelta(days=10 - i))
            ids.append(row.id)
        return user.id, ids


def spend(Session, user_id: int, dollars: int, key: str | None = None):
    with Session() as db:
        try:
            payment, replayed = iw.pay(db, db.get(User, user_id), product_code=camp.AD_CREDIT_PRODUCT_CODE,
                                       quantity=dollars, idempotency_key=key or uuid.uuid4().hex)
            db.commit()
            return ("replayed" if replayed else "spent", payment.id)
        except iw.WalletError as exc:
            db.rollback()
            return ("refused", exc.code)


def usd(Session, user_id: int, key: str | None = None):
    with Session() as db:
        try:
            out = cs.request_usd_cashout(db, db.get(User, user_id), idempotency_key=key or uuid.uuid4().hex, now=NOW)
            return ("reserved", out.id, D(str(out.gross_amount)))
        except cs.CashoutError as exc:
            db.rollback()
            return ("refused", exc.code)


def facts(Session, user_id: int) -> dict:
    """Everything the invariant needs, read in one fresh session."""
    with Session() as db:
        rows = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == user_id).all()
        eligible = sum((D(str(r.commission_amount)) for r in rows if r.status != CommissionStatus.CANCELLED), D("0"))
        used = D(str(db.query(func.coalesce(func.sum(InternalWalletPaymentLine.amount), 0))
                     .join(AffiliateCommission, AffiliateCommission.id == InternalWalletPaymentLine.commission_id)
                     .filter(AffiliateCommission.user_id == user_id, InternalWalletPaymentLine.status == "ACTIVE")
                     .scalar()))
        open_cashouts = D(str(db.query(func.coalesce(func.sum(AffiliateCashoutRequest.gross_amount), 0))
                              .filter(AffiliateCashoutRequest.user_id == user_id,
                                      AffiliateCashoutRequest.status.in_(("requested", "processing", "unknown")))
                              .scalar()))
        paid_out = D(str(db.query(func.coalesce(func.sum(AffiliateCashoutRequest.gross_amount), 0))
                         .filter(AffiliateCashoutRequest.user_id == user_id,
                                 AffiliateCashoutRequest.status == "completed").scalar()))
        bal = get_commission_balance(db, user_id)
        d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                        func.coalesce(func.sum(JournalLine.credit_amount), 0)).one()
        out = dict(eligible=eligible, used=used, open=open_cashouts, paid_out=paid_out, available=bal.available,
                   reserved=bal.reserved, spendable=iw.spendable_balance(db, user_id), balanced=D(d) == D(c),
                   discrepancies=[x["kind"] if "kind" in x else x for x in engine_service.discrepancies(db, now=NOW)],
                   wallet_ok=iw.reconciliation(db)["ok"])
    # The invariant: each cent of a commission is in exactly one place, never two.
    assert out["used"] + out["open"] + out["paid_out"] + out["available"] == out["eligible"], out
    assert out["reserved"] == out["open"] and out["available"] == out["spendable"] and out["available"] >= 0, out
    assert out["balanced"] and out["wallet_ok"], out
    return out


# ---------------------------------------------------------------- Scenario 1: concurrent wallet spending

def test_scenario_1_two_simultaneous_purchases_of_70_from_100(world):
    _e, Session = world
    uid, _ = setup_member(Session, "USD", "100.00")
    results = in_threads(2, lambda i: spend(Session, uid, 70))
    assert sorted(r[0] for r in results) == ["refused", "spent"], results
    assert [r[1] for r in results if r[0] == "refused"] == ["INSUFFICIENT_BALANCE"]
    f = facts(Session, uid)
    assert (f["used"], f["available"], f["spendable"]) == (D("70.00"), D("30.00"), D("30.00"))


# ---------------------------------------------------------------- Scenario 2: concurrent cashouts

def test_scenario_2_two_simultaneous_usd_cashouts_reserve_once(world):
    _e, Session = world
    uid, _ = setup_member(Session, "USD", "250.00")
    spend(Session, uid, 50)                                                 # a partly spent row: 200 left
    results = in_threads(2, lambda i: usd(Session, uid))
    assert sorted(r[0] for r in results) == ["refused", "reserved"], results
    assert [r[1] for r in results if r[0] == "refused"] == ["CASHOUT_IN_PROGRESS"]
    assert [r[2] for r in results if r[0] == "reserved"] == [D("200.00")]   # the whole open amount, once
    f = facts(Session, uid)
    assert (f["open"], f["available"]) == (D("200.00"), D("0.00"))


def test_scenario_2b_concurrent_payout_workers_send_a_remainder_once(world, engine_on):
    _e, Session = world
    uid, _ = setup_member(Session, "CRYPTO", "100.00", crypto=True)
    spend(Session, uid, 20)                                                 # 80 left, payable on its own
    provider = slow_provider()

    def cycle(_i):
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=NOW)

    reports = in_threads(4, cycle)
    assert not any(isinstance(r, Exception) for r in reports), reports
    assert [c["amount"] for c in provider.created] == [D("80.00")]
    f = facts(Session, uid)
    assert (f["open"], f["available"], f["used"]) == (D("80.00"), D("0.00"), D("20.00"))


# ---------------------------------------------------------------- Scenario 3: wallet vs cashout

@pytest.mark.parametrize("attempt", range(3))
def test_scenario_3_wallet_purchase_and_cashout_race_for_the_same_money(world, attempt):
    _e, Session = world
    uid, _ = setup_member(Session, "USD", "160.00")
    results = in_threads(2, lambda i: spend(Session, uid, 60) if i == 0 else usd(Session, uid))
    wallet, cashout = results
    # Either the purchase won (100 left, cashed out whole) or the cashout won (160 reserved, purchase refused):
    # never both on the same money.
    assert (wallet[0], cashout[0]) in {("spent", "reserved"), ("refused", "reserved")}, results
    f = facts(Session, uid)
    if wallet[0] == "spent":
        assert (cashout[2], f["used"], f["open"], f["available"]) == (D("100.00"), D("60.00"), D("100.00"), 0)
    else:
        assert wallet[1] == "INSUFFICIENT_BALANCE"
        assert (cashout[2], f["used"], f["open"]) == (D("160.00"), D("0.00"), D("160.00"))


# ---------------------------------------------------------------- Scenario 4: mixed partial consumption

def test_scenario_4_wallet_30_and_a_cashout_reservation_of_50_leave_20(world, engine_on):
    _e, Session = world
    uid, (first,) = setup_member(Session, "CRYPTO", "50.00", crypto=True)
    provider = FakeProvider()
    with Session() as db:
        engine_service.run_cycle(db, provider=provider, now=NOW)            # 50 reserved and sent
        commission(db, db.get(User, uid), "50.00")                          # a second commission is earned
    assert spend(Session, uid, 30)[0] == "spent"                            # 30 of it spent
    f = facts(Session, uid)                                                 # eligible 100
    assert (f["used"], f["open"], f["available"], f["spendable"]) == (D("30.00"), D("50.00"), D("20.00"), D("20.00"))


@pytest.mark.parametrize("attempt", range(3))
def test_scenario_4b_a_purchase_racing_a_payout_cycle_never_uses_money_twice(world, engine_on, attempt):
    _e, Session = world
    uid, _ = setup_member(Session, "CRYPTO", "50.00", "50.00", crypto=True)
    provider = slow_provider()

    def work(i):
        if i == 0:
            return spend(Session, uid, 30)
        with Session() as db:
            return engine_service.run_cycle(db, provider=provider, now=NOW)

    results = in_threads(2, work)
    assert not isinstance(results[1], Exception), results
    f = facts(Session, uid)                                                 # the invariant holds either way
    sent = sum((c["amount"] for c in provider.created), D("0"))
    assert sent == f["open"] and sent + f["used"] + f["available"] == D("100.00"), (results, f)
    assert len({c["external_id"] for c in provider.created}) == len(provider.created)


# ---------------------------------------------------------------- Scenario 5: reservation release

def test_scenario_5_a_rejected_cashout_is_released_once_however_many_callbacks(world, engine_on):
    _e, Session = world
    uid, _ = setup_member(Session, "USD", "100.00")
    _r, cashout_id, gross = usd(Session, uid)
    with Session() as db:
        admin = member(db, f"boss{uuid.uuid4().hex[:4]}", admin=True).id

    def cancel(_i):
        with Session() as db:
            try:
                cs.cancel_request(db, db.get(AffiliateCashoutRequest, cashout_id), actor=db.get(User, admin),
                                  reason="rejected", now=NOW)
                return "released"
            except cs.CashoutError as exc:
                db.rollback()
                return exc.code

    results = in_threads(4, cancel)
    assert results.count("released") == 1 and set(results) <= {"released", "NOT_CANCELLABLE"}, results
    assert facts(Session, uid)["available"] == D("100.00")                  # back to 100, never above

    cuid, (crow,) = setup_member(Session, "CRYPTO", "100.00", crypto=True)
    spend(Session, cuid, 30)
    provider = FakeProvider(statuses={"batch-1": "REJECTED"})
    with Session() as db:
        engine_service.run_cycle(db, provider=provider, now=NOW)            # 70 reserved and sent

    def reconcile(_i):
        with Session() as db:
            return engine_service.reconcile_open(db, provider, now=NOW)

    assert not any(isinstance(r, Exception) for r in in_threads(4, reconcile))
    f = facts(Session, cuid)
    assert (f["open"], f["available"], f["used"]) == (D("0.00"), D("70.00"), D("30.00"))
    with Session() as db:
        assert db.get(AffiliateCommission, crow).payout_reference == iw.REMAINDER_MARK


# ---------------------------------------------------------------- Scenario 6: idempotent retry

def test_scenario_6_the_same_wallet_request_repeated_consumes_once(world):
    _e, Session = world
    uid, _ = setup_member(Session, "USD", "100.00")
    key = uuid.uuid4().hex
    results = in_threads(6, lambda i: spend(Session, uid, 40, key=key))
    assert [r[0] for r in results].count("spent") == 1 and len({r[1] for r in results}) == 1, results
    with Session() as db:
        assert db.query(InternalWalletPayment).filter_by(user_id=uid).count() == 1
    assert facts(Session, uid)["available"] == D("60.00")


# ---------------------------------------------------------------- Scenario 7: provider outcome uncertain

def test_scenario_7_an_uncertain_payout_keeps_the_remainder_reserved(world, engine_on):
    _e, Session = world
    uid, _ = setup_member(Session, "CRYPTO", "100.00", crypto=True)
    spend(Session, uid, 30)
    provider = FakeProvider()                                                # status stays PROCESSING
    for _ in range(3):
        with Session() as db:
            engine_service.run_cycle(db, provider=provider, now=NOW)
    f = facts(Session, uid)
    assert (len(provider.created), f["open"], f["available"], f["spendable"]) == (1, D("70.00"), 0, 0)
    assert spend(Session, uid, 1) == ("refused", "INSUFFICIENT_BALANCE")    # not released, not spendable


# ---------------------------------------------------------------- Scenario 8: transaction rollback

def test_scenario_8_a_failure_before_commit_leaves_no_phantom_consumption(world, engine_on, monkeypatch):
    _e, Session = world
    uid, (row_id,) = setup_member(Session, "CRYPTO", "100.00", crypto=True)
    fulfilled = iw._fulfilled
    monkeypatch.setattr(iw, "_fulfilled", lambda *_a, **_k: False)          # fails after lines and journal
    assert spend(Session, uid, 30) == ("refused", "FULFILMENT_FAILED")
    monkeypatch.setattr(iw, "_fulfilled", fulfilled)
    with Session() as db:
        assert db.query(InternalWalletPaymentLine).count() == 0 and db.query(JournalEntry).count() == 0
        assert db.get(AffiliateCommission, row_id).payout_reference is None
    spend(Session, uid, 30)
    provider = FakeProvider(statuses={"batch-1": "FINISHED"})
    with Session() as db:
        engine_service.run_cycle(db, provider=provider, now=NOW)            # 70 reserved and sent
    from app.services import accounting_service as acc

    def boom(*_a, **_k):
        raise RuntimeError("ledger down")

    post = acc.accounting_service.create_journal_entry
    monkeypatch.setattr(acc.accounting_service, "create_journal_entry", boom)
    with Session() as db:
        try:
            engine_service.reconcile_open(db, provider, now=NOW)            # the posting fails inside
        except Exception:  # noqa: BLE001 - either way nothing may be half-written
            db.rollback()
    f = facts(Session, uid)
    assert (f["open"], f["paid_out"]) == (D("70.00"), D("0.00"))            # still reserved, not half-paid
    with Session() as db:
        assert db.get(AffiliateCommission, row_id).status == CommissionStatus.APPROVED
        assert db.query(JournalEntry).filter(JournalEntry.description.like("Affiliate Cashout #%")).count() == 0
    monkeypatch.setattr(acc.accounting_service, "create_journal_entry", post)
    with Session() as db:
        engine_service.reconcile_open(db, provider, now=NOW)                # the retry settles it, once
    f = facts(Session, uid)
    assert (f["open"], f["paid_out"], f["available"]) == (D("0.00"), D("70.00"), D("0.00"))


# ---------------------------------------------------------------- duplicate payout callbacks

def test_duplicate_payout_confirmations_settle_a_remainder_once(world, engine_on):
    _e, Session = world
    uid, (row_id,) = setup_member(Session, "CRYPTO", "100.00", crypto=True)
    spend(Session, uid, 30)
    provider = FakeProvider(statuses={"batch-1": "FINISHED"})
    with Session() as db:
        engine_service.run_cycle(db, provider=provider, now=NOW)

    def reconcile(_i):
        with Session() as db:
            return engine_service.reconcile_open(db, provider, now=NOW)

    assert not any(isinstance(r, Exception) for r in in_threads(4, reconcile))
    f = facts(Session, uid)
    assert (f["paid_out"], f["open"], f["available"], f["used"]) == (D("70.00"), 0, 0, D("30.00"))
    with Session() as db:
        out = db.query(AffiliateCashoutRequest).filter_by(user_id=uid).one()
        entries = db.query(JournalEntry).filter_by(description=f"Affiliate Cashout #{out.id}").all()
        assert len(entries) == 1 and entries[0].total_debit == D("70.00")
        assert db.get(AffiliateCommission, row_id).status == CommissionStatus.PAID


def test_a_cashout_cancellation_racing_a_purchase_never_frees_money_twice(world):
    _e, Session = world
    uid, _ = setup_member(Session, "USD", "150.00")
    spend(Session, uid, 30)
    _r, cashout_id, _g = usd(Session, uid)
    with Session() as db:
        admin = member(db, f"boss{uuid.uuid4().hex[:4]}", admin=True).id

    def work(i):
        if i == 0:
            with Session() as db:
                cs.cancel_request(db, db.get(AffiliateCashoutRequest, cashout_id), actor=db.get(User, admin),
                                  reason="member asked", now=NOW)
                return ("released",)
        return spend(Session, uid, 100)

    results = in_threads(2, work)
    assert results[0] == ("released",) and results[1][0] in ("spent", "refused"), results
    f = facts(Session, uid)
    assert f["available"] == (D("20.00") if results[1][0] == "spent" else D("120.00")), (results, f)
