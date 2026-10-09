"""Fail-closed network guard: no test can reach NOWPayments.

Every way this code base (or a library under it) can open a connection is
intercepted for the provider's hosts, whatever the client:

  * httpx, sync and async - the real transports refuse before connecting
    (an in-process httpx.MockTransport is a different class and still works);
  * everything else (requests, urllib, aiohttp, a raw socket) - the name is
    refused at resolution and at connection, so no packet leaves.

A refused request raises BlockedProviderRequest AND is recorded. Application
code often catches a provider error and carries on ("the provider could not
be reached"), which would hide the attempt; so after each test the record is
checked and the test FAILS if anything was attempted, caught or not.

The guard is installed for the whole session and is not something a test can
opt out of. A test that exercises the guard itself declares the attempts it
expects with `provider_network.expect_blocked()`; they are still refused.

The provider credentials are blanked for the session as well, so a credential
from a developer's local .env is never present in a test process. Tests that
need one set a synthetic value with monkeypatch.
"""
from __future__ import annotations

import socket
from typing import List, Optional

import httpx
import pytest

BLOCKED_DOMAINS = ("nowpayments.io",)
PROVIDER_CREDENTIAL_SETTINGS = ("NOWPAYMENTS_API_KEY", "NOWPAYMENTS_IPN_SECRET", "NOWPAYMENTS_PAYOUT_API_KEY",
                                "NOWPAYMENTS_EMAIL", "NOWPAYMENTS_PASSWORD", "NOWPAYMENTS_PAYOUT_TOTP_SECRET")


class BlockedProviderRequest(AssertionError):
    """A test tried to reach the real payment provider."""


def is_blocked_host(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    name = str(host or "").strip().rstrip(".").lower()
    return any(name == domain or name.endswith("." + domain) for domain in BLOCKED_DOMAINS)


class ProviderNetworkGuard:
    def __init__(self) -> None:
        self.attempts: List[str] = []
        self._expected = False
        self.installed = False

    def refuse(self, how: str, host) -> None:
        self.attempts.append(f"{how} -> {host}")
        raise BlockedProviderRequest(
            f"A test tried to reach the payment provider ({how} -> {host}). Tests must use an in-process "
            "HTTP transport or a fake provider; nothing may be sent to NOWPayments.")

    def start_test(self) -> None:
        self.attempts, self._expected = [], False

    def expect_blocked(self) -> None:
        """This test deliberately attempts a provider request to prove it is refused."""
        self._expected = True

    def verdict(self) -> Optional[str]:
        """Why the finished test must fail (None = it attempted nothing unexpected)."""
        if self.attempts and not self._expected:
            return ("This test attempted a real payment-provider request, which was blocked: "
                    + "; ".join(self.attempts))
        return None


guard = ProviderNetworkGuard()


def _install() -> None:
    if guard.installed:
        return
    guard.installed = True

    real_sync = httpx.HTTPTransport.handle_request
    real_async = httpx.AsyncHTTPTransport.handle_async_request
    real_getaddrinfo = socket.getaddrinfo
    real_create_connection = socket.create_connection
    real_gethostbyname = socket.gethostbyname

    def handle_request(self, request):
        if is_blocked_host(request.url.host):
            guard.refuse(f"httpx {request.method} {request.url.path}", request.url.host)
        return real_sync(self, request)

    async def handle_async_request(self, request):
        if is_blocked_host(request.url.host):
            guard.refuse(f"httpx (async) {request.method} {request.url.path}", request.url.host)
        return await real_async(self, request)

    def getaddrinfo(host, *args, **kwargs):
        if is_blocked_host(host):
            guard.refuse("name resolution", host)
        return real_getaddrinfo(host, *args, **kwargs)

    def gethostbyname(host, *args, **kwargs):
        if is_blocked_host(host):
            guard.refuse("name resolution", host)
        return real_gethostbyname(host, *args, **kwargs)

    def create_connection(address, *args, **kwargs):
        if isinstance(address, tuple) and address and is_blocked_host(address[0]):
            guard.refuse("socket connection", address[0])
        return real_create_connection(address, *args, **kwargs)

    httpx.HTTPTransport.handle_request = handle_request
    httpx.AsyncHTTPTransport.handle_async_request = handle_async_request
    socket.getaddrinfo = getaddrinfo
    socket.gethostbyname = gethostbyname
    socket.create_connection = create_connection


# Installed at import, before any test module (or the application) is imported.
_install()


@pytest.fixture(scope="session", autouse=True)
def _no_local_provider_credentials():
    """A real credential from a local .env must never exist in a test process."""
    from app.core.config import settings

    for name in PROVIDER_CREDENTIAL_SETTINGS:
        setattr(settings, name, "")
    yield


@pytest.fixture(autouse=True)
def provider_network():
    """Active in EVERY test. Fails the test if it attempted a provider request."""
    guard.start_test()
    yield guard
    problem = guard.verdict()
    guard.start_test()
    if problem:
        pytest.fail(problem, pytrace=False)
