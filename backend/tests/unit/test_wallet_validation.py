"""Unit tests for payout wallet validation."""
import pytest

from app.services.wallet_validation import (
    normalize_payout_currency,
    validate_payout_address,
    PAYOUT_CURRENCY_OPTIONS,
)


pytestmark = pytest.mark.unit

VALID_BEP20 = "0x" + "a" * 40
VALID_TRC20 = "T" + "1" * 33


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("usdtbep20", "usdtbsc"),
        ("USDT-BSC", "usdtbsc"),
        ("usdterc20", "usdterc20"),
        ("usdttrc20", "usdttrc20"),
        (None, "usdtbsc"),
        ("unknown", "usdtbsc"),
    ],
)
def test_normalize_payout_currency(raw, expected):
    assert normalize_payout_currency(raw) == expected


def test_validate_bep20_address():
    assert validate_payout_address(VALID_BEP20, "usdtbsc") == VALID_BEP20


def test_validate_trc20_address():
    assert validate_payout_address(VALID_TRC20, "usdttrc20") == VALID_TRC20


def test_rejects_empty_address():
    with pytest.raises(ValueError, match="required"):
        validate_payout_address("", "usdtbsc")


def test_rejects_invalid_bep20():
    with pytest.raises(ValueError):
        validate_payout_address("0xshort", "usdtbsc")


def test_payout_currency_options_cover_networks():
    assert set(PAYOUT_CURRENCY_OPTIONS) == {"usdtbsc", "usdterc20", "usdttrc20"}
