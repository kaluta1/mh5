"""Financial boundary helpers shared by payment, commission, and ledger flows."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


MONEY_QUANTUM = Decimal("0.01")
SUPPORTED_FIAT_CURRENCIES = frozenset({"USD"})


class FinancialIntegrityError(ValueError):
    """Raised when an input would violate a financial invariant."""


def money(value: Any) -> Decimal:
    """Return a finite, cent-rounded Decimal without using binary-float arithmetic."""
    try:
        amount = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FinancialIntegrityError("Invalid monetary amount") from exc
    if not amount.is_finite():
        raise FinancialIntegrityError("Invalid monetary amount")
    return amount


def positive_money(value: Any) -> Decimal:
    amount = money(value)
    if amount <= 0:
        raise FinancialIntegrityError("Amount must be positive")
    return amount


def normalize_fiat_currency(value: Any) -> str:
    currency = str(value or "").strip().upper()
    if currency not in SUPPORTED_FIAT_CURRENCIES:
        raise FinancialIntegrityError(f"Unsupported price currency: {currency or 'missing'}")
    return currency


def authoritative_product_terms(product: Any) -> tuple[Decimal, str]:
    """Resolve immutable checkout terms from the server-side product row."""
    if product is None or not bool(getattr(product, "is_active", False)):
        raise FinancialIntegrityError("Product is unavailable")
    return positive_money(getattr(product, "price", None)), normalize_fiat_currency(
        getattr(product, "currency", None) or "USD"
    )


def validate_client_purchase_terms(
    *,
    submitted_amount: Any,
    submitted_currency: Any,
    expected_amount: Decimal,
    expected_currency: str,
) -> None:
    """Reject tampering instead of silently accepting client pricing."""
    if money(submitted_amount) != expected_amount:
        raise FinancialIntegrityError("Submitted amount does not match the server product price")
    if normalize_fiat_currency(submitted_currency) != expected_currency:
        raise FinancialIntegrityError("Submitted currency does not match the server product currency")


def validate_provider_payment_identity(deposit: Any, payload: dict[str, Any]) -> None:
    """Bind a signed/polled provider event to the local order and authoritative price."""
    order_id = str(payload.get("order_id") or "").strip()
    if order_id and order_id != str(getattr(deposit, "order_id", "") or ""):
        raise FinancialIntegrityError("Provider order_id does not match the deposit")

    payment_id = str(payload.get("payment_id") or "").strip()
    local_payment_id = str(getattr(deposit, "external_payment_id", "") or "").strip()
    if payment_id and local_payment_id and payment_id != local_payment_id:
        raise FinancialIntegrityError("Provider payment_id does not match the deposit")

    if payload.get("price_amount") is not None:
        if money(payload["price_amount"]) != money(getattr(deposit, "amount", None)):
            raise FinancialIntegrityError("Provider price does not match the authoritative deposit amount")

    provider_currency = payload.get("price_currency")
    if provider_currency:
        if normalize_fiat_currency(provider_currency) != normalize_fiat_currency(
            getattr(deposit, "currency", None) or "USD"
        ):
            raise FinancialIntegrityError("Provider currency does not match the deposit")

