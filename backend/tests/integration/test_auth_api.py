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


def test_register_never_creates_a_duplicate_and_does_not_reveal_the_account(client, db, test_user_data):
    """A second registration with the same address creates nothing, changes
    nothing, and answers exactly like the first (no account enumeration). The
    full matrix is in tests/unit/test_email2_auth_security.py."""
    from app.models.user import User

    first = client.post("/api/v1/auth/register", json=test_user_data)
    assert first.status_code == 201

    second = client.post("/api/v1/auth/register", json={**test_user_data, "username": "another_name_1"})
    assert second.status_code == 201
    assert second.json() == first.json()
    assert "existe" not in second.text.lower() and "already" not in second.text.lower()
    assert db.query(User).filter(User.email == test_user_data["email"]).count() == 1
    assert db.query(User).filter(User.username == "another_name_1").count() == 0


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
