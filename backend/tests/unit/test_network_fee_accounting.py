"""Network fee of a crypto payout that MyHigh5 pays (ledger account 5005).

Owner decision 2026-10-10: the fee is an expense, Dr 5005 / Cr 1001 (USDT
treasury). Only an ACTUAL fee is posted: the one the provider reported for the
finished payout, and only when it says the fee came from our balance, or the
one an authorised administrator reads from the provider's statement. Never the
estimate, never for a payout that is not completed, once per cashout.

The provider is a fake object; every member, commission and fee is SYNTHETIC.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.accounting import AccountType, AuditTrail, ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCashoutRequest
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
from tests.unit.test_new_business_model import _assert_all_journals_balance, _balance, world  # noqa: F401
from tests.unit.test_nowpayments_integration import RichProvider, paid_member, provider  # noqa: F401
from tests.unit.test_payment_config import plain_admin

pytestmark = pytest.mark.unit

PAYER_ENV = "NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES"


@pytest.fixture
def books(ledger):
    """The cashout ledger plus the approved expense account."""
    parent = ledger.query(ChartOfAccounts).filter_by(account_code="5000").one()
    ledger.add(ChartOfAccounts(account_code="5005", account_name="Crypto payout network fees (paid by MyHigh5)",
                               account_type=AccountType.EXPENSE, parent_id=parent.id, is_active=True))
    ledger.commit()
    return ledger


@pytest.fixture
def payer_confirmed(monkeypatch):
    """The provider's value for "taken from the merchant balance" has been confirmed."""
    monkeypatch.setenv(PAYER_ENV, "merchant, Sender")


def finished(db, user, *, fee="0.0234", paid_by="merchant", estimate="0.02", name="batch-1", **config):
    """Create one payout and let the provider report it finished."""
    if config:
        configure(db, **config)
    provider_ = RichProvider(fee=estimate)
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}
    provider_.details[name] = {"status": "FINISHED", "address": WALLET, "fee": fee, "fee_paid_by": paid_by}
    assert run(db, provider_)["reconciled"] == {"COMPLETED": 1}
    return cashouts(db, user)[0], provider_


def fee_entries(db, cashout_id: int) -> list:
    return db.query(JournalEntry).filter(JournalEntry.description == cs.network_fee_description(cashout_id)).all()


def lines(db, entry) -> list:
    rows = (db.query(ChartOfAccounts.account_code, JournalLine.debit_amount, JournalLine.credit_amount)
            .join(JournalLine, JournalLine.account_id == ChartOfAccounts.id)
            .filter(JournalLine.entry_id == entry.id).order_by(ChartOfAccounts.account_code).all())
    return [(code, Decimal(str(debit)), Decimal(str(credit))) for code, debit, credit in rows]


# ===========================================================================
# 1. The posting
# ===========================================================================

def test_the_actual_fee_is_an_expense_against_the_treasury_and_the_payout_entry_is_unchanged(books, engine_on,
                                                                                            payer_confirmed):
    db = books
    user = paid_member(db)
    row, _ = finished(db, user, fee="0.25")
    (entry,) = fee_entries(db, row.id)
    assert lines(db, entry) == [("1001", Decimal("0.00"), Decimal("0.25")), ("5005", Decimal("0.25"), Decimal("0.00"))]
    assert Decimal(str(entry.total_debit)) == Decimal(str(entry.total_credit)) == Decimal("0.25")
    payout = db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{row.id}").one()
    assert lines(db, payout) == [("1001", Decimal("0.00"), Decimal("5.00")), ("2001", Decimal("5.00"), Decimal("0.00"))]
    # Liability reduced by the gross commission; the treasury by everything that left it.
    assert _balance(db, "2001") == Decimal("5.00") and _balance(db, "1001") == Decimal("-5.25")
    assert _balance(db, "5005") == Decimal("0.25")
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")
    _assert_all_journals_balance(db)
    state = cs.network_fee_state(db, row)
    assert (state["status"], state["amount"], state["source"]) == ("POSTED", "0.25", "PROVIDER_REPORTED")


def test_the_estimate_is_never_what_gets_posted(books, engine_on, payer_confirmed):
    db = books
    user = paid_member(db)
    row, _ = finished(db, user, fee="0.31", estimate="0.02")
    assert Decimal(str(row.network_fee)) == Decimal("0.02")                        # the estimate, kept as an estimate
    (entry,) = fee_entries(db, row.id)
    assert Decimal(str(entry.total_debit)) == Decimal("0.31")                      # the provider's actual figure
    recorded = db.query(AuditTrail).filter_by(action="CASHOUT_NETWORK_FEE_POSTED", record_id=row.id).one().new_values
    assert (recorded["amount"], recorded["reported_amount"], recorded["estimate"]) == ("0.31", "0.31", "0.02")
    assert recorded["expense_account"] == "5005" and recorded["treasury_account"] == "1001"
    assert WALLET not in str(recorded)


@pytest.mark.parametrize("reported, posted", [("0.0234", "0.02"), ("0.005", "0.01"), ("1.32765969", "1.33")])
def test_the_ledger_keeps_cents_and_the_exact_figure_stays_in_the_audit_trail(books, engine_on, payer_confirmed,
                                                                              reported, posted):
    db = books
    user = paid_member(db)
    row, _ = finished(db, user, fee=reported)
    (entry,) = fee_entries(db, row.id)
    assert Decimal(str(entry.total_debit)) == Decimal(posted)
    recorded = db.query(AuditTrail).filter_by(action="CASHOUT_NETWORK_FEE_POSTED", record_id=row.id).one().new_values
    assert (recorded["amount"], recorded["reported_amount"]) == (posted, reported)


@pytest.mark.parametrize("reported", ["0", "0.0", "0.004"])
def test_a_fee_of_nothing_or_under_half_a_cent_is_recorded_but_posts_no_entry(books, engine_on, payer_confirmed,
                                                                             reported):
    db = books
    user = paid_member(db)
    row, _ = finished(db, user, fee=reported)
    assert fee_entries(db, row.id) == [] and _balance(db, "5005") == 0
    state = cs.network_fee_state(db, row)
    assert (state["status"], state["reported"]) == ("NONE", reported)
    assert engine.reconciliation_report(db, now=NOW)["network_fees"]["not_recorded_count"] == 0


def test_the_fee_is_posted_once_however_often_the_payout_is_looked_at(books, engine_on, payer_confirmed):
    db = books
    user = paid_member(db)
    row, provider_ = finished(db, user, fee="0.25")
    for hour in range(1, 4):
        run(db, provider_, now=NOW + timedelta(hours=hour))
        engine.reconcile_cashout(db, row.id, provider_, now=NOW + timedelta(hours=hour))
    assert len(fee_entries(db, row.id)) == 1 and db.query(JournalEntry).count() == 2
    with pytest.raises(cs.CashoutError) as error:
        cs.record_network_fee(db, db.get(AffiliateCashoutRequest, row.id), amount="0.25",
                              source=cs.FEE_SOURCE_PROVIDER, actor_id=None, now=NOW)
    db.rollback()
    assert error.value.code == "FEE_ALREADY_RECORDED" and _balance(db, "5005") == Decimal("0.25")


# ===========================================================================
# 2. Nothing uncertain is posted
# ===========================================================================

def test_without_a_confirmed_payer_value_nothing_is_posted_automatically(books, engine_on, monkeypatch):
    """The default: the provider's fee_paid_by values are not documented."""
    monkeypatch.delenv(PAYER_ENV, raising=False)
    db = books
    user = paid_member(db)
    row, _ = finished(db, user, fee="0.25", paid_by="merchant")
    assert pc.company_fee_payer_values() == frozenset()
    assert fee_entries(db, row.id) == [] and _balance(db, "5005") == 0
    assert cs.network_fee_state(db, row)["status"] == "NOT_RECORDED"
    summary = engine.reconciliation_report(db, now=NOW)["network_fees"]
    assert summary["automatic_posting"] is False and summary["not_recorded_count"] == 1
    assert summary["not_recorded"] == [{"cashout_id": row.id, "user_id": user.id, "estimate": 0.02}]
    evidence = db.query(AuditTrail).filter_by(action="CASHOUT_PROVIDER_EVIDENCE", record_id=row.id).one().new_values
    assert (evidence["provider_fee"], evidence["provider_fee_paid_by"]) == ("0.25", "merchant")   # kept for the books


@pytest.mark.parametrize("fee, paid_by", [(None, "merchant"), ("", "merchant"), ("0.25", None), ("0.25", ""),
                                          ("0.25", "receiver"), ("0.25", "user"), ("not-a-number", "merchant"),
                                          ("-0.25", "merchant"), ("9999", "merchant")])
def test_a_missing_unreadable_or_someone_elses_fee_is_never_posted(books, engine_on, payer_confirmed, fee, paid_by):
    db = books
    user = paid_member(db)
    row, _ = finished(db, user, fee=fee, paid_by=paid_by)
    assert row.status == "completed"                                               # the payout itself is settled
    assert fee_entries(db, row.id) == [] and _balance(db, "5005") == 0
    assert cs.network_fee_state(db, row)["status"] == "NOT_RECORDED"
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")
    _assert_all_journals_balance(db)


@pytest.mark.parametrize("status, expected", [("FAILED", "unknown"), ("REJECTED", "failed"),
                                              ("PROCESSING", "processing"), ("SENDING", "processing")])
def test_no_fee_is_posted_for_a_payout_that_did_not_complete(books, engine_on, payer_confirmed, status, expected):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider(fee="0.02")
    run(db, provider_)
    provider_.details["batch-1"] = {"status": status, "address": WALLET, "fee": "0.25", "fee_paid_by": "merchant"}
    run(db, provider_)
    row = cashouts(db, user)[0]
    assert row.status == expected and db.query(JournalEntry).count() == 0
    assert cs.network_fee_state(db, row)["status"] == "NOT_APPLICABLE"
    with pytest.raises(cs.CashoutError) as error:                                  # nor by hand
        cs.record_network_fee_by_admin(db, row, admin=admin, amount="0.25", reference="statement 1", now=NOW)
    assert error.value.code == "NOT_COMPLETED" and db.query(JournalEntry).count() == 0


def test_an_unknown_outcome_carries_no_fee_until_it_is_settled_as_sent(books, engine_on, payer_confirmed):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)

    def timeout(**_kwargs):
        raise TimeoutError("no answer")

    run(db, FakeProvider(create=timeout))
    row = cashouts(db, user)[0]
    assert row.status == "unknown"
    with pytest.raises(cs.CashoutError):
        cs.record_network_fee_by_admin(db, row, admin=admin, amount="0.25", reference="statement 1", now=NOW)
    cs.resolve_uncertain(db, row, admin=admin, outcome="SENT", reference="batch-9", now=NOW)
    row = cashouts(db, user)[0]
    assert row.status == "completed" and fee_entries(db, row.id) == []             # settling it posts no fee
    assert cs.network_fee_state(db, row)["status"] == "NOT_RECORDED"
    cs.record_network_fee_by_admin(db, row, admin=admin, amount="0.25", reference="statement 1", now=NOW)
    assert _balance(db, "5005") == Decimal("0.25")


def test_when_the_member_pays_the_fee_there_is_no_expense(books, engine_on, payer_confirmed):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row, _ = finished(db, user, fee="0.25", network_fee_policy="MEMBER_PAYS")
    assert row.network_fee_policy == "MEMBER_PAYS" and Decimal(str(row.net_amount)) == Decimal("4.98")
    assert fee_entries(db, row.id) == [] and _balance(db, "5005") == 0
    assert _balance(db, "1001") == Decimal("-5.00")                                # the whole gross left the treasury
    assert cs.network_fee_state(db, row)["status"] == "NOT_APPLICABLE"
    with pytest.raises(cs.CashoutError) as error:
        cs.record_network_fee_by_admin(db, row, admin=admin, amount="0.25", reference="statement 1", now=NOW)
    assert error.value.code == "FEE_NOT_COMPANY_PAID"
    assert engine.reconciliation_report(db, now=NOW)["network_fees"]["not_recorded_count"] == 0


def test_a_payout_in_a_currency_the_ledger_cannot_carry_at_par_is_refused(books, engine_on, payer_confirmed):
    db = books
    user = paid_member(db)
    row, _ = finished(db, user, fee=None)
    row.payout_currency = "btc"
    db.commit()
    with pytest.raises(cs.CashoutError) as error:
        cs.record_network_fee(db, row, amount="0.0001", source=cs.FEE_SOURCE_ADMIN, actor_id=None, now=NOW)
    db.rollback()
    assert error.value.code == "FEE_CURRENCY_UNSUPPORTED" and db.query(JournalEntry).count() == 1


# ===========================================================================
# 3. The ledger accounts
# ===========================================================================

def test_a_payout_completes_even_when_the_expense_account_does_not_exist_yet(ledger, engine_on, payer_confirmed):
    """Before migration b6c7d8e9f0a1: the payout is settled, the fee waits."""
    db = ledger
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row, _ = finished(db, user, fee="0.25")
    assert row.status == "completed" and fee_entries(db, row.id) == []
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")
    assert cs.network_fee_state(db, row)["status"] == "NOT_RECORDED"
    with pytest.raises(cs.CashoutError) as error:
        cs.record_network_fee_by_admin(db, row, admin=admin, amount="0.25", reference="statement 1", now=NOW)
    assert error.value.code == "LEDGER_NOT_CONFIGURED" and "5005" in str(error.value)
    assert db.query(AuditTrail).filter(AuditTrail.action.like("CASHOUT_NETWORK_FEE%")).count() == 0
    db.add(ChartOfAccounts(account_code="5005", account_name="5005", account_type=AccountType.EXPENSE, is_active=True))
    db.commit()
    cs.record_network_fee_by_admin(db, cashouts(db, user)[0], admin=admin, amount="0.25", reference="statement 1",
                                   now=NOW)
    assert _balance(db, "5005") == Decimal("0.25")


@pytest.mark.parametrize("code", ["5005", "1001"])
def test_the_fee_is_not_posted_to_an_inactive_account(books, engine_on, payer_confirmed, code):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider(fee="0.02")
    run(db, provider_)
    row = cashouts(db, user)[0]
    if code == "5005":                                             # 1001 inactive would stop the payout entry itself
        db.query(ChartOfAccounts).filter_by(account_code=code).one().is_active = False
        db.commit()
    provider_.details["batch-1"] = {"status": "FINISHED", "address": WALLET, "fee": "0.25", "fee_paid_by": "merchant"}
    run(db, provider_)
    if code == "1001":
        db.query(ChartOfAccounts).filter_by(account_code=code).one().is_active = False
        db.commit()
        db.query(AuditTrail).filter(AuditTrail.action == "CASHOUT_NETWORK_FEE_POSTED").delete()
        db.query(JournalLine).filter(JournalLine.entry_id.in_(
            [e.id for e in fee_entries(db, row.id)])).delete(synchronize_session=False)
        db.query(JournalEntry).filter(JournalEntry.description == cs.network_fee_description(row.id)).delete()
        db.commit()
    row = cashouts(db, user)[0]
    assert row.status == "completed" and fee_entries(db, row.id) == []
    with pytest.raises(cs.CashoutError) as error:
        cs.record_network_fee_by_admin(db, row, admin=admin, amount="0.25", reference="statement 1", now=NOW)
    assert error.value.code == "LEDGER_ACCOUNT_INACTIVE" and code in str(error.value)
    assert fee_entries(db, row.id) == []
    assert db.query(AuditTrail).filter(AuditTrail.action.like("CASHOUT_NETWORK_FEE%")).count() == 0


# ===========================================================================
# 4. Recording by an administrator
# ===========================================================================

def unrecorded(db, user, monkeypatch):
    monkeypatch.delenv(PAYER_ENV, raising=False)
    row, _ = finished(db, user, fee="0.25")
    return row


def test_an_administrator_records_the_fee_from_the_providers_statement(client, books, engine_on, monkeypatch):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row = unrecorded(db, user, monkeypatch)
    url = f"/api/v1/admin/cashouts/{row.id}/network-fee"
    detail = client.get(f"/api/v1/admin/cashouts/{row.id}", headers=auth(admin)).json()
    assert detail["network_fee_record"] == {"status": "NOT_RECORDED", "amount": None, "source": None,
                                            "reported": None, "estimate": "0.02"}
    answer = client.post(url, headers=auth(admin), json={"amount": "0.27", "reference": "payout 5000000713"})
    assert answer.status_code == 200
    assert answer.json()["network_fee_record"] == {"status": "POSTED", "amount": "0.27", "source": "ADMIN_RECORDED",
                                                   "reported": "0.27", "estimate": "0.02"}
    (entry,) = fee_entries(db, row.id)
    assert lines(db, entry) == [("1001", Decimal("0.00"), Decimal("0.27")), ("5005", Decimal("0.27"), Decimal("0.00"))]
    recorded = db.query(AuditTrail).filter_by(action="CASHOUT_NETWORK_FEE_POSTED", record_id=row.id).one()
    assert recorded.user_id == admin.id and recorded.new_values["reference"] == "payout 5000000713"
    again = client.post(url, headers=auth(admin), json={"amount": "0.27", "reference": "payout 5000000713"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "FEE_ALREADY_RECORDED"
    assert len(fee_entries(db, row.id)) == 1 and _balance(db, "5005") == Decimal("0.27")
    report = client.get("/api/v1/admin/finance/reconciliation", headers=auth(admin)).json()["network_fees"]
    assert (report["posted_count"], report["posted_total"], report["not_recorded_count"]) == (1, 0.27, 0)
    _assert_all_journals_balance(db)


def test_an_administrator_can_confirm_that_no_fee_was_charged(client, books, engine_on, monkeypatch):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row = unrecorded(db, user, monkeypatch)
    answer = client.post(f"/api/v1/admin/cashouts/{row.id}/network-fee", headers=auth(admin),
                         json={"amount": "0", "reference": "statement October"})
    assert answer.status_code == 200 and answer.json()["network_fee_record"]["status"] == "NONE"
    assert fee_entries(db, row.id) == []
    assert engine.reconciliation_report(db, now=NOW)["network_fees"]["confirmed_none_count"] == 1


@pytest.mark.parametrize("body, status_code", [
    ({"amount": "-0.01", "reference": "statement 1"}, 422),
    ({"amount": "abc", "reference": "statement 1"}, 422),
    ({"amount": "0.25", "reference": "x"}, 422),
    ({"amount": "0.25"}, 422),
    ({"reference": "statement 1"}, 422),
    ({"amount": "5.01", "reference": "statement 1"}, 422),          # larger than the payout itself
    ({"amount": "250", "reference": "statement 1"}, 422),
])
def test_an_impossible_fee_is_refused_and_nothing_is_recorded(client, books, engine_on, monkeypatch, body,
                                                             status_code):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    row = unrecorded(db, user, monkeypatch)
    answer = client.post(f"/api/v1/admin/cashouts/{row.id}/network-fee", headers=auth(admin), json=body)
    assert answer.status_code == status_code
    assert fee_entries(db, row.id) == [] and cs.network_fee_state(db, row)["status"] == "NOT_RECORDED"


def test_recording_a_fee_needs_the_process_cashouts_permission(client, books, engine_on, monkeypatch):
    db = books
    user = paid_member(db)
    row = unrecorded(db, user, monkeypatch)
    url = f"/api/v1/admin/cashouts/{row.id}/network-fee"
    body = {"amount": "0.25", "reference": "statement 1"}
    assert client.post(url, json=body).status_code in (401, 403)
    assert client.post(url, headers=auth(user), json=body).status_code == 403                 # a member
    assert client.post(url, headers=auth(plain_admin(db)), json=body).status_code == 403      # an admin without it
    assert fee_entries(db, row.id) == []
    assert client.post("/api/v1/admin/cashouts/999999/network-fee", headers=auth(member(db, "boss", admin=True)),
                       json=body).status_code == 404


def test_a_usd_cashout_has_no_network_fee(client, books):
    db = books
    user = member(db, "m1", method="USD")
    admin = member(db, "boss", admin=True)
    commission(db, user, "150.00")
    configure(db, usd_destination_required=False)
    row = cs.request_usd_cashout(db, user, now=NOW)
    assert cs.network_fee_state(db, row)["status"] == "NOT_APPLICABLE"
    answer = client.post(f"/api/v1/admin/cashouts/{row.id}/network-fee", headers=auth(admin),
                         json={"amount": "0.25", "reference": "statement 1"})
    assert answer.status_code == 409 and answer.json()["detail"]["code"] == "NOT_COMPLETED"


# ===========================================================================
# 5. Reconciliation
# ===========================================================================

def test_reconciliation_separates_fees_booked_from_fees_still_to_record(books, engine_on, monkeypatch):
    db = books
    monkeypatch.setenv(PAYER_ENV, "merchant")
    first = paid_member(db, "m1")
    row_a, _ = finished(db, first, fee="0.25")
    monkeypatch.delenv(PAYER_ENV)
    second = paid_member(db, "m2", "7.00")
    provider_ = RichProvider(fee="0.03")
    assert run(db, provider_, now=NOW + timedelta(days=2))["members"] == {"SUBMITTED": 1}
    provider_.details["batch-1"] = {"status": "FINISHED", "address": WALLET, "fee": "0.30", "fee_paid_by": "merchant"}
    run(db, provider_, now=NOW + timedelta(days=2))
    row_b = cashouts(db, second)[0]
    report = engine.reconciliation_report(db, now=NOW)
    fees = report["network_fees"]
    assert (fees["expense_account"], fees["posted_count"], fees["posted_total"]) == ("5005", 1, 0.25)
    assert fees["not_recorded"] == [{"cashout_id": row_b.id, "user_id": second.id, "estimate": 0.03}]
    # A completed payout with an unrecorded fee is never reported as reconciled.
    assert [(d["type"], d["severity"], d["cashout_id"]) for d in report["discrepancies"]] == [
        ("NETWORK_FEE_NOT_RECORDED", "warning", row_b.id)]
    assert engine.discrepancies(db) == []                          # the internal checks themselves are unaffected
    admin = member(db, "boss", admin=True)
    cs.record_network_fee_by_admin(db, row_b, admin=admin, amount="0.3049", reference="statement 1", now=NOW)
    report = engine.reconciliation_report(db, now=NOW)
    fees = report["network_fees"]
    assert report["discrepancies"] == [] and fees["not_recorded_count"] == 0
    # Ledger in cents (0.25 + 0.30); the exact figures and what rounding left out stay visible.
    assert (fees["posted_total"], fees["reported_total"], fees["rounding_difference"]) == (0.55, "0.5549", "0.0049")
    assert _balance(db, "5005") == Decimal("0.55")
    # Internal liabilities are untouched by fees: both payouts are paid in full.
    assert get_commission_balance(db, first.id).paid_lifetime == Decimal("5.00")
    assert get_commission_balance(db, second.id).paid_lifetime == Decimal("7.00")
    assert _balance(db, "2001") == Decimal("12.00") and _balance(db, "1001") == Decimal("-12.55")
    assert row_a.id != row_b.id
    _assert_all_journals_balance(db)
