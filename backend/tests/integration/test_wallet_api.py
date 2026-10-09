"""Integration tests for wallet and user payout endpoints."""
import pytest

VALID_BEP20 = "0x" + "b" * 40


pytestmark = pytest.mark.integration


def test_get_wallet_unauthenticated(client):
    resp = client.get("/api/v1/users/me/wallet")
    assert resp.status_code == 401


def test_wallet_balance_unauthenticated(client):
    resp = client.get("/api/v1/wallet/balance")
    assert resp.status_code == 401


def test_update_and_get_wallet(client, auth_headers, test_user_data):
    payload = {"usdt_wallet_address": VALID_BEP20, "payout_currency": "usdtbsc"}
    # The payout destination cannot be set with a session alone.
    for password in (None, "not-the-password"):
        body = payload if password is None else {**payload, "current_password": password}
        refused = client.patch("/api/v1/users/me/wallet", json=body, headers=auth_headers)
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PASSWORD_REQUIRED"
    assert client.get("/api/v1/users/me/wallet", headers=auth_headers).json()["wallet_configured"] is False

    payload["current_password"] = test_user_data["password"]
    patch = client.patch("/api/v1/users/me/wallet", json=payload, headers=auth_headers)
    assert patch.status_code == 200, patch.text
    body = patch.json()
    # The password alone records a pending change: the wallet takes effect only
    # when the one-time link sent to the account's email address is confirmed.
    assert body["confirmation_required"] is True
    assert body["usdt_wallet_address"] is None and body["wallet_configured"] is False
    assert body["payout_currency"] == "usdtbsc"
    assert body["pending_wallet"]["wallet"] == f"{VALID_BEP20[:6]}...{VALID_BEP20[-4:]}"

    get_resp = client.get("/api/v1/users/me/wallet", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["wallet_configured"] is False
    assert get_resp.json()["pending_wallet"]["payout_currency"] == "usdtbsc"


def test_update_wallet_rejects_invalid_address(client, auth_headers):
    resp = client.patch(
        "/api/v1/users/me/wallet",
        json={"usdt_wallet_address": "not-a-wallet", "payout_currency": "usdtbsc"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
