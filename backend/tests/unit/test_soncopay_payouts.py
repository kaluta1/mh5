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
        self.asset_minimum = None            # limits["USDT:BSC"].minimum, as SoncoPay answered on 2026-10-29
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
            answer = {"fees": {"USDT:BSC": self.fee, "USDT:TRON": "1"}, "min_payout_usd": self.min_payout}
            if self.asset_minimum is not None:
                answer["limits"] = {"USDT:BSC": {"asset": "USDT", "network": "BSC", "minimum": self.asset_minimum,
                                                 "fee": self.fee, "available": True},
                                    "USDT:TRON": {"minimum": "5", "fee": "2.2701", "available": True}}
            return httpx.Response(200, json=answer)
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
    monkeypatch.setattr(spo, "_limits", {"facts": None, "read_at": None, "checked": 0.0})
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


def test_each_commission_that_clears_the_threshold_gets_its_own_payout(payouts_on, fake):
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
    # Owner decision 2026-10-29 (Option A): it waits for more commissions instead of being lost.
    assert run(db)["members"] == {"ACCUMULATING_BELOW_THRESHOLD": 1} and fake.posts("/v1/payouts") == []


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


# ===========================================================================
# Owner decision 2026-10-29 (Option A): small commissions accumulate per member
# ===========================================================================
# The figures SoncoPay answered for this account on 2026-10-29: USDT:BSC fee 0.23, per-asset
# minimum 2, account-wide min_payout_usd 0.5. Threshold = 2 + 0.23 = 2.23.

def real_figures(db, fake, *, margin="0"):
    fake.fee, fake.min_payout, fake.asset_minimum = "0.23", "0.5", "2"
    configure(db, member_fee_cap_percent=Decimal("20.000"), member_fee_cap_usd=Decimal("1.00"),
              max_network_fee_percent=Decimal("20.000"), fee_estimate_margin_percent=Decimal(margin))


def payable_member(db, fake, name="m1", *, wallet=WALLET, amounts=()):
    """A member with an approved wallet whose SoncoPay destination is usable, then `amounts`."""
    from app.models.payment_config import CashoutFeeConsent

    user = member(db, name, method="CRYPTO", wallet=wallet)
    consent = db.query(CashoutFeeConsent).filter(CashoutFeeConsent.user_id == user.id).one()
    consent.cap_percent = Decimal("20.000")                         # the member accepted a 20 % limit
    db.commit()
    run(db)                                                         # registered at SoncoPay
    fake.confirm(destination(db, user).destination_id, usable=True)
    return user, [commission(db, user, a, when=NOW - timedelta(days=10 - i)) for i, a in enumerate(amounts)]


def test_the_asset_minimum_and_fee_come_from_soncopays_limits(fake):
    from dataclasses import replace

    real = {"fees": {"USDT:BSC": "0.23", "USDT:TRON": "1"}, "min_payout_usd": 0.5,
            "limits": {"USDT:BSC": {"minimum": "2", "fee": "0.23", "total_minimum": "2.23", "available": True},
                       "USDT:TRON": {"minimum": "5", "fee": "2.2701", "available": True}}}
    facts = spo.published_fee_and_minimum(real)
    assert (facts.fee, facts.minimum) == (Decimal("0.23"), Decimal("2"))     # not the account-wide 0.5
    config = payment_config.default_config()
    assert engine.payout_threshold(replace(config, fee_estimate_margin_percent=Decimal("0")),
                                   facts.minimum, facts.fee) == Decimal("2.23")
    assert engine.payout_threshold(replace(config, fee_estimate_margin_percent=Decimal("10")),
                                   facts.minimum, facts.fee) == Decimal("2.26")   # 2.253 rounded up
    with pytest.raises(spo.PayoutUnavailable):                      # two different fees: never guessed
        spo.published_fee_and_minimum({**real, "fees": {"USDT:BSC": "0.20"}})
    with pytest.raises(spo.PayoutUnavailable):
        spo.published_fee_and_minimum({**real, "limits": {"USDT:BSC": {"minimum": "2", "fee": "0.23",
                                                                       "available": False}}})


def test_a_single_commission_above_the_threshold_is_still_paid_on_its_own(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user, [row] = payable_member(db, fake, amounts=["3.00"])
    assert run(db)["members"] == {"SUBMITTED": 1}
    [po] = fake.payouts.values()
    assert po["reference"] == f"c{row.id}-a1" and Decimal(po["amount"]) == Decimal("2.77")
    assert cashouts(db, user)[0].commission_id == row.id


def test_small_commissions_are_paid_together_once_they_reach_the_threshold(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["1.00", "0.80"])
    assert run(db)["members"] == {"ACCUMULATING_BELOW_THRESHOLD": 1}       # 1.80 < 2.23
    assert fake.posts("/v1/payouts") == [] and cashouts(db, user) == []
    rows.append(commission(db, user, "0.50"))                                # 2.30 >= 2.23
    assert run(db)["members"] == {"SUBMITTED": 1}
    [po] = fake.payouts.values()
    assert po["reference"] == f"m{user.id}-c{rows[0].id}-a1"
    assert Decimal(po["amount"]) == Decimal("2.07")                         # 2.30 less the 0.23 fee
    out = cashouts(db, user)[0]
    assert out.commission_id is None and out.gross_amount == Decimal("2.30")
    assert engine.payout_commission_ids(db, [out.id]) == {out.id: [r.id for r in rows]}
    for row in rows:
        db.refresh(row)
        assert row.status == CommissionStatus.APPROVED and row.payout_reference == out.payout_reference
    fake.complete(po["id"])
    run(db)
    run(db)                                                         # a repeated read changes nothing
    out = cashouts(db, user)[0]
    assert out.status == "completed" and out.fee_flag is None and Decimal(out.net_received) == Decimal("2.07")
    for row in rows:
        db.refresh(row)
        assert row.status == CommissionStatus.PAID and row.payout_reference == po["id"]
    assert len(fake.posts("/v1/payouts")) == 1
    assert engine.commission_payout_reconciliation(db)["problems"] == []
    assert engine.accumulated_payouts(db)[0]["commission_ids"] == [r.id for r in rows]
    _assert_all_journals_balance(db)
    from app.models.accounting import JournalEntry

    assert db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{out.id}").count() == 1


def test_a_larger_commission_is_paid_alone_and_the_small_ones_together(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["1.20", "5.00", "1.20"])
    run(db)
    references = sorted(p["reference"] for p in fake.payouts.values())
    assert references == sorted([f"c{rows[1].id}-a1", f"m{user.id}-c{rows[0].id}-a1"])
    combined = [c for c in cashouts(db, user) if c.commission_id is None]
    assert len(combined) == 1 and combined[0].gross_amount == Decimal("2.40")


def test_commissions_of_different_members_are_never_combined(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    payable_member(db, fake, "m1", amounts=["1.20"])
    payable_member(db, fake, "m2", wallet=OTHER_WALLET, amounts=["1.20"])
    assert run(db)["members"] == {"ACCUMULATING_BELOW_THRESHOLD": 2}
    assert fake.posts("/v1/payouts") == []


@pytest.mark.parametrize("change, waits", [
    ({"fee": "0.50"}, True),                  # threshold 2.50 > 2.30
    ({"asset_minimum": "3"}, True),           # threshold 3.23
    ({"fee": "0.10"}, False),                 # threshold 2.10
])
def test_the_threshold_follows_soncopays_published_fee_and_minimum(payouts_on, fake, change, waits):
    db = payouts_on
    real_figures(db, fake)
    for name, value in change.items():
        setattr(fake, name, value)
    _user, _rows = payable_member(db, fake, amounts=["1.15", "1.15"])
    outcome = run(db)["members"]
    if waits:
        assert outcome == {"ACCUMULATING_BELOW_THRESHOLD": 1} and fake.posts("/v1/payouts") == []
    else:
        assert outcome == {"SUBMITTED": 1}
        [po] = fake.payouts.values()
        assert Decimal(po["amount"]) == Decimal("2.30") - Decimal(fake.fee)


def test_a_fee_above_the_members_limit_holds_the_payout(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    configure(db, member_fee_cap_usd=Decimal("0.10"))               # SoncoPay charges 0.23
    user, rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    assert run(db)["members"] == {"NETWORK_FEE_ABOVE_MEMBER_LIMIT": 1}
    assert fake.posts("/v1/payouts") == [] and cashouts(db, user) == []
    for row in rows:
        db.refresh(row)
        assert row.payout_reference is None and row.status == CommissionStatus.APPROVED


def test_an_unapproved_wallet_or_a_cooling_destination_keeps_the_accumulated_commissions(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    waiting = member(db, "m1", method="CRYPTO", approved=False)
    commission(db, waiting, "1.20")
    commission(db, waiting, "1.20")
    [(code, count)] = run(db)["members"].items()
    assert code.startswith("WALLET_") and count == 1
    cooling = member(db, "m2", method="CRYPTO", wallet=OTHER_WALLET)
    run(db)
    fake.confirm(destination(db, cooling).destination_id, usable=False)  # in its 24-hour waiting period
    commission(db, cooling, "1.20")
    commission(db, cooling, "1.20")
    assert run(db)["members"].get("DESTINATION_WAITING_PERIOD") == 1
    assert fake.posts("/v1/payouts") == [] and cashouts(db) == []


def test_a_lost_answer_on_a_combined_payout_is_never_resent(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    fake.drop_payout = True
    assert run(db)["members"] == {"OUTCOME_UNKNOWN": 1}
    fake.drop_payout = False
    commission(db, user, "1.50")                                    # new earnings wait meanwhile
    for _ in range(3):
        run(db)
    assert len(fake.posts("/v1/payouts")) == 1 and len(fake.payouts) == 1
    out = cashouts(db, user)[0]
    assert out.provider_batch_id == next(iter(fake.payouts))        # located by its reference
    fake.complete(out.provider_batch_id)
    run(db)
    for row in rows:
        db.refresh(row)
        assert row.status == CommissionStatus.PAID
    _assert_all_journals_balance(db)


def test_a_failed_combined_payout_releases_every_commission_and_retries_as_a_new_attempt(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    configure(db, retry_backoff_hours=1)
    user, rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    run(db)
    [po] = fake.payouts.values()
    fake.payouts[po["id"]]["status"] = "failed"
    run(db)
    assert cashouts(db, user)[0].status == "failed"
    for row in rows:
        db.refresh(row)
        assert row.payout_reference is None and row.status == CommissionStatus.APPROVED
    run(db, now=NOW + timedelta(hours=2))
    assert len(fake.payouts) == 2
    assert fake.payouts["po_000002"]["reference"] == f"m{user.id}-c{rows[0].id}-a2"


def test_a_cancelled_commission_is_never_part_of_a_combined_payout(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    _user, rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    rows[1].status = CommissionStatus.CANCELLED                     # reversed before any payout
    db.commit()
    assert run(db)["members"] == {"ACCUMULATING_BELOW_THRESHOLD": 1}
    assert fake.posts("/v1/payouts") == []


def test_a_reversal_after_reservation_is_never_posted_as_paid(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    run(db)
    [po] = fake.payouts.values()
    rows[1].status = CommissionStatus.CANCELLED                     # reversed while SoncoPay pays
    db.commit()
    fake.complete(po["id"])
    run(db)
    out = cashouts(db, user)[0]
    assert out.status != "completed"                                # left for an administrator
    db.refresh(rows[0])
    assert rows[0].status != CommissionStatus.PAID
    assert any(d["type"] == "RESERVATION_MISMATCH" for d in engine.discrepancies(db))


def test_two_workers_never_consume_the_same_commission_twice(payouts_on, fake):
    from app.services import cashout_service as cs

    db = payouts_on
    real_figures(db, fake)
    user, _rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    run(db)
    run(db)
    assert len(fake.payouts) == 1 and len(fake.posts("/v1/payouts")) == 1
    # A second combined payout of the same member is refused by the database while one is open.
    extra = commission(db, user, "2.00")
    db.refresh(user)
    second = cs.reserve(db, user, [extra], method=cs.METHOD_CRYPTO, fee=Decimal("0"), intent_ref="intent:m-test",
                        now=NOW, wallet=WALLET, currency="usdtbsc")
    assert second is None
    db.refresh(extra)
    assert extra.payout_reference is None


def test_a_worker_that_lost_the_race_reserves_nothing(payouts_on, fake, monkeypatch):
    from app.services import cashout_service as cs

    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    calls = {"n": 0}
    real_available = cs.available_rows

    def available(session, uid):
        calls["n"] += 1
        if calls["n"] == 2:            # the re-check before reserving: another worker took one row
            session.query(AffiliateCommission).filter(AffiliateCommission.id == rows[0].id) \
                .update({"payout_reference": "intent:other"})
        return real_available(session, uid)

    monkeypatch.setattr(cs, "available_rows", available)
    assert run(db)["members"] == {"BALANCE_CHANGED": 1}
    assert fake.posts("/v1/payouts") == [] and cashouts(db, user) == []


def test_the_member_sees_the_threshold_and_what_is_accumulating(payouts_on, fake):
    from app.services import cashout_service as cs

    db = payouts_on
    real_figures(db, fake)
    user, _rows = payable_member(db, fake, amounts=["1.00", "0.80", "5.00"])
    run(db)                                                         # 5.00 is paid on its own; 1.80 waits
    summary = cs.summary(db, user, now=NOW)
    view = summary["crypto_payout_threshold"]
    assert (view["threshold"], view["network_fee"], view["provider_minimum"]) == ("2.23", "0.23", "2")
    assert view["accumulated"] == "1.80" and view["awaiting_threshold"] is True
    assert view["destination"]["destination_state"] == "READY"
    assert summary["minimums"]["CRYPTO"] == 2.23


def test_the_admin_sees_accumulating_members_and_each_combined_payouts_commissions(payouts_on, fake, client):
    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["1.20", "1.20"])
    waiting, _small = payable_member(db, fake, "m2", wallet=OTHER_WALLET, amounts=["1.00"])
    run(db)
    boss = superadmin(db, "viewer")
    answer = client.get("/api/v1/admin/finance/soncopay/payouts?provider=true", headers=bearer(boss))
    assert answer.status_code == 200, answer.text
    view = answer.json()["accumulation"]
    assert (view["threshold"], view["fee"], view["minimum"]) == ("2.23", "0.23", "2")
    [line] = [m for m in view["members"] if m["user_id"] == waiting.id]
    assert (line["accumulating"], line["reaches_threshold"]) == ("1.00", False)
    [payout] = view["payouts"]
    assert payout["user_id"] == user.id and payout["commission_ids"] == [r.id for r in rows]
    assert payout["gross_amount"] == "2.40" and LIVE_KEY not in answer.text


# ===========================================================================
# Owner decision 2026-10-30: minimum crypto cashout $10 (as on Kinjy)
# ===========================================================================

@pytest.mark.ten_dollar_minimum
def test_the_default_minimum_crypto_cashout_is_ten_dollars(ledger):
    from app.services import cashout_service as cs

    assert payment_config.default_config().crypto_min_usd == Decimal("10.00")
    assert cs.crypto_minimum(ledger) == Decimal("10.00")


@pytest.mark.ten_dollar_minimum
@pytest.mark.parametrize("amounts, outcome, sent", [
    (["1.00"], "ACCUMULATING_BELOW_THRESHOLD", None),
    (["5.00"], "ACCUMULATING_BELOW_THRESHOLD", None),          # above SoncoPay's 2.23, below $10
    (["9.99"], "ACCUMULATING_BELOW_THRESHOLD", None),
    (["10.00"], "SUBMITTED", ["9.77"]),                         # on its own: 10.00 less the 0.23 fee
    (["15.00"], "SUBMITTED", ["14.77"]),
    (["4.00", "3.00", "3.00"], "SUBMITTED", ["9.77"]),          # together exactly $10
    (["4.00", "3.00", "2.99"], "ACCUMULATING_BELOW_THRESHOLD", None),
])
def test_commissions_accumulate_until_the_ten_dollar_minimum(payouts_on, fake, amounts, outcome, sent):
    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=amounts)
    assert run(db)["members"] == {outcome: 1}
    assert sorted(Decimal(p["amount"]) for p in fake.payouts.values()) == sorted(Decimal(s) for s in sent or [])
    if sent:
        out = cashouts(db, user)[0]
        assert out.commission_id == (rows[0].id if len(rows) == 1 else None)
        assert out.gross_amount == sum(Decimal(a) for a in amounts)


@pytest.mark.ten_dollar_minimum
def test_a_ten_dollar_commission_goes_alone_and_smaller_ones_wait_for_ten_together(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["6.00", "12.00", "3.00"])
    run(db)
    assert [p["reference"] for p in fake.payouts.values()] == [f"c{rows[1].id}-a1"]   # 6 + 3 = 9 waits
    commission(db, user, "1.00")
    run(db)
    combined = [c for c in cashouts(db, user) if c.commission_id is None]
    assert len(combined) == 1 and combined[0].gross_amount == Decimal("10.00")


@pytest.mark.ten_dollar_minimum
def test_soncopays_minimum_applies_when_it_is_higher_than_ten_dollars(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    fake.asset_minimum = "12"                                   # threshold 12 + 0.23 = 12.23
    _user, _rows = payable_member(db, fake, amounts=["10.00"])
    assert run(db)["members"] == {"ACCUMULATING_BELOW_THRESHOLD": 1}
    fake.payouts.clear()
    db2 = payouts_on
    user2, _rows2 = payable_member(db2, fake, "m2", wallet=OTHER_WALLET, amounts=["10.00", "2.50"])
    report = run(db2)
    assert report["members"].get("SUBMITTED") == 1
    assert [Decimal(p["amount"]) for p in fake.payouts.values()] == [Decimal("12.27")]


@pytest.mark.ten_dollar_minimum
@pytest.mark.parametrize("fee, received", [("0.23", "9.77"), ("0.50", "9.50"), ("1.00", "9.00")])
def test_the_network_fee_is_read_from_soncopay_and_taken_from_the_ten_dollars(payouts_on, fake, fee, received):
    db = payouts_on
    real_figures(db, fake)
    fake.fee = fee
    _user, _rows = payable_member(db, fake, amounts=["10.00"])
    assert run(db)["members"] == {"SUBMITTED": 1}
    [po] = fake.payouts.values()
    assert Decimal(po["amount"]) == Decimal(received)


@pytest.mark.ten_dollar_minimum
def test_the_production_fee_limits_hold_a_ten_dollar_payout(payouts_on, fake):
    """Production on 2026-10-30: member limit 5 % / $0.10 and a 25 % margin; SoncoPay charges 0.23."""
    db = payouts_on
    real_figures(db, fake, margin="25")
    configure(db, member_fee_cap_percent=Decimal("5.000"), member_fee_cap_usd=Decimal("0.10"))
    user, rows = payable_member(db, fake, amounts=["10.00"])
    assert run(db)["members"] == {"NETWORK_FEE_ABOVE_MEMBER_LIMIT": 1}
    assert fake.posts("/v1/payouts") == [] and cashouts(db, user) == []
    db.refresh(rows[0])
    assert rows[0].payout_reference is None


@pytest.mark.ten_dollar_minimum
def test_a_waiting_wallet_keeps_ten_dollars_unpaid(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    cooling = member(db, "m1", method="CRYPTO")
    run(db)
    fake.confirm(destination(db, cooling).destination_id, usable=False)
    commission(db, cooling, "10.00")
    assert run(db)["members"] == {"DESTINATION_WAITING_PERIOD": 1} and fake.posts("/v1/payouts") == []


@pytest.mark.ten_dollar_minimum
def test_cancelled_and_held_commissions_do_not_count_towards_ten_dollars(payouts_on, fake):
    from app.models.affiliate import CommissionStatus

    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["6.00", "5.00"])
    rows[0].status = CommissionStatus.CANCELLED                  # reversed
    rows[1].business_model_version = None                       # historical: held for review
    commission(db, user, "4.00")
    db.commit()
    assert run(db)["members"] == {"ACCUMULATING_BELOW_THRESHOLD": 1}    # only 4.00 counts
    assert fake.posts("/v1/payouts") == []


@pytest.mark.ten_dollar_minimum
def test_ten_dollars_is_paid_once_and_posted_once(payouts_on, fake):
    from app.models.accounting import JournalEntry

    db = payouts_on
    real_figures(db, fake)
    user, rows = payable_member(db, fake, amounts=["5.00", "5.00"])
    run(db)
    run(db)                                                     # a second worker finds nothing new
    assert len(fake.posts("/v1/payouts")) == 1
    [po] = fake.payouts.values()
    fake.complete(po["id"])
    run(db)
    run(db)
    out = cashouts(db, user)[0]
    assert out.status == "completed" and Decimal(out.net_received) == Decimal("9.77")
    assert db.query(JournalEntry).filter(JournalEntry.description == f"Affiliate Cashout #{out.id}").count() == 1
    _assert_all_journals_balance(db)


@pytest.mark.ten_dollar_minimum
def test_the_member_sees_the_ten_dollar_minimum_and_what_is_missing(payouts_on, fake):
    from app.services import cashout_service as cs

    db = payouts_on
    real_figures(db, fake)
    user, _rows = payable_member(db, fake, amounts=["4.00", "2.50"])
    run(db)
    summary = cs.summary(db, user, now=NOW)
    assert summary["minimum"] == 10.0 and summary["payable_amount"] == 6.5
    assert summary["remaining_to_minimum"] == 3.5 and summary["status"] == "BELOW_MINIMUM"
    view = summary["crypto_payout_threshold"]
    assert (view["threshold"], view["business_minimum"], view["accumulated"], view["network_fee"]) == \
        ("10.00", "10.00", "6.50", "0.23")
    commission(db, user, "3.50")
    assert cs.summary(db, user, now=NOW)["remaining_to_minimum"] == 0.0


@pytest.mark.ten_dollar_minimum
def test_the_owner_minimum_is_stored_through_the_audited_settings(ledger):
    from app.models.payment_config import PaymentConfigAudit

    db = ledger
    configure(db, crypto_min_usd=Decimal("1.00"))
    before = payment_config.load(db).version
    with pytest.raises(payment_config.PaymentConfigError):
        payment_config.apply_owner_crypto_minimum(db, "10.00", decision="short")
    config = payment_config.apply_owner_crypto_minimum(db, "10.00", decision="Shafi Abeid 2026-10-30: $10 as on Kinjy")
    assert config.crypto_min_usd == Decimal("10.00") and config.version == before + 1
    audit = db.query(PaymentConfigAudit).order_by(PaymentConfigAudit.id.desc()).first()
    assert audit.old_values == {"crypto_min_usd": "1.00"} and audit.new_values["crypto_min_usd"] == "10.00"
    assert "Kinjy" in audit.new_values["owner_decision"] and audit.actor_id is None
    again = payment_config.apply_owner_crypto_minimum(db, "10.00", decision="Shafi Abeid 2026-10-30: $10 as on Kinjy")
    assert again.version == config.version                      # idempotent: nothing written twice
    configure(db, max_single_payout_usd=Decimal("5.00"), crypto_min_usd=Decimal("1.00"))
    with pytest.raises(payment_config.PaymentConfigError):
        payment_config.apply_owner_crypto_minimum(db, "10.00", decision="Shafi Abeid 2026-10-30: $10 as on Kinjy")
    with pytest.raises(payment_config.PaymentConfigError):
        payment_config._coerce(payment_config.FIELDS["crypto_min_usd"], "10.001")      # cents only
