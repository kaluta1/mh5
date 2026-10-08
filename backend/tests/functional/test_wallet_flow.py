"""Functional tests for affiliate payout wallet configuration."""
import pytest

VALID_BEP20 = "0x" + "c" * 40


pytestmark = pytest.mark.functional


def test_wallet_configuration_flow(client, auth_headers, test_user_data):
    balance = client.get("/api/v1/wallet/balance", headers=auth_headers)
    assert balance.status_code == 200
    assert "available_balance" in balance.json()

    save = client.patch(
        "/api/v1/users/me/wallet",
        json={"usdt_wallet_address": VALID_BEP20, "payout_currency": "usdtbsc",
              "current_password": test_user_data["password"]},
        headers=auth_headers,
    )
    assert save.status_code == 200
    saved = save.json()
    assert saved["payout_currency"] == "usdtbsc"
    assert saved["wallet_configured"] is True
    # A new wallet is on a security hold and saving it pays nothing.
    assert saved["wallet_status"] == "ON_HOLD" and saved["pending_commissions_paid"] == 0

    preview = client.get("/api/v1/wallet/withdraw/preview", headers=auth_headers)
    assert preview.status_code == 200
    assert preview.json()["wallet_configured"] is True
