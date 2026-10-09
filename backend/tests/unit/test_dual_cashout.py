"""Dual cashout of affiliate commissions (owner requirement, 2026-10-08).

Crypto Cashout: minimum $1, paid automatically to the member's verified
wallet by an engine that is OFF by default. USD Cashout: minimum $100, the
member asks for it, the existing fee applies, and no payout provider is
called. The level-1 affiliate program itself is unchanged.

The payout provider is a FAKE object in every test. No test can reach
NOWPayments: `no_network` fails the test if the real HTTP layer is touched.
All users, deposits and commissions are SYNTHETIC.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.accounting import AccountType, AuditTrail, ChartOfAccounts, JournalEntry
from app.models.affiliate import (
    AffiliateCashoutRequest,
    AffiliateCommission,
    CommissionStatus,
    CommissionType,
    PayoutWalletChange,
)
from app.models.payment_config import PaymentSettings
from app.models.user import Permission, Role, User
from app.services import cashout_engine as engine
from app.services import payment_config
from app.services import cashout_service as cs
from app.services import nowpayments_service as nowpayments
from app.services.commission_distribution import process_payment_validation
from app.services.financial_balances import get_commission_balance
from app.services.financial_eligibility import FinancialEligibilityHold
from app.services.financial_reversal import reverse_provider_refund
from app.services.financial_integrity import FinancialIntegrityError
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_new_business_model import (  # noqa: F401
    _assert_all_journals_balance,
    _balance,
    _deposit,
    _retired_legacy,
    world,
)

pytestmark = pytest.mark.unit

PASSWORD = "Str0ng!Passw0rd#26"
WALLET = "0x" + "a" * 40
OTHER_WALLET = "0x" + "b" * 40
NOW = datetime(2026, 10, 8, 12, 0, 0)
LONG_AGO = NOW - timedelta(days=30)


class FakeProvider:
    """Stands in for NOWPayments. Records every call."""

    def __init__(self, *, balance="1000", minimum="0.10", fee="0.02", create=None, statuses=None):
        self._balance, self._minimum, self._fee = Decimal(balance), Decimal(minimum), Decimal(fee)
        self._create = create
        self.statuses = statuses or {}
        self.created = []
        self.status_calls = []

    def balance(self, currency):
        return self._balance

    def minimum(self, currency):
        return self._minimum

    def network_fee(self, currency, amount):
        return self._fee

    def create_payout(self, **kwargs):
        self.created.append(kwargs)
        if self._create is not None:
            return self._create(**kwargs)
        return {"batch_id": f"batch-{len(self.created)}", "status": "WAITING", "verified": True}

    def payout_status(self, batch_id):
        self.status_calls.append(batch_id)
        return self.statuses.get(batch_id, "PROCESSING")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """The real provider functions must never run in a test."""
    def refuse(*_a, **_k):
        raise AssertionError("a test tried to reach the payout provider")

    for name in ("send_payout_sync", "verify_payout_sync", "create_single_payout_sync", "custody_balance_sync",
                 "payout_fee_estimate_sync", "payout_min_amount_sync", "payout_status_sync", "_get_payout_jwt_sync"):
        monkeypatch.setattr(nowpayments, name, refuse)


# Synthetic payout credentials (never sent anywhere: the provider is a fake).
PAYOUT_ENV = {"NOWPAYMENTS_PAYOUT_API_KEY": "synthetic-payout-api-key", "NOWPAYMENTS_EMAIL": "payouts@example.com",
              "NOWPAYMENTS_PASSWORD": "synthetic-password", "NOWPAYMENTS_PAYOUT_TOTP_SECRET": "JBSWY3DPEHPK3PXP"}


def configure(db, **values):
    """Write Finance & Payments settings directly (test set-up only)."""
    row = db.query(PaymentSettings).filter(PaymentSettings.id == 1).first()
    if row is None:
        row = PaymentSettings(id=1, version=0, **payment_config.defaults())
        db.add(row)
    for name, value in values.items():
        assert name in payment_config.FIELDS, name
        setattr(row, name, value)
    db.commit()


def finance_role(db) -> Role:
    """A role that explicitly holds both Finance & Payments permissions."""
    role = db.query(Role).filter(Role.name == "finance_admin").first()
    if role is None:
        role = Role(name="finance_admin", permissions=[
            Permission(name=name, category="admin")
            for name in (payment_config.PERMISSION_MANAGE, payment_config.PERMISSION_PROCESS)])
        db.add(role)
        db.flush()
    return role


@pytest.fixture
def engine_on(monkeypatch, db):
    """Server master switch on, payout credentials present, automatic payouts
    switched on in Finance & Payments."""
    monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", True)
    for name, value in PAYOUT_ENV.items():
        monkeypatch.setattr(settings, name, value)
    configure(db, crypto_auto_payout_enabled=True)


@pytest.fixture
def ledger(world):
    world.add(ChartOfAccounts(account_code="4005", account_name="4005", account_type=AccountType.REVENUE,
                              is_active=True))
    world.add(ChartOfAccounts(account_code="1010", account_name="USD bank", account_type=AccountType.ASSET,
                              is_active=True))
    world.commit()
    return world


def member(db, name, *, method=None, wallet=WALLET, verified_at=LONG_AGO, sponsor=None, admin=False,
           dob=datetime(1990, 1, 1)) -> User:
    row = User(email=f"{name}@example.com", username=name, hashed_password=get_password_hash(PASSWORD),
               is_active=True, is_deleted=False, is_admin=admin, date_of_birth=dob,
               sponsor_id=sponsor.id if sponsor else None, personal_referral_code=name.upper(),
               usdt_wallet_address=wallet, payout_currency="usdtbsc", cashout_method=method,
               role_id=finance_role(db).id if admin else None,
               payout_wallet_verified_at=verified_at if wallet else None)
    db.add(row)
    db.commit()
    return row


def commission(db, user, amount, *, status=CommissionStatus.APPROVED, when=None) -> AffiliateCommission:
    payer = db.query(User).filter(User.username == "payer").first() or member(db, "payer", wallet=None)
    row = AffiliateCommission(user_id=user.id, source_user_id=payer.id, commission_type=CommissionType.KYC_PAYMENT,
                              level=1, base_amount=Decimal("10.00"), commission_amount=Decimal(amount), status=status,
                              transaction_date=when or NOW - timedelta(days=2))
    db.add(row)
    db.commit()
    return row


def cashouts(db, user=None):
    db.expire_all()
    query = db.query(AffiliateCashoutRequest)
    if user is not None:
        query = query.filter(AffiliateCashoutRequest.user_id == user.id)
    return query.order_by(AffiliateCashoutRequest.id).all()


def run(db, provider, now=NOW):
    return engine.run_cycle(db, provider=provider, now=now)


# ===========================================================================
# 1. The affiliate program is unchanged: direct sponsor only
# ===========================================================================

def test_level_one_commission_is_calculated_as_before_and_becomes_the_balance(ledger):
    db = ledger
    upline = member(db, "upline")
    sponsor = member(db, "sponsor", sponsor=upline, method="CRYPTO")
    payer = member(db, "payer", sponsor=sponsor, wallet=None)
    assert process_payment_validation(db, _deposit(db, payer, "annual_membership"), defer_commit=True) is True
    db.commit()

    row = db.query(AffiliateCommission).one()
    assert (row.user_id, row.level, row.commission_amount) == (sponsor.id, 1, Decimal("10.00"))   # 20% of $50
    assert db.query(AffiliateCommission).filter_by(user_id=upline.id).count() == 0                # nothing above level 1
    balance = get_commission_balance(db, sponsor.id)
    assert (balance.available, balance.reserved, balance.paid_lifetime) == (Decimal("10.00"), 0, 0)
    assert cs.summary(db, sponsor, now=NOW)["balances"] == {
        "total_earned": 10.0, "pending": 0.0, "available": 10.0, "reserved": 0.0, "paid": 0.0}


# ===========================================================================
# 2. The engine is off unless explicitly enabled
# ===========================================================================

def test_disabled_engine_reserves_nothing_and_never_calls_the_provider(ledger):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    assert settings.CRYPTO_AUTO_PAYOUT_ENABLED is False
    assert run(db, provider) == {"enabled": False, "reconciled": {}, "members": {}}
    assert engine.process_member(db, user.id, provider, facts={}, now=NOW) == "ENGINE_DISABLED"
    assert provider.created == [] and provider.status_calls == [] and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")
    assert cs.summary(db, user, now=NOW)["status"] == "AUTOMATIC_PAYOUT_NOT_ACTIVE"


def test_the_flag_alone_does_not_enable_the_engine_without_provider_credentials(ledger, monkeypatch):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", True)     # credentials still missing
    provider = FakeProvider()
    configure(db, crypto_auto_payout_enabled=True)
    assert engine.engine_enabled(db) is False and run(db, provider)["enabled"] is False
    assert provider.created == [] and cashouts(db) == []


# ===========================================================================
# 3. Crypto Cashout thresholds
# ===========================================================================

@pytest.mark.parametrize("amounts, paid", [(["0.99"], False), (["1.00"], True), (["0.60", "0.40"], True),
                                           (["7.50"], True)])
def test_crypto_minimum_is_one_dollar(ledger, engine_on, amounts, paid):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    for amount in amounts:
        commission(db, user, amount)
    total = sum(Decimal(a) for a in amounts)
    provider = FakeProvider()
    report = run(db, provider)
    if not paid:
        assert report["members"] == {"BELOW_MINIMUM": 1} and provider.created == [] and cashouts(db) == []
        assert get_commission_balance(db, user.id).available == total
        return
    assert report["members"] == {"SUBMITTED": 1}
    assert provider.created == [{"address": WALLET, "amount": total, "currency": "usdtbsc",
                                 "external_id": provider.created[0]["external_id"]}]
    row = cashouts(db, user)[0]
    assert (row.status, row.cashout_method, row.gross_amount, row.fee, row.net_amount) == (
        "processing", "CRYPTO", total, Decimal("0.00"), total)       # the member receives the full amount
    balance = get_commission_balance(db, user.id)
    assert (balance.available, balance.reserved, balance.paid_lifetime) == (0, total, 0)   # reserved, not yet paid


def test_successful_payout_is_paid_only_when_the_provider_reports_it_finished(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "3.00")
    commission(db, user, "2.00")
    provider = FakeProvider()
    run(db, provider)
    assert db.query(JournalEntry).count() == 0                      # nothing posted on submission
    assert run(db, provider)["reconciled"] == {"PENDING": 1}        # provider still working: unchanged

    provider.statuses["batch-1"] = "FINISHED"
    assert run(db, provider)["reconciled"] == {"COMPLETED": 1}
    row = cashouts(db, user)[0]
    assert row.status == "completed" and row.settlement_reference == "batch-1" and row.provider_status == "FINISHED"
    assert all(c.status == CommissionStatus.PAID and c.payout_reference == "batch-1"
               for c in db.query(AffiliateCommission).all())
    balance = get_commission_balance(db, user.id)
    assert (balance.available, balance.reserved, balance.paid_lifetime) == (0, 0, Decimal("5.00"))
    journal = db.query(JournalEntry).filter_by(description=f"Affiliate Cashout #{row.id}").one()
    assert journal.total_debit == journal.total_credit == Decimal("5.00")
    assert _balance(db, "2001") == Decimal("5.00") and _balance(db, "1001") == Decimal("-5.00")
    _assert_all_journals_balance(db)
    # A later cycle changes nothing and pays nothing again.
    assert run(db, provider) == {"enabled": True, "reconciled": {}, "members": {}}
    assert len(provider.created) == 1 and db.query(JournalEntry).count() == 1


# ===========================================================================
# 4. Wallet rules
# ===========================================================================

@pytest.mark.parametrize("kwargs, code", [
    (dict(wallet=None), "WALLET_MISSING"),
    (dict(wallet="not-an-address"), "WALLET_INVALID"),
    (dict(verified_at=None), "WALLET_UNVERIFIED"),
    (dict(verified_at=NOW - timedelta(hours=1)), "WALLET_ON_HOLD"),
])
def test_no_payout_to_a_missing_invalid_unverified_or_held_wallet(ledger, engine_on, kwargs, code):
    db = ledger
    user = member(db, "m1", method="CRYPTO", **kwargs)
    if kwargs.get("wallet") == "not-an-address":
        user.payout_wallet_verified_at = LONG_AGO
        db.commit()
    commission(db, user, "5.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {code: 1}
    assert provider.created == [] and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")     # nothing lost, nothing deducted


def test_wallet_change_needs_the_password_and_starts_a_hold(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    configure(db, wallet_email_verification_required=False)            # the password-only rule
    body = {"usdt_wallet_address": OTHER_WALLET, "payout_currency": "usdtbsc"}

    for password in ("", "wrong-password"):
        resp = client.patch("/api/v1/users/me/wallet", headers=auth(user), json={**body, "current_password": password})
        assert resp.status_code == 403 and resp.json()["detail"]["code"] == "PASSWORD_REQUIRED"
    db.refresh(user)
    assert user.usdt_wallet_address == WALLET and db.query(PayoutWalletChange).count() == 0

    resp = client.patch("/api/v1/users/me/wallet", headers=auth(user), json={**body, "current_password": PASSWORD})
    assert resp.status_code == 200, resp.text
    assert resp.json()["wallet_status"] == "ON_HOLD" and resp.json()["pending_commissions_paid"] == 0
    change = db.query(PayoutWalletChange).one()
    assert (change.old_address, change.new_address) == (WALLET, OTHER_WALLET)
    assert db.query(AuditTrail).filter_by(action="PAYOUT_WALLET_CHANGED").count() == 1

    # Saving a wallet pays nothing, and the engine does not pay to it during the hold.
    provider = FakeProvider()
    now = datetime.utcnow()
    assert run(db, provider, now=now)["members"] == {"WALLET_ON_HOLD": 1} and provider.created == []
    after_hold = now + timedelta(hours=payment_config.load(db).wallet_hold_hours + 1)
    assert run(db, provider, now=after_hold)["members"] == {"SUBMITTED": 1}
    assert provider.created[0]["address"] == OTHER_WALLET


def test_wallet_changes_are_limited_and_refused_during_a_payout(ledger, engine_on, monkeypatch):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    run(db, FakeProvider())                                            # a payout is now in progress
    with pytest.raises(cs.CashoutError) as held:
        cs.change_payout_wallet(db, user, address=OTHER_WALLET, currency="usdtbsc", password=PASSWORD, now=NOW)
    assert held.value.code == "PAYOUT_IN_PROGRESS"

    other = member(db, "m2")
    configure(db, wallet_max_changes_per_day=2, wallet_email_verification_required=False)
    for index in (1, 2):
        cs.change_payout_wallet(db, other, address="0x" + str(index) * 40, currency="usdtbsc", password=PASSWORD,
                                now=NOW)
    with pytest.raises(cs.CashoutError) as limited:
        cs.change_payout_wallet(db, other, address=OTHER_WALLET, currency="usdtbsc", password=PASSWORD, now=NOW)
    assert limited.value.code == "TOO_MANY_CHANGES"
    with pytest.raises(cs.CashoutError) as network:
        cs.change_payout_wallet(db, other, address="T" + "a" * 33, currency="usdttrc20", password=PASSWORD, now=NOW)
    assert network.value.code == "NETWORK_NOT_ENABLED"


def test_wallet_changed_between_reservation_and_sending_cancels_the_payout(ledger, engine_on, monkeypatch):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    real_reserve = cs.reserve

    def reserve_then_change(db_, user_, rows, **kwargs):
        cashout = real_reserve(db_, user_, rows, **kwargs)
        target = db_.query(User).filter(User.id == user_.id).one()
        target.usdt_wallet_address = OTHER_WALLET                      # as if changed by another request
        db_.commit()
        return cashout

    monkeypatch.setattr(cs, "reserve", reserve_then_change)
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"WALLET_CHANGED": 1}
    assert provider.created == [] and cashouts(db, user)[0].status == "cancelled"
    assert get_commission_balance(db, user.id).available == Decimal("5.00")


# ===========================================================================
# 5. Provider conditions
# ===========================================================================

@pytest.mark.parametrize("provider, code", [
    (FakeProvider(balance="4.00"), "INSUFFICIENT_PROVIDER_BALANCE"),
    (FakeProvider(balance="5.01", fee="0.02"), "INSUFFICIENT_PROVIDER_BALANCE"),   # amount + network fee
    (FakeProvider(minimum="6.00"), "BELOW_PROVIDER_MINIMUM"),
    (FakeProvider(fee="2.00"), "NETWORK_FEE_TOO_HIGH"),
])
def test_provider_balance_minimum_and_fee_are_checked_before_anything_is_reserved(ledger, engine_on, provider, code):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    assert run(db, provider)["members"] == {code: 1}
    assert provider.created == [] and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")


def test_the_provider_balance_is_not_spent_twice_in_one_cycle(ledger, engine_on):
    db = ledger
    first, second = member(db, "m1", method="CRYPTO"), member(db, "m2", method="CRYPTO")
    commission(db, first, "5.00", when=NOW - timedelta(days=3))
    commission(db, second, "5.00")
    provider = FakeProvider(balance="6.00")
    assert run(db, provider)["members"] == {"SUBMITTED": 1, "INSUFFICIENT_PROVIDER_BALANCE": 1}
    assert [c["address"] for c in provider.created] == [WALLET] and len(cashouts(db)) == 1
    assert get_commission_balance(db, second.id).available == Decimal("5.00")


def test_unreadable_provider_facts_stop_the_cycle_without_reserving(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    provider.balance = lambda currency: (_ for _ in ()).throw(TimeoutError("no answer"))
    assert run(db, provider)["stopped"] == "PROVIDER_FACTS_UNAVAILABLE"
    assert provider.created == [] and cashouts(db) == []


def test_provider_timeout_is_unknown_stays_reserved_and_is_never_sent_again(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")

    def timeout(**_kwargs):
        raise TimeoutError("provider timed out")

    provider = FakeProvider(create=timeout)
    assert run(db, provider)["members"] == {"OUTCOME_UNKNOWN": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code, row.provider_batch_id) == ("unknown", "PROVIDER_OUTCOME_UNKNOWN", None)
    balance = get_commission_balance(db, user.id)
    assert (balance.available, balance.reserved) == (0, Decimal("5.00"))
    for _ in range(3):                                               # later cycles: no second attempt
        run(db, provider, now=NOW + timedelta(days=5))
    assert len(provider.created) == 1 and len(cashouts(db, user)) == 1 and db.query(JournalEntry).count() == 0
    assert cs.summary(db, user, now=NOW)["status"] == "IN_PROGRESS"


@pytest.mark.parametrize("outcome, status, available, paid", [("NOT_SENT", "failed", "5.00", "0.00"),
                                                              ("SENT", "completed", "0.00", "5.00")])
def test_an_administrator_settles_an_unknown_payout_exactly_once(ledger, engine_on, outcome, status, available, paid):
    db = ledger
    user, admin = member(db, "m1", method="CRYPTO"), member(db, "boss", admin=True)
    commission(db, user, "5.00")
    run(db, FakeProvider(create=lambda **_k: (_ for _ in ()).throw(TimeoutError())))
    row = cashouts(db, user)[0]
    with pytest.raises(cs.CashoutError):
        cs.resolve_uncertain(db, row, admin=user, outcome=outcome, reference="tx-1")      # not an administrator
    with pytest.raises(cs.CashoutError):
        cs.resolve_uncertain(db, row, admin=admin, outcome="MAYBE")
    cs.resolve_uncertain(db, row, admin=admin, outcome=outcome, reference="tx-1", now=NOW)
    balance = get_commission_balance(db, user.id)
    assert cashouts(db, user)[0].status == status
    assert (balance.available, balance.reserved, balance.paid_lifetime) == (Decimal(available), 0, Decimal(paid))
    with pytest.raises(cs.CashoutError) as again:                                         # never twice
        cs.resolve_uncertain(db, cashouts(db, user)[0], admin=admin, outcome="SENT", reference="tx-2")
    assert again.value.code == "NOT_UNCERTAIN"
    assert db.query(JournalEntry).count() == (1 if outcome == "SENT" else 0)


def test_a_payout_the_provider_refuses_is_released_and_not_retried_at_once(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")

    def refuse(**_kwargs):
        raise nowpayments.NowPaymentsError("bad request", status_code=400)

    provider = FakeProvider(create=refuse)
    assert run(db, provider)["members"] == {"PROVIDER_REFUSED": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code) == ("failed", "PROVIDER_REFUSED")
    assert get_commission_balance(db, user.id).available == Decimal("5.00")             # back, once
    assert run(db, provider, now=NOW + timedelta(hours=1))["members"] == {"RETRY_BACKOFF": 1}
    assert len(provider.created) == 1
    good = FakeProvider()
    later = NOW + timedelta(hours=settings.CASHOUT_RETRY_BACKOFF_HOURS + 1)
    assert run(db, good, now=later)["members"] == {"SUBMITTED": 1}                       # recovery
    assert [r.status for r in cashouts(db, user)] == ["failed", "processing"]
    assert get_commission_balance(db, user.id).reserved == Decimal("5.00")


def test_a_payout_the_provider_later_fails_is_released_by_reconciliation(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider(statuses={"batch-1": "FAILED"})
    run(db, provider)
    assert run(db, provider)["reconciled"] == {"FAILED": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code) == ("failed", "PROVIDER_FAILED")
    balance = get_commission_balance(db, user.id)
    assert (balance.available, balance.reserved, balance.paid_lifetime) == (Decimal("5.00"), 0, 0)
    assert db.query(JournalEntry).count() == 0


def test_created_but_unconfirmed_payout_is_unknown_and_settled_by_the_provider_status(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider(create=lambda **_k: {"batch_id": "b-9", "status": "CREATING", "verified": False})
    assert run(db, provider)["members"] == {"OUTCOME_UNKNOWN": 1}
    assert cashouts(db, user)[0].failure_code == "PROVIDER_CONFIRMATION_FAILED"
    provider.statuses["b-9"] = "FINISHED"
    assert run(db, provider)["reconciled"] == {"COMPLETED": 1}
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00") and len(provider.created) == 1


# ===========================================================================
# 6. Duplicates and concurrency
# ===========================================================================

def test_repeated_cycles_and_a_second_worker_never_pay_the_same_commission_twice(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    facts = {"balance": Decimal("1000"), "minimum": Decimal("0.10"), "network_fee": Decimal("0.02")}
    assert engine.process_member(db, user.id, provider, facts=facts, now=NOW) == "SUBMITTED"
    assert engine.process_member(db, user.id, provider, facts=facts, now=NOW) == "CASHOUT_IN_PROGRESS"
    run(db, provider)
    commission(db, user, "9.00")                                       # new earnings wait for the open payout
    assert run(db, provider)["members"] == {"CASHOUT_IN_PROGRESS": 1}
    assert len(provider.created) == 1 and len(cashouts(db, user)) == 1


def test_the_database_refuses_a_second_open_cashout_for_one_member(ledger):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    first, second = commission(db, user, "5.00"), commission(db, user, "6.00")
    assert cs.reserve(db, user, [first], method="CRYPTO", fee=Decimal("0"), intent_ref="intent:one", now=NOW,
                      wallet=WALLET, currency="usdtbsc") is not None
    # A racing worker that did not see the first reservation:
    assert cs.reserve(db, user, [second], method="CRYPTO", fee=Decimal("0"), intent_ref="intent:two", now=NOW,
                      wallet=WALLET, currency="usdtbsc") is None
    db.expire_all()
    assert db.get(AffiliateCommission, second.id).payout_reference is None   # the loser reserved nothing
    assert len(cashouts(db, user)) == 1
    balance = get_commission_balance(db, user.id)
    assert (balance.available, balance.reserved) == (Decimal("6.00"), Decimal("5.00"))


def test_partial_failure_one_member_does_not_stop_or_affect_the_others(ledger, engine_on):
    db = ledger
    a, b, c = (member(db, name, method="CRYPTO", wallet="0x" + ch * 40) for name, ch in
               (("ma", "1"), ("mb", "2"), ("mc", "3")))
    for index, user in enumerate((a, b, c)):
        commission(db, user, "5.00", when=NOW - timedelta(days=9 - index))

    def create(**kwargs):
        if kwargs["address"] == b.usdt_wallet_address:
            raise TimeoutError("no answer")
        return {"batch_id": "ok-" + kwargs["address"][2], "status": "WAITING", "verified": True}

    provider = FakeProvider(create=create)
    assert run(db, provider)["members"] == {"SUBMITTED": 2, "OUTCOME_UNKNOWN": 1}
    assert {r.user_id: r.status for r in cashouts(db)} == {a.id: "processing", b.id: "unknown", c.id: "processing"}
    provider.statuses.update({"ok-1": "FINISHED", "ok-3": "FINISHED"})
    run(db, provider)
    assert {r.user_id: r.status for r in cashouts(db)} == {a.id: "completed", b.id: "unknown", c.id: "completed"}
    assert get_commission_balance(db, b.id).reserved == Decimal("5.00")
    _assert_all_journals_balance(db)


# ===========================================================================
# 7. USD Cashout
# ===========================================================================

def test_usd_minimum_is_one_hundred_dollars_and_no_provider_is_called(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="USD", wallet=None)
    commission(db, user, "99.99")
    with pytest.raises(cs.CashoutError) as below:
        cs.request_usd_cashout(db, user, idempotency_key="k1", now=NOW)
    assert below.value.code == "BELOW_MINIMUM" and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal("99.99")

    commission(db, user, "0.01")                                       # exactly $100.00
    provider = FakeProvider()
    row = cs.request_usd_cashout(db, user, idempotency_key="k2", now=NOW)
    assert (row.status, row.cashout_method, row.payout_method) == ("requested", "USD", "usd_manual")
    assert (row.gross_amount, row.fee, row.net_amount) == (Decimal("100.00"), Decimal("20.00"), Decimal("80.00"))
    assert run(db, provider)["members"] == {} and provider.created == []     # the engine ignores USD members
    balance = get_commission_balance(db, user.id)
    assert (balance.available, balance.reserved) == (0, Decimal("100.00"))


@pytest.mark.parametrize("gross, fee", [("100.00", "20.00"), ("2000.00", "20.00"), ("5000.00", "50.00"),
                                        ("200000.00", "1000.00")])
def test_usd_cashout_keeps_the_existing_fee_rule(ledger, gross, fee):
    db = ledger
    user = member(db, "m1", method="USD", wallet=None)
    commission(db, user, gross)
    row = cs.request_usd_cashout(db, user, idempotency_key="fee", now=NOW)
    assert (row.fee, row.net_amount) == (Decimal(fee), Decimal(gross) - Decimal(fee))
    preview = cs.summary(db, user, now=NOW)
    assert preview["fees"]["USD"]["rule"] == "1% of the amount, minimum $20, maximum $1,000"


def test_usd_request_is_idempotent_single_and_must_be_chosen_explicitly(client, ledger):
    db = ledger
    user = member(db, "m1", wallet=None)                               # no method chosen
    commission(db, user, "150.00")
    headers = {**auth(user), "Idempotency-Key": "same-key"}
    resp = client.post("/api/v1/wallet/cashout/usd", headers=headers, json={})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "METHOD_NOT_USD"

    assert client.put("/api/v1/wallet/cashout/method", headers=auth(user), json={"method": "USD"}).status_code == 200
    assert cashouts(db) == []                                          # choosing a method starts nothing
    first = client.post("/api/v1/wallet/cashout/usd", headers=headers, json={})
    replay = client.post("/api/v1/wallet/cashout/usd", headers=headers, json={})
    assert first.status_code == replay.status_code == 200 and first.json()["id"] == replay.json()["id"]
    other = client.post("/api/v1/wallet/cashout/usd", headers={**auth(user), "Idempotency-Key": "new-key"}, json={})
    assert other.status_code == 409 and other.json()["detail"]["code"] == "CASHOUT_IN_PROGRESS"
    assert len(cashouts(db, user)) == 1
    history = client.get("/api/v1/wallet/cashout/history", headers=auth(user)).json()
    assert [(h["method"], h["status"], h["net_amount"]) for h in history] == [("USD", "requested", 130.0)]
    # The original withdrawal address is the same USD request, not a crypto payout.
    legacy = client.post("/api/v1/wallet/withdraw", headers=headers, json={"amount": 150})
    assert legacy.status_code == 200 and legacy.json()["status"] == "requested"
    wrong = client.post("/api/v1/wallet/cashout/usd", headers={**auth(user), "Idempotency-Key": "k3"},
                        json={"amount": 120})
    assert wrong.status_code == 409


def test_usd_settlement_is_disabled_until_configured_then_posts_fee_and_payable(ledger, monkeypatch):
    db = ledger
    user, admin = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True)
    commission(db, user, "500.00")
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    with pytest.raises(cs.CashoutError) as disabled:
        cs.settle_usd_cashout(db, row, admin=admin, reference="wire-1", now=NOW)
    assert disabled.value.code == "USD_SETTLEMENT_DISABLED"
    assert cashouts(db, user)[0].status == "requested" and db.query(JournalEntry).count() == 0

    monkeypatch.setattr(settings, "USD_CASHOUT_SETTLEMENT_ENABLED", True)         # server master switch
    with pytest.raises(cs.CashoutError) as still_off:                             # the Admin switch is still off
        cs.settle_usd_cashout(db, row, admin=admin, reference="wire-1", now=NOW)
    assert still_off.value.code == "USD_SETTLEMENT_DISABLED"
    configure(db, usd_settlement_enabled=True, usd_settlement_account="1010")
    with pytest.raises(cs.CashoutError):
        cs.settle_usd_cashout(db, row, admin=user, reference="wire-1", now=NOW)           # not an administrator
    cs.settle_usd_cashout(db, row, admin=admin, reference="wire-1", now=NOW)
    done = cashouts(db, user)[0]
    assert (done.status, done.settlement_reference, done.reviewed_by) == ("completed", "wire-1", admin.id)
    assert _balance(db, "2001") == Decimal("500.00")                   # payable cleared
    assert _balance(db, "1010") == Decimal("-480.00")                  # net left the USD account
    assert _balance(db, "4005") == Decimal("-20.00")                   # the existing fee is revenue
    assert _balance(db, "1001") == 0                                   # crypto treasury untouched
    _assert_all_journals_balance(db)
    with pytest.raises(cs.CashoutError):
        cs.settle_usd_cashout(db, done, admin=admin, reference="wire-2", now=NOW)         # never twice
    assert db.query(JournalEntry).count() == 1


def test_cancelling_a_usd_request_returns_the_balance_once(client, ledger):
    db = ledger
    user, stranger = member(db, "m1", method="USD", wallet=None), member(db, "m2", method="USD", wallet=None)
    commission(db, user, "150.00")
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    assert client.post(f"/api/v1/wallet/cashout/{row.id}/cancel", headers=auth(stranger),
                       json={"reason": "x"}).status_code == 404
    assert client.post(f"/api/v1/wallet/cashout/{row.id}/cancel", headers=auth(user),
                       json={"reason": "changed my mind"}).status_code == 200
    balance = get_commission_balance(db, user.id)
    assert (balance.available, balance.reserved) == (Decimal("150.00"), 0)
    assert client.post(f"/api/v1/wallet/cashout/{row.id}/cancel", headers=auth(user),
                       json={"reason": "again"}).status_code == 409
    assert get_commission_balance(db, user.id).available == Decimal("150.00")


# ===========================================================================
# 8. Preference
# ===========================================================================

def test_switching_the_cashout_method_moves_no_money_and_duplicates_nothing(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1")
    commission(db, user, "150.00")
    before = cs.summary(db, user, now=NOW)["balances"]
    assert cs.summary(db, user, now=NOW)["status"] == "METHOD_REQUIRED"
    assert run(db, FakeProvider())["members"] == {}                    # no method chosen: never paid

    for method in ("USD", "CRYPTO", "USD", "USD"):
        resp = client.put("/api/v1/wallet/cashout/method", headers=auth(user), json={"method": method})
        assert resp.status_code == 200 and resp.json()["cashout_method"] == method
        assert resp.json()["balances"] == before
    assert cashouts(db) == [] and db.query(JournalEntry).count() == 0
    assert db.query(AuditTrail).filter_by(action="CASHOUT_METHOD_CHANGED").count() == 3   # the repeat is not a change
    assert client.put("/api/v1/wallet/cashout/method", headers=auth(user), json={"method": "BANK"}).status_code == 422

    # An open USD request keeps its method; switching to crypto cannot pay the same rows again.
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    client.put("/api/v1/wallet/cashout/method", headers=auth(user), json={"method": "CRYPTO"})
    provider = FakeProvider()
    assert run(db, provider)["members"] == {} and provider.created == []
    assert cashouts(db, user)[0].cashout_method == "USD" and cashouts(db, user)[0].id == row.id


def test_summary_reports_minimum_fee_destination_and_status_per_method(ledger):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "0.40")
    commission(db, user, "0.30", status=CommissionStatus.PENDING)
    data = cs.summary(db, user, now=NOW)
    assert data["minimum"] == 1.0 and data["status"] == "BELOW_MINIMUM" and data["payable_amount"] == 0.7
    assert data["destination"] == {"type": "CRYPTO", "wallet": "0xaaaa...aaaa", "wallet_status": "VERIFIED",
                                   "payout_currency": "usdtbsc", "network": "USDT BSC (BEP20)",
                                   "payable_from": (LONG_AGO + cs.wallet_hold(db)).isoformat(),
                                   "hold_hours": 72, "email_verification_required": True,
                                   "pending_wallet": None}
    assert data["fees"]["CRYPTO"]["platform_fee"] == 0.0 and data["crypto_payouts_active"] is False
    cs.set_cashout_method(db, user, "USD", now=NOW)
    db.refresh(user)
    data = cs.summary(db, user, now=NOW)
    assert (data["minimum"], data["status"], data["usd_settlement_active"]) == (100.0, "BELOW_MINIMUM", False)


def test_pending_commissions_become_available_only_with_a_usable_destination(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", verified_at=None)
    commission(db, user, "5.00", status=CommissionStatus.PENDING)
    assert run(db, FakeProvider())["members"] == {"WALLET_UNVERIFIED": 1}
    assert get_commission_balance(db, user.id).pending == Decimal("5.00")
    user.payout_wallet_verified_at = LONG_AGO
    db.commit()
    assert run(db, FakeProvider())["members"] == {"SUBMITTED": 1}
    assert get_commission_balance(db, user.id).reserved == Decimal("5.00")


# ===========================================================================
# 9. Eligibility, reversals, authorisation
# ===========================================================================

def test_a_member_on_a_financial_hold_is_never_paid(ledger, engine_on):
    db = ledger
    minor = member(db, "teen", method="CRYPTO", dob=None)             # age unknown: never an adult for payouts
    commission(db, minor, "5.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"ELIGIBILITY_HOLD": 1} and provider.created == []
    cs.set_cashout_method(db, minor, "USD", now=NOW)
    commission(db, minor, "200.00")
    db.refresh(minor)
    with pytest.raises(FinancialEligibilityHold):
        cs.request_usd_cashout(db, minor, idempotency_key="k", now=NOW)
    assert cashouts(db) == [] and get_commission_balance(db, minor.id).earned_lifetime == Decimal("205.00")


def test_reversed_commission_is_never_paid_and_a_reserved_one_blocks_the_refund(ledger, engine_on):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    payer_a = member(db, "payer", sponsor=sponsor, wallet=None)
    payer_b = member(db, "payer2", sponsor=sponsor, wallet=None)
    dep_a = _deposit(db, payer_a, "annual_membership", deposit_id=71)
    dep_b = _deposit(db, payer_b, "annual_membership", deposit_id=72)
    for deposit in (dep_a, dep_b):
        process_payment_validation(db, deposit, defer_commit=True)
    db.commit()

    assert reverse_provider_refund(db, dep_a, {"refund_amount": "50.00"}) is True         # reversed before payout
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 1}
    assert provider.created[0]["amount"] == Decimal("10.00")           # only the commission that still stands
    cancelled = db.query(AffiliateCommission).filter_by(source_id=71).one()
    assert cancelled.status == CommissionStatus.CANCELLED and cancelled.payout_reference is None

    # A refund of a commission that is reserved for an open payout waits for that payout.
    with pytest.raises(FinancialIntegrityError):
        reverse_provider_refund(db, dep_b, {"refund_amount": "50.00"})
    db.rollback()
    provider.statuses["batch-1"] = "FINISHED"
    run(db, provider)
    assert reverse_provider_refund(db, dep_b, {"refund_amount": "50.00"}) is True         # paid: becomes a receivable
    assert _balance(db, "1200") == Decimal("10.00")
    assert get_commission_balance(db, sponsor.id).available == 0
    _assert_all_journals_balance(db)


def test_cashout_endpoints_need_the_owner_or_an_administrator(client, ledger):
    db = ledger
    user, admin = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True)
    commission(db, user, "150.00")
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    assert client.get("/api/v1/wallet/cashout").status_code in (401, 403)
    for path, body in ((f"/api/v1/admin/cashouts/{row.id}/cancel", {"reason": "x"}),
                       (f"/api/v1/admin/cashouts/{row.id}/settle-usd", {"reference": "wire-1"}),
                       (f"/api/v1/admin/cashouts/{row.id}/resolve", {"outcome": "SENT", "reference": "t"}),
                       ("/api/v1/admin/cashouts/run", {})):
        assert client.post(path, headers=auth(user), json=body).status_code == 403
    assert client.get("/api/v1/admin/cashouts", headers=auth(user)).status_code == 403
    assert client.get("/api/v1/admin/cashouts/overview", headers=auth(user)).status_code == 403

    listing = client.get("/api/v1/admin/cashouts?status=requested", headers=auth(admin)).json()
    assert listing["total"] == 1 and listing["items"][0]["user_id"] == user.id
    report = client.get("/api/v1/admin/cashouts/overview", headers=auth(admin)).json()
    assert report["owed"] == {"pending": 0.0, "available": 0.0, "reserved": 150.0}
    assert report["provider_balance_state"] == "NOT_VERIFIED" and report["provider_balance"] is None
    assert report["engine"]["enabled"] is False and report["usd_settlement_enabled"] is False
    assert client.post("/api/v1/admin/cashouts/run", headers=auth(admin)).json()["enabled"] is False
    settle = client.post(f"/api/v1/admin/cashouts/{row.id}/settle-usd", headers=auth(admin),
                         json={"reference": "wire-1"})
    assert settle.status_code == 409 and settle.json()["detail"]["code"] == "USD_SETTLEMENT_DISABLED"
    assert client.post(f"/api/v1/admin/cashouts/{row.id}/cancel", headers=auth(admin),
                       json={"reason": "duplicate"}).status_code == 200
    assert get_commission_balance(db, user.id).available == Decimal("150.00")


def test_reconciliation_report_compares_what_is_owed_with_the_provider_balance(ledger, engine_on):
    db = ledger
    crypto, usd = member(db, "m1", method="CRYPTO"), member(db, "m2", method="USD", wallet=None)
    commission(db, crypto, "40.00")
    commission(db, usd, "300.00")
    short = engine.reconciliation_report(db, provider=FakeProvider(balance="25.00"), read_provider=True)
    assert short["owed_total"] == 340.0 and short["owed_to_crypto_cashout_members"] == 40.0
    assert (short["provider_balance_state"], short["provider_balance"]) == ("READ", 25.0)
    assert short["provider_covers_crypto_members"] is False
    unread = engine.reconciliation_report(db, provider=FakeProvider(balance="25.00"))
    assert unread["provider_balance_state"] == "NOT_VERIFIED" and unread["provider_covers_crypto_members"] is None


def test_every_cashout_step_is_audited_without_full_wallet_addresses(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider(statuses={"batch-1": "FINISHED"})
    run(db, provider)
    run(db, provider)
    row = cashouts(db, user)[0]
    trail = db.query(AuditTrail).filter_by(table_name="affiliate_cashout_requests", record_id=row.id).all()
    assert [a.action for a in trail] == ["CASHOUT_RESERVED", "CASHOUT_COMPLETED"]
    assert WALLET not in str([a.new_values for a in trail])
