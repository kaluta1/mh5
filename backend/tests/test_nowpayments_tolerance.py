"""Underpayment tolerance and pay currency normalization for NOWPayments."""
from types import SimpleNamespace

from app.services.nowpayments_service import normalize_pay_currency, within_underpayment_tolerance


def _deposit(amount: float = 10.0):
    return SimpleNamespace(amount=amount, currency="USD")


def test_accepts_shortfall_within_half_dollar():
    deposit = _deposit(10.0)
    payload = {
        "payment_status": "partially_paid",
        "price_amount": 10.0,
        "price_currency": "usd",
        "pay_amount": 10.0,
        "actually_paid": 9.7,
    }
    assert within_underpayment_tolerance(deposit, payload) is True


def test_rejects_shortfall_over_half_dollar():
    deposit = _deposit(10.0)
    payload = {
        "payment_status": "partially_paid",
        "price_amount": 10.0,
        "pay_amount": 10.0,
        "actually_paid": 9.4,
    }
    assert within_underpayment_tolerance(deposit, payload) is False


def test_accepts_overpayment():
    deposit = _deposit(10.0)
    payload = {
        "payment_status": "partially_paid",
        "price_amount": 10.0,
        "pay_amount": 10.0,
        "actually_paid": 10.5,
    }
    assert within_underpayment_tolerance(deposit, payload) is True


def test_usdtbep20_maps_to_usdtbsc():
    assert normalize_pay_currency("usdtbep20") == "usdtbsc"
    assert normalize_pay_currency("USDT-BSC") == "usdtbsc"
