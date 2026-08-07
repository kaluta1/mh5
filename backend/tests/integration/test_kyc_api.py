"""Integration tests for KYC API surface."""
import pytest


pytestmark = pytest.mark.integration


def test_kaluta_deployment_urls(client):
    resp = client.get("/api/v1/kyc/deployment/kaluta-urls")
    assert resp.status_code == 200
    body = resp.json()
    assert "webhook_url" in body
    assert "redirect_url" in body
    assert "provider" in body
    assert body["provider"] == "kaluta"


def test_kyc_status_requires_auth(client):
    resp = client.get("/api/v1/kyc/status")
    assert resp.status_code == 401
