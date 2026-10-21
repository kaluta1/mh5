"""NOWPayments checkout switch, separate from automatic payouts.

  1. a NEW NOWPayments checkout needs provider_enabled (master emergency stop)
     AND checkout_enabled; refused before anything is created (no deposit, no
     provider call) with a clear "unavailable" answer;
  2. automatic payouts never read checkout_enabled: they keep every existing
     gate, and provider_enabled still stops them (master stop);
  3. existing NOWPayments payments (IPN, status polling, idempotent replay) are
     processed whatever the switches say, once;
  4. the checkout gateway never falls back silently to a gateway that is off;
  5. switching checkout on is an activation (permission + password), audited;
     defaults and the migration activate nothing.

Every account and value is SYNTHETIC; no provider is reached.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from decimal import Decimal

import pytest

from app.models.affiliate import AffiliateCommission
from app.models.payment import Deposit, DepositStatus
from app.models.payment_config import PaymentConfigAudit, PaymentSettings
from app.services import cashout_engine as engine
from app.services import checkout_routing
from app.services import nowpayments_service
from app.services import payment_config as pc
from app.services.payment_scheduler import PaymentScheduler
from tests.unit.test_admin_security_hardening import bearer, code_of
from tests.unit.test_dual_cashout import (  # noqa: F401
    PASSWORD,
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
from tests.unit.test_new_business_model import world  # noqa: F401

pytestmark = pytest.mark.unit

CREATE, GATEWAY, SETTINGS = "/api/v1/payments/create", "/api/v1/payments/checkout-gateway", "/api/v1/admin/finance/settings"
IPN_SECRET = "ipn_synthetic_secret_value_0001"


@pytest.fixture
def nowpayments(monkeypatch):
    """NOWPayments is faked: every pay-in call is recorded, none leaves the process."""
    calls = []
    from app.api.api_v1.endpoints import payments as endpoint

    async def create(**kw):
        calls.append(("create", kw["order_id"]))
        return {"payment_id": f"np_{kw['order_id']}", "pay_address": "0xsynthetic", "pay_amount": 50,
                "pay_currency": "usdtbsc", "payment_status": "waiting"}

    async def status(payment_id):
        calls.append(("status", payment_id))
        return {"payment_status": "finished", "payment_id": payment_id}

    monkeypatch.setattr(endpoint, "now_create_payment", create)
    monkeypatch.setattr(nowpayments_service, "get_payment_status", status)
    monkeypatch.setattr(pc, "ipn_secret", lambda _db: IPN_SECRET)
    pc.invalidate_runtime()
    yield calls
    pc.invalidate_runtime()


PRICES = {"annual_membership": 50, "kyc": 10}


def buy(client, user, key="k-1", product="annual_membership"):
    return client.post(CREATE, headers={**bearer(user), "Idempotency-Key": key},
                       json={"amount": PRICES[product], "currency": "usd", "product_code": product})


def signed_ipn(client, body: dict):
    sig = hmac.new(IPN_SECRET.encode(), json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
                   hashlib.sha512).hexdigest()
    return client.post("/api/v1/webhooks/nowpayments", content=json.dumps(body),
                       headers={"x-nowpayments-sig": sig, "Content-Type": "application/json"})


@pytest.fixture
def buyer(ledger):
    sponsor = member(ledger, "sponsor", method="CRYPTO")
    return member(ledger, "buyer", sponsor=sponsor, wallet=None)


# ===========================================================================
# 1. Defaults and the migration activate nothing
# ===========================================================================

def test_checkout_is_on_by_default_so_what_is_in_force_does_not_change():
    config = pc.default_config()
    assert config.checkout_enabled is True and config.checkout_allowed is True
    # With the provider off (production today), checkout stays off: the new default changes nothing.
    from dataclasses import replace
    off = replace(config, provider_enabled=False)
    assert off.checkout_allowed is False and off.auto_payout_allowed is False
    assert pc.PayinRuntime(False, "ENVIRONMENT", None).checkout_allowed is False   # an older caller
    assert PaymentSettings.__table__.c.checkout_enabled.server_default.arg == "true"


# ===========================================================================
# 2. A new NOWPayments checkout needs BOTH switches; refused before anything is created
# ===========================================================================

@pytest.mark.parametrize("switches", [{"checkout_enabled": False}, {"provider_enabled": False},
                                      {"provider_enabled": False, "checkout_enabled": False}])
def test_no_deposit_and_no_provider_call_while_nowpayments_checkout_is_off(client, ledger, buyer, nowpayments,
                                                                         switches):
    db = ledger
    configure(db, **switches)
    for product in ("annual_membership", "kyc"):
        refused = buy(client, buyer, key=f"k-{product}", product=product)
        assert refused.status_code == 503, refused.text
        assert code_of(refused) == "CHECKOUT_UNAVAILABLE"
        assert "temporarily unavailable" in refused.json()["detail"]["message"]
    assert db.query(Deposit).count() == 0 and nowpayments == []
    assert client.get(GATEWAY, headers=bearer(buyer)).json() == {
        "provider": "none", "available": False, "message": checkout_routing.UNAVAILABLE_MESSAGE}


def test_checkout_off_is_answered_before_eligibility_and_kyc_checks_run(client, ledger, nowpayments, monkeypatch):
    db = ledger
    from datetime import datetime
    from app.services import financial_eligibility, kyc_fee

    configure(db, checkout_enabled=False)
    child = member(db, "child", wallet=None, dob=datetime(2016, 1, 1))
    looked = []
    monkeypatch.setattr(financial_eligibility, "require", lambda *a, **k: looked.append("eligibility"))
    monkeypatch.setattr(kyc_fee, "payment_refusal", lambda *a, **k: looked.append("kyc-lock"))
    refused = buy(client, child, product="kyc")
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert looked == [] and db.query(Deposit).count() == 0 and nowpayments == []


def test_a_switch_moved_during_the_request_still_creates_nothing(client, ledger, buyer, nowpayments, monkeypatch):
    db = ledger
    configure(db, provider_enabled=True, checkout_enabled=True)
    answers = iter(["nowpayments", None])                 # open at the first check, closed at the second
    monkeypatch.setattr(checkout_routing, "new_payment_gateway", lambda _db: next(answers))
    refused = buy(client, buyer)
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert db.query(Deposit).count() == 0 and nowpayments == []


def test_both_switches_on_creates_the_nowpayments_payment_as_before(client, ledger, buyer, nowpayments):
    db = ledger
    configure(db, provider_enabled=True, checkout_enabled=True)
    created = buy(client, buyer)
    assert created.status_code == 200, created.text
    dep = db.query(Deposit).one()
    assert (dep.payment_provider, dep.status, dep.external_payment_id) == ("nowpayments", DepositStatus.PENDING,
                                                                            f"np_{dep.order_id}")
    assert [c[0] for c in nowpayments] == ["create"]
    assert client.get(GATEWAY, headers=bearer(buyer)).json() == {"provider": "nowpayments", "available": True}


def test_the_nowpayments_service_refuses_too_when_called_directly(monkeypatch):
    monkeypatch.setattr(pc, "payin_runtime", lambda: pc.PayinRuntime(True, "ENVIRONMENT", "k", False))
    with pytest.raises(nowpayments_service.NowPaymentsError, match="checkout is switched off"):
        asyncio.run(nowpayments_service.create_payment(price_amount=Decimal("50"), price_currency="usd",
                                                       order_id="o-1", order_description="d"))
    monkeypatch.setattr(pc, "payin_runtime", lambda: pc.PayinRuntime(False, "ENVIRONMENT", "k", True))
    with pytest.raises(nowpayments_service.NowPaymentsError, match="switched off"):
        asyncio.run(nowpayments_service.create_payment(price_amount=Decimal("50"), price_currency="usd",
                                                       order_id="o-2", order_description="d"))


def test_an_existing_payment_is_still_answered_when_checkout_is_switched_off(client, ledger, buyer, nowpayments):
    db = ledger
    configure(db, provider_enabled=True, checkout_enabled=True)
    first = buy(client, buyer, key="k-replay")
    configure(db, checkout_enabled=False)
    again = buy(client, buyer, key="k-replay")
    assert again.status_code == 200 and again.json()["deposit_id"] == first.json()["deposit_id"]
    assert db.query(Deposit).count() == 1 and [c[0] for c in nowpayments] == ["create"]


# ===========================================================================
# 3. Existing NOWPayments payments are processed whatever the switches say
# ===========================================================================

@pytest.mark.parametrize("switches", [{"checkout_enabled": False}, {"provider_enabled": False}])
def test_an_existing_payment_is_confirmed_once_by_its_ipn_and_by_the_scheduler(client, ledger, buyer, nowpayments,
                                                                              switches):
    db = ledger
    configure(db, provider_enabled=True, checkout_enabled=True)
    created = buy(client, buyer, key=f"k-{'-'.join(switches)}")
    dep = db.query(Deposit).filter(Deposit.id == created.json()["deposit_id"]).one()
    configure(db, **switches)                        # switched off AFTER the payment was started
    body = {"payment_id": dep.external_payment_id, "order_id": dep.order_id, "payment_status": "finished",
            "price_amount": 50, "price_currency": "usd"}
    assert signed_ipn(client, body).status_code == 200
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.VALIDATED
    commissions = db.query(AffiliateCommission).count()
    # The same IPN again and the scheduler: nothing more.
    assert signed_ipn(client, body).status_code == 200
    assert asyncio.run(PaymentScheduler()._check_single_payment(db, dep.id)) == "SKIPPED"
    db.expire_all()
    assert db.query(AffiliateCommission).count() == commissions


def test_the_scheduler_still_polls_a_pending_nowpayments_payment_while_checkout_is_off(client, ledger, buyer,
                                                                                     nowpayments):
    db = ledger
    configure(db, provider_enabled=True, checkout_enabled=True)
    created = buy(client, buyer)
    configure(db, checkout_enabled=False)
    outcome = asyncio.run(PaymentScheduler()._check_single_payment(db, created.json()["deposit_id"]))
    assert outcome == "SYNCED" and ("status", f"np_{db.query(Deposit).one().order_id}") in nowpayments
    db.expire_all()
    assert db.query(Deposit).one().status == DepositStatus.VALIDATED


# ===========================================================================
# 4. Automatic payouts are independent of checkout; the provider is still the master stop
# ===========================================================================

def test_checkout_off_does_not_stop_payouts_or_their_reconciliation(ledger, engine_on):
    db = ledger
    configure(db, checkout_enabled=False)
    config = pc.load(db)
    assert config.auto_payout_allowed is True and config.checkout_allowed is False
    assert engine.engine_enabled(db) is True and engine.engine_status(db)["enabled"] is True
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    report = run(db, provider)
    assert report["enabled"] is True and report["members"] == {"SUBMITTED": 1}
    assert len(provider.created) == 1 and len(cashouts(db, user)) == 1
    # The next cycle reconciles the open payout as usual.
    run(db, provider)
    assert provider.status_calls


def test_provider_off_is_still_the_emergency_stop_for_payouts(ledger, engine_on):
    db = ledger
    configure(db, provider_enabled=False, checkout_enabled=True)
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    assert run(db, provider) == {"enabled": False, "reconciled": {}, "members": {}}
    assert provider.created == [] and cashouts(db, user) == []
    assert pc.load(db).checkout_allowed is False


def test_provider_off_also_stops_reconciliation_calls_for_an_open_payout(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 1}         # one payout is now open
    calls = len(provider.status_calls)
    configure(db, provider_enabled=False)                           # emergency stop
    assert run(db, provider) == {"enabled": False, "reconciled": {}, "members": {}}
    assert len(provider.status_calls) == calls                      # NOWPayments is not even asked
    configure(db, provider_enabled=True, checkout_enabled=False)    # checkout off: reconciliation resumes
    run(db, provider)
    assert len(provider.status_calls) > calls


@pytest.mark.parametrize("gate", ["crypto_cashout_enabled", "crypto_auto_payout_enabled"])
def test_checkout_on_never_overrides_a_payout_gate(ledger, engine_on, gate):
    db = ledger
    configure(db, checkout_enabled=True, **{gate: False})
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    run(db, provider)
    assert provider.created == [] and pc.load(db).auto_payout_allowed is False


# ===========================================================================
# 5. Gateway decision: no silent fallback
# ===========================================================================

def test_the_gateway_is_soncopay_when_ready_whatever_the_nowpayments_checkout_switch(ledger, monkeypatch):
    db = ledger
    from app.services import soncopay_settings

    configure(db, checkout_enabled=False)
    monkeypatch.setattr(soncopay_settings, "default_checkout_provider", lambda _db: "soncopay")
    assert checkout_routing.new_payment_gateway(db) == "soncopay"
    monkeypatch.setattr(soncopay_settings, "default_checkout_provider", lambda _db: "nowpayments")
    assert checkout_routing.new_payment_gateway(db) is None             # not ready AND NOWPayments off: none
    configure(db, checkout_enabled=True)
    assert checkout_routing.new_payment_gateway(db) == "nowpayments"


# ===========================================================================
# 6. Switching checkout on is an audited activation; off is an ordinary change
# ===========================================================================

def test_switching_checkout_needs_the_activation_permission_to_go_on_and_is_audited(client, ledger):
    db = ledger
    configure(db, checkout_enabled=False)
    manager = member(db, "manager", admin=True, permissions=(pc.PERMISSION_MANAGE,))
    activator = member(db, "activator", admin=True)
    body = {"changes": {"checkout_enabled": True}, "current_password": PASSWORD}
    refused = client.put(SETTINGS, headers=bearer(manager), json=body)
    assert refused.status_code == 403 and pc.load(db).checkout_enabled is False
    assert client.put(SETTINGS, headers=bearer(activator), json={**body, "current_password": "wrong"}).status_code in (401, 403)
    done = client.put(SETTINGS, headers=bearer(activator), json=body)
    assert done.status_code == 200, done.text
    db.expire_all()
    assert pc.load(db).checkout_enabled is True
    audit = db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first()
    assert audit.changed_fields == ["checkout_enabled"] and audit.actor_id == activator.id
    assert audit.old_values == {"checkout_enabled": False} and audit.new_values == {"checkout_enabled": True}
    # Switching it off needs no activation.
    off = client.put(SETTINGS, headers=bearer(manager), json={"changes": {"checkout_enabled": False},
                                                              "current_password": PASSWORD})
    assert off.status_code == 200, off.text
    view = client.get(SETTINGS, headers=bearer(manager)).json()
    assert view["activation"]["values"]["checkout_enabled"] is True
    field = next(f for f in view["fields"] if f["name"] == "checkout_enabled")
    assert field["group"] == "provider" and "NOWPayments checkout" in field["label"]


def test_the_readiness_view_shows_the_checkout_state(client, ledger):
    db = ledger
    configure(db, provider_enabled=True, checkout_enabled=False)
    items = {i["key"]: i for i in pc.readiness_view(db)["items"]}
    assert items["checkout"]["state"] == "DISABLED" and "payouts are not affected" in items["checkout"]["detail"]
    assert items["provider"]["state"] == "CONFIGURED"
    view = pc.provider_view(db)
    assert (view["enabled"], view["checkout_enabled"], view["checkout_available"]) == (True, False, False)
