"""Multi-Unit Referral Pool, P5: revenue, commission and refunds per unit on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC; no provider is called,
no payout is sent.

A confirmed pool payment is held in 2100 once (existing receipt); each ACTIVE unit then moves
$100 from 2100 to revenue 4008 and accrues one $20 direct commission, once. A refund reverses
exactly the refunded units. Every scenario ends with the purchase reconciled against the ledger.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func

from app.models.accounting import JournalEntry, JournalLine
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus
from app.models.business_model import (
    ReferralPoolConfig, ReferralPoolPurchase, ReferralPoolUnit, RevenueRecognition,
)
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import leaders_service, payment_config
from app.services import referral_pool_accounting as accounting
from app.services import referral_pool_units as units
from app.services.financial_integrity import FinancialIntegrityError
from app.services.financial_reversal import reverse_provider_refund
from app.services.new_model_payments import process_new_model_deposit
from tests.integration.test_payments_postgres import in_threads, pg, seed_ledger  # noqa: F401
from tests.integration.test_referral_pool_units_postgres import (  # noqa: F401
    NOW, activate, buy, confirm, deposit, member, set_kyc, unit_id_list, world,
)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))
D = Decimal


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sponsored_buyer(Session, *, sponsor: int | None = None) -> tuple:
    """(buyer, sponsor): a KYC-approved buyer whose direct sponsor is a KYC-approved member."""
    sponsor = sponsor or member(Session)
    buyer = member(Session)
    with Session() as db:
        u = db.get(User, buyer)
        u.sponsor_id, u.sponsor_source = sponsor, "PERSONAL_REFERRAL"
        db.commit()
    return buyer, sponsor


def paid_purchase(Session, buyer: int, n: int) -> tuple:
    purchase_id, deposit_id = buy(Session, buyer, n)
    confirm(Session, deposit_id)
    activate(Session, deposit_id)
    return purchase_id, deposit_id


def ledger(Session, purchase_id: int) -> dict:
    with Session() as db:
        return accounting.purchase_ledger(db, purchase_id)


def reconciled(Session, purchase_id: int) -> list:
    with Session() as db:
        return accounting.reconcile_purchase(db, purchase_id)


def commissions(Session, purchase_id: int) -> list:
    with Session() as db:
        ids = [u.id for u in db.query(ReferralPoolUnit).filter_by(purchase_id=purchase_id)]
        return [(c.user_id, c.commission_amount, c.status, c.level, c.deposit_id) for c in db.query(AffiliateCommission)
                .filter(AffiliateCommission.source_type == accounting.SOURCE_UNIT, AffiliateCommission.source_id.in_(ids))
                .order_by(AffiliateCommission.source_id)]


@pytest.fixture
def finance_admin(world, monkeypatch):
    """An administrator allowed to record verified refunds (permission and password checks are
    the existing payment_config ones; replaced here by allow-all, a separate test covers refusal)."""
    _engine, Session = world
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: True)
    monkeypatch.setattr(payment_config, "require_reauth", lambda actor, password: None)
    return member(Session)


_SECOND_ADMIN: dict = {}


def record_refund(Session, admin_id: int, purchase_id: int, quantity: int, reference: str, amount=None):
    """A manual refund as P7 requires: proposed by `admin_id`, approved by a different administrator.
    Returns the refunded unit indexes, or the refusal code."""
    approver = _SECOND_ADMIN.setdefault(id(Session), member(Session))
    with Session() as db:
        try:
            record = units.propose_manual_refund(
                db, db.get(User, admin_id), purchase_id=purchase_id, quantity=quantity,
                amount=amount if amount is not None else D("100.00") * quantity, provider_reference=reference,
                evidence_note="Refund seen in the provider dashboard (synthetic test)", password="x")
            record_id = record.id
        except units.UnitsError as exc:
            db.rollback()
            return exc.code
    with Session() as db:
        try:
            record = units.decide_manual_refund(db, db.get(User, approver), record_id, approve=True,
                                                note="Checked by a second administrator", password="x", now=NOW)
            ids = [int(i) for i in (record.executed_unit_ids or "").split(",") if i]
            return sorted(db.get(ReferralPoolUnit, i).unit_index for i in ids)
        except units.UnitsError as exc:
            db.rollback()
            return exc.code


def provider_full_refund(Session, deposit_id: int, amount) -> str:
    with Session() as db:
        try:
            reverse_provider_refund(db, db.get(Deposit, deposit_id), {"refund_amount": str(amount)})
            return "ok"
        except FinancialIntegrityError as exc:
            db.rollback()
            return f"refused:{exc}"


def ledger_balanced(Session) -> bool:
    with Session() as db:
        debit, credit = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                                 func.coalesce(func.sum(JournalLine.credit_amount), 0)).one()
        return D(debit) == D(credit)


def leaders_revenue(Session) -> Decimal:
    now = datetime.utcnow()
    with Session() as db:
        return D(leaders_service.eligible_company_revenue(db, now.year, now.month))


# ---------------------------------------------------------------------------
# 1. Revenue and commission
# ---------------------------------------------------------------------------

def test_one_unit_is_100_revenue_from_the_2100_hold(world):
    _engine, Session = world
    buyer = member(Session)
    p, _d = paid_purchase(Session, buyer, 1)
    assert ledger(Session, p) == {"1001": D("100.00"), "4008": D("-100.00")}            # 2100 back to zero
    with Session() as db:
        unit = db.query(ReferralPoolUnit).filter_by(purchase_id=p).one()
        rec = db.get(RevenueRecognition, unit.revenue_recognition_id)
        assert (rec.source_type, rec.source_id, rec.website_revenue_amount, rec.leaders_revenue_eligible) == \
            (accounting.SOURCE_UNIT, unit.id, D("100.00"), True)
    assert reconciled(Session, p) == [] and ledger_balanced(Session)


def test_three_units_are_300_revenue_and_three_20_commissions_to_the_direct_sponsor(world):
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    p, _d = paid_purchase(Session, buyer, 3)
    assert ledger(Session, p) == {"1001": D("300.00"), "4008": D("-300.00"), "5001": D("60.00"), "2001": D("-60.00")}
    assert commissions(Session, p) == [(sponsor, D("20.00"), CommissionStatus.APPROVED, 1, None)] * 3
    with Session() as db:
        assert all(u.direct_commission_id for u in db.query(ReferralPoolUnit).filter_by(purchase_id=p))
    assert reconciled(Session, p) == [] and ledger_balanced(Session)


def test_no_direct_sponsor_or_an_ineligible_one_means_no_commission_and_no_replacement(world):
    _engine, Session = world
    lone = member(Session)
    p1, _ = paid_purchase(Session, lone, 2)
    buyer, sponsor = sponsored_buyer(Session)
    with Session() as db:
        db.get(User, sponsor).is_deleted = True
        db.commit()
    p2, _ = paid_purchase(Session, buyer, 2)
    assert commissions(Session, p1) == [] and commissions(Session, p2) == []
    with Session() as db:
        assert db.query(AffiliateCommission).filter_by(source_type=accounting.SOURCE_UNIT).count() == 0
    assert ledger(Session, p2) == {"1001": D("200.00"), "4008": D("-200.00")}
    assert reconciled(Session, p1) == [] == reconciled(Session, p2)


def test_only_the_direct_sponsor_earns_no_ten_level_distribution(world):
    _engine, Session = world
    grandparent = member(Session)
    parent, _ = sponsored_buyer(Session, sponsor=grandparent)
    buyer, _ = sponsored_buyer(Session, sponsor=parent)
    p, _d = paid_purchase(Session, buyer, 2)
    assert {c[0] for c in commissions(Session, p)} == {parent}
    with Session() as db:
        assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id == grandparent).count() == 0
        assert {c.level for c in db.query(AffiliateCommission)} == {1}


@pytest.mark.parametrize("source", ["REFERRAL_POOL", "DSM_IMPORT"])
def test_an_assigned_sponsor_earns_the_direct_commission_of_later_purchases_only(world, source):
    """Owner rule 2026-10-26: a pool or DSM sponsor is the direct sponsor the existing engine
    pays (users.sponsor_id), once per unit, from future purchases; being assigned earns nothing."""
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    with Session() as db:
        db.get(User, buyer).sponsor_source = source
        db.commit()
        assert db.query(AffiliateCommission).count() == 0                     # the assignment itself: nothing
    p, _d = paid_purchase(Session, buyer, 2)
    assert commissions(Session, p) == [(sponsor, D("20.00"), CommissionStatus.APPROVED, 1, None)] * 2
    assert reconciled(Session, p) == [] and ledger_balanced(Session)


def test_duplicate_and_concurrent_payment_callbacks_post_once(world):
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    p, d = buy(Session, buyer, 3)
    confirm(Session, d)
    results = in_threads(8, lambda _i: activate(Session, d))
    assert results == [units.P_PAID] * 8, results
    activate(Session, d)                                                               # and once more later
    with Session() as db:
        assert db.query(JournalEntry).filter_by(source_type="DEPOSIT", source_id=d).count() == 1
        ids = unit_id_list(Session, p)
        assert db.query(RevenueRecognition).filter(RevenueRecognition.source_type == accounting.SOURCE_UNIT,
                                                   RevenueRecognition.source_id.in_(ids)).count() == 3
    assert len(commissions(Session, p)) == 3
    assert reconciled(Session, p) == [] and ledger_balanced(Session)


def test_a_held_for_review_payment_earns_nothing_and_its_cash_stays_in_2100(world):
    _engine, Session = world
    buyer, _ = sponsored_buyer(Session)
    p, d = buy(Session, buyer, 2)
    with Session() as db:
        dep = db.get(Deposit, d)
        dep.amount, dep.status, dep.validated_at = D("100.00"), DepositStatus.VALIDATED, NOW      # underpaid
        db.commit()
    assert activate(Session, d) == units.P_HELD
    assert ledger(Session, p) == {"1001": D("100.00"), "2100": D("-100.00")}
    assert commissions(Session, p) == [] and reconciled(Session, p) == []


def test_a_unit_suspended_at_payment_earns_when_its_holder_becomes_eligible(world):
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    p, d = buy(Session, buyer, 2)
    set_kyc(Session, buyer, approved=False)
    confirm(Session, d)
    activate(Session, d)
    assert ledger(Session, p) == {"1001": D("200.00"), "2100": D("-200.00")}               # paid, not yet earned
    set_kyc(Session, buyer, approved=True)
    with Session() as db:
        units.sync_member_eligibility(db, buyer, now=NOW)
        db.commit()
    assert ledger(Session, p) == {"1001": D("200.00"), "4008": D("-200.00"), "5001": D("40.00"), "2001": D("-40.00")}
    assert reconciled(Session, p) == []


# ---------------------------------------------------------------------------
# 2. Refunds
# ---------------------------------------------------------------------------

def test_a_verified_partial_refund_reverses_exactly_one_unit(world, finance_admin):
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    p, _d = paid_purchase(Session, buyer, 3)
    assert record_refund(Session, finance_admin, p, 1, "prov-ref-1") == [3]
    assert ledger(Session, p) == {"1001": D("200.00"), "4008": D("-200.00"), "5001": D("40.00"), "2001": D("-40.00")}
    assert [c[2] for c in commissions(Session, p)] == [CommissionStatus.APPROVED, CommissionStatus.APPROVED,
                                                       CommissionStatus.CANCELLED]
    with Session() as db:
        third = db.query(ReferralPoolUnit).filter_by(purchase_id=p, unit_index=3).one()
        assert third.status == "REFUNDED" and third.refund_journal_entry_id and third.refund_reference == "prov-ref-1"
        rec = db.get(RevenueRecognition, third.revenue_recognition_id)
        assert db.query(RevenueRecognition).filter_by(reverses_id=rec.id).one().website_revenue_amount == D("-100.00")
    assert reconciled(Session, p) == [] and ledger_balanced(Session)

    # The remaining two, later: everything back to zero.
    assert record_refund(Session, finance_admin, p, 2, "prov-ref-2") == [1, 2]
    assert ledger(Session, p) == {}
    with Session() as db:
        assert (db.get(ReferralPoolPurchase, p).status, db.get(ReferralPoolPurchase, p).refunded_quantity) == ("REFUNDED", 3)
    assert reconciled(Session, p) == [] and ledger_balanced(Session)


def test_a_duplicate_refund_record_changes_nothing(world, finance_admin):
    from app.models.accounting import AuditTrail

    _engine, Session = world
    buyer, _ = sponsored_buyer(Session)
    p, _d = paid_purchase(Session, buyer, 3)
    assert record_refund(Session, finance_admin, p, 1, "dup-ref") == [3]
    before = ledger(Session, p)
    assert record_refund(Session, finance_admin, p, 1, "dup-ref") == "REFERENCE_REUSED"   # the same refund again
    assert record_refund(Session, finance_admin, p, 2, "dup-ref") == "REFERENCE_REUSED"
    assert ledger(Session, p) == before
    with Session() as db:
        assert db.query(AuditTrail).filter_by(action=units.AUDIT_REFUND_DECIDED).count() == 1


def test_refund_records_are_refused_without_permission_or_with_a_wrong_amount(world, finance_admin, monkeypatch):
    _engine, Session = world
    buyer, _ = sponsored_buyer(Session)
    p, _d = paid_purchase(Session, buyer, 3)
    before = ledger(Session, p)
    assert record_refund(Session, finance_admin, p, 1, "r", amount=D("50.00")) == "AMOUNT_MISMATCH"
    assert record_refund(Session, finance_admin, p, 4, "r") == "INVALID_QUANTITY"
    assert record_refund(Session, finance_admin, p, 1, "  ") == "REFERENCE_REQUIRED"
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: False)
    assert record_refund(Session, finance_admin, p, 1, "r") == "FORBIDDEN"
    assert ledger(Session, p) == before


def test_a_full_provider_refund_reverses_every_unit_once(world):
    _engine, Session = world
    buyer, _ = sponsored_buyer(Session)
    p, d = paid_purchase(Session, buyer, 3)
    assert provider_full_refund(Session, d, "300.00") == "ok"
    assert provider_full_refund(Session, d, "300.00") == "ok"                            # replayed callback
    assert ledger(Session, p) == {}
    assert [c[2] for c in commissions(Session, p)] == [CommissionStatus.CANCELLED] * 3
    with Session() as db:
        assert {u.status for u in db.query(ReferralPoolUnit).filter_by(purchase_id=p)} == {"REFUNDED"}
        assert all(u.refund_journal_entry_id for u in db.query(ReferralPoolUnit).filter_by(purchase_id=p))
    assert reconciled(Session, p) == [] and ledger_balanced(Session)


def test_a_refused_provider_refund_reverses_nothing(world):
    """A provider event that is not a verified full refund (here: a partial amount) is refused by
    the existing path; the units keep their revenue and commission."""
    _engine, Session = world
    buyer, _ = sponsored_buyer(Session)
    p, d = paid_purchase(Session, buyer, 3)
    before = ledger(Session, p)
    assert provider_full_refund(Session, d, "100.00").startswith("refused:")
    assert ledger(Session, p) == before
    with Session() as db:
        assert {u.status for u in db.query(ReferralPoolUnit).filter_by(purchase_id=p)} == {"ACTIVE"}


def test_a_paid_commission_becomes_a_receivable_and_a_payout_in_flight_blocks_the_refund(world, finance_admin):
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    p, _d = paid_purchase(Session, buyer, 3)
    with Session() as db:
        ids = unit_id_list(Session, p)
        paid = db.query(AffiliateCommission).filter_by(source_type=accounting.SOURCE_UNIT, source_id=ids[2]).one()
        paid.status = CommissionStatus.PAID                                # paid out before the refund
        flight = db.query(AffiliateCommission).filter_by(source_type=accounting.SOURCE_UNIT, source_id=ids[1]).one()
        flight.payout_reference = "intent:synthetic"                       # a payout of unit 2 is in flight
        db.commit()
    assert record_refund(Session, finance_admin, p, 1, "after-payout") == [3]
    ledger_now = ledger(Session, p)
    assert ledger_now["1200"] == D("20.00")                                 # receivable from the sponsor, recorded
    assert ledger_now["1001"] == D("200.00") and ledger_now["4008"] == D("-200.00")
    with Session() as db:
        assert db.query(AffiliateCashoutRequest).count() == 0               # nothing debited or sent
    with pytest.raises(FinancialIntegrityError, match="payout intent"):
        record_refund(Session, finance_admin, p, 1, "during-payout")
    with Session() as db:
        assert db.query(ReferralPoolUnit).filter_by(purchase_id=p, unit_index=2).one().status == "ACTIVE"
    assert ledger(Session, p) == ledger_now


# ---------------------------------------------------------------------------
# 3. Leaders, history, payouts, switches
# ---------------------------------------------------------------------------

def test_leaders_counts_each_unit_once_and_refunds_take_it_back(world, finance_admin):
    _engine, Session = world
    start = leaders_revenue(Session)
    buyer, _ = sponsored_buyer(Session)
    p, d = paid_purchase(Session, buyer, 3)
    activate(Session, d)                                                    # repeated event
    assert leaders_revenue(Session) - start == D("300.00")
    record_refund(Session, finance_admin, p, 1, "lead-ref")
    assert record_refund(Session, finance_admin, p, 1, "lead-ref") == "REFERENCE_REUSED"   # repeated record
    assert leaders_revenue(Session) - start == D("200.00")


def test_historical_2100_holds_are_left_exactly_as_they_are(world):
    """A pool payment of the retired model (no purchase record) keeps its 2100 hold; P5 never
    converts it, and new purchases never touch it."""
    _engine, Session = world
    legacy_buyer = member(Session)
    legacy = deposit(Session, legacy_buyer, 1)
    with Session() as db:
        dep = db.get(Deposit, legacy)
        dep.status, dep.validated_at = DepositStatus.VALIDATED, NOW
        db.commit()
        process_new_model_deposit(db, db.get(Deposit, legacy))
        db.commit()
    def hold(db):
        entry = accounting.receipt_for(db, db.get(Deposit, legacy))
        return [(l.debit_amount, l.credit_amount) for l in db.query(JournalLine).filter_by(entry_id=entry.id)]
    with Session() as db:
        before = hold(db)
    buyer, _ = sponsored_buyer(Session)
    paid_purchase(Session, buyer, 2)
    with Session() as db:
        assert hold(db) == before
        assert db.query(RevenueRecognition).filter(RevenueRecognition.source_type == "DEPOSIT",
                                                   RevenueRecognition.source_id == legacy).count() == 0
        assert db.query(JournalEntry).filter_by(source_type="DEPOSIT", source_id=legacy).count() == 1


def test_no_payout_is_created_by_pool_accounting(world):
    _engine, Session = world
    buyer, _ = sponsored_buyer(Session)
    paid_purchase(Session, buyer, 3)
    with Session() as db:
        assert db.query(AffiliateCashoutRequest).count() == 0


def test_the_switches_are_off_by_default(pg):
    _engine, Session = pg
    with Session() as db:
        seed_ledger(db)
        cfg = db.query(ReferralPoolConfig).one()
        assert (cfg.multiunit_sales_enabled, cfg.allocation_enabled) == (False, False)
        product = db.query(ProductType).filter(ProductType.code == units.PRODUCT_CODE).one()
        assert product.price == D("100.00")


@pytest.mark.parametrize("round_", range(ROUNDS))
def test_refunds_and_revenue_posting_at_once_stay_reconciled(world, finance_admin, round_):
    _engine, Session = world
    buyer, _ = sponsored_buyer(Session)
    first, _ = paid_purchase(Session, buyer, 3)
    second, d2 = buy(Session, buyer, 2)
    confirm(Session, d2)
    third, d3 = buy(Session, buyer, 2)
    set_kyc(Session, buyer, approved=False)
    confirm(Session, d3)
    activate(Session, d3)                                                   # suspended: not earned yet
    set_kyc(Session, buyer, approved=True)

    def act(i):
        kind = (i + round_) % 4
        try:
            if kind == 0:
                return record_refund(Session, finance_admin, first, 1, f"c{round_}-{i}")
            if kind == 1:
                return activate(Session, d2)
            with Session() as db:
                if kind == 2:
                    units.sync_member_eligibility(db, buyer, now=NOW)      # restores third: earns
                else:
                    units.suspend_member_units(db, buyer, "test", admin=False, now=NOW)
                db.commit()
            return "ok"
        except Exception as exc:  # noqa: BLE001 - a deadlock or integrity error would surface here
            return f"error:{type(exc).__name__}:{getattr(getattr(exc, 'orig', None), 'pgcode', '')}"

    results = in_threads(8, act)
    assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("error")], results
    with Session() as db:                                                   # settle: everything eligible again
        units.sync_member_eligibility(db, buyer, now=NOW)
        db.commit()
    for purchase_id in (first, second, third):
        assert reconciled(Session, purchase_id) == [], (purchase_id, ledger(Session, purchase_id))
    with Session() as db:
        per_unit = dict(db.query(RevenueRecognition.source_id, func.count())
                        .filter(RevenueRecognition.source_type == accounting.SOURCE_UNIT,
                                RevenueRecognition.reverses_id.is_(None))
                        .group_by(RevenueRecognition.source_id).all())
        assert set(per_unit.values()) <= {1}                                 # never recognized twice
    assert ledger_balanced(Session)
