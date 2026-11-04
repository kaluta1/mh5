"""Internal wallet payments (Prompt 5): paying approved products with available commission earnings.
Feature switch, KYC, which commissions are spendable, full payment only, server-side price, idempotency,
accounting (no cash, no SoncoPay record, no new commission), cashout interplay, refunds, API access.
SYNTHETIC data only; real transactional locking is covered by tests/integration/test_internal_wallet_postgres."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func

from app.core.config import settings
from app.models.accounting import ChartOfAccounts, JournalLine
from app.models.affiliate import AffiliateCommission, CommissionStatus, CommissionType
from app.models.advertising_v2 import AdvCreditMovement
from app.models.email import EmailDelivery
from app.models.internal_wallet import InternalWalletPayment, InternalWalletPaymentLine
from app.models.kyc import KYCStatus, KYCVerification
from app.models.payment import Deposit
from app.services import ad_campaigns as camp, cashout_service as cs, internal_wallet as iw
from app.services.financial_balances import get_commission_balance
from app.services.financial_integrity import FinancialIntegrityError
from tests.unit.test_new_business_model import _user, world  # noqa: F401  (fixtures)

pytestmark = pytest.mark.unit
D = Decimal
OLD = datetime.utcnow() - timedelta(days=40)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", True)


@pytest.fixture
def shop(world):
    """Advertiser credit on sale (prices and funding on for these tests only)."""
    cfg = camp.get_settings(world)
    cfg.cpm_rate_usd, cfg.min_campaign_budget_usd, cfg.funding_enabled = D("0.50"), D("10.00"), True
    world.commit()
    return world


def earn(db, user, amount, *, status=CommissionStatus.APPROVED, ref=None, version="NEW_V2", when=None, level=1):
    row = AffiliateCommission(user_id=user.id, source_user_id=user.id, commission_type=CommissionType.KYC_PAYMENT,
                              level=level, base_amount=D("10.00"), commission_amount=D(amount), status=status,
                              payout_reference=ref, transaction_date=when or OLD, business_model_version=version)
    db.add(row)
    db.flush()
    return row


def balance(db, code) -> Decimal:
    acc = db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).one()
    d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0)).filter(JournalLine.account_id == acc.id).one()
    return D(str(d)) - D(str(c))


def balanced(db) -> bool:
    d, c = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0),
                    func.coalesce(func.sum(JournalLine.credit_amount), 0)).one()
    return D(str(d)) == D(str(c))


def key() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------- switch and eligibility

def test_the_switch_is_off_by_default_and_blocks_every_payment(shop):
    db = shop
    assert settings.INTERNAL_WALLET_PAYMENTS_ENABLED is False and not iw.enabled()
    m = _user(db, "off@t.com")
    earn(db, m, "50.00")
    assert iw.preview(db, m, camp.AD_CREDIT_PRODUCT_CODE, 10)["reason"] == "WALLET_PAYMENTS_DISABLED"
    with pytest.raises(iw.WalletError) as e:
        iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=10, idempotency_key=key())
    assert e.value.code == "WALLET_PAYMENTS_DISABLED"
    assert db.query(InternalWalletPayment).count() == 0


@pytest.mark.parametrize("kyc_status", [None, KYCStatus.PENDING, KYCStatus.REJECTED, KYCStatus.EXPIRED])
def test_only_approved_kyc_may_pay(shop, on, kyc_status):
    db = shop
    m = _user(db, f"k{uuid.uuid4().hex[:5]}@t.com", kyc=False)
    if kyc_status is not None:
        db.add(KYCVerification(user_id=m.id, status=kyc_status))
        db.flush()
    earn(db, m, "50.00")
    assert iw.preview(db, m, camp.AD_CREDIT_PRODUCT_CODE, 10)["reason"] == "KYC_REQUIRED"
    with pytest.raises(iw.WalletError) as e:
        iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=10, idempotency_key=key())
    assert e.value.code == "KYC_REQUIRED"


def test_only_approved_unreserved_payable_commissions_are_spendable(shop, on):
    db = shop
    m = _user(db, "src@t.com")
    earn(db, m, "10.00")                                                    # spendable
    earn(db, m, "1.00", status=CommissionStatus.PENDING)                    # pending
    earn(db, m, "2.00", status=CommissionStatus.PAID)                       # paid
    earn(db, m, "4.00", status=CommissionStatus.CANCELLED)                  # cancelled / reversed
    earn(db, m, "8.00", ref="intent:cashout-1")                              # reserved for a payout
    earn(db, m, "16.00", version=None)                                       # historical, held for review
    db.commit()
    assert iw.spendable_balance(db, m.id) == D("10.00")
    assert get_commission_balance(db, m.id).available == D("10.00")          # same rule as cashouts


def test_products_have_a_central_policy(shop, on):
    db = shop
    m = _user(db, "pol@t.com")
    assert iw.product_terms(db, m, camp.AD_CREDIT_PRODUCT_CODE, 25).amount == D("25.00")
    assert iw.product_terms(db, m, "annual_membership", 1).reason == "RETIRED"
    assert iw.product_terms(db, m, "kyc", 1).reason == "NOT_APPLICABLE"
    assert iw.product_terms(db, m, "nope", 1).reason == "UNKNOWN_PRODUCT"
    assert iw.product_terms(db, m, camp.AD_CREDIT_PRODUCT_CODE, 0).reason == "INVALID_QUANTITY"
    camp.get_settings(db).funding_enabled = False
    assert iw.product_terms(db, m, camp.AD_CREDIT_PRODUCT_CODE, 5).reason == "PRODUCT_DISABLED"
    codes = {p["product_code"]: p for p in iw.policy_overview(db)}
    assert not codes["annual_ads"]["eligible"] and not codes["marketplace_order"]["eligible"]


# ---------------------------------------------------------------- paying

def test_full_payment_settles_commissions_and_books_no_cash(shop, on):
    db = shop
    m = _user(db, "pay@t.com")
    first, second = earn(db, m, "15.50", when=OLD), earn(db, m, "10.00", when=OLD + timedelta(days=1))
    db.commit()
    payment, replayed = iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=20, idempotency_key=key())
    db.commit()
    assert not replayed and payment.status == "COMPLETED" and payment.amount == D("20.00")
    assert (first.status, first.payout_reference) == (CommissionStatus.PAID, f"iwp:{payment.reference}")
    assert (second.status, second.payout_reference) == (CommissionStatus.APPROVED, iw.REMAINDER_MARK)
    assert iw.spendable_balance(db, m.id) == D("5.50")                     # 25.50 - 20.00
    assert iw.remainder_total(db, m.id) == D("5.50")
    bal = get_commission_balance(db, m.id)
    # 2026-11-04 fix: the remainder is spendable AND cashable (the same 5.50, counted once).
    assert (bal.available, bal.reserved, bal.paid_lifetime) == (D("5.50"), D("0.00"), D("20.00"))
    assert cs.available_rows(db, m.id) == [second] and cs.rows_total([second]) == D("5.50")
    dep = db.get(Deposit, payment.deposit_id)
    assert (dep.payment_provider, dep.status.value, dep.external_payment_id) == ("internal_wallet", "validated", None)
    assert db.query(Deposit).filter(Deposit.payment_provider == "soncopay").count() == 0
    assert camp.credit_balance(db, m.id) == D("20.00")
    assert balance(db, "1050") == D("0") and balance(db, "1001") == D("0")   # no cash, clearing nets to zero
    assert balance(db, "2001") == D("20.00") and balance(db, "2320") == D("-20.00")
    assert db.query(AffiliateCommission).count() == 2                       # no commission was created
    assert balanced(db) and iw.reconciliation(db)["ok"]


def test_insufficient_balance_writes_nothing(shop, on):
    db = shop
    m = _user(db, "poor@t.com")
    earn(db, m, "15.00")
    db.commit()
    p = iw.preview(db, m, camp.AD_CREDIT_PRODUCT_CODE, 20)
    assert (p["allowed"], p["reason"]) == (False, "INSUFFICIENT_BALANCE")
    with pytest.raises(iw.WalletError) as e:
        iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=20, idempotency_key=key())
    db.rollback()
    assert e.value.code == "INSUFFICIENT_BALANCE"
    assert db.query(InternalWalletPayment).count() == 0 and db.query(Deposit).count() == 0
    assert iw.spendable_balance(db, m.id) == D("15.00")


def test_preview_shows_amount_balance_and_remaining(shop, on):
    db = shop
    m = _user(db, "pre@t.com")
    earn(db, m, "25.00")
    p = iw.preview(db, m, camp.AD_CREDIT_PRODUCT_CODE, 20)
    assert (p["amount"], p["available"], p["remaining_after"], p["allowed"]) == ("20.00", "25.00", "5.00", True)


def test_idempotency_replay_conflict_and_price_change(shop, on):
    db = shop
    m = _user(db, "idem@t.com")
    earn(db, m, "60.00")
    db.commit()
    k = key()
    a, _ = iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=10, idempotency_key=k)
    db.commit()
    b, replayed = iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=10, idempotency_key=k)
    assert replayed and b.id == a.id and camp.credit_balance(db, m.id) == D("10.00")
    with pytest.raises(iw.WalletError) as e:
        iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=11, idempotency_key=k)
    assert e.value.code == "IDEMPOTENCY_CONFLICT"
    db.rollback()
    with pytest.raises(iw.WalletError) as e:
        iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=10, idempotency_key=key(),
               expected_amount=D("9.00"))                                   # the browser amount is never the price
    assert e.value.code == "PRICE_CHANGED"
    db.rollback()
    assert db.query(InternalWalletPayment).count() == 1


def test_remainders_are_used_first_and_rows_close_when_used_up(shop, on):
    db = shop
    m = _user(db, "rem@t.com")
    a, b = earn(db, m, "10.00", when=OLD), earn(db, m, "10.00", when=OLD + timedelta(days=1))
    db.commit()
    iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=3, idempotency_key=key())
    db.commit()
    assert (a.payout_reference, iw.spendable_balance(db, m.id)) == (iw.REMAINDER_MARK, D("17.00"))
    p2, _ = iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=8, idempotency_key=key())
    db.commit()
    assert a.status == CommissionStatus.PAID and b.payout_reference == iw.REMAINDER_MARK
    used = dict(db.query(InternalWalletPaymentLine.commission_id, InternalWalletPaymentLine.amount)
                .filter(InternalWalletPaymentLine.payment_id == p2.id).all())
    assert used == {a.id: D("7.00"), b.id: D("1.00")}
    assert iw.spendable_balance(db, m.id) == D("9.00") and iw.reconciliation(db)["ok"]


def test_a_partly_spent_commission_cannot_be_cancelled_silently(shop, on):
    from app.services.new_model_revenue import reverse_direct_commissions

    db = shop
    m = _user(db, "rev@t.com")
    row = earn(db, m, "10.00")
    row.source_type, row.source_id = "DEPOSIT", 999
    db.commit()
    iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=4, idempotency_key=key())
    db.commit()
    with pytest.raises(FinancialIntegrityError):
        reverse_direct_commissions(db, source_type="DEPOSIT", source_id=999, reason="provider refund")


def test_payout_reconciliation_does_not_flag_wallet_remainders(shop, on):
    from app.services import cashout_engine

    db = shop
    m = _user(db, "orph@t.com")
    earn(db, m, "10.00")
    db.commit()
    iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=4, idempotency_key=key())
    db.commit()
    problems = cashout_engine.reconciliation_report(db).get("problems") or []
    assert not [p for p in problems if p.get("type") == "ORPHAN_RESERVATION"]


# ---------------------------------------------------------------- refunds

def test_advertiser_credit_is_not_refunded_without_a_policy(shop, on):
    db = shop
    m, admin = _user(db, "rf@t.com"), _user(db, "rf-adm@t.com")
    earn(db, m, "20.00")
    db.commit()
    p, _ = iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=10, idempotency_key=key())
    db.commit()
    with pytest.raises(iw.WalletError) as e:
        iw.refund(db, admin, p.id, reason="member asked")
    assert e.value.code == "REFUND_POLICY_NOT_APPROVED"
    with pytest.raises(iw.WalletError):
        iw.refund(db, admin, p.id, reason="x")                              # a reason is required
    assert db.get(InternalWalletPayment, p.id).status == "COMPLETED"


# ---------------------------------------------------------------- notifications and API

def test_emails_once_and_only_while_switched_on(shop, on, monkeypatch):
    from app.services import email_render
    from app.services.email_events import EmailEvent

    db = shop
    assert EmailEvent.BILLING_WALLET_PAYMENT_UPDATE.value in email_render.RENDERERS
    m = _user(db, "mail@t.com")
    earn(db, m, "20.00")
    db.commit()
    p, _ = iw.pay(db, m, product_code=camp.AD_CREDIT_PRODUCT_CODE, quantity=5, idempotency_key=key())
    db.commit()
    assert iw.notify(db, p, "COMPLETED") and not iw.notify(db, p, "COMPLETED")
    monkeypatch.setattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", False)
    assert not iw.notify(db, p, "FAILED")
    keys = [k for (k,) in db.query(EmailDelivery.idempotency_key)]
    assert keys == [f"iwp:{p.reference}:COMPLETED"]


def test_api_switch_ownership_and_admin_controls(shop, client, monkeypatch):
    from tests.unit.test_admin_security_hardening import bearer
    from tests.unit.test_super_admin import superadmin

    db = shop
    m, other = _user(db, "api@t.com"), _user(db, "api-other@t.com")
    earn(db, m, "30.00")
    boss = superadmin(db, "boss-iw")
    db.commit()
    body = {"product_code": camp.AD_CREDIT_PRODUCT_CODE, "quantity": 10, "idempotency_key": key()}
    off = client.post("/api/v1/internal-wallet/pay", json=body, headers=bearer(m))
    assert off.status_code == 403 and off.json()["detail"]["code"] == "WALLET_PAYMENTS_DISABLED"
    summary = client.get("/api/v1/internal-wallet/summary", headers=bearer(m)).json()
    assert (summary["enabled"], summary["spendable"]) == (False, "30.00")
    monkeypatch.setattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", True)
    ok = client.post("/api/v1/internal-wallet/pay", json={**body, "amount": "1.00"}, headers=bearer(m))
    assert ok.status_code == 200, ok.text
    assert (ok.json()["amount"], ok.json()["remaining"]) == ("10.00", "20.00")   # the server's price
    again = client.post("/api/v1/internal-wallet/pay", json=body, headers=bearer(m)).json()
    assert again["replayed"] and again["id"] == ok.json()["id"]
    poor = client.post("/api/v1/internal-wallet/pay", json={**body, "quantity": 50, "idempotency_key": key()},
                       headers=bearer(m))
    assert poor.status_code == 409 and poor.json()["detail"]["code"] == "INSUFFICIENT_BALANCE"
    statuses = sorted(s for (s,) in db.query(InternalWalletPayment.status))
    assert statuses == ["COMPLETED", "FAILED"]                               # the failed attempt is history
    pid = ok.json()["id"]
    assert client.get(f"/api/v1/internal-wallet/payments/{pid}", headers=bearer(other)).status_code == 404
    assert client.get("/api/v1/admin/finance/internal-wallet/overview", headers=bearer(m)).status_code == 403
    ov = client.get("/api/v1/admin/finance/internal-wallet/overview", headers=bearer(boss))
    assert ov.status_code == 200 and ov.json()["reconciliation"]["ok"] and ov.json()["enabled"] is True
    detail = client.get(f"/api/v1/admin/finance/internal-wallet/payments/{pid}", headers=bearer(boss)).json()
    assert detail["lines"] and detail["settlement_journal_entry_id"]
    refused = client.post(f"/api/v1/admin/finance/internal-wallet/payments/{pid}/refund",
                          json={"reason": "member asked", "current_password": "wrong"}, headers=bearer(boss))
    assert refused.status_code == 403                                        # current password required
    assert client.post(f"/api/v1/admin/finance/internal-wallet/payments/{pid}/refund",
                       json={"reason": "member asked"}, headers=bearer(m)).status_code == 403
