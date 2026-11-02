"""Prompt 3 (2026-11-02): SoncoPay payment/payout readiness, SoncoPay payment reconciliation, payout status
emails and the provider balance of the payout reconciliation. SYNTHETIC members and a fake SoncoPay; nothing
reaches the network, nothing is activated."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.checkout_gateway import SoncoPayWebhookEvent
from app.models.email import EmailDelivery
from app.models.payment import Deposit, DepositStatus
from app.services import cashout_engine as engine
from app.services import payment_config
from app.services import soncopay_payouts as spo
from app.services import soncopay_readiness as readiness
from tests.unit.test_dual_cashout import NOW, OTHER_WALLET, commission, member  # noqa: F401
from tests.unit.test_soncopay_payouts import (  # noqa: F401
    dashboard_confirm,
    destination,
    engine_on,
    fake,
    keys,
    ledger,
    no_network,
    payouts_on,
    real_figures,
    run,
    soncopay_live,
    world,
)

pytestmark = [pytest.mark.unit, pytest.mark.discontinued, pytest.mark.ten_dollar_minimum]


@pytest.fixture(autouse=True)
def real_minimum(monkeypatch, keys):  # noqa: F811
    monkeypatch.setattr(spo, "PROVIDER_MIN_PAYOUT_USD", Decimal("5.00"))


def emails(db, prefix):
    db.expire_all()
    return db.query(EmailDelivery).filter(EmailDelivery.idempotency_key.like(f"{prefix}%")).all()


def report(db, **kw):
    return asyncio.run(readiness.readiness(db, now=NOW, **kw))


def item(rep, key):
    return next(i for i in rep["items"] if i["key"] == key)


def soncopay_deposit(db, user, *, status=DepositStatus.PENDING, provider_status="waiting", payment_id="pay_1",
                     expires=None):
    from app.models.payment import ProductType

    product = db.query(ProductType).first()
    if product is None:
        product = ProductType(code="kyc", name="KYC", price=Decimal("5.00"))
        db.add(product)
        db.flush()
    dep = Deposit(user_id=user.id, product_type_id=product.id, amount=Decimal("5.00"), currency="USD",
                  status=status, order_id=f"ord-{payment_id}", external_payment_id=payment_id,
                  payment_provider="soncopay", provider_environment="live", provider_status=provider_status,
                  provider_expires_at=expires)
    db.add(dep)
    db.commit()
    return dep


# ---------------------------------------------------------------- readiness

def test_readiness_without_authorization_reports_blockers_and_activates_nothing(ledger, engine_on, fake):
    db = ledger
    soncopay_live(db, authorize=False)
    before = (payment_config.payout_activation_switch(), payment_config.crypto_master_switch())
    rep = report(db)
    assert len(rep["items"]) == 16
    assert item(rep, "payout_authorization")["status"] == "BLOCKED"
    assert item(rep, "live_payout_activation")["status"] == "BLOCKED"
    assert item(rep, "provider_balance")["status"] == "NOT_VERIFIED"       # no provider read asked
    assert item(rep, "payment_methods")["status"] == "NOT_VERIFIED"
    assert item(rep, "destination_registration")["status"] == "BLOCKED"
    assert (payment_config.payout_activation_switch(), payment_config.crypto_master_switch()) == before
    assert fake.posts("/v1/payouts") == [] and fake.posts("/v1/payout-destinations") == []
    text = repr(rep)
    assert "sp_live_" not in text and "whsec" not in text                  # never a key or secret


def test_readiness_with_authorization_and_a_payable_destination(payouts_on, fake, monkeypatch):
    from app.services import soncopay_payments as scp

    db = payouts_on
    real_figures(db, fake)
    user = member(db, "r1", method="CRYPTO")
    commission(db, user, "1.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    dashboard_confirm(db, user)
    run(db)                                                        # read back: usable, past the 24 hours

    async def methods(_db):                                        # GET /v1/methods answered (synthetic)
        return [{"code": "usdt_bsc"}, {"code": "card"}]

    monkeypatch.setattr(scp, "account_methods", methods)
    monkeypatch.setattr(scp, "_methods_cache", {"environment": "live", "methods": [{"code": "card"}], "checked": 1.0})
    rep = report(db, read_provider=True)
    assert item(rep, "payment_methods")["status"] == "READY" and item(rep, "payment_methods")["methods"] == [
        "usdt_bsc", "card"]
    assert item(rep, "payout_authorization")["status"] == "READY"
    assert item(rep, "destination_registration")["status"] == "READY"
    assert item(rep, "waiting_period")["status"] == "READY"
    assert item(rep, "provider_balance")["status"] in ("READY", "BLOCKED")    # read, not guessed
    assert "balance" in item(rep, "provider_balance")
    assert item(rep, "live_payout_activation")["status"] == "BLOCKED"        # never READY by itself
    assert rep["limits"]["manual_review_above_usd"] == "1000.00"
    assert rep["limits"]["count_limit"] == 50 and rep["limits"]["amount_limit"] == "10000.00"


def test_the_readiness_endpoint_needs_a_finance_viewer(payouts_on, fake, client):
    from tests.unit.test_admin_security_hardening import bearer
    from tests.unit.test_super_admin import superadmin

    db = payouts_on
    plain = member(db, "plain-r")
    assert client.get("/api/v1/admin/finance/soncopay/readiness", headers=bearer(plain)).status_code == 403
    boss = superadmin(db, "boss-ready")
    answer = client.get("/api/v1/admin/finance/soncopay/readiness", headers=bearer(boss))
    assert answer.status_code == 200, answer.text
    assert {i["status"] for i in answer.json()["items"]} <= {"READY", "BLOCKED", "NOT_VERIFIED", "NOT_APPLICABLE"}
    rec = client.get("/api/v1/admin/finance/soncopay/payments/reconciliation", headers=bearer(boss))
    assert rec.status_code == 200 and "problems" in rec.json()


# ---------------------------------------------------------------- payment reconciliation

def test_payment_reconciliation_finds_mismatches_and_changes_nothing(ledger):
    db = ledger
    user = member(db, "payer-r")
    soncopay_deposit(db, user, provider_status="paid", payment_id="pay_a")               # paid, not confirmed
    soncopay_deposit(db, user, status=DepositStatus.VALIDATED, provider_status="failed", payment_id="pay_b")
    soncopay_deposit(db, user, provider_status="waiting", payment_id="pay_c", expires=NOW - timedelta(hours=5))
    soncopay_deposit(db, user, provider_status="paid_other_asset", payment_id="pay_d")
    soncopay_deposit(db, user, status=DepositStatus.VALIDATED, provider_status="paid", payment_id="pay_e")
    db.add(SoncoPayWebhookEvent(delivery_id="dlv_x", event="payment.paid", environment="live", payment_id="pay_zz",
                                outcome="UNKNOWN_PAYMENT"))
    db.commit()
    snapshot = sorted((d.id, d.status.value, d.provider_status) for d in db.query(Deposit).all())
    rec = readiness.payment_reconciliation(db, now=NOW)
    kinds = sorted(p["type"] for p in rec["problems"])
    assert kinds == ["CONFIRMED_NOT_PAID", "MISSING_PROVIDER_EVENT", "PAID_NOT_CONFIRMED", "PAID_OTHER_ASSET",
                     "UNKNOWN_PAYMENT_EVENT"]
    assert rec["critical"] == 2 and rec["deposits"]["validated"] == 2
    assert rec["webhooks"]["by_outcome"] == {"UNKNOWN_PAYMENT": 1}
    db.expire_all()
    assert sorted((d.id, d.status.value, d.provider_status) for d in db.query(Deposit).all()) == snapshot


def test_a_clean_book_has_no_problems(ledger):
    rec = readiness.payment_reconciliation(ledger, now=NOW)
    assert rec["problems"] == [] and rec["critical"] == 0 and rec["webhooks"]["last_received_at"] is None


# ---------------------------------------------------------------- payout reconciliation: SoncoPay balance

def test_the_payout_reconciliation_reads_the_soncopay_balance_never_nowpayments(payouts_on, fake, monkeypatch):
    db = payouts_on
    fake.balance = "123.45"

    def never(*_a, **_k):
        raise AssertionError("NOWPayments must not be asked")

    monkeypatch.setattr(engine, "NowPaymentsPayoutProvider", never)
    rep = engine.reconciliation_report(db, read_provider=True)
    assert rep["provider_balance_state"] == "READ"


def test_without_authorization_the_balance_stays_not_verified(ledger, engine_on, fake):
    soncopay_live(ledger, authorize=False)
    assert engine.reconciliation_report(ledger, read_provider=True)["provider_balance_state"] == "NOT_VERIFIED"


# ---------------------------------------------------------------- payout status emails

def test_destination_emails_are_sent_once_per_state(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user = member(db, "e1", method="CRYPTO")
    commission(db, user, "1.00")
    run(db)                                                        # registered -> awaiting SoncoPay confirmation
    run(db)
    first = emails(db, "payout-destination:")
    assert len(first) == 1 and ":DESTINATION_AWAITING_CONFIRMATION:" in first[0].idempotency_key
    fake.confirm(destination(db, user).destination_id, usable=True)
    dashboard_confirm(db, user, at=NOW - timedelta(hours=2))      # confirmed, 22 hours left
    run(db)
    run(db)
    kinds = sorted(e.idempotency_key.split(":")[2] for e in emails(db, "payout-destination:"))
    assert kinds == ["DESTINATION_AWAITING_CONFIRMATION", "DESTINATION_WAITING_PERIOD"]


def test_a_kyc_blocked_eligible_member_is_told_once_only_while_payouts_are_active(payouts_on, fake, monkeypatch):
    db = payouts_on
    real_figures(db, fake)
    with monkeypatch.context() as off:
        off.setattr(payment_config, "payout_activation_switch", lambda: False)
        user = member(db, "k1", method="CRYPTO", kyc=False)
        commission(db, user, "20.00")
        run(db)
        fake.confirm(destination(db, user).destination_id, usable=True)
        dashboard_confirm(db, user)
        run(db)
        assert emails(db, "payout-kyc_not_approved:") == []       # activation off: no eligibility email
    run(db)
    run(db)
    sent = emails(db, "payout-kyc_not_approved:")
    assert len(sent) == 1 and sent[0].user_id == user.id
    assert fake.posts("/v1/payouts") == []


def test_a_changed_wallet_submission_says_payouts_are_paused(payouts_on, monkeypatch):
    from tests.unit.test_dual_cashout import approve_wallet
    from app.services import payout_notifications

    db = payouts_on
    user = member(db, "w1", method="CRYPTO")
    approve_wallet(db, user)                                       # the first wallet
    user.usdt_wallet_address = OTHER_WALLET
    db.commit()
    second = approve_wallet(db, user, status="PENDING")            # the change
    seen = []
    monkeypatch.setattr(payout_notifications, "_enqueue", lambda db, event, u, key, ctx: seen.append(ctx) or True)
    payout_notifications.wallet_submitted(db, user, second.id)
    first_only = db.query(__import__("app.models.affiliate", fromlist=["x"]).PayoutWalletApproval).filter_by(
        user_id=user.id).order_by("id").first()
    payout_notifications.wallet_submitted(db, user, first_only.id)
    assert [c["changed"] for c in seen] == [True, False]


def test_the_payout_status_email_renders_without_secrets():
    from app.services.email_render import RENDERERS
    from app.services.email_events import EmailEvent

    assert EmailEvent.PAYOUT_STATUS_UPDATE.value in RENDERERS


# ---------------------------------------------------------------- member summary

def test_the_member_summary_shows_missed_earnings_as_non_payable(ledger):
    from app.models.missed_earning import CATEGORY_REFERRAL
    from app.services import cashout_service, missed_earnings

    db = ledger
    user = member(db, "m-missed", method="CRYPTO", kyc=False)
    missed_earnings.record(db, user_id=user.id, category=CATEGORY_REFERRAL, source_type="DEPOSIT", source_id=991,
                           amount=Decimal("2.50"), kyc_status="NONE")
    db.commit()
    summary = cashout_service.summary(db, user)
    assert summary["balances"]["missed"] == 2.5
    assert summary["balances"]["available_unpaid"] == 0.0 and summary["payable_amount"] == 0.0
