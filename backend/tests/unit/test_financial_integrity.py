from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest

from app.api.api_v1.endpoints import payments as payments_endpoint
from app.core.config import settings
from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.fmr import MemberFmpBalance, MemberFmpLedger
from app.models.user import User
from app.services.affiliate_hierarchy import (
    AffiliateHierarchyError,
    MAX_AFFILIATE_LEVELS,
    validate_sponsor_assignment,
    walk_sponsor_chain,
)
from app.services.financial_integrity import FinancialIntegrityError, money
from app.services.financial_reversal import reverse_provider_refund
from app.services.nowpayments_service import finalize_deposit_from_nowpayments


def _user(db, email: str, *, sponsor_id=None, wallet=None) -> User:
    row = User(
        email=email,
        hashed_password="not-used",
        username=email.split("@")[0],
        is_active=True,
        is_deleted=False,
        sponsor_id=sponsor_id,
        usdt_wallet_address=wallet,
        payout_currency="usdtbsc",
    )
    db.add(row)
    db.flush()
    return row


def _account(db, code: str, account_type: AccountType) -> ChartOfAccounts:
    row = ChartOfAccounts(
        account_code=code,
        account_name=f"Account {code}",
        account_type=account_type,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_decimal_money_rounds_centrally_without_binary_float():
    assert money("10.005") == Decimal("10.01")
    assert money(0.1) + money(0.2) == Decimal("0.30")
    with pytest.raises(FinancialIntegrityError):
        money("NaN")


def test_affiliate_walk_stops_at_ten_levels(db):
    sponsor_id = None
    users = []
    for index in range(12, -1, -1):
        row = _user(db, f"level{index}@test.com", sponsor_id=sponsor_id)
        users.append(row)
        sponsor_id = row.id
    db.commit()

    chain = walk_sponsor_chain(db, users[-1].id, max_levels=99)
    assert len(chain.hops) == MAX_AFFILIATE_LEVELS
    assert [hop.level for hop in chain.hops] == list(range(1, 11))
    assert chain.stopped_reason == "max_levels"


def test_affiliate_cycle_and_self_referral_fail_closed(db):
    first = _user(db, "first@test.com")
    second = _user(db, "second@test.com", sponsor_id=first.id)
    first.sponsor_id = second.id
    db.commit()

    chain = walk_sponsor_chain(db, first.id)
    assert chain.hops == (chain.hops[0],)
    assert chain.stopped_reason == "cycle"
    with pytest.raises(AffiliateHierarchyError):
        validate_sponsor_assignment(db, user_id=first.id, sponsor_id=first.id)


def test_sponsor_reassignment_is_rejected(db):
    sponsor = _user(db, "sponsor@test.com")
    replacement = _user(db, "replacement@test.com")
    member = _user(db, "member@test.com", sponsor_id=sponsor.id)
    db.commit()
    with pytest.raises(AffiliateHierarchyError):
        validate_sponsor_assignment(db, user_id=member.id, sponsor_id=replacement.id)


def test_payment_amount_tampering_is_rejected_before_provider_call(
    client, auth_headers, db, monkeypatch
):
    product = ProductType(code="secure-product", name="Secure", price=Decimal("10.00"), currency="USD")
    db.add(product)
    db.commit()
    calls = []

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return {"payment_id": "provider-1", "pay_address": "address", "pay_amount": "10"}

    monkeypatch.setattr(payments_endpoint, "now_create_payment", fake_create)
    response = client.post(
        "/api/v1/payments/create",
        headers={**auth_headers, "Idempotency-Key": "tamper-test"},
        json={"amount": 1, "currency": "usd", "product_code": "secure-product"},
    )
    assert response.status_code == 400
    assert calls == []
    assert db.query(Deposit).count() == 0


def test_payment_creation_uses_server_price_and_idempotency(
    client, auth_headers, db, monkeypatch
):
    product = ProductType(code="server-priced", name="Server priced", price=Decimal("10.00"), currency="USD")
    db.add(product)
    db.commit()
    calls = []

    async def fake_create(**kwargs):
        calls.append(kwargs)
        return {
            "payment_id": "provider-order",
            "payment_status": "waiting",
            "pay_address": "address",
            "pay_amount": "10",
            "pay_currency": "usdtbsc",
        }

    monkeypatch.setattr(payments_endpoint, "now_create_payment", fake_create)
    headers = {**auth_headers, "Idempotency-Key": "same-order"}
    payload = {"amount": "10.00", "currency": "USD", "product_code": "server-priced"}
    first = client.post("/api/v1/payments/create", headers=headers, json=payload)
    second = client.post("/api/v1/payments/create", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["deposit_id"] == second.json()["deposit_id"]
    assert calls[0]["price_amount"] == Decimal("10.00")
    assert len(calls) == 1
    assert db.query(Deposit).one().amount == Decimal("10.00000000")


def test_provider_payment_identity_mismatch_never_validates(db):
    user = _user(db, "payer@test.com")
    product = ProductType(code="identity-check", name="Identity", price=10, currency="USD")
    db.add(product)
    db.flush()
    deposit = Deposit(
        user_id=user.id,
        product_type_id=product.id,
        amount=10,
        currency="USD",
        order_id="local-order",
        external_payment_id="local-payment",
        status=DepositStatus.PENDING,
    )
    db.add(deposit)
    db.commit()
    with pytest.raises(FinancialIntegrityError):
        finalize_deposit_from_nowpayments(
            db,
            deposit,
            {
                "payment_status": "finished",
                "order_id": "other-order",
                "payment_id": "local-payment",
                "price_amount": 10,
                "price_currency": "usd",
            },
            defer_commit=True,
        )
    db.rollback()
    assert db.get(Deposit, deposit.id).status == DepositStatus.PENDING


def test_webhook_signature_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "webhook-secret")
    response = client.post(
        "/api/v1/webhooks/nowpayments",
        headers={"x-nowpayments-sig": "bad"},
        json={"order_id": "missing", "payment_status": "finished"},
    )
    assert response.status_code == 403


def test_webhook_replay_has_one_financial_result(client, db, monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "webhook-secret")
    user = _user(db, "webhook@test.com")
    product = ProductType(code="no-commission", name="No commission", price=10, currency="USD")
    db.add(product)
    db.flush()
    deposit = Deposit(
        user_id=user.id,
        product_type_id=product.id,
        amount=10,
        currency="USD",
        order_id="webhook-order",
        external_payment_id="webhook-payment",
        status=DepositStatus.PENDING,
    )
    db.add(deposit)
    db.commit()
    body = {
        "order_id": "webhook-order",
        "payment_id": "webhook-payment",
        "payment_status": "finished",
        "price_amount": 10,
        "price_currency": "usd",
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(b"webhook-secret", canonical.encode(), hashlib.sha512).hexdigest()
    headers = {"x-nowpayments-sig": signature}
    for _ in range(5):
        response = client.post("/api/v1/webhooks/nowpayments", headers=headers, json=body)
        assert response.status_code == 200, response.text
    assert db.get(Deposit, deposit.id).status == DepositStatus.VALIDATED
    assert db.query(AffiliateCommission).count() == 0


def test_full_refund_is_compensating_and_idempotent(db):
    cash = _account(db, "1001", AccountType.ASSET)
    revenue = _account(db, "4001", AccountType.REVENUE)
    _account(db, "1200", AccountType.ASSET)
    _account(db, "2001", AccountType.LIABILITY)
    _account(db, "2002", AccountType.LIABILITY)
    user = _user(db, "refund@test.com")
    sponsor = _user(db, "refund-sponsor@test.com")
    product = ProductType(code="refundable", name="Refundable", price=10, currency="USD")
    db.add(product)
    db.flush()
    deposit = Deposit(
        user_id=user.id,
        product_type_id=product.id,
        amount=10,
        currency="USD",
        order_id="refund-order",
        external_payment_id="refund-payment",
        status=DepositStatus.VALIDATED,
    )
    db.add(deposit)
    db.flush()
    entry = JournalEntry(
        entry_number="JE-ORIGINAL-REFUND",
        entry_date=deposit.created_at,
        description=f"Payment - Deposit #{deposit.id}",
        total_debit=10,
        total_credit=10,
        status="posted",
    )
    db.add(entry)
    db.flush()
    db.add_all(
        [
            JournalLine(entry_id=entry.id, account_id=cash.id, debit_amount=10, credit_amount=0),
            JournalLine(entry_id=entry.id, account_id=revenue.id, debit_amount=0, credit_amount=10),
            AffiliateCommission(
                user_id=sponsor.id,
                source_user_id=user.id,
                product_type_id=product.id,
                deposit_id=deposit.id,
                commission_type=CommissionType.KYC_PAYMENT,
                level=1,
                base_amount=10,
                commission_amount=1,
                status=CommissionStatus.APPROVED,
            ),
        ]
    )
    db.commit()
    payload = {
        "payment_status": "refunded",
        "order_id": "refund-order",
        "payment_id": "refund-payment",
        "price_amount": 10,
        "price_currency": "usd",
    }
    assert reverse_provider_refund(db, deposit, payload) is True
    first_count = db.query(JournalEntry).count()
    assert reverse_provider_refund(db, deposit, payload) is True
    assert db.query(JournalEntry).count() == first_count == 2
    assert db.get(Deposit, deposit.id).status == DepositStatus.FAILED
    assert db.query(AffiliateCommission).one().status == CommissionStatus.CANCELLED


def test_partial_refund_is_explicitly_rejected(db):
    user = _user(db, "partial@test.com")
    product = ProductType(code="partial", name="Partial", price=10, currency="USD")
    db.add(product)
    db.flush()
    deposit = Deposit(
        user_id=user.id,
        product_type_id=product.id,
        amount=10,
        currency="USD",
        status=DepositStatus.VALIDATED,
    )
    db.add(deposit)
    db.commit()
    with pytest.raises(FinancialIntegrityError, match="Partial refunds"):
        reverse_provider_refund(db, deposit, {"refund_amount": "5.00"})
    db.rollback()
    assert db.get(Deposit, deposit.id).status == DepositStatus.VALIDATED


def test_refund_of_paid_commission_creates_receivable_and_reverses_fmp(db):
    _account(db, "1200", AccountType.ASSET)
    _account(db, "2001", AccountType.LIABILITY)
    _account(db, "2002", AccountType.LIABILITY)
    payer = _user(db, "paid-refund@test.com")
    sponsor = _user(db, "paid-refund-sponsor@test.com")
    product = ProductType(code="paid-refundable", name="Paid refundable", price=20, currency="USD")
    db.add(product)
    db.flush()
    deposit = Deposit(
        user_id=payer.id,
        product_type_id=product.id,
        amount=20,
        currency="USD",
        order_id="paid-refund-order",
        external_payment_id="paid-refund-payment",
        status=DepositStatus.VALIDATED,
    )
    db.add(deposit)
    db.flush()
    db.add_all(
        [
            AffiliateCommission(
                user_id=sponsor.id,
                source_user_id=payer.id,
                product_type_id=product.id,
                deposit_id=deposit.id,
                commission_type=CommissionType.FOUNDING_MEMBERSHIP_FEE,
                level=1,
                base_amount=20,
                commission_amount=2,
                status=CommissionStatus.PAID,
                payout_reference="provider-payout",
            ),
            MemberFmpLedger(
                user_id=payer.id,
                source_type="FOUNDING_JOIN",
                source_id=deposit.id,
                points=Decimal("1"),
            ),
            MemberFmpBalance(user_id=payer.id, total_fmp=Decimal("1")),
        ]
    )
    db.commit()

    assert reverse_provider_refund(db, deposit, {"refund_amount": "20.00"}) is True
    commission = db.query(AffiliateCommission).one()
    assert commission.status == CommissionStatus.CANCELLED
    assert commission.payout_reference == "provider-payout"
    receivable = db.query(JournalEntry).filter(
        JournalEntry.description == f"Refund paid-commission receivable - Deposit #{deposit.id}"
    ).one()
    assert receivable.total_debit == receivable.total_credit == Decimal("2.00")
    assert db.get(MemberFmpBalance, payer.id).total_fmp == Decimal("0.000000")
    assert db.query(MemberFmpLedger).filter_by(source_type="FOUNDING_JOIN_REVERSAL").count() == 1


def test_annualads_webhook_signature_amount_network_and_replay(client, db, monkeypatch):
    monkeypatch.setattr(settings, "ANNUALADS_WEBHOOK_SECRET", "annual-secret")
    monkeypatch.setattr(settings, "ANNUALADS_TENANT_ID", "tenant-1")
    for code, kind in (
        ("1030", AccountType.ASSET),
        ("1210", AccountType.ASSET),
        ("2310", AccountType.LIABILITY),
        ("4010", AccountType.REVENUE),
        ("7110", AccountType.EXPENSE),
    ):
        _account(db, code, kind)
    db.commit()

    body = {
        "event": "sponsor_payment_confirmed",
        "payment": {
            "tx_hash": "0xannual-event",
            "amount": "100.00",
            "platform_fee": "30.00",
            "client_revenue": "70.00",
            "currency": "usdtbsc",
        },
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"annual-secret", timestamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    headers = {
        "content-type": "application/json",
        "x-webhook-timestamp": timestamp,
        "x-webhook-signature": signature,
        "x-webhook-event": "sponsor_payment_confirmed",
    }
    first = client.post("/api/v1/webhooks/sponsor-payment", content=raw, headers=headers)
    second = client.post("/api/v1/webhooks/sponsor-payment", content=raw, headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "recorded"
    assert second.json()["status"] == "already_recorded"
    assert db.query(JournalEntry).count() == 1

    bad = client.post(
        "/api/v1/webhooks/sponsor-payment",
        content=raw,
        headers={**headers, "x-webhook-signature": "bad"},
    )
    assert bad.status_code == 401

    refund_body = {"event": "sponsor_payment_refunded", "payment": {"tx_hash": "0xannual-event"}}
    refund_raw = json.dumps(refund_body, separators=(",", ":")).encode()
    refund_signature = hmac.new(
        b"annual-secret", timestamp.encode() + b"." + refund_raw, hashlib.sha256
    ).hexdigest()
    unsupported_refund = client.post(
        "/api/v1/webhooks/sponsor-payment",
        content=refund_raw,
        headers={**headers, "x-webhook-signature": refund_signature, "x-webhook-event": "sponsor_payment_refunded"},
    )
    assert unsupported_refund.status_code == 409

    wrong_tenant_body = {
        "event": "sponsor_payment_confirmed",
        "tenant_id": "another-tenant",
        "payment": body["payment"],
    }
    wrong_tenant_raw = json.dumps(wrong_tenant_body, separators=(",", ":")).encode()
    wrong_tenant_signature = hmac.new(
        b"annual-secret", timestamp.encode() + b"." + wrong_tenant_raw, hashlib.sha256
    ).hexdigest()
    wrong_tenant = client.post(
        "/api/v1/webhooks/sponsor-payment",
        content=wrong_tenant_raw,
        headers={**headers, "x-webhook-signature": wrong_tenant_signature},
    )
    assert wrong_tenant.status_code == 401


def test_annualads_sso_token_is_authenticated_and_not_cacheable(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "ANNUALADS_SSO_SECRET", "annual-sso-secret")
    monkeypatch.setattr(settings, "ANNUALADS_TENANT_ID", "tenant-1")
    monkeypatch.setattr(settings, "ANNUALADS_TENANT_API_KEY", "public-embed-key")

    anonymous = client.get("/api/v1/sponsor-embed/sso-token")
    assert anonymous.status_code == 401
    response = client.get("/api/v1/sponsor-embed/sso-token", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["tenant_id"] == "tenant-1"
