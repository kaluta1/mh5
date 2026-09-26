"""Phase 4.2: an exceeded rate limit answers 429 (not 500), with the app's
existing safe body, no traceback and no sensitive values in logs. The
rate-limit POLICY itself (limits, windows, keys, client-IP resolution) is
unchanged and pinned here.
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import app.core.rate_limit as rl

LOGIN = "/api/v1/auth/login"
PW = "RL-PASSWORD-SECRET-9q"
TOKEN = "RL-ACCESS-TOKEN-SECRET-77"
GTOKEN = "RL-GUARDIAN-TOKEN-SECRET-abcdefghijklmnopqrstuvwxyz"
CTOKEN = "RL-COMPLETION-TOKEN-SECRET-0123456789abcdefghij"
SECRETS = (PW, TOKEN, GTOKEN, CTOKEN)
ROUTE_BODY = {"detail": "Too many requests. Please try again later.", "code": "HTTP_429", "message": "Too many requests. Please try again later."}


@pytest.fixture
def api(client, app):
    """Real middleware stack; server exceptions become responses, as in production."""
    rl._buckets.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    rl._buckets.clear()


def exhaust(api, path, n, **kw):
    return [api.post(path, **kw).status_code for _ in range(n)]


# 1-5, 7-11 ----------------------------------------------------------------------

def test_exceeding_a_route_limit_returns_safe_429_not_500(api, caplog):
    caplog.set_level(logging.DEBUG)
    limit, _ = rl.RATE_LIMITS[LOGIN]
    below = exhaust(api, LOGIN, limit, data={"username": "u", "password": PW})
    assert 429 not in below and 500 not in below                                  # 1 below the limit: normal
    r = api.post(LOGIN, data={"username": "u", "password": PW, "access_token": TOKEN,
                              "guardian_token": GTOKEN, "completion_token": CTOKEN})
    assert r.status_code == 429                                                    # 2
    assert r.json() == ROUTE_BODY                                                  # 5 existing safe format
    for bad in ("Traceback", "HTTPException", "_buckets", "rate_limit.py", "127.0.0.1", "testclient"):
        assert bad not in r.text                                                   # 3, 4
    assert "retry-after" not in {k.lower() for k in r.headers}                     # 6 never implemented; not invented
    assert r.headers.get("x-content-type-options") == "nosniff"                    # still inside security headers
    assert "x-backend-build-id" in {k.lower() for k in r.headers}
    assert not [rec for rec in caplog.records if rec.levelno >= logging.ERROR]     # 7 no error logging
    assert "Traceback" not in caplog.text
    for secret in SECRETS:                                                         # 8-11 nothing sensitive
        assert secret not in caplog.text
    assert "Rate limit exceeded: POST /api/v1/auth/login" in caplog.text           # safe operational line
    assert "testclient" not in caplog.text                                         # no client address logged


def test_global_limit_returns_its_existing_message(api):
    g_limit, _ = rl.GLOBAL_LIMIT
    codes = [api.get("/health").status_code for _ in range(g_limit)]
    assert set(codes) == {200}
    r = api.get("/health")
    assert r.status_code == 429
    assert r.json() == {"detail": rl.GLOBAL_LIMIT_MESSAGE, "code": "HTTP_429", "message": rl.GLOBAL_LIMIT_MESSAGE}


def test_options_preflight_is_never_rate_limited(api):
    limit, _ = rl.RATE_LIMITS[LOGIN]
    exhaust(api, LOGIN, limit + 1, data={})
    r = api.options(LOGIN, headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert r.status_code != 429


# 12-14 ----------------------------------------------------------------------------

def test_unrelated_application_error_is_still_a_500(api, app):
    async def broken():
        raise RuntimeError("unexpected")
    app.add_api_route("/__test__/rl-broken", broken, methods=["GET"])
    try:
        r = api.get("/__test__/rl-broken")
    finally:
        app.router.routes[:] = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/__test__/rl-broken"]
    assert r.status_code == 500 and r.text == "Internal Server Error"


def test_validation_and_auth_errors_unchanged(api):
    assert api.post("/api/v1/auth/register/complete", json={"token": "x"}).status_code == 422
    assert api.get("/api/v1/users/me").status_code == 401
    assert api.post("/api/v1/guardian/requests/lookup", json={"token": "x" * 43}).status_code == 404


# 15-17: policy is unchanged and routes stay independent ------------------------------

def test_rate_limit_policy_is_unchanged():
    assert rl.RATE_LIMITS == {
        "/api/v1/auth/login": (10, 60),
        "/api/v1/auth/register": (5, 3600),
        "/api/v1/guardian": (30, 3600),
        "/api/v1/contest-eligibility/claims": (30, 3600),  # Phase 5 nominee claim tokens
        "/api/v1/admin/content-moderation": (120, 60),  # Phase 6 moderation endpoints
        "/api/v1/auth/password-reset-request": (5, 3600),
        "/api/v1/auth/password-reset-confirm": (10, 3600),
        "/api/v1/share-links": (60, 60),
        "/api/v1/kyc/initiate": (10, 3600),
        "/api/v1/kyc/webhook": (300, 60),
        "/api/v1/payments": (20, 60),
        "/api/v1/wallet": (30, 60),
        "/api/v1/votes": (120, 60),
        "/api/v1/comments": (30, 60),
        "/api/v1/media/upload": (20, 60),
        "/api/v1/search": (60, 60),
    }
    assert rl.GLOBAL_LIMIT == (200, 60)


def test_routes_keep_separate_budgets(api):
    limit, _ = rl.RATE_LIMITS[LOGIN]
    exhaust(api, LOGIN, limit + 1, data={})
    assert api.post(LOGIN, data={}).status_code == 429
    # A different policy route (guardian: 30/hour) is unaffected by the login budget.
    r = api.post("/api/v1/guardian/requests/lookup", json={"token": "x" * 43})
    assert r.status_code == 404


def test_guardian_limit_still_applies_at_30(api):
    g_limit, _ = rl.RATE_LIMITS["/api/v1/guardian"]
    codes = [api.post("/api/v1/guardian/requests/lookup", json={"token": "x" * 43}).status_code
             for _ in range(g_limit)]
    assert 429 not in codes
    r = api.post("/api/v1/guardian/requests/respond", json={"token": GTOKEN, "decision": "DECLINE"})
    assert r.status_code == 429 and r.json() == ROUTE_BODY and GTOKEN not in r.text


def test_register_limit_still_applies_at_5(api):
    limit, _ = rl.RATE_LIMITS["/api/v1/auth/register"]
    codes = exhaust(api, "/api/v1/auth/register", limit, json={"password": PW})
    assert 429 not in codes
    assert api.post("/api/v1/auth/register", json={"password": PW}).status_code == 429


# ordering: the middleware must answer, never raise ---------------------------------------

def _request(path="/api/v1/auth/login", client=("203.0.113.9", 1234), headers=()):
    scope = {"type": "http", "method": "POST", "path": path, "headers": [(k.encode(), v.encode()) for k, v in headers],
             "client": client, "query_string": b"", "scheme": "http", "server": ("testserver", 80)}
    return Request(scope)


@pytest.mark.anyio
async def test_middleware_returns_429_response_instead_of_raising():
    rl._buckets.clear()
    mw = rl.RateLimitMiddleware(app=lambda *a: None)
    called = []

    async def call_next(request):
        called.append(1)
        return "downstream"
    limit, _ = rl.RATE_LIMITS[LOGIN]
    for _ in range(limit):
        assert await mw.dispatch(_request(), call_next) == "downstream"
    response = await mw.dispatch(_request(), call_next)             # must not raise
    assert response.status_code == 429 and len(called) == limit    # downstream not called when limited
    rl._buckets.clear()


def test_rate_limit_middleware_sits_inside_security_headers(app):
    order = [m.cls.__name__ for m in app.user_middleware]            # outermost first
    assert order.index("BuildIdMiddleware") < order.index("RateLimitMiddleware")
    assert order.index("SecurityHeadersMiddleware") < order.index("RateLimitMiddleware")


# client IP / proxy (current design pinned; see report) --------------------------------------

def test_direct_untrusted_peer_ignores_forwarded_header():
    req = _request(client=("198.51.100.20", 1), headers=[("x-forwarded-for", "1.1.1.1")])
    assert rl._client_ip(req) == "198.51.100.20"


def test_trusted_local_proxy_peer_uses_forwarded_client():
    req = _request(client=("127.0.0.1", 1), headers=[("x-forwarded-for", "203.0.113.50")])
    assert rl._client_ip(req) == "203.0.113.50"


def test_spoofed_forwarded_for_cannot_bypass_limit_behind_uvicorn_proxy_headers(client, app):
    """Production topology: Apache (127.0.0.1) appends the real client to
    X-Forwarded-For; uvicorn's ProxyHeadersMiddleware (trusted 127.0.0.1) picks the
    right-most untrusted entry. Rotating a client-supplied left-most value must not
    create fresh budgets."""
    rl._buckets.clear()
    stack = ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")
    limit, _ = rl.RATE_LIMITS[LOGIN]
    with TestClient(stack, raise_server_exceptions=False, client=("127.0.0.1", 40000)) as c:
        codes = [c.post(LOGIN, data={}, headers={"X-Forwarded-For": f"10.9.{i}.{i}, 203.0.113.77"}).status_code
                 for i in range(limit + 1)]
    assert codes[-1] == 429 and 429 not in codes[:-1]
    rl._buckets.clear()


@pytest.mark.xfail(strict=True, reason="FINDING (not fixed in 4.2): without uvicorn's proxy-header rewrite, "
                                       "_client_ip trusts the LEFT-most X-Forwarded-For entry, which a client "
                                       "can supply; the right-most (proxy-appended) entry is the trustworthy one.")
def test_app_level_forwarded_parsing_uses_proxy_appended_entry():
    req = _request(client=("127.0.0.1", 1), headers=[("x-forwarded-for", "1.1.1.1, 203.0.113.77")])
    assert rl._client_ip(req) == "203.0.113.77"
