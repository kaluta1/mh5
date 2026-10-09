"""No automated test can reach NOWPayments.

Regression for 2026-10-09: the connection test gained a payout login check;
`test_connection_test_uses_only_read_requests_and_records_a_sanitized_result`
injected a fake only for the GET requests, and the guard of the time was a
list of function NAMES to replace, which did not contain the new function. One
real `POST /v1/auth` with synthetic example credentials left the machine.

The guard is now in tests/provider_network_guard.py: it refuses the provider's
HOSTS at the transport and socket level for every test, whichever function or
HTTP client is used, and fails the test even when the application swallows the
refusal. Each test below makes a request with NO mock installed and shows
that it is refused before anything is sent.
"""
from __future__ import annotations

import socket
import urllib.request
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.services import nowpayments_service as nowpayments
from app.services import payment_config as pc
from tests.provider_network_guard import (
    BLOCKED_DOMAINS,
    PROVIDER_CREDENTIAL_SETTINGS,
    BlockedProviderRequest,
    ProviderNetworkGuard,
    guard,
    is_blocked_host,
)
from tests.unit.test_dual_cashout import member

pytestmark = pytest.mark.unit

CREDENTIALS = pc.ProviderCredentials("ENVIRONMENT", "ENVIRONMENT", {
    "PAYIN_API_KEY": "synthetic-payin-key", "IPN_SECRET": "synthetic-ipn-secret",
    "PAYOUT_API_KEY": "synthetic-payout-key", "PAYOUT_EMAIL": "payouts@example.com",
    "PAYOUT_PASSWORD": "synthetic-password", "PAYOUT_TOTP_SECRET": "JBSWY3DPEHPK3PXP"})
HOSTS = ("api.nowpayments.io", "api-sandbox.nowpayments.io")


@pytest.fixture(autouse=True)
def clean_provider_state(monkeypatch):
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "synthetic-payin-key")
    nowpayments.forget_payout_session()
    pc.invalidate_runtime()
    yield
    nowpayments.forget_payout_session()
    pc.invalidate_runtime()


def test_the_guard_is_installed_for_the_whole_session_and_local_credentials_are_absent(provider_network):
    assert provider_network is guard and guard.installed
    assert BLOCKED_DOMAINS == ("nowpayments.io",)
    assert all(is_blocked_host(h) for h in HOSTS + ("nowpayments.io", "API.NowPayments.IO.", b"api.nowpayments.io"))
    assert not any(is_blocked_host(h) for h in ("localhost", "127.0.0.1", "example.com", "notnowpayments.io",
                                                "nowpayments.io.example.com", "", None))
    assert nowpayments.NOWPAYMENTS_API_BASE.split("/")[2] in HOSTS
    assert nowpayments.NOWPAYMENTS_SANDBOX_BASE.split("/")[2] in HOSTS
    # Nothing from a developer's .env: only what a test sets.
    assert settings.NOWPAYMENTS_API_KEY == "synthetic-payin-key"
    assert all(getattr(settings, name) == "" for name in PROVIDER_CREDENTIAL_SETTINGS if name != "NOWPAYMENTS_API_KEY")


@pytest.mark.parametrize("sandbox", [False, True])
def test_the_exact_request_that_escaped_is_now_refused_before_it_is_sent(provider_network, monkeypatch, sandbox):
    """POST /v1/auth through the payout login, with no mock at all."""
    monkeypatch.setattr(settings, "NOWPAYMENTS_SANDBOX", sandbox)
    provider_network.expect_blocked()
    with pytest.raises(BlockedProviderRequest):
        nowpayments.payout_login_check_sync(CREDENTIALS)
    assert provider_network.attempts == [f"httpx POST /v1/auth -> {HOSTS[1] if sandbox else HOSTS[0]}"]
    assert nowpayments._engine_session["token"] is None


def test_the_connection_test_path_that_leaked_is_refused_and_would_fail_its_test(db, provider_network, monkeypatch):
    """The original path: the GETs are faked, the login is not. The service
    swallows the refusal and reports "unreachable", so only the recorded
    attempt reveals it - and that record fails the test at teardown."""
    for name, value in (("NOWPAYMENTS_PAYOUT_API_KEY", "synthetic-payout-key"), ("NOWPAYMENTS_EMAIL",
                        "payouts@example.com"), ("NOWPAYMENTS_PASSWORD", "synthetic-password"),
                        ("NOWPAYMENTS_PAYOUT_TOTP_SECRET", "JBSWY3DPEHPK3PXP")):
        monkeypatch.setattr(settings, name, value)
    admin = member(db, "boss", admin=True)

    def only_the_gets(url, headers):
        if "/balance" in url:
            return 200, '{"usdtbsc": {"amount": 1, "pendingAmount": 0}}'
        if "min-amount" in url:
            return 200, '{"result": 0.5}'
        if "payout/fee" in url:
            return 200, '{"fee": 0.02}'
        return 200, '{"message": "OK", "currencies": ["usdtbsc"]}'

    result = pc.run_connection_test(db, admin, http=only_the_gets)
    assert result["payout_login"] == "UNREACHABLE" and result["status"] != "OK"
    assert provider_network.attempts == ["httpx POST /v1/auth -> api.nowpayments.io"]
    assert "blocked" in provider_network.verdict()                                # this is what fails a test
    provider_network.expect_blocked()
    assert provider_network.verdict() is None


def test_every_synchronous_adapter_call_is_refused(provider_network):
    provider_network.expect_blocked()
    calls = [
        lambda: nowpayments.custody_balance_sync("usdtbsc", CREDENTIALS),
        lambda: nowpayments.payout_min_amount_sync("usdtbsc", CREDENTIALS),
        lambda: nowpayments.payout_fee_estimate_sync("usdtbsc", Decimal("5"), CREDENTIALS),
        lambda: nowpayments.validate_payout_address_sync("0x" + "a" * 40, "usdtbsc", CREDENTIALS),
        lambda: nowpayments.payout_details_sync("5000000713", CREDENTIALS),
        lambda: nowpayments.find_payout_by_external_id_sync("ref", CREDENTIALS),
        lambda: nowpayments._engine_token_sync(CREDENTIALS),
        lambda: nowpayments._confirm_payout_sync("5000000713", CREDENTIALS),
        lambda: nowpayments.create_single_payout_sync(wallet_address="0x" + "a" * 40, amount=Decimal("5"),
                                                      currency="usdtbsc", external_id="ref",
                                                      credentials=CREDENTIALS),
        lambda: pc._http_get("https://api.nowpayments.io/v1/status", {}),
        lambda: pc._http_get("https://api-sandbox.nowpayments.io/v1/balance", {"x-api-key": "synthetic"}),
        lambda: pc._payout_login(CREDENTIALS),
    ]
    for call in calls:
        with pytest.raises(BlockedProviderRequest):
            call()
    assert len(provider_network.attempts) == len(calls)
    # A payout is never created: its login is refused first, so POST /v1/payout is not even attempted.
    assert not any(a.startswith("httpx POST /v1/payout ") for a in provider_network.attempts)


async def test_every_asynchronous_pay_in_call_is_refused(provider_network):
    provider_network.expect_blocked()
    with pytest.raises(BlockedProviderRequest):
        await nowpayments.get_payment_status("5745459419")
    with pytest.raises(BlockedProviderRequest):
        await nowpayments.get_available_currencies()
    with pytest.raises(BlockedProviderRequest):
        await nowpayments.create_payment(price_amount=Decimal("10"), price_currency="usd", order_id="mh5-guard",
                                         order_description="guard", pay_currency="usdtbsc")
    assert provider_network.attempts == ["httpx (async) GET /v1/payment/5745459419 -> api.nowpayments.io",
                                         "httpx (async) GET /v1/currencies -> api.nowpayments.io",
                                         "httpx (async) POST /v1/payment -> api.nowpayments.io"]


async def test_a_plain_httpx_client_of_either_kind_is_refused(provider_network):
    provider_network.expect_blocked()
    for host in HOSTS:
        with pytest.raises(BlockedProviderRequest):
            httpx.get(f"https://{host}/v1/status")
        with pytest.raises(BlockedProviderRequest):
            with httpx.Client() as client:
                client.post(f"https://{host}/v1/payout", json={"withdrawals": []})
        with pytest.raises(BlockedProviderRequest):
            async with httpx.AsyncClient() as client:
                await client.get(f"https://{host}/v1/balance")
    assert len(provider_network.attempts) == 6


def test_any_other_http_client_or_a_raw_socket_is_refused_too(provider_network):
    """requests, urllib, aiohttp and friends all resolve the name or open a
    socket to it: both are refused, so no packet leaves."""
    provider_network.expect_blocked()
    for host in HOSTS:
        with pytest.raises(BlockedProviderRequest):
            socket.getaddrinfo(host, 443)
        with pytest.raises(BlockedProviderRequest):
            socket.gethostbyname(host)
        with pytest.raises(BlockedProviderRequest):
            socket.create_connection((host, 443), timeout=1)
        with pytest.raises(BlockedProviderRequest):
            urllib.request.urlopen(f"https://{host}/v1/status", timeout=1)
    requests = pytest.importorskip("requests")
    with pytest.raises(BlockedProviderRequest):
        requests.post("https://api.nowpayments.io/v1/auth", json={"email": "a@example.com"}, timeout=1)
    assert len(provider_network.attempts) == 9


def test_an_in_process_transport_and_other_hosts_are_not_affected(provider_network):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"message": "OK"}))
    with httpx.Client(transport=transport) as client:
        assert client.get("https://api.nowpayments.io/v1/status").json() == {"message": "OK"}
    assert socket.getaddrinfo("localhost", 80)
    assert provider_network.attempts == [] and provider_network.verdict() is None


def test_an_attempt_fails_the_test_even_when_the_code_under_test_swallowed_it():
    watcher = ProviderNetworkGuard()
    watcher.start_test()
    assert watcher.verdict() is None
    try:
        watcher.refuse("httpx POST /v1/auth", "api.nowpayments.io")
    except Exception:  # noqa: BLE001 - exactly what application code does
        pass
    assert "httpx POST /v1/auth -> api.nowpayments.io" in watcher.verdict()
    watcher.start_test()                                                           # the next test starts clean
    assert watcher.verdict() is None
