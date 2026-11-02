"""Internal wallet payments (Prompt 5) on real PostgreSQL: Referral Pool units paid with commission earnings
through the existing unit lifecycle and ledger, real row locking under concurrency (two purchases, wallet vs
cashout reservation, duplicate keys, concurrent refunds) and migration f6b8d0a2c4e7.

Opt-in: RUN_POSTGRES_TESTS=1. One disposable database per test. Everything is SYNTHETIC."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, text

from app.core.config import settings
from app.models.accounting import ChartOfAccounts, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.business_model import ReferralPoolPurchase, ReferralPoolUnit
from app.models.internal_wallet import InternalWalletPayment, InternalWalletPaymentLine
from app.models.payment import Deposit
from app.models.user import User
from app.services import internal_wallet as iw
from app.services import referral_pool_units as units
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401
from tests.integration.test_referral_pool_accounting_postgres import sponsored_buyer
from tests.integration.test_referral_pool_units_postgres import member, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]
D = Decimal
OLD = datetime.utcnow() - timedelta(days=40)


@pytest.fixture(autouse=True)
def wallet_on(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", True)


def earn(Session, user_id: int, *amounts) -> list:
    with Session() as db:
        rows = [AffiliateCommission(user_id=user_id, source_user_id=user_id, commission_type=CommissionType.KYC_PAYMENT,
                                    level=1, base_amount=D("10.00"), commission_amount=D(a), status=CommissionStatus.APPROVED,
                                    transaction_date=OLD + timedelta(minutes=i), business_model_version="NEW_V2")
                for i, a in enumerate(amounts)]
        db.add_all(rows)
        db.commit()
        return [r.id for r in rows]


def pay(Session, user_id: int, quantity: int = 1, *, key: str | None = None):
    with Session() as db:
        try:
            payment, replayed = iw.pay(db, db.get(User, user_id), product_code=units.PRODUCT_CODE, quantity=quantity,
                                       idempotency_key=key or uuid.uuid4().hex)
            db.commit()
            return ("replayed" if replayed else "ok", payment.id)
        except iw.WalletError as exc:
            db.rollback()
            return ("refused", exc.code)


def spendable(Session, user_id: int) -> Decimal:
    with Session() as db:
        return iw.spendable_balance(db, user_id)


def account(Session, code: str) -> Decimal:
    with Session() as db:
        d, c = (db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                         func.coalesce(func.sum(JournalLine.credit_amount), 0))
                .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
                .filter(ChartOfAccounts.account_code == code).one())
        return D(d) - D(c)


def balanced(Session) -> bool:
    with Session() as db:
        d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                        func.coalesce(func.sum(JournalLine.credit_amount), 0)).one()
        return D(d) == D(c)


def test_a_unit_paid_with_earnings_goes_through_the_existing_unit_lifecycle(world):  # noqa: F811
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    earn(Session, buyer, "90.00", "60.00")
    assert pay(Session, buyer)[0] == "ok"
    with Session() as db:
        p = db.query(InternalWalletPayment).one()
        dep = db.get(Deposit, p.deposit_id)
        purchase = db.query(ReferralPoolPurchase).filter_by(deposit_id=dep.id).one()
        unit_states = [u.status for u in db.query(ReferralPoolUnit).filter_by(purchase_id=purchase.id)]
        sponsor_commissions = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor).count()
        assert (dep.payment_provider, purchase.status, unit_states) == ("internal_wallet", "PAID", ["ACTIVE"])
        assert db.query(Deposit).filter(Deposit.payment_provider == "soncopay").count() == 0
        assert sponsor_commissions == 1                     # the unit's own commission rule, once
        assert iw.reconciliation(db)["ok"]
    assert spendable(Session, buyer) == D("50.00")
    assert account(Session, "1050") == 0 and account(Session, "1001") == 0 and balanced(Session)
    assert account(Session, "2001") > 0                     # buyer's liability settled (minus the sponsor's new one)


def test_two_simultaneous_purchases_cannot_overdraw(world):  # noqa: F811
    _engine, Session = world
    buyer = member(Session)
    earn(Session, buyer, "150.00")
    results = in_threads(2, lambda i: pay(Session, buyer))
    assert sorted(r[0] for r in results) == ["ok", "refused"], results
    assert [r[1] for r in results if r[0] == "refused"] == ["INSUFFICIENT_BALANCE"]
    assert spendable(Session, buyer) == D("50.00") and balanced(Session)


def test_the_same_key_from_many_tabs_pays_once(world):  # noqa: F811
    _engine, Session = world
    buyer = member(Session)
    earn(Session, buyer, "500.00")
    key = uuid.uuid4().hex
    results = in_threads(5, lambda i: pay(Session, buyer, key=key))
    assert sorted(r[0] for r in results).count("ok") == 1 and len({r[1] for r in results}) == 1, results
    with Session() as db:
        assert db.query(InternalWalletPayment).count() == 1 and db.query(ReferralPoolPurchase).count() == 1


def test_wallet_and_cashout_never_use_the_same_commission(world):  # noqa: F811
    from app.services import cashout_service as cs

    _engine, Session = world
    buyer = member(Session)
    earn(Session, buyer, "60.00", "60.00")

    def cashout_reserve():
        with Session() as db:
            rows = cs.available_rows(db, buyer)                 # the cashout's own locked selection
            for r in rows:
                r.payout_reference = "intent:race"
            db.commit()
            return ("reserved", len(rows))

    results = in_threads(2, lambda i: pay(Session, buyer) if i == 0 else cashout_reserve())
    with Session() as db:
        rows = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == buyer).all()
        wallet_ids = {ln.commission_id for ln in db.query(InternalWalletPaymentLine)}
        reserved_ids = {r.id for r in rows if r.payout_reference == "intent:race"}
    assert not (wallet_ids & reserved_ids), results
    assert (results[0][0], results[1]) in {("ok", ("reserved", 0)), ("refused", ("reserved", 2))}, results
    assert balanced(Session)


def test_refund_restores_earnings_once_and_reverses_the_unit(world, monkeypatch):  # noqa: F811
    _engine, Session = world
    buyer, sponsor = sponsored_buyer(Session)
    earn(Session, buyer, "100.00", "30.00")
    admin = member(Session)
    _, payment_id = pay(Session, buyer)
    assert spendable(Session, buyer) == D("30.00")

    def refund(_i):
        with Session() as db:
            try:
                iw.refund(db, db.get(User, admin), payment_id, reason="member asked, approved")
                db.commit()
                return "refunded"
            except iw.WalletError as exc:
                db.rollback()
                return exc.code

    results = in_threads(4, refund)
    assert sorted(results).count("refunded") == 1 and set(results) <= {"refunded", "ALREADY_REFUNDED"}, results
    assert spendable(Session, buyer) == D("130.00")
    with Session() as db:
        p = db.get(InternalWalletPayment, payment_id)
        unit = db.query(ReferralPoolUnit).one()
        sponsor_rows = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == sponsor).all()
        assert p.status == "REFUNDED" and p.refund_journal_entry_id and unit.status == "REFUNDED"
        assert all(c.status == CommissionStatus.CANCELLED for c in sponsor_rows)
        assert db.query(InternalWalletPaymentLine).filter_by(status="ACTIVE").count() == 0
        assert iw.reconciliation(db)["ok"]
    assert account(Session, "1050") == 0 and balanced(Session)


def test_migration_is_additive_and_refuses_to_drop_payments(world):  # noqa: F811
    engine, Session = world
    migration = "f6b8d0a2c4e7_internal_wallet_payments.py"
    with engine.begin() as c:
        c.execute(text("DROP TABLE internal_wallet_payment_lines"))
        c.execute(text("DROP TABLE internal_wallet_payments"))
        c.execute(text("DELETE FROM chart_of_accounts WHERE account_code = '1050'"))
    migrate(engine, migration, "upgrade")
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM internal_wallet_payments")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM chart_of_accounts WHERE account_code = '1050'")).scalar() == 1
    migrate(engine, migration, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('public.internal_wallet_payments')")).scalar() is None
    migrate(engine, migration, "upgrade")
    buyer = member(Session)
    earn(Session, buyer, "100.00")
    assert pay(Session, buyer)[0] == "ok"
    with pytest.raises(Exception, match="cannot be dropped"):
        migrate(engine, migration, "downgrade")
