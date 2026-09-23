"""Retirement gate for the old MyHigh5 business model.

The old model = 10-level affiliate commissions + the Founding Members
program (enrollment, 10% pool accrual on 2104, month-end allocation to 2105,
Founding Membership Points). It is retired for all FUTURE activity.

This module only gates writers. Historical rows (commissions, deposits,
journals, FMP ledger, founding snapshots) are never modified or hidden.
"""
from __future__ import annotations

from decimal import Decimal

from app.core.config import settings

# The $100 Founding products. ``efm_membership`` is deliberately NOT here: it is
# a $9.99 / 30-day advanced-features subscription, not a Founding product.
LEGACY_FOUNDING_PRODUCT_CODES = frozenset({"founding_membership", "mfm_membership"})

LEGACY_FOUNDING_POOL_RATE = Decimal("0.10")

RETIRED_MESSAGE = (
    "The legacy MyHigh5 business model (10-level affiliate commissions and the "
    "Founding Members program) has been retired. Historical records remain available."
)


class LegacyBusinessModelRetiredError(RuntimeError):
    """Raised when a retired old-model writer is invoked."""


def legacy_business_model_enabled() -> bool:
    return bool(getattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", False))


def is_legacy_founding_product(product_code: str | None) -> bool:
    return (product_code or "").strip().lower() in LEGACY_FOUNDING_PRODUCT_CODES


def founding_pool_rate() -> Decimal:
    """Share of gross accrued to the Founding pool (2104) for new postings."""
    return LEGACY_FOUNDING_POOL_RATE if legacy_business_model_enabled() else Decimal("0")


def require_legacy_business_model(action: str) -> None:
    if not legacy_business_model_enabled():
        raise LegacyBusinessModelRetiredError(f"{action}: {RETIRED_MESSAGE}")


def without_zero_lines(lines: list[dict]) -> list[dict]:
    """Drop journal lines whose debit and credit are both zero (e.g. a retired 2104 accrual)."""
    return [
        line
        for line in lines
        if Decimal(str(line.get("debit") or 0)) != 0 or Decimal(str(line.get("credit") or 0)) != 0
    ]
