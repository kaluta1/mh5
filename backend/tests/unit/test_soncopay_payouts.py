"""SoncoPay automatic USDT BEP20 commission payouts (app.services.soncopay_payouts + cashout_engine).

Everything runs against an in-process fake of the documented SoncoPay API (httpx.MockTransport);
the network guard refuses the real soncopay.com host. No money, no real key.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.checkout_gateway import SoncoPayPayoutDestination
from app.services import cashout_engine as engine
from app.services import payment_config
from app.services import soncopay_payouts as spo
from app.services import soncopay_settings as sp
from tests.unit.test_admin_security_hardening import PASSWORD as ADMIN_PASSWORD
from tests.unit.test_admin_security_hardening import bearer
from tests.unit.test_dual_cashout import (  # noqa: F401
    NOW,
    OTHER_WALLET,
    WALLET,
    approve_wallet,
    cashouts,
    commission,
    configure,
    engine_on,
    ledger,
    member,
    no_network,
)
from tests.unit.test_new_business_model import _assert_all_journals_balance, world  # noqa: F401
from tests.unit.test_super_admin import superadmin

pytestmark = [pytest.mark.unit, pytest.mark.discontinued]

LIVE_KEY, LIVE_SECRET = "sp_live_synthetic_payout_key_01", "whsec_live_synthetic_secret_02"
FEE = "0.10"


class FakeSoncoPay:
    """The documented payout endpoints, in memory."""

    def __init__(self):
        self.calls: list = []
        self.destinations: dict = {}
        self.payouts: dict = {}
        self.balance, self.fee, self.min_payout = "100", FEE, "1"
        self.auto_confirm = False
        self.refuse_payout = None            # (status, code) answered to POST /v1/payouts
        self.drop_payout = False             # POST /v1/payouts gets no answer (after creating it)
        self.extra_open = 0                  # destinations of the merchant outside MyHigh5

    def _dest_view(self, d):
        return {"id": d["id"], "object": "payout_destination", "livemode": True, "kind": "crypto",
                "currency": "USDT", "status": d["status"], "usable": d["usable"], "usable_from": d.get("usable_from"),
                "confirmed_at": d.get("confirmed_at"),
                "details": {"asset": "USDT", "network": "BSC", "address": d["address"]}}

    def confirm(self, pid, *, usable=False):
        d = self.destinations[pid]
        d.update(status="active", usable=usable, confirmed_at="2026-10-29T10:00:00+00:00",
                 usable_from="2026-10-30T10:00:00+00:00")

    def complete(self, po, *, tx="0x" + "ab" * 32, amount=None, fee=None):
        self.payouts[po].update(status="completed", tx_hash=tx)
        if amount is not None:
            self.payouts[po]["amount"] = amount
        if fee is not None:
            self.payouts[po]["fee"] = fee

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append((method, path))
        assert request.headers["X-Api-Key"] == LIVE_KEY
        body = json.loads(request.content) if request.content else {}
        if path == "/v1/balances":
            return httpx.Response(200, json={"livemode": True, "balances": {"USDT": self.balance},
                                             "available": {"USDT": self.balance}, "reserved": {}})
        if path == "/v1/payout-fees":
            return httpx.Response(200, json={"fees": {"USDT:BSC": self.fee, "USDT:TRON": "1"},
                                             "min_payout_usd": self.min_payout})
        if path == "/v1/payout-destinations" and method == "GET":
            items = [self._dest_view(d) for d in self.destinations.values()]
            items += [{"id": f"pd_other{i}", "status": "active"} for i in range(self.extra_open)]
            return httpx.Response(200, json={"items": items, "settings": {"cooldown_hours": 24,
                                                                          "api_auto_confirm": self.auto_confirm}})
        if path == "/v1/payout-destinations" and method == "POST":
            assert (body["kind"], body["asset"], body["network"]) == ("crypto", "USDT", "BSC")
            open_now = sum(1 for d in self.destinations.values() if d["status"] in spo.OPEN_PROVIDER_STATUSES)
            for d in self.destinations.values():
                if d["address"].lower() == body["address"].lower() and d["status"] != "disabled":
                    return httpx.Response(409, json={"code": "destination_duplicate", "destination_id": d["id"]})
            if open_now + self.extra_open >= 50:
                return httpx.Response(409, json={"code": "destination_limit", "detail": "50 at most"})
            pid = f"pd_{len(self.destinations) + 1:06d}"
            self.destinations[pid] = {"id": pid, "address": body["address"], "status": "pending_confirmation",
                                      "usable": False}
            if self.auto_confirm:
                self.confirm(pid)
            return httpx.Response(201, json=self._dest_view(self.destinations[pid]))
        if path.startswith("/v1/payout-destinations/"):
            pid = path.rsplit("/", 1)[1]
            if pid not in self.destinations:
                return httpx.Response(404, json={"code": "destination_not_found"})
            if method == "DELETE":
                self.destinations[pid].update(status="disabled", usable=False)
            return httpx.Response(200, json=self._dest_view(self.destinations[pid]))
        if path == "/v1/payouts" and method == "POST":
            if self.refuse_payout:
                status, code = self.refuse_payout
                return httpx.Response(status, json={"code": code, "detail": "synthetic"})
            for p in self.payouts.values():
                if p["reference"] == body["reference"]:
                    return httpx.Response(200, json=p)
            d = self.destinations.get(body["destination_id"])
            if d is None or d["status"] != "active":
                return httpx.Response(409, json={"code": "destination_not_confirmed"})
            if not d["usable"]:
                return httpx.Response(409, json={"code": "destination_cooling_down", "usable_from": d["usable_from"]})
            po = f"po_{len(self.payouts) + 1:06d}"
            self.payouts[po] = {"id": po, "object": "payout", "status": "queued", "asset": "USDT", "network": "BSC",
                                "amount": body["amount"], "fee": self.fee, "address": d["address"],
                                "destination_id": d["id"], "reference": body["reference"], "tx_hash": None}
            if self.drop_payout:
                raise httpx.ReadTimeout("synthetic: no answer")
            return httpx.Response(201, json=self.payouts[po])
        if path == "/v1/payouts" and method == "GET":
            return httpx.Response(200, json={"items": list(self.payouts.values())})
        if path.startswith("/v1/payouts/"):
            po = path.rsplit("/", 1)[1]
            return httpx.Response(200, json=self.payouts[po]) if po in self.payouts else \
                httpx.Response(404, json={"code": "not_found"})
        return httpx.Response(404, json={"detail": "not found"})

    def posts(self, path):
        return [c for c in self.calls if c == ("POST", path)]


@pytest.fixture
def fake(monkeypatch):
    f = FakeSoncoPay()
    monkeypatch.setattr(spo, "_transport", lambda: httpx.MockTransport(f.handler))
    monkeypatch.setattr(spo.time, "sleep", lambda *_a: None)
    return f


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://api.example.test")


def soncopay_live(db, *, authorize=True):
    boss = superadmin(db, f"boss{db.query(SoncoPayPayoutDestination).count()}x{id(db) % 1000}")
    sp.update(db, boss, password=ADMIN_PASSWORD, credentials={"LIVE_API_KEY": LIVE_KEY,
                                                              "LIVE_WEBHOOK_SECRET": LIVE_SECRET})
    sp.update(db, boss, password=ADMIN_PASSWORD, environment="live", confirmation=sp.CONFIRM_LIVE)
    sp.update(db, boss, password=ADMIN_PASSWORD, enabled=True)
    if authorize:
        spo.authorize(db, boss, password=ADMIN_PASSWORD, confirmation=spo.CONFIRM_AUTHORIZATION,
                      note="SoncoPay support ticket 1234 confirmed member payouts")
    return boss


@pytest.fixture
def payouts_on(ledger, engine_on):
    """Every switch on, the SoncoPay fee behaviour selected, SoncoPay Live and authorized."""
    configure(ledger, provider_fee_mode=payment_config.FEE_MODE_ADDED)
    soncopay_live(ledger)
    return ledger


def run(db, now=NOW):
    return engine.run_cycle(db, now=now)


def destination(db, user):
    db.expire_all()
    return db.query(SoncoPayPayoutDestination).filter(SoncoPayPayoutDestination.user_id == user.id) \
        .order_by(SoncoPayPayoutDestination.id.desc()).first()


def ready_member(db, fake, name="m1", *, amount="2.00"):
    """An approved member whose destination SoncoPay confirmed and whose waiting period is over."""
    user = member(db, name, method="CRYPTO")
    row = commission(db, user, amount)
    run(db)                                                         # queued and registered
    pid = destination(db, user).destination_id
    fake.confirm(pid, usable=True)
    run(db)                                                         # read back: usable -> paid in this cycle
    return user, row


# ===========================================================================
# Readiness and the owner's authorization
# ===========================================================================

def test_without_the_owners_authorization_nothing_is_registered_or_paid(ledger, engine_on, fake):
    db = ledger
    configure(db, provider_fee_mode=payment_config.FEE_MODE_ADDED)
    soncopay_live(db, authorize=False)
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    report = run(db)
    assert report["enabled"] is False and "SONCOPAY_PAYOUTS_NOT_AUTHORIZED" in report["blocked_by"]
    assert fake.calls == [] and destination(db, user) is None and cashouts(db, user) == []


def test_test_mode_never_pays(ledger, engine_on, fake):
    db = ledger
    configure(db, provider_fee_mode=payment_config.FEE_MODE_ADDED)
    boss = soncopay_live(db)
    sp.update(db, boss, password=ADMIN_PASSWORD, credentials={"TEST_API_KEY": "sp_test_synthetic_key_0000001",
                                                              "TEST_WEBHOOK_SECRET": "whsec_test_synthetic_01"})
    sp.update(db, boss, password=ADMIN_PASSWORD, environment="test")
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    assert "SONCOPAY_NOT_LIVE" in run(db)["blocked_by"] and fake.calls == []


def test_the_authorization_needs_a_super_admin_the_password_and_the_phrase(ledger, fake):
    db = ledger
    boss = soncopay_live(db, authorize=False)
    with pytest.raises(payment_config.PaymentConfigError):
        spo.authorize(db, boss, password="wrong", confirmation=spo.CONFIRM_AUTHORIZATION, note="ticket 1234 ok ok")
    db.rollback()
    with pytest.raises(ValueError):
        spo.authorize(db, boss, password=ADMIN_PASSWORD, confirmation="yes", note="ticket 1234 ok ok")
    db.rollback()
    plain = member(db, "plain", admin=True)
    with pytest.raises(PermissionError):
        spo.authorize(db, plain, password="x", confirmation=spo.CONFIRM_AUTHORIZATION, note="ticket 1234 ok ok")
    db.rollback()
    assert spo.authorization(db) is None


def test_the_fee_behaviour_must_be_sonco_pays_added_fee(ledger, engine_on, fake):
    db = ledger                                                     # engine_on selects DEDUCTED_BY_PROVIDER
    soncopay_live(db)
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    report = run(db)
    assert report["stopped"] == "PROVIDER_FEE_MODE_UNVERIFIED" and fake.posts("/v1/payouts") == []


# ===========================================================================
# Destination lifecycle
# ===========================================================================

def test_an_approved_wallet_is_registered_and_waits_for_dashboard_confirmation(payouts_on, fake):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    report = run(db)
    row = destination(db, user)
    assert (row.status, row.usable) == ("PENDING_CONFIRMATION", False) and row.destination_id.startswith("pd_")
    assert report["members"] == {"DESTINATION_AWAITING_CONFIRMATION": 1}
    assert fake.posts("/v1/payouts") == [] and cashouts(db, user) == []


def test_a_confirmed_destination_waits_for_the_security_period(payouts_on, fake):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=False)
    report = run(db)
    row = destination(db, user)
    assert (row.status, row.usable) == ("ACTIVE", False) and row.usable_from is not None
    assert report["members"] == {"DESTINATION_WAITING_PERIOD": 1} and fake.posts("/v1/payouts") == []


def test_an_unapproved_wallet_is_never_registered(payouts_on, fake):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO", approved=False)
    commission(db, user, "2.00")
    run(db)
    assert destination(db, user) is None and fake.posts("/v1/payout-destinations") == []


def test_a_wallet_change_supersedes_and_disables_the_old_destination(payouts_on, fake):
    db = payouts_on
    user, _row = ready_member(db, fake)
    old = destination(db, user)
    user.usdt_wallet_address = OTHER_WALLET
    db.commit()
    approve_wallet(db, user)
    commission(db, user, "3.00")
    run(db)
    db.expire_all()
    old = db.get(SoncoPayPayoutDestination, old.id)
    assert old.status == "SUPERSEDED" and old.usable is False
    assert fake.destinations[old.destination_id]["status"] == "disabled"
    new = destination(db, user)
    assert new.id != old.id and new.status == "PENDING_CONFIRMATION"
    assert len(fake.posts("/v1/payouts")) == 1                       # only the first commission, to the old wallet


def test_the_fifty_destination_limit_queues_and_never_disables_another_member(payouts_on, fake):
    db = payouts_on
    fake.extra_open = 50                                            # the merchant account is full
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    report = run(db)
    row = destination(db, user)
    assert row.status == "QUEUED" and report["destinations"].get("waiting_for_slot") == 1
    assert [c for c in fake.calls if c[0] == "DELETE"] == []
    fake.extra_open = 49
    run(db)
    assert destination(db, user).status == "PENDING_CONFIRMATION"


def test_automatic_confirmation_still_respects_the_waiting_period(payouts_on, fake):
    db = payouts_on
    fake.auto_confirm = True
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    assert run(db)["members"] == {"DESTINATION_WAITING_PERIOD": 1}
    assert destination(db, user).status == "ACTIVE" and fake.posts("/v1/payouts") == []


def test_a_destination_whose_address_differs_is_disabled_and_never_paid(payouts_on, fake):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    pid = destination(db, user).destination_id
    fake.confirm(pid, usable=True)
    fake.destinations[pid]["address"] = OTHER_WALLET                # SoncoPay reports another address
    run(db)
    row = destination(db, user)
    assert (row.status, row.last_error) == ("DISABLED", "ADDRESS_MISMATCH") and fake.posts("/v1/payouts") == []


# ===========================================================================
# Payouts
# ===========================================================================

def test_one_commission_one_payout_net_of_the_fee_paid_only_after_completion(payouts_on, fake):
    db = payouts_on
    user, row = ready_member(db, fake)
    [po] = fake.payouts.values()
    assert Decimal(po["amount"]) == Decimal("2.00") - Decimal(FEE)    # the member bears the fee
    assert po["reference"] == f"c{row.id}-a1"
    out = cashouts(db, user)[0]
    assert out.status == "processing" and Decimal(out.amount_sent) == Decimal("1.90")
    db.refresh(row)
    assert row.status != CommissionStatus.PAID                      # not paid before SoncoPay says so
    fake.complete(po["id"])
    run(db)
    out = cashouts(db, user)[0]
    assert out.status == "completed" and out.tx_hash == "0x" + "ab" * 32
    assert out.fee_reconciliation == "PROVIDER_VERIFIED" and Decimal(out.net_received) == Decimal("1.90")
    assert Decimal(out.network_fee_actual) == Decimal(FEE) and out.fee_flag is None
    db.refresh(row)
    assert row.status == CommissionStatus.PAID
    _assert_all_journals_balance(db)


def test_a_fee_other_than_the_one_withheld_suspends_payouts(payouts_on, fake):
    db = payouts_on
    user, _row = ready_member(db, fake)
    [po] = fake.payouts.values()
    fake.complete(po["id"], fee="0.20")                             # SoncoPay charged more than it published
    run(db)
    out = cashouts(db, user)[0]
    assert out.status == "completed" and out.fee_flag is not None
    assert payment_config.load(db).suspended_reason is not None
    commission(db, user, "4.00")
    assert run(db).get("stopped") == "PAYOUTS_SUSPENDED"


def test_each_commission_gets_its_own_payout_never_batched(payouts_on, fake):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    commission(db, user, "3.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    run(db)
    amounts = sorted(Decimal(p["amount"]) for p in fake.payouts.values())
    assert amounts == [Decimal("1.90"), Decimal("2.90")]
    assert len({p["reference"] for p in fake.payouts.values()}) == 2


def test_below_the_minimum_stays_unpaid(payouts_on, fake):
    db = payouts_on
    fake.min_payout = "5"
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    assert run(db)["members"] == {"BELOW_PROVIDER_MINIMUM": 1} and fake.posts("/v1/payouts") == []


def test_insufficient_balance_stays_unpaid(payouts_on, fake):
    db = payouts_on
    fake.balance = "1"
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    assert run(db)["members"] == {"INSUFFICIENT_PROVIDER_BALANCE": 1} and fake.posts("/v1/payouts") == []


@pytest.mark.parametrize("refusal,outcome", [
    ((429, "payout_velocity_exceeded"), "PROVIDER_VELOCITY_LIMIT"),
    ((422, "payout_funds_on_hold"), "PROVIDER_FUNDS_ON_HOLD"),
    ((403, "policy_denied"), "PROVIDER_POLICY_DENIED"),
    ((403, "api_key_ip_not_allowed"), "PROVIDER_IP_NOT_WHITELISTED"),
    ((403, "api_key_scope"), "PROVIDER_AUTH_FAILED"),
    ((409, "destination_cooling_down"), "DESTINATION_NOT_USABLE"),
])
def test_documented_refusals_release_the_commission_without_blaming_the_member(payouts_on, fake, refusal, outcome):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    fake.refuse_payout = refusal
    report = run(db)
    assert report["members"] == {outcome: 1}
    out = cashouts(db, user)[0]
    assert (out.status, out.failure_code) == ("cancelled", outcome)
    db.refresh(row)
    assert row.payout_reference is None and row.status != CommissionStatus.PAID
    fake.refuse_payout = None
    run(db, now=NOW + timedelta(hours=1))                           # retried once the refusal is gone
    assert len(fake.payouts) == 1


def test_a_lost_answer_is_unknown_never_resent_and_found_by_its_reference(payouts_on, fake):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    row = commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    fake.drop_payout = True
    assert run(db)["members"] == {"OUTCOME_UNKNOWN": 1}
    fake.drop_payout = False
    for _ in range(3):
        run(db)
    assert len(fake.posts("/v1/payouts")) == 1 and len(fake.payouts) == 1
    out = cashouts(db, user)[0]
    assert out.provider_batch_id == next(iter(fake.payouts))        # located by the reference
    fake.complete(out.provider_batch_id)
    run(db)
    db.refresh(row)
    assert cashouts(db, user)[0].status == "completed" and row.status == CommissionStatus.PAID


def test_a_failed_payout_is_released_and_paid_again_as_a_new_attempt(payouts_on, fake):
    db = payouts_on
    configure(db, retry_backoff_hours=1)
    user, row = ready_member(db, fake)
    [po] = fake.payouts.values()
    fake.payouts[po["id"]]["status"] = "failed"
    run(db)
    assert cashouts(db, user)[0].status == "failed"
    run(db, now=NOW + timedelta(hours=2))
    assert len(fake.payouts) == 2 and fake.payouts["po_000002"]["reference"] == f"c{row.id}-a2"


def test_two_workers_never_pay_the_same_commission_twice(payouts_on, fake):
    db = payouts_on
    user, _row = ready_member(db, fake)
    run(db)
    run(db)
    assert len(fake.payouts) == 1 and len(fake.posts("/v1/payouts")) == 1


# ===========================================================================
# The activation guard and no fallback
# ===========================================================================

def test_without_the_server_activation_nothing_is_sent(payouts_on, fake, monkeypatch):
    db = payouts_on
    monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", False)
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    report = run(db)
    assert report["enabled"] is False and fake.posts("/v1/payouts") == [] and cashouts(db, user) == []


def test_the_payout_call_itself_refuses_without_activation(payouts_on, fake, monkeypatch):
    db = payouts_on
    monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", False)
    provider = spo.SoncoPayPayoutProvider(db)
    with pytest.raises(spo.PayoutRefused) as refused:
        provider.create_payout(address=WALLET, amount=Decimal("1.90"), currency="usdtbsc", external_id="c1-a1")
    assert refused.value.platform_fault == "NOT_ACTIVATED" and fake.calls == []


def test_activation_withdrawn_after_reservation_sends_nothing(payouts_on, fake, monkeypatch):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    real_lock = payment_config.lock_settings

    def lock_after_withdrawal(session):
        monkeypatch.setattr(settings, "AUTOMATIC_PAYOUT_ACTIVATED", False)
        return real_lock(session)

    monkeypatch.setattr(payment_config, "lock_settings", lock_after_withdrawal)
    run(db)
    assert fake.posts("/v1/payouts") == []
    assert all(c.status == "cancelled" for c in cashouts(db, user))


def test_nowpayments_is_never_used(payouts_on, fake, monkeypatch):
    from app.services import nowpayments_service

    def never(*_a, **_k):
        raise AssertionError("NOWPayments was called")

    for name in ("create_single_payout_sync", "custody_balance_sync", "payout_min_amount_sync"):
        monkeypatch.setattr(nowpayments_service, name, never)
    ready_member(db=payouts_on, fake=fake)
    assert len(fake.payouts) == 1


def test_a_soncopay_outage_pays_nothing(payouts_on, fake, monkeypatch):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    fake.confirm(destination(db, user).destination_id, usable=True)
    monkeypatch.setattr(spo, "_transport", lambda: httpx.MockTransport(lambda r: httpx.Response(503)))
    report = run(db)
    assert report.get("stopped") in ("PROVIDER_AUTH_FAILED", "PAYOUT_ASSET_UNVERIFIED", "PROVIDER_FACTS_UNAVAILABLE")
    assert fake.posts("/v1/payouts") == [] and cashouts(db, user) == []


# ===========================================================================
# Webhooks, views
# ===========================================================================

def test_a_payout_webhook_only_wakes_the_cycle(payouts_on, fake, client, monkeypatch):
    import hashlib
    import hmac
    import time as _time

    woken = []
    monkeypatch.setattr(engine, "request_cycle", lambda: woken.append(1) or True)
    raw = json.dumps({"event": "payout.completed", "data": {"id": "po_000001", "status": "completed"}}).encode()
    ts = int(_time.time())
    mac = hmac.new(LIVE_SECRET.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    headers = {"X-SoncoPay-Signature": f"t={ts},v1={mac}", "X-SoncoPay-Delivery-Id": "dlv_p1",
               "Content-Type": "application/json"}
    assert client.post("/api/v1/webhooks/soncopay", content=raw, headers=headers).status_code == 200
    assert client.post("/api/v1/webhooks/soncopay", content=raw, headers=headers).json().get("duplicate") is True
    assert woken == [1] and fake.calls == []


def test_the_member_is_told_where_their_wallet_stands(payouts_on, fake, client):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    from app.services.soncopay_payouts import member_status

    status = member_status(db, user)
    assert status["destination_state"] == "DESTINATION_AWAITING_CONFIRMATION"
    assert "SoncoPay" in status["message"] and status["network"] == "USDT on BNB Smart Chain (BEP20)"


def test_the_admin_view_masks_addresses_and_never_shows_the_key(payouts_on, fake, client):
    db = payouts_on
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "2.00")
    run(db)
    boss = superadmin(db, "viewer")
    answer = client.get("/api/v1/admin/finance/soncopay/payouts?provider=true", headers=bearer(boss))
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["counts"] == {"PENDING_CONFIRMATION": 1} and WALLET not in answer.text
    assert LIVE_KEY not in answer.text and body["provider"]["fee"] == FEE
    plain = member(db, "plain")
    assert client.get("/api/v1/admin/finance/soncopay/payouts", headers=bearer(plain)).status_code == 403
