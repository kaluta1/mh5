"""Phase 3.1 payment hardening.

* GET /payments/verify-user returns public names only.
* A cashout journal is never posted to an inactive ledger account.
* Callbacks that fail verification are bounded per address; a signed one is
  always processed.
* One provider payment id belongs to one deposit.
* What the provider says a payout cost is recorded, never posted or estimated.

The provider is the in-process stand-in of test_nowpayments_integration; all
members, deposits and commissions are SYNTHETIC.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from app.api.api_v1.endpoints import payment_webhooks, payments
from app.core import rate_limit
from app.core.config import settings
from app.models.accounting import AuditTrail, ChartOfAccounts, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest
from app.models.payment import Deposit, DepositStatus
from app.models.payment_config import PaymentWebhookStat
from app.models.user import User
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services import payment_config as pc
from app.services.financial_balances import get_commission_balance
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import (  # noqa: F401
    NOW,
    WALLET,
    FakeProvider,
    cashouts,
    commission,
    configure,
    engine_on,
    ledger,
    member,
    run,
)
from tests.unit.test_new_business_model import _deposit, _user, world  # noqa: F401
from tests.unit.test_nowpayments_integration import (  # noqa: F401
    DOC_PAYMENT,
    IPN_SECRET,
    IPN_URL,
    RichProvider,
    ipn_body,
    money_rows,
    paid_member,
    pending_deposit,
    post_ipn,
    provider,
    sign,
)

pytestmark = pytest.mark.unit

VERIFY_URL = "/api/v1/payments/verify-user"


@pytest.fixture(autouse=True)
def clean_limits():
    rate_limit._buckets.clear()
    payment_webhooks._bad_callbacks.clear()
    yield
    rate_limit._buckets.clear()
    payment_webhooks._bad_callbacks.clear()


# ===========================================================================
# 1. Recipient lookup: public names only
# ===========================================================================

def people(db):
    me = _user(db, "me@example.com")
    other = _user(db, "other@private-mail.example")
    other.full_name = "Other Member"
    db.commit()
    return me, other


def lookup(client, who, value):
    return client.get(VERIFY_URL, params={"username_or_email": value}, headers=auth(who))


@pytest.mark.parametrize("by", ["username", "email"])
def test_a_recipient_is_confirmed_with_public_names_only(client, db, by):
    me, other = people(db)
    answer = lookup(client, me, other.username if by == "username" else other.email)
    assert answer.status_code == 200
    assert answer.json() == {"username": "other", "display_name": "Other Member"}       # exactly these two fields
    text = answer.text
    assert "private-mail.example" not in text and "@" not in text                        # no email address
    assert "id" not in answer.json() and str(other.id) not in json.dumps(answer.json())  # no internal id


def test_the_purchase_dialog_still_gets_everything_it_uses(client, db):
    """components/dialogs/payment-dialog-v2.tsx shows display_name and
    @username and sends username back as the recipient; nothing else."""
    me, other = people(db)
    found = lookup(client, me, "other").json()
    assert isinstance(found["display_name"], str) and found["display_name"]
    assert found["username"] == other.username
    mine = lookup(client, me, "me@example.com").json()
    assert mine == {"username": "me", "display_name": "me"}


def test_a_member_without_a_username_is_not_named_after_their_email(client, db):
    me, other = people(db)
    other.username, other.full_name = None, None
    db.commit()
    assert lookup(client, me, "other@private-mail.example").json() == {"username": "member",
                                                                       "display_name": "member"}


def test_lookup_needs_a_signed_in_member(client, db):
    people(db)
    assert client.get(VERIFY_URL, params={"username_or_email": "other"}).status_code in (401, 403)
    assert client.get(VERIFY_URL, params={"username_or_email": "other"},
                      headers={"Authorization": "Bearer not-a-token"}).status_code in (401, 403)


def test_missing_inactive_and_deleted_members_all_answer_the_same(client, db):
    me, other = people(db)
    gone = lookup(client, me, "nobody-by-that-name")
    assert gone.status_code == 404
    other.is_active = False
    db.commit()
    inactive = lookup(client, me, "other")
    other.is_active, other.is_deleted = True, True
    db.commit()
    deleted = lookup(client, me, "other@private-mail.example")
    assert inactive.status_code == deleted.status_code == 404
    assert inactive.json() == deleted.json() == gone.json()                              # nothing tells them apart


@pytest.mark.parametrize("value, status_code", [("", 422), ("x" * 255, 422), ("   ", 404), ("a\x00b", 404),
                                                ("' OR 1=1 --", 404), ("%", 404), ("other%", 404)])
def test_invalid_input_is_refused_and_never_matches_loosely(client, db, value, status_code):
    me, _other = people(db)
    assert lookup(client, me, value).status_code == status_code


def test_missing_parameter_is_refused(client, db):
    me, _other = people(db)
    assert client.get(VERIFY_URL, headers=auth(me)).status_code == 422


def test_the_member_list_cannot_be_walked(client, db):
    me, other = people(db)
    second = _user(db, "second@example.com")
    db.commit()
    answers = []
    for i in range(payments.VERIFY_USER_LIMIT):
        # The per-address limit on /payments (20 a minute) would answer first;
        # set it aside to show the per-member limit on its own.
        for key in [k for k in rate_limit._buckets if k.endswith(":/api/v1/payments")]:
            rate_limit._buckets.pop(key)
        answers.append(lookup(client, me, f"guess-{i}").status_code)
    assert set(answers) == {404}
    for key in [k for k in rate_limit._buckets if k.endswith(":/api/v1/payments")]:
        rate_limit._buckets.pop(key)
    assert lookup(client, me, "other").status_code == 429                                # even a real name now
    assert lookup(client, second, "other").status_code == 200                            # another member is not affected


def test_the_existing_per_address_limit_on_payment_routes_also_covers_the_lookup(client, db):
    me, _other = people(db)
    answers = [lookup(client, me, f"guess-{i}").status_code for i in range(25)]
    assert answers[:20] == [404] * 20 and set(answers[20:]) == {429}


# ===========================================================================
# 2. Cashout journals and inactive ledger accounts
# ===========================================================================

def set_active(db, code: str, active: bool) -> None:
    db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).one().is_active = active
    db.commit()


def cashout_journals(db, cashout_id: int) -> int:
    return db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{cashout_id}").count()


def test_with_every_account_active_a_finished_payout_is_posted(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    provider_ = FakeProvider(statuses={"batch-1": "FINISHED"})
    run(db, provider_)
    assert run(db, provider_)["reconciled"] == {"COMPLETED": 1}
    assert cashout_journals(db, cashouts(db, user)[0].id) == 1


@pytest.mark.parametrize("code", ["1001", "2001", "2002", "4005"])
def test_a_finished_payout_is_not_posted_to_an_inactive_account_and_nothing_is_half_written(ledger, engine_on, code):
    db = ledger
    user = paid_member(db)
    provider_ = FakeProvider(statuses={"batch-1": "FINISHED"})
    run(db, provider_)
    row = cashouts(db, user)[0]
    set_active(db, code, False)
    for _ in range(2):
        assert engine.reconcile_cashout(db, row.id, provider_, now=NOW) == "PAID_BUT_NOT_POSTED"
    db.expire_all()
    row = cashouts(db, user)[0]
    balance = get_commission_balance(db, user.id)
    assert row.status == "processing" and cashout_journals(db, row.id) == 0
    assert (balance.reserved, balance.paid_lifetime, balance.available) == (Decimal("5.00"), 0, 0)
    assert db.query(JournalEntry).count() == 0                                           # not redirected elsewhere
    set_active(db, code, True)
    assert engine.reconcile_cashout(db, row.id, provider_, now=NOW) == "COMPLETED"       # posted once, afterwards
    assert cashout_journals(db, row.id) == 1
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")


def test_the_error_names_the_inactive_account_and_is_not_the_missing_account_error(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    run(db, FakeProvider())
    row = cashouts(db, user)[0]
    set_active(db, "1001", False)
    with pytest.raises(cs.CashoutError) as inactive:
        cs.complete(db, row, settlement_reference="batch-1", cash_account="1001", actor_id=None, now=NOW)
    db.rollback()
    assert inactive.value.code == "LEDGER_ACCOUNT_INACTIVE" and "1001" in str(inactive.value)
    with pytest.raises(cs.CashoutError) as missing:
        cs.complete(db, db.get(AffiliateCashoutRequest, row.id), settlement_reference="batch-1",
                    cash_account="1999", actor_id=None, now=NOW)
    db.rollback()
    assert missing.value.code == "LEDGER_NOT_CONFIGURED" and "1999" in str(missing.value)


def test_an_administrator_cannot_record_a_payout_as_sent_into_an_inactive_account(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    admin = member(db, "boss", admin=True)

    def timeout(**_kwargs):
        raise TimeoutError("no answer")

    run(db, FakeProvider(create=timeout))
    row = cashouts(db, user)[0]
    set_active(db, "1001", False)
    with pytest.raises(cs.CashoutError) as error:
        cs.resolve_uncertain(db, row, admin=admin, outcome="SENT", reference="batch-9", now=NOW)
    db.rollback()
    assert error.value.code == "LEDGER_ACCOUNT_INACTIVE"
    db.expire_all()
    assert cashouts(db, user)[0].status == "unknown" and get_commission_balance(db, user.id).reserved == Decimal("5.00")


def test_entries_already_posted_stay_valid_when_an_account_is_switched_off_later(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    provider_ = FakeProvider(statuses={"batch-1": "FINISHED"})
    run(db, provider_)
    run(db, provider_)
    row = cashouts(db, user)[0]
    before = (cashout_journals(db, row.id), db.query(JournalEntry).count(), row.status)
    set_active(db, "1001", False)
    db.expire_all()
    assert (cashout_journals(db, row.id), db.query(JournalEntry).count(), cashouts(db, user)[0].status) == before
    assert engine.discrepancies(db) == []                                                # history is not invalidated
    assert engine.reconcile_cashout(db, row.id, provider_, now=NOW) == "SKIPPED"
    assert cashout_journals(db, row.id) == 1


def test_releasing_a_cashout_needs_no_ledger_account(ledger, engine_on):
    """Nothing is posted when a payout was NOT made, so an inactive account
    never keeps a member's money reserved."""
    db = ledger
    user = paid_member(db)
    provider_ = FakeProvider(statuses={"batch-1": "REJECTED"})
    run(db, provider_)
    set_active(db, "1001", False)
    assert run(db, provider_)["reconciled"] == {"FAILED": 1}
    assert get_commission_balance(db, user.id).available == Decimal("5.00")


# ===========================================================================
# 3. Rejected callbacks are bounded; signed ones are always processed
# ===========================================================================

def stat(db, outcome: str) -> int:
    db.expire_all()
    row = db.query(PaymentWebhookStat).filter(PaymentWebhookStat.outcome == outcome).first()
    return int(row.count) if row else 0


def test_repeated_rejected_callbacks_stop_costing_anything(client, db, monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    body = {"order_id": "mh5-unknown", "payment_id": "1", "payment_status": "finished"}
    limit = payment_webhooks.BAD_CALLBACK_LIMIT
    answers = [post_ipn(client, body, signature="0" * 128).status_code for _ in range(limit)]
    assert answers == [403] * limit and stat(db, "REJECTED_SIGNATURE") == limit
    for attempt in ("0" * 128, False):                                    # wrongly signed, then unsigned
        assert post_ipn(client, body, signature=attempt).status_code == 429
    assert client.post(IPN_URL, content=b"{not json", headers={"content-type": "application/json"}).status_code == 429
    assert client.post(IPN_URL, content=b"x" * (payment_webhooks.MAX_IPN_BODY_BYTES + 1)).status_code == 429
    assert stat(db, "REJECTED_SIGNATURE") == limit and stat(db, "INVALID_JSON") == 0      # nothing more was written


def test_a_correctly_signed_callback_is_processed_even_from_an_address_that_is_being_limited(client, world,
                                                                                             monkeypatch):
    """The provider's notification must never be lost because somebody else,
    seen under the same address, sent rubbish."""
    db = world
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    deposit, _sponsor = pending_deposit(db, code="annual_membership")
    for _ in range(payment_webhooks.BAD_CALLBACK_LIMIT + 5):
        post_ipn(client, ipn_body(deposit, "finished"), signature="0" * 128)
    assert post_ipn(client, ipn_body(deposit, "finished"), signature="0" * 128).status_code == 429
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.PENDING
    assert post_ipn(client, ipn_body(deposit, "finished")).status_code == 200            # signed: processed
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.VALIDATED and money_rows(db, deposit)[0] == 1
    assert stat(db, "ACCEPTED") == 1


def test_the_limit_forgets_after_its_window_and_is_per_address(monkeypatch):
    clock = [1000.0]
    for _ in range(payment_webhooks.BAD_CALLBACK_LIMIT):
        payment_webhooks._note_bad_callback("203.0.113.9", clock[0])
    assert payment_webhooks._recent_bad_callbacks("203.0.113.9", clock[0]) == payment_webhooks.BAD_CALLBACK_LIMIT
    assert payment_webhooks._recent_bad_callbacks("198.51.100.7", clock[0]) == 0
    clock[0] += payment_webhooks.BAD_CALLBACK_WINDOW + 1
    assert payment_webhooks._recent_bad_callbacks("203.0.113.9", clock[0]) == 0
    assert "203.0.113.9" not in payment_webhooks._bad_callbacks                           # no memory kept
    monkeypatch.setattr(payment_webhooks, "_MAX_TRACKED_ADDRESSES", 3)
    for i in range(10):
        payment_webhooks._note_bad_callback(f"192.0.2.{i}", clock[0])
    assert len(payment_webhooks._bad_callbacks) <= 3                                      # bounded


# ===========================================================================
# 4. One provider payment id, one deposit
# ===========================================================================

def test_a_payment_id_another_deposit_already_holds_is_never_attached_twice(client, world, provider, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-payin-key")
    pc.invalidate_runtime()
    first, _sponsor = pending_deposit(db, tag="first")
    first.external_payment_id = DOC_PAYMENT["payment_id"]
    buyer = _user(db, "buyer-dup@t.com")
    db.commit()
    provider.routes[("POST", "/v1/payment")] = (201, DOC_PAYMENT)                         # the same id again
    answer = client.post("/api/v1/payments/create", headers=auth(buyer),
                         json={"amount": 10, "currency": "usd", "product_code": "kyc"})
    assert answer.status_code == 502 and DOC_PAYMENT["payment_id"] not in answer.text
    db.expire_all()
    second = db.query(Deposit).filter(Deposit.user_id == buyer.id).one()
    assert second.status == DepositStatus.FAILED and not second.external_payment_id
    assert db.query(Deposit).filter(Deposit.external_payment_id == DOC_PAYMENT["payment_id"]).count() == 1


def test_a_callback_that_matches_two_deposits_by_payment_id_credits_neither(client, world, monkeypatch):
    """Legacy rows can share a provider id (the column has no unique rule yet)."""
    db = world
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    a, _ = pending_deposit(db, tag="a", code="annual_membership")
    b, _ = pending_deposit(db, tag="b", code="annual_membership")
    a.external_payment_id = b.external_payment_id = "777000111"
    db.commit()
    body = ipn_body(a, "finished", order_id=None, payment_id="777000111")
    assert post_ipn(client, body).status_code == 409
    db.expire_all()
    assert {db.get(Deposit, a.id).status, db.get(Deposit, b.id).status} == {DepositStatus.PENDING}
    assert money_rows(db, a) == (0, 0)
    # With its order id the callback is unambiguous and credits exactly its own deposit.
    assert post_ipn(client, ipn_body(a, "finished", payment_id="777000111")).status_code == 200
    db.expire_all()
    assert db.get(Deposit, a.id).status == DepositStatus.VALIDATED
    assert db.get(Deposit, b.id).status == DepositStatus.PENDING and money_rows(db, a)[0] == 1


# ===========================================================================
# 5. Network fee: recorded as reported, never posted, never estimated
# ===========================================================================

def evidence(db, cashout_id: int) -> dict:
    return db.query(AuditTrail).filter_by(action="CASHOUT_PROVIDER_EVIDENCE", record_id=cashout_id).one().new_values


@pytest.mark.parametrize("reported, paid_by", [("0.0234", "merchant"), (None, None)])
def test_the_fee_the_provider_reports_is_recorded_and_the_ledger_shows_only_the_payout(ledger, engine_on, reported,
                                                                                       paid_by):
    db = ledger
    user = paid_member(db)
    provider_ = RichProvider(fee="0.02")
    run(db, provider_)
    row = cashouts(db, user)[0]
    provider_.details["batch-1"] = {"status": "FINISHED", "address": WALLET, "fee": reported, "fee_paid_by": paid_by}
    assert run(db, provider_)["reconciled"] == {"COMPLETED": 1}
    recorded = evidence(db, row.id)
    assert recorded["provider_fee"] == reported and recorded["provider_fee_paid_by"] == paid_by   # never invented
    assert recorded["network_fee_estimate"] == "0.02" and recorded["network_fee_policy"] == "COMPANY_PAYS"
    entry = db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{row.id}").one()
    assert Decimal(str(entry.total_debit)) == Decimal(str(entry.total_credit)) == Decimal("5.00")   # balanced
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")           # the liability, in full
    for _ in range(2):                                                                   # idempotent
        run(db, provider_, now=NOW + timedelta(hours=1))
    assert db.query(JournalEntry).count() == 1
    assert db.query(AuditTrail).filter_by(action="CASHOUT_PROVIDER_EVIDENCE").count() == 1


@pytest.mark.parametrize("status", ["FAILED", "REJECTED", "PROCESSING"])
def test_no_fee_is_recorded_or_posted_for_a_payout_that_was_not_completed(ledger, engine_on, status):
    db = ledger
    user = paid_member(db)
    provider_ = RichProvider(fee="0.02")
    run(db, provider_)
    provider_.details["batch-1"] = {"status": status, "address": WALLET, "fee": "0.0234", "fee_paid_by": "merchant"}
    run(db, provider_)
    assert db.query(JournalEntry).count() == 0
    assert db.query(AuditTrail).filter_by(action="CASHOUT_PROVIDER_EVIDENCE").count() == 0
    assert get_commission_balance(db, user.id).paid_lifetime == 0
