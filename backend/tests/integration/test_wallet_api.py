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


def test_update_and_get_wallet(client, auth_headers):
    payload = {"usdt_wallet_address": VALID_BEP20, "payout_currency": "usdtbsc"}
    patch = client.patch("/api/v1/users/me/wallet", json=payload, headers=auth_headers)
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["usdt_wallet_address"] == VALID_BEP20
    assert body["wallet_configured"] is True
    assert body["payout_currency"] == "usdtbsc"

    get_resp = client.get("/api/v1/users/me/wallet", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["wallet_configured"] is True


def test_update_wallet_rejects_invalid_address(client, auth_headers):
    resp = client.patch(
        "/api/v1/users/me/wallet",
        json={"usdt_wallet_address": "not-a-wallet", "payout_currency": "usdtbsc"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
