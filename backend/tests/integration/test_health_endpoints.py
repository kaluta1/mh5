"""Integration tests for health and status endpoints."""
import pytest


pytestmark = pytest.mark.integration


def test_root_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "build_id" in body


def test_api_build_info(client):
    resp = client.get("/api/v1/build-info")
    assert resp.status_code == 200
    body = resp.json()
    assert "build_id" in body
    assert body.get("nomination_roster_fix") is True


def test_auth_health_probe(client):
    resp = client.get("/api/v1/auth/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_db_schema_health_against_sqlite(client):
    resp = client.get("/api/v1/health/db-schema")
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body
    assert "missing_users_columns" in body
    # In-memory SQLite test DB should have all model columns after create_all.
    assert body["ok"] is True
    assert body["missing_users_columns"] == []


def test_security_headers_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert "X-Backend-Build-Id" in resp.headers
