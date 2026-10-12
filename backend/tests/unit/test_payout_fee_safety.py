"""Crypto payouts: recording gate, estimate safety margin, suspension (Phase 3.3 A).

The member's fee limit is checked against the provider's ESTIMATE. The actual
fee is decided by the provider when it sends and is known only afterwards, so
nothing here guarantees the actual fee of a payout, including the first one.
These controls keep the exposure small instead:

* recording gate (temporary): no further payout while more payouts than the
  configured number (default 0) are still at the provider or completed without
  a VERIFIED actual fee. A missing fee is never taken to be zero, and a figure
  nobody verified does not count. Nothing is wrong yet, so nothing is
  suspended: the gate lifts by itself once the fee is verified;
* safety margin: the estimate is raised by a configured share before it is
  compared with the member's limit. It is not set by default (no payout);
* suspension (persistent): a CONFIRMED inconsistency stops all payouts, the
  reason is kept, and only an administrator's explicit reactivation lifts it.
  Recording a fee afterwards does not.

The provider is a fake object; every member, commission, fee, limit and margin
is SYNTHETIC. No value used here is a policy.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest
from app.models.payment_config import PaymentConfigAudit, PaymentSettings
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services import payment_config as pc
from app.services.financial_balances import get_commission_balance
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_beneficiary_network_fee import (  # noqa: F401
    AMOUNT_ENV,
    COMPANY_ENV,
    RECEIVER_ENV,
    STATEMENT,
    books,
    discrepancy_types,
    finish,
    payers_confirmed,
)
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

NOTE = "Checked payout batch-1 against the provider statement; fee and amount received agree."


@pytest.fixture
def strict(books, engine_on):
    """The real default of the recording gate: one payout at a time, each
    verified before the next. (The shared test rules open it wide.)"""
    configure(books, max_unreconciled_payouts=0)
    return books


def verify(db, row, admin, *, fee="0.02", **overrides):
    """An administrator records a VERIFIED actual fee from the provider's statement."""
    received = str(Decimal(str(row.gross_amount)) - Decimal(fee))
    return cs.record_member_fee_by_admin(db, row, admin=admin, now=NOW, **{
        "amount": fee, "charged_to": "PAYOUT_AMOUNT", "reference": "payout batch-1", "verified": True,
        "received": received, **STATEMENT, **overrides})


def reactivate(db, admin, **overrides):
    return cs.reactivate_payouts(db, admin, **{"password": PASSWORD, "confirmation": pc.CONFIRM_REACTIVATION,
                                               "note": NOTE, **overrides})


def review(db, row, admin, **overrides):
    """An administrator records that they reviewed a flagged payout (Phase 3.3 B)."""
    return cs.review_fee_exception(db, row, admin=admin, now=NOW, **{"password": PASSWORD, "note": NOTE, **overrides})


def suspension(db):
    db.expire_all()
    config = pc.load(db)
    return config.suspended_reason, config.suspended_cashout_id


def restore_rules(db, admin):
    """Put back what a provider mismatch took away: the confirmed fee behaviour and the approval."""
    pc.update_settings(db, admin, {"provider_fee_mode": "DEDUCTED_BY_PROVIDER"}, password=PASSWORD, now=NOW,
                       expected_version=pc.load(db).version,
                       confirmation=pc.CONFIRM_FEE_MODE)
    pc.update_settings(db, admin, {"fee_terms_approved": True}, password=PASSWORD, now=NOW,
                       expected_version=pc.load(db).version,
                       confirmation=pc.CONFIRM_FEE_LIMITS)


# ===========================================================================
# 1. Wording: an estimate limit is not a guarantee
# ===========================================================================

def test_the_terms_say_that_the_limit_is_on_the_estimate_and_the_actual_fee_is_not_guaranteed(books, engine_on):
    db = books
    user = member(db, "m1", method="CRYPTO", terms=False)
    commission(db, user, "5.00")
    crypto = cs.summary(db, user, now=NOW)["fees"]["CRYPTO"]
    assert (crypto["terms"]["limit_applies_to"], crypto["terms"]["actual_fee_guaranteed"]) == ("ESTIMATE", False)
    assert crypto["terms"]["provider"] == "NOWPayments"
    note = crypto["note"]
    for said in ("You pay the blockchain network fee", "NOWPayments deducts it", "you receive the rest",
                 "is an estimate", "the actual fee may differ"):
        assert said in note, said
    for promised in ("guarantee", "never more", "at most", "up to"):
        assert promised not in note.lower()


def test_the_provider_named_to_the_member_is_the_configured_one(books, engine_on):
    db = books
    user = member(db, "m1", method="CRYPTO")
    configure(db, provider_display_name="Synthetic Provider")
    crypto = cs.summary(db, user, now=NOW)["fees"]["CRYPTO"]
    assert crypto["terms"]["provider"] == "Synthetic Provider" and "Synthetic Provider deducts it" in crypto["note"]


def test_the_corrected_wording_leaves_an_existing_acceptance_in_force(books, engine_on):
    """Nothing was deployed with the earlier wording, so no acceptance is
    invalidated: the version, the limits and the stored record are untouched."""
    db = books
    user = member(db, "m1", method="CRYPTO")                       # accepted version 1
    commission(db, user, "5.00")
    assert pc.load(db).fee_terms_version == 1
    terms = cs.summary(db, user, now=NOW)["fees"]["CRYPTO"]["terms"]
    assert terms["accepted"] is True and terms["version"] == 1
    assert run(db, RichProvider())["members"] == {"SUBMITTED": 1}


# ===========================================================================
# 2. Recording gate
# ===========================================================================

def test_by_default_one_payout_is_outstanding_at_a_time(strict):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    assert pc.default_config().max_unreconciled_payouts == 0
    provider_ = RichProvider()
    report = run(db, provider_)
    # A batch is no way around it: the second member of the same cycle waits.
    assert report["members"] == {"SUBMITTED": 1, "FEE_RECONCILIATION_PENDING": 1}
    assert report["stopped"] == "FEE_RECONCILIATION_PENDING" and len(provider_.created) == 1
    assert cs.reconciliation_exposure(db) == {"in_flight": 1, "completed_unreconciled": 0, "total": 1}
    assert get_commission_balance(db, second.id).available == Decimal("7.00") and cashouts(db, second) == []
    # Neither is asking again: a payout still at the provider is not a reconciled one.
    for hour in range(1, 4):
        again = run(db, provider_, now=NOW + timedelta(hours=hour))
        assert again == {"enabled": True, "reconciled": {"PENDING": 1}, "members": {},
                         "stopped": "FEE_RECONCILIATION_PENDING"}
    assert engine.process_member(db, second.id, provider_, now=NOW,
                                 facts={"balance": Decimal("1000"), "minimum": Decimal("0.10")}) \
        == "FEE_RECONCILIATION_PENDING"
    assert len(provider_.created) == 1 and cashouts(db, first)[0].status == "processing"


def test_a_missing_actual_fee_is_never_zero_and_holds_payouts_back_without_suspending_them(strict):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider()
    run(db, provider_)
    report = finish(db, provider_)                                 # finished, and it reports no fee at all
    assert report["reconciled"] == {"COMPLETED": 1} and report["stopped"] == "FEE_RECONCILIATION_PENDING"
    row = cashouts(db, first)[0]
    assert row.status == "completed"                               # the payout itself is settled, in full
    assert (row.network_fee_actual, row.net_received, row.fee_reconciliation) == (None, None, None)
    assert cs.fee_reconciled(row) is False
    assert cs.reconciliation_exposure(db) == {"in_flight": 0, "completed_unreconciled": 1, "total": 1}
    # Nothing is inconsistent, so nothing is suspended and nothing was un-confirmed.
    assert suspension(db) == (None, None)
    config = pc.load(db)
    assert (config.fee_gate(), config.provider_fee_mode, config.fee_terms_approved) == (
        None, "DEDUCTED_BY_PROVIDER", True)
    assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").count() == 0
    assert len(provider_.created) == 1 and cashouts(db, second) == []
    assert discrepancy_types(db) == [("MEMBER_FEE_NOT_RECORDED", "warning")]
    report = engine.reconciliation_report(db, now=NOW)
    assert report["recording_gate"] == {"limit": 0, "in_flight": 0, "completed_unreconciled": 1, "total": 1,
                                        "blocked": True}
    assert report["payout_suspension"] is None and report["network_fee_gate"] is None
    # It stays that way for as long as nobody verifies the fee: time and retries are no way through.
    for day in range(1, 4):
        again = run(db, provider_, now=NOW + timedelta(days=day))
        assert again == {"enabled": True, "reconciled": {}, "members": {}, "stopped": "FEE_RECONCILIATION_PENDING"}
    assert len(provider_.created) == 1


def test_an_unverified_manual_figure_is_kept_but_does_not_count_as_a_reconciliation(strict):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    row = cashouts(db, first)[0]
    cs.record_member_fee_by_admin(db, row, admin=admin, amount="0.02", charged_to="PAYOUT_AMOUNT",
                                  reference="read in the dashboard", now=NOW, **STATEMENT)
    row = cashouts(db, first)[0]
    assert (row.network_fee_actual, row.net_received) == (Decimal("0.02"), Decimal("4.98"))     # recorded
    assert (row.fee_reconciliation, row.fee_evidence, cs.fee_reconciled(row)) == (
        "ADMIN_UNVERIFIED", "PROVIDER_STATEMENT", False)                                       # not a reconciliation
    assert cs.reconciliation_exposure(db)["completed_unreconciled"] == 1
    assert discrepancy_types(db) == [("MEMBER_FEE_NOT_VERIFIED", "warning")]
    recorded = db.query(AuditTrail).filter_by(action="CASHOUT_MEMBER_FEE_RECORDED", record_id=row.id).one()
    assert recorded.user_id == admin.id
    assert (recorded.new_values["verified"], recorded.new_values["evidence"], recorded.new_values["reconciliation"]) \
        == (False, "PROVIDER_STATEMENT", "ADMIN_UNVERIFIED")
    # Still held back by the gate, and still not a suspension: there is nothing to reactivate.
    assert suspension(db) == (None, None)
    with pytest.raises(pc.PaymentConfigError) as error:
        reactivate(db, admin)
    assert error.value.code == "NOT_SUSPENDED"
    assert run(db, provider_, now=NOW + timedelta(days=2))["stopped"] == "FEE_RECONCILIATION_PENDING"
    assert len(provider_.created) == 1 and cashouts(db, second) == []


def test_an_administrators_verified_reconciliation_releases_the_gate_by_itself(strict):
    """Nothing was inconsistent, so no reactivation is asked for: verifying the
    fee is what the gate was waiting for."""
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    later = NOW + timedelta(days=2)
    assert run(db, provider_, now=later)["stopped"] == "FEE_RECONCILIATION_PENDING"
    verify(db, cashouts(db, first)[0], admin)
    row = cashouts(db, first)[0]
    assert (row.fee_reconciliation, row.fee_evidence, cs.fee_reconciled(row)) == (
        "ADMIN_VERIFIED", "PROVIDER_STATEMENT", True)
    assert cs.reconciliation_exposure(db)["total"] == 0 and suspension(db) == (None, None)
    assert discrepancy_types(db) == []
    report = run(db, provider_, now=later)                         # the very next cycle pays the next member
    assert report == {"enabled": True, "reconciled": {}, "members": {"SUBMITTED": 1}}
    assert [c["amount"] for c in provider_.created] == [Decimal("5.00"), Decimal("7.00")]     # whole amounts, once each
    assert cashouts(db, second)[0].status == "processing"
    # No suspension ever existed and nobody had to reactivate anything.
    assert db.query(PaymentConfigAudit).filter(
        PaymentConfigAudit.action.in_(["PAYOUTS_SUSPENDED", "PAYOUTS_REACTIVATED"])).count() == 0
    assert db.query(JournalEntry).count() == 1 and _balance(db, "5005") == 0
    _assert_all_journals_balance(db)


@pytest.mark.parametrize("overrides, code", [
    (dict(received=None), "RECEIVED_REQUIRED"),                    # the amount received was not read
    (dict(received="4.99"), "AMOUNTS_DO_NOT_ADD_UP"),              # it is not the payout less the fee
    (dict(received="5.00"), "AMOUNTS_DO_NOT_ADD_UP"),
    (dict(evidence="OTHER"), "EVIDENCE_REQUIRED"),                 # nothing that can be checked
    (dict(evidence=None), "EVIDENCE_REQUIRED"),
    (dict(evidence="PROVIDER_API"), "EVIDENCE_REQUIRED"),          # an administrator is not the provider
    (dict(charged_to=""), "CHARGED_TO_REQUIRED"),                  # who bore the fee was not stated
    (dict(reference="x"), "REFERENCE_REQUIRED"),
])
def test_a_verified_figure_needs_the_fee_the_payer_the_amount_received_and_real_evidence(strict, overrides, code):
    db = strict
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    with pytest.raises(cs.CashoutError) as error:
        verify(db, cashouts(db, user)[0], admin, **overrides)
    assert error.value.code == code
    row = cashouts(db, user)[0]
    assert row.network_fee_actual is None and row.fee_reconciliation is None and cs.fee_reconciled(row) is False


def test_an_unverified_figure_can_be_replaced_once_by_a_verified_one_and_a_verified_one_never(strict):
    db = strict
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    row = cashouts(db, user)[0]
    record = dict(admin=admin, charged_to="PAYOUT_AMOUNT", reference="payout batch-1", now=NOW, **STATEMENT)
    cs.record_member_fee_by_admin(db, row, amount="0.05", **record)                 # typed in, not verified
    with pytest.raises(cs.CashoutError) as error:                                   # a second unverified guess
        cs.record_member_fee_by_admin(db, row, amount="0.06", **record)
    assert error.value.code == "FEE_ALREADY_RECORDED"
    verify(db, cashouts(db, user)[0], admin, fee="0.0234")                          # the checked figure replaces it
    row = cashouts(db, user)[0]
    assert (row.network_fee_actual, row.net_received, row.fee_reconciliation) == (
        Decimal("0.0234"), Decimal("4.9766"), "ADMIN_VERIFIED")
    replaced = (db.query(AuditTrail).filter_by(action="CASHOUT_MEMBER_FEE_RECORDED", record_id=row.id)
                .order_by(AuditTrail.id.desc()).first())
    assert replaced.old_values == {"network_fee": "0.05", "net_received": "4.95", "reconciliation": "ADMIN_UNVERIFIED",
                                   "evidence": "PROVIDER_STATEMENT"}        # the earlier figure stays on record
    for attempt in (dict(fee="0.03"), dict(fee="0.0234")):                          # verified: never changed again
        with pytest.raises(cs.CashoutError) as error:
            verify(db, cashouts(db, user)[0], admin, **attempt)
        assert error.value.code == "FEE_ALREADY_RECORDED"
    assert cashouts(db, user)[0].network_fee_actual == Decimal("0.0234")


def test_what_the_provider_reports_reconciles_a_payout_only_when_everything_was_confirmed(strict, payers_confirmed):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider()
    run(db, provider_)
    report = finish(db, provider_, fee="0.0234", paid_by="receiver")       # reports the amount it was asked to send
    row = cashouts(db, first)[0]
    assert (row.fee_reconciliation, row.fee_evidence, row.net_received) == (
        "PROVIDER_VERIFIED", "PROVIDER_API", Decimal("4.9766"))
    assert cs.fee_reconciled(row) is True and suspension(db) == (None, None)
    # Reconciled in the same cycle, so the next member's payout goes out in it.
    assert report["reconciled"] == {"COMPLETED": 1} and report["members"] == {"SUBMITTED": 1}
    assert [c["amount"] for c in provider_.created] == [Decimal("5.00"), Decimal("7.00")]
    assert cashouts(db, second)[0].status == "processing"


@pytest.mark.parametrize("env, details, reconciliation", [
    ({AMOUNT_ENV: None}, dict(fee="0.02", paid_by="receiver"), "PROVIDER_UNVERIFIED"),       # meaning of `amount` unknown
    ({}, dict(fee="0.02", paid_by="receiver", amount=None), "PROVIDER_UNVERIFIED"),         # no amount reported
    ({RECEIVER_ENV: None}, dict(fee="0.02", paid_by="receiver"), None),                     # payer value not confirmed
    ({}, dict(fee="0.02", paid_by="unknown-value"), None),                                  # a payer value nobody confirmed
    ({}, dict(fee="0.02", paid_by=None), None),                                             # no payer reported
    ({}, dict(fee=None, paid_by="receiver"), None),                                         # no fee reported
    ({}, dict(fee=None, paid_by=None), None),                                               # nothing reported
    ({}, dict(fee="not-a-number", paid_by="receiver"), None),
])
def test_anything_short_of_a_fully_confirmed_report_holds_payouts_back_and_suspends_nothing(strict, payers_confirmed,
                                                                                           monkeypatch, env, details,
                                                                                           reconciliation):
    for name in env:
        monkeypatch.delenv(name)
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider()
    run(db, provider_)
    report = finish(db, provider_, **details)
    row = cashouts(db, first)[0]
    assert row.fee_reconciliation == reconciliation and cs.fee_reconciled(row) is False and row.fee_flag is None
    # Unverified is not inconsistent: the gate holds the next payout, nothing is suspended or un-confirmed.
    assert report["stopped"] == "FEE_RECONCILIATION_PENDING" and suspension(db) == (None, None)
    assert len(provider_.created) == 1 and cashouts(db, second) == []
    config = pc.load(db)
    assert (config.provider_fee_mode, config.fee_terms_approved, config.fee_gate()) == (
        "DEDUCTED_BY_PROVIDER", True, None)
    assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").count() == 0


def test_a_confirmed_meaning_of_the_amount_that_the_report_contradicts_is_a_mismatch(strict, payers_confirmed,
                                                                                    monkeypatch):
    monkeypatch.setenv(AMOUNT_ENV, "RECEIVED")                     # confirmed: `amount` is what was received
    db = strict
    user = paid_member(db)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_, fee="0.02", paid_by="receiver", amount="4.90")   # 5.00 - 0.02 is 4.98, not 4.90
    row = cashouts(db, user)[0]
    assert row.fee_flag == "PROVIDER_AMOUNT_MISMATCH" and cs.fee_reconciled(row) is False
    assert suspension(db) == ("PROVIDER_AMOUNT_MISMATCH", row.id)
    flagged = db.query(AuditTrail).filter_by(action="CASHOUT_FEE_FLAGGED", record_id=row.id).one().new_values
    assert (flagged["amount_sent"], flagged["provider_amount"], flagged["expected_amount"], flagged["amount_means"]) \
        == ("5", "4.9", "4.98", "RECEIVED")


def test_the_received_meaning_reconciles_when_the_amount_is_the_payout_less_the_fee(strict, payers_confirmed,
                                                                                   monkeypatch):
    monkeypatch.setenv(AMOUNT_ENV, "RECEIVED")
    db = strict
    user = paid_member(db)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_, fee="0.02", paid_by="receiver", amount="4.98")
    row = cashouts(db, user)[0]
    assert (row.fee_reconciliation, row.fee_flag, row.net_received) == ("PROVIDER_VERIFIED", None, Decimal("4.98"))
    assert suspension(db) == (None, None)


def test_a_payout_that_was_not_sent_frees_the_gate_and_an_unknown_one_does_not(strict):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider()
    run(db, provider_)
    provider_.details["batch-1"] = {"status": "FAILED", "address": WALLET}           # not final at this provider
    report = run(db, provider_, now=NOW + timedelta(hours=1))
    assert report["reconciled"] == {"PROVIDER_FAILED": 1} and report["stopped"] == "FEE_RECONCILIATION_PENDING"
    assert cashouts(db, first)[0].status == "unknown" and len(provider_.created) == 1
    provider_.details["batch-1"] = {"status": "REJECTED", "address": WALLET}         # final: nothing was sent
    report = run(db, provider_, now=NOW + timedelta(days=2))
    assert report["reconciled"] == {"FAILED": 1} and cashouts(db, first)[0].status == "failed"
    assert suspension(db) == (None, None)                          # nothing to reconcile, nothing suspended
    # The gate is free again, so the next member's payout goes out (and is now the one outstanding).
    assert report["members"].get("SUBMITTED") == 1 and len(provider_.created) == 2
    assert cashouts(db, second)[0].status == "processing"
    assert cs.reconciliation_exposure(db) == {"in_flight": 1, "completed_unreconciled": 0, "total": 1}


def test_a_payout_settled_by_hand_has_no_fee_and_is_held_by_the_gate(strict):
    db = strict
    user, waiting = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)

    def timeout(**_kwargs):
        raise TimeoutError("no answer")

    provider_ = RichProvider(create=timeout)
    run(db, provider_)
    row = cashouts(db, user)[0]
    assert row.status == "unknown" and cs.reconciliation_exposure(db)["in_flight"] == 1
    cs.resolve_uncertain(db, row, admin=admin, outcome="SENT", reference="batch-9", now=NOW)
    row = cashouts(db, user)[0]
    assert row.status == "completed" and row.network_fee_actual is None
    assert cs.reconciliation_exposure(db) == {"in_flight": 0, "completed_unreconciled": 1, "total": 1}
    assert suspension(db) == (None, None)                          # settling it by hand is not an inconsistency
    assert cs.recording_gate(db, pc.load(db)) == "FEE_RECONCILIATION_PENDING"
    assert run(db, RichProvider(), now=NOW + timedelta(days=2))["stopped"] == "FEE_RECONCILIATION_PENDING"
    assert cashouts(db, waiting) == []


def test_a_completed_payout_written_before_these_rules_counts_as_unreconciled(strict):
    """Fail closed on an ambiguous state: no reconciliation recorded means not reconciled."""
    db = strict
    old, new = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    configure(db, max_unreconciled_payouts=1000)
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"SUBMITTED": 2}
    finish(db, provider_)
    row = cashouts(db, old)[0]
    row.network_fee_actual, row.net_received = Decimal("0.02"), Decimal("4.98")      # figures, but no verification
    db.commit()
    configure(db, max_unreconciled_payouts=0)
    assert cs.fee_reconciled(cashouts(db, old)[0]) is False
    assert cs.reconciliation_exposure(db) == {"in_flight": 1, "completed_unreconciled": 1, "total": 2}
    third = paid_member(db, "m3", "9.00")
    assert run(db, provider_, now=NOW + timedelta(days=2))["stopped"] == "FEE_RECONCILIATION_PENDING"
    assert cashouts(db, third) == [] and cashouts(db, new)[0].status == "processing"


@pytest.mark.parametrize("limit, sent", [(0, 1), (1, 2), (2, 3), (5, 4)])
def test_the_configured_number_is_the_most_that_may_be_outstanding(strict, limit, sent):
    db = strict
    for index in range(4):
        paid_member(db, f"m{index}", "5.00")
    configure(db, max_unreconciled_payouts=limit)
    provider_ = RichProvider()
    report = run(db, provider_)
    assert report["members"].get("SUBMITTED") == sent and len(provider_.created) == sent
    assert cs.reconciliation_exposure(db)["in_flight"] == sent
    for hour in range(1, 3):                                       # and no retry sends one more
        run(db, provider_, now=NOW + timedelta(hours=hour))
    assert len(provider_.created) == sent


def test_usd_cashouts_and_company_paid_rows_are_not_part_of_the_gate(strict):
    db = strict
    usd = member(db, "u1", method="USD")
    commission(db, usd, "150.00")
    configure(db, usd_destination_required=False)
    cs.request_usd_cashout(db, usd, now=NOW)
    assert cs.reconciliation_exposure(db)["total"] == 0
    assert run(db, RichProvider())["members"] == {}                # nobody to pay, nothing blocked


# ===========================================================================
# 3. Safety margin on the estimate
# ===========================================================================

@pytest.mark.parametrize("estimate, margin, adjusted", [
    ("0.3", "0", "0.3"),
    ("0.3", "50", "0.45"),
    ("0.4", "25", "0.5"),
    ("0.33333333", "10", "0.36666667"),        # 0.366666663 is rounded UP at the provider's precision
    ("0.00000001", "1", "0.00000002"),         # never rounded down to the estimate itself
    ("0.1", "0.001", "0.100001"),
    ("1.23456789", "500", "7.40740734"),
    ("0", "50", "0"),
])
def test_the_adjusted_estimate_is_exact_decimal_arithmetic_rounded_up(estimate, margin, adjusted):
    result = cs.adjusted_estimate(Decimal(estimate), Decimal(margin))
    assert isinstance(result, Decimal) and result == Decimal(adjusted)
    assert result >= Decimal(estimate)                             # a margin never lowers the estimate
    assert result == result.quantize(Decimal("0.00000001"))


@pytest.mark.parametrize("margin", [None, Decimal("-1"), Decimal("NaN")])
def test_without_a_usable_margin_there_is_no_adjusted_estimate(margin):
    with pytest.raises(cs.CashoutError) as error:
        cs.adjusted_estimate(Decimal("0.3"), margin)
    assert error.value.code == "FEE_SAFETY_MARGIN_NOT_SET"


def test_the_margin_is_not_set_by_default_and_then_no_payout_is_created(books, engine_on):
    db = books
    user = paid_member(db)
    assert pc.default_config().fee_estimate_margin_percent is None
    configure(db, fee_estimate_margin_percent=None)
    assert pc.load(db).fee_gate() == "FEE_SAFETY_MARGIN_NOT_SET"
    provider_ = RichProvider()
    assert run(db, provider_) == {"enabled": True, "reconciled": {}, "members": {},
                                  "stopped": "FEE_SAFETY_MARGIN_NOT_SET"}
    assert provider_.created == [] and get_commission_balance(db, user.id).available == Decimal("5.00")
    assert cs.summary(db, user, now=NOW)["fees"]["CRYPTO"]["terms"]["available"] is False


@pytest.mark.parametrize("estimate, margin, code", [
    ("0.40", "25", "SUBMITTED"),                                   # 0.40 x 1.25 = 0.50, exactly the 10% limit
    ("0.40", "25.001", "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),          # 0.500004
    ("0.40", "0", "SUBMITTED"),
    ("0.50", "0", "SUBMITTED"),
    ("0.50", "0.001", "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),
    ("0.10", "400", "SUBMITTED"),                                  # 0.50
    ("0.10", "401", "NETWORK_FEE_ABOVE_MEMBER_LIMIT"),
])
def test_the_adjusted_estimate_not_the_estimate_is_checked_against_the_members_limit(books, engine_on, estimate,
                                                                                    margin, code):
    db = books
    user = paid_member(db)                                         # 5.00: the limit is 10% = 0.50
    configure(db, fee_estimate_margin_percent=Decimal(margin))
    provider_ = RichProvider(fee=estimate)
    assert run(db, provider_)["members"] == {code: 1}
    if code != "SUBMITTED":
        assert provider_.created == [] and cashouts(db) == []
        assert get_commission_balance(db, user.id).available == Decimal("5.00")
        return
    # The margin changes what is CHECKED, never what is sent: the whole amount, once.
    assert [c["amount"] for c in provider_.created] == [Decimal("5.00")]
    row = cashouts(db, user)[0]
    adjusted = cs.adjusted_estimate(Decimal(estimate), Decimal(margin))
    assert (row.amount_sent, row.network_fee_estimate, row.fee_estimate_adjusted, row.fee_margin_percent) == (
        Decimal("5.00"), Decimal(estimate), adjusted, Decimal(margin))
    assert row.network_fee_actual is None                          # three figures, and the actual one is not known
    assert row.net_amount == Decimal("5.00") - Decimal(estimate).quantize(Decimal("0.01"))
    view = cs.cashout_dict(row)["beneficiary_fee"]
    assert view["actual"] is None and Decimal(view["estimate_adjusted"]) == adjusted
    assert Decimal(view["estimate"]) == Decimal(estimate)


@pytest.mark.parametrize("estimate, margin, minimum, code", [
    ("0.25", "50", "4.70", "BELOW_MINIMUM_RECEIVED"),              # 5.00 - 0.375 = 4.625
    ("0.25", "0", "4.70", "SUBMITTED"),                            # 4.75
    ("0.20", "50", "4.70", "SUBMITTED"),                           # exactly 4.70
    ("0.20", "50.001", "4.70", "BELOW_MINIMUM_RECEIVED"),
])
def test_the_minimum_amount_received_is_checked_with_the_adjusted_estimate(books, engine_on, estimate, margin,
                                                                           minimum, code):
    db = books
    paid_member(db)
    configure(db, fee_estimate_margin_percent=Decimal(margin), min_net_payout_usd=Decimal(minimum))
    provider_ = RichProvider(fee=estimate)
    assert run(db, provider_)["members"] == {code: 1}
    assert [c["amount"] for c in provider_.created] == ([Decimal("5.00")] if code == "SUBMITTED" else [])


def test_the_companys_own_fee_limit_and_the_provider_balance_use_the_adjusted_estimate(books, engine_on):
    db = books
    paid_member(db)
    configure(db, fee_estimate_margin_percent=Decimal("100"), max_network_fee_percent=Decimal("5"))
    assert run(db, RichProvider(fee="0.20"))["members"] == {"NETWORK_FEE_TOO_HIGH": 1}        # 0.40 > 5% of 5.00
    configure(db, max_network_fee_percent=Decimal("25"))
    assert run(db, RichProvider(fee="0.20", balance="5.39"))["members"] == {"INSUFFICIENT_PROVIDER_BALANCE": 1}
    assert run(db, RichProvider(fee="0.20", balance="5.40"))["members"] == {"SUBMITTED": 1}


@pytest.mark.parametrize("value", ["-1", "-0.001", "500.001", "501", "1.2345", "abc", "NaN", "1e3", True])
def test_an_invalid_margin_is_refused(db, value):
    admin = member(db, "boss", admin=True)
    with pytest.raises(pc.PaymentConfigError) as error:
        pc.update_settings(db, admin, {"fee_estimate_margin_percent": value}, password=PASSWORD, now=NOW)
    assert error.value.code == "INVALID_VALUE" and error.value.field == "fee_estimate_margin_percent"
    assert pc.load(db).fee_estimate_margin_percent is None


@pytest.mark.parametrize("value, stored", [("0", "0"), ("12.5", "12.5"), ("0.001", "0.001"), ("500", "500")])
def test_a_valid_margin_is_stored_exactly_and_can_be_cleared_again(db, value, stored):
    admin = member(db, "boss", admin=True)
    config = pc.update_settings(db, admin, {"fee_estimate_margin_percent": value}, password=PASSWORD, now=NOW)
    assert isinstance(config.fee_estimate_margin_percent, Decimal)
    assert config.fee_estimate_margin_percent == Decimal(stored)
    config = pc.update_settings(db, admin, {"fee_estimate_margin_percent": ""}, password=PASSWORD, now=NOW)
    assert config.fee_estimate_margin_percent is None and config.fee_gate() is not None      # cleared = no payout


@pytest.mark.parametrize("change", [{"fee_estimate_margin_percent": "20"}, {"fee_estimate_margin_percent": ""},
                                    {"max_unreconciled_payouts": 3}])
def test_changing_the_margin_or_the_gate_withdraws_the_approval(books, engine_on, change):
    db = books
    admin = member(db, "boss", admin=True)
    assert pc.load(db).fee_terms_approved is True
    config = pc.update_settings(db, admin, change, password=PASSWORD, now=NOW)
    assert config.fee_terms_approved is False and config.fee_gate() is not None
    last = db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first()
    assert set(last.changed_fields) == {*change, "fee_terms_approved"}
    with pytest.raises(pc.PaymentConfigError) as error:            # and both cannot arrive in one change
        pc.update_settings(db, admin, {**{k: "30" if "margin" in k else 4 for k in change}, "fee_terms_approved": True},
                           password=PASSWORD, now=NOW, confirmation=pc.CONFIRM_FEE_LIMITS)
    assert error.value.code == "UNSAFE_ACTIVATION"


@pytest.mark.parametrize("value", [-1, 1001, "1.5", "abc", ""])
def test_an_invalid_gate_limit_is_refused(db, value):
    admin = member(db, "boss", admin=True)
    with pytest.raises(pc.PaymentConfigError) as error:
        pc.update_settings(db, admin, {"max_unreconciled_payouts": value}, password=PASSWORD, now=NOW)
    assert error.value.code == "INVALID_VALUE" and pc.load(db).max_unreconciled_payouts == 0


# ===========================================================================
# 4. Suspension and reactivation
# ===========================================================================

@pytest.mark.parametrize("details, reason", [
    (dict(fee="0.25", paid_by="sender"), "PROVIDER_FEE_MODE_MISMATCH"),             # the fee was charged to MyHigh5
    (dict(fee=None, paid_by="sender"), "PROVIDER_FEE_MODE_MISMATCH"),
    (dict(fee="0.02", paid_by="receiver", amount="5.02"), "PROVIDER_AMOUNT_MISMATCH"),   # more left than was sent
    (dict(fee="0.02", paid_by="receiver", amount="4.50"), "PROVIDER_AMOUNT_MISMATCH"),   # not what `amount` means
    (dict(fee="0.75", paid_by="receiver"), "FEE_CAP_EXCEEDED"),                     # above the member's limit
])
def test_every_confirmed_inconsistency_suspends_payouts_and_keeps_the_reason(strict, payers_confirmed, details,
                                                                             reason):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider(fee="0.40")
    run(db, provider_)
    report = finish(db, provider_, **details)
    row = cashouts(db, first)[0]
    assert report["stopped"] == "PAYOUTS_SUSPENDED" and suspension(db) == (reason, row.id)
    config = pc.load(db)
    # The provider did not behave as configured: its behaviour is un-confirmed and the approval withdrawn.
    assert (config.fee_gate(), config.provider_fee_mode, config.fee_terms_approved) == (
        "PAYOUTS_SUSPENDED", "UNVERIFIED", False)
    event = db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").one()
    assert (event.new_values["reason"], event.new_values["cashout_id"], event.actor_id) == (reason, row.id, None)
    assert len(provider_.created) == 1 and cashouts(db, second) == []
    assert ("PAYOUTS_SUSPENDED", "critical") in discrepancy_types(db)
    # Looking again changes nothing and records nothing twice.
    for hour in range(1, 4):
        assert run(db, provider_, now=NOW + timedelta(hours=hour))["stopped"] == "PAYOUTS_SUSPENDED"
        engine.reconcile_cashout(db, row.id, provider_, now=NOW + timedelta(hours=hour))
    assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").count() == 1
    assert db.query(JournalEntry).count() == 1 and len(provider_.created) == 1


def test_a_fee_recorded_afterwards_never_lifts_a_suspension(strict, payers_confirmed):
    """The provider charged MyHigh5, without saying how much. An administrator
    then records the verified fee: the payout is reconciled, the temporary gate
    is satisfied, and payouts stay suspended all the same."""
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_, fee=None, paid_by="sender")
    row = cashouts(db, first)[0]
    assert suspension(db) == ("PROVIDER_FEE_MODE_MISMATCH", row.id) and cs.fee_reconciled(row) is False
    verify(db, row, admin, fee="0.25", charged_to="PROVIDER_BALANCE", received="5.00")
    row = cashouts(db, first)[0]
    assert cs.fee_reconciled(row) is True and cs.reconciliation_exposure(db)["total"] == 0
    assert cs.recording_gate(db, pc.load(db)) is None              # the gate has nothing left to wait for ...
    assert suspension(db) == ("PROVIDER_FEE_MODE_MISMATCH", row.id)        # ... and the suspension is untouched
    restore_rules(db, admin)                                       # nor does putting the settings back
    later = NOW + timedelta(days=2)
    assert run(db, provider_, now=later) == {"enabled": True, "reconciled": {}, "members": {},
                                             "stopped": "PAYOUTS_SUSPENDED"}
    assert len(provider_.created) == 1 and cashouts(db, second) == []
    review(db, cashouts(db, first)[0], admin)                      # the flagged payout was looked at ...
    assert suspension(db) == ("PROVIDER_FEE_MODE_MISMATCH", row.id)        # ... which lifts nothing either
    reactivate(db, admin)                                          # only this does
    assert run(db, provider_, now=later)["members"] == {"SUBMITTED": 1}


def test_the_suspension_is_stored_and_survives_a_new_session_and_new_settings(strict, payers_confirmed, db):
    first = paid_member(strict, "m1")
    provider_ = RichProvider()
    run(strict, provider_)
    finish(strict, provider_, fee="0.25", paid_by="sender")
    row_id = cashouts(strict, first)[0].id
    stored = strict.query(PaymentSettings).one()
    assert (stored.payout_suspended_reason, stored.payout_suspended_cashout_id) == ("PROVIDER_FEE_MODE_MISMATCH",
                                                                                    row_id)
    assert stored.payout_suspended_at is not None
    strict.expire_all()
    view = pc.settings_view(strict)["payout_suspension"]
    assert (view["reason"], view["cashout_id"], view["rules_gate"]) == (
        "PROVIDER_FEE_MODE_MISMATCH", row_id, "PROVIDER_FEE_MODE_UNVERIFIED")
    assert "charged a network fee to the MyHigh5 balance" in view["message"]
    assert pc.settings_view(strict)["network_fee_gate"]["code"] == "PAYOUTS_SUSPENDED"


def test_restoring_the_fee_behaviour_and_the_approval_does_not_resume_payouts(strict, payers_confirmed):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_, fee="0.25", paid_by="sender")
    restore_rules(db, admin)
    config = pc.load(db)
    assert (config.provider_fee_mode, config.fee_terms_approved, config.fee_rules_gate()) == (
        "DEDUCTED_BY_PROVIDER", True, None)                        # everything is back as it was ...
    assert config.fee_gate() == "PAYOUTS_SUSPENDED" and suspension(db)[0] == "PROVIDER_FEE_MODE_MISMATCH"
    later = NOW + timedelta(days=2)
    assert run(db, provider_, now=later)["stopped"] == "PAYOUTS_SUSPENDED"              # ... and nothing is sent
    assert engine.process_member(db, second.id, provider_, now=later,
                                 facts={"balance": Decimal("1000"), "minimum": Decimal("0.10")}) == "PAYOUTS_SUSPENDED"
    assert len(provider_.created) == 1 and cashouts(db, second) == []
    assert cs.summary(db, second, now=later)["status"] == "AUTOMATIC_PAYOUT_NOT_ACTIVE"
    # Switching automatic payouts off and on again is no way around it either.
    configure(db, crypto_auto_payout_enabled=False)
    with pytest.raises(pc.PaymentConfigError) as error:
        pc.update_settings(db, admin, {"crypto_auto_payout_enabled": True}, password=PASSWORD, now=NOW,
                           confirmation=pc.CONFIRM_AUTO_PAYOUT)
    assert error.value.code == "UNSAFE_ACTIVATION" and "suspended" in str(error.value)


def test_reactivation_is_a_separate_deliberate_act(strict, payers_confirmed):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_, fee="0.25", paid_by="sender")            # recorded by the provider, flagged, unverified

    def refused(actor=admin, **overrides) -> str:
        with pytest.raises(pc.PaymentConfigError) as error:
            reactivate(db, actor, **overrides)
        assert suspension(db)[0] == "PROVIDER_FEE_MODE_MISMATCH"
        return error.value.code

    assert refused() == "UNSAFE_ACTIVATION"                        # the payout's fee is not verified yet
    verify(db, cashouts(db, first)[0], admin, fee="0.25", charged_to="PROVIDER_BALANCE", received="5.00")
    assert refused() == "UNSAFE_ACTIVATION"                        # the provider's behaviour is not confirmed again
    restore_rules(db, admin)
    assert refused() == "UNSAFE_ACTIVATION"                        # the flagged payout has not been reviewed
    review(db, cashouts(db, first)[0], admin)
    assert refused(plain_admin(db)) == "FORBIDDEN"                 # an administrator without the permission
    assert refused(first) == "FORBIDDEN"                           # a member
    assert refused(password="wrong") == "REAUTH_REQUIRED"
    assert refused(password="") == "REAUTH_REQUIRED"
    assert refused(confirmation="") == "CONFIRMATION_REQUIRED"
    assert refused(confirmation=pc.CONFIRM_AUTO_PAYOUT) == "CONFIRMATION_REQUIRED"      # another switch's phrase
    assert refused(note="") == "REVIEW_NOTE_REQUIRED"
    assert refused(note="looks fine") == "REVIEW_NOTE_REQUIRED"    # not a review
    assert refused(note="x" * 501) == "REVIEW_NOTE_REQUIRED"
    assert len(provider_.created) == 1

    before = pc.load(db)
    config = reactivate(db, admin)
    assert config.suspended_reason is None and config.fee_gate() is None
    # It lifted the suspension and changed nothing else.
    for name in ("provider_fee_mode", "fee_terms_approved", "crypto_auto_payout_enabled", "member_fee_cap_usd",
                 "fee_estimate_margin_percent", "max_unreconciled_payouts"):
        assert getattr(config, name) == getattr(before, name), name
    event = db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_REACTIVATED").one()
    assert event.actor_id == admin.id and event.new_values["review_note"] == NOTE
    assert event.old_values["payout_suspended_reason"] == "PROVIDER_FEE_MODE_MISMATCH"
    with pytest.raises(pc.PaymentConfigError) as error:            # once
        reactivate(db, admin)
    assert error.value.code == "NOT_SUSPENDED"
    assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_REACTIVATED").count() == 1
    assert run(db, provider_, now=NOW + timedelta(days=2))["members"] == {"SUBMITTED": 1}
    assert cashouts(db, second)[0].amount_sent == Decimal("7.00")


def test_reactivation_does_not_switch_automatic_payouts_on(strict, payers_confirmed):
    db = strict
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_, fee="0.25", paid_by="sender")
    verify(db, cashouts(db, user)[0], admin, fee="0.25", charged_to="PROVIDER_BALANCE", received="5.00")
    restore_rules(db, admin)
    review(db, cashouts(db, user)[0], admin)
    configure(db, crypto_auto_payout_enabled=False)                # an administrator paused payouts meanwhile
    config = reactivate(db, admin)
    assert config.suspended_reason is None
    assert config.crypto_auto_payout_enabled is False and config.auto_payout_allowed is False
    assert run(db, provider_, now=NOW + timedelta(days=2))["enabled"] is False


def test_the_first_finding_stays_the_one_to_review_and_only_an_inconsistency_can_suspend(books, engine_on):
    db = books
    assert pc.suspend_payouts(db, reason="FEE_CAP_EXCEEDED", cashout_id=3, now=NOW) is True
    db.commit()
    assert suspension(db) == ("FEE_CAP_EXCEEDED", 3) and pc.load(db).provider_fee_mode == "UNVERIFIED"
    assert pc.suspend_payouts(db, reason="FEE_CAP_EXCEEDED", cashout_id=4, now=NOW) is False       # nothing new
    assert pc.suspend_payouts(db, reason="PROVIDER_FEE_MODE_MISMATCH", cashout_id=5, now=NOW) is False
    db.commit()
    assert suspension(db) == ("FEE_CAP_EXCEEDED", 3)               # the first finding stays in front
    assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_SUSPENDED").count() == 1
    assert set(pc.SUSPENSION_MESSAGES) == {"PROVIDER_FEE_MODE_MISMATCH", "PROVIDER_AMOUNT_MISMATCH",
                                           "FEE_CAP_EXCEEDED"}
    # A missing or unverified fee is the gate's business: it cannot be made a suspension at all.
    for not_a_reason in ("FEE_NOT_RECONCILED", "FEE_RECONCILIATION_PENDING", "BECAUSE", ""):
        with pytest.raises(ValueError):
            pc.suspend_payouts(db, reason=not_a_reason, cashout_id=None)
    db.rollback()
    assert suspension(db) == ("FEE_CAP_EXCEEDED", 3)


def test_a_verified_fee_above_the_members_limit_is_an_inconsistency_and_suspends(strict):
    db = strict
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    assert suspension(db) == (None, None)                          # only waiting for its fee so far
    verify(db, cashouts(db, user)[0], admin, fee="0.75")           # verified, and above the member's 0.50 limit
    row = cashouts(db, user)[0]
    assert (row.fee_flag, row.fee_reconciliation, row.net_received) == ("FEE_CAP_EXCEEDED", "ADMIN_VERIFIED",
                                                                       Decimal("4.25"))
    assert suspension(db) == ("FEE_CAP_EXCEEDED", row.id) and pc.load(db).provider_fee_mode == "UNVERIFIED"
    assert db.query(JournalEntry).count() == 1 and _balance(db, "5005") == 0       # nothing booked, nothing refunded


def test_members_can_still_accept_the_terms_while_the_gate_holds_payouts_back(strict):
    db = strict
    first = paid_member(db, "m1")
    late = member(db, "m2", method="CRYPTO", terms=False)
    commission(db, late, "7.00")
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    assert cs.recording_gate(db, pc.load(db)) == "FEE_RECONCILIATION_PENDING"
    assert cashouts(db, first)[0].status == "completed"
    cs.accept_fee_terms(db, late, version=1, cap_percent="10", cap_usd="1", now=NOW)
    summary = cs.summary(db, late, now=NOW)
    assert summary["fees"]["CRYPTO"]["terms"]["accepted"] is True
    assert run(db, provider_, now=NOW + timedelta(days=2))["stopped"] == "FEE_RECONCILIATION_PENDING"
    assert cashouts(db, late) == []                                # accepted, and still waiting its turn


# ===========================================================================
# 5. The administrator's endpoints
# ===========================================================================

def test_the_reactivation_endpoint_needs_the_permission_the_password_the_phrase_and_a_note(client, strict):
    db = strict
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    url = "/api/v1/admin/finance/payouts/reactivate"
    body = {"current_password": PASSWORD, "confirmation": pc.CONFIRM_REACTIVATION, "note": NOTE}
    waiting = client.post(url, headers=auth(admin), json=body)     # held by the gate only: nothing to reactivate
    assert waiting.status_code == 409 and waiting.json()["detail"]["code"] == "NOT_SUSPENDED"
    pc.suspend_payouts(db, reason="PROVIDER_AMOUNT_MISMATCH", cashout_id=cashouts(db, user)[0].id, now=NOW)
    db.commit()
    body = {"current_password": PASSWORD, "confirmation": pc.CONFIRM_REACTIVATION, "note": NOTE}
    assert client.post(url, json=body).status_code in (401, 403)
    assert client.post(url, headers=auth(user), json=body).status_code == 403
    assert client.post(url, headers=auth(plain_admin(db)), json=body).status_code == 403
    pending = client.post(url, headers=auth(admin), json=body)
    assert pending.status_code == 409 and pending.json()["detail"]["code"] == "UNSAFE_ACTIVATION"
    recorded = client.post(f"/api/v1/admin/cashouts/{cashouts(db, user)[0].id}/network-fee", headers=auth(admin),
                           json={"amount": "0.02", "reference": "payout batch-1", "charged_to": "PAYOUT_AMOUNT",
                                 "evidence": "BLOCKCHAIN_EXPLORER", "verified": True, "received": "4.98"})
    assert recorded.status_code == 200
    fee = recorded.json()["cashout"]["beneficiary_fee"]
    assert (fee["reconciliation"], fee["evidence"], fee["reconciled"]) == ("ADMIN_VERIFIED", "BLOCKCHAIN_EXPLORER", True)
    for wrong, status_code, code in (({"current_password": "wrong"}, 403, "REAUTH_REQUIRED"),
                                     ({"confirmation": "REACTIVATE"}, 409, "CONFIRMATION_REQUIRED"),
                                     ({"note": "ok"}, 409, "REVIEW_NOTE_REQUIRED")):
        answer = client.post(url, headers=auth(admin), json={**body, **wrong})
        assert (answer.status_code, answer.json()["detail"]["code"]) == (status_code, code)
    assert client.post(url, headers=auth(admin), json={**body, "extra": 1}).status_code == 422
    rules = client.post(url, headers=auth(admin), json=body)       # the fee behaviour is not confirmed again yet
    assert rules.status_code == 409 and rules.json()["detail"]["code"] == "UNSAFE_ACTIVATION"
    restore_rules(db, admin)
    assert suspension(db)[0] == "PROVIDER_AMOUNT_MISMATCH"
    answer = client.post(url, headers=auth(admin), json=body)
    assert answer.status_code == 200 and answer.json()["payout_suspension"] is None
    assert answer.json()["network_fee_gate"] is None
    assert answer.json()["confirmations"]["payout_reactivation"] == pc.CONFIRM_REACTIVATION
    again = client.post(url, headers=auth(admin), json=body)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "NOT_SUSPENDED"


@pytest.mark.parametrize("body, code", [
    ({"verified": True}, "RECEIVED_REQUIRED"),
    ({"verified": True, "received": "4.90"}, "AMOUNTS_DO_NOT_ADD_UP"),
    ({"verified": True, "received": "4.98", "evidence": "OTHER"}, "EVIDENCE_REQUIRED"),
    ({"evidence": "A_GUESS"}, "EVIDENCE_REQUIRED"),
    ({"evidence": None}, "EVIDENCE_REQUIRED"),
])
def test_the_fee_endpoint_refuses_a_verification_it_cannot_stand_behind(client, strict, body, code):
    db = strict
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    finish(db, provider_)
    answer = client.post(f"/api/v1/admin/cashouts/{cashouts(db, user)[0].id}/network-fee", headers=auth(admin),
                         json={"amount": "0.02", "reference": "payout batch-1", "charged_to": "PAYOUT_AMOUNT",
                               "evidence": "PROVIDER_STATEMENT", **body})
    assert answer.status_code == 422 and answer.json()["detail"]["code"] == code
    assert cashouts(db, user)[0].network_fee_actual is None


def test_the_settings_endpoint_stores_the_new_settings_for_an_authorised_administrator_only(client, db):
    admin = member(db, "boss", admin=True)
    url = "/api/v1/admin/finance/settings"
    change = {"changes": {"fee_estimate_margin_percent": "15.5", "max_unreconciled_payouts": 2},
              "current_password": PASSWORD}
    assert client.put(url, headers=auth(plain_admin(db)), json=change).status_code == 403
    assert client.put(url, headers=auth(admin), json={**change, "current_password": "wrong"}).status_code == 403
    bad = client.put(url, headers=auth(admin), json={"changes": {"fee_estimate_margin_percent": "600"},
                                                    "current_password": PASSWORD})
    assert bad.status_code == 422 and bad.json()["detail"]["field"] == "fee_estimate_margin_percent"
    answer = client.put(url, headers=auth(admin), json=change)
    assert answer.status_code == 200
    fields = {f["name"]: f for f in answer.json()["fields"]}
    assert Decimal(fields["fee_estimate_margin_percent"]["value"]) == Decimal("15.5")
    assert fields["max_unreconciled_payouts"]["value"] == 2
    assert (fields["fee_estimate_margin_percent"]["default"], fields["max_unreconciled_payouts"]["default"]) == (None, 0)
    assert fields["fee_estimate_margin_percent"]["approval_note"]          # not a decided value
    assert answer.json()["payout_suspension"] is None
    event = db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first()
    assert event.actor_id == admin.id and set(event.new_values) == {"fee_estimate_margin_percent",
                                                                    "max_unreconciled_payouts"}
    cleared = client.put(url, headers=auth(admin), json={"changes": {"fee_estimate_margin_percent": ""},
                                                        "current_password": PASSWORD})
    assert cleared.status_code == 200 and pc.load(db).fee_estimate_margin_percent is None
