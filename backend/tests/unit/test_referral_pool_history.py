"""P9: classification of historical single-seat pool records and the read-only conversion preview
(pure functions over the redacted audit rows; synthetic data only)."""
from __future__ import annotations

from app.services import referral_pool_history as h

RECOGNIZED = "1001:100.00;2100:0.00;4008:-100.00"
HELD = "1001:100.00;2100:-100.00"


def dep(deposit_id, user_id, **extra) -> dict:
    row = {"deposit_id": deposit_id, "user_id": user_id, "product": "referral_pool_entry", "amount": "100.00000000",
           "currency": "USD", "deposit_status": "validated", "provider": "nowpayments", "provider_env": "",
           "has_provider_payment_id": "t", "has_tx_hash": "f", "admin_granted": "f", "refund_marker": "f",
           "ledger_net_by_account": RECOGNIZED, "commissions": "1", "same_provider_id_count": "1",
           "account_ok": "t", "payer_has_sponsor": "t"}
    row.update(extra)
    return row


def mem(membership_id, user_id, deposit_id, **extra) -> dict:
    row = {"membership_id": membership_id, "user_id": user_id, "status": "ACTIVE", "entitlement_source": "PAID",
           "source_deposit_id": "" if deposit_id is None else deposit_id, "assignments_count": "0", "assignment_rows": "0",
           "account_ok": "t", "identity_verified": "t", "latest_kyc": "approved"}
    row.update(extra)
    return row


def groups(deposits, memberships) -> dict:
    return {(d.kind, d.record_id): (d.group, d.reasons) for d in h.classify(deposits, memberships)}


def test_a_confirmed_recognized_100_dollar_seat_is_one_candidate_unit_with_no_new_revenue_or_commission():
    out = h.classify([dep(1, 10)], [mem(5, 10, 1, assignments_count="2", assignment_rows="2")])
    assert [(d.group, d.unit_status_if_converted, d.assignments_to_preserve) for d in out] == [(h.A, "ACTIVE", 2)]
    p = h.preview(out)
    assert p["conversion_candidates"] == {"memberships": 1, "units": 1, "units_active": 1, "units_suspended": 0,
                                               "value": "100.00", "new_revenue": "0.00", "new_commission": "0.00"}
    assert p["assignments_to_preserve"] == 2
    assert p["expected_new_records_if_approved"]["journal_entries"] == 0


def test_a_candidate_whose_holder_is_not_kyc_approved_today_would_get_a_suspended_unit():
    out = h.classify([dep(1, 10)], [mem(5, 10, 1, latest_kyc="rejected", identity_verified="f")])
    assert (out[0].group, out[0].unit_status_if_converted) == (h.A, "SUSPENDED")


def test_founding_and_admin_granted_seats_are_never_automatic_paid_units():
    g = groups([dep(2, 11, product="founding_membership", ledger_net_by_account="")],
               [mem(6, 11, 2, entitlement_source="LEGACY_FOUNDING_MIGRATION"),
                mem(7, 12, None, entitlement_source="ADMIN_ADJUSTMENT")])
    assert g[("MEMBERSHIP", 6)][0] == g[("MEMBERSHIP", 7)][0] == h.B


def test_a_confirmed_payment_held_in_2100_without_a_seat_needs_an_owner_decision():
    out = h.classify([dep(3, 13, ledger_net_by_account=HELD, commissions="0")], [])
    assert (out[0].kind, out[0].group, out[0].commission_exposure_if_converted) == ("DEPOSIT", h.C, "20.00")
    held = h.preview(out)["held_in_2100"]
    assert held == {"payments": 1, "value": "100.00",
                    "if_converted": {"revenue_dr2100_cr4008": "100.00", "commission_exposure": "20.00"},
                    "if_refunded": {"cash_out_dr2100_cr1001": "100.00"}}
    no_sponsor = h.classify([dep(3, 13, ledger_net_by_account=HELD, commissions="0", payer_has_sponsor="f")], [])
    assert no_sponsor[0].commission_exposure_if_converted == "0.00"


def test_a_2100_balance_alone_is_not_enough_evidence():
    out = h.classify([dep(3, 13, ledger_net_by_account=HELD, commissions="0", has_provider_payment_id="f"),
                      dep(4, 14, ledger_net_by_account=HELD, commissions="0", admin_granted="t"),
                      dep(5, 15, ledger_net_by_account=HELD, commissions="0", provider_env="test")], [])
    assert [(d.group, d.reasons) for d in out] == [
        (h.E, ["NO_PROVIDER_EVIDENCE"]), (h.E, ["ADMIN_GRANTED"]), (h.E, ["TEST_ENVIRONMENT_PAYMENT"])]


def test_refunded_or_reversed_records_are_excluded_and_unpaid_ones_are_not_memberships():
    g = groups([dep(1, 10, refund_marker="t"), dep(2, 11, deposit_status="failed"), dep(3, 12, deposit_status="expired"),
                dep(4, 13, deposit_status="pending")],
               [mem(5, 10, 1), mem(6, 11, 2, status="REFUNDED"), mem(7, 12, 3, status="EXPIRED")])
    assert g[("MEMBERSHIP", 5)][0] == g[("MEMBERSHIP", 6)][0] == h.D
    assert g[("MEMBERSHIP", 7)][0] == g[("DEPOSIT", 4)][0] == h.X


def test_conflicts_go_to_manual_review_and_never_become_units():
    g = groups(
        [dep(1, 10, amount="50.00"), dep(2, 11, same_provider_id_count="2"), dep(3, 12, commissions="2"),
         dep(4, 13, ledger_net_by_account=HELD), dep(6, 15), dep(7, 16, currency="EUR")],
        [mem(5, 10, 1), mem(6, 11, 2), mem(7, 12, 3), mem(8, 13, 4), mem(9, 14, None), mem(10, 15, 6),
         mem(11, 15, 6), mem(12, 16, 7), mem(13, 17, 99, status="CAPACITY_REVIEW"),
         mem(14, 18, None, account_ok="f"), mem(15, 19, None, assignments_count="3", assignment_rows="1")])
    expected = {5: "AMOUNT_NOT_100", 6: "DUPLICATE_PROVIDER_PAYMENT_ID", 7: "MORE_THAN_ONE_COMMISSION",
                8: "LEDGER_NOT_RECOGNIZED_AS_REVENUE", 9: "PAYMENT_MISSING", 10: "USER_HAS_SEVERAL_MEMBERSHIPS",
                11: "PAYMENT_BACKS_SEVERAL_MEMBERSHIPS", 12: "CURRENCY_NOT_USD", 13: "PAYMENT_MISSING",
                14: "ACCOUNT_INACTIVE_OR_DELETED", 15: "ASSIGNMENT_COUNTER_MISMATCH"}
    for mid, reason in expected.items():
        group, reasons = g[("MEMBERSHIP", mid)]
        assert group == h.E and reason in reasons, (mid, group, reasons)


def test_the_counter_mismatch_alone_holds_back_an_otherwise_clean_seat():
    out = h.classify([dep(1, 10)], [mem(5, 10, 1, assignments_count="3", assignment_rows="2")])
    assert (out[0].group, out[0].reasons, out[0].assignments_to_preserve) == (h.E, ["ASSIGNMENT_COUNTER_MISMATCH"], 2)


def test_the_classification_is_deterministic_and_every_record_is_counted_once():
    deposits = [dep(i, 100 + i) for i in range(1, 6)] + [dep(9, 200, ledger_net_by_account=HELD, commissions="0")]
    memberships = [mem(50 + i, 100 + i, i) for i in range(1, 6)]
    first = h.as_rows(h.classify(deposits, memberships))
    second = h.as_rows(h.classify(list(reversed(deposits)), list(reversed(memberships))))
    assert first == second
    p = h.preview(h.classify(deposits, memberships))
    assert sum(p["counts"].values()) == len(memberships) + 1
    assert p["counts"][h.A] == 5 and p["counts"][h.C] == 1 and p["manual_review"] == 0 and p["excluded"] == 0


def test_the_ledger_parser_reads_net_amounts_per_account():
    assert h.ledger("1001:100.00;2100:-100.00;bad") == {"1001": h.UNIT_PRICE, "2100": -h.UNIT_PRICE}
    assert h.ledger(None) == {}
