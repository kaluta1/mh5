"""NOWPayments integration (Phase 2): pay-in, IPN signature, status polling,
custody, payout authentication, the payout adapter and reconciliation.

NOTHING here reaches NOWPayments. The adapter is exercised through an
in-process HTTP transport that answers with the fixtures published in the
provider's API documentation; any request made without one fails the test.
The IPN vectors in nowpayments_ipn_vectors.json were produced with the Node.js
example from that documentation and a synthetic secret. All users, deposits,
commissions, addresses and credentials are SYNTHETIC.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.payment import Deposit, DepositStatus
from app.models.payment_config import PaymentConfigAudit, PaymentSettings
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services import nowpayments_service as nowpayments
from app.services import payment_config as pc
from app.services import payment_scheduler
from app.services.financial_balances import get_commission_balance
from app.services.financial_reversal import _REFUND_MARKER
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import (  # noqa: F401
    NOW,
    PASSWORD,
    PAYOUT_ENV,
    WALLET,
    FakeProvider,
    cashouts,
    commission,
    configure,
    engine_on,
    ledger,
    member,
    run,
)
from tests.unit.test_new_business_model import _deposit, _user, world  # noqa: F401

pytestmark = pytest.mark.unit

VECTORS = json.loads((Path(__file__).parent / "nowpayments_ipn_vectors.json").read_text(encoding="utf-8"))
IPN_SECRET = VECTORS["secret"]
IPN_URL = "/api/v1/webhooks/nowpayments"
CREDENTIALS = pc.ProviderCredentials("ENVIRONMENT", "ENVIRONMENT", {
    "PAYIN_API_KEY": "synthetic-payin-key", "IPN_SECRET": IPN_SECRET, "PAYOUT_API_KEY": "synthetic-payout-key",
    "PAYOUT_EMAIL": "payouts@example.com", "PAYOUT_PASSWORD": "synthetic-password",
    "PAYOUT_TOTP_SECRET": "JBSWY3DPEHPK3PXP"})
SECRET_VALUES = [v for k, v in CREDENTIALS.values.items() if k != "PAYOUT_EMAIL"]

# ---- fixtures copied from the provider's API documentation -----------------
DOC_BALANCE = {"eth": {"amount": 0.0001817185463659148, "pendingAmount": 0},
               "trx": {"amount": 0, "pendingAmount": 0}, "usdtbsc": {"amount": 250.5, "pendingAmount": 1.25}}
DOC_MIN_AMOUNT = {"success": True, "result": 0.00002496}
DOC_FEE = {"currency": "USDTTRC20", "fee": 1.32765969}
DOC_AUTH = {"token": "synthetic.session.token"}
DOC_INVALID_ADDRESS = {"status": False, "statusCode": 400, "code": "BAD_CREATE_WITHDRAWAL_REQUEST",
                       "message": "Invalid payout_address: [currency] [address]"}


def doc_withdrawal(**changes) -> dict:
    row = {"id": "5000000000", "address": WALLET, "currency": "usdtbsc", "amount": "5", "ipn_callback_url": None,
           "batch_withdrawal_id": "5000000713", "status": "CREATING", "error": None, "extra_id": None, "hash": None,
           "payout_description": None, "unique_external_id": None, "created_at": "2020-11-12T17:21:27.561Z",
           "requested_at": None, "updated_at": "2020-11-13T17:21:27.561Z", "update_history_log": None,
           "rejected_check_attempts": 0, "fee": None, "fee_paid_by": None, "is_request_payouts": False}
    row.update(changes)
    return row


def doc_create_response(**changes) -> dict:
    return {"id": "5000000713", "withdrawals": [doc_withdrawal(**changes)]}


def doc_status_response(**changes) -> dict:
    return {"id": "5000000713", "createdAt": "2020-11-12T17:06:12.791Z", "withdrawals": [doc_withdrawal(**changes)]}


class Provider:
    """An in-process stand-in for api.nowpayments.io. Records every request."""

    def __init__(self, routes=None):
        self.requests: list[httpx.Request] = []
        self.routes = {("POST", "/v1/auth"): (200, DOC_AUTH), ("GET", "/v1/balance"): (200, DOC_BALANCE)}
        self.routes.update(routes or {})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.routes.get((request.method, request.url.path))
        if answer is None:
            return httpx.Response(404, json={"message": "not found"})
        if callable(answer):
            answer = answer(request)
        if isinstance(answer, Exception):
            raise answer
        status, body = answer
        return httpx.Response(status, text=body) if isinstance(body, str) else httpx.Response(status, json=body)

    def paths(self) -> list[str]:
        return [f"{r.method} {r.url.path}" for r in self.requests]

    def body(self, index: int) -> dict:
        return json.loads(self.requests[index].content.decode("utf-8"))


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    """Every httpx client the NOWPayments service opens talks to `Provider`."""
    stand_in = Provider()
    real_client, real_async = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(nowpayments.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(stand_in.handler)))
    monkeypatch.setattr(nowpayments.httpx, "AsyncClient",
                        lambda **kw: real_async(transport=httpx.MockTransport(stand_in.handler)))
    monkeypatch.setattr(settings, "NOWPAYMENTS_SANDBOX", False)
    monkeypatch.setattr(pc, "_payout_login", lambda credentials: None)
    stand_in.waits = []
    monkeypatch.setattr(nowpayments, "_wait_for_next_code", lambda: stand_in.waits.append(1))
    nowpayments._last_code["value"] = None
    nowpayments.forget_payout_session()
    pc.invalidate_runtime()
    yield stand_in
    nowpayments.forget_payout_session()
    pc.invalidate_runtime()


def sign(raw: bytes, secret: str = IPN_SECRET) -> str:
    """What a JSON.stringify-based sender signs: sorted keys, non-ASCII kept."""
    text = json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(secret.encode(), text.encode("utf-8"), hashlib.sha512).hexdigest()


def post_ipn(client, body: dict, *, secret: str = IPN_SECRET, signature=None):
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"content-type": "application/json"}
    if signature is not False:
        headers["x-nowpayments-sig"] = signature or sign(raw, secret)
    return client.post(IPN_URL, content=raw, headers=headers)


# ===========================================================================
# 1. IPN signature
# ===========================================================================

@pytest.mark.parametrize("name", sorted(VECTORS["vectors"]))
@pytest.mark.parametrize("kind", ["documented_node", "arrays_kept"])
def test_a_callback_signed_the_way_the_provider_documents_is_accepted(name, kind):
    vector = VECTORS["vectors"][name]
    raw = vector["raw"].encode("utf-8")
    assert nowpayments.verify_ipn_signature(json.loads(raw), vector[kind], secret=IPN_SECRET, raw=raw) is True
    assert nowpayments.verify_ipn_signature(json.loads(raw), vector[kind].upper(), secret=IPN_SECRET, raw=raw) is True


def test_the_em_dash_in_the_order_description_was_the_reason_real_callbacks_were_refused():
    """Every MyHigh5 payment was created with 'MyHigh5 <product> — deposit <id>'.
    The check used before this change hashed the dash as \\u2014; the documented
    Node.js algorithm hashes the dash itself, so the two never matched."""
    vector = VECTORS["vectors"]["em_dash"]
    body = json.loads(vector["raw"])
    assert "—" in body["order_description"]
    earlier_check = hmac.new(IPN_SECRET.encode(), json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
                             hashlib.sha512).hexdigest()
    assert earlier_check != vector["documented_node"]
    assert nowpayments.verify_ipn_signature(body, vector["documented_node"], secret=IPN_SECRET) is True
    # The provider's own Python example still verifies (bodies it would have signed that way).
    assert nowpayments.verify_ipn_signature(body, earlier_check, secret=IPN_SECRET) is True


@pytest.mark.parametrize("signature", ["", None, "0" * 128, "zz" * 64, "abc", "0" * 127])
def test_a_missing_or_malformed_signature_is_refused(signature):
    vector = VECTORS["vectors"]["ascii_only"]
    raw = vector["raw"].encode()
    assert nowpayments.verify_ipn_signature(json.loads(raw), signature, secret=IPN_SECRET, raw=raw) is False


def test_a_wrong_or_missing_secret_and_a_changed_body_are_refused():
    vector = VECTORS["vectors"]["ascii_only"]
    raw = vector["raw"].encode()
    body = json.loads(raw)
    good = vector["documented_node"]
    assert nowpayments.verify_ipn_signature(body, good, secret="another-secret", raw=raw) is False
    assert nowpayments.verify_ipn_signature(body, good, secret="", raw=raw) is False
    assert nowpayments.verify_ipn_signature(body, good, secret="   ", raw=raw) is False
    tampered = raw.replace(b'"price_amount":10', b'"price_amount":1')
    assert tampered != raw
    assert nowpayments.verify_ipn_signature(json.loads(tampered), good, secret=IPN_SECRET, raw=tampered) is False
    extra = raw[:-1] + b',"payment_status_override":"finished"}'
    assert nowpayments.verify_ipn_signature(json.loads(extra), good, secret=IPN_SECRET, raw=extra) is False
    assert nowpayments.verify_ipn_signature([body], good, secret=IPN_SECRET, raw=raw) is False     # not an object


@pytest.mark.parametrize("token, expected", [
    ("10", "10"), ("10.0", "10"), ("14.8106", "14.8106"), ("1e-7", "1e-7"), ("0.0000001", "1e-7"),
    ("0.000001", "0.000001"), ("1e21", "1e+21"), ("123456789012345678901", "123456789012345680000"),
    ("0.0001817185463659148", "0.0001817185463659148"), ("-0.5", "-0.5"), ("0", "0"), ("2.50", "2.5"),
])
def test_numbers_are_written_as_javascript_writes_them(token, expected):
    assert nowpayments._js_number(token) == expected


def test_signature_verification_is_never_switched_off_by_configuration(client, db, monkeypatch):
    """No setting, switch or environment makes the endpoint accept an unsigned callback."""
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "")
    body = {"order_id": "mh5-none", "payment_id": "1", "payment_status": "finished"}
    assert post_ipn(client, body, signature=False).status_code == 403
    assert post_ipn(client, body, secret="").status_code == 403                    # an empty secret signs nothing
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    assert post_ipn(client, body, signature=False).status_code == 403
    assert post_ipn(client, body).json() == {"ok": True}                           # signed, unknown order: acknowledged
    for raw in (b"[1,2]", b'"text"', b"null", b"\xff\xfe"):
        assert client.post(IPN_URL, content=raw, headers={"content-type": "application/json",
                                                          "x-nowpayments-sig": "0" * 128}).status_code == 400


# ===========================================================================
# 2. IPN: crediting, duplicates, replay
# ===========================================================================

def pending_deposit(db, tag="ipn", code="kyc"):
    sponsor = _user(db, f"sponsor-{tag}@t.com")
    buyer = _user(db, f"buyer-{tag}@t.com", sponsor=sponsor)
    deposit = _deposit(db, buyer, code, status=DepositStatus.PENDING, tag=tag)
    db.commit()
    return deposit, sponsor


def ipn_body(deposit: Deposit, status: str, **extra) -> dict:
    body = {"payment_id": deposit.external_payment_id, "parent_payment_id": None, "payment_status": status,
            "pay_address": "0xpay", "price_amount": float(deposit.amount), "price_currency": "usd",
            "pay_amount": float(deposit.amount), "actually_paid": float(deposit.amount), "pay_currency": "usdtbsc",
            "order_id": deposit.order_id,
            "order_description": f"MyHigh5 kyc — deposit {deposit.id}", "outcome_amount": 9.97,
            "outcome_currency": "usdtbsc"}
    body.update(extra)
    return body


def money_rows(db, deposit) -> tuple[int, int]:
    db.expire_all()
    return db.query(AffiliateCommission).count(), db.query(JournalEntry).count()


def test_a_signed_finished_callback_credits_the_payment_once_however_often_it_is_sent(client, world, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    deposit, _sponsor = pending_deposit(db, code="annual_membership")
    assert post_ipn(client, ipn_body(deposit, "waiting")).status_code == 200
    assert money_rows(db, deposit) == (0, 0)
    assert post_ipn(client, ipn_body(deposit, "finished")).status_code == 200
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.VALIDATED
    credited = money_rows(db, deposit)
    assert credited[0] == 1 and credited[1] > 0
    for status in ("finished", "finished", "confirming", "waiting"):               # duplicates and late arrivals
        assert post_ipn(client, ipn_body(deposit, status)).status_code == 200
    assert money_rows(db, deposit) == credited
    assert db.get(Deposit, deposit.id).status == DepositStatus.VALIDATED


def test_a_callback_for_another_payment_or_another_price_is_refused_and_credits_nothing(client, world, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    deposit, _sponsor = pending_deposit(db)
    # A repeated deposit arrives as a NEW payment id pointing at the original (parent_payment_id).
    redeposit = ipn_body(deposit, "finished", payment_id="999000111", parent_payment_id=deposit.external_payment_id)
    assert post_ipn(client, redeposit).status_code == 409
    assert post_ipn(client, ipn_body(deposit, "finished", price_amount=1)).status_code == 409
    assert post_ipn(client, ipn_body(deposit, "finished", price_currency="eur")).status_code == 409
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.PENDING and money_rows(db, deposit) == (0, 0)


def test_a_replayed_finished_callback_cannot_revive_a_refunded_payment(client, world, monkeypatch):
    db = world
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    deposit, _sponsor = pending_deposit(db, code="annual_membership")
    assert post_ipn(client, ipn_body(deposit, "finished")).status_code == 200
    assert post_ipn(client, ipn_body(deposit, "refunded")).status_code == 200
    db.expire_all()
    row = db.get(Deposit, deposit.id)
    assert row.status == DepositStatus.FAILED and _REFUND_MARKER in row.admin_notes
    after_refund = money_rows(db, deposit)
    for _ in range(2):
        assert post_ipn(client, ipn_body(deposit, "finished")).status_code == 200  # an old notification, replayed
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.FAILED and money_rows(db, deposit) == after_refund


def test_a_payout_notification_is_acknowledged_and_never_pays_or_releases_anything(client, ledger, engine_on,
                                                                                   monkeypatch):
    db = ledger
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "5.00")
    run(db, FakeProvider())
    row = cashouts(db, user)[0]
    for status in ("FINISHED", "REJECTED", "FAILED"):
        notice = {"id": "123456789", "batch_withdrawal_id": row.provider_batch_id, "status": status, "error": None,
                  "currency": "usdtbsc", "amount": "5", "address": WALLET, "fee": None, "extra_id": None,
                  "hash": "0xhash", "ipn_callback_url": "callback_url"}
        assert post_ipn(client, notice).json() == {"ok": True}
        assert post_ipn(client, notice, signature="0" * 128).status_code == 403
    row = cashouts(db, user)[0]
    assert row.status == "processing" and db.query(JournalEntry).count() == 0
    assert get_commission_balance(db, user.id).reserved == Decimal("5.00")
    assert pc.webhook_health(db)["payout_notices_7_days"] == 3


# ===========================================================================
# 3. Pay-in: creation and status mapping
# ===========================================================================

DOC_PAYMENT = {"payment_id": "5745459419", "payment_status": "waiting", "pay_address": "0xpayaddress",
               "price_amount": 10, "price_currency": "usd", "pay_amount": 10.02, "pay_currency": "usdtbsc",
               "order_id": "mh5-synthetic", "order_description": "MyHigh5 kyc - deposit 1",
               "ipn_callback_url": "https://example.com/api/v1/webhooks/nowpayments",
               "created_at": "2020-12-22T15:00:22.742Z", "updated_at": "2020-12-22T15:00:22.742Z",
               "purchase_id": "5837122679", "amount_received": None, "payin_extra_id": None}


async def create(**changes):
    kwargs = dict(price_amount=Decimal("10.00"), price_currency="USD", order_id="mh5-synthetic",
                  order_description="MyHigh5 kyc - deposit 1", pay_currency="usdtbep20")
    kwargs.update(changes)
    return await nowpayments.create_payment(**kwargs)


async def test_payment_creation_sends_the_documented_fields_with_the_pay_in_key(provider, monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-payin-key")
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://example.com")
    provider.routes[("POST", "/v1/payment")] = (201, DOC_PAYMENT)
    created = await create()
    assert created["payment_id"] == "5745459419" and created["pay_address"] == "0xpayaddress"
    request = provider.requests[-1]
    assert request.headers["x-api-key"] == "synthetic-payin-key" and "authorization" not in request.headers
    assert provider.body(-1) == {"price_amount": 10.0, "price_currency": "usd", "order_id": "mh5-synthetic",
                                 "order_description": "MyHigh5 kyc - deposit 1", "pay_currency": "usdtbsc",
                                 "ipn_callback_url": "https://example.com/api/v1/webhooks/nowpayments"}


@pytest.mark.parametrize("answer", [
    (400, {"status": False, "statusCode": 400, "code": "INVALID_REQUEST_PARAMS", "message": "bad"}),
    (401, {"message": "Invalid api key"}),
    (500, "upstream error"),
    (201, {"payment_status": "waiting"}),                     # accepted, but no payment id to poll
    (201, "<html>not json</html>"),
])
async def test_a_payment_the_provider_did_not_create_is_an_error_not_a_pending_invoice(provider, monkeypatch, answer):
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-payin-key")
    provider.routes[("POST", "/v1/payment")] = answer
    with pytest.raises(nowpayments.NowPaymentsError) as error:
        await create()
    assert "synthetic-payin-key" not in str(error.value)


async def test_a_provider_timeout_on_creation_is_raised_and_nothing_is_assumed(provider, monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-payin-key")
    provider.routes[("POST", "/v1/payment")] = httpx.ReadTimeout("no answer")
    with pytest.raises(httpx.TimeoutException):
        await create()


async def test_payments_cannot_be_created_while_the_provider_is_switched_off_or_has_no_key(db, provider,
                                                                                         monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "")
    pc.invalidate_runtime()
    with pytest.raises(nowpayments.NowPaymentsError):
        await create()
    assert provider.requests == []


@pytest.mark.parametrize("provider_status, expected", [
    ("waiting", DepositStatus.PENDING), ("confirming", DepositStatus.PENDING), ("sending", DepositStatus.PENDING),
    ("confirmed", DepositStatus.VALIDATED), ("finished", DepositStatus.VALIDATED),
    ("partially_paid", DepositStatus.PARTIALLY_PAID), ("failed", DepositStatus.FAILED),
    ("refunded", DepositStatus.FAILED), ("expired", DepositStatus.EXPIRED),
    ("something_new", DepositStatus.PENDING), ("", DepositStatus.PENDING),
])
def test_every_documented_payment_status_maps_to_one_deposit_status(provider_status, expected):
    assert nowpayments.map_nowpayments_status(provider_status) == expected


@pytest.mark.parametrize("actually_paid, expected", [
    (10.0, DepositStatus.VALIDATED),          # the full price
    (12.5, DepositStatus.VALIDATED),          # an overpayment is a payment
    (9.6, DepositStatus.VALIDATED),           # short by no more than the configured tolerance
    (9.0, DepositStatus.PARTIALLY_PAID),      # an underpayment is never credited
    (0, DepositStatus.PARTIALLY_PAID),
])
def test_partial_under_and_over_payments(world, monkeypatch, actually_paid, expected):
    db = world
    monkeypatch.setattr(settings, "NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD", 0.5)
    deposit, _sponsor = pending_deposit(db, tag="amt")
    payload = {"payment_id": deposit.external_payment_id, "order_id": deposit.order_id,
               "payment_status": "partially_paid", "price_amount": 10, "price_currency": "usd", "pay_amount": 10,
               "actually_paid": actually_paid, "pay_currency": "usdtbsc"}
    assert nowpayments.resolve_deposit_status_from_provider(deposit, payload) == expected


# ===========================================================================
# 4. Status polling
# ===========================================================================

def aged(db, deposit, *, hours):
    deposit.created_at = datetime.utcnow() - timedelta(hours=hours)
    db.commit()
    return deposit


def status_payload(deposit, status, **extra):
    payload = {"payment_id": deposit.external_payment_id, "order_id": deposit.order_id, "payment_status": status,
               "price_amount": float(deposit.amount), "price_currency": "usd", "pay_amount": 10, "actually_paid": 0,
               "pay_currency": "usdtbsc"}
    payload.update(extra)
    return payload


def test_an_unpaid_invoice_expires_after_an_hour_only_once_the_provider_confirms_nothing_arrived(world):
    db = world
    deposit, _ = pending_deposit(db, tag="exp")
    fresh = aged(db, deposit, hours=0.5)
    assert payment_scheduler.apply_provider_status(db, fresh.id, status_payload(fresh, "waiting")) == "SYNCED"
    assert db.get(Deposit, deposit.id).status == DepositStatus.PENDING                # not yet an hour old
    aged(db, deposit, hours=2)
    assert payment_scheduler.apply_provider_status(db, deposit.id, status_payload(deposit, "waiting")) == "EXPIRED"
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.EXPIRED and money_rows(db, deposit) == (0, 0)


@pytest.mark.parametrize("status, expected", [("confirming", DepositStatus.PENDING),
                                              ("sending", DepositStatus.PENDING),
                                              ("partially_paid", DepositStatus.PARTIALLY_PAID),
                                              ("finished", DepositStatus.VALIDATED)])
def test_an_old_invoice_the_customer_did_pay_is_never_expired(world, status, expected):
    db = world
    deposit, _ = pending_deposit(db, tag="late")
    aged(db, deposit, hours=30)
    paid = 5 if status == "partially_paid" else 10
    payment_scheduler.apply_provider_status(db, deposit.id, status_payload(deposit, status, actually_paid=paid))
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == expected


async def test_when_the_provider_cannot_be_reached_nothing_expires_and_nothing_is_credited(world, monkeypatch):
    db = world
    deposit, _ = pending_deposit(db, tag="down")
    aged(db, deposit, hours=30)

    async def unreachable(_payment_id):
        raise nowpayments.NowPaymentsError("provider down")

    monkeypatch.setattr(nowpayments, "get_payment_status", unreachable)
    scheduler = payment_scheduler.PaymentScheduler()
    assert await scheduler._check_single_payment(db, deposit.id) == "PROVIDER_UNAVAILABLE"
    assert (await payment_scheduler.check_payment_now(db, deposit.id))["status"] == "pending"
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.PENDING and money_rows(db, deposit) == (0, 0)


def test_an_invoice_expired_here_is_credited_when_the_provider_later_reports_the_money(world):
    db = world
    deposit, _ = pending_deposit(db, tag="reopen", code="annual_membership")
    aged(db, deposit, hours=3)
    payment_scheduler.apply_provider_status(db, deposit.id, status_payload(deposit, "waiting"))
    apply = payment_scheduler.apply_provider_status
    assert apply(db, deposit.id, status_payload(deposit, "waiting")) == "STILL_EXPIRED"      # never re-opened
    assert apply(db, deposit.id, status_payload(deposit, "expired")) == "STILL_EXPIRED"
    assert apply(db, deposit.id, status_payload(deposit, "finished", actually_paid=10)) == "REOPENED"
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.VALIDATED
    credited = money_rows(db, deposit)
    assert credited[0] == 1
    assert apply(db, deposit.id, status_payload(deposit, "finished", actually_paid=10)) == "SKIPPED"
    assert money_rows(db, deposit) == credited                                               # credited once


def test_a_provider_answer_for_a_different_payment_changes_nothing(world):
    db = world
    deposit, _ = pending_deposit(db, tag="other")
    wrong = status_payload(deposit, "finished", payment_id="another-payment")
    assert payment_scheduler.apply_provider_status(db, deposit.id, wrong) == "IDENTITY_REJECTED"
    db.expire_all()
    assert db.get(Deposit, deposit.id).status == DepositStatus.PENDING and money_rows(db, deposit) == (0, 0)


async def test_one_pass_keeps_the_result_of_every_deposit_and_a_broken_one_stops_nothing(world, monkeypatch):
    """Earlier, each deposit's rollback discarded the changes made for the
    deposits before it, so only the last one of a pass was saved."""
    db = world
    first, _ = pending_deposit(db, tag="a")
    broken, _ = pending_deposit(db, tag="b")
    third, _ = pending_deposit(db, tag="c")
    expired, _ = pending_deposit(db, tag="d")
    aged(db, expired, hours=5)
    expired.status = DepositStatus.EXPIRED
    stub = Deposit(user_id=first.user_id, product_type_id=first.product_type_id, amount=10, currency="USD",
                   status=DepositStatus.PENDING, order_id="0xstub-no-payment-id")
    db.add(stub)
    db.commit()
    asked = []

    async def status(payment_id):
        asked.append(payment_id)
        if payment_id == broken.external_payment_id:
            raise RuntimeError("unexpected provider answer")
        deposit = db.query(Deposit).filter(Deposit.external_payment_id == payment_id).one()
        return status_payload(deposit, "finished", actually_paid=10)

    monkeypatch.setattr(nowpayments, "get_payment_status", status)
    monkeypatch.setattr(payment_scheduler, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    await payment_scheduler.PaymentScheduler()._check_pending_payments()
    db.expire_all()
    assert [db.get(Deposit, d.id).status for d in (first, broken, third, expired)] == [
        DepositStatus.VALIDATED, DepositStatus.PENDING, DepositStatus.VALIDATED, DepositStatus.VALIDATED]
    assert db.get(Deposit, stub.id).status == DepositStatus.PENDING and len(asked) == 4      # the stub is never polled


# ===========================================================================
# 5. Custody (read-only)
# ===========================================================================

def test_custody_balance_reads_the_spendable_amount_of_the_payout_currency(provider):
    assert nowpayments.custody_balance_sync("usdtbsc", CREDENTIALS) == Decimal("250.5")
    assert nowpayments.custody_balance_sync("USDT-BSC", CREDENTIALS) == Decimal("250.5")     # alias, any case
    assert nowpayments.custody_balance_sync("trx", CREDENTIALS) == Decimal("0")
    assert nowpayments.custody_balance_sync("usdttrc20", CREDENTIALS) == Decimal("0")       # not held: zero
    provider.routes[("GET", "/v1/balance")] = (200, {"USDTBSC": {"amount": "12.5", "pendingAmount": 3}})
    assert nowpayments.custody_balance_sync("usdtbsc", CREDENTIALS) == Decimal("12.5")
    assert all(r.method == "GET" and r.headers["x-api-key"] == "synthetic-payout-key"
               and "authorization" not in r.headers for r in provider.requests)             # key only, no session


@pytest.mark.parametrize("answer, status_code, ip_refused", [
    ((401, {"message": "Invalid api key"}), 401, False),
    ((403, {"status": False, "statusCode": 403, "code": "INVALID_IP", "message": "Invalid IP"}), 403, True),
    ((403, {"message": "Access denied"}), 403, False),
    ((500, "upstream error with details"), 500, False),
    ((200, "<html>not json</html>"), None, False),
    ((200, [1, 2, 3]), None, False),
    ((200, {"usdtbsc": {"pendingAmount": 3}}), None, False),
    ((200, {"usdtbsc": {"amount": "not-a-number"}}), None, False),
    ((200, {"usdtbsc": {"amount": -1}}), None, False),
])
def test_an_unreadable_or_refused_balance_is_an_error_and_never_an_assumed_balance(provider, answer, status_code,
                                                                                  ip_refused):
    provider.routes[("GET", "/v1/balance")] = answer
    with pytest.raises(nowpayments.NowPaymentsError) as error:
        nowpayments.custody_balance_sync("usdtbsc", CREDENTIALS)
    assert error.value.status_code == status_code and error.value.ip_refused is ip_refused
    text = str(error.value)
    assert "Invalid IP" not in text and "upstream error" not in text and "synthetic-payout-key" not in text


def test_the_provider_being_unreachable_is_raised_not_swallowed(provider):
    provider.routes[("GET", "/v1/balance")] = httpx.ConnectError("no route")
    with pytest.raises(httpx.HTTPError):
        nowpayments.custody_balance_sync("usdtbsc", CREDENTIALS)


def test_minimum_and_network_fee_use_the_documented_endpoints_and_fields(provider):
    provider.routes[("GET", "/v1/payout-withdrawal/min-amount/usdtbsc")] = (200, DOC_MIN_AMOUNT)
    provider.routes[("GET", "/v1/payout/fee")] = (200, DOC_FEE)
    assert nowpayments.payout_min_amount_sync("usdtbsc", CREDENTIALS) == Decimal("0.00002496")
    assert nowpayments.payout_fee_estimate_sync("usdtbsc", Decimal("5.00"), CREDENTIALS) == Decimal("1.32765969")
    assert dict(provider.requests[-1].url.params) == {"currency": "usdtbsc", "amount": "5.00"}
    provider.routes[("GET", "/v1/payout/fee")] = (200, {"currency": "usdtbsc"})
    with pytest.raises(nowpayments.NowPaymentsError):                                       # no fee: not "free"
        nowpayments.payout_fee_estimate_sync("usdtbsc", Decimal("5.00"), CREDENTIALS)
    provider.routes[("GET", "/v1/payout-withdrawal/min-amount/usdtbsc")] = (200, {"success": False})
    with pytest.raises(nowpayments.NowPaymentsError):
        nowpayments.payout_min_amount_sync("usdtbsc", CREDENTIALS)


def test_unsupported_currency_is_refused_by_the_address_check_before_any_payout(provider):
    provider.routes[("POST", "/v1/payout/validate-address")] = (400, DOC_INVALID_ADDRESS)
    assert nowpayments.validate_payout_address_sync(WALLET, "usdtbsc", CREDENTIALS) is False
    provider.routes[("POST", "/v1/payout/validate-address")] = (200, "OK")
    assert nowpayments.validate_payout_address_sync(WALLET, "usdtbep20", CREDENTIALS) is True
    assert provider.body(-1) == {"address": WALLET, "currency": "usdtbsc", "extra_id": None}
    provider.routes[("POST", "/v1/payout/validate-address")] = (403, {"message": "Invalid IP"})
    with pytest.raises(nowpayments.NowPaymentsError):
        nowpayments.validate_payout_address_sync(WALLET, "usdtbsc", CREDENTIALS)


# ===========================================================================
# 6. Payout authentication
# ===========================================================================

def test_the_payout_login_is_reused_for_under_five_minutes_then_renewed(provider, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(nowpayments.time, "time", lambda: clock[0])
    headers = nowpayments._engine_headers(CREDENTIALS, jwt=True)
    assert headers["Authorization"] == "Bearer synthetic.session.token"
    assert headers["x-api-key"] == "synthetic-payout-key"
    assert provider.body(0) == {"email": "payouts@example.com", "password": "synthetic-password"}
    clock[0] += 4 * 60
    nowpayments._engine_headers(CREDENTIALS, jwt=True)
    assert provider.paths().count("POST /v1/auth") == 1                                    # still the same session
    clock[0] += 60                                                                         # the token's 5 minutes
    nowpayments._engine_headers(CREDENTIALS, jwt=True)
    assert provider.paths().count("POST /v1/auth") == 2
    other = pc.ProviderCredentials("DATABASE", "DATABASE", {**CREDENTIALS.values, "PAYOUT_PASSWORD": "rotated"})
    nowpayments._engine_headers(other, jwt=True)
    assert provider.paths().count("POST /v1/auth") == 3                                    # never another login's token


@pytest.mark.parametrize("answer, status_code", [((401, {"message": "Unauthorized"}), 401),
                                                 ((403, {"message": "Invalid IP"}), 403),
                                                 ((200, {"no_token": True}), None),
                                                 ((200, "<html>"), None)])
def test_a_refused_login_is_an_authentication_error_without_any_credential_in_it(provider, answer, status_code):
    provider.routes[("POST", "/v1/auth")] = answer
    with pytest.raises(nowpayments.NowPaymentsError) as error:
        nowpayments._engine_token_sync(CREDENTIALS)
    assert error.value.stage == "auth" and error.value.status_code == status_code
    assert not any(secret in str(error.value) for secret in SECRET_VALUES + ["payouts@example.com"])
    assert nowpayments._engine_session["token"] is None


@pytest.mark.parametrize("missing", ["PAYOUT_API_KEY", "PAYOUT_EMAIL", "PAYOUT_PASSWORD", "PAYOUT_TOTP_SECRET"])
def test_a_payout_needs_every_payout_credential_and_never_borrows_the_pay_in_key(provider, missing):
    credentials = pc.ProviderCredentials("ENVIRONMENT", "ENVIRONMENT", {**CREDENTIALS.values, missing: None})
    with pytest.raises(nowpayments.NowPaymentsError):
        nowpayments.create_single_payout_sync(wallet_address=WALLET, amount=Decimal("5.00"), currency="usdtbsc",
                                              external_id="ref-1", credentials=credentials)
    assert "POST /v1/payout" not in provider.paths()
    assert all(r.headers.get("x-api-key") != "synthetic-payin-key" for r in provider.requests)


def test_the_login_check_opens_a_session_and_discards_it(provider):
    nowpayments.payout_login_check_sync(CREDENTIALS)
    assert provider.paths() == ["POST /v1/auth"] and nowpayments._engine_session["token"] is None


# ===========================================================================
# 7. Payout adapter
# ===========================================================================

def create_payout(**changes):
    kwargs = dict(wallet_address=WALLET, amount=Decimal("5.00"), currency="usdtbep20", external_id="ref-abc",
                  credentials=CREDENTIALS)
    kwargs.update(changes)
    return nowpayments.create_single_payout_sync(**kwargs)


def test_a_payout_is_created_once_then_confirmed_with_a_fresh_one_time_code(provider):
    provider.routes[("POST", "/v1/payout")] = (200, doc_create_response(unique_external_id="ref-abc"))
    provider.routes[("POST", "/v1/payout/5000000713/verify")] = (200, "OK")
    result = create_payout()
    assert result == {"batch_id": "5000000713", "withdrawal_id": "5000000000", "status": "CREATING",
                      "verified": True}
    assert provider.paths() == ["POST /v1/auth", "POST /v1/payout", "POST /v1/payout/5000000713/verify"]
    created = provider.requests[1]
    assert created.headers["x-api-key"] == "synthetic-payout-key"
    assert created.headers["authorization"] == "Bearer synthetic.session.token"
    assert provider.body(1) == {"withdrawals": [{"address": WALLET, "currency": "usdtbsc", "amount": 5.0,
                                                 "unique_external_id": "ref-abc"}]}        # one withdrawal, no extra_id
    code = provider.body(2)["verification_code"]
    assert isinstance(code, str) and len(code) == 6 and code.isdigit()
    assert provider.requests[2].headers["authorization"] == "Bearer synthetic.session.token"


@pytest.mark.parametrize("answer, code", [
    ((400, DOC_INVALID_ADDRESS), "BAD_CREATE_WITHDRAWAL_REQUEST"),
    ((400, {"status": False, "statusCode": 400, "code": "INSUFFICIENT_FUNDS", "message": "Not enough funds"}),
     "INSUFFICIENT_FUNDS"),
    ((403, {"message": "Invalid IP"}), None),
    ((422, "plain text"), None),
])
def test_a_refused_creation_reports_its_status_and_code_and_confirms_nothing(provider, answer, code):
    provider.routes[("POST", "/v1/payout")] = answer
    with pytest.raises(nowpayments.NowPaymentsError) as error:
        create_payout()
    assert error.value.status_code == answer[0] and error.value.code == code and error.value.stage == "create"
    assert "Invalid payout_address" not in str(error.value) and "Not enough funds" not in str(error.value)
    assert not any("/verify" in path for path in provider.paths())


def test_a_created_payout_whose_confirmation_fails_is_reported_as_created_and_unverified(provider):
    provider.routes[("POST", "/v1/payout")] = (200, doc_create_response())
    for answer, attempts in (((400, {"message": "Invalid verification code"}), 2), (httpx.ReadTimeout("x"), 1),
                             ((500, "x"), 1), ((401, {"message": "Unauthorized"}), 1), ((429, "slow"), 1)):
        provider.requests.clear()
        provider.routes[("POST", "/v1/payout/5000000713/verify")] = answer
        assert create_payout() == {"batch_id": "5000000713", "withdrawal_id": "5000000000", "status": "CREATING",
                                   "verified": False}
        assert provider.paths().count("POST /v1/payout/5000000713/verify") == attempts
        assert provider.paths().count("POST /v1/payout") == 1                      # verifying again never re-creates


def test_a_refused_code_is_tried_once_more_with_the_next_code_and_never_reused(provider):
    answers = iter([(400, {"message": "Invalid verification code"}), (200, "OK")])
    provider.routes[("POST", "/v1/payout")] = (200, doc_create_response())
    provider.routes[("POST", "/v1/payout/5000000713/verify")] = lambda request: next(answers)
    assert create_payout()["verified"] is True
    assert provider.paths().count("POST /v1/payout") == 1 and len(provider.waits) == 1     # waited for a new code
    provider.routes[("POST", "/v1/payout/5000000713/verify")] = (200, "OK")
    assert create_payout()["verified"] is True                                    # the next payout, seconds later
    assert len(provider.waits) == 2                                               # never the code already sent


@pytest.mark.parametrize("answer", [httpx.ReadTimeout("no answer"), httpx.ConnectError("reset"),
                                    (500, "upstream"), (502, "bad gateway"), (200, "<html>"), (200, {"id": ""}),
                                    (200, {"withdrawals": []}), (429, {"message": "slow down"})])
def test_no_answer_or_an_unreadable_answer_is_never_reported_as_a_refusal(provider, answer):
    """The engine releases a reservation only for a definite 4xx refusal."""
    provider.routes[("POST", "/v1/payout")] = answer
    with pytest.raises(Exception) as error:
        create_payout()
    code = getattr(error.value, "status_code", None)
    assert not (code is not None and 400 <= code < 500 and code not in (408, 429))


def test_payout_status_reads_the_documented_answer_with_the_api_key(provider):
    provider.routes[("GET", "/v1/payout/5000000713")] = (200, doc_status_response(
        status="FINISHED", hash="0xtransactionhash", unique_external_id="ref-abc"))
    details = nowpayments.payout_details_sync("5000000713", CREDENTIALS)
    assert details == {"status": "FINISHED", "withdrawal_id": "5000000000", "batch_id": "5000000713",
                       "address": WALLET, "currency": "usdtbsc", "amount": "5", "hash": "0xtransactionhash",
                       "unique_external_id": "ref-abc", "error": None}
    assert nowpayments.payout_status_sync("5000000713", CREDENTIALS) == "FINISHED"
    assert provider.paths() == ["GET /v1/payout/5000000713"] * 2                           # no login needed
    assert "authorization" not in provider.requests[0].headers


def test_payout_status_retries_once_with_the_session_only_when_the_key_alone_is_refused(provider):
    def answer(request):
        if "authorization" not in request.headers:
            return 401, {"message": "Unauthorized"}
        return 200, doc_status_response(status="SENDING")

    provider.routes[("GET", "/v1/payout/5000000713")] = answer
    assert nowpayments.payout_status_sync("5000000713", CREDENTIALS) == "SENDING"
    assert provider.paths() == ["GET /v1/payout/5000000713", "POST /v1/auth", "GET /v1/payout/5000000713"]


@pytest.mark.parametrize("answer", [(200, {"id": "5000000713", "withdrawals": []}),
                                    (200, {"id": "5000000713", "withdrawals": [doc_withdrawal(), doc_withdrawal()]}),
                                    (200, "nonsense"), (404, {"message": "not found"}), (500, "x")])
def test_a_status_answer_that_is_not_one_withdrawal_is_not_a_status(provider, answer):
    provider.routes[("GET", "/v1/payout/5000000713")] = answer
    with pytest.raises(nowpayments.NowPaymentsError):
        nowpayments.payout_status_sync("5000000713", CREDENTIALS)


def test_a_payout_can_be_found_again_by_its_unique_reference(provider):
    listed = {"payouts": [doc_withdrawal(id="1", batch_withdrawal_id="10", unique_external_id=None),
                          doc_withdrawal(id="2", batch_withdrawal_id="20", unique_external_id="ref-abc",
                                         status="SENDING"),
                          doc_withdrawal(id="3", batch_withdrawal_id="30", unique_external_id="ref-other")]}
    provider.routes[("GET", "/v1/payout")] = (200, listed)
    found = nowpayments.find_payout_by_external_id_sync("ref-abc", CREDENTIALS)
    assert (found["batch_id"], found["withdrawal_id"], found["status"]) == ("20", "2", "SENDING")
    assert nowpayments.find_payout_by_external_id_sync("ref-missing", CREDENTIALS) is None
    listed["payouts"].append(doc_withdrawal(id="4", batch_withdrawal_id="40", unique_external_id="ref-abc"))
    with pytest.raises(nowpayments.NowPaymentsError):                                      # two: not a match
        nowpayments.find_payout_by_external_id_sync("ref-abc", CREDENTIALS)
    provider.routes[("GET", "/v1/payout")] = (200, {"unexpected": []})
    with pytest.raises(nowpayments.NowPaymentsError):
        nowpayments.find_payout_by_external_id_sync("ref-abc", CREDENTIALS)


def test_the_earlier_direct_payout_senders_refuse(provider):
    for sender in (nowpayments.send_payout_sync, nowpayments.verify_payout_sync, nowpayments.send_single_payout_sync,
                   nowpayments._get_payout_jwt_sync):
        with pytest.raises(nowpayments.NowPaymentsError):
            sender(wallet_address=WALLET, amount_usd=5.0, currency="usdtbsc")
    assert provider.requests == []


async def test_the_earlier_async_payout_senders_refuse(provider):
    for sender in (nowpayments.send_payout, nowpayments.verify_payout, nowpayments.send_single_payout):
        with pytest.raises(nowpayments.NowPaymentsError):
            await sender(withdrawals=[])
    assert provider.requests == []


# ===========================================================================
# 8. Engine: safety and reconciliation
# ===========================================================================

class RichProvider(FakeProvider):
    """A FakeProvider that also reports what the real adapter can."""

    def __init__(self, *, details=None, found=None, valid_address=True, session_error=None, **kwargs):
        super().__init__(**kwargs)
        self.details = details or {}
        self.found = found
        self.valid_address = valid_address
        self.session_error = session_error
        self.validated, self.searched = [], []

    def payout_details(self, batch_id):
        self.status_calls.append(batch_id)
        answer = self.details.get(batch_id, {"status": self.statuses.get(batch_id, "PROCESSING")})
        if isinstance(answer, Exception):
            raise answer
        return dict(answer)

    def find_payout(self, external_id):
        self.searched.append(external_id)
        if isinstance(self.found, Exception):
            raise self.found
        return self.found(external_id) if callable(self.found) else self.found

    def check_session(self):
        if self.session_error is not None:
            raise self.session_error

    def validate_address(self, address, currency):
        self.validated.append((address, currency))
        if isinstance(self.valid_address, Exception):
            raise self.valid_address
        return self.valid_address


def paid_member(db, name="m1", amount="5.00"):
    user = member(db, name, method="CRYPTO")
    commission(db, user, amount)
    return user


def reserved(db, user) -> Decimal:
    return get_commission_balance(db, user.id).reserved


def test_a_failed_payout_is_not_final_so_it_stays_reserved_and_is_never_sent_again(ledger, engine_on):
    """The provider: 'only finished and rejected are final statuses' and a
    failed payout 'may be retried on NOWPayments' side'."""
    db = ledger
    user = paid_member(db)
    provider = RichProvider(statuses={"batch-1": "FAILED"})
    run(db, provider)
    assert run(db, provider)["reconciled"] == {"PROVIDER_FAILED": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code, row.provider_status) == ("unknown", "PROVIDER_FAILED_NOT_FINAL", "FAILED")
    assert reserved(db, user) == Decimal("5.00") and db.query(JournalEntry).count() == 0
    assert [d["type"] for d in engine.discrepancies(db)] == ["PROVIDER_FAILED_NOT_FINAL"]
    for day in range(1, 4):                                                        # later cycles: no second payout
        run(db, provider, now=NOW + timedelta(days=day))
    assert len(provider.created) == 1 and len(cashouts(db, user)) == 1


def test_a_failed_payout_the_provider_resumes_and_finishes_is_paid_exactly_once(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(statuses={"batch-1": "FAILED"})
    run(db, provider)
    run(db, provider)
    provider.statuses["batch-1"] = "SENDING"
    assert run(db, provider)["reconciled"] == {"PENDING": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code) == ("processing", None)
    provider.statuses["batch-1"] = "FINISHED"
    assert run(db, provider)["reconciled"] == {"COMPLETED": 1}
    assert run(db, provider)["reconciled"] == {}
    balance = get_commission_balance(db, user.id)
    assert (balance.paid_lifetime, balance.reserved, balance.available) == (Decimal("5.00"), 0, 0)
    assert len(provider.created) == 1 and engine.discrepancies(db) == []


def test_a_failed_payout_the_provider_finally_rejects_is_released(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(statuses={"batch-1": "FAILED"})
    run(db, provider)
    run(db, provider)
    provider.statuses["batch-1"] = "REJECTED"
    assert run(db, provider)["reconciled"] == {"FAILED": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code) == ("failed", "PROVIDER_REJECTED")
    assert get_commission_balance(db, user.id).available == Decimal("5.00") and reserved(db, user) == 0


@pytest.mark.parametrize("status", ["CREATING", "WAITING", "PROCESSING", "SENDING", "CANCELLED", "SOMETHING_NEW", ""])
def test_any_status_that_is_not_final_neither_pays_nor_releases(ledger, engine_on, status):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(statuses={"batch-1": status})
    run(db, provider)
    run(db, provider)
    assert cashouts(db, user)[0].status == "processing" and reserved(db, user) == Decimal("5.00")
    assert db.query(JournalEntry).count() == 0 and len(provider.created) == 1


@pytest.mark.parametrize("details, problem", [
    ({"status": "FINISHED", "address": "0x" + "c" * 40}, "PROVIDER_ADDRESS_MISMATCH"),
    ({"status": "FINISHED", "address": None}, "PROVIDER_ADDRESS_MISMATCH"),
    ({"status": "FINISHED", "address": WALLET, "unique_external_id": "someone-elses"}, "PROVIDER_REFERENCE_MISMATCH"),
    ({"status": "FINISHED", "address": WALLET, "currency": "usdttrc20"}, "PROVIDER_CURRENCY_MISMATCH"),
    ({"status": "REJECTED", "address": "0x" + "c" * 40}, "PROVIDER_ADDRESS_MISMATCH"),
])
def test_a_payout_that_is_not_this_cashouts_payout_is_never_settlement_evidence(ledger, engine_on, details, problem):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(details={"batch-1": details})
    run(db, provider)
    assert run(db, provider)["reconciled"] == {"EVIDENCE_MISMATCH": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.failure_code) == ("unknown", problem)
    assert reserved(db, user) == Decimal("5.00") and db.query(JournalEntry).count() == 0   # not paid, not released
    assert [d["type"] for d in engine.discrepancies(db)] == ["PROVIDER_EVIDENCE_MISMATCH"]


def test_a_finished_payout_to_the_same_address_is_evidence_and_its_hash_is_recorded(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    provider = RichProvider()
    run(db, provider)
    row = cashouts(db, user)[0]
    provider.details["batch-1"] = {"status": "FINISHED", "address": WALLET.upper().replace("0X", "0x"),
                                   "currency": "USDTBSC", "hash": "0xtransactionhash", "withdrawal_id": "77",
                                   "unique_external_id": engine.external_reference(row)}
    assert run(db, provider)["reconciled"] == {"COMPLETED": 1}
    evidence = db.query(AuditTrail).filter_by(action="CASHOUT_PROVIDER_EVIDENCE", record_id=row.id).one()
    assert evidence.new_values["transaction_hash"] == "0xtransactionhash"
    assert WALLET not in json.dumps(evidence.new_values)
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")


def timed_out(**_kwargs):
    raise TimeoutError("provider timed out")


def test_a_payout_whose_creation_got_no_answer_is_found_again_by_its_unique_reference(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(create=timed_out, found=None)
    assert run(db, provider)["members"] == {"OUTCOME_UNKNOWN": 1}
    assert run(db, provider)["reconciled"] == {"NOT_LOCATED": 1}                    # not found proves nothing
    row = cashouts(db, user)[0]
    assert (row.status, row.provider_batch_id) == ("unknown", None) and reserved(db, user) == Decimal("5.00")
    reference = engine.external_reference(row)
    assert provider.searched == [reference] and provider.created[0]["external_id"] == reference

    provider.found = lambda ref: {"batch_id": "b-77", "status": "SENDING", "address": WALLET,
                                  "unique_external_id": ref}
    assert run(db, provider)["reconciled"] == {"LOCATED": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.provider_batch_id, row.provider_status) == ("unknown", "b-77", "SENDING")
    provider.details["b-77"] = {"status": "FINISHED", "address": WALLET, "unique_external_id": reference}
    assert run(db, provider)["reconciled"] == {"COMPLETED": 1}
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00") and len(provider.created) == 1


@pytest.mark.parametrize("found", [
    lambda ref: {"batch_id": "b-77", "status": "SENDING", "address": "0x" + "c" * 40, "unique_external_id": ref},
    lambda ref: {"batch_id": "b-77", "status": "SENDING", "address": WALLET, "unique_external_id": "another"},
    lambda ref: {"batch_id": None, "status": "SENDING", "address": WALLET, "unique_external_id": ref},
    RuntimeError("list unavailable"),
])
def test_a_payout_that_cannot_be_matched_stays_unknown_and_reserved(ledger, engine_on, found):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(create=timed_out, found=found)
    run(db, provider)
    for _ in range(3):
        run(db, provider)
    row = cashouts(db, user)[0]
    assert row.status == "unknown" and row.provider_batch_id is None
    assert reserved(db, user) == Decimal("5.00") and len(provider.created) == 1 and len(cashouts(db, user)) == 1


def test_a_refused_payout_login_stops_the_cycle_before_anything_is_reserved(ledger, engine_on):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(session_error=nowpayments.NowPaymentsError("refused", status_code=401, stage="auth"))
    report = run(db, provider)
    assert report["stopped"] == "PROVIDER_AUTH_FAILED" and report["members"] == {}
    assert cashouts(db) == [] and provider.created == [] and reserved(db, user) == 0


@pytest.mark.parametrize("error, code", [
    (nowpayments.NowPaymentsError("refused", status_code=401, stage="auth"), "PROVIDER_AUTH_FAILED"),
    (nowpayments.NowPaymentsError("refused", status_code=403, stage="create", ip_refused=True),
     "PROVIDER_IP_NOT_WHITELISTED"),
])
def test_a_platform_side_refusal_is_not_the_members_failed_attempt(ledger, engine_on, error, code):
    db = ledger
    first, second = paid_member(db, "m1"), paid_member(db, "m2")

    def refuse(**_kwargs):
        raise error

    provider = RichProvider(create=refuse)
    report = run(db, provider)
    assert report["members"] == {code: 1} and report["stopped"] == code           # the second member is not tried
    row = cashouts(db, first)[0]
    assert (row.status, row.failure_code) == ("cancelled", code) and cashouts(db, second) == []
    assert get_commission_balance(db, first.id).available == Decimal("5.00")
    # Not counted as a failed attempt: the member is paid as soon as the platform problem is fixed.
    assert run(db, RichProvider(), now=NOW + timedelta(minutes=20))["members"] == {"SUBMITTED": 2}


@pytest.mark.parametrize("valid, outcome", [(False, "PROVIDER_ADDRESS_INVALID"),
                                            (TimeoutError("no answer"), "ADDRESS_CHECK_UNAVAILABLE")])
def test_an_address_the_provider_does_not_accept_is_never_reserved_or_sent(ledger, engine_on, valid, outcome):
    db = ledger
    user = paid_member(db)
    provider = RichProvider(valid_address=valid)
    assert run(db, provider)["members"] == {outcome: 1}
    assert provider.validated == [(WALLET, "usdtbsc")] and provider.created == [] and cashouts(db) == []
    assert get_commission_balance(db, user.id).available == Decimal("5.00")


def test_the_real_provider_object_offers_every_step_the_engine_uses(provider):
    real = engine.NowPaymentsPayoutProvider(CREDENTIALS)
    for name in ("balance", "minimum", "network_fee", "create_payout", "payout_status", "payout_details",
                 "find_payout", "check_session", "validate_address"):
        assert callable(getattr(real, name))
    real.check_session()
    assert real.balance("usdtbsc") == Decimal("250.5")
    assert provider.paths() == ["POST /v1/auth", "GET /v1/balance"]


def test_with_the_server_switch_off_nothing_reaches_the_provider(ledger, provider, monkeypatch):
    db = ledger
    for name, value in PAYOUT_ENV.items():
        monkeypatch.setattr(settings, name, value)
    configure(db, crypto_auto_payout_enabled=True)
    user = paid_member(db)
    assert settings.CRYPTO_AUTO_PAYOUT_ENABLED is False
    assert engine.run_cycle(db, now=NOW) == {"enabled": False, "reconciled": {}, "members": {}}
    assert provider.requests == [] and cashouts(db) == [] and reserved(db, user) == 0


def test_the_whole_engine_cycle_against_the_documented_provider_answers(ledger, engine_on, provider):
    """The real adapter and the real engine together, over the in-process provider."""
    db = ledger
    user = paid_member(db)
    sent = {}

    def created(request):
        sent.update(json.loads(request.content)["withdrawals"][0])
        return 200, doc_create_response(unique_external_id=sent["unique_external_id"])

    provider.routes.update({
        ("GET", "/v1/payout-withdrawal/min-amount/usdtbsc"): (200, {"success": True, "result": 0.5}),
        ("GET", "/v1/payout/fee"): (200, {"currency": "usdtbsc", "fee": 0.0234}),
        ("POST", "/v1/payout/validate-address"): (200, "OK"),
        ("POST", "/v1/payout"): created,
        ("POST", "/v1/payout/5000000713/verify"): (200, "OK"),
    })
    assert engine.run_cycle(db, now=NOW)["members"] == {"SUBMITTED": 1}
    row = cashouts(db, user)[0]
    assert (row.status, row.provider_batch_id, row.provider_status) == ("processing", "5000000713", "CREATING")
    assert sent == {"address": WALLET, "currency": "usdtbsc", "amount": 5.0,
                    "unique_external_id": engine.external_reference(row)}
    assert provider.paths().count("POST /v1/payout") == 1

    provider.routes[("GET", "/v1/payout/5000000713")] = (200, doc_status_response(
        status="FINISHED", hash="0xtransactionhash", unique_external_id=sent["unique_external_id"]))
    assert engine.run_cycle(db, now=NOW + timedelta(minutes=20))["reconciled"] == {"COMPLETED": 1}
    assert get_commission_balance(db, user.id).paid_lifetime == Decimal("5.00")
    assert provider.paths().count("POST /v1/payout") == 1                          # one payout, ever
    logged = " ".join(str(r.url) for r in provider.requests)
    assert not any(secret in logged for secret in SECRET_VALUES)


# ===========================================================================
# 9. Admin: connection test and readiness
# ===========================================================================

def http_for(provider_routes=None):
    table = {"/status": (200, '{"message": "OK"}'), "/currencies": (200, '{"currencies": ["usdtbsc"]}'),
             "/balance": (200, json.dumps(DOC_BALANCE)),
             "payout-withdrawal/min-amount": (200, json.dumps(DOC_MIN_AMOUNT)), "payout/fee": (200, json.dumps(DOC_FEE))}
    table.update(provider_routes or {})

    def http(url, headers):
        for fragment, answer in table.items():
            if fragment in url:
                return answer
        return 404, "{}"

    return http


def payout_env(monkeypatch):
    for name, value in PAYOUT_ENV.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-env-payin-key")
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", IPN_SECRET)


def states(db) -> dict:
    return {i["key"]: i["state"] for i in pc.provider_view(db)["readiness"]["items"]}


def test_credentials_alone_are_never_shown_as_verified(db, monkeypatch):
    payout_env(monkeypatch)
    view = pc.provider_view(db)["readiness"]
    assert set(i["state"] for i in view["items"]) <= set(view["states"]) == set(pc.READINESS_STATES)
    assert states(db) == {"provider": "CONFIGURED", "api_authentication": "CONFIGURED", "ipn": "CONFIGURED",
                          "custody": "CONFIGURED", "ip_whitelist": "UNVERIFIED", "payout_login": "CONFIGURED",
                          "payout_2fa": "CONFIGURED", "automatic_payouts": "DISABLED"}
    assert view["last_error"] is None and view["last_test_at"] is None and view["outstanding"]


def test_nothing_configured_is_unverified_and_says_what_is_missing(db, monkeypatch):
    for name in ("NOWPAYMENTS_API_KEY", "NOWPAYMENTS_IPN_SECRET", *PAYOUT_ENV):
        monkeypatch.setattr(settings, name, "")
    assert states(db) == {"provider": "CONFIGURED", "api_authentication": "UNVERIFIED", "ipn": "UNVERIFIED",
                          "custody": "UNVERIFIED", "ip_whitelist": "UNVERIFIED", "payout_login": "UNVERIFIED",
                          "payout_2fa": "UNVERIFIED", "automatic_payouts": "DISABLED"}
    outstanding = " ".join(pc.provider_view(db)["readiness"]["outstanding"])
    assert "pay-in API key" in outstanding and "IPN secret" in outstanding and "authenticator" in outstanding


def test_a_successful_connection_test_verifies_what_it_proved_and_nothing_more(db, monkeypatch):
    payout_env(monkeypatch)
    admin = member(db, "boss", admin=True)
    logins = []
    result = pc.run_connection_test(db, admin, http=http_for(), now=NOW, login=logins.append)
    assert result["status"] == "OK" and len(logins) == 1
    assert states(db) == {"provider": "CONFIGURED", "api_authentication": "VERIFIED", "ipn": "CONFIGURED",
                          "custody": "VERIFIED", "ip_whitelist": "VERIFIED", "payout_login": "VERIFIED",
                          "payout_2fa": "CONFIGURED",                 # provable only by a real payout
                          "automatic_payouts": "DISABLED"}            # the switches are off
    assert result["facts"]["custody_balance"] == "250.5" and result["facts"]["custody_pending"] == "1.25"


def test_the_ip_whitelist_refusal_is_shown_as_blocked_and_the_login_is_not_even_tried(db, monkeypatch):
    payout_env(monkeypatch)
    admin = member(db, "boss", admin=True)
    logins = []
    blocked = (403, '{"status":false,"statusCode":403,"code":"INVALID_IP","message":"Invalid IP 2a02:4780::1"}')
    result = pc.run_connection_test(db, admin, now=NOW, login=logins.append, http=http_for(
        {"/balance": blocked, "payout-withdrawal/min-amount": blocked, "payout/fee": blocked}))
    assert result["status"] == "IP_NOT_WHITELISTED" and logins == []
    view = pc.provider_view(db)
    current = {i["key"]: i["state"] for i in view["readiness"]["items"]}
    assert (current["custody"], current["ip_whitelist"], current["payout_login"]) == ("BLOCKED", "BLOCKED",
                                                                                     "CONFIGURED")
    assert current["api_authentication"] == "VERIFIED"
    assert view["readiness"]["last_error"] == {"check": "custody_balance", "code": "IP_NOT_WHITELISTED",
                                              "message": pc.CONNECTION_MESSAGES["IP_NOT_WHITELISTED"],
                                              "at": NOW.isoformat()}
    assert any("Whitelist this server" in line for line in view["readiness"]["outstanding"])
    assert "2a02:4780" not in json.dumps(view) and "Invalid IP" not in json.dumps(view)     # sanitized


@pytest.mark.parametrize("error, code", [
    (nowpayments.NowPaymentsError("x", status_code=401, stage="auth"), "AUTH_FAILED"),
    (nowpayments.NowPaymentsError("x", status_code=404, stage="auth"), "AUTH_FAILED"),
    (nowpayments.NowPaymentsError("x", status_code=403, stage="auth", ip_refused=True), "IP_NOT_WHITELISTED"),
    (nowpayments.NowPaymentsError("x", status_code=429, stage="auth"), "RATE_LIMITED"),
    (nowpayments.NowPaymentsError("x", status_code=500, stage="auth"), "PROVIDER_ERROR"),
    (nowpayments.NowPaymentsError("token missing", stage="auth"), "INVALID_RESPONSE"),
    (TimeoutError("no answer"), "UNREACHABLE"),
])
def test_a_refused_payout_login_blocks_readiness_with_a_code_and_no_provider_text(db, monkeypatch, error, code):
    payout_env(monkeypatch)
    admin = member(db, "boss", admin=True)

    def login(_credentials):
        raise error

    result = pc.run_connection_test(db, admin, http=http_for(), now=NOW, login=login)
    assert result["status"] == code and result["last_success_at"] is None and result["payout_login"] == code
    assert states(db)["payout_login"] == "BLOCKED" and states(db)["custody"] == "VERIFIED"
    saved = json.dumps(db.query(PaymentSettings).one().last_connection_test_detail)
    audit = json.dumps([a.new_values for a in db.query(PaymentConfigAudit).all()])
    for secret in list(PAYOUT_ENV.values()) + ["synthetic-env-payin-key", IPN_SECRET]:
        assert secret not in saved and secret not in audit and secret not in json.dumps(result)


def test_readiness_follows_the_switches(db, monkeypatch):
    payout_env(monkeypatch)
    admin = member(db, "boss", admin=True)
    pc.run_connection_test(db, admin, http=http_for(), now=NOW, login=lambda c: None)
    monkeypatch.setattr(settings, "CRYPTO_AUTO_PAYOUT_ENABLED", True)
    assert states(db)["automatic_payouts"] == "DISABLED"                           # the admin switch is still off
    configure(db, crypto_auto_payout_enabled=True)
    assert states(db)["automatic_payouts"] == "CONFIGURED"                         # proven only by a real payout
    configure(db, provider_enabled=False)
    assert states(db)["provider"] == "DISABLED" and states(db)["automatic_payouts"] == "DISABLED"


def test_ipn_readiness_is_verified_only_by_an_accepted_callback(client, db, monkeypatch):
    payout_env(monkeypatch)
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://example.com")
    body = {"order_id": "mh5-unknown", "payment_id": "1", "payment_status": "waiting"}
    assert states(db)["ipn"] == "CONFIGURED"
    assert post_ipn(client, body, signature="0" * 128).status_code == 403
    assert states(db)["ipn"] == "BLOCKED"
    assert post_ipn(client, body).status_code == 200                               # signed with the configured secret
    assert states(db)["ipn"] == "VERIFIED"
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "http://example.com")
    assert states(db)["ipn"] == "BLOCKED"                                          # the callback URL must be https


def test_the_provider_page_needs_an_administrator_and_never_returns_a_secret(client, db, monkeypatch):
    payout_env(monkeypatch)
    admin = member(db, "boss", admin=True)
    ordinary = member(db, "ordinary")
    url = "/api/v1/admin/finance/provider"
    assert client.get(url).status_code in (401, 403)
    assert client.get(url, headers=auth(ordinary)).status_code == 403
    assert client.post("/api/v1/admin/finance/connection-test", headers=auth(ordinary)).status_code == 403
    page = client.get(url, headers=auth(admin))
    assert page.status_code == 200 and page.json()["readiness"]["items"]
    text = page.text
    for secret in list(PAYOUT_ENV.values()) + ["synthetic-env-payin-key", IPN_SECRET]:
        assert secret not in text


def test_the_connection_test_is_bounded_per_administrator(client, db, monkeypatch):
    """Each run logs in to the provider: it cannot be replayed without limit."""
    from app.api.api_v1.endpoints import payment_settings
    from app.core import rate_limit

    payout_env(monkeypatch)
    admin = member(db, "boss", admin=True)
    rate_limit._buckets.clear()
    runs = []
    monkeypatch.setattr(pc, "run_connection_test", lambda db, actor, **kw: runs.append(actor.id) or {"status": "OK"})
    url = "/api/v1/admin/finance/connection-test"
    answers = [client.post(url, headers=auth(admin)).status_code
               for _ in range(payment_settings.CONNECTION_TEST_LIMIT + 2)]
    assert answers == [200] * payment_settings.CONNECTION_TEST_LIMIT + [429, 429]
    assert len(runs) == payment_settings.CONNECTION_TEST_LIMIT
    rate_limit._buckets.clear()
