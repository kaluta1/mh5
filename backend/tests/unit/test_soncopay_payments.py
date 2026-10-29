"""SoncoPay customer payments: checkout routing, webhook verification,
reconciliation and the financial confirmation they lead to.

  1. routing: NOWPayments stays the gateway unless SoncoPay is the default AND
     ready; a deposit keeps its gateway forever; NOWPayments code never
     touches a SoncoPay deposit and SoncoPay code never touches a NOWPayments one;
  2. checkout: server-side creation, idempotent order id, amount/currency/mode
     checked, hosted checkout URL, safe retry after a failure;
  3. webhook: timestamped signature over the raw body, 5 minute window,
     legacy and unsigned refused, each delivery processed once, the payment
     re-read from SoncoPay, nothing credited from the body;
  4. statuses: paid (also late), underpaid, partially paid, expired, failed,
     refunds; one confirmation, one commission, whatever arrives twice;
  5. Test/Live isolation, credentials never exposed, unauthorized calls refused.

SoncoPay is a fake (httpx.MockTransport): no test reaches the network. Every
account, key and secret is SYNTHETIC.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.models.accounting import JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.checkout_gateway import SoncoPayWebhookEvent
from app.models.payment import Deposit, DepositStatus
from app.services import payment_config
from app.services import soncopay_client
from app.services import soncopay_payments as scp
from app.services import soncopay_settings as sp
from app.services.financial_integrity import FinancialIntegrityError
from app.services.nowpayments_service import finalize_deposit_from_nowpayments
from app.services.payment_scheduler import PaymentScheduler
from tests.unit.test_admin_security_hardening import PASSWORD as ADMIN_PASSWORD
from tests.unit.test_admin_security_hardening import bearer, code_of
from tests.unit.test_dual_cashout import ledger, member, no_network  # noqa: F401
from tests.unit.test_new_business_model import world  # noqa: F401
from tests.unit.test_super_admin import superadmin

pytestmark = pytest.mark.unit

TEST_KEY, TEST_SECRET = "sp_test_synthetic_key_0000001", "whsec_test_synthetic_secret_01"
LIVE_KEY, LIVE_SECRET = "sp_live_synthetic_key_0000002", "whsec_live_synthetic_secret_02"
CREATE, WEBHOOK = "/api/v1/payments/create", "/api/v1/webhooks/soncopay"
PRODUCT, PRICE = "annual_membership", Decimal("50")


# ---------------------------------------------------------------------------
# A fake SoncoPay, following the documented API
# ---------------------------------------------------------------------------

class FakeSonco:
    def __init__(self):
        self.payments: dict = {}
        self.calls: list = []
        self.fail_create = None        # HTTP status to answer POST /v1/payments with
        self.fail_read = None          # HTTP status to answer GET /v1/payments/{id} with
        self.drop_create = 0           # number of creations that get no answer at all
        self.payer_required = False    # answer 422 payer_required when a method is preselected

    def public(self, p):
        return {k: v for k, v in p.items() if not k.startswith("_")}

    def handler(self, request: httpx.Request) -> httpx.Response:
        key = request.headers.get("X-Api-Key", "")
        env = "test" if key.startswith("sp_test_") else "live" if key.startswith("sp_live_") else None
        self.calls.append((request.method, request.url.path, env))
        if env is None or key not in (TEST_KEY, LIVE_KEY):
            return httpx.Response(401, json={"detail": "invalid api key"})
        path = request.url.path
        if request.method == "POST" and path == "/v1/payments":
            if self.drop_create:
                self.drop_create -= 1
                raise httpx.ConnectError("synthetic: no answer")
            if self.fail_create:
                return httpx.Response(self.fail_create, json={"detail": "synthetic", "code": "provider_down"})
            body = json.loads(request.content)
            if self.payer_required and body.get("method"):
                return httpx.Response(422, json={"detail": "payer details missing", "code": "payer_required",
                                                 "fields": ["phone"]})
            for p in self.payments.values():
                if p["order_id"] == body["order_id"] and p["_env"] == env:     # same order_id -> same payment
                    if p["amount"] != body["amount"]:
                        return httpx.Response(409, json={"detail": "order_id reused", "code": "order_conflict"})
                    return httpx.Response(200, json=self.public(p))
            pid = f"pay_{len(self.payments) + 1:020d}"
            p = {"id": pid, "object": "payment", "livemode": env == "live", "status": "new",
                 "amount": body["amount"], "currency": body["currency"], "order_id": body["order_id"],
                 "checkout_url": f"https://soncopay.com/pay/{pid}", "expires_at": "2026-10-21T15:30:00+00:00",
                 "asset": body.get("asset"), "network": body.get("network"), "_env": env, "_body": body}
            self.payments[pid] = p
            return httpx.Response(201, json=self.public(p))
        if request.method == "GET" and path.startswith("/v1/payments/"):
            if self.fail_read:
                return httpx.Response(self.fail_read, json={"detail": "synthetic"})
            p = self.payments.get(path.split("/")[3])
            if p is None or p["_env"] != env:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=self.public(p))
        if request.method == "GET" and path == "/v1/methods":
            return httpx.Response(200, json={"methods": [{"method": "crypto"}], "payment_methods": [{"code": "crypto"}]})
        return httpx.Response(404, json={"detail": "not found"})

    def set(self, pid, **fields):
        self.payments[pid].update(fields)

    def reads(self):
        return [c for c in self.calls if c[0] == "GET" and c[1].startswith("/v1/payments/")]


@pytest.fixture
def fake(monkeypatch):
    f = FakeSonco()
    monkeypatch.setattr(soncopay_client, "_transport", lambda: httpx.MockTransport(f.handler))
    monkeypatch.setattr(soncopay_client, "_backoff", lambda *_a: 0)
    return f


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://api.example.test")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example.test")
    # NOWPayments can take new payments (synthetic pay-in credentials; it is never reached).
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-payin-api-key")
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "synthetic-ipn-secret-0001")


@pytest.fixture
def nowpayments_calls(monkeypatch):
    """NOWPayments is never reached: its functions are replaced and every call recorded."""
    calls = []
    from app.api.api_v1.endpoints import payments as payments_endpoint
    from app.services import nowpayments_service

    async def create(**kw):
        calls.append(("create", kw["order_id"]))
        return {"payment_id": f"np_{kw['order_id']}", "pay_address": "0xsynthetic", "pay_amount": 50,
                "pay_currency": "usdtbsc", "payment_status": "waiting"}

    async def status(payment_id):
        calls.append(("status", payment_id))
        return {"payment_status": "waiting", "payment_id": payment_id}

    monkeypatch.setattr(payments_endpoint, "now_create_payment", create)
    monkeypatch.setattr(nowpayments_service, "get_payment_status", status)
    return calls


def configure(db, *, default=True, enabled=True, live=False):
    boss = superadmin(db, f"boss{db.query(Deposit).count()}{int(time.time() * 1000) % 100000}")
    sp.update(db, boss, password=ADMIN_PASSWORD, credentials={"TEST_API_KEY": TEST_KEY,
                                                              "TEST_WEBHOOK_SECRET": TEST_SECRET})
    if live:
        sp.update(db, boss, password=ADMIN_PASSWORD, credentials={"LIVE_API_KEY": LIVE_KEY,
                                                                  "LIVE_WEBHOOK_SECRET": LIVE_SECRET})
    if enabled:
        sp.update(db, boss, password=ADMIN_PASSWORD, enabled=True)
    if default:
        sp.update(db, boss, password=ADMIN_PASSWORD, default_provider="soncopay")
    return boss


def buy(client, user, key="k-1"):
    return client.post(CREATE, headers={**bearer(user), "Idempotency-Key": key},
                       json={"amount": float(PRICE), "currency": "usd", "product_code": PRODUCT})


def signed(event, data, *, secret=TEST_SECRET, ts=None, delivery="dlv_0001", header="X-SoncoPay-Signature"):
    raw = json.dumps({"event": event, "created_at": "2026-10-21T10:00:00+00:00", "data": data}).encode()
    ts = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw, {header: f"t={ts},v1={mac}", "X-SoncoPay-Delivery-Id": delivery, "X-SoncoPay-Event": event,
                 "Content-Type": "application/json"}


def post_webhook(client, event, data, **kw):
    raw, headers = signed(event, data, **kw)
    return client.post(WEBHOOK, content=raw, headers=headers)


def deposit_of(db, response) -> Deposit:
    db.expire_all()
    return db.query(Deposit).filter(Deposit.id == response.json()["deposit_id"]).one()


def benefits(db, dep) -> tuple:
    db.expire_all()
    return (db.query(AffiliateCommission).filter(AffiliateCommission.source_deposit_id == dep.id).count()
            if hasattr(AffiliateCommission, "source_deposit_id") else db.query(AffiliateCommission).count(),
            db.query(JournalEntry).count())


@pytest.fixture
def buyer(ledger):
    sponsor = member(ledger, "sponsor", method="CRYPTO")
    return member(ledger, "buyer", sponsor=sponsor, wallet=None)


def soncopay_purchase(client, db, fake, buyer, key="k-1"):
    created = buy(client, buyer, key)
    assert created.status_code == 200, created.text
    return created, deposit_of(db, created)


# ===========================================================================
# 1. Routing
# ===========================================================================

def test_nowpayments_stays_the_gateway_until_soncopay_is_the_ready_default(client, ledger, fake, buyer,
                                                                           nowpayments_calls):
    db = ledger
    assert client.get("/api/v1/payments/checkout-gateway").status_code == 401
    assert client.get("/api/v1/payments/checkout-gateway", headers=bearer(buyer)).json() == {"provider": "nowpayments", "available": True}
    configure(db, default=False)                                   # on, ready, but not the default
    created = buy(client, buyer, "k-np")
    assert created.status_code == 200, created.text
    assert created.json()["provider"] == "nowpayments" and created.json()["checkout_url"] is None
    dep = deposit_of(db, created)
    assert (dep.payment_provider, dep.provider_environment) == ("nowpayments", None)
    assert [c[0] for c in nowpayments_calls] == ["create"] and fake.calls == []


def test_a_new_payment_goes_to_soncopay_when_it_is_the_ready_default(client, ledger, fake, buyer, nowpayments_calls):
    db = ledger
    configure(db)
    assert client.get("/api/v1/payments/checkout-gateway", headers=bearer(buyer)).json() == {"provider": "soncopay", "available": True}
    created, dep = soncopay_purchase(client, db, fake, buyer)
    body = created.json()
    assert body["provider"] == "soncopay" and body["checkout_url"] == f"https://soncopay.com/pay/{dep.external_payment_id}"
    assert (dep.payment_provider, dep.provider_environment, dep.status) == ("soncopay", "test", DepositStatus.PENDING)
    sent = fake.payments[dep.external_payment_id]["_body"]
    assert sent["order_id"] == dep.order_id and sent["amount"] == "50.00" and sent["currency"] == "USD"
    assert sent["callback_url"] == "https://api.example.test/api/v1/webhooks/soncopay"
    assert sent["return_url"] == f"https://app.example.test/dashboard/wallet?payment=soncopay&deposit={dep.id}"
    assert sent["description"].isascii() and sent["metadata"] == {"deposit_id": dep.id}
    assert nowpayments_calls == []
    for secret in (TEST_KEY, TEST_SECRET, LIVE_KEY, LIVE_SECRET):
        assert secret not in created.text


def test_the_same_idempotency_key_returns_the_same_payment(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    first, dep = soncopay_purchase(client, db, fake, buyer, "k-same")
    again = buy(client, buyer, "k-same")
    assert again.status_code == 200 and again.json()["deposit_id"] == dep.id
    assert again.json()["checkout_url"] == first.json()["checkout_url"]
    assert len(fake.payments) == 1 and db.query(Deposit).count() == 1


def test_a_deposit_keeps_its_gateway_when_the_default_changes(client, ledger, fake, buyer, nowpayments_calls):
    db = ledger
    boss = configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    sp.update(db, boss, password=ADMIN_PASSWORD, default_provider="nowpayments")
    sp.update(db, boss, password=ADMIN_PASSWORD, enabled=False)                       # SoncoPay off for new payments
    fake.set(dep.external_payment_id, status="paid")
    synced = client.post(f"/api/v1/payments/sync/{dep.id}", headers=bearer(buyer))
    assert synced.status_code == 200, synced.text
    assert synced.json()["provider"] == "soncopay" and synced.json()["is_confirmed"] is True
    assert nowpayments_calls == []                                  # never asked NOWPayments about it


def test_nowpayments_code_refuses_a_soncopay_deposit(client, ledger, fake, buyer, monkeypatch):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    with pytest.raises(FinancialIntegrityError):
        finalize_deposit_from_nowpayments(db, dep, {"payment_status": "finished", "order_id": dep.order_id})
    db.rollback()
    # A correctly signed NOWPayments IPN naming the SoncoPay order finds nothing to credit.
    monkeypatch.setattr(payment_config, "ipn_secret", lambda _db: "ipn_synthetic_secret_value")
    body = {"payment_id": dep.external_payment_id, "order_id": dep.order_id, "payment_status": "finished",
            "price_amount": 50, "price_currency": "usd"}
    sig = hmac.new(b"ipn_synthetic_secret_value", json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
                   hashlib.sha512).hexdigest()
    answer = client.post("/api/v1/webhooks/nowpayments", content=json.dumps(body),
                         headers={"x-nowpayments-sig": sig, "Content-Type": "application/json"})
    assert answer.status_code == 200
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING


def test_a_soncopay_webhook_never_matches_a_nowpayments_deposit(client, ledger, fake, buyer, nowpayments_calls):
    db = ledger
    configure(db, default=False)
    created = buy(client, buyer, "k-np")
    dep = deposit_of(db, created)
    answer = post_webhook(client, "payment.paid", {"id": "pay_00000000000000000001", "order_id": dep.order_id,
                                                   "status": "paid", "livemode": False, "asset": "USDT", "network": "BSC"})
    assert answer.status_code == 200
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING
    assert db.query(SoncoPayWebhookEvent).one().outcome == "UNKNOWN_PAYMENT"
    assert fake.reads() == []


def test_the_scheduler_asks_each_deposit_s_own_gateway(client, ledger, fake, buyer, nowpayments_calls):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    fake.set(dep.external_payment_id, status="paid")
    outcome = asyncio.run(PaymentScheduler()._check_single_payment(db, dep.id))
    assert outcome == "SYNCED" and nowpayments_calls == []
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.VALIDATED


def test_the_scheduler_leaves_a_soncopay_deposit_alone_when_soncopay_cannot_answer(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    fake.fail_read = 502
    assert asyncio.run(PaymentScheduler()._check_single_payment(db, dep.id)) == "PROVIDER_UNAVAILABLE"
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING


# ===========================================================================
# 2. Checkout failures
# ===========================================================================

def test_a_refused_creation_fails_the_deposit_and_a_retry_with_the_same_key_succeeds(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    fake.fail_create = 422
    refused = buy(client, buyer, "k-retry")
    assert refused.status_code == 502 and "provider_down" not in refused.text
    dep = db.query(Deposit).one()
    assert dep.status == DepositStatus.FAILED and dep.external_payment_id is None
    fake.fail_create = None
    again = buy(client, buyer, "k-retry")
    assert again.status_code == 200, again.text
    db.expire_all()
    dep = db.query(Deposit).one()
    assert dep.status == DepositStatus.PENDING and dep.external_payment_id and len(fake.payments) == 1


def test_a_creation_without_an_answer_is_retried_with_the_same_order_id(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    fake.drop_create = 1
    created = buy(client, buyer)
    assert created.status_code == 200, created.text
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert len(posts) == 2 and len(fake.payments) == 1


def test_a_created_payment_that_is_not_the_order_is_refused(client, ledger, fake, buyer, monkeypatch):
    db = ledger
    configure(db)
    original = fake.handler

    def wrong_amount(request):
        answer = original(request)
        if request.method == "POST" and request.url.path == "/v1/payments":
            data = answer.json()
            data["amount"] = "5.00"
            return httpx.Response(201, json=data)
        return answer

    monkeypatch.setattr(soncopay_client, "_transport", lambda: httpx.MockTransport(wrong_amount))
    assert buy(client, buyer).status_code == 502
    dep = db.query(Deposit).one()
    assert dep.status == DepositStatus.FAILED and dep.external_payment_id is None


# ===========================================================================
# 3. Webhook verification
# ===========================================================================

def test_signature_rules():
    raw, now = b'{"event":"payment.paid","data":{}}', 1_800_000_000
    good = "t=%d,v1=%s" % (now, hmac.new(b"s3cret", f"{now}.".encode() + raw, hashlib.sha256).hexdigest())
    assert scp.verify_signature(raw, good, "s3cret", now=now)
    assert scp.verify_signature(raw, good, "s3cret", now=now + 300)
    assert not scp.verify_signature(raw, good, "s3cret", now=now + 301)               # replayed later
    assert not scp.verify_signature(raw, good, "s3cret", now=now - 301)               # from the future
    assert not scp.verify_signature(raw, good, "other", now=now)                      # wrong secret
    assert not scp.verify_signature(raw + b" ", good, "s3cret", now=now)              # body changed
    assert not scp.verify_signature(raw, good.replace(f"t={now}", f"t={now + 1}"), "s3cret", now=now)
    assert scp.verify_signature(raw, good + ",v1=" + "0" * 64, "s3cret", now=now)     # one of several v1
    legacy = hmac.new(b"s3cret", raw, hashlib.sha512).hexdigest()
    assert not scp.verify_signature(raw, legacy, "s3cret", now=now)                   # legacy: never
    for bad in ("", "t=,v1=", "t=abc,v1=00", f"t={now}", "v1=" + "0" * 64):
        assert not scp.verify_signature(raw, bad, "s3cret", now=now)


def test_an_unsigned_stale_or_wrongly_signed_webhook_changes_nothing(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    fake.set(dep.external_payment_id, status="paid")
    data = {"id": dep.external_payment_id, "order_id": dep.order_id, "status": "paid", "livemode": False, "asset": "USDT", "network": "BSC"}
    assert post_webhook(client, "payment.paid", data, secret="whsec_wrong_synthetic_00000").status_code == 400
    assert post_webhook(client, "payment.paid", data, ts=int(time.time()) - 600).status_code == 400
    raw, headers = signed("payment.paid", data)
    assert client.post(WEBHOOK, content=raw + b" ", headers=headers).status_code == 400
    headers["X-SoncoPay-Signature"] = hmac.new(TEST_SECRET.encode(), raw, hashlib.sha512).hexdigest()   # legacy
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 400
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING
    assert db.query(SoncoPayWebhookEvent).count() == 0 and fake.reads() == []


def test_a_paid_webhook_confirms_once_from_the_payment_read_back(client, ledger, fake, buyer, monkeypatch):
    db = ledger
    configure(db)
    from app.services import commission_distribution

    confirmations = []
    real_validation = commission_distribution.process_payment_validation

    def counted(db_, deposit, **kw):
        confirmations.append(deposit.id)
        return real_validation(db_, deposit, **kw)

    monkeypatch.setattr(commission_distribution, "process_payment_validation", counted)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    before = benefits(db, dep)
    # The body claims "paid" but SoncoPay still says "waiting": nothing is credited.
    fake.set(dep.external_payment_id, status="waiting")
    data = {"id": dep.external_payment_id, "order_id": dep.order_id, "status": "paid", "livemode": False, "asset": "USDT", "network": "BSC"}
    assert post_webhook(client, "payment.paid", data, delivery="dlv_a").status_code == 200
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING and benefits(db, dep) == before
    # Now really paid: confirmed once.
    fake.set(dep.external_payment_id, status="paid")
    assert post_webhook(client, "payment.paid", data, delivery="dlv_b").status_code == 200
    db.expire_all()
    paid = db.get(Deposit, dep.id)
    assert paid.status == DepositStatus.VALIDATED and paid.validated_at is not None
    validated_at = paid.validated_at
    after = benefits(db, dep)
    assert after != before and confirmations == [dep.id]
    # The same delivery again, another delivery of the same event, a sync and the scheduler: nothing more.
    reads = len(fake.reads())
    again = post_webhook(client, "payment.paid", data, delivery="dlv_b")
    assert again.status_code == 200 and again.json().get("duplicate") is True
    assert len(fake.reads()) == reads                                # a processed delivery is not even re-read
    assert post_webhook(client, "payment.paid", data, delivery="dlv_c").status_code == 200
    assert client.post(f"/api/v1/payments/sync/{paid.id}", headers=bearer(buyer)).status_code == 200
    assert asyncio.run(PaymentScheduler()._check_single_payment(db, paid.id)) == "SKIPPED"
    assert benefits(db, dep) == after
    db.expire_all()
    assert confirmations == [dep.id] and db.get(Deposit, dep.id).validated_at == validated_at   # confirmed ONCE
    assert db.query(SoncoPayWebhookEvent).filter(SoncoPayWebhookEvent.deposit_id == dep.id).count() == 3


def test_the_v2_header_used_while_an_account_is_on_the_legacy_format_is_accepted(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    fake.set(dep.external_payment_id, status="paid")
    raw, headers = signed("payment.paid", {"id": dep.external_payment_id, "order_id": dep.order_id},
                          header="X-SoncoPay-Signature-V2")
    headers["X-SoncoPay-Signature"] = hmac.new(TEST_SECRET.encode(), raw, hashlib.sha512).hexdigest()
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 200
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.VALIDATED


@pytest.mark.parametrize("change", [{"amount": "49.00"}, {"currency": "EUR"}, {"livemode": True},
                                    {"order_id": "someone-else"}])
def test_a_payment_that_does_not_match_its_deposit_is_never_credited(client, ledger, fake, buyer, change):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    before = benefits(db, dep)
    fake.set(dep.external_payment_id, status="paid", **change)
    answer = post_webhook(client, "payment.paid", {"id": dep.external_payment_id, "order_id": dep.order_id})
    assert answer.status_code == 409
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING and benefits(db, dep) == before
    assert db.query(SoncoPayWebhookEvent).count() == 0               # not recorded: SoncoPay keeps retrying


def test_a_webhook_is_retried_later_when_soncopay_cannot_be_read(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    fake.set(dep.external_payment_id, status="paid")
    fake.fail_read = 503
    data = {"id": dep.external_payment_id, "order_id": dep.order_id}
    assert post_webhook(client, "payment.paid", data, delivery="dlv_r").status_code == 503
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING and db.query(SoncoPayWebhookEvent).count() == 0
    fake.fail_read = None
    assert post_webhook(client, "payment.paid", data, delivery="dlv_r").status_code == 200    # the retry
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.VALIDATED


def test_other_events_unknown_payments_and_a_missing_delivery_id(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    assert post_webhook(client, "ping", {}, delivery="dlv_ping").status_code == 200
    assert post_webhook(client, "payout.sent", {"id": "po_1"}, delivery="dlv_po").status_code == 200
    assert post_webhook(client, "payment.paid", {"id": "pay_99999999999999999999", "order_id": "nobody"},
                        delivery="dlv_unknown").status_code == 200
    outcomes = sorted(r.outcome for r in db.query(SoncoPayWebhookEvent).all())
    assert outcomes == ["ACKNOWLEDGED", "PAYOUT_SYNC_REQUESTED", "UNKNOWN_PAYMENT"] and fake.reads() == []
    raw, headers = signed("payment.paid", {"id": "pay_1"})
    del headers["X-SoncoPay-Delivery-Id"]
    assert client.post(WEBHOOK, content=raw, headers=headers).status_code == 400


# ===========================================================================
# 4. Statuses
# ===========================================================================

def status_after(client, db, fake, buyer, dep, **payment):
    fake.set(dep.external_payment_id, **payment)
    answer = client.get(f"/api/v1/payments/check-status/{dep.id}", headers=bearer(buyer))
    assert answer.status_code == 200, answer.text
    db.expire_all()
    return db.get(Deposit, dep.id), answer.json()


def test_member_states_and_deposit_statuses(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    before = benefits(db, dep)
    for provider_status, deposit_status, state in (
            ("new", DepositStatus.PENDING, "pending"), ("waiting", DepositStatus.PENDING, "pending"),
            ("confirming", DepositStatus.PENDING, "awaiting_confirmation"),
            ("underpaid", DepositStatus.PENDING, "partial"),
            ("partially_paid", DepositStatus.PARTIALLY_PAID, "partial")):
        row, shown = status_after(client, db, fake, buyer, dep, status=provider_status)
        assert (row.status, shown["payment_state"], shown["is_confirmed"]) == (deposit_status, state, False)
        assert benefits(db, dep) == before                         # no benefit before "paid"
    row, shown = status_after(client, db, fake, buyer, dep, status="paid")
    assert (row.status, shown["payment_state"], shown["is_confirmed"]) == (DepositStatus.VALIDATED, "paid", True)
    assert TEST_KEY not in json.dumps(shown)


def test_expired_then_paid_late_is_confirmed(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    row, shown = status_after(client, db, fake, buyer, dep, status="expired")
    assert (row.status, shown["payment_state"]) == (DepositStatus.EXPIRED, "expired")
    # Expired deposits are still re-checked by the scheduler (a deposit can arrive up to 24 h late).
    fake.set(dep.external_payment_id, status="paid", late=True)
    assert asyncio.run(PaymentScheduler()._check_single_payment(db, dep.id)) == "SYNCED"
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.VALIDATED


def test_failed_payment(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    before = benefits(db, dep)
    row, shown = status_after(client, db, fake, buyer, dep, status="failed")
    assert (row.status, shown["payment_state"]) == (DepositStatus.FAILED, "failed") and benefits(db, dep) == before


def test_full_refund_reverses_once_and_partial_refund_is_refused(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    status_after(client, db, fake, buyer, dep, status="paid")
    data = {"id": dep.external_payment_id, "order_id": dep.order_id}
    # A partial refund, with or without its amount, is never handled as a full one.
    fake.set(dep.external_payment_id, status="partially_refunded", refunded_amount="10")
    assert post_webhook(client, "payment.refunded", data, delivery="dlv_pr").status_code == 409
    fake.payments[dep.external_payment_id].pop("refunded_amount")
    assert post_webhook(client, "payment.refunded", data, delivery="dlv_pr2").status_code == 409
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.VALIDATED          # left for manual reconciliation
    fake.set(dep.external_payment_id, status="refunded", refunded_amount="50")
    assert post_webhook(client, "payment.refunded", data, delivery="dlv_fr").status_code == 200
    db.expire_all()
    refunded = db.get(Deposit, dep.id)
    assert refunded.status == DepositStatus.FAILED
    # A late "paid" never validates a refunded deposit again.
    fake.set(dep.external_payment_id, status="paid")
    assert post_webhook(client, "payment.paid", data, delivery="dlv_late").status_code == 200
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.FAILED


# ===========================================================================
# 5. Test/Live isolation, authorization, credentials
# ===========================================================================

def test_test_and_live_never_mix(client, ledger, fake, buyer):
    db = ledger
    boss = configure(db, live=True)
    _created, test_dep = soncopay_purchase(client, db, fake, buyer, "k-test")
    assert fake.calls[-1] == ("POST", "/v1/payments", "test")
    sp.update(db, boss, password=ADMIN_PASSWORD, default_provider="nowpayments")
    sp.update(db, boss, password=ADMIN_PASSWORD, environment="live", confirmation=sp.CONFIRM_LIVE)
    sp.update(db, boss, password=ADMIN_PASSWORD, default_provider="soncopay")
    _created, live_dep = soncopay_purchase(client, db, fake, buyer, "k-live")
    assert (live_dep.provider_environment, fake.calls[-1]) == ("live", ("POST", "/v1/payments", "live"))
    # The Test deposit is still read with the Test key, after the switch to Live.
    fake.set(test_dep.external_payment_id, status="paid")
    client.get(f"/api/v1/payments/check-status/{test_dep.id}", headers=bearer(buyer))
    assert fake.reads()[-1][2] == "test"
    db.expire_all()
    assert db.get(Deposit, test_dep.id).status == DepositStatus.VALIDATED
    # A webhook about the Live payment signed with the Test secret is refused.
    fake.set(live_dep.external_payment_id, status="paid")
    data = {"id": live_dep.external_payment_id, "order_id": live_dep.order_id, "livemode": True}
    assert post_webhook(client, "payment.paid", data, delivery="dlv_x").status_code == 400     # livemode != test
    data.pop("livemode")
    assert post_webhook(client, "payment.paid", data, delivery="dlv_y").status_code == 409     # deposit is live
    assert post_webhook(client, "payment.paid", data, secret=LIVE_SECRET, delivery="dlv_z").status_code == 200
    db.expire_all()
    assert db.get(Deposit, live_dep.id).status == DepositStatus.VALIDATED


def test_the_client_refuses_a_key_of_the_other_environment_and_simulates_in_test_only():
    with pytest.raises(soncopay_client.SoncoPayError):
        soncopay_client.SoncoPayClient(LIVE_KEY, "test")
    with pytest.raises(soncopay_client.SoncoPayError):
        soncopay_client.SoncoPayClient(TEST_KEY, "live")
    live = soncopay_client.SoncoPayClient(LIVE_KEY, "live")
    assert LIVE_KEY not in repr(live)
    with pytest.raises(soncopay_client.SoncoPayError):
        asyncio.run(live.simulate("pay_00000000000000000001"))
    with pytest.raises(soncopay_client.SoncoPayError):
        asyncio.run(live.retrieve_payment("../v1/payouts"))                 # nothing else goes in a URL


def test_another_member_cannot_read_or_sync_the_payment(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    other = member(db, "other", wallet=None)
    for answer in (client.post(f"/api/v1/payments/sync/{dep.id}", headers=bearer(other)),
                   client.get(f"/api/v1/payments/check-status/{dep.id}", headers=bearer(other))):
        assert answer.status_code == 403
    assert client.post(f"/api/v1/payments/sync/{dep.id}").status_code == 401


def test_connection_test_is_super_admin_only_and_has_no_side_effect(client, ledger, fake):
    db = ledger
    boss = configure(db, default=False, enabled=False)
    url = "/api/v1/admin/finance/soncopay/connection-test"
    plain = member(db, "plainadmin", admin=True)
    assert client.post(url, json={"environment": "test"}).status_code == 401
    refused = client.post(url, headers=bearer(plain), json={"environment": "test"})
    assert refused.status_code == 403
    done = client.post(url, headers=bearer(boss), json={"environment": "test"})
    assert done.status_code == 200 and done.json() == {"ok": True, "environment": "test", "methods": 1}
    missing = client.post(url, headers=bearer(boss), json={"environment": "live"})
    assert missing.status_code == 200 and missing.json()["ok"] is False
    assert fake.calls == [("GET", "/v1/methods", "test")] and len(fake.payments) == 0
    for secret in (TEST_KEY, TEST_SECRET):
        assert secret not in done.text + missing.text
    assert code_of(client.post(url, headers=bearer(boss), json={"environment": "prod"})) is not None


# ===========================================================================
# USDT on BNB Smart Chain only (owner decision 2026-10-29)
# ===========================================================================

def test_every_payment_is_created_as_usdt_on_bsc(client, ledger, fake, buyer):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    sent = fake.payments[dep.external_payment_id]["_body"]
    assert (sent["method"], sent["asset"], sent["network"]) == ("crypto", "USDT", "BSC")


@pytest.mark.parametrize("paid", [{"asset": "USDT", "network": "TRON"}, {"asset": "USDC", "network": "BSC"},
                                  {"asset": None, "network": None}])
def test_a_payment_paid_in_another_asset_or_network_is_never_confirmed(client, ledger, fake, buyer, paid):
    db = ledger
    configure(db)
    _created, dep = soncopay_purchase(client, db, fake, buyer)
    before = benefits(db, dep)
    fake.set(dep.external_payment_id, status="paid", **paid)
    synced = client.post(f"/api/v1/payments/sync/{dep.id}", headers=bearer(buyer))
    assert synced.status_code == 200, synced.text
    assert synced.json()["is_confirmed"] is False
    db.expire_all()
    dep = db.get(Deposit, dep.id)
    assert (dep.status, dep.provider_status) == (DepositStatus.PENDING, "paid_other_asset")
    assert benefits(db, dep) == before                              # no commission, no journal


@pytest.mark.discontinued
def test_nowpayments_takes_no_new_payment_even_as_the_stored_default(client, ledger, fake, buyer,
                                                                     nowpayments_calls):
    db = ledger
    assert payment_config.nowpayments_checkout_problem(db) == payment_config.DISCONTINUED_MESSAGE
    answer = client.get("/api/v1/payments/checkout-gateway", headers=bearer(buyer)).json()
    assert answer["available"] is False                             # stored default nowpayments -> none
    created = buy(client, buyer, "k-np")
    assert created.status_code == 503
    assert nowpayments_calls == [] and db.query(Deposit).count() == 0
    configure(db)                                                   # SoncoPay ready and the default
    assert client.get("/api/v1/payments/checkout-gateway", headers=bearer(buyer)).json() == \
        {"provider": "soncopay", "available": True}


@pytest.mark.discontinued
def test_nowpayments_cannot_be_chosen_as_the_default_again(ledger):
    db = ledger
    boss = configure(db)
    with pytest.raises(Exception):
        sp.update(db, boss, password=ADMIN_PASSWORD, default_provider="nowpayments")
    db.rollback()
    assert sp.current_state(db)["default_provider"] == "soncopay"


@pytest.mark.discontinued
async def test_the_nowpayments_client_itself_refuses_a_new_payment():
    from app.services import nowpayments_service

    with pytest.raises(nowpayments_service.NowPaymentsError) as caught:
        await nowpayments_service.create_payment(price_amount=Decimal("50"), price_currency="usd",
                                                 order_id="o-1", order_description="x")
    assert caught.value.code == "PROVIDER_DISCONTINUED"


def test_when_payer_details_are_required_the_payment_is_created_without_a_preselected_method(client, ledger, fake,
                                                                                            buyer):
    db = ledger
    configure(db)
    fake.payer_required = True
    created, dep = soncopay_purchase(client, db, fake, buyer)
    assert created.json()["checkout_url"] == f"https://soncopay.com/pay/{dep.external_payment_id}"
    sent = fake.payments[dep.external_payment_id]["_body"]
    assert "method" not in sent and len(fake.payments) == 1
    fake.set(dep.external_payment_id, status="paid", asset="USDT", network="TRON")     # payer chose TRON
    client.post(f"/api/v1/payments/sync/{dep.id}", headers=bearer(buyer))
    db.expire_all()
    assert db.get(Deposit, dep.id).status == DepositStatus.PENDING                    # never credited
    fake.set(dep.external_payment_id, network="BSC")
    assert client.post(f"/api/v1/payments/sync/{dep.id}", headers=bearer(buyer)).json()["is_confirmed"] is True
