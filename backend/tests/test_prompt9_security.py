"""Prompt 9 cross-cutting security regression tests."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.core.rate_limit import _client_ip
from app.services.shufti_pro import ShuftiProService


def test_registration_rejects_privileged_mass_assignment(client, test_user_data):
    response = client.post(
        "/api/v1/auth/register",
        json={**test_user_data, "is_admin": True, "is_verified": True, "is_active": False},
    )
    assert response.status_code == 422


def test_validate_token_does_not_accept_query_string(client, auth_headers):
    token = auth_headers["Authorization"].split(" ", 1)[1]
    response = client.post(f"/api/v1/auth/validate-token?token={token}")
    assert response.status_code == 401
    assert client.post("/api/v1/auth/validate-token", headers=auth_headers).status_code == 200


def test_financial_graphql_requires_admin(client):
    response = client.post("/graphql", json={"query": "{ chartOfAccounts { id } }"})
    assert response.status_code == 200
    assert response.json().get("errors")
    assert response.json().get("data") is None


def test_kyc_deployment_diagnostics_require_admin(client, auth_headers):
    response = client.get("/api/v1/kyc/deployment/kaluta-urls", headers=auth_headers)
    assert response.status_code == 403


def test_inactive_shufti_webhook_is_fail_closed(client):
    response = client.post(
        "/api/v1/kyc/webhook/shufti-pro",
        json={"reference": "attacker", "event": "verification.accepted"},
    )
    assert response.status_code == 404


def test_shufti_signature_uses_raw_body_and_secret(monkeypatch):
    service = ShuftiProService()
    monkeypatch.setattr(service, "secret_key", "test-provider-secret")
    body = b'{"event":"verification.accepted","reference":"ref_1"}'
    hashed_secret = hashlib.sha256(b"test-provider-secret").hexdigest().encode("ascii")
    signature = hashlib.sha256(body + hashed_secret).hexdigest()
    assert service.verify_webhook_signature(body, signature)
    assert not service.verify_webhook_signature(body + b" ", signature)
    assert not service.verify_webhook_signature(body, "")


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = []
    if forwarded:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1234)})


def test_untrusted_peer_cannot_spoof_rate_limit_identity(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    assert _client_ip(_request("203.0.113.10", "198.51.100.2")) == "203.0.113.10"
    assert _client_ip(_request("127.0.0.1", "198.51.100.2")) == "198.51.100.2"
