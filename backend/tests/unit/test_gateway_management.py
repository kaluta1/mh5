"""Payment gateway management (owner decisions D1-D5, 2026-10-21).

  D1  the stored default gateway is kept; the EFFECTIVE default is the stored one
      while it is ready, otherwise none. Never the other gateway.
  D2  a gateway can be switched off while it is the default; nothing is chosen
      automatically.
  D3  switching NOWPayments back on while automatic payouts are configured on
      needs the activation permission, a connection test of the last 24 hours
      and the typed phrase; enforced on the server and audited.
  D4  while NOWPayments is off, payouts already handed to it are followed up by
      reading their status only; nothing is created, retried or sent.
  D5  SoncoPay has no payout.

Every account and value is SYNTHETIC; no provider is reached.
"""
from __future__ import annotations

from datetime import timedelta
from itertools import product

import pytest

from app.models.checkout_gateway import CheckoutGatewaySettings
from app.models.payment import Deposit, DepositStatus
from app.models.payment_config import PaymentConfigAudit, PaymentSettings
from app.services import cashout_engine as engine
from app.services import checkout_routing
from app.services import payment_config as pc
from app.services import soncopay_settings as sp
from app.core.config import settings
from tests.unit.test_admin_security_hardening import bearer, code_of
from tests.unit.test_dual_cashout import (  # noqa: F401
    NOW,
    PASSWORD,
    FakeProvider,
    cashouts,
    commission,
    engine_on,
    ledger,
    member,
    no_network,
    run,
)
from tests.unit.test_dual_cashout import configure as np_configure
from tests.unit.test_new_business_model import world  # noqa: F401
from tests.unit.test_soncopay_payments import (  # noqa: F401
    ADMIN_PASSWORD,
    CREATE,
    buy,
    buyer,
    deposit_of,
    environment,
    fake,
    nowpayments_calls,
    post_webhook,
)
from tests.unit.test_soncopay_payments import configure as sp_setup
from tests.unit.test_super_admin import superadmin

pytestmark = pytest.mark.unit

GATEWAY, ADMIN = "/api/v1/payments/checkout-gateway", "/api/v1/admin/finance/soncopay"


def gateway_answer(client, user) -> dict:
    return client.get(GATEWAY, headers=bearer(user)).json()


def sp_off(db, boss):
    sp.update(db, boss, password=ADMIN_PASSWORD, enabled=False)


def stored_row(db):
    db.expire_all()
    row = db.query(CheckoutGatewaySettings).first()
    return None if row is None else (row.default_provider, row.soncopay_enabled, row.soncopay_environment, row.version)


# ===========================================================================
# 1. The owner's combination table: incoming payments
# ===========================================================================

CASES = [(now_on, sp_on, default) for now_on, sp_on, default in product((True, False), (True, False),
                                                                        ("nowpayments", "soncopay"))]


@pytest.mark.parametrize("now_on,sp_on,default", CASES)
def test_every_combination_routes_to_the_ready_default_or_nowhere(client, ledger, fake, buyer, nowpayments_calls,
                                                                  now_on, sp_on, default):
    db = ledger
    boss = sp_setup(db, default=(default == "soncopay"))            # SoncoPay on + ready (+ default when asked)
    if not sp_on:
        sp_off(db, boss)                                            # D2: allowed even while it is the default
    np_configure(db, provider_enabled=now_on)
    expected = default if (now_on if default == "nowpayments" else sp_on) else None

    assert checkout_routing.stored_default(db) == default           # D1: the stored choice is never changed
    assert checkout_routing.new_payment_gateway(db) == expected     # ... and never replaced by the other one
    answer = gateway_answer(client, buyer)
    deposits = db.query(Deposit).count()
    created = buy(client, buyer, key=f"k-{now_on}-{sp_on}-{default}")
    if expected is None:
        assert answer == {"provider": "none", "available": False, "message": checkout_routing.UNAVAILABLE_MESSAGE}
        assert (created.status_code, code_of(created)) == (503, "CHECKOUT_UNAVAILABLE")
        assert db.query(Deposit).count() == deposits                # nothing written
        assert nowpayments_calls == [] and not [c for c in fake.calls if c[0] == "POST"]
    else:
        assert (answer["provider"], answer["available"]) == (expected, True)
        if expected == "soncopay":                                  # with the methods SoncoPay offers
            assert [m["code"] for m in answer["methods"]][:1] == ["usdt_bsc"]
        assert created.status_code == 200, created.text
        assert deposit_of(db, created).payment_provider == expected


def test_both_gateways_off_means_no_new_checkout(client, ledger, fake, buyer, nowpayments_calls):
    db = ledger
    boss = sp_setup(db, default=False)
    sp_off(db, boss)
    np_configure(db, provider_enabled=False)
    for gateway in ("nowpayments", "soncopay"):
        db.query(CheckoutGatewaySettings).update({"default_provider": gateway})
        db.commit()
        assert checkout_routing.new_payment_gateway(db) is None
        assert buy(client, buyer, key=f"k-{gateway}").status_code == 503
    assert db.query(Deposit).count() == 0 and nowpayments_calls == [] and fake.calls == []


@pytest.mark.parametrize("missing", ["NOWPAYMENTS_API_KEY", "NOWPAYMENTS_IPN_SECRET"])
def test_nowpayments_without_its_pay_in_credentials_takes_no_payment(client, ledger, buyer, nowpayments_calls,
                                                                     monkeypatch, missing):
    db = ledger
    monkeypatch.setattr(settings, missing, "")
    pc.invalidate_runtime()
    state = checkout_routing.nowpayments_state(db)
    assert (state.enabled, state.ready) == (True, False) and "Missing or unreadable" in state.reason
    assert gateway_answer(client, buyer)["provider"] == "none"
    refused = buy(client, buyer)
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert db.query(Deposit).count() == 0 and nowpayments_calls == []


def test_the_effective_default_says_why_there_is_none(ledger):
    db = ledger
    np_configure(db, provider_enabled=False)
    effective = checkout_routing.effective_default(db)
    assert (effective.stored, effective.gateway) == ("nowpayments", None)
    assert "NOWPayments (discontinued) cannot take new payments: NOWPayments is switched off." in effective.reason
    np_configure(db, provider_enabled=True, checkout_enabled=False)
    assert "checkout is switched off" in checkout_routing.effective_default(db).reason


# ===========================================================================
# 2. Choosing the default (Super Admin): only a ready gateway, checked on the server
# ===========================================================================

def test_a_forged_request_cannot_choose_a_gateway_that_is_off(client, ledger, fake):
    db = ledger
    boss = sp_setup(db)                                             # SoncoPay is the default
    np_configure(db, provider_enabled=False)
    before = stored_row(db)
    refused = client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD,
                                                            "default_provider": "nowpayments"})
    assert (refused.status_code, code_of(refused)) == (409, "NOT_READY")
    assert "NOWPayments is switched off" in refused.text
    assert stored_row(db) == before

    sp_off(db, boss)
    before = stored_row(db)
    refused = client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD,
                                                            "default_provider": "soncopay"})
    assert stored_row(db) == before                                 # already the stored value: no change at all
    db.query(CheckoutGatewaySettings).update({"default_provider": "nowpayments"})
    db.commit()
    before = stored_row(db)
    refused = client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD,
                                                            "default_provider": "soncopay"})
    assert (refused.status_code, code_of(refused)) == (409, "NOT_READY")
    assert stored_row(db) == before


@pytest.mark.parametrize("value", ["none", "paypal", "NOWPayments", ""])
def test_only_the_two_gateways_exist_as_a_default(client, ledger, value):
    db = ledger
    boss = superadmin(db, "boss")
    refused = client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD,
                                                            "default_provider": value})
    assert refused.status_code in (409, 422) and stored_row(db) is None


def test_nowpayments_without_credentials_cannot_be_chosen(client, ledger, fake, monkeypatch):
    db = ledger
    boss = sp_setup(db)
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "")
    refused = client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD,
                                                            "default_provider": "nowpayments"})
    assert (refused.status_code, code_of(refused)) == (409, "NOT_READY") and "IPN secret" in refused.text
    assert checkout_routing.stored_default(db) == "soncopay"


def test_switching_a_gateway_on_never_changes_the_stored_default(client, ledger, fake, buyer):
    db = ledger
    boss = sp_setup(db)                                             # default SoncoPay
    sp_off(db, boss)
    np_configure(db, provider_enabled=False)
    np_configure(db, provider_enabled=True)                         # NOWPayments on and ready...
    assert checkout_routing.stored_default(db) == "soncopay"        # ...is NOT made the default
    assert checkout_routing.new_payment_gateway(db) is None
    sp.update(db, boss, password=ADMIN_PASSWORD, enabled=True)      # the stored one back on
    assert checkout_routing.new_payment_gateway(db) == "soncopay"

    db.query(CheckoutGatewaySettings).update({"default_provider": "nowpayments", "soncopay_enabled": False})
    db.commit()
    sp.update(db, boss, password=ADMIN_PASSWORD, enabled=True)      # SoncoPay on: NOT made the default
    assert checkout_routing.stored_default(db) == "nowpayments"
    assert checkout_routing.new_payment_gateway(db) == "nowpayments"


def test_the_default_gateway_can_be_switched_off_and_nothing_is_chosen_for_it(client, ledger, fake, buyer):
    db = ledger
    boss = sp_setup(db)
    off = client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD, "enabled": False})
    assert off.status_code == 200, off.text
    view = off.json()
    assert (view["default_provider"], view["default_provider_in_force"]) == ("soncopay", "none")
    assert view["default_unavailable_reason"].startswith("The default gateway SoncoPay cannot take new payments")
    assert gateway_answer(client, buyer)["provider"] == "none"      # NOWPayments is ready but never used


def test_the_admin_view_shows_each_gateway_and_both_defaults(client, ledger, fake):
    db = ledger
    boss = sp_setup(db, default=False)
    np_configure(db, provider_enabled=False)
    view = client.get(ADMIN, headers=bearer(boss)).json()
    gateways = {g["provider"]: g for g in view["gateways"]}
    assert (gateways["nowpayments"]["enabled"], gateways["nowpayments"]["ready"]) == (False, False)
    assert gateways["nowpayments"]["reason"] == "NOWPayments is switched off."
    assert gateways["nowpayments"]["outgoing"] == "Discontinued: no payout"
    assert (gateways["soncopay"]["enabled"], gateways["soncopay"]["ready"], gateways["soncopay"]["reason"]) == (
        True, True, None)
    assert gateways["soncopay"]["outgoing"] == "Not connected yet (automatic payouts stay off)"     # D5
    assert {p["provider"]: p["available"] for p in view["checkout_providers"]} == {"nowpayments": False,
                                                                                  "soncopay": True}
    assert (view["default_provider"], view["default_provider_in_force"]) == ("nowpayments", "none")


def test_a_stale_form_changes_nothing(client, ledger, fake):
    db = ledger
    boss = sp_setup(db, default=False)
    version = client.get(ADMIN, headers=bearer(boss)).json()["version"]
    assert client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD, "enabled": False,
                                                         "expected_version": version}).status_code == 200
    before = stored_row(db)
    stale = client.put(ADMIN, headers=bearer(boss), json={"current_password": ADMIN_PASSWORD,
                                                          "default_provider": "soncopay", "expected_version": version})
    assert (stale.status_code, code_of(stale)) == (409, "STALE") and stored_row(db) == before


# ===========================================================================
# 3. A gateway switched off DURING a payment creation or a retry
# ===========================================================================

def _switch_off_after(monkeypatch, calls: int, switch_off):
    """checkout_routing.new_payment_gateway answers truthfully, then switches the gateway off right after
    its call number `calls` (the gateway is decided, the deposit not yet sent to the provider)."""
    real, seen = checkout_routing.new_payment_gateway, {"n": 0}

    def decide(db):
        answer = real(db)
        seen["n"] += 1
        if seen["n"] == calls:
            switch_off()
        return answer

    monkeypatch.setattr(checkout_routing, "new_payment_gateway", decide)


def test_nowpayments_switched_off_between_the_two_checks_writes_nothing(client, ledger, buyer, nowpayments_calls,
                                                                        monkeypatch):
    db = ledger
    _switch_off_after(monkeypatch, 1, lambda: np_configure(db, provider_enabled=False))
    refused = buy(client, buyer)
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert db.query(Deposit).count() == 0 and nowpayments_calls == []


def test_nowpayments_switched_off_after_the_deposit_is_written_is_never_called(client, ledger, buyer,
                                                                               nowpayments_calls, monkeypatch):
    db = ledger
    _switch_off_after(monkeypatch, 2, lambda: np_configure(db, provider_enabled=False))
    refused = buy(client, buyer)
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    deposit = db.query(Deposit).one()
    assert deposit.status == DepositStatus.FAILED and not deposit.external_payment_id
    assert nowpayments_calls == []


def test_soncopay_switched_off_before_the_deposit_is_written_writes_nothing(client, ledger, fake, buyer,
                                                                             monkeypatch):
    db = ledger
    boss = sp_setup(db)
    _switch_off_after(monkeypatch, 2, lambda: sp_off(db, boss))
    refused = buy(client, buyer)
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert db.query(Deposit).count() == 0 and not [c for c in fake.calls if c[0] == "POST"]


def test_soncopay_switched_off_after_the_deposit_is_written_is_never_called(client, ledger, fake, buyer,
                                                                            monkeypatch):
    db = ledger
    boss = sp_setup(db)
    real, seen = sp.checkout_environment, {"n": 0}

    def environment_then_off(db_):
        answer = real(db_)
        seen["n"] += 1
        if seen["n"] == 1:                                          # the deposit is written with this answer
            sp_off(db, boss)
        return answer

    monkeypatch.setattr(sp, "checkout_environment", environment_then_off)
    refused = buy(client, buyer)
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    db.expire_all()
    deposit = db.query(Deposit).one()
    assert deposit.status == DepositStatus.FAILED and deposit.payment_provider == "soncopay"
    assert not deposit.external_payment_id and not [c for c in fake.calls if c[0] == "POST"]


def test_a_failed_soncopay_payment_is_not_retried_while_soncopay_is_off(client, ledger, fake, buyer):
    db = ledger
    boss = sp_setup(db)
    fake.fail_create = 502
    assert buy(client, buyer, key="k-retry").status_code == 502     # the deposit is FAILED, no payment
    fake.fail_create = None
    posts = len([c for c in fake.calls if c[0] == "POST"])
    sp_off(db, boss)
    refused = buy(client, buyer, key="k-retry")                     # the same key: a retry
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert len([c for c in fake.calls if c[0] == "POST"]) == posts  # SoncoPay was not asked
    db.expire_all()
    assert db.query(Deposit).one().status == DepositStatus.FAILED
    sp.update(db, boss, password=ADMIN_PASSWORD, enabled=True)      # on again: the retry goes through
    done = buy(client, buyer, key="k-retry")
    assert done.status_code == 200, done.text
    assert done.json()["provider"] == "soncopay"


def test_a_failed_soncopay_payment_is_not_retried_in_the_other_environment(client, ledger, fake, buyer):
    db = ledger
    boss = sp_setup(db, live=True)
    fake.fail_create = 502
    assert buy(client, buyer, key="k-env").status_code == 502       # a Test deposit
    fake.fail_create = None
    sp.update(db, boss, password=ADMIN_PASSWORD, environment="live", confirmation=sp.CONFIRM_LIVE)
    posts = len([c for c in fake.calls if c[0] == "POST"])
    refused = buy(client, buyer, key="k-env")
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert len([c for c in fake.calls if c[0] == "POST"]) == posts


def test_a_failed_soncopay_payment_is_not_retried_while_a_switch_moves_during_the_retry(client, ledger, fake,
                                                                                         buyer, monkeypatch):
    db = ledger
    boss = sp_setup(db)
    fake.fail_create = 502
    assert buy(client, buyer, key="k-race").status_code == 502
    fake.fail_create = None
    posts = len([c for c in fake.calls if c[0] == "POST"])
    real = sp.checkout_environment
    seen = {"n": 0}

    def environment_then_off(db_):
        answer = real(db_)
        seen["n"] += 1
        if seen["n"] == 1:                                          # the endpoint's check passes...
            sp_off(db, boss)                                        # ...then SoncoPay is switched off
        return answer

    monkeypatch.setattr(sp, "checkout_environment", environment_then_off)
    refused = buy(client, buyer, key="k-race")
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert len([c for c in fake.calls if c[0] == "POST"]) == posts


# ===========================================================================
# 4. Existing payments keep working whatever the switches say
# ===========================================================================

def test_an_existing_soncopay_payment_is_still_read_and_confirmed_while_soncopay_is_off(client, ledger, fake, buyer):
    db = ledger
    boss = sp_setup(db)
    created = buy(client, buyer)
    deposit = deposit_of(db, created)
    sp_off(db, boss)
    np_configure(db, provider_enabled=False)                        # both gateways off
    fake.set(deposit.external_payment_id, status="paid")
    reads = len(fake.reads())
    checked = client.post(f"/api/v1/payments/check/{deposit.id}", headers=bearer(buyer))
    assert checked.status_code == 200, checked.text
    assert len(fake.reads()) > reads
    db.expire_all()
    assert db.query(Deposit).filter(Deposit.id == deposit.id).one().status == DepositStatus.VALIDATED
    again = post_webhook(client, "payment.paid", {"id": deposit.external_payment_id, "status": "paid"},
                         delivery="dlv_after_off")
    assert again.status_code == 200                                 # verified and handled, nothing twice


# ===========================================================================
# 5. D3: switching NOWPayments back on while automatic payouts are configured on
# ===========================================================================

@pytest.fixture
def resumable(ledger, engine_on):
    """Automatic payouts configured on, the provider (master switch) off: switching it on resumes payouts."""
    np_configure(ledger, provider_enabled=False)
    return member(ledger, "activator", admin=True)                  # manage + activate permissions


def tested(db, hours_ago: float):
    row = db.query(PaymentSettings).first()
    row.last_connection_test_status, row.last_connection_ok_at = "OK", NOW - timedelta(hours=hours_ago)
    db.commit()


def resume(db, actor, confirmation=None, version=True):
    return pc.update_settings(db, actor, {"provider_enabled": True}, password=PASSWORD, confirmation=confirmation,
                              now=NOW, expected_version=pc.load(db).version if version else None)


def refused_code(call) -> str:
    with pytest.raises(pc.PaymentConfigError) as error:
        call()
    return error.value.code


def test_resuming_payouts_needs_a_recent_connection_test_the_phrase_and_the_version(ledger, resumable):
    db, actor = ledger, resumable
    assert refused_code(lambda: resume(db, actor, pc.CONFIRM_PROVIDER_RESUME)) == "UNSAFE_ACTIVATION"   # never tested
    tested(db, 25)
    assert refused_code(lambda: resume(db, actor, pc.CONFIRM_PROVIDER_RESUME)) == "UNSAFE_ACTIVATION"   # too old
    tested(db, 1)
    assert refused_code(lambda: resume(db, actor)) == "CONFIRMATION_REQUIRED"
    assert refused_code(lambda: resume(db, actor, "resume nowpayments")) == "CONFIRMATION_REQUIRED"
    assert refused_code(lambda: resume(db, actor, pc.CONFIRM_PROVIDER_RESUME, version=False)) == "VERSION_REQUIRED"
    db.expire_all()
    assert pc.load(db).provider_enabled is False                    # every refusal changed nothing
    assert resume(db, actor, pc.CONFIRM_PROVIDER_RESUME).provider_enabled is True
    audit = db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first()
    assert audit.action == "SETTINGS_UPDATED" and audit.actor_id == actor.id
    assert audit.new_values["provider_enabled"] is True and audit.new_values["payouts_may_resume"] is True
    assert audit.new_values["connection_test_ok_at"]


def test_resuming_payouts_still_needs_the_activation_permission(ledger, resumable):
    db = ledger
    manager = member(db, "manager", admin=True, permissions=(pc.PERMISSION_MANAGE,))
    tested(db, 1)
    assert refused_code(lambda: resume(db, manager, pc.CONFIRM_PROVIDER_RESUME)) == "ACTIVATION_PERMISSION_REQUIRED"
    assert pc.load(db).provider_enabled is False


def test_the_provider_without_automatic_payouts_comes_back_without_the_phrase(ledger):
    db = ledger
    np_configure(db, provider_enabled=False, crypto_auto_payout_enabled=False)
    actor = member(db, "activator", admin=True)
    assert resume(db, actor).provider_enabled is True               # nothing resumes: an ordinary change


def test_the_phrase_is_offered_only_while_switching_on_would_resume_payouts(ledger, engine_on):
    db = ledger
    assert "provider_enabled" not in pc.settings_view(db)["confirmations"]          # provider on
    np_configure(db, provider_enabled=False)
    assert pc.settings_view(db)["confirmations"]["provider_enabled"] == pc.CONFIRM_PROVIDER_RESUME
    np_configure(db, crypto_auto_payout_enabled=False)
    assert "provider_enabled" not in pc.settings_view(db)["confirmations"]


def test_resuming_through_the_api_is_refused_without_the_phrase(client, ledger, resumable):
    db, actor = ledger, resumable
    from datetime import datetime

    row = db.query(PaymentSettings).first()                         # the API decides with the real clock
    row.last_connection_test_status, row.last_connection_ok_at = "OK", datetime.utcnow() - timedelta(minutes=5)
    db.commit()
    body = {"changes": {"provider_enabled": True}, "current_password": PASSWORD,
            "expected_version": pc.load(db).version}
    refused = client.put("/api/v1/admin/finance/settings", headers=bearer(actor), json=body)
    assert refused.status_code in (409, 422) and code_of(refused) == "CONFIRMATION_REQUIRED"
    db.expire_all()
    assert pc.load(db).provider_enabled is False


# ===========================================================================
# 6. D4: payouts already handed over are followed up, by status only, while the provider is off
# ===========================================================================

def test_the_status_only_provider_reads_and_refuses_everything_else():
    inner = FakeProvider()
    window = engine.StatusOnlyProvider(inner)
    assert window.payout_status("batch-1") == "PROCESSING" and inner.status_calls == ["batch-1"]
    assert getattr(window, "payout_details", None) is None          # the fake has none: reported as missing
    for name in ("create_payout", "balance", "minimum", "network_fee", "check_session", "validate_address"):
        with pytest.raises(engine.PayoutNotAllowed):
            getattr(window, name)
    assert inner.created == []


def test_a_payout_finished_while_the_provider_is_off_is_completed_and_nothing_new_is_sent(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    assert run(db, provider)["members"] == {"SUBMITTED": 1}
    other = member(db, "m2", method="CRYPTO")
    commission(db, other, "5.00")
    np_configure(db, provider_enabled=False)
    provider.statuses["batch-1"] = "FINISHED"
    report = run(db, provider)
    assert report["reconcile_only"] == "PROVIDER_DISABLED" and report["reconciled"] == {"COMPLETED": 1}
    assert cashouts(db, user)[0].status == "completed"
    assert len(provider.created) == 1 and cashouts(db, other) == []
    assert run(db, provider) == {"enabled": False, "reconciled": {}, "members": {}}      # nothing open: no call
    assert provider.status_calls.count("batch-1") == 1


def test_a_payout_rejected_while_the_provider_is_off_releases_the_balance_and_is_not_resent(ledger, engine_on):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    run(db, provider)
    np_configure(db, provider_enabled=False)
    provider.statuses["batch-1"] = "REJECTED"
    assert run(db, provider)["reconciled"] == {"FAILED": 1}
    assert cashouts(db, user)[0].status == "failed" and len(provider.created) == 1


def test_without_payout_credentials_the_provider_off_reads_nothing(ledger, engine_on, monkeypatch):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    provider = FakeProvider()
    run(db, provider)
    np_configure(db, provider_enabled=False)
    monkeypatch.setattr(settings, "NOWPAYMENTS_PAYOUT_API_KEY", "")
    calls = len(provider.status_calls)
    assert run(db, provider) == {"enabled": False, "reconciled": {}, "members": {}}
    assert len(provider.status_calls) == calls


# ===========================================================================
# 7. Automatic payouts keep every existing gate (the provider switch is only one of them)
# ===========================================================================

@pytest.mark.parametrize("gate", ["server_switch", "crypto_cashout_enabled", "crypto_auto_payout_enabled",
                                  "suspended", "payout_credentials", "fee_terms"])
def test_with_the_provider_on_every_other_payout_gate_still_holds(ledger, engine_on, monkeypatch, gate):
    db = ledger
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    if gate == "server_switch":
        monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", False)
    elif gate == "suspended":
        row = db.query(PaymentSettings).first()
        row.payout_suspended_reason = "SYNTHETIC_REVIEW"
        db.commit()
    elif gate == "payout_credentials":
        monkeypatch.setattr(settings, "NOWPAYMENTS_PAYOUT_TOTP_SECRET", "")
    elif gate == "fee_terms":
        np_configure(db, fee_terms_approved=False)
    else:
        np_configure(db, **{gate: False})
    provider = FakeProvider()
    run(db, provider)
    assert provider.created == [] and cashouts(db, user) == []


def test_checkout_switch_and_payouts_stay_independent(ledger, engine_on):
    db = ledger
    np_configure(db, checkout_enabled=False)
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    assert run(db, FakeProvider())["members"] == {"SUBMITTED": 1}  # checkout off: payouts unaffected
    assert checkout_routing.new_payment_gateway(db) is None         # ... and no new member payment
