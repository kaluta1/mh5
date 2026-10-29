"""KYC commission at payment and individual automatic USDT BEP20 payouts
(owner rules, 2026-10-18).

* A confirmed KYC fee payment creates the direct sponsor's commission at once,
  available immediately (no hold); its cost waits in 1230 until the KYC revenue
  is recognized.
* Every wallet and every wallet change needs an administrator's approval.
* Every commission is paid by its OWN payout, bound to the approved wallet, as
  soon as it is available. No combining, no 24-hour interval.

The payout provider is a FAKE in every test; all data is SYNTHETIC.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import (
    AffiliateCashoutRequest,
    AffiliateCommission,
    CommissionStatus,
    CommissionType,
    PayoutWalletApproval,
)
from app.models.email import EmailDelivery
from app.models.payment import DepositStatus, ProductType
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services import payment_config
from app.services import payout_notifications as notes
from app.services import payout_wallet_approval as approvals
from app.services.commission_distribution import process_payment_validation
from app.services.financial_balances import get_commission_balance
from app.services.financial_integrity import FinancialIntegrityError
from app.services.financial_reversal import reverse_provider_refund
from app.services.nowpayments_service import finalize_deposit_from_nowpayments
from app.services.payment_accounting import payment_accounting
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import (  # noqa: F401
    LONG_AGO,
    NOW,
    OTHER_WALLET,
    PASSWORD,
    WALLET,
    FakeProvider,
    approve_wallet,
    cashouts,
    commission,
    configure,
    engine_on,
    ledger,
    member,
    no_network,
    run,
)
from tests.unit.test_new_business_model import (  # noqa: F401
    _assert_all_journals_balance,
    _balance,
    _deposit,
    _retired_legacy,
    world,
)

pytestmark = pytest.mark.unit


class DetailedProvider(FakeProvider):
    """A fake provider that also reports payout details (hash, address, reference)
    and its currency data, like the real one."""

    def __init__(self, *, contract="0x55d398326f99059fF775485246999027B3197955", network="bsc", **kw):
        super().__init__(**kw)
        self.contract, self.network = contract, network
        self.hashes = {}

    def payout_details(self, batch_id):
        created = self.created[int(batch_id.split("-")[1]) - 1]
        return {"status": self.statuses.get(batch_id, "PROCESSING"), "address": created["address"],
                "unique_external_id": created["external_id"], "currency": created["currency"],
                "hash": self.hashes.get(batch_id)}

    def currency_details(self, currency):
        return {"code": currency, "network": self.network, "smart_contract": self.contract}


def _pay_kyc(db, payer, *, code="kyc", tag=""):
    """A KYC fee confirmed through the real provider path."""
    dep = _deposit(db, payer, code, status=DepositStatus.PENDING, tag=tag)
    db.commit()
    assert finalize_deposit_from_nowpayments(db, dep, {"payment_status": "finished", "order_id": dep.order_id,
                                                       "payment_id": dep.external_payment_id}) is True
    db.commit()
    return dep


def _kyc_commission(db, sponsor, name="payer"):
    payer = member(db, name, sponsor=sponsor, wallet=None)
    _pay_kyc(db, payer, tag=name)
    return db.query(AffiliateCommission).filter(AffiliateCommission.source_user_id == payer.id).one()


def _deliveries(db, prefix):
    return db.query(EmailDelivery).filter(EmailDelivery.idempotency_key.like(f"{prefix}%")).all()


# ===========================================================================
# 1. KYC commission trigger and accounting
# ===========================================================================

def test_confirmed_kyc_payment_creates_the_commission_at_once_with_its_cost_deferred(ledger):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    payer = member(db, "payer", sponsor=sponsor, wallet=None)
    dep = _pay_kyc(db, payer)
    row = db.query(AffiliateCommission).one()
    assert (row.user_id, row.level, row.base_amount, row.commission_amount) == (sponsor.id, 1, Decimal("10.00"),
                                                                                Decimal("2.00"))
    assert row.status == CommissionStatus.APPROVED and row.commission_type == CommissionType.KYC_PAYMENT
    assert row.deposit_id == dep.id and row.business_model_version == "NEW_V2"
    # Available immediately: same instant, no hold.
    assert get_commission_balance(db, sponsor.id).available == Decimal("2.00")
    assert cs.summary(db, sponsor, now=row.transaction_date)["balances"]["available_unpaid"] == 2.0
    # Payment, commission and revenue are separate events.
    assert _balance(db, "1001") == Decimal("10.00") and _balance(db, "2113") == Decimal("-10.00")
    assert _balance(db, "1230") == Decimal("2.00") and _balance(db, "2001") == Decimal("-2.00")
    assert _balance(db, "5001") == 0 and _balance(db, "4001") == 0

    assert payment_accounting.post_kyc_verification_recognition_for_user(db, payer.id) is True
    assert _balance(db, "1230") == 0 and _balance(db, "5001") == Decimal("2.00")
    assert _balance(db, "4001") == Decimal("-8.00") and _balance(db, "2003") == Decimal("-2.00")
    assert payment_accounting.post_kyc_verification_recognition_for_user(db, payer.id) is False
    assert db.query(AffiliateCommission).count() == 1
    _assert_all_journals_balance(db)


def test_duplicate_payment_callbacks_create_one_commission_and_one_journal_set(ledger):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    payer = member(db, "payer", sponsor=sponsor, wallet=None)
    dep = _pay_kyc(db, payer)
    for _ in range(3):
        finalize_deposit_from_nowpayments(db, dep, {"payment_status": "finished", "order_id": dep.order_id})
        process_payment_validation(db, dep, defer_commit=True)
        db.commit()
    assert db.query(AffiliateCommission).count() == 1
    assert db.query(JournalEntry).count() == 2               # receipt + commission accrual


def test_no_sponsor_inactive_sponsor_or_unconfirmed_payment_creates_nothing(ledger):
    db = ledger
    lone = member(db, "lone", wallet=None)
    _pay_kyc(db, lone, tag="a")
    inactive = member(db, "inactive", method="CRYPTO")
    inactive.is_active = False
    db.commit()
    _pay_kyc(db, member(db, "p2", sponsor=inactive, wallet=None), tag="b")
    sponsor = member(db, "sponsor", method="CRYPTO")
    payer = member(db, "p3", sponsor=sponsor, wallet=None)
    for status in ("waiting", "failed", "expired"):
        dep = _deposit(db, payer, "kyc", status=DepositStatus.PENDING, tag=status)
        db.commit()
        finalize_deposit_from_nowpayments(db, dep, {"payment_status": status, "order_id": dep.order_id})
        db.commit()
    assert db.query(AffiliateCommission).count() == 0


def test_rejected_kyc_after_payment_keeps_the_commission_and_is_not_a_refund(ledger):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    row = _kyc_commission(db, sponsor)
    # The verification never gets approved: nothing is reversed automatically.
    assert row.status == CommissionStatus.APPROVED
    assert _balance(db, "2113") == Decimal("-10.00") and _balance(db, "1230") == Decimal("2.00")


def test_refund_before_payout_reverses_commission_and_deferred_cost(ledger):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    row = _kyc_commission(db, sponsor)
    dep = row.deposit
    assert reverse_provider_refund(db, dep, {"refund_amount": "10.00"}) is True
    db.refresh(row)
    assert row.status == CommissionStatus.CANCELLED
    for code in ("1001", "2113", "1230", "2001", "5001"):
        assert _balance(db, code) == 0, code
    assert reverse_provider_refund(db, dep, {"refund_amount": "10.00"}) is True      # replay: nothing new
    _assert_all_journals_balance(db)


def test_refund_after_approval_reverses_expense_recognition_too(ledger):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    payer = member(db, "payer", sponsor=sponsor, wallet=None)
    dep = _pay_kyc(db, payer)
    payment_accounting.post_kyc_verification_recognition_for_user(db, payer.id)
    assert reverse_provider_refund(db, dep, {"refund_amount": "10.00"}) is True
    for code in ("1230", "2001", "5001", "4001", "2113", "2003"):
        assert _balance(db, code) == 0, code
    _assert_all_journals_balance(db)


def test_refund_after_payout_records_a_receivable_never_a_deduction(ledger, engine_on):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    row = _kyc_commission(db, sponsor)
    provider = FakeProvider()
    run(db, provider)
    with pytest.raises(FinancialIntegrityError):
        reverse_provider_refund(db, row.deposit, {"refund_amount": "10.00"})    # payout open: refused
    db.rollback()
    provider.statuses["batch-1"] = "FINISHED"
    run(db, provider)
    other = _kyc_commission(db, sponsor, "payer2")                              # an unrelated balance
    assert reverse_provider_refund(db, row.deposit, {"refund_amount": "10.00"}) is True
    assert _balance(db, "1200") == Decimal("2.00")                              # receivable from the member
    assert _balance(db, "1230") == Decimal("2.00")                              # only the other commission's cost
    db.refresh(other)
    assert other.status == CommissionStatus.APPROVED and other.commission_amount == Decimal("2.00")
    _assert_all_journals_balance(db)


# ===========================================================================
# 2. KYC product consistency
# ===========================================================================

def test_retired_kyc_product_is_not_sold(client, ledger):
    db = ledger
    db.add(ProductType(code="kyc_verification", name="kyc_verification", price=10, currency="USD", validity_days=365))
    db.commit()
    user = member(db, "buyer", wallet=None)
    resp = client.post("/api/v1/payments/create", headers=auth(user),
                       json={"product_code": "kyc_verification", "amount": 10, "currency": "USD"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "KYC_PRODUCT_NOT_SOLD"


def test_a_paid_retired_kyc_product_is_honoured_once_as_a_kyc_payment(ledger):
    from app.crud import crud_deposit

    db = ledger
    db.add(ProductType(code="kyc_verification", name="kyc_verification", price=10, currency="USD", validity_days=365))
    db.commit()
    sponsor = member(db, "sponsor", method="CRYPTO")
    payer = member(db, "payer", sponsor=sponsor, wallet=None)
    dep = _pay_kyc(db, payer, code="kyc_verification")
    assert crud_deposit.deposit.get_valid_deposit_for_product(db, user_id=payer.id, product_code="kyc").id == dep.id
    assert crud_deposit.deposit.count_valid_deposits_for_product(db, user_id=payer.id, product_code="kyc") == 1
    assert db.query(AffiliateCommission).count() == 1                        # one commission, like a kyc payment
    assert payment_accounting.post_kyc_verification_recognition_for_user(db, payer.id) is True
    assert _balance(db, "2113") == 0 and _balance(db, "1230") == 0


def test_approval_recognises_the_oldest_unrecognised_kyc_payment(ledger):
    db = ledger
    sponsor = member(db, "sponsor", method="CRYPTO")
    payer = member(db, "payer", sponsor=sponsor, wallet=None)
    first = _pay_kyc(db, payer, tag="1")
    second = _pay_kyc(db, payer, tag="2")
    assert db.query(AffiliateCommission).count() == 2                        # each paid fee earns once
    payment_accounting.post_kyc_verification_recognition_for_user(db, payer.id)
    payment_accounting.post_kyc_verification_recognition_for_user(db, payer.id)
    assert _balance(db, "2113") == 0 and _balance(db, "1230") == 0
    assert first.id < second.id


# ===========================================================================
# 3. Wallet approval
# ===========================================================================

def _submit(client, db, user, address=WALLET):
    configure(db, wallet_email_verification_required=False)
    return client.patch("/api/v1/users/me/wallet", headers=auth(user),
                        json={"usdt_wallet_address": address, "payout_currency": "usdtbsc",
                              "current_password": PASSWORD})


def test_wallet_submission_is_pending_until_an_administrator_approves_it(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", wallet=None)
    admin = member(db, "boss", admin=True)
    row = _kyc_commission(db, user)
    assert _submit(client, db, user).json()["wallet_status"] == "PENDING_APPROVAL"
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"WALLET_PENDING_APPROVAL": 1} and provider.created == []
    summary = cs.summary(db, user)
    assert summary["status"] == "WALLET_APPROVAL_PENDING"
    assert summary["balances"]["awaiting_wallet_approval"] == 2.0
    assert summary["wallet_approval"]["status"] == "PENDING"
    assert len(_deliveries(db, "payout-wallet-submitted:")) == 1

    queue = client.get("/api/v1/admin/cashouts/wallet-approvals?status=PENDING", headers=auth(admin)).json()
    assert queue["total"] == 1 and queue["items"][0]["address"] == WALLET
    pending_id = queue["items"][0]["id"]
    resp = client.post(f"/api/v1/admin/cashouts/wallet-approvals/{pending_id}", headers=auth(admin),
                       json={"decision": "APPROVE", "current_password": PASSWORD})
    assert resp.status_code == 200 and resp.json()["status"] == "APPROVED"
    assert len(_deliveries(db, "payout-wallet-approved:")) == 1
    later = datetime.utcnow() + timedelta(hours=payment_config.load(db).wallet_hold_hours + 1)
    assert run(db, provider, now=later)["members"] == {"SUBMITTED": 1}
    out = cashouts(db, user)[0]
    assert (out.commission_id, out.wallet_approval_id, out.wallet_snapshot) == (row.id, pending_id, WALLET)
    assert db.query(AuditTrail).filter_by(action="PAYOUT_WALLET_APPROVED").count() == 1


def test_wallet_decisions_need_permission_password_and_never_self(client, ledger):
    db = ledger
    user = member(db, "m1", method="CRYPTO", wallet=None)
    _submit(client, db, user)
    pending = approvals.current(db, user.id)
    plain = member(db, "plain", admin=True, permissions=())
    with pytest.raises(approvals.WalletApprovalError) as forbidden:
        approvals.decide(db, plain, pending.id, decision="APPROVE", note=None, password=PASSWORD)
    assert forbidden.value.code == "FORBIDDEN"
    admin = member(db, "boss", admin=True)
    with pytest.raises(approvals.WalletApprovalError) as wrong:
        approvals.decide(db, admin, pending.id, decision="APPROVE", note=None, password="wrong")
    assert wrong.value.code == "REAUTH_REQUIRED"
    with pytest.raises(approvals.WalletApprovalError) as short:
        approvals.decide(db, admin, pending.id, decision="REJECT", note="no", password=PASSWORD)
    assert short.value.code == "REASON_REQUIRED"
    # Self-approval: an administrator's own wallet.
    configure(db, wallet_email_verification_required=False)
    cs.change_payout_wallet(db, admin, address=OTHER_WALLET, currency="usdtbsc", password=PASSWORD)
    own = approvals.current(db, admin.id)
    with pytest.raises(approvals.WalletApprovalError) as self_:
        approvals.decide(db, admin, own.id, decision="APPROVE", note=None, password=PASSWORD)
    assert self_.value.code == "SELF_ACTION_FORBIDDEN"
    approvals.decide(db, admin, pending.id, decision="APPROVE", note=None, password=PASSWORD)
    with pytest.raises(approvals.WalletApprovalError) as twice:
        approvals.decide(db, admin, pending.id, decision="REJECT", note="changed my mind", password=PASSWORD)
    assert twice.value.code == "ALREADY_DECIDED"


def test_the_database_refuses_a_self_decision(ledger):
    db = ledger
    user = member(db, "m1", wallet=WALLET)
    db.add(PayoutWalletApproval(user_id=user.id, address=WALLET, currency="usdtbsc", status="APPROVED",
                                submitted_at=NOW, decided_by=user.id, decided_at=NOW))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_rejected_wallet_is_never_paid_and_can_be_submitted_again(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO", wallet=None)
    admin = member(db, "boss", admin=True)
    _kyc_commission(db, user)
    _submit(client, db, user)
    approvals.decide(db, admin, approvals.current(db, user.id).id, decision="REJECT",
                     note="Address belongs to an exchange deposit", password=PASSWORD)
    assert len(_deliveries(db, "payout-wallet-rejected:")) == 1
    later = datetime.utcnow() + timedelta(days=5)
    assert run(db, FakeProvider(), now=later)["members"] == {"WALLET_REJECTED": 1}
    view = cs.summary(db, user)["wallet_approval"]
    assert view["status"] == "REJECTED" and view["reason"] == "Address belongs to an exchange deposit"
    assert _submit(client, db, user).json()["wallet_status"] == "PENDING_APPROVAL"   # same address, new decision
    assert db.query(PayoutWalletApproval).filter_by(user_id=user.id).count() == 2


def test_wallet_change_after_approval_needs_a_fresh_approval_and_stops_payouts(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")                        # approved WALLET (fixture)
    admin = member(db, "boss", admin=True)
    old = approvals.current(db, user.id)
    _submit(client, db, user, address=OTHER_WALLET)
    db.refresh(old)
    assert old.status == "SUPERSEDED"
    _kyc_commission(db, user)
    assert run(db, FakeProvider())["members"] == {"WALLET_PENDING_APPROVAL": 1}   # never to the old wallet
    approvals.decide(db, admin, approvals.current(db, user.id).id, decision="APPROVE", note=None, password=PASSWORD)
    later = datetime.utcnow() + timedelta(days=5)
    provider = FakeProvider()
    assert run(db, provider, now=later)["members"] == {"SUBMITTED": 1}
    assert provider.created[0]["address"] == OTHER_WALLET


def test_a_wallet_change_request_withdraws_the_approval_at_once_and_pauses_payouts(ledger, engine_on):
    """Owner rule 2026-10-19: asking for another address (email confirmation pending)
    stops payouts to the old one immediately; the new one needs its email link,
    an administrator's approval and the 72-hour hold."""
    db = ledger
    user = member(db, "m1", method="CRYPTO")                        # approved WALLET (fixture)
    admin = member(db, "boss", admin=True)
    old = approvals.current(db, user.id)
    asked = cs.change_payout_wallet(db, user, address=OTHER_WALLET, currency="usdtbsc", password=PASSWORD, now=NOW)
    assert asked.pending is True
    db.refresh(old)
    db.refresh(user)
    assert old.status == "SUPERSEDED" and user.usdt_wallet_address == WALLET   # the address is not changed yet
    withdrawn = db.query(AuditTrail).filter_by(action="PAYOUT_WALLET_APPROVAL_WITHDRAWN").one()
    assert withdrawn.new_values["reason"] == "WALLET_CHANGE_REQUESTED" and WALLET not in str(withdrawn.new_values)
    commission(db, user, "2.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"WALLET_UNVERIFIED": 1} and provider.created == []

    assert cs.confirm_payout_wallet(db, user, asked.token, now=NOW).status == cs.WALLET_PENDING_APPROVAL
    assert run(db, provider)["members"] == {"WALLET_PENDING_APPROVAL": 1}
    approvals.decide(db, admin, approvals.current(db, user.id).id, decision="APPROVE", note=None, password=PASSWORD)
    hold = timedelta(hours=payment_config.load(db).wallet_hold_hours)
    assert run(db, provider, now=NOW + hold - timedelta(minutes=1))["members"] == {"WALLET_ON_HOLD": 1}
    assert run(db, provider, now=NOW + hold + timedelta(minutes=1))["members"] == {"SUBMITTED": 1}
    assert provider.created[0]["address"] == OTHER_WALLET


def test_an_abandoned_change_request_leaves_the_old_address_unapproved(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    cs.change_payout_wallet(db, user, address=OTHER_WALLET, currency="usdtbsc", password=PASSWORD, now=NOW)
    commission(db, user, "2.00")
    later = NOW + timedelta(days=5)                                 # the link expired unused
    provider = FakeProvider()
    assert run(db, provider, now=later)["members"] == {"WALLET_UNVERIFIED": 1} and provider.created == []
    # Going back to the old address is a new submission: email link, approval, hold.
    again = cs.change_payout_wallet(db, user, address=WALLET, currency="usdtbsc", password=PASSWORD, now=later)
    assert again.pending is True
    cs.confirm_payout_wallet(db, user, again.token, now=later)
    assert approvals.current(db, user.id).status == "PENDING"
    assert run(db, provider, now=later + timedelta(days=4))["members"] == {"WALLET_PENDING_APPROVAL": 1}


def test_asking_again_for_the_approved_address_changes_nothing(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    approval = approvals.current(db, user.id)
    same = cs.change_payout_wallet(db, user, address=WALLET, currency="usdtbsc", password=PASSWORD, now=NOW)
    assert same.pending is False and same.state.status == cs.WALLET_VERIFIED
    db.refresh(approval)
    assert approval.status == "APPROVED"
    commission(db, user, "2.00")
    assert run(db, FakeProvider())["members"] == {"SUBMITTED": 1}


def test_one_approval_pays_every_later_commission_without_a_new_approval_or_hold(ledger, engine_on):
    """Owner rules 1, 5 and 6: an approved, confirmed wallet is paid every eligible
    commission, each on its own; neither the approval nor the hold restarts."""
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    approval = approvals.current(db, user.id)
    confirmed_at = user.payout_wallet_verified_at
    provider = FakeProvider()
    commission(db, user, "2.00", when=NOW - timedelta(days=1))
    assert run(db, provider)["members"] == {"SUBMITTED": 1}
    commission(db, user, "1.00", when=NOW + timedelta(days=3))
    assert run(db, provider, now=NOW + timedelta(days=3, hours=1))["members"] == {"SUBMITTED": 1}
    db.refresh(user)
    assert [c.wallet_approval_id for c in cashouts(db, user)] == [approval.id, approval.id]
    assert [c["amount"] for c in provider.created] == [Decimal("2.00"), Decimal("1.00")]
    assert user.payout_wallet_verified_at == confirmed_at
    assert db.query(PayoutWalletApproval).filter_by(user_id=user.id).count() == 1


def test_a_wallet_changed_after_reservation_is_never_paid(ledger, engine_on, monkeypatch):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    real = cs.reserve

    def reserve_then_reapprove_other(db_, user_, rows, **kwargs):
        out = real(db_, user_, rows, **kwargs)
        target = db_.query(type(user_)).filter_by(id=user_.id).one()
        target.usdt_wallet_address = OTHER_WALLET
        db_.commit()
        approve_wallet(db_, target)                                   # another approval than the one reserved
        return out

    monkeypatch.setattr(cs, "reserve", reserve_then_reapprove_other)
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"WALLET_CHANGED": 1}
    assert provider.created == [] and cashouts(db, user)[0].status == "cancelled"


# ===========================================================================
# 4. Individual payouts
# ===========================================================================

def test_every_commission_gets_its_own_payout_with_a_deterministic_reference(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    rows = [commission(db, user, amount) for amount in ("1.00", "2.00", "3.00")]
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 3}
    assert [c["amount"] for c in provider.created] == [Decimal("1.00"), Decimal("2.00"), Decimal("3.00")]
    assert [c["external_id"] for c in provider.created] == [f"c{r.id}-a1" for r in rows]
    assert [o.commission_id for o in cashouts(db, user)] == [r.id for r in rows]
    for i in range(1, 4):
        provider.statuses[f"batch-{i}"] = "FINISHED"
    assert run(db, provider)["reconciled"] == {"COMPLETED": 3}
    assert all(r.status == CommissionStatus.PAID for r in db.query(AffiliateCommission).all())
    assert db.query(JournalEntry).filter(JournalEntry.description.like("Affiliate Cashout #%")).count() == 3
    _assert_all_journals_balance(db)


def test_no_artificial_interval_a_new_commission_is_paid_right_after_the_last(ledger, engine_on):
    db = ledger
    assert payment_config.load(db).min_hours_between_payouts == 0
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    provider = FakeProvider()
    run(db, provider)
    provider.statuses["batch-1"] = "FINISHED"
    run(db, provider)
    commission(db, user, "2.00")
    assert run(db, provider, now=NOW + timedelta(minutes=1))["members"] == {"SUBMITTED": 1}


def test_a_second_live_attempt_for_the_same_commission_is_refused_by_the_database(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")
    run(db, FakeProvider())
    db.add(AffiliateCashoutRequest(user_id=user.id, gross_amount=Decimal("2.00"), fee=0, net_amount=Decimal("2.00"),
                                   status="processing", cashout_method="CRYPTO", commission_id=row.id,
                                   payout_reference="intent:c-duplicate"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_second_worker_finds_nothing_to_pay(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    provider = FakeProvider()
    facts = {"balance": Decimal("1000"), "minimum": Decimal("0.10")}
    assert engine.process_member(db, user.id, provider, facts=facts, now=NOW) == "SUBMITTED"
    assert engine.process_member(db, user.id, provider, facts=facts, now=NOW) == "NOTHING_TO_PAY"
    assert len(provider.created) == 1


def test_insufficient_treasury_and_provider_minimum_keep_the_commission_unpaid(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    assert run(db, FakeProvider(balance="1.00"))["members"] == {"INSUFFICIENT_PROVIDER_BALANCE": 1}
    assert run(db, FakeProvider(minimum="5.00"))["members"] == {"BELOW_PROVIDER_MINIMUM": 1}
    small = member(db, "m2", method="CRYPTO", wallet=OTHER_WALLET)
    commission(db, small, "0.50")                                     # below the $1 crypto minimum
    report = run(db, FakeProvider())
    assert report["members"]["BELOW_MINIMUM"] == 1
    assert get_commission_balance(db, small.id).available == Decimal("0.50")      # kept, never combined


def test_a_one_dollar_commission_is_paid_on_its_own_with_the_providers_real_figures(ledger, engine_on):
    # Owner rule 2026-10-18: the automatic payout minimum is $1.00. Minimum and
    # fee are the values NOWPayments reported for usdtbsc on 2026-10-18.
    db = ledger
    assert cs.crypto_minimum(db) == Decimal("1.00")
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "1.00")
    assert run(db, FakeProvider(balance="0", minimum="0.04418904", fee="0.02209452"))["members"] == \
        {"INSUFFICIENT_PROVIDER_BALANCE": 1}
    provider = FakeProvider(balance="1000", minimum="0.04418904", fee="0.02209452")
    assert run(db, provider)["members"] == {"SUBMITTED": 1}
    assert [c["amount"] for c in provider.created] == [Decimal("1.00")]     # the provider takes its fee out of it
    assert cashouts(db, user)[0].gross_amount == Decimal("1.00")


def test_a_small_old_commission_never_holds_back_a_newer_one(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    small = commission(db, user, "0.50", when=NOW - timedelta(days=5))     # below the $1 minimum
    large = commission(db, user, "2.00", when=NOW - timedelta(days=1))
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 1}
    assert provider.created[0]["external_id"] == f"c{large.id}-a1"
    db.refresh(small)
    assert small.status == CommissionStatus.APPROVED and small.payout_reference is None   # kept, unpaid
    assert run(db, provider)["members"] == {"BELOW_MINIMUM": 1}            # nothing else payable on its own


def test_timeout_is_unknown_never_resent_and_found_by_its_reference(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")

    def timeout(**_k):
        raise TimeoutError("no answer")

    provider = DetailedProvider(create=timeout)
    assert run(db, provider)["members"] == {"OUTCOME_UNKNOWN": 1}
    assert len(_deliveries(db, "payout-delayed:")) == 1
    for _ in range(3):
        run(db, provider)
    assert len(provider.created) == 1                                  # never a second transfer
    provider.find_payout = lambda ref: {"batch_id": "batch-1", "status": "FINISHED", "address": WALLET,
                                        "unique_external_id": ref}
    provider.statuses["batch-1"] = "FINISHED"
    provider.hashes["batch-1"] = "0x" + "c" * 64
    run(db, provider)
    run(db, provider)
    out = cashouts(db, user)[0]
    assert out.status == "completed" and out.tx_hash == "0x" + "c" * 64
    db.refresh(row)
    assert row.status == CommissionStatus.PAID


def test_a_worker_interrupted_after_hand_over_is_looked_up_never_resent(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")
    db.add(AffiliateCashoutRequest(user_id=user.id, gross_amount=Decimal("2.00"), fee=0, net_amount=Decimal("2.00"),
                                   status="processing", cashout_method="CRYPTO", commission_id=row.id,
                                   wallet_snapshot=WALLET, payout_currency="usdtbsc",
                                   payout_reference=f"intent:c{row.id}-a1", requested_at=NOW - timedelta(hours=1)))
    row.payout_reference = f"intent:c{row.id}-a1"
    db.commit()
    provider = DetailedProvider()
    provider.find_payout = lambda ref: None
    report = run(db, provider, now=NOW)
    assert report["reconciled"] == {"NOT_LOCATED": 1} and provider.created == []
    out = cashouts(db, user)[0]
    assert (out.status, out.failure_code) == ("unknown", "WORKER_INTERRUPTED")


def test_failed_transfer_is_released_and_retried_as_a_new_attempt(ledger, engine_on):
    db = ledger
    configure(db, retry_backoff_hours=1)
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")
    provider = FakeProvider()
    run(db, provider)
    provider.statuses["batch-1"] = "REJECTED"
    run(db, provider)
    assert cashouts(db, user)[0].status == "failed" and len(_deliveries(db, "payout-failed:")) == 1
    assert run(db, provider, now=NOW + timedelta(hours=2))["members"] == {"SUBMITTED": 1}
    assert provider.created[1]["external_id"] == f"c{row.id}-a2"


def test_a_refused_wallet_is_a_failed_attempt_that_sends_nothing_and_keeps_the_commission(ledger, engine_on):
    # The provider refusing the address (an address-whitelist rule, an invalid wallet)
    # answers 4xx at creation: nothing left, the commission waits for the next attempt.
    from app.services import nowpayments_service as nowpayments
    db = ledger
    configure(db, retry_backoff_hours=1)
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")

    def refuse(**_k):
        raise nowpayments.NowPaymentsError("NowPayments create -> 400", status_code=400, stage="create")

    provider = DetailedProvider(create=refuse)
    assert run(db, provider)["members"] == {"PROVIDER_REFUSED": 1}
    out = cashouts(db, user)[0]
    assert (out.status, out.failure_code) == ("failed", "PROVIDER_REFUSED")
    assert len(_deliveries(db, "payout-failed:")) == 1
    db.refresh(row)
    assert row.status != CommissionStatus.PAID and row.payout_reference is None
    run(db, provider)                                                  # inside the back-off: no new attempt
    assert len(provider.created) == 1


def test_a_refused_server_ip_stops_the_cycle_and_is_not_the_members_failure(ledger, engine_on):
    from app.services import nowpayments_service as nowpayments
    db = ledger
    first, second = member(db, "m1", method="CRYPTO"), member(db, "m2", method="CRYPTO")
    commission(db, first, "2.00")
    commission(db, second, "2.00")

    def refuse(**_k):
        raise nowpayments.NowPaymentsError("NowPayments create -> 403", status_code=403, stage="create",
                                           ip_refused=True)

    provider = DetailedProvider(create=refuse)
    report = run(db, provider)
    assert report["members"] == {"PROVIDER_IP_NOT_WHITELISTED": 1} and len(provider.created) == 1
    out = cashouts(db)[0]
    assert (out.status, out.failure_code) == ("cancelled", "PROVIDER_IP_NOT_WHITELISTED")
    assert _deliveries(db, "payout-failed:") == []


def test_completed_payout_records_hash_explorer_link_and_emails_once(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    provider = DetailedProvider()
    run(db, provider)
    assert notes.payout_outcome(db, cashouts(db, user)[0].id, "COMPLETED") is False   # not settled: no email
    provider.statuses["batch-1"] = "FINISHED"
    provider.hashes["batch-1"] = "0x" + "a" * 64
    run(db, provider)
    out = cashouts(db, user)[0]
    view = cs.cashout_dict(out)
    assert view["tx_hash"] == "0x" + "a" * 64
    assert view["explorer_url"] == "https://bscscan.com/tx/0x" + "a" * 64
    notes.payout_outcome(db, out.id, "COMPLETED")                      # replay
    assert len(_deliveries(db, "payout-completed:")) == 1


def test_payout_asset_must_be_usdt_bep20_on_chain_56(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    wrong = DetailedProvider(contract="0x" + "1" * 40)
    assert run(db, wrong)["stopped"] == "PAYOUT_ASSET_MISMATCH" and wrong.created == []
    other_chain = DetailedProvider(network="eth")
    assert run(db, other_chain)["stopped"] == "PAYOUT_ASSET_MISMATCH"
    assert run(db, DetailedProvider())["members"] == {"SUBMITTED": 1}


def test_historical_held_commissions_are_never_paid_or_shown_as_available(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    payer = member(db, "hp", wallet=None)
    for status in (CommissionStatus.APPROVED, CommissionStatus.PENDING):
        db.add(AffiliateCommission(user_id=user.id, source_user_id=payer.id, commission_type=CommissionType.KYC_PAYMENT,
                                   level=1, base_amount=Decimal("10"), commission_amount=Decimal("3.00"),
                                   status=status, transaction_date=LONG_AGO, business_model_version=None))
    db.commit()
    commission(db, user, "2.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 1}
    assert [c["amount"] for c in provider.created] == [Decimal("2.00")]
    balances = cs.summary(db, user)["balances"]
    assert balances["held"] == 6.0 and balances["pending"] == 0.0 and balances["available_unpaid"] == 0.0
    assert cs.summary(db, user)["payable_amount"] == 0.0


def test_emergency_pause_stops_new_payouts_but_keeps_reconciling(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    admin = member(db, "boss", admin=True)
    commission(db, user, "2.00")
    provider = FakeProvider()
    run(db, provider)
    resp = client.post("/api/v1/admin/finance/payouts/pause", headers=auth(admin),
                       json={"reason": "suspicious wallet activity", "current_password": PASSWORD})
    assert resp.status_code == 200, resp.text
    assert payment_config.load(db).crypto_auto_payout_enabled is False
    commission(db, user, "2.00")
    provider.statuses["batch-1"] = "FINISHED"
    report = run(db, provider)
    assert report["enabled"] is False and report["reconciled"] == {"COMPLETED": 1}
    assert len(provider.created) == 1
    bad = client.post("/api/v1/admin/finance/payouts/pause", headers=auth(user),
                      json={"reason": "suspicious wallet activity", "current_password": PASSWORD})
    assert bad.status_code in (401, 403)


def test_commission_to_payout_reconciliation_lists_each_commission(client, ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    admin = member(db, "boss", admin=True)
    commission(db, user, "2.00")
    provider = FakeProvider()
    run(db, provider)
    provider.statuses["batch-1"] = "FINISHED"
    run(db, provider)
    data = client.get("/api/v1/admin/cashouts/commission-payouts", headers=auth(admin)).json()
    assert data["checked"] == 1 and data["items"][0]["status"] == "PAID"
    assert data["problems"][0]["problems"] == ["COMPLETED_WITHOUT_HASH"]   # the plain fake reports no hash


# ===========================================================================
# 5. Wallet-missing notification
# ===========================================================================

def test_missing_wallet_email_is_sent_once_per_commission_batch(ledger):
    db = ledger
    sponsor = member(db, "sponsor", wallet=None)
    _kyc_commission(db, sponsor, "p1")
    _kyc_commission(db, sponsor, "p2")
    assert notes.sweep(db) == 1                                          # one email for both
    assert notes.sweep(db) == 0                                          # never twice
    _kyc_commission(db, sponsor, "p3")
    assert notes.sweep(db) == 1                                          # a new commission: one more
    assert len(_deliveries(db, f"commission-wallet-missing:{sponsor.id}:")) == 2
    assert all(c.wallet_notice_at is not None for c in db.query(AffiliateCommission).all())


def test_no_wallet_email_while_a_wallet_waits_for_approval_or_is_approved(client, ledger):
    db = ledger
    approved = member(db, "approved", method="CRYPTO")
    _kyc_commission(db, approved, "p1")
    waiting = member(db, "waiting", method="CRYPTO", wallet=None)
    _submit(client, db, waiting)
    _kyc_commission(db, waiting, "p2")
    assert notes.sweep(db) == 0


# ===========================================================================
# Independent activation: switching the provider on never starts payouts
# ===========================================================================

def test_the_activation_switch_is_off_unless_the_server_sets_it():
    assert settings.AUTOMATIC_PAYOUT_ACTIVATED is False


@pytest.mark.parametrize("provider_on,activated,expected", [
    (False, False, {}),
    (True, False, {}),                         # the dangerous case: provider back on, activation still off
    (False, True, {}),
    (True, True, {"SUBMITTED": 1}),            # everything mocked: FakeProvider
])
def test_a_payout_is_created_only_with_the_provider_on_and_payouts_activated(ledger, engine_on, monkeypatch,
                                                                              provider_on, activated, expected):
    db = ledger
    monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", activated)
    configure(db, provider_enabled=provider_on)
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")
    provider = FakeProvider()
    report = run(db, provider)
    assert report["members"] == expected
    assert len(provider.created) == len(expected)
    db.refresh(row)
    if not expected:
        assert report["enabled"] is False
        assert cashouts(db, user) == [] and row.status != CommissionStatus.PAID
    _assert_all_journals_balance(db)


def test_activation_withdrawn_after_reservation_releases_it_and_sends_nothing(ledger, engine_on, monkeypatch):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    provider = FakeProvider()
    real_lock = payment_config.lock_settings

    def lock_after_withdrawal(session):           # the operator deactivates between reservation and hand-over
        monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", False)
        return real_lock(session)

    monkeypatch.setattr(payment_config, "lock_settings", lock_after_withdrawal)
    facts = {"balance": Decimal("1000"), "minimum": Decimal("0.10")}
    assert engine.process_member(db, user.id, provider, facts=facts, now=NOW) == "ENGINE_DISABLED"
    assert provider.created == []
    assert [o.status for o in cashouts(db, user)] == ["cancelled"]
    _assert_all_journals_balance(db)


from app.services import nowpayments_service as _nowpayments  # noqa: E402

_REAL_CREATE_PAYOUT = _nowpayments.create_single_payout_sync   # captured before no_network replaces it


def test_the_provider_call_itself_refuses_without_activation(monkeypatch):
    nowpayments = _nowpayments

    def no_http(*_a, **_k):
        raise AssertionError("an HTTP client was opened")

    monkeypatch.setattr(nowpayments.httpx, "Client", no_http)
    monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", False)
    with pytest.raises(nowpayments.NowPaymentsError) as refused:
        _REAL_CREATE_PAYOUT(wallet_address=WALLET, amount=Decimal("2.00"), currency="usdtbsc",
                            external_id="c1-a1", credentials=None)
    assert refused.value.status_code == 403 and refused.value.code == "PAYOUTS_NOT_ACTIVATED"


def test_status_names_the_missing_activation(ledger, engine_on, monkeypatch):
    db = ledger
    monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", False)
    status = engine.crypto_payout_status(db)
    assert status["can_create_payouts"] is False
    assert "NOT_ACTIVATED" in [b["code"] for b in status["blockers"]]
    assert status["switches"]["activation"] is False
    assert engine.engine_status(db)["activation"] is False and engine.engine_status(db)["enabled"] is False
