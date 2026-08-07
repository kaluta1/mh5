"""End-to-end platform journey through the HTTP API."""
import pytest

VALID_BEP20 = "0x" + "d" * 40


pytestmark = pytest.mark.e2e


def test_full_member_onboarding_journey(client, test_user_data):
    """
    Register → login → profile → wallet → KYC config probe → wallet balance.
    """
    reg = client.post("/api/v1/auth/register", json=test_user_data)
    assert reg.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200

    kyc_urls = client.get("/api/v1/kyc/deployment/kaluta-urls")
    assert kyc_urls.status_code == 200
    assert kyc_urls.json()["provider"] == "kaluta"

    wallet = client.patch(
        "/api/v1/users/me/wallet",
        json={"usdt_wallet_address": VALID_BEP20, "payout_currency": "usdtbsc"},
        headers=headers,
    )
    assert wallet.status_code == 200

    balance = client.get("/api/v1/wallet/balance", headers=headers)
    assert balance.status_code == 200

    schema = client.get("/api/v1/health/db-schema")
    assert schema.status_code == 200
    assert schema.json()["ok"] is True
