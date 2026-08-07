"""Integration tests for auth API."""
import pytest


pytestmark = pytest.mark.integration


def test_register_and_login(client, test_user_data):
    reg = client.post("/api/v1/auth/register", json=test_user_data)
    assert reg.status_code == 201
    assert reg.json()["email"] == test_user_data["email"]

    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    assert login.status_code == 200
    body = login.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_rejects_duplicate_email(client, test_user_data):
    first = client.post("/api/v1/auth/register", json=test_user_data)
    assert first.status_code == 201

    second = client.post("/api/v1/auth/register", json=test_user_data)
    assert second.status_code == 400
    assert "existe déjà" in second.json()["detail"].lower() or "already" in second.json()["detail"].lower()


def test_login_rejects_wrong_password(client, test_user_data):
    client.post("/api/v1/auth/register", json=test_user_data)
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": "WrongPass123!@"},
    )
    assert login.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 401
