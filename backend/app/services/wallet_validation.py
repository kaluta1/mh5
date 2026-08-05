"""Payout wallet address validation per crypto network."""
from __future__ import annotations

import re
from typing import Optional

PAYOUT_CURRENCY_OPTIONS: dict[str, dict[str, str]] = {
    "usdtbsc": {
        "label": "USDT BSC (BEP20)",
        "network": "BEP20",
        "hint": "Address must start with 0x and be 42 characters.",
    },
    "usdterc20": {
        "label": "USDT Ethereum (ERC20)",
        "network": "ERC20",
        "hint": "Address must start with 0x and be 42 characters.",
    },
    "usdttrc20": {
        "label": "USDT Tron (TRC20)",
        "network": "TRC20",
        "hint": "Address must start with T and be 34 characters.",
    },
}

BEP20_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
TRC20_PATTERN = re.compile(r"^T[a-zA-Z0-9]{33}$")


def normalize_payout_currency(code: Optional[str]) -> str:
    raw = (code or "usdtbsc").strip().lower()
    aliases = {
        "usdtbep20": "usdtbsc",
        "usdtbep": "usdtbsc",
        "usdt_eth": "usdterc20",
        "usdt_trx": "usdttrc20",
    }
    return aliases.get(raw, raw if raw in PAYOUT_CURRENCY_OPTIONS else "usdtbsc")


def validate_payout_address(address: str, currency: Optional[str] = None) -> str:
    """Return trimmed address or raise ValueError."""
    trimmed = (address or "").strip()
    if not trimmed:
        raise ValueError("Wallet address is required.")

    cur = normalize_payout_currency(currency)
    if cur in ("usdtbsc", "usdterc20"):
        if not BEP20_PATTERN.match(trimmed):
            raise ValueError(PAYOUT_CURRENCY_OPTIONS[cur]["hint"])
    elif cur == "usdttrc20":
        if not TRC20_PATTERN.match(trimmed):
            raise ValueError(PAYOUT_CURRENCY_OPTIONS[cur]["hint"])
    else:
        if not BEP20_PATTERN.match(trimmed):
            raise ValueError("Unsupported payout currency or invalid address format.")

    return trimmed
