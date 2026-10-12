"""Crypto cashout: the network fee is paid by the BENEFICIARY.

Owner decision (Phase 3.2): network fees are borne by the beneficiary, who
receives the payout net of them. The whole commission amount is handed to the
provider, which takes its fee out of it (provider fee behaviour
DEDUCTED_BY_PROVIDER). Members accept the fee terms and a maximum fee before
any automatic payout.

What is NOT known and is therefore never assumed here: the provider's actual
deduction behaviour, the values of its `fee_paid_by` field and the unit of its
`fee`. Every default fails closed.

The provider is a fake object; every member, commission, fee and limit is
SYNTHETIC. The limits used (10% / $1.00) are test values, not a policy.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.accounting import AccountType, AuditTrail, ChartOfAccounts, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest
from app.models.payment_config import CashoutFeeConsent, PaymentConfigAudit
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services import payment_config as pc
from app.services.financial_balances import get_commission_balance
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import (  # noqa: F401
    FEE_RULES,
    NOW,
    PASSWORD,
    WALLET,
    FakeProvider,
    accept_terms,
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
from tests.unit.test_nowpayments_integration import RichProvider, paid_member, provider  # noqa: F401
from tests.unit.test_payment_config import plain_admin

pytestmark = pytest.mark.unit

RECEIVER_ENV, COMPANY_ENV = "NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES", "NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES"
AMOUNT_ENV = "NOWPAYMENTS_PAYOUT_AMOUNT_MEANS"
# An administrator read the figures from the provider's statement but did not verify them.
STATEMENT = dict(evidence="PROVIDER_STATEMENT")


@pytest.fixture
def books(ledger):
    """The cashout ledger plus account 5005, which must stay untouched."""
    parent = ledger.query(ChartOfAccounts).filter_by(account_code="5000").one()
    ledger.add(ChartOfAccounts(account_code="5005", account_name="Crypto payout network fees (paid by MyHigh5)",
                               account_type=AccountType.EXPENSE, parent_id=parent.id, is_active=True))
    ledger.commit()
    return ledger


@pytest.fixture
def payers_confirmed(monkeypatch):
    """Both of the provider's payer values and the meaning of its `amount`
    have been confirmed with it (synthetic values)."""
    monkeypatch.setenv(RECEIVER_ENV, "receiver")
    monkeypatch.setenv(COMPANY_ENV, "sender")
    monkeypatch.setenv(AMOUNT_ENV, "REQUESTED")


def finish(db, provider_, *, fee=None, paid_by=None, amount="sent", batch="batch-1", now=NOW):
    """The provider reports the payout finished. By default it reports the
    amount it was asked to send; `amount=None` makes it report none."""
    details = {"status": "FINISHED", "address": WALLET, "fee": fee, "fee_paid_by": paid_by}
    if amount == "sent":
        db.expire_all()
        sent = db.query(AffiliateCashoutRequest.amount_sent).filter_by(provider_batch_id=batch).scalar()
        amount = str(sent) if sent is not None else None
    if amount is not None:
        details["amount"] = amount
    provider_.details[batch] = details
    return run(db, provider_, now=now)


def paid_out(db, user, *, estimate="0.02", **finished):
    """One payout created and reported finished by the provider."""
    provider_ = RichProvider(fee=estimate)
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}
    assert finish(db, provider_, **finished)["reconciled"] == {"COMPLETED": 1}
    return cashouts(db, user)[0], provider_


def discrepancy_types(db) -> list:
    return [(d["type"], d["severity"]) for d in engine.reconciliation_report(db, now=NOW)["discrepancies"]]


# ===========================================================================
# 1. Fail closed: nothing is paid until every fact and approval is in place
# ===========================================================================

@pytest.mark.parametrize("change, code", [
    (dict(provider_fee_mode="UNVERIFIED"), "PROVIDER_FEE_MODE_UNVERIFIED"),
    (dict(provider_fee_mode="CHARGED_TO_BALANCE"), "PROVIDER_FEE_MODE_UNVERIFIED"),
    (dict(network_fee_policy="COMPANY_PAYS"), "FEE_POLICY_NOT_BENEFICIARY_PAID"),
    (dict(member_fee_cap_percent=Decimal("0"), member_fee_cap_usd=Decimal("0")), "FEE_LIMITS_NOT_CONFIGURED"),
    (dict(fee_terms_approved=False), "FEE_LIMITS_NOT_APPROVED"),
    (dict(fee_estimate_margin_percent=None), "FEE_SAFETY_MARGIN_NOT_SET"),
])
def test_no_payout_is_created_unless_the_network_fee_rules_are_in_force(ledger, engine_on, change, code):
    db = ledger
    user = paid_member(db)
    configure(db, **change)
    provider_ = RichProvider()
    assert run(db, provider_) == {"enabled": True, "reconciled": {}, "members": {}, "stopped": code}
    assert engine.process_member(db, user.id, provider_, facts={"balance": Decimal("1000"),
                                                               "minimum": Decimal("0.10")}, now=NOW) == code
    assert provider_.created == [] and provider_.validated == [] and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")
    assert cs.summary(db, user, now=NOW)["status"] == "AUTOMATIC_PAYOUT_NOT_ACTIVE"
    assert cs.summary(db, user, now=NOW)["crypto_payouts_active"] is False


def test_the_built_in_defaults_pay_nobody(ledger, monkeypatch):
    """A fresh installation: the master switch and the credentials alone do nothing."""
    db = ledger
    user = paid_member(db)
    from app.core.config import settings
    from tests.unit.test_dual_cashout import PAYOUT_ENV

    monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", True)
    for name, value in PAYOUT_ENV.items():
        monkeypatch.setattr(settings, name, value)
    configure(db, crypto_auto_payout_enabled=True)                 # everything else is the default
    config = pc.load(db)
    assert (config.network_fee_policy, config.provider_fee_mode, config.fee_terms_approved) == (
        "MEMBER_PAYS", "UNVERIFIED", False)
    provider_ = RichProvider()
    assert run(db, provider_)["stopped"] == "PROVIDER_FEE_MODE_UNVERIFIED"
    assert provider_.created == [] and get_commission_balance(db, user.id).available == Decimal("5.00")


def test_the_only_function_that_decides_what_is_sent_refuses_every_other_behaviour():
    assert cs.amount_to_send("DEDUCTED_BY_PROVIDER", Decimal("5.00")) == Decimal("5.00")
    for mode in ("UNVERIFIED", "CHARGED_TO_BALANCE", "", None, "deducted_by_provider"):
        with pytest.raises(cs.CashoutError) as error:
            cs.amount_to_send(mode, Decimal("5.00"))
        assert error.value.code == "PROVIDER_FEE_MODE_UNVERIFIED"


# ===========================================================================
# 2. The fee is taken once
# ===========================================================================

@pytest.mark.parametrize("gross, estimate", [("5.00", "0.02"), ("5.00", "0.4999"), ("1.00", "0.1"),
                                             ("37.41", "0.31337")])
def test_the_whole_amount_is_handed_to_the_provider_and_the_fee_is_never_subtracted_here(ledger, engine_on, gross,
                                                                                         estimate):
    """Double-deduction prevention: the provider takes the fee out of what it
    is given. Sending gross minus the estimate would take it a second time."""
    db = ledger
    user = paid_member(db, amount=gross)
    provider_ = RichProvider(fee=estimate)
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}
    assert [c["amount"] for c in provider_.created] == [Decimal(gross)]
    row = cashouts(db, user)[0]
    assert (row.amount_sent, row.gross_amount, row.provider_fee_mode) == (Decimal(gross), Decimal(gross),
                                                                         "DEDUCTED_BY_PROVIDER")
    assert row.network_fee_estimate == Decimal(estimate)           # exact, not rounded to cents
    assert row.network_fee_actual is None and row.net_received is None     # nothing is known yet
    reserved = db.query(AuditTrail).filter_by(action="CASHOUT_RESERVED", record_id=row.id).one().new_values
    assert (reserved["amount_sent"], reserved["network_fee_estimate"]) == (gross.rstrip("0").rstrip("."), estimate)


def test_each_payout_gets_its_own_estimate_for_its_own_amount(ledger, engine_on):
    db = ledger
    small, large = paid_member(db, "m1", "5.00"), paid_member(db, "m2", "80.00")
    asked = []

    class ByAmount(RichProvider):
        def network_fee(self, currency, amount):
            asked.append((currency, amount))
            return Decimal(amount) / Decimal("400")                # the fee depends on the amount

    assert run(db, ByAmount())["members"] == {"SUBMITTED": 2}
    assert asked == [("usdtbsc", Decimal("5.00")), ("usdtbsc", Decimal("80.00"))]
    assert cashouts(db, small)[0].network_fee_estimate == Decimal("0.0125")
    assert cashouts(db, large)[0].network_fee_estimate == Decimal("0.2")


def test_no_estimate_means_no_payout(ledger, engine_on):
    db = ledger
    user = paid_member(db)

    class NoEstimate(RichProvider):
        def network_fee(self, currency, amount):
            raise TimeoutError("no answer")

    provider_ = NoEstimate()
    assert run(db, provider_)["members"] == {"FEE_ESTIMATE_UNAVAILABLE": 1}
    assert provider_.created == [] and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")


# ===========================================================================
# 3. The member's acceptance of the fee terms
# ===========================================================================

def test_a_member_who_has_not_accepted_the_fee_terms_is_not_paid(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, "5.00")
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"FEE_TERMS_REQUIRED": 1}
    assert provider_.created == [] and cashouts(db) == []
    summary = cs.summary(db, user, now=NOW)
    assert summary["status"] == "FEE_TERMS_REQUIRED"
    assert summary["fees"]["CRYPTO"]["terms"] == {
        "available": True, "version": 1, "cap_percent": "10", "cap_usd": "1", "valid_days": 0,
        "minimum_received": 0.01, "provider": "NOWPayments", "limit_applies_to": "ESTIMATE",
        "actual_fee_guaranteed": False, "accepted": False, "accepted_at": None, "expires_at": None}
    cs.accept_fee_terms(db, user, version=1, cap_percent="10", cap_usd="1.00", ip="203.0.113.9", now=NOW)
    assert cs.summary(db, user, now=NOW)["status"] == "AUTOMATIC_PAYOUT_PENDING"
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}
    row = cashouts(db, user)[0]
    consent = db.query(CashoutFeeConsent).one()
    assert (row.fee_consent_id, consent.ip_address, consent.terms_version) == (consent.id, "203.0.113.9", 1)
    accepted = db.query(AuditTrail).filter_by(action="CASHOUT_FEE_TERMS_ACCEPTED").one()
    assert accepted.user_id == user.id and accepted.new_values["cap_percent"] == "10"


@pytest.mark.parametrize("consent, valid_days", [
    (dict(version=1, expires_at=NOW - timedelta(seconds=1)), 30),          # expired by time
    (dict(version=1, expires_at=NOW), 30),                                 # expires exactly now
])
def test_an_expired_acceptance_is_no_acceptance(ledger, engine_on, consent, valid_days):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, "5.00")
    configure(db, fee_consent_valid_days=valid_days)
    accept_terms(db, user, **consent)
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"FEE_TERMS_REQUIRED": 1} and provider_.created == []
    assert cs.summary(db, user, now=NOW)["status"] == "FEE_TERMS_REQUIRED"


def test_new_terms_make_every_earlier_acceptance_expire(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    configure(db, fee_terms_version=2)                             # the terms were revised
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"FEE_TERMS_REQUIRED": 1} and provider_.created == []
    cs.accept_fee_terms(db, user, version=2, cap_percent="10.000", cap_usd="1.00", now=NOW)
    rows = db.query(CashoutFeeConsent).order_by(CashoutFeeConsent.id).all()
    assert [(r.terms_version, r.revoked_reason) for r in rows] == [(1, "REPLACED"), (2, None)]
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}


def test_an_acceptance_expires_after_its_lifetime(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, "5.00")
    configure(db, fee_consent_valid_days=30)
    consent = cs.accept_fee_terms(db, user, version=1, cap_percent="10", cap_usd="1", now=NOW - timedelta(days=29))
    assert consent.expires_at == NOW + timedelta(days=1)
    assert cs.active_fee_consent(db, user.id, pc.load(db), NOW) is not None
    assert cs.active_fee_consent(db, user.id, pc.load(db), NOW + timedelta(days=1)) is None
    provider_ = RichProvider()
    assert run(db, provider_, now=NOW + timedelta(days=2))["members"] == {"FEE_TERMS_REQUIRED": 1}


def test_only_the_terms_that_were_shown_and_are_on_offer_can_be_accepted(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)

    def refused(**kwargs) -> str:
        with pytest.raises(cs.CashoutError) as error:
            cs.accept_fee_terms(db, user, now=NOW, **{"version": 1, "cap_percent": "10", "cap_usd": "1", **kwargs})
        return error.value.code

    assert refused(version=2) == "FEE_TERMS_CHANGED"
    assert refused(cap_percent="25") == "FEE_TERMS_CHANGED"        # a limit the member was never shown
    assert refused(cap_usd="50") == "FEE_TERMS_CHANGED"
    assert refused(cap_percent="abc") == "FEE_TERMS_CHANGED"
    configure(db, fee_terms_approved=False)
    assert refused() == "FEE_TERMS_UNAVAILABLE"                    # not approved: nothing to accept
    configure(db, fee_terms_approved=True, provider_fee_mode="UNVERIFIED")
    assert refused() == "FEE_TERMS_UNAVAILABLE"
    assert db.query(CashoutFeeConsent).count() == 0


def test_accepting_twice_keeps_one_acceptance_and_withdrawing_stops_payouts(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, "5.00")
    first = cs.accept_fee_terms(db, user, version=1, cap_percent="10", cap_usd="1", now=NOW)
    again = cs.accept_fee_terms(db, user, version=1, cap_percent="10", cap_usd="1", now=NOW + timedelta(hours=1))
    assert first.id == again.id and db.query(CashoutFeeConsent).count() == 1
    assert cs.withdraw_fee_consent(db, user, now=NOW) is True and cs.withdraw_fee_consent(db, user, now=NOW) is False
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"FEE_TERMS_REQUIRED": 1} and provider_.created == []
    assert db.query(CashoutFeeConsent).one().revoked_reason == "WITHDRAWN"


def test_the_database_keeps_one_acceptance_in_force_per_member(ledger):
    db = ledger
    user = member(db, "m1", method="CRYPTO")                       # holds one acceptance
    from sqlalchemy.exc import IntegrityError

    db.add(CashoutFeeConsent(user_id=user.id, terms_version=1, cap_percent=Decimal("10"), cap_usd=Decimal("1"),
                             accepted_at=NOW))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_terms_withdrawn_between_reservation_and_sending_cancel_the_payout(ledger, engine_on, monkeypatch):
    db = ledger
    user = paid_member(db)
    real_reserve = cs.reserve

    def reserve_then_withdraw(db_, user_, rows, **kwargs):
        cashout = real_reserve(db_, user_, rows, **kwargs)
        cs.withdraw_fee_consent(db_, user_, now=NOW)               # the member withdraws in that instant
        return cashout

    monkeypatch.setattr(cs, "reserve", reserve_then_withdraw)
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"FEE_TERMS_REQUIRED": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code) == ("cancelled", "FEE_TERMS_REQUIRED") and provider_.created == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")        # released, never sent


def test_the_fee_behaviour_suspended_between_reservation_and_sending_cancels_the_payout(ledger, engine_on,
                                                                                        monkeypatch):
    db = ledger
    user = paid_member(db)
    real_reserve = cs.reserve

    def reserve_then_suspend(db_, user_, rows, **kwargs):
        cashout = real_reserve(db_, user_, rows, **kwargs)
        pc.suspend_payouts(db_, reason="PROVIDER_FEE_MODE_MISMATCH", cashout_id=None)
        db_.commit()
        return cashout

    monkeypatch.setattr(cs, "reserve", reserve_then_suspend)
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"PAYOUTS_SUSPENDED": 1}
    assert cashouts(db, user)[0].status == "cancelled" and provider_.created == []


def test_the_member_endpoints_accept_and_withdraw_and_touch_no_money(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, "5.00")
    url = "/api/v1/payments/cashout-fee-terms"
    body = {"version": 1, "cap_percent": "10.000", "cap_usd": "1.00", "accept": True}
    assert client.post(f"{url}/accept", json=body).status_code in (401, 403)
    assert client.post(f"{url}/accept", headers=auth(user), json={**body, "accept": False}).status_code == 422
    stale = client.post(f"{url}/accept", headers=auth(user), json={**body, "cap_usd": "9.00"})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "FEE_TERMS_CHANGED"
    answer = client.post(f"{url}/accept", headers=auth(user), json=body)
    assert answer.status_code == 200 and answer.json()["fees"]["CRYPTO"]["terms"]["accepted"] is True
    assert answer.json()["status"] == "AUTOMATIC_PAYOUT_PENDING"
    assert cashouts(db) == [] and db.query(JournalEntry).count() == 0
    answer = client.post(f"{url}/withdraw", headers=auth(user))
    assert answer.status_code == 200 and answer.json()["status"] == "FEE_TERMS_REQUIRED"
    assert db.query(CashoutFeeConsent).one().revoked_at is not None


# ===========================================================================
# 4. The member's fee limit
# ===========================================================================

@pytest.mark.parametrize("gross, estimate, settings_, consent, code", [
    ("5.00", "0.50", {}, {}, "SUBMITTED"),                         # exactly at 10%
    ("5.00", "0.5001", {}, {}, "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),  # one hair over 10%
    ("50.00", "1.00", {}, {}, "SUBMITTED"),                        # the $1.00 limit is the lower one
    ("50.00", "1.0001", {}, {}, "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),
    # The member accepted LOWER limits than the ones in force now: theirs still bind.
    ("50.00", "0.60", dict(member_fee_cap_usd=Decimal("5.00")), dict(cap_usd="0.50"), "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),
    ("50.00", "0.50", dict(member_fee_cap_usd=Decimal("5.00")), dict(cap_usd="0.50"), "SUBMITTED"),
    # The limits were lowered since the member accepted: the lower ones apply.
    ("50.00", "0.30", dict(member_fee_cap_usd=Decimal("0.25")), {}, "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),
    # Only one kind of limit set.
    ("50.00", "4.99", dict(member_fee_cap_usd=Decimal("0")), dict(cap_usd="0"), "SUBMITTED"),
    ("50.00", "5.01", dict(member_fee_cap_usd=Decimal("0")), dict(cap_usd="0"), "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),
])
def test_the_estimate_is_checked_against_the_lowest_limit_before_anything_is_reserved(ledger, engine_on, gross,
                                                                                      estimate, settings_, consent,
                                                                                      code):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, gross)
    accept_terms(db, user, **consent)
    if settings_:
        configure(db, **settings_)
    provider_ = RichProvider(fee=estimate)
    assert run(db, provider_)["members"] == {code: 1}
    if code == "SUBMITTED":
        assert provider_.created[0]["amount"] == Decimal(gross)
        return
    assert provider_.created == [] and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal(gross)


@pytest.mark.parametrize("gross, estimate, settings_, code", [
    ("5.00", "5.00", dict(member_fee_cap_percent=Decimal("100"), member_fee_cap_usd=Decimal("0"),
                          max_network_fee_percent=Decimal("100")), "NETWORK_FEE_TOO_HIGH"),     # would receive nothing
    ("5.00", "7.00", dict(member_fee_cap_percent=Decimal("100"), member_fee_cap_usd=Decimal("0"),
                          max_network_fee_percent=Decimal("100")), "NETWORK_FEE_TOO_HIGH"),     # negative
    ("5.00", "0.40", dict(min_net_payout_usd=Decimal("4.70")), "BELOW_MINIMUM_RECEIVED"),
    ("5.00", "0.30", dict(min_net_payout_usd=Decimal("4.70")), "SUBMITTED"),
    ("5.00", "0.40", dict(max_network_fee_percent=Decimal("5")), "NETWORK_FEE_TOO_HIGH"),       # the company's own limit
])
def test_a_payout_that_would_leave_nothing_or_too_little_is_never_sent(ledger, engine_on, gross, estimate, settings_,
                                                                       code):
    db = ledger
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, gross)
    configure(db, **settings_)
    accept_terms(db, user, cap_percent=str(pc.load(db).member_fee_cap_percent),
                 cap_usd=str(pc.load(db).member_fee_cap_usd))
    provider_ = RichProvider(fee=estimate)
    assert run(db, provider_)["members"] == {code: 1}
    assert bool(provider_.created) is (code == "SUBMITTED")


def test_an_actual_fee_cannot_leave_the_member_with_nothing(books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row, _ = paid_out(db, user)
    for amount in ("5.00", "5.01", "-0.01", "0.123456789", "abc"):
        with pytest.raises(cs.CashoutError) as error:
            cs.record_member_fee_by_admin(db, row, admin=admin, amount=amount, charged_to="PAYOUT_AMOUNT",
                                          reference="statement 1", now=NOW, **STATEMENT)
        assert error.value.code == "INVALID_FEE"
    assert cashouts(db, user)[0].network_fee_actual is None


# ===========================================================================
# 5. Accounting: the cashout's own entry, nothing else, never 5005
# ===========================================================================

def test_a_completed_payout_settles_the_whole_liability_and_posts_nothing_for_the_fee(books, engine_on,
                                                                                     payers_confirmed):
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user, estimate="0.30", fee="0.2874", paid_by="receiver")
    # Gross, estimate, actual fee and amount received: four separate figures, exact.
    assert (row.gross_amount, row.amount_sent, row.network_fee_estimate, row.network_fee_actual, row.net_received) == (
        Decimal("5.00"), Decimal("5.00"), Decimal("0.30"), Decimal("0.2874"), Decimal("4.7126"))
    assert (row.network_fee_source, row.fee_flag, row.network_fee_policy) == ("PROVIDER_REPORTED", None,
                                                                             "MEMBER_PAYS")
    # One entry: Dr 2001 5.00 / Cr 1001 5.00. The fee is nobody's income or expense here.
    (entry,) = db.query(JournalEntry).all()
    assert entry.description == f"Affiliate Cashout #{row.id}"
    assert Decimal(str(entry.total_debit)) == Decimal(str(entry.total_credit)) == Decimal("5.00")
    assert _balance(db, "2001") == Decimal("5.00") and _balance(db, "1001") == Decimal("-5.00")
    assert _balance(db, "5005") == 0 and _balance(db, "4005") == 0
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")
    _assert_all_journals_balance(db)
    recorded = db.query(AuditTrail).filter_by(action="CASHOUT_MEMBER_FEE_RECORDED", record_id=row.id).one().new_values
    assert (recorded["gross"], recorded["network_fee"], recorded["net_received"], recorded["estimate"]) == (
        "5.00", "0.2874", "4.7126", "0.3")
    assert recorded["charged_to"] == "PAYOUT_AMOUNT" and WALLET not in str(recorded)
    assert discrepancy_types(db) == []
    view = cs.cashout_dict(row)["beneficiary_fee"]
    assert (view["status"], view["actual"], view["net_received"], view["estimate"]) == (
        "RECORDED", "0.2874", "4.7126", "0.3")


def test_account_5005_is_never_used_for_a_beneficiary_paid_payout(client, books, engine_on, payers_confirmed):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row, _ = paid_out(db, user)                                    # the provider reported no fee
    with pytest.raises(cs.CashoutError) as error:
        cs.record_network_fee_by_admin(db, row, admin=admin, amount="0.25", reference="statement 1", now=NOW)
    assert error.value.code == "FEE_NOT_COMPANY_PAID"
    assert cs.network_fee_state(db, row)["status"] == "NOT_APPLICABLE"
    # Even a fee the provider wrongly charged to MyHigh5 is recorded and flagged, not posted.
    answer = client.post(f"/api/v1/admin/cashouts/{row.id}/network-fee", headers=auth(admin),
                         json={"amount": "0.25", "reference": "statement 1", "charged_to": "PROVIDER_BALANCE",
                               "evidence": "PROVIDER_STATEMENT"})
    assert answer.status_code == 200
    assert _balance(db, "5005") == 0 and db.query(JournalEntry).count() == 1
    assert db.query(AuditTrail).filter(AuditTrail.action.like("CASHOUT_NETWORK_FEE%")).count() == 0


@pytest.mark.parametrize("status, expected", [("FAILED", "unknown"), ("REJECTED", "failed"),
                                              ("PROCESSING", "processing")])
def test_a_payout_that_did_not_complete_posts_nothing_and_records_no_fee(books, engine_on, payers_confirmed, status,
                                                                        expected):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    provider_.details["batch-1"] = {"status": status, "address": WALLET, "fee": "0.25", "fee_paid_by": "receiver"}
    run(db, provider_)
    row = cashouts(db, user)[0]
    assert row.status == expected and db.query(JournalEntry).count() == 0
    assert row.network_fee_actual is None and row.net_received is None and row.fee_flag is None
    with pytest.raises(cs.CashoutError) as error:
        cs.record_member_fee_by_admin(db, row, admin=admin, amount="0.25", charged_to="PAYOUT_AMOUNT",
                                      reference="statement 1", now=NOW, **STATEMENT)
    assert error.value.code == "NOT_COMPLETED"
    balance = get_commission_balance(db, user.id)
    # Rejected: the whole commission is owed again. Otherwise it stays reserved.
    assert (balance.available, balance.reserved) == ((Decimal("5.00"), 0) if expected == "failed"
                                                     else (0, Decimal("5.00")))
    assert pc.load(db).provider_fee_mode == "DEDUCTED_BY_PROVIDER"         # nothing was learned: not suspended


def test_an_unknown_outcome_settled_as_sent_waits_for_its_actual_fee(books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)

    def timeout(**_kwargs):
        raise TimeoutError("no answer")

    run(db, RichProvider(create=timeout))
    row = cashouts(db, user)[0]
    assert row.status == "unknown" and db.query(JournalEntry).count() == 0
    cs.resolve_uncertain(db, row, admin=admin, outcome="SENT", reference="batch-9", now=NOW)
    row = cashouts(db, user)[0]
    assert row.status == "completed" and row.network_fee_actual is None
    assert _balance(db, "1001") == Decimal("-5.00") and _balance(db, "5005") == 0
    assert discrepancy_types(db) == [("MEMBER_FEE_NOT_RECORDED", "warning")]
    cs.record_member_fee_by_admin(db, row, admin=admin, amount="0.21", charged_to="PAYOUT_AMOUNT",
                                  reference="statement 1", now=NOW, verified=True, received="4.79", **STATEMENT)
    assert cashouts(db, user)[0].net_received == Decimal("4.79") and discrepancy_types(db) == []


# ===========================================================================
# 6. What the provider reports: nothing is assumed, a mismatch stops payouts
# ===========================================================================

@pytest.mark.parametrize("fee, paid_by", [("0.25", "receiver"), ("0.25", None), ("0.25", ""), (None, "receiver"),
                                          ("0.25", "user"), ("0.25", "sender")])
def test_without_confirmed_payer_values_no_actual_fee_is_recorded_automatically(books, engine_on, monkeypatch, fee,
                                                                               paid_by):
    """The default: the provider documents neither value, so none is trusted."""
    monkeypatch.delenv(RECEIVER_ENV, raising=False)
    monkeypatch.delenv(COMPANY_ENV, raising=False)
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user, fee=fee, paid_by=paid_by)
    assert row.status == "completed" and row.network_fee_actual is None and row.fee_flag is None
    assert cs.cashout_dict(row)["beneficiary_fee"]["status"] == "NOT_RECORDED"
    report = engine.reconciliation_report(db, now=NOW)
    assert report["beneficiary_fees"]["automatic_recording"] is False
    assert report["beneficiary_fees"]["not_recorded"] == [{"cashout_id": row.id, "user_id": user.id,
                                                           "estimate": "0.02"}]
    assert discrepancy_types(db) == [("MEMBER_FEE_NOT_RECORDED", "warning")]
    assert pc.load(db).provider_fee_mode == "DEDUCTED_BY_PROVIDER"


@pytest.mark.parametrize("fee", ["not-a-number", "-0.25", "9999", "0.123456789"])
def test_an_unusable_reported_fee_is_never_recorded(books, engine_on, payers_confirmed, fee):
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user, fee=fee, paid_by="receiver")
    assert row.status == "completed" and row.network_fee_actual is None
    assert discrepancy_types(db) == [("MEMBER_FEE_NOT_RECORDED", "warning")]


def test_a_fee_charged_to_the_myhigh5_balance_is_flagged_and_stops_new_payouts(books, engine_on, payers_confirmed):
    """Unexpected provider behaviour: the account is set to charge the sender."""
    db = books
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"SUBMITTED": 2}
    report = finish(db, provider_, fee="0.25", paid_by="sender")
    assert report["reconciled"] == {"COMPLETED": 1, "PENDING": 1} and report["stopped"] == "PAYOUTS_SUSPENDED"
    row = cashouts(db, first)[0]
    # The member received the whole amount; nothing is taken from them afterwards.
    assert (row.network_fee_actual, row.net_received, row.fee_flag) == (Decimal("0.25"), Decimal("5.00"),
                                                                       "PROVIDER_FEE_MODE_MISMATCH")
    assert _balance(db, "5005") == 0 and _balance(db, "1001") == Decimal("-5.00")    # not booked by itself
    config = pc.load(db)
    assert (config.provider_fee_mode, config.fee_terms_approved) == ("UNVERIFIED", False)
    suspended = db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").one()
    assert suspended.new_values["reason"] == "PROVIDER_FEE_MODE_MISMATCH" and suspended.new_values["cashout_id"] == row.id
    assert ("PROVIDER_FEE_MODE_MISMATCH", "critical") in discrepancy_types(db)
    # A third member is not paid, and the payout already at the provider is still reconciled.
    third = paid_member(db, "m3", "9.00")
    later = finish(db, provider_, batch="batch-2", fee="0.20", paid_by="sender", now=NOW + timedelta(days=2))
    assert later["reconciled"] == {"COMPLETED": 1} and later["members"] == {}
    assert len(provider_.created) == 2 and get_commission_balance(db, third.id).available == Decimal("9.00")
    assert cashouts(db, second)[0].status == "completed"


def test_the_payer_reported_without_a_fee_still_shows_the_mismatch(books, engine_on, payers_confirmed):
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user, fee=None, paid_by="sender")
    assert (row.fee_flag, row.network_fee_actual) == ("PROVIDER_FEE_MODE_MISMATCH", None)
    assert pc.load(db).provider_fee_mode == "UNVERIFIED"
    assert set(discrepancy_types(db)) == {("PAYOUTS_SUSPENDED", "critical"),
                                          ("PROVIDER_FEE_MODE_MISMATCH", "critical"),
                                          ("MEMBER_FEE_NOT_RECORDED", "warning")}


def test_a_provider_that_reports_more_than_it_was_asked_to_send_is_flagged(books, engine_on, payers_confirmed):
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user, fee="0.02", paid_by="receiver", amount="5.02")
    assert row.fee_flag == "PROVIDER_AMOUNT_MISMATCH" and pc.load(db).provider_fee_mode == "UNVERIFIED"
    assert ("PROVIDER_AMOUNT_MISMATCH", "critical") in discrepancy_types(db)


@pytest.mark.parametrize("amount", ["5.00", "5", "4.98", "4.7", None])
def test_while_the_meaning_of_the_amount_is_not_confirmed_it_proves_nothing(books, engine_on, payers_confirmed,
                                                                            monkeypatch, amount):
    """Whether `amount` is what was requested or what was received is not
    documented. Until it is confirmed, an amount at or below the one sent
    raises no flag, and the fee it comes with is recorded as NOT verified."""
    monkeypatch.delenv(AMOUNT_ENV)
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user, fee="0.02", paid_by="receiver", amount=amount)
    assert row.fee_flag is None and row.net_received == Decimal("4.98")
    assert row.fee_reconciliation == "PROVIDER_UNVERIFIED" and cs.fee_reconciled(row) is False
    assert pc.load(db).provider_fee_mode == "DEDUCTED_BY_PROVIDER"


def test_an_actual_fee_above_the_members_limit_is_flagged_and_nothing_more_is_taken(books, engine_on,
                                                                                    payers_confirmed):
    """Fee-cap violation: the estimate was inside the limit, the fee taken was not."""
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user, estimate="0.40", fee="0.75", paid_by="receiver")
    assert row.fee_cap == Decimal("0.50")                          # 10% of 5.00, lower than $1.00
    assert (row.network_fee_actual, row.net_received, row.fee_flag) == (Decimal("0.75"), Decimal("4.25"),
                                                                       "FEE_CAP_EXCEEDED")
    assert ("FEE_CAP_EXCEEDED", "critical") in discrepancy_types(db)
    assert pc.load(db).provider_fee_mode == "UNVERIFIED"           # no further payout until a person has looked
    # The books are untouched by it and the member's liability is settled once, in full.
    assert db.query(JournalEntry).count() == 1 and _balance(db, "5005") == 0
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")
    assert cs.cashout_dict(row)["beneficiary_fee"]["flag"] == "FEE_CAP_EXCEEDED"


def test_the_outcome_is_recorded_once_however_often_the_payout_is_looked_at(books, engine_on, payers_confirmed):
    db = books
    user = paid_member(db)
    row, provider_ = paid_out(db, user, fee="0.25", paid_by="receiver")
    for hour in range(1, 4):
        run(db, provider_, now=NOW + timedelta(hours=hour))
        engine.reconcile_cashout(db, row.id, provider_, now=NOW + timedelta(hours=hour))
    assert db.query(AuditTrail).filter_by(action="CASHOUT_MEMBER_FEE_RECORDED").count() == 1
    assert db.query(JournalEntry).count() == 1
    with pytest.raises(cs.CashoutError) as error:
        cs.record_member_fee(db, db.get(AffiliateCashoutRequest, row.id), amount="0.30", charged_to="PAYOUT_AMOUNT",
                             source=cs.FEE_SOURCE_ADMIN, actor_id=None, now=NOW, **STATEMENT)
    db.rollback()
    assert error.value.code == "FEE_ALREADY_RECORDED" and cashouts(db, user)[0].network_fee_actual == Decimal("0.25")


# ===========================================================================
# 7. Recording by an administrator
# ===========================================================================

def test_an_administrator_records_the_actual_fee_from_the_providers_statement(client, books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row, _ = paid_out(db, user)
    url = f"/api/v1/admin/cashouts/{row.id}/network-fee"
    detail = client.get(f"/api/v1/admin/cashouts/{row.id}", headers=auth(admin)).json()
    assert detail["cashout"]["beneficiary_fee"] == {
        "applies": True, "provider_fee_mode": "DEDUCTED_BY_PROVIDER", "gross": "5.00", "amount_sent": "5",
        "estimate": "0.02", "estimate_adjusted": "0.02", "margin_percent": "0", "actual": None,
        "net_received": None, "fee_cap": "0.5", "source": None, "flag": None, "reconciliation": None,
        "evidence": None, "reconciled": False, "status": "NOT_RECORDED"}
    body = {"amount": "0.0234", "reference": "payout 5000000713", "evidence": "PROVIDER_STATEMENT"}
    missing = client.post(url, headers=auth(admin), json=body)
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "CHARGED_TO_REQUIRED"
    no_evidence = client.post(url, headers=auth(admin), json={"amount": "0.0234", "reference": "payout 5000000713",
                                                             "charged_to": "PAYOUT_AMOUNT"})
    assert no_evidence.status_code == 422 and no_evidence.json()["detail"]["code"] == "EVIDENCE_REQUIRED"
    answer = client.post(url, headers=auth(admin), json={**body, "charged_to": "PAYOUT_AMOUNT"})
    assert answer.status_code == 200
    fee = answer.json()["cashout"]["beneficiary_fee"]
    assert (fee["status"], fee["actual"], fee["net_received"], fee["source"], fee["flag"]) == (
        "RECORDED", "0.0234", "4.9766", "ADMIN_RECORDED", None)
    recorded = db.query(AuditTrail).filter_by(action="CASHOUT_MEMBER_FEE_RECORDED", record_id=row.id).one()
    assert recorded.user_id == admin.id and recorded.new_values["reference"] == "payout 5000000713"
    again = client.post(url, headers=auth(admin), json={**body, "amount": "0.03", "charged_to": "PAYOUT_AMOUNT"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "FEE_ALREADY_RECORDED"
    assert db.query(JournalEntry).count() == 1 and _balance(db, "5005") == 0
    assert pc.load(db).provider_fee_mode == "DEDUCTED_BY_PROVIDER"
    _assert_all_journals_balance(db)


@pytest.mark.parametrize("body, flag", [
    ({"amount": "0.25", "charged_to": "PROVIDER_BALANCE"}, "PROVIDER_FEE_MODE_MISMATCH"),
    ({"amount": "0.75", "charged_to": "PAYOUT_AMOUNT"}, "FEE_CAP_EXCEEDED"),
])
def test_what_an_administrator_records_can_also_stop_new_payouts(client, books, engine_on, body, flag):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row, _ = paid_out(db, user)
    answer = client.post(f"/api/v1/admin/cashouts/{row.id}/network-fee", headers=auth(admin),
                         json={**body, "reference": "statement October", "evidence": "PROVIDER_STATEMENT"})
    assert answer.status_code == 200 and answer.json()["cashout"]["beneficiary_fee"]["flag"] == flag
    assert pc.load(db).provider_fee_mode == "UNVERIFIED" and pc.load(db).fee_terms_approved is False
    assert (flag, "critical") in discrepancy_types(db)


def test_a_fee_of_nothing_can_be_confirmed(books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row, _ = paid_out(db, user)
    cs.record_member_fee_by_admin(db, row, admin=admin, amount="0", charged_to="PAYOUT_AMOUNT",
                                  reference="statement 1", now=NOW, verified=True, received="5.00", **STATEMENT)
    row = cashouts(db, user)[0]
    assert (row.network_fee_actual, row.net_received, row.fee_flag) == (0, Decimal("5.00"), None)
    assert discrepancy_types(db) == []


def test_recording_an_actual_fee_needs_the_process_cashouts_permission(client, books, engine_on):
    db = books
    user = paid_member(db)
    row, _ = paid_out(db, user)
    url = f"/api/v1/admin/cashouts/{row.id}/network-fee"
    body = {"amount": "0.25", "reference": "statement 1", "charged_to": "PAYOUT_AMOUNT",
            "evidence": "PROVIDER_STATEMENT"}
    assert client.post(url, json=body).status_code in (401, 403)
    assert client.post(url, headers=auth(user), json=body).status_code == 403                 # a member
    assert client.post(url, headers=auth(plain_admin(db)), json=body).status_code == 403      # an admin without it
    assert cashouts(db, user)[0].network_fee_actual is None


# ===========================================================================
# 8. Configuration: explicit, confirmed, approved separately
# ===========================================================================

def test_the_fee_behaviour_and_the_limits_need_a_confirmation_and_a_separate_approval(db):
    admin = member(db, "boss", admin=True)

    def refused(changes, **kwargs) -> str:
        with pytest.raises(pc.PaymentConfigError) as error:
            pc.update_settings(db, admin, changes, password=PASSWORD, now=NOW, **kwargs)
        return error.value.code

    assert refused({"provider_fee_mode": "CHARGED_TO_BALANCE"}) == "NOT_AVAILABLE"
    assert refused({"provider_fee_mode": "DEDUCTED_BY_PROVIDER"}) == "CONFIRMATION_REQUIRED"
    assert refused({"fee_terms_approved": True}, confirmation=pc.CONFIRM_FEE_LIMITS) == "UNSAFE_ACTIVATION"
    pc.update_settings(db, admin, {"provider_fee_mode": "DEDUCTED_BY_PROVIDER"}, password=PASSWORD, now=NOW,
                       confirmation=pc.CONFIRM_FEE_MODE)
    assert refused({"fee_terms_approved": True}, confirmation=pc.CONFIRM_FEE_LIMITS) == "UNSAFE_ACTIVATION"  # no limit
    # The limits and their approval cannot arrive in one change.
    assert refused({"member_fee_cap_usd": "1.00", "fee_terms_approved": True},
                   confirmation=pc.CONFIRM_FEE_LIMITS) == "UNSAFE_ACTIVATION"
    pc.update_settings(db, admin, {"member_fee_cap_usd": "1.00"}, password=PASSWORD, now=NOW)
    assert pc.load(db).fee_gate() == "FEE_SAFETY_MARGIN_NOT_SET"
    assert refused({"fee_terms_approved": True}, confirmation=pc.CONFIRM_FEE_LIMITS) == "UNSAFE_ACTIVATION"  # no margin
    pc.update_settings(db, admin, {"fee_estimate_margin_percent": "0"}, password=PASSWORD, now=NOW)
    assert pc.load(db).fee_gate() == "FEE_LIMITS_NOT_APPROVED"
    assert refused({"fee_terms_approved": True}) == "CONFIRMATION_REQUIRED"
    config = pc.update_settings(db, admin, {"fee_terms_approved": True}, password=PASSWORD, now=NOW,
                                confirmation=pc.CONFIRM_FEE_LIMITS)
    assert config.fee_gate() is None
    # Any later change to what was approved withdraws the approval.
    config = pc.update_settings(db, admin, {"member_fee_cap_usd": "2.00"}, password=PASSWORD, now=NOW)
    assert (config.member_fee_cap_usd, config.fee_terms_approved, config.fee_gate()) == (
        Decimal("2.00"), False, "FEE_LIMITS_NOT_APPROVED")
    last = db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first()
    assert set(last.changed_fields) == {"member_fee_cap_usd", "fee_terms_approved"}


def test_the_settings_screen_states_why_no_payout_can_be_created(client, db):
    admin = member(db, "boss", admin=True)
    view = client.get("/api/v1/admin/finance/settings", headers=auth(admin)).json()
    assert view["network_fee_gate"]["code"] == "PROVIDER_FEE_MODE_UNVERIFIED"
    assert view["confirmations"]["provider_fee_mode"] == pc.CONFIRM_FEE_MODE
    fields = {f["name"]: f for f in view["fields"]}
    assert fields["provider_fee_mode"]["value"] == "UNVERIFIED" and fields["fee_terms_approved"]["value"] is False
    assert fields["member_fee_cap_percent"]["approval_note"] and fields["member_fee_cap_usd"]["approval_note"]


# ===========================================================================
# 9. Reconciliation
# ===========================================================================

def test_reconciliation_shows_gross_fee_and_received_and_what_is_still_open(books, engine_on, payers_confirmed,
                                                                           monkeypatch):
    db = books
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider(fee="0.03")
    assert run(db, provider_)["members"] == {"SUBMITTED": 2}
    finish(db, provider_, fee="0.0234", paid_by="receiver")
    monkeypatch.delenv(RECEIVER_ENV)                               # the second payout's fee is not reported usably
    finish(db, provider_, batch="batch-2", fee="0.05", paid_by="receiver")
    row_a, row_b = cashouts(db, first)[0], cashouts(db, second)[0]
    report = engine.reconciliation_report(db, now=NOW)
    fees = report["beneficiary_fees"]
    assert (fees["completed_count"], fees["gross_total"], fees["recorded_count"]) == (2, "12.00", 1)
    assert (fees["fee_total"], fees["received_total"]) == ("0.0234", "4.9766")
    assert fees["not_recorded"] == [{"cashout_id": row_b.id, "user_id": second.id, "estimate": "0.03"}]
    assert [(d["type"], d["severity"], d["cashout_id"]) for d in report["discrepancies"]] == [
        ("MEMBER_FEE_NOT_RECORDED", "warning", row_b.id)]
    assert report["network_fees"]["not_recorded_count"] == 0       # nothing waits to be booked to 5005
    assert report["network_fee_gate"] is None and engine.discrepancies(db) == []
    admin = member(db, "boss", admin=True)
    cs.record_member_fee_by_admin(db, row_b, admin=admin, amount="0.0501", charged_to="PAYOUT_AMOUNT",
                                  reference="statement 1", now=NOW, verified=True, received="6.9499", **STATEMENT)
    report = engine.reconciliation_report(db, now=NOW)
    fees = report["beneficiary_fees"]
    assert report["discrepancies"] == [] and fees["not_recorded_count"] == 0
    assert (fees["fee_total"], fees["received_total"]) == ("0.0735", "11.9265")
    # Books: both liabilities settled in full, the treasury down by exactly what was handed over.
    assert _balance(db, "2001") == Decimal("12.00") and _balance(db, "1001") == Decimal("-12.00")
    assert _balance(db, "5005") == 0 and row_a.id != row_b.id
    _assert_all_journals_balance(db)


def test_the_provider_balance_is_reduced_by_each_payouts_own_estimate(ledger, engine_on):
    db = ledger
    paid_member(db, "m1", "5.00")
    paid_member(db, "m2", "5.00")
    # 10.30 covers the first payout and its fee (5.00 + 0.25) but not a second one.
    provider_ = RichProvider(balance="10.30", fee="0.25")
    assert run(db, provider_)["members"] == {"SUBMITTED": 1, "INSUFFICIENT_PROVIDER_BALANCE": 1}
    assert len(provider_.created) == 1
