"""Functional tests for authentication business flows."""
import pytest


pytestmark = pytest.mark.functional


def test_user_can_register_login_and_fetch_profile(client, db, test_user_data):
    from tests.conftest import confirm_email

    reg = client.post("/api/v1/auth/register", json=test_user_data)
    assert reg.status_code == 201
    confirm_email(db, test_user_data["email"])       # the member follows the emailed link

    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    profile = me.json()
    assert profile["email"] == test_user_data["email"]
    assert profile["username"] == test_user_data["username"]
    assert profile["email_verified"] is True and profile["email_verification_required"] is True


def test_user_can_update_profile(client, auth_headers, test_user_data):
    update = client.put(
        "/api/v1/users/me",
        json={"bio": "Contest enthusiast"},
        headers=auth_headers,
    )
    assert update.status_code == 200
    assert update.json()["bio"] == "Contest enthusiast"

    me = client.get("/api/v1/users/me", headers=auth_headers)
    assert me.json()["bio"] == "Contest enthusiast"
