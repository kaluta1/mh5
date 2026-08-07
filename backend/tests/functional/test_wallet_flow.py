"""Functional tests for affiliate payout wallet configuration."""
import pytest

VALID_ERC20 = "0x" + "c" * 40


pytestmark = pytest.mark.functional


def test_wallet_configuration_flow(client, auth_headers):
    balance = client.get("/api/v1/wallet/balance", headers=auth_headers)
    assert balance.status_code == 200
    assert "available_balance" in balance.json()

    save = client.patch(
        "/api/v1/users/me/wallet",
        json={"usdt_wallet_address": VALID_ERC20, "payout_currency": "usdterc20"},
        headers=auth_headers,
    )
    assert save.status_code == 200
    saved = save.json()
    assert saved["payout_currency"] == "usdterc20"
    assert saved["wallet_configured"] is True

    preview = client.get("/api/v1/wallet/withdraw/preview", headers=auth_headers)
    assert preview.status_code == 200
    assert preview.json()["wallet_configured"] is True
