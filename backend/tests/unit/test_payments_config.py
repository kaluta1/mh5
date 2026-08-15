"""Unit tests for NOWPayments payout configuration helpers."""
import pytest

from app.services.nowpayments_service import normalize_pay_currency, payouts_configured


pytestmark = pytest.mark.unit


def test_normalize_pay_currency_aliases():
    assert normalize_pay_currency("usdtbep20") == "usdtbsc"
    assert normalize_pay_currency("USDTTRC20") == "usdttrc20"


def test_payouts_configured_false_without_credentials(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "NOWPAYMENTS_API_KEY", "")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PAYOUT_API_KEY", "")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_EMAIL", "")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PASSWORD", "")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PAYOUT_TOTP_SECRET", "")
    assert payouts_configured() is False


def test_payouts_configured_false_without_totp(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "NOWPAYMENTS_API_KEY", "key")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PAYOUT_API_KEY", "key")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_EMAIL", "a@b.c")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PASSWORD", "secret")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PAYOUT_TOTP_SECRET", "")
    assert payouts_configured() is False


def test_payouts_configured_true_with_full_credentials(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "NOWPAYMENTS_API_KEY", "key")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PAYOUT_API_KEY", "")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_EMAIL", "a@b.c")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PASSWORD", "secret")
    monkeypatch.setattr(config.settings, "NOWPAYMENTS_PAYOUT_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    assert payouts_configured() is True
