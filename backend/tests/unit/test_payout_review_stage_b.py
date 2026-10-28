"""Crypto payouts: stale configuration, flagged payout review, admin status (Phase 3.3 B).

* A cycle never pays under values that are no longer in force. If the
  configuration changes while a cycle is running (even if it is changed and
  approved again), nothing more is reserved, a reservation not yet handed to
  the provider is released, and the cycle stops.
* An approval or an activation must name the configuration version the
  administrator was shown, so nobody approves values they did not see.
* A flagged payout is reviewed by an administrator: who, when, and a written
  note. The review is a record and nothing else: it changes no amount, no
  journal entry, no flag, no reconciliation; it lifts no suspension, does not
  pass the recording gate and allows no payout.
* The Admin Panel is told EVERYTHING that stops a payout, not just the first
  reason, and never something the engine would not also decide.

The provider is a fake object; every member, commission, fee, limit and margin
is SYNTHETIC. No value used here is a policy.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission
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
    books,
    discrepancy_types,
    finish,
    payers_confirmed,
)
from tests.unit.test_dual_cashout import (  # noqa: F401
    FEE_RULES,
    NOW,
    PASSWORD,
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
from tests.unit.test_new_business_model import _assert_all_journals_balance, world  # noqa: F401
from tests.unit.test_nowpayments_integration import RichProvider, paid_member, provider  # noqa: F401
from tests.unit.test_payment_config import plain_admin
from tests.unit.test_payout_fee_safety import NOTE, reactivate, restore_rules, strict, suspension, verify  # noqa: F401

pytestmark = pytest.mark.unit

FOUND = "Compared payout batch-1 with the provider statement: the fee was charged to our balance."


class ChangingProvider(RichProvider):
    """A provider during whose FIRST fee estimate something else happens (an
    administrator saves a setting): the estimate is asked for after the cycle
    read its configuration and before anything is reserved."""

    def __init__(self, meanwhile, **kwargs):
        super().__init__(**kwargs)
        self._meanwhile, self.estimates = meanwhile, 0

    def network_fee(self, currency, amount):
        self.estimates += 1
        if self.estimates == 1:
            self._meanwhile()
        return super().network_fee(currency, amount)


def save(db, admin, changes, **kwargs):
    return pc.update_settings(db, admin, changes, password=PASSWORD, now=NOW, **kwargs)


def approve(db, admin):
    return save(db, admin, {"fee_terms_approved": True}, confirmation=pc.CONFIRM_FEE_LIMITS,
                expected_version=pc.load(db).version)


def review(db, row, admin, **overrides):
    return cs.review_fee_exception(db, row, admin=admin, now=NOW, **{"password": PASSWORD, "note": FOUND, **overrides})


def flagged_payout(db, *, fee="0.25", paid_by="sender", name="m1", **finished):
    """One completed payout that the provider's report flagged. By default the
    provider says it charged the fee to MyHigh5 (a confirmed inconsistency)."""
    user = paid_member(db, name)
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}
    finish(db, provider_, fee=fee, paid_by=paid_by, **finished)
    return user, cashouts(db, user)[0], provider_


_KEPT = ("gross_amount", "fee", "net_amount", "status", "amount_sent", "network_fee", "network_fee_estimate",
         "fee_estimate_adjusted", "network_fee_actual", "net_received", "network_fee_source", "fee_cap", "fee_flag",
         "fee_reconciliation", "fee_evidence", "settlement_reference", "payout_reference", "processed_at",
         "reviewed_by", "reviewed_at", "provider_batch_id", "provider_status", "failure_code")


def everything_else(db, row_id: int) -> dict:
    """Whatever a review must leave exactly as it is."""
    db.expire_all()
    row = db.get(AffiliateCashoutRequest, row_id)
    stored = db.query(PaymentSettings).one()
    return {
        "cashout": {name: getattr(row, name) for name in _KEPT},
        "journal": [(e.id, e.description) for e in db.query(JournalEntry).order_by(JournalEntry.id).all()],
        "commissions": [(c.id, c.status, c.payout_reference, c.commission_amount)
                        for c in db.query(AffiliateCommission).order_by(AffiliateCommission.id).all()],
        "settings": (stored.version, stored.payout_suspended_reason, stored.payout_suspended_cashout_id,
                     stored.provider_fee_mode, stored.fee_terms_approved, stored.crypto_auto_payout_enabled),
        "configuration_events": db.query(PaymentConfigAudit).count(),
        "exposure": cs.reconciliation_exposure(db),
    }


# ===========================================================================
# 1. A cycle never pays under values that are no longer in force
# ===========================================================================

def test_a_limit_changed_and_approved_again_during_a_cycle_stops_the_payout(books, engine_on):
    """The same-cycle risk: the limits are changed AND approved again while a
    cycle is running. Every gate is open again, so only the configuration
    version tells that the cycle checked this payout against other values."""
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)

    def meanwhile():
        save(db, admin, {"member_fee_cap_usd": "0.01"})            # the approval is withdrawn by this ...
        approve(db, admin)                                         # ... and given again, for the new limit

    provider_ = ChangingProvider(meanwhile)                        # its estimate (0.02) is above the new limit
    report = run(db, provider_)
    assert pc.load(db).fee_gate() is None                          # nothing else would have stopped it
    assert report["members"] == {"CONFIGURATION_CHANGED": 1} and report["stopped"] == "CONFIGURATION_CHANGED"
    assert provider_.created == [] and cashouts(db, user) == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")
    # The next cycle starts from the new configuration and applies the new limit.
    assert run(db, provider_)["members"] == {"NETWORK_FEE_ABOVE_MEMBER_LIMIT": 1}
    assert provider_.created == []


def test_a_setting_that_needs_no_new_approval_is_not_a_way_around_it(books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = ChangingProvider(lambda: save(db, admin, {"max_single_payout_usd": "2.00", "crypto_min_usd": "1.00"}))
    report = run(db, provider_)
    assert pc.load(db).fee_terms_approved is True                  # the approval was not touched by that change
    assert report["members"] == {"CONFIGURATION_CHANGED": 1} and provider_.created == []
    assert cashouts(db, user) == []
    assert run(db, provider_)["members"] == {"EXCEEDS_SINGLE_LIMIT": 1}


def test_the_rest_of_the_cycle_is_not_paid_under_the_old_values_either(books, engine_on):
    db = books
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    provider_ = ChangingProvider(lambda: save(db, admin, {"retry_backoff_hours": 48}))
    report = run(db, provider_)
    assert report["members"] == {"CONFIGURATION_CHANGED": 1} and report["stopped"] == "CONFIGURATION_CHANGED"
    assert provider_.estimates == 1 and provider_.created == []    # the second member was not even looked at
    assert cashouts(db, first) == [] and cashouts(db, second) == []
    assert run(db, provider_)["members"] == {"SUBMITTED": 2}       # nothing was lost: the next cycle pays both


def test_a_change_after_the_reservation_releases_it_before_anything_is_sent(books, engine_on, monkeypatch):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    reserve = cs.reserve

    def reserve_then_change(*args, **kwargs):
        cashout = reserve(*args, **kwargs)
        save(db, admin, {"retry_backoff_hours": 48})               # saved between the reservation and the hand-over
        return cashout

    monkeypatch.setattr(cs, "reserve", reserve_then_change)
    provider_ = RichProvider()
    report = run(db, provider_)
    assert report["members"] == {"CONFIGURATION_CHANGED": 1} and report["stopped"] == "CONFIGURATION_CHANGED"
    assert provider_.created == []                                 # the provider was never asked to send
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code, row.provider_batch_id) == ("cancelled", "CONFIGURATION_CHANGED", None)
    assert get_commission_balance(db, user.id).available == Decimal("5.00")
    assert get_commission_balance(db, user.id).reserved == Decimal("0.00")
    released = db.query(AuditTrail).filter_by(action="CASHOUT_RELEASED", record_id=row.id).one()
    assert released.new_values["failure_code"] == "CONFIGURATION_CHANGED"
    # Not a failed attempt of the member's: the next cycle pays them.
    monkeypatch.setattr(cs, "reserve", reserve)
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}


def test_a_suspension_during_a_cycle_is_reported_as_the_suspension(books, engine_on):
    """A suspension also changes the configuration version; the more telling
    reason is the one reported, and nothing is paid either way."""
    db = books
    user = paid_member(db)

    def meanwhile():
        pc.suspend_payouts(db, reason="PROVIDER_AMOUNT_MISMATCH", cashout_id=None, now=NOW)
        db.commit()

    provider_ = ChangingProvider(meanwhile)
    report = run(db, provider_)
    assert report["members"] == {"PAYOUTS_SUSPENDED": 1} and report["stopped"] == "PAYOUTS_SUSPENDED"
    assert provider_.created == [] and cashouts(db, user) == []


def test_an_unchanged_configuration_pays_as_before_and_the_version_is_on_record(books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    save(db, admin, {"retry_backoff_hours": 48})                   # version 1, before the cycle
    provider_ = RichProvider()
    assert run(db, provider_)["members"] == {"SUBMITTED": 1}
    row = cashouts(db, user)[0]
    assert row.status == "processing" and row.amount_sent == Decimal("5.00")
    reserved = db.query(AuditTrail).filter_by(action="CASHOUT_RESERVED", record_id=row.id).one()
    assert reserved.new_values["settings_version"] == pc.load(db).version == 1


def test_a_member_processed_on_its_own_reads_the_configuration_in_force(books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    save(db, admin, {"retry_backoff_hours": 48})
    facts = {"balance": Decimal("1000"), "minimum": Decimal("0.10")}
    assert engine.process_member(db, user.id, RichProvider(), now=NOW, facts=facts) == "SUBMITTED"


# ===========================================================================
# 2. Nobody approves values they were not shown
# ===========================================================================

def test_a_change_decided_on_an_older_configuration_is_refused(books):
    db = books
    first, second = member(db, "boss", admin=True), member(db, "second", admin=True)
    configure(db, **{**FEE_RULES, "fee_terms_approved": False})
    shown = pc.settings_view(db)["version"]                        # what the first administrator is looking at
    save(db, second, {"member_fee_cap_usd": "50.00"})              # meanwhile somebody else raises the limit
    with pytest.raises(pc.PaymentConfigError) as error:
        save(db, first, {"fee_terms_approved": True}, confirmation=pc.CONFIRM_FEE_LIMITS, expected_version=shown)
    assert error.value.code == "STALE_CONFIGURATION"
    config = pc.load(db)
    assert config.fee_terms_approved is False and config.version == shown + 1      # nothing was stored
    assert db.query(PaymentConfigAudit).filter_by(action="SETTINGS_UPDATED").count() == 1
    # Shown the values in force, the same administrator can approve them.
    assert save(db, first, {"fee_terms_approved": True}, confirmation=pc.CONFIRM_FEE_LIMITS,
                expected_version=pc.settings_view(db)["version"]).fee_terms_approved is True


@pytest.mark.parametrize("change, confirmation", [
    ({"fee_terms_approved": True}, pc.CONFIRM_FEE_LIMITS),
    ({"provider_fee_mode": "DEDUCTED_BY_PROVIDER"}, pc.CONFIRM_FEE_MODE),
])
def test_an_approval_or_a_confirmation_must_name_the_version_it_was_decided_on(books, change, confirmation):
    db = books
    admin = member(db, "boss", admin=True)
    start = {**FEE_RULES, "fee_terms_approved": False}
    if "provider_fee_mode" in change:
        start["provider_fee_mode"] = "UNVERIFIED"
    configure(db, **start)
    with pytest.raises(pc.PaymentConfigError) as error:
        save(db, admin, change, confirmation=confirmation)
    assert error.value.code == "VERSION_REQUIRED"
    for name, value in change.items():
        assert getattr(pc.load(db), name) != value
    assert db.query(PaymentConfigAudit).count() == 0
    save(db, admin, change, confirmation=confirmation, expected_version=pc.load(db).version)
    for name, value in change.items():
        assert getattr(pc.load(db), name) == value


def test_an_ordinary_change_may_name_its_version_and_is_then_held_to_it(books):
    db = books
    admin = member(db, "boss", admin=True)
    assert save(db, admin, {"retry_backoff_hours": 48}).version == 1               # without a version: as before
    with pytest.raises(pc.PaymentConfigError) as error:
        save(db, admin, {"retry_backoff_hours": 12}, expected_version=0)
    assert error.value.code == "STALE_CONFIGURATION" and pc.load(db).retry_backoff_hours == 48
    assert save(db, admin, {"retry_backoff_hours": 12}, expected_version=1).retry_backoff_hours == 12


def test_the_settings_endpoint_refuses_a_change_made_on_an_older_page(client, books):
    db = books
    admin = member(db, "boss", admin=True)
    url = "/api/v1/admin/finance/settings"
    shown = client.get(url, headers=auth(admin)).json()["version"]
    save(db, admin, {"retry_backoff_hours": 48})
    stale = client.put(url, headers=auth(admin), json={"changes": {"retry_backoff_hours": 12},
                                                       "current_password": PASSWORD, "expected_version": shown})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE_CONFIGURATION"
    assert pc.load(db).retry_backoff_hours == 48
    fresh = client.put(url, headers=auth(admin), json={"changes": {"retry_backoff_hours": 12},
                                                       "current_password": PASSWORD, "expected_version": shown + 1})
    assert fresh.status_code == 200 and fresh.json()["version"] == shown + 2
    assert client.put(url, headers=auth(admin), json={"changes": {"retry_backoff_hours": 6},
                                                      "current_password": PASSWORD,
                                                      "expected_version": -1}).status_code == 422


# ===========================================================================
# 3. Review of a flagged payout
# ===========================================================================

def test_a_review_records_who_when_and_what_was_found_and_changes_nothing_else(strict, payers_confirmed):
    db = strict
    user, row, _provider = flagged_payout(db)
    admin = member(db, "boss", admin=True)
    assert (row.fee_flag, cs.fee_review_state(row)) == ("PROVIDER_FEE_MODE_MISMATCH", "PENDING")
    assert cs.unreviewed_flagged_count(db) == 1
    before = everything_else(db, row.id)
    events = db.query(AuditTrail).count()

    reviewed = review(db, row, admin, ip="203.0.113.7")
    assert (reviewed.fee_review_flag, reviewed.fee_reviewed_by, reviewed.fee_reviewed_at, reviewed.fee_review_note) == (
        "PROVIDER_FEE_MODE_MISMATCH", admin.id, NOW, FOUND)
    assert cs.fee_review_state(reviewed) == "REVIEWED" and cs.unreviewed_flagged_count(db) == 0
    # The original payout, its accounting, the configuration and the gate are exactly as they were.
    assert everything_else(db, row.id) == before
    _assert_all_journals_balance(db)
    # One audit event, by that administrator.
    assert db.query(AuditTrail).count() == events + 1
    event = db.query(AuditTrail).filter_by(action="CASHOUT_FEE_EXCEPTION_REVIEWED", record_id=row.id).one()
    assert (event.user_id, event.ip_address, event.table_name) == (admin.id, "203.0.113.7", "affiliate_cashout_requests")
    assert event.old_values is None
    assert (event.new_values["flag"], event.new_values["note"], event.new_values["effect"]) == (
        "PROVIDER_FEE_MODE_MISMATCH", FOUND, "RECORD_ONLY")
    assert event.new_values["payouts_suspended"] is True and event.new_values["fee_reconciled"] is False
    view = cs.fee_review_view(reviewed)
    assert (view["state"], view["reviewed_by"], view["note"], view["superseded"]) == ("REVIEWED", admin.id, FOUND, False)
    assert user.id == reviewed.user_id


def test_a_review_does_not_lift_the_suspension_or_allow_a_payout(strict, payers_confirmed):
    db = strict
    _user, row, provider_ = flagged_payout(db)
    second = paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    assert suspension(db) == ("PROVIDER_FEE_MODE_MISMATCH", row.id)
    review(db, row, admin)
    assert suspension(db) == ("PROVIDER_FEE_MODE_MISMATCH", row.id)        # still suspended
    config = pc.load(db)
    assert (config.fee_gate(), config.provider_fee_mode, config.fee_terms_approved) == (
        "PAYOUTS_SUSPENDED", "UNVERIFIED", False)                          # nothing was restored by it either
    for day in range(1, 4):
        again = run(db, provider_, now=NOW + timedelta(days=day))
        assert again["stopped"] == "PAYOUTS_SUSPENDED" and again["members"] == {}
    assert len(provider_.created) == 1 and cashouts(db, second) == []
    assert db.query(PaymentConfigAudit).filter_by(action="PAYOUTS_REACTIVATED").count() == 0
    # Reactivation is still its own act, with its own conditions.
    with pytest.raises(pc.PaymentConfigError) as error:
        reactivate(db, admin)
    assert error.value.code == "UNSAFE_ACTIVATION" and suspension(db)[0] == "PROVIDER_FEE_MODE_MISMATCH"


def test_a_review_does_not_pass_the_recording_gate(strict, payers_confirmed):
    """The payout is reviewed, the suspension is lifted properly afterwards,
    and still no payout is created: the actual fee was never verified."""
    db = strict
    _user, row, provider_ = flagged_payout(db, fee=None, amount="9.00", paid_by=None)   # more left than was asked for
    second = paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    assert (row.fee_flag, row.network_fee_actual, cs.fee_reconciled(row)) == ("PROVIDER_AMOUNT_MISMATCH", None, False)
    assert cs.recording_gate(db, pc.load(db)) == "FEE_RECONCILIATION_PENDING"
    review(db, row, admin)
    row = cashouts(db)[-1] if False else db.get(AffiliateCashoutRequest, row.id)
    assert (row.network_fee_actual, row.fee_reconciliation, cs.fee_reconciled(row)) == (None, None, False)
    assert cs.reconciliation_exposure(db) == {"in_flight": 0, "completed_unreconciled": 1, "total": 1}
    assert cs.recording_gate(db, pc.load(db)) == "FEE_RECONCILIATION_PENDING"
    restore_rules(db, admin)
    with pytest.raises(pc.PaymentConfigError) as error:            # reviewed, but its fee is not verified
        reactivate(db, admin)
    assert error.value.code == "UNSAFE_ACTIVATION" and "no verified actual network fee" in str(error.value)
    # Even with the suspension out of the way, the gate alone holds the next payout back.
    stored = db.query(PaymentSettings).one()
    stored.payout_suspended_reason = stored.payout_suspended_at = stored.payout_suspended_cashout_id = None
    db.commit()
    report = run(db, provider_, now=NOW + timedelta(days=2))
    assert report["stopped"] == "FEE_RECONCILIATION_PENDING" and report["members"] == {}
    assert len(provider_.created) == 1 and cashouts(db, second) == []


def test_reactivation_waits_for_the_review_and_the_review_alone_is_not_enough(strict, payers_confirmed):
    db = strict
    _user, row, provider_ = flagged_payout(db)
    second = paid_member(db, "m2", "7.00")
    admin = member(db, "boss", admin=True)
    verify(db, row, admin, fee="0.25", charged_to="PROVIDER_BALANCE", received="5.00")
    restore_rules(db, admin)
    with pytest.raises(pc.PaymentConfigError) as error:            # everything else is in place
        reactivate(db, admin)
    assert error.value.code == "UNSAFE_ACTIVATION" and "have not been reviewed" in str(error.value)
    assert suspension(db)[0] == "PROVIDER_FEE_MODE_MISMATCH"
    review(db, db.get(AffiliateCashoutRequest, row.id), admin)
    assert suspension(db)[0] == "PROVIDER_FEE_MODE_MISMATCH"       # the review did not do it
    assert run(db, provider_, now=NOW + timedelta(days=2))["stopped"] == "PAYOUTS_SUSPENDED"
    assert reactivate(db, admin).suspended_reason is None
    assert run(db, provider_, now=NOW + timedelta(days=2))["members"] == {"SUBMITTED": 1}
    assert cashouts(db, second)[0].amount_sent == Decimal("7.00")


def test_only_an_authorised_administrator_with_their_password_and_a_real_note_can_review(strict, payers_confirmed):
    db = strict
    user, row, _provider = flagged_payout(db)
    admin = member(db, "boss", admin=True)
    before = everything_else(db, row.id)

    def refused(actor=admin, **overrides) -> str:
        with pytest.raises(cs.CashoutError) as error:
            review(db, db.get(AffiliateCashoutRequest, row.id), actor, **overrides)
        return error.value.code

    assert refused(plain_admin(db)) == "FORBIDDEN"                 # an administrator without process_cashouts
    assert refused(user) == "FORBIDDEN"                            # the member themselves
    assert refused(password="wrong") == "REAUTH_REQUIRED"
    assert refused(password="") == "REAUTH_REQUIRED"
    assert refused(password=None) == "REAUTH_REQUIRED"
    for note in ("", None, "ok", "looked at it", "   reviewed    \n\t   ", "a" * 40, "ab " * 30, "x" * 501):
        assert refused(note=note) == "REVIEW_NOTE_REQUIRED", note
    row = db.get(AffiliateCashoutRequest, row.id)
    assert (row.fee_review_flag, row.fee_reviewed_by, row.fee_reviewed_at, row.fee_review_note) == (
        None, None, None, None)
    assert everything_else(db, row.id) == before
    assert db.query(AuditTrail).filter_by(action="CASHOUT_FEE_EXCEPTION_REVIEWED").count() == 0


def test_a_payout_that_is_not_flagged_cannot_be_reviewed(strict, payers_confirmed):
    db = strict
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    provider_ = RichProvider()
    run(db, provider_)
    in_flight = cashouts(db, user)[0]
    with pytest.raises(cs.CashoutError) as error:
        review(db, in_flight, admin)
    assert error.value.code == "NOT_FLAGGED"
    finish(db, provider_, fee="0.02", paid_by="receiver")          # it adds up: verified by the provider's report
    row = cashouts(db, user)[0]
    assert (row.fee_flag, cs.fee_reconciled(row), cs.fee_review_state(row)) == (None, True, "NOT_REQUIRED")
    with pytest.raises(cs.CashoutError) as error:
        review(db, row, admin)
    assert error.value.code == "NOT_FLAGGED" and db.get(AffiliateCashoutRequest, row.id).fee_reviewed_at is None


def test_a_review_is_recorded_once_and_is_never_replaced(strict, payers_confirmed):
    db = strict
    _user, row, _provider = flagged_payout(db)
    first, second = member(db, "boss", admin=True), member(db, "second", admin=True)
    review(db, row, first)
    recorded = everything_else(db, row.id)

    def stored():
        db.expire_all()
        current = db.get(AffiliateCashoutRequest, row.id)
        return current.fee_review_flag, current.fee_reviewed_by, current.fee_reviewed_at, current.fee_review_note

    kept = stored()
    # The same review sent again (a double click, a retry): accepted, nothing new recorded.
    again = cs.review_fee_exception(db, row, admin=first, password=PASSWORD, note=f"  {FOUND}  ",
                                    now=NOW + timedelta(hours=1))
    assert again.id == row.id and stored() == kept
    # A different note, or another administrator: refused, the record stands.
    for actor, note in ((first, "On second thought the provider was right about this payout."), (second, FOUND),
                        (second, "Reviewed independently by the second administrator on duty.")):
        with pytest.raises(cs.CashoutError) as error:
            review(db, db.get(AffiliateCashoutRequest, row.id), actor, note=note)
        assert error.value.code == "ALREADY_REVIEWED" and f"#{first.id}" in str(error.value)
    assert stored() == kept == ("PROVIDER_FEE_MODE_MISMATCH", first.id, NOW, FOUND)
    assert everything_else(db, row.id) == recorded
    assert db.query(AuditTrail).filter_by(action="CASHOUT_FEE_EXCEPTION_REVIEWED").count() == 1
    # The password is still asked for on a repeat: a review is never confirmed by a session alone.
    with pytest.raises(cs.CashoutError) as error:
        review(db, db.get(AffiliateCashoutRequest, row.id), first, password="wrong")
    assert error.value.code == "REAUTH_REQUIRED"


def test_a_payout_flagged_for_something_else_later_needs_a_new_review(strict, payers_confirmed):
    db = strict
    _user, row, _provider = flagged_payout(db, fee=None, amount="9.00", paid_by=None)
    first, second = member(db, "boss", admin=True), member(db, "second", admin=True)
    assert row.fee_flag == "PROVIDER_AMOUNT_MISMATCH"
    review(db, row, first)
    assert cs.unreviewed_flagged_count(db) == 0
    # The statement then shows that the provider also charged its fee to MyHigh5.
    verify(db, db.get(AffiliateCashoutRequest, row.id), first, fee="0.25", charged_to="PROVIDER_BALANCE",
           received="5.00")
    row = db.get(AffiliateCashoutRequest, row.id)
    assert row.fee_flag == "PROVIDER_FEE_MODE_MISMATCH"
    view = cs.fee_review_view(row)
    assert (view["state"], view["reviewed_flag"], view["superseded"]) == ("PENDING", "PROVIDER_AMOUNT_MISMATCH", True)
    assert cs.unreviewed_flagged_count(db) == 1                    # the earlier review does not cover the new finding
    later = "The fee charged to our balance is confirmed by the statement; accounting was informed."
    reviewed = cs.review_fee_exception(db, row, admin=second, password=PASSWORD, note=later,
                                       now=NOW + timedelta(hours=2))
    assert (reviewed.fee_review_flag, reviewed.fee_reviewed_by) == ("PROVIDER_FEE_MODE_MISMATCH", second.id)
    events = (db.query(AuditTrail).filter_by(action="CASHOUT_FEE_EXCEPTION_REVIEWED", record_id=row.id)
              .order_by(AuditTrail.id).all())
    assert [e.user_id for e in events] == [first.id, second.id]    # both reviews stay in the audit trail
    assert events[1].old_values["reviewed_flag"] == "PROVIDER_AMOUNT_MISMATCH"
    assert events[1].old_values["note"] == FOUND and events[1].old_values["reviewed_by"] == first.id


def test_the_list_shows_what_was_expected_what_happened_and_the_evidence(strict, payers_confirmed):
    db = strict
    user, row, _provider = flagged_payout(db, fee="0.75", paid_by="receiver")     # above the member's limit of 0.50
    admin = member(db, "boss", admin=True)
    assert (row.fee_flag, cs.fee_reconciled(row)) == ("FEE_CAP_EXCEEDED", True)
    listing = cs.fee_exceptions(db)
    assert (listing["total"], listing["flagged_count"], listing["pending_count"], listing["reviewed_count"]) == (
        1, 1, 1, 0)
    assert listing["payout_suspension"]["reason"] == "FEE_CAP_EXCEEDED"
    item = listing["items"][0]
    assert (item["cashout_id"], item["user_id"], item["username"], item["status"]) == (row.id, user.id, "m1",
                                                                                      "completed")
    assert (item["flag"], item["caused_suspension"]) == ("FEE_CAP_EXCEEDED", True)
    assert "higher than the limit the member accepted" in item["flag_message"]
    assert item["expected"] == {"amount_sent": "5", "network_fee_estimate": "0.02",
                                "network_fee_estimate_adjusted": "0.02", "fee_cap": "0.5", "received": "4.98"}
    assert item["actual"] == {"network_fee": "0.75", "received": "4.25", "fee_above_estimate": "0.73",
                              "fee_above_cap": "0.25", "received_difference": "-0.73"}
    assert item["evidence"] == {"source": "PROVIDER_REPORTED", "evidence": "PROVIDER_API",
                                "reconciliation": "PROVIDER_VERIFIED", "reconciled": True, "recorded": True}
    assert item["review"]["state"] == "PENDING" and item["provider_batch_id"] == "batch-1"
    assert item["destination"] and "..." in item["destination"]    # the wallet is masked
    assert cs.fee_exceptions(db, state="REVIEWED")["items"] == []
    assert [i["cashout_id"] for i in cs.fee_exceptions(db, state="PENDING")["items"]] == [row.id]

    review(db, row, admin)
    listing = cs.fee_exceptions(db)
    assert (listing["pending_count"], listing["reviewed_count"]) == (0, 1)
    assert listing["items"][0]["review"]["reviewed_by"] == admin.id
    assert cs.fee_exceptions(db, state="PENDING")["items"] == []
    assert [i["cashout_id"] for i in cs.fee_exceptions(db, state="REVIEWED")["items"]] == [row.id]
    actions = [e["action"] for e in cs.fee_exception_events(db, row.id)]
    assert actions == ["CASHOUT_RESERVED", "CASHOUT_COMPLETED", "CASHOUT_PROVIDER_EVIDENCE",
                       "CASHOUT_MEMBER_FEE_RECORDED", "CASHOUT_FEE_EXCEPTION_REVIEWED"]


def test_the_list_keeps_what_the_provider_reported_when_it_was_flagged(strict, payers_confirmed):
    db = strict
    _user, row, _provider = flagged_payout(db, fee=None, amount="9.00", paid_by=None)
    item = cs.fee_exceptions(db)["items"][0]
    assert item["flag"] == "PROVIDER_AMOUNT_MISMATCH"
    assert item["flag_details"] == {"amount_sent": "5", "provider_amount": "9"}
    assert item["evidence"] == {"source": None, "evidence": None, "reconciliation": None, "reconciled": False,
                                "recorded": False}
    assert item["actual"] == {"network_fee": None, "received": None, "fee_above_estimate": None,
                              "fee_above_cap": None, "received_difference": None}


def test_the_reports_say_whether_a_flagged_payout_was_reviewed(strict, payers_confirmed):
    db = strict
    _user, row, _provider = flagged_payout(db)
    admin = member(db, "boss", admin=True)

    def flagged_line():
        report = engine.reconciliation_report(db, now=NOW)
        line = next(d for d in report["discrepancies"] if d["type"] == "PROVIDER_FEE_MODE_MISMATCH")
        return line, report["beneficiary_fees"]

    line, fees = flagged_line()
    assert line["review"] == "PENDING" and line["message"].endswith("Not reviewed yet (Flagged Payout Review).")
    assert fees["flagged_unreviewed_count"] == 1 and fees["flagged"][0]["review"] == "PENDING"
    assert cs.cashout_dict(row, admin=True)["fee_review"]["state"] == "PENDING"
    assert "fee_review" not in cs.cashout_dict(row)                # nothing about the review is shown to the member
    review(db, row, admin)
    line, fees = flagged_line()
    assert line["review"] == "REVIEWED" and "Not reviewed yet" not in line["message"]
    assert line["severity"] == "critical"                          # reviewed, not resolved: it stays listed
    assert fees["flagged_unreviewed_count"] == 0 and len(fees["flagged"]) == 1


def test_the_review_endpoint_needs_the_permission_the_password_and_a_note(client, strict, payers_confirmed):
    db = strict
    user, row, _provider = flagged_payout(db)
    admin, second = member(db, "boss", admin=True), member(db, "second", admin=True)
    url = f"/api/v1/admin/cashouts/{row.id}/fee-review"
    body = {"note": FOUND, "current_password": PASSWORD}
    assert client.post(url, json=body).status_code in (401, 403)
    assert client.post(url, headers=auth(user), json=body).status_code == 403
    assert client.post(url, headers=auth(plain_admin(db)), json=body).status_code == 403
    for wrong, status_code, code in (({"current_password": "wrong"}, 403, "REAUTH_REQUIRED"),
                                     ({"current_password": ""}, 403, "REAUTH_REQUIRED"),
                                     ({"note": "fine"}, 422, "REVIEW_NOTE_REQUIRED"),
                                     ({"note": ""}, 422, "REVIEW_NOTE_REQUIRED")):
        answer = client.post(url, headers=auth(admin), json={**body, **wrong})
        assert (answer.status_code, answer.json()["detail"]["code"]) == (status_code, code), wrong
    assert client.post(url, headers=auth(admin), json={**body, "extra": 1}).status_code == 422
    assert client.post(url, headers=auth(admin), json={**body, "note": "x" * 501}).status_code == 422
    assert client.post("/api/v1/admin/cashouts/999999/fee-review", headers=auth(admin), json=body).status_code == 404
    assert cs.unreviewed_flagged_count(db) == 1

    answer = client.post(url, headers=auth(admin), json=body)
    assert answer.status_code == 200
    data = answer.json()
    assert data["cashout"]["fee_review"]["state"] == "REVIEWED" and data["fee_exception"]["review"]["note"] == FOUND
    assert data["cashout"]["status"] == "completed"
    assert client.post(url, headers=auth(admin), json=body).status_code == 200            # the same review again
    duplicate = client.post(url, headers=auth(second), json=body)
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "ALREADY_REVIEWED"
    assert db.query(AuditTrail).filter_by(action="CASHOUT_FEE_EXCEPTION_REVIEWED").count() == 1
    # It reactivated nothing.
    assert suspension(db)[0] == "PROVIDER_FEE_MODE_MISMATCH"
    settings_now = client.get("/api/v1/admin/finance/settings", headers=auth(admin)).json()
    assert settings_now["payout_suspension"]["reason"] == "PROVIDER_FEE_MODE_MISMATCH"


def test_the_exception_endpoints_are_read_only_and_for_administrators(client, strict, payers_confirmed):
    db = strict
    user, row, _provider = flagged_payout(db)
    admin = member(db, "boss", admin=True)
    url = "/api/v1/admin/cashouts/fee-exceptions"
    assert client.get(url).status_code in (401, 403)
    assert client.get(url, headers=auth(user)).status_code == 403
    before = everything_else(db, row.id)
    listing = client.get(url, headers=auth(plain_admin(db)))       # reading needs an administrator, nothing more
    assert listing.status_code == 200 and listing.json()["pending_count"] == 1
    assert client.get(url, headers=auth(admin), params={"state": "PENDING"}).json()["total"] == 1
    assert client.get(url, headers=auth(admin), params={"state": "REVIEWED"}).json()["total"] == 0
    assert client.get(url, headers=auth(admin), params={"state": "anything"}).status_code == 422
    detail = client.get(f"/api/v1/admin/cashouts/{row.id}", headers=auth(admin)).json()
    assert detail["fee_exception"]["flag"] == "PROVIDER_FEE_MODE_MISMATCH"
    assert detail["fee_exception"]["caused_suspension"] is True
    assert [e["action"] for e in detail["fee_events"]][:2] == ["CASHOUT_RESERVED", "CASHOUT_COMPLETED"]
    assert everything_else(db, row.id) == before


# ===========================================================================
# 4. What the Admin Panel is told
# ===========================================================================

def codes(status: dict) -> list:
    return [b["code"] for b in status["blockers"]]


def test_with_the_defaults_every_reason_is_listed_not_just_the_first(books):
    db = books
    status = engine.crypto_payout_status(db)
    assert status["can_create_payouts"] is False
    assert codes(status) == ["SERVER_SWITCH_OFF", "NOT_ACTIVATED", "PAYOUT_CREDENTIALS_MISSING", "PROVIDER_FEE_MODE_UNVERIFIED",
                             "FEE_LIMITS_NOT_CONFIGURED", "FEE_SAFETY_MARGIN_NOT_SET", "FEE_LIMITS_NOT_APPROVED",
                             "AUTOMATIC_PAYOUTS_OFF"]
    assert all(b["message"] and b["action"] and b["section"] for b in status["blockers"])
    assert [(m["field"], m["section"]) for m in status["missing_settings"]] == [
        ("provider_fee_mode", "provider"), ("member_fee_cap_percent", "fee_limits"),
        ("member_fee_cap_usd", "fee_limits"), ("fee_estimate_margin_percent", "safety")]
    assert status["approval"] == {"approved": False, "can_approve": False,
                                  "blocked_by": {"code": "PROVIDER_FEE_MODE_UNVERIFIED",
                                                 "message": pc.FEE_GATE_MESSAGES["PROVIDER_FEE_MODE_UNVERIFIED"]}}
    assert status["provider_semantics"] == {
        "fee_mode": "UNVERIFIED", "fee_mode_confirmed": False, "receiver_fee_values_confirmed": False,
        "company_fee_values_confirmed": False, "amount_meaning": None, "automatic_verification": False}
    assert status["suspension"] is None and status["recording_gate"]["blocked"] is False
    # No number is proposed anywhere: the values are the business owner's.
    assert not any(ch.isdigit() for b in status["blockers"] if b["section"] in ("fee_limits", "safety")
                   for ch in b["action"])
    assert db.query(PaymentSettings).count() == 0                  # asking changed nothing, not even the row


def test_when_nothing_is_listed_the_engine_pays_and_only_then(books, engine_on, payers_confirmed):
    db = books
    user = paid_member(db)
    status = engine.crypto_payout_status(db)
    assert status["can_create_payouts"] is True and status["blockers"] == [] and status["missing_settings"] == []
    assert status["approval"] == {"approved": True, "can_approve": True, "blocked_by": None}
    assert status["provider_semantics"] == {
        "fee_mode": "DEDUCTED_BY_PROVIDER", "fee_mode_confirmed": True, "receiver_fee_values_confirmed": True,
        "company_fee_values_confirmed": True, "amount_meaning": "REQUESTED", "automatic_verification": True}
    assert status["switches"] == {"server": True, "activation": True, "provider": True, "crypto_cashout": True,
                                  "automatic_payouts": True, "credentials_ready": True}
    assert run(db, RichProvider())["members"] == {"SUBMITTED": 1} and cashouts(db, user)[0].status == "processing"


@pytest.mark.parametrize("change, code, section", [
    (dict(provider_fee_mode="UNVERIFIED"), "PROVIDER_FEE_MODE_UNVERIFIED", "provider"),
    (dict(network_fee_policy="COMPANY_PAYS"), "FEE_POLICY_NOT_BENEFICIARY_PAID", "provider"),
    (dict(member_fee_cap_percent=Decimal("0"), member_fee_cap_usd=Decimal("0")), "FEE_LIMITS_NOT_CONFIGURED",
     "fee_limits"),
    (dict(fee_estimate_margin_percent=None), "FEE_SAFETY_MARGIN_NOT_SET", "safety"),
    (dict(fee_terms_approved=False), "FEE_LIMITS_NOT_APPROVED", "activation"),
    (dict(crypto_cashout_enabled=False), "CRYPTO_CASHOUT_DISABLED", "activation"),
    (dict(crypto_auto_payout_enabled=False), "AUTOMATIC_PAYOUTS_OFF", "activation"),
    (dict(provider_enabled=False), "PROVIDER_DISABLED", "provider"),
])
def test_each_reason_shown_is_one_the_engine_enforces(books, engine_on, change, code, section):
    db = books
    user = paid_member(db)
    configure(db, **change)
    status = engine.crypto_payout_status(db)
    assert status["can_create_payouts"] is False
    assert [(b["code"], b["section"], b["temporary"]) for b in status["blockers"]] == [(code, section, False)]
    provider_ = RichProvider()
    report = run(db, provider_)
    assert provider_.created == [] and cashouts(db, user) == []    # and the engine indeed pays nothing
    assert report.get("members", {}).get("SUBMITTED") is None


def test_a_suspension_and_the_temporary_hold_are_told_apart(strict, payers_confirmed):
    db = strict
    first, second = paid_member(db, "m1"), paid_member(db, "m2", "7.00")
    provider_ = RichProvider()
    run(db, provider_)
    status = engine.crypto_payout_status(db)                       # one payout is on its way
    assert [(b["code"], b["temporary"]) for b in status["blockers"]] == [("FEE_RECONCILIATION_PENDING", True)]
    assert "No reactivation is needed" in status["blockers"][0]["action"]
    assert status["recording_gate"] == {"limit": 0, "in_flight": 1, "completed_unreconciled": 0, "total": 1,
                                        "blocked": True}
    assert status["suspension"] is None
    finish(db, provider_, fee="0.25", paid_by="sender")            # the provider charged MyHigh5
    status = engine.crypto_payout_status(db)
    assert codes(status) == ["PAYOUTS_SUSPENDED", "PROVIDER_FEE_MODE_UNVERIFIED", "FEE_LIMITS_NOT_APPROVED",
                             "FEE_RECONCILIATION_PENDING"]
    assert (status["blockers"][0]["section"], status["blockers"][0]["temporary"]) == ("suspension", False)
    assert status["suspension"]["cashout_id"] == cashouts(db, first)[0].id
    assert status["flagged_payouts"] == {"pending_review": 1}
    assert status["approval"]["approved"] is False and cashouts(db, second) == []


def test_the_sections_cover_every_crypto_setting_and_unsupported_choices_are_marked(books):
    db = books
    view = pc.settings_view(db)
    crypto = [f["name"] for f in view["fields"] if f["group"] == "crypto"]
    sectioned = [name for section in view["crypto_sections"] for name in section["fields"]]
    assert sorted(sectioned) == sorted(crypto) and len(sectioned) == len(set(sectioned))
    assert [s["key"] for s in view["crypto_sections"]] == ["provider", "fee_limits", "safety", "activation", "limits"]
    fields = {f["name"]: f for f in view["fields"]}
    assert [c["value"] for c in fields["network_fee_policy"]["disabled_choices"]] == ["COMPANY_PAYS"]
    assert [c["value"] for c in fields["provider_fee_mode"]["disabled_choices"]] == ["CHARGED_TO_BALANCE"]
    assert all(c["reason"] for name in ("network_fee_policy", "provider_fee_mode")
               for c in fields[name]["disabled_choices"])
    assert fields["member_fee_cap_usd"]["disabled_choices"] == []
    assert fields["fee_estimate_margin_percent"]["optional"] is True
    # Marked in the screen AND refused by the server, whatever a client sends.
    admin = member(db, "boss", admin=True)
    for change, code in (({"network_fee_policy": "COMPANY_PAYS"}, "POLICY_RETIRED"),
                         ({"provider_fee_mode": "CHARGED_TO_BALANCE"}, "NOT_AVAILABLE")):
        configure(db, network_fee_policy="MEMBER_PAYS")
        with pytest.raises(pc.PaymentConfigError) as error:
            pc.update_settings(db, admin, change, password=PASSWORD, now=NOW, expected_version=pc.load(db).version)
        assert error.value.code == code


def test_the_status_endpoint_is_read_only_and_for_administrators(client, books, engine_on):
    db = books
    user = paid_member(db)
    admin = member(db, "boss", admin=True)
    url = "/api/v1/admin/finance/payout-status"
    assert client.get(url).status_code in (401, 403)
    assert client.get(url, headers=auth(user)).status_code == 403
    version = pc.load(db).version
    answer = client.get(url, headers=auth(plain_admin(db)))
    assert answer.status_code == 200
    data = answer.json()
    assert data["can_create_payouts"] is True and data["configuration_version"] == version
    assert client.get(url, headers=auth(admin)).json() == data
    assert pc.load(db).version == version and cashouts(db, user) == []
    assert client.post(url, headers=auth(admin), json={}).status_code == 405
