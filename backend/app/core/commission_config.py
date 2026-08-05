"""
Single source of truth for commission rates and product pricing.

All marketing pages, API responses, and payout logic should reference this module.
"""
from __future__ import annotations

from typing import TypedDict


class ProductCommission(TypedDict):
    price_cents: int
    platform_rate_percent: float
    payout_cents: int
    currency: str


# Canonical rates: 10% direct, 1% indirect (levels 2-10) — matches DB commission_rules seed.
DIRECT_RATE = 0.10
INDIRECT_RATE = 0.01
MAX_LEVELS = 10

COMMISSION_CONFIG: dict[str, ProductCommission] = {
    "kyc": {
        "price_cents": 100,
        "platform_rate_percent": 10.0,
        "payout_cents": 90,
        "currency": "USD",
    },
    "founding_membership": {
        "price_cents": 10000,
        "platform_rate_percent": 10.0,
        "payout_cents": 9000,
        "currency": "USD",
    },
    "mfm_membership": {
        "price_cents": 10000,
        "platform_rate_percent": 10.0,
        "payout_cents": 9000,
        "currency": "USD",
    },
    "annual_membership": {
        "price_cents": 5000,
        "platform_rate_percent": 10.0,
        "payout_cents": 4500,
        "currency": "USD",
    },
}


def get_commission_display(product_code: str) -> dict[str, str | float | int]:
    cfg = COMMISSION_CONFIG.get(product_code)
    if not cfg:
        return {}
    return {
        "price": f"${cfg['price_cents'] / 100:.2f}",
        "platform_rate": f"{cfg['platform_rate_percent']:.0f}%",
        "payout": f"${cfg['payout_cents'] / 100:.2f}",
        "price_cents": cfg["price_cents"],
        "platform_rate_percent": cfg["platform_rate_percent"],
        "payout_cents": cfg["payout_cents"],
    }


def level_rate(level: int) -> float:
    """Return commission rate for affiliate level (1=direct, 2-10=indirect)."""
    if level == 1:
        return DIRECT_RATE
    if 2 <= level <= MAX_LEVELS:
        return INDIRECT_RATE
    return 0.0
