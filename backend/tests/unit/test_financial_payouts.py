from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus, CommissionType
from app.models.user import User
from app.services import commission_payout_service as payouts


def _setup(db):
    user = User(
        email="cashout@test.com",
        username="cashout",
        hashed_password="unused",
        is_active=True,
        is_deleted=False,
        usdt_wallet_address="0x" + "a" * 40,
        payout_currency="usdtbsc",
    )
    source = User(
        email="source@test.com",
        username="source",
        hashed_password="unused",
        is_active=True,
        is_deleted=False,
    )
    db.add_all([user, source])
    for code, kind in (
        ("1001", AccountType.ASSET),
        ("2001", AccountType.LIABILITY),
        ("2002", AccountType.LIABILITY),
        ("4005", AccountType.REVENUE),
    ):
        db.add(ChartOfAccounts(account_code=code, account_name=code, account_type=kind))
    db.flush()
    rows = []
    for index, amount in enumerate(("60.00", "60.00"), start=1):
        row = AffiliateCommission(
            user_id=user.id,
            source_user_id=source.id,
            commission_type=CommissionType.KYC_PAYMENT,
            level=index,
            base_amount=Decimal("600.00"),
            commission_amount=Decimal(amount),
            status=CommissionStatus.APPROVED,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return user, rows


def test_partial_commission_withdrawal_is_rejected_without_provider_call(db, monkeypatch):
    user, _rows = _setup(db)
    monkeypatch.setattr(payouts, "payouts_configured", lambda: True)
    called = []
    monkeypatch.setattr(payouts, "send_single_payout_sync", lambda **kwargs: called.append(kwargs))
    with pytest.raises(ValueError, match="whole-commission"):
        payouts.process_manual_withdrawal_sync(db, user, Decimal("100.00"), idempotency_key="partial")
    db.rollback()
    assert called == []
    assert db.query(AffiliateCashoutRequest).count() == 0
    assert all(row.status == CommissionStatus.APPROVED for row in db.query(AffiliateCommission).all())


def test_payout_intent_commits_then_posts_once(db, monkeypatch):
    user, rows = _setup(db)
    monkeypatch.setattr(payouts, "payouts_configured", lambda: True)
    provider_calls = []

    def provider(**kwargs):
        provider_calls.append(kwargs)
        assert db.query(AffiliateCashoutRequest).filter_by(status="processing").count() == 1
        assert all(
            str(row.payout_reference).startswith("intent:")
            for row in db.query(AffiliateCommission).order_by(AffiliateCommission.id).all()
        )
        return {"id": "provider-batch-1"}

    monkeypatch.setattr(payouts, "send_single_payout_sync", provider)
    first = payouts.process_manual_withdrawal_sync(
        db, user, Decimal("120.00"), idempotency_key="one-payout"
    )
    second = payouts.process_manual_withdrawal_sync(
        db, user, Decimal("120.00"), idempotency_key="one-payout"
    )
    assert first["status"] == second["status"] == "completed"
    assert len(provider_calls) == 1
    assert all(row.status == CommissionStatus.PAID for row in db.query(AffiliateCommission).all())
    cashout = db.query(AffiliateCashoutRequest).one()
    assert cashout.status == "completed"
    assert "provider:provider-batch-1" in cashout.payout_reference
    journal = db.query(JournalEntry).filter_by(description=f"Affiliate Cashout #{cashout.id}").one()
    assert journal.total_debit == journal.total_credit == Decimal("120.00")


def test_provider_failure_is_not_blindly_retried(db, monkeypatch):
    user, _rows = _setup(db)
    monkeypatch.setattr(payouts, "payouts_configured", lambda: True)
    provider_calls = []

    def provider(**kwargs):
        provider_calls.append(kwargs)
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(payouts, "send_single_payout_sync", provider)
    with pytest.raises(ValueError, match="outcome is unknown"):
        payouts.process_manual_withdrawal_sync(
            db, user, Decimal("120.00"), idempotency_key="unknown-payout"
        )
    replay = payouts.process_manual_withdrawal_sync(
        db, user, Decimal("120.00"), idempotency_key="unknown-payout"
    )
    assert replay["status"] == "unknown"
    assert len(provider_calls) == 1
    assert payouts.get_approved_balance_sync(db, user.id) == Decimal("0.00")
    assert db.query(AffiliateCashoutRequest).one().status == "unknown"


def test_insufficient_balance_never_calls_provider(db, monkeypatch):
    user, _rows = _setup(db)
    monkeypatch.setattr(payouts, "payouts_configured", lambda: True)
    called = []
    monkeypatch.setattr(payouts, "send_single_payout_sync", lambda **kwargs: called.append(kwargs))
    with pytest.raises(ValueError, match="Insufficient"):
        payouts.process_manual_withdrawal_sync(
            db, user, Decimal("180.00"), idempotency_key="too-much"
        )
    assert called == []


def test_payout_rejects_unledgered_network_before_provider_call(db, monkeypatch):
    user, _rows = _setup(db)
    user.payout_currency = "usdterc20"
    db.commit()
    monkeypatch.setattr(payouts, "payouts_configured", lambda: True)
    called = []
    monkeypatch.setattr(payouts, "send_single_payout_sync", lambda **kwargs: called.append(kwargs))
    with pytest.raises(ValueError, match="Only USDT on BSC"):
        payouts.process_manual_withdrawal_sync(
            db, user, Decimal("120.00"), idempotency_key="wrong-network"
        )
    assert called == []
