"""Phase 1 financial controls.

1. Historical commissions are HELD from every payout path until an authorised
   administrator records a decision; a decision is final and audited.
2. Manually recorded payments need two administrators (maker-checker).
3. Database guards on referrals and commissions.
4. The correction scripts: invalid payment reversal, historical commission
   reconciliation, sponsor-cycle correction (dry run by default, idempotent).

Every account, payment and amount here is SYNTHETIC.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission, AffiliateTree, CommissionStatus, CommissionType
from app.models.financial_controls import CommissionPayoutReview, ManualPaymentConfirmation
from app.models.payment import Deposit, DepositStatus
from app.models.user import User
from app.services import cashout_engine, cashout_service as cs
from app.services import commission_payout_hold as hold
from app.services import ledger_snapshot
from app.services import manual_payment_service as mps
from app.services import payment_config as pc
from app.services.accounting_service import accounting_service
from app.services.commission_distribution import process_payment_validation
from app.services.financial_balances import get_commission_balance
from app.services.financial_reversal import INVALID_PAYMENT_REVERSAL_MARKER
from app.services.nowpayments_service import finalize_deposit_from_nowpayments
from tests.unit.test_admin_security_hardening import PASSWORD, person
from tests.unit.test_new_business_model import _assert_all_journals_balance, _balance, _deposit, _user, world  # noqa: F401

pytestmark = pytest.mark.unit

WALLET = "0x" + "4" * 40


def legacy_commission(db, beneficiary, payer, *, level=1, amount="1.00", status=CommissionStatus.APPROVED,
                      deposit=None, when=None) -> AffiliateCommission:
    row = AffiliateCommission(user_id=beneficiary.id, source_user_id=payer.id, commission_type=CommissionType.KYC_PAYMENT,
                              level=level, base_amount=Decimal("10.00"), commission_amount=Decimal(amount),
                              status=status, deposit_id=deposit.id if deposit else None,
                              transaction_date=when or datetime(2026, 7, 6))
    db.add(row)
    db.commit()
    return row


def processor(db, name="processor"):
    return person(db, name, admin=True, permissions=(pc.PERMISSION_PROCESS,))


def cashier(db, name):
    from app.services import admin_security as sec

    return person(db, name, admin=True, permissions=(sec.PERMISSION_GRANT_PAYMENTS,))


# ===========================================================================
# 1. Historical commissions are held from payout
# ===========================================================================

def test_historical_commissions_are_held_from_every_payout_path_new_ones_are_not(world):
    db = world
    sponsor = _user(db, "hs@example.com", wallet=True)
    payer = _user(db, "hp@example.com", sponsor=sponsor)
    db.commit()
    old = legacy_commission(db, sponsor, payer, amount="1.00")
    old_pending = legacy_commission(db, sponsor, payer, level=2, amount="0.10", status=CommissionStatus.PENDING)
    process_payment_validation(db, _deposit(db, payer, "annual_membership"))            # NEW_V2: $10
    new = db.query(AffiliateCommission).filter(AffiliateCommission.business_model_version.isnot(None)).one()

    assert [r.id for r in cs.available_rows(db, sponsor.id)] == [new.id]
    db.rollback()
    bal = get_commission_balance(db, sponsor.id)
    assert (bal.available, bal.held, bal.pending) == (Decimal("10.00"), Decimal("1.10"), Decimal("0.10"))
    # A PENDING historical row is not promoted when a payout destination appears.
    sponsor.cashout_method = cs.METHOD_USD
    db.commit()
    cs.release_pending(db, sponsor)
    db.commit()
    db.refresh(old_pending)
    assert old_pending.status == CommissionStatus.PENDING
    # The crypto engine and the legacy payout service never pick a held row.
    sponsor.cashout_method = cs.METHOD_CRYPTO
    other = _user(db, "only-old@example.com", wallet=True)
    other.cashout_method = cs.METHOD_CRYPTO
    legacy_commission(db, other, payer)
    db.commit()
    assert other.id not in cashout_engine.candidate_user_ids(db, 50)
    from app.services.commission_payout_service import trigger_commission_payout_sync

    assert trigger_commission_payout_sync(db, sponsor, old) is False
    db.refresh(old)
    assert (old.status, old.payout_reference) == (CommissionStatus.APPROVED, None)          # untouched
    assert cashout_engine.reconciliation_report(db)["held_for_review"] == pytest.approx(2.10)


def test_a_commission_stamped_with_the_legacy_version_is_historical_too(world):
    """The codebase's rule (new_model_ledger.is_new_model): anything but NEW_V2 is legacy, not only NULL."""
    db = world
    sponsor = _user(db, "lv@example.com", wallet=True)
    payer = _user(db, "lvp@example.com", sponsor=sponsor)
    db.commit()
    stamped = legacy_commission(db, sponsor, payer, level=2, amount="0.10")
    stamped.business_model_version = "LEGACY_V1"
    db.commit()                                                     # level 2 is allowed for a legacy stamp
    assert cs.available_rows(db, sponsor.id) == []
    db.rollback()
    assert get_commission_balance(db, sponsor.id).held == Decimal("0.10")
    assert hold.is_payable(db, stamped) is False
    assert [r["commission_id"] for r in hold.held_view(db)] == [stamped.id]
    hold.review(db, processor(db), stamped.id, decision="RELEASE", reason="Verified against provider statement",
                password=PASSWORD)
    assert [r.id for r in cs.available_rows(db, sponsor.id)] == [stamped.id]


def test_a_release_decision_makes_one_historical_row_payable_and_nothing_else(world):
    db = world
    sponsor = _user(db, "rs@example.com")
    payer = _user(db, "rp@example.com", sponsor=sponsor)
    db.commit()
    a = legacy_commission(db, sponsor, payer, amount="1.00")
    b = legacy_commission(db, sponsor, payer, level=2, amount="0.10")
    admin = processor(db)
    hold.review(db, admin, a.id, decision="RELEASE", reason="Verified against provider statement", password=PASSWORD,
                evidence_reference="statement 2026-04")
    assert [r.id for r in cs.available_rows(db, sponsor.id)] == [a.id]
    db.rollback()
    hold.review(db, admin, b.id, decision="CANCEL", reason="Retired multi-level row, owner decision", password=PASSWORD)
    assert [r.id for r in cs.available_rows(db, sponsor.id)] == [a.id]            # CANCEL stays held until executed
    db.rollback()
    db.refresh(b)
    assert b.status == CommissionStatus.APPROVED                                     # the decision alone changes nothing
    audits = db.query(AuditTrail).filter(AuditTrail.action == hold.AUDIT_REVIEW).order_by(AuditTrail.id).all()
    assert [(x.record_id, x.new_values["decision"], x.user_id) for x in audits] == [(a.id, "RELEASE", admin.id),
                                                                                    (b.id, "CANCEL", admin.id)]
    assert PASSWORD not in str([(x.old_values, x.new_values) for x in audits])


def test_a_review_needs_the_permission_the_password_a_reason_and_is_final(world, client):
    db = world
    sponsor = _user(db, "vs@example.com")
    payer = _user(db, "vp@example.com", sponsor=sponsor)
    db.commit()
    row = legacy_commission(db, sponsor, payer)
    plain = person(db, "plainadmin", admin=True)
    admin = processor(db)
    with pytest.raises(hold.CommissionReviewError) as e:
        hold.review(db, plain, row.id, decision="RELEASE", reason="Looks fine to me", password=PASSWORD)
    assert e.value.code == "FORBIDDEN"
    for kwargs, code in (({"password": "wrong"}, "REAUTH_REQUIRED"), ({"reason": "ok"}, "REASON_REQUIRED"),
                         ({"decision": "PAY"}, "INVALID_DECISION")):
        args = {"decision": "RELEASE", "reason": "Verified against statement", "password": PASSWORD, **kwargs}
        with pytest.raises(hold.CommissionReviewError) as e:
            hold.review(db, admin, row.id, **args)
        assert e.value.code == code
    hold.review(db, admin, row.id, decision="RELEASE", reason="Verified against statement", password=PASSWORD)
    with pytest.raises(hold.CommissionReviewError) as e:
        hold.review(db, admin, row.id, decision="CANCEL", reason="Changed my mind about it", password=PASSWORD)
    assert e.value.code == "ALREADY_DECIDED"
    # Nobody reviews their own commission; a NEW_V2 row is never held.
    own = legacy_commission(db, admin, payer)
    with pytest.raises(hold.CommissionReviewError) as e:
        hold.review(db, admin, own.id, decision="RELEASE", reason="Verified against statement", password=PASSWORD)
    assert e.value.code == "SELF_ACTION_FORBIDDEN"
    process_payment_validation(db, _deposit(db, payer, "annual_membership"))
    new = db.query(AffiliateCommission).filter(AffiliateCommission.business_model_version.isnot(None)).one()
    with pytest.raises(hold.CommissionReviewError) as e:
        hold.review(db, admin, new.id, decision="RELEASE", reason="Verified against statement", password=PASSWORD)
    assert e.value.code == "NOT_HELD"
    # Through the API: the list, and a refusal without the permission.
    from tests.unit.test_admin_security_hardening import bearer

    listed = client.get("/api/v1/admin/cashouts/commission-reviews", headers=bearer(admin)).json()["items"]
    assert {i["commission_id"]: i["decision"] for i in listed} == {row.id: "RELEASE", own.id: None}
    refused = client.post(f"/api/v1/admin/cashouts/commission-reviews/{own.id}", headers=bearer(plain),
                          json={"decision": "RELEASE", "reason": "Verified against statement", "current_password": PASSWORD})
    assert refused.status_code == 403


# ===========================================================================
# 2. Manual payments: two administrators
# ===========================================================================

def test_maker_checker_rules_at_service_level(world):
    db = world
    sponsor = _user(db, "ms@example.com")
    member = _user(db, "mm@example.com", sponsor=sponsor)
    db.commit()
    maker, checker = cashier(db, "maker"), cashier(db, "checker")
    out = mps.record(db, maker, member.id, product_code="annual_membership", reason="Bank ref 2026-10-16/77",
                     password=PASSWORD, verify_identity=True)
    req = out.request
    assert (out.status, out.deposit.status, db.query(JournalEntry).count(), db.query(AffiliateCommission).count()) == \
        ("pending_confirmation", DepositStatus.PENDING, 0, 0)
    with pytest.raises(mps.ManualPaymentError) as e:                                 # one open request per product
        mps.record(db, maker, member.id, product_code="annual_membership", reason="Bank ref 2026-10-16/78",
                   password=PASSWORD)
    assert e.value.code == "REQUEST_PENDING"
    with pytest.raises(mps.ManualPaymentError) as e:
        mps.reject(db, maker, req.id, password=PASSWORD, reason="I want to reject my own")
    assert e.value.code == "SAME_ADMINISTRATOR"
    with pytest.raises(mps.ManualPaymentError) as e:
        mps.cancel(db, checker, req.id, password=PASSWORD, reason="Not mine to withdraw")
    assert e.value.code == "NOT_REQUESTER"
    db.refresh(member)
    assert member.identity_verified is not True                                      # nothing before confirmation
    done = mps.confirm(db, checker, req.id, password=PASSWORD, evidence_reference="TX-0xfeed01")
    db.refresh(member)
    assert (done.status, done.deposit.status, done.deposit.validated_by, member.identity_verified) == \
        ("granted", DepositStatus.VALIDATED, checker.id, True)
    commission = db.query(AffiliateCommission).one()
    assert (commission.user_id, commission.commission_amount) == (sponsor.id, Decimal("10.00"))
    for call in (lambda: mps.confirm(db, checker, req.id, password=PASSWORD, evidence_reference="TX-0xfeed01"),
                 lambda: mps.reject(db, checker, req.id, password=PASSWORD, reason="Too late to reject it")):
        with pytest.raises(mps.ManualPaymentError) as e:
            call()
        assert e.value.code == "ALREADY_DECIDED"
    assert db.query(AffiliateCommission).count() == 1
    _assert_all_journals_balance(db)


def test_reject_and_cancel_credit_nothing_and_close_only_the_deposit_they_created(world):
    db = world
    member = _user(db, "rm@example.com")
    db.commit()
    maker, checker = cashier(db, "maker2"), cashier(db, "checker2")
    first = mps.record(db, maker, member.id, product_code="kyc", reason="Cash at the office, receipt 12",
                       password=PASSWORD).request
    mps.reject(db, checker, first.id, password=PASSWORD, reason="No receipt exists for this")
    assert db.get(Deposit, first.deposit_id).status == DepositStatus.FAILED
    # Attached to an unfinished provider deposit: rejecting leaves that deposit as it was.
    provider_dep = _deposit(db, member, "annual_membership", status=DepositStatus.PENDING, tag="prov")
    db.commit()
    second = mps.record(db, maker, member.id, product_code="annual_membership", reason="Paid, callback lost #1",
                        password=PASSWORD).request
    assert (second.deposit_id, second.created_new_deposit) == (provider_dep.id, False)
    mps.cancel(db, maker, second.id, password=PASSWORD, reason="Recorded for the wrong member")
    assert db.get(Deposit, provider_dep.id).status == DepositStatus.PENDING
    assert (db.query(JournalEntry).count(), db.query(AffiliateCommission).count()) == (0, 0)
    actions = [a.action for a in db.query(AuditTrail).order_by(AuditTrail.id)]
    assert actions.count("MANUAL_PAYMENT_REQUESTED") == 2 and "MANUAL_PAYMENT_REJECTED" in actions \
        and "MANUAL_PAYMENT_CANCELLED" in actions


def test_confirming_a_payment_the_provider_already_validated_credits_nothing_twice(world):
    db = world
    member = _user(db, "pm@example.com")
    db.commit()
    maker, checker = cashier(db, "maker3"), cashier(db, "checker3")
    dep = _deposit(db, member, "annual_membership", status=DepositStatus.PENDING, tag="late")
    db.commit()
    req = mps.record(db, maker, member.id, product_code="annual_membership", reason="Paid, callback lost #2",
                     password=PASSWORD).request
    finalize_deposit_from_nowpayments(db, dep, {"payment_status": "finished", "payment_id": dep.external_payment_id,
                                                "order_id": dep.order_id, "price_amount": 50, "price_currency": "usd"})
    db.commit()
    entries = db.query(JournalEntry).count()
    out = mps.confirm(db, checker, req.id, password=PASSWORD, evidence_reference="TX-0xfeed02")
    assert out.status == "superseded" and db.query(JournalEntry).count() == entries


def test_the_member_cannot_confirm_and_a_reversed_deposit_cannot_be_confirmed(world):
    db = world
    maker = cashier(db, "maker4")
    member_admin = cashier(db, "memberadmin")
    req = mps.record(db, maker, member_admin.id, product_code="kyc", reason="Cash at the office, receipt 13",
                     password=PASSWORD).request
    with pytest.raises(mps.ManualPaymentError) as e:
        mps.confirm(db, member_admin, req.id, password=PASSWORD, evidence_reference="TX-0xfeed03")
    assert e.value.code == "SELF_ACTION_FORBIDDEN"
    dep = db.get(Deposit, req.deposit_id)
    dep.admin_notes = f"{dep.admin_notes}\n{INVALID_PAYMENT_REVERSAL_MARKER} at x"
    db.commit()
    with pytest.raises(mps.ManualPaymentError) as e:
        mps.confirm(db, cashier(db, "checker4"), req.id, password=PASSWORD, evidence_reference="TX-0xfeed03")
    assert e.value.code == "DEPOSIT_REVERSED"


# ===========================================================================
# 3. Database guards
# ===========================================================================

@pytest.mark.parametrize("bad", [
    {"commission_amount": Decimal("0.00")},
    {"commission_amount": Decimal("-1.00")},
    {"level": 11},
    {"level": 2, "business_model_version": "NEW_V2"},
])
def test_commission_guards(world, bad):
    db = world
    a = _user(db, f"ga{len(str(bad))}@example.com")
    b = _user(db, f"gb{len(str(bad))}@example.com", sponsor=a)
    db.commit()
    row = dict(user_id=a.id, source_user_id=b.id, commission_type=CommissionType.KYC_PAYMENT, level=1,
               commission_amount=Decimal("1.00"), status=CommissionStatus.APPROVED)
    row.update(bad)
    db.add(AffiliateCommission(**row))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_one_commission_per_payment_and_per_source_and_no_self_sponsor(world):
    db = world
    a = _user(db, "ua@example.com")
    b = _user(db, "ub@example.com", sponsor=a)
    db.commit()
    dep = _deposit(db, b, "annual_membership")
    db.commit()
    common = dict(user_id=a.id, source_user_id=b.id, commission_type=CommissionType.KYC_PAYMENT, level=1,
                  commission_amount=Decimal("1.00"), status=CommissionStatus.APPROVED)
    db.add(AffiliateCommission(**common, deposit_id=dep.id))
    db.commit()
    db.add(AffiliateCommission(**common, deposit_id=dep.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(AffiliateCommission(**common, source_type="MARKET_ORDER", source_id=7))
    db.commit()
    db.add(AffiliateCommission(**common, source_type="MARKET_ORDER", source_id=7))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    a.sponsor_id = a.id
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ===========================================================================
# 4a. Invalid payment reversal
# ===========================================================================

def _invalid_payment_world(db):
    """Synthetic: a member sponsored by another account, two annual
    memberships and two KYC payments recorded by administrators without any provider payment."""
    sponsor_account = _user(db, "spa@example.com", wallet=True)
    referral = _user(db, "ref@example.com", sponsor=sponsor_account)
    admin = person(db, "rogue", admin=True)
    db.commit()
    deposits = []
    for user, code in ((sponsor_account, "annual_membership"), (sponsor_account, "kyc"), (referral, "kyc"), (referral, "annual_membership")):
        d = _deposit(db, user, code, tag=f"f{len(deposits)}", external_payment_id=None, validated_by=admin.id,
                     order_id=f"ADMIN-{len(deposits)}")
        process_payment_validation(db, d)
        deposits.append(d)
    return sponsor_account, referral, deposits


def test_invalid_payment_reversal_dry_run_changes_nothing_and_apply_reverses_exactly(world):
    from app.scripts import reverse_invalid_payments as script

    db = world
    sponsor_account, _referral, deposits = _invalid_payment_world(db)
    ids = [d.id for d in deposits]
    before = ledger_snapshot.snapshot(db)
    assert before["accounts_debit_minus_credit"]["1001"] == "120.00"
    assert before["open_commissions"]["new_v2"] == "10.00"

    script.reverse(db, ids, case="CASE-TEST", evidence_ref="synthetic approval reference")
    db.rollback()                                                                    # the dry run
    assert ledger_snapshot.snapshot(db) == before

    result = script.reverse(db, ids, case="CASE-TEST", evidence_ref="synthetic approval reference", actor_id=None)
    db.commit()
    after = ledger_snapshot.snapshot(db)
    for code in ("1001", "4002", "2113", "2001", "5001"):
        assert after["accounts_debit_minus_credit"][code] == "0.00", code
    assert after["open_commissions"]["all"] == "0.00"
    assert [r["deposit_id"] for r in result["reversed"]] == ids
    for d in deposits:
        db.refresh(d)
        assert d.status == DepositStatus.FAILED and INVALID_PAYMENT_REVERSAL_MARKER in d.admin_notes
    assert db.query(AffiliateCommission).one().status == CommissionStatus.CANCELLED
    audits = db.query(AuditTrail).filter(AuditTrail.action == script.AUDIT_ACTION).all()
    assert len(audits) == 4 and all(a.old_values["deposit"]["status"] == "validated" for a in audits)
    _assert_all_journals_balance(db)
    entries = db.query(JournalEntry).count()
    # Idempotent, and a late "finished" provider event never validates a reversed payment again.
    again = script.reverse(db, ids, case="CASE-TEST", evidence_ref="synthetic approval reference")
    db.commit()
    assert again == {"reversed": [], "already_reversed": ids} and db.query(JournalEntry).count() == entries
    finalize_deposit_from_nowpayments(db, deposits[0], {"payment_status": "finished", "order_id": deposits[0].order_id})
    db.commit()
    db.refresh(deposits[0])
    assert deposits[0].status == DepositStatus.FAILED and db.query(JournalEntry).count() == entries


def test_invalid_payment_reversal_refuses_anything_it_must_not_touch(world):
    from app.scripts import reverse_invalid_payments as script

    db = world
    sponsor_account, referral, deposits = _invalid_payment_world(db)
    provider_paid = _deposit(db, referral, "kyc", tag="real")                     # has a provider payment id
    with pytest.raises(script.ReversalRefused, match="provider payment id"):
        script.reverse(db, [provider_paid.id], case="CASE-TEST", evidence_ref="synthetic approval reference")
    db.rollback()
    commission = db.query(AffiliateCommission).one()
    commission.payout_reference = "intent:synthetic"
    db.commit()
    with pytest.raises(script.ReversalRefused, match="reserved"):
        script.reverse(db, [d.id for d in deposits], case="CASE-TEST", evidence_ref="synthetic approval reference")
    db.rollback()
    assert all(db.get(Deposit, d.id).status == DepositStatus.VALIDATED for d in deposits)   # all or nothing
    with pytest.raises(script.ReversalRefused, match="required"):
        script.reverse(db, [deposits[0].id], case="x", evidence_ref="y")


# ===========================================================================
# 4b. Historical commission reconciliation
# ===========================================================================

def _legacy_world(db):
    """A historical deposit whose commission journal was posted twice, one with none, and a referral
    link written by the admin fallback (affiliate_tree level 1, no path, after registration)."""
    root = _user(db, "root@example.com")
    founder = _user(db, "founder@example.com")
    mid = _user(db, "mid@example.com", sponsor=root)
    db.commit()
    root.created_at = datetime(2025, 12, 28)
    root.sponsor_id = founder.id                                                     # written by the fallback...
    db.add(AffiliateTree(user_id=root.id, sponsor_id=founder.id, level=1, path=None,
                         join_date=datetime(2026, 4, 22, 21, 13)))                     # ...on that day
    payer = _user(db, "payer@example.com", sponsor=mid)
    db.commit()
    dep_a = _deposit(db, payer, "kyc", tag="a", version=None)
    dep_b = _deposit(db, payer, "kyc", tag="b", version=None)
    c1 = legacy_commission(db, mid, payer, amount="1.00", deposit=dep_a, when=datetime(2026, 4, 8))
    c2 = legacy_commission(db, root, payer, level=2, amount="0.10", deposit=dep_a, when=datetime(2026, 4, 8))
    c3 = legacy_commission(db, mid, payer, amount="1.00", deposit=dep_b, when=datetime(2026, 7, 6))
    c4 = legacy_commission(db, root, payer, level=2, amount="0.10", deposit=dep_b, when=datetime(2026, 7, 6))
    c5 = legacy_commission(db, founder, payer, level=3, amount="0.10", deposit=dep_b, when=datetime(2026, 7, 6))
    lines = [{"account_code": "5001", "debit": 1.10, "credit": 0}, {"account_code": "2001", "debit": 0, "credit": 1.00},
             {"account_code": "2002", "debit": 0, "credit": 0.10}]
    for _ in range(2):                                                               # posted twice
        accounting_service.create_journal_entry(db, description=f"KYC Payment - Deposit #{dep_a.id} - User #{payer.id} (Commissions)",
                                                lines=lines, commit=True)
    return dep_a, dep_b, [c1, c2, c3, c4, c5]


def test_legacy_report_and_corrections_bring_the_ledger_to_the_subledger(world):
    from app.scripts import reconcile_legacy_commissions as script

    db = world
    dep_a, dep_b, rows = _legacy_world(db)
    report = script.report(db)
    assert report["deposits_with_duplicate_commission_journal"] == [dep_a.id]
    assert report["deposits_without_commission_journal"] == [dep_b.id]
    flags = {i["commission_id"]: i["flags"] for i in report["historical_commissions"]}
    assert "REFERRAL_LINK_FROM_ADMIN_FALLBACK" in flags[rows[4].id]                  # level 3 via the fallback link
    assert all("REFERRAL_LINK_FROM_ADMIN_FALLBACK" not in flags[r.id] for r in rows[:4])
    assert report["open_flagged_fallback_total"] == "0.10"
    assert report["ledger"]["5001_expense"] == "2.20" and report["ledger"]["commissions_not_cancelled"] == "2.30"

    script.fix_duplicate_journal(db, [dep_a.id])
    script.post_missing_accruals(db)
    db.commit()
    ledger = ledger_snapshot.snapshot(db)["ledger_vs_subledger"]
    assert (ledger["2001_liability"], ledger["open_level_1"]) == ("2.00", "2.00")
    assert (ledger["2002_liability"], ledger["open_levels_2_10"]) == ("0.30", "0.30")
    assert (ledger["5001_expense"], ledger["commissions_not_cancelled"]) == ("2.30", "2.30")
    entries = db.query(JournalEntry).count()
    script.fix_duplicate_journal(db, [dep_a.id])                                     # idempotent
    script.post_missing_accruals(db)
    db.commit()
    assert db.query(JournalEntry).count() == entries
    _assert_all_journals_balance(db)
    # Nothing was cancelled and nothing was released by any of this.
    assert all(db.get(AffiliateCommission, r.id).status == CommissionStatus.APPROVED for r in rows)
    assert db.query(CommissionPayoutReview).count() == 0


def test_legacy_cancellation_only_after_a_recorded_decision(world):
    from app.scripts import reconcile_legacy_commissions as script

    db = world
    dep_a, dep_b, rows = _legacy_world(db)
    script.fix_duplicate_journal(db, [dep_a.id])
    script.post_missing_accruals(db)
    db.commit()
    assert script.execute_cancellations(db)["cancellations"] == []                   # no decision, nothing happens
    admin = processor(db)
    hold.review(db, admin, rows[4].id, decision="CANCEL", reason="Derived from fabricated referral link",
                password=PASSWORD)
    out = script.execute_cancellations(db, actor_id=admin.id)
    db.commit()
    assert [c["commission_id"] for c in out["cancellations"]] == [rows[4].id]
    assert db.get(AffiliateCommission, rows[4].id).status == CommissionStatus.CANCELLED
    ledger = ledger_snapshot.snapshot(db)["ledger_vs_subledger"]
    assert (ledger["2002_liability"], ledger["open_levels_2_10"]) == ("0.20", "0.20")       # 0.30 - the cancelled 0.10
    assert ledger["5001_expense"] == ledger["commissions_not_cancelled"] == "2.20"
    assert script.execute_cancellations(db)["cancellations"] == []                   # executed once
    _assert_all_journals_balance(db)


# ===========================================================================
# 4c. Sponsor cycle correction
# ===========================================================================

def test_cycle_correction_removes_only_the_named_link(world):
    from app.scripts import correct_sponsor_cycle as script

    db = world
    a = _user(db, "cya@example.com")
    b = _user(db, "cyb@example.com", sponsor=a)
    c = _user(db, "cyc@example.com", sponsor=b)
    below = _user(db, "cyd@example.com", sponsor=c)
    db.commit()
    a.sponsor_id = c.id                                                              # historical cycle a -> c -> b -> a
    db.commit()
    with pytest.raises(script.CorrectionRefused, match="not"):
        script.correct(db, a.id, b.id, evidence_ref="owner approval 1")              # wrong expected sponsor
    db.rollback()
    with pytest.raises(script.CorrectionRefused, match="not on a referral cycle"):
        script.correct(db, below.id, c.id, evidence_ref="owner approval 1")
    db.rollback()
    script.correct(db, a.id, c.id, evidence_ref="owner approval 1")
    db.rollback()                                                                    # dry run
    assert db.get(User, a.id).sponsor_id == c.id
    out = script.correct(db, a.id, c.id, evidence_ref="owner approval 1")
    db.commit()
    assert (out["status"], out["cycle_remaining"], db.get(User, a.id).sponsor_id) == ("corrected", False, None)
    assert [db.get(User, u.id).sponsor_id for u in (b, c, below)] == [a.id, b.id, c.id]
    audit = db.query(AuditTrail).filter(AuditTrail.action == script.AUDIT_ACTION).one()
    assert audit.old_values["sponsor_id"] == c.id and audit.new_values["sponsor_id"] is None
    assert script.correct(db, a.id, c.id, evidence_ref="owner approval 1")["status"] == "already_root"


def test_administrator_text_cannot_carry_a_reversal_marker(world):
    """The markers that stop a deposit from ever being validated again live in its notes:
    no reason, evidence or note typed by an administrator may contain one."""
    from app.services.financial_reversal import REVERSAL_MARKERS

    db = world
    member = _user(db, "mk@example.com")
    db.commit()
    maker, checker = cashier(db, "mk_maker"), cashier(db, "mk_checker")
    for marker in REVERSAL_MARKERS:
        with pytest.raises(mps.ManualPaymentError) as e:
            mps.record(db, maker, member.id, product_code="kyc", reason=f"Bank ref 77 {marker.upper()}", password=PASSWORD)
        assert e.value.code == "TEXT_NOT_ALLOWED"
    assert db.query(ManualPaymentConfirmation).count() == 0
    req = mps.record(db, maker, member.id, product_code="kyc", reason="Bank ref 2026-10-16/88", password=PASSWORD).request
    for kwargs in ({"evidence_reference": f"TX-1 {REVERSAL_MARKERS[1]}"},
                   {"evidence_reference": "TX-0xfeed02", "note": REVERSAL_MARKERS[0]}):
        with pytest.raises(mps.ManualPaymentError) as e:
            mps.confirm(db, checker, req.id, password=PASSWORD, **kwargs)
        assert e.value.code == "TEXT_NOT_ALLOWED"
    db.refresh(req)
    deposit = db.get(Deposit, req.deposit_id)
    assert (req.status, deposit.status, db.query(AffiliateCommission).count()) == ("REQUESTED", DepositStatus.PENDING, 0)


# ===========================================================================
# 5. Manual-payment queue: finance permission only (F2)
# ===========================================================================

def test_the_manual_payment_queue_is_visible_only_with_the_payment_permission(client, world):
    from app.services import admin_security as sec
    from tests.unit.test_admin_security_hardening import bearer, code_of, confirm, denials, grant

    db = world
    sponsor = person(db, "q_sponsor")
    member = person(db, "q_member", sponsor_id=sponsor.id)
    plain = person(db, "q_plain", admin=True)
    wildcard = person(db, "q_wild", admin=True, permissions=("all",))
    finance_other = person(db, "q_fin", admin=True, permissions=(pc.PERMISSION_MANAGE, pc.PERMISSION_PROCESS))
    maker, checker = cashier(db, "q_maker"), cashier(db, "q_checker")
    url = "/api/v1/admin/manual-payments"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=bearer(member)).status_code == 403                 # a member
    for actor in (plain, wildcard, finance_other):                                    # admins without the permission
        refused = client.get(url, headers=bearer(actor))
        assert (refused.status_code, code_of(refused)) == (403, "FORBIDDEN"), actor.username
        assert member.email not in refused.text
    assert [(d[0], d[2], d[3]) for d in denials(db)][-3:] == [(a.id, "view manual payments", "FORBIDDEN")
                                                            for a in (plain, wildcard, finance_other)]

    recorded = grant(client, maker, member)
    assert recorded.status_code == 200 and recorded.json()["status"] == "pending_confirmation"
    request_id = recorded.json()["request_id"]
    for viewer in (maker, checker):
        listed = client.get(url, headers=bearer(viewer), params={"status": "REQUESTED"})
        assert listed.status_code == 200 and [i["id"] for i in listed.json()["items"]] == [request_id]
        assert listed.json()["current_admin_id"] == viewer.id

    # Maker-checker is unchanged at the API: the maker cannot confirm; the checker can, once.
    assert code_of(confirm(client, maker, request_id)) == "SAME_ADMINISTRATOR"
    assert confirm(client, plain, request_id).status_code == 403
    done = confirm(client, checker, request_id)
    assert done.status_code == 200 and done.json()["status"] == "granted"
    assert code_of(confirm(client, checker, request_id)) == "ALREADY_DECIDED"
    db.expire_all()
    commissions = db.query(AffiliateCommission).all()
    assert [(c.user_id, c.level, c.commission_amount) for c in commissions] == [(sponsor.id, 1, Decimal("10.00"))]
    assert not {maker.id, checker.id} & {c.user_id for c in commissions}


def test_a_maker_or_checker_in_the_members_referral_line_is_refused_at_the_api(client, world):
    from tests.unit.test_admin_security_hardening import bearer, code_of, confirm, grant

    db = world
    upline_cashier = cashier(db, "q_upline")
    member = person(db, "q_down", sponsor_id=upline_cashier.id)
    other = cashier(db, "q_other")
    assert code_of(grant(client, upline_cashier, member)) == "COMMISSION_CONFLICT"            # maker would earn
    request_id = grant(client, other, member).json()["request_id"]
    assert code_of(confirm(client, upline_cashier, request_id)) == "COMMISSION_CONFLICT"      # checker would earn
    db.expire_all()
    assert db.query(AffiliateCommission).count() == 0
    assert db.get(ManualPaymentConfirmation, request_id).status == "REQUESTED"


# ===========================================================================
# 6. Final commission policy (owner, 2026-10-16): level 1 only; 20% standard;
#    40% on eligible ad-slot purchases for a permanently qualified sponsor
# ===========================================================================

def _ad_slot_commission(db, split, buyer, *, level=1, source_id=1):
    """The row an ad-slot revenue event would write (no such event exists yet; the calculator is the rule)."""
    row = AffiliateCommission(user_id=split.sponsor_user_id, source_user_id=buyer.id, level=level,
                              commission_type=CommissionType.KYC_PAYMENT, base_amount=split.gross,
                              commission_amount=split.sponsor_commission, commission_rate=split.sponsor_rate,
                              status=CommissionStatus.APPROVED, transaction_date=datetime.utcnow(),
                              business_model_version="NEW_V2", revenue_category="AD_SLOT_PURCHASE",
                              source_type="AD_SLOT_TEST", source_id=source_id)
    db.add(row)
    db.flush()
    return row


def test_standard_20_and_qualified_40_ad_slot_commissions_are_level_one_payable_and_direct_only(world):
    from app.services import ad_revenue_policy as ads
    from app.services import affiliate_rate_policy as rates
    from tests.unit.test_ad_revenue_policy import _qualify

    db = world
    grand = _user(db, "pol-grand@example.com")
    sponsor = _user(db, "pol-sponsor@example.com", sponsor=grand)
    buyer = _user(db, "pol-buyer@example.com", sponsor=sponsor)
    db.commit()
    assert (rates.STANDARD_DIRECT_RATE, rates.QUALIFIED_DIRECT_RATE) == (Decimal("0.20"), Decimal("0.40"))
    assert rates.QUALIFICATION_DIRECT_REFERRALS == 10000 and rates.QUALIFICATION_WINDOW_MONTHS == 6

    standard = ads.ad_slot_split(db, buyer_user_id=buyer.id, gross_amount="100.00")
    assert (standard.sponsor_user_id, standard.sponsor_rate, standard.sponsor_commission) == \
        (sponsor.id, Decimal("0.20"), Decimal("20.00"))                         # the direct sponsor only
    row20 = _ad_slot_commission(db, standard, buyer, source_id=1)
    _qualify(db, sponsor)
    special = ads.ad_slot_split(db, buyer_user_id=buyer.id, gross_amount="100.00")
    assert (special.sponsor_user_id, special.sponsor_rate, special.sponsor_commission) == \
        (sponsor.id, Decimal("0.40"), Decimal("40.00"))                         # replaces 20, never 60
    row40 = _ad_slot_commission(db, special, buyer, source_id=2)
    db.commit()
    # Both are level-1 NEW_V2 rows: accepted by the guards and never held.
    assert hold.is_payable(db, row20) and hold.is_payable(db, row40)
    assert sorted(r.id for r in cs.available_rows(db, sponsor.id)) == sorted([row20.id, row40.id])
    db.rollback()
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id == grand.id).count() == 0
    # The 40% is a level-1 rate: the same commission one level up cannot exist.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _ad_slot_commission(db, special, buyer, level=2, source_id=3)
    # A qualified sponsor's other categories keep the revenue-policy rate (the 40% is for ad slots only).
    for category in ("KYC_VERIFICATION", "MEMBERSHIP", "PLATFORM_SUBSCRIPTION", "MARKETPLACE_MARKUP", "SERVICE_FEE"):
        assert rates.direct_rate_for_category(db, db.get(User, sponsor.id), category) is None


def test_a_live_payment_pays_20_percent_to_the_direct_sponsor_only_even_when_qualified(world):
    from tests.unit.test_ad_revenue_policy import _qualify

    db = world
    grand = _user(db, "live-grand@example.com")
    sponsor = _user(db, "live-sponsor@example.com", sponsor=grand)
    buyer = _user(db, "live-buyer@example.com", sponsor=sponsor)
    db.commit()
    _qualify(db, sponsor)                                                        # 40% applies to ad slots only
    process_payment_validation(db, _deposit(db, buyer, "annual_membership"))     # $50 -> 20% = $10
    rows = db.query(AffiliateCommission).all()
    assert [(r.user_id, r.level, r.commission_amount, r.business_model_version) for r in rows] == \
        [(sponsor.id, 1, Decimal("10.00"), "NEW_V2")]                            # nobody above level 1
    assert hold.is_payable(db, rows[0])
    _assert_all_journals_balance(db)
