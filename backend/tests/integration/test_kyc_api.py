"""Integration tests for KYC API surface."""
import pytest


pytestmark = pytest.mark.integration


def test_kaluta_deployment_urls_are_admin_only(client, auth_headers):
    resp = client.get("/api/v1/kyc/deployment/kaluta-urls", headers=auth_headers)
    assert resp.status_code == 403


def test_kyc_status_requires_auth(client):
    resp = client.get("/api/v1/kyc/status")
    assert resp.status_code == 401
