"""Fail-closed rules for the dormant club and digital-marketplace domains.

The legacy routers are deliberately not registered: neither domain has a
durable link from its membership/purchase row to the canonical payment and
ledger records. These helpers define the invariants an eventual integration
must use without introducing another wallet or accounting system.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.models.clubs import ClubStatus, MembershipStatus
from app.services.financial_integrity import (
    FinancialIntegrityError,
    money,
    normalize_fiat_currency,
    positive_money,
    validate_client_purchase_terms,
)


class ClubMarketplaceIntegrityError(FinancialIntegrityError):
    """Raised when a club or marketplace invariant would be violated."""


VALID_MEMBERSHIP_TRANSITIONS = {
    MembershipStatus.ACTIVE: {
        MembershipStatus.SUSPENDED,
        MembershipStatus.EXPIRED,
        MembershipStatus.CANCELLED,
    },
    MembershipStatus.SUSPENDED: {
        MembershipStatus.ACTIVE,
        MembershipStatus.EXPIRED,
        MembershipStatus.CANCELLED,
    },
    MembershipStatus.EXPIRED: set(),
    MembershipStatus.CANCELLED: set(),
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def require_owner(*, actor_user_id: int, owner_user_id: int) -> None:
    if int(actor_user_id) != int(owner_user_id):
        raise ClubMarketplaceIntegrityError("Resource ownership is required")


def validate_membership_transition(
    current: MembershipStatus, target: MembershipStatus
) -> None:
    if target == current:
        return
    if target not in VALID_MEMBERSHIP_TRANSITIONS.get(current, set()):
        raise ClubMarketplaceIntegrityError(
            f"Invalid membership transition: {current.value} -> {target.value}"
        )


def validate_authoritative_charge(
    *,
    submitted_amount: Any,
    submitted_currency: Any,
    server_amount: Any,
    server_currency: Any,
) -> tuple[Decimal, str]:
    """Validate client display terms against an authoritative server record."""
    try:
        expected_amount = positive_money(server_amount)
        expected_currency = normalize_fiat_currency(server_currency)
        validate_client_purchase_terms(
            submitted_amount=submitted_amount,
            submitted_currency=submitted_currency,
            expected_amount=expected_amount,
            expected_currency=expected_currency,
        )
    except FinancialIntegrityError as exc:
        raise ClubMarketplaceIntegrityError(str(exc)) from exc
    return expected_amount, expected_currency


def membership_is_entitled(
    membership: Any,
    *,
    club: Any,
    authoritative_payment_confirmed: bool,
    payment_refunded: bool = False,
    at: datetime | None = None,
) -> bool:
    """Recognize access only for a paid, current membership in an active club."""
    if not authoritative_payment_confirmed or payment_refunded:
        return False
    if membership is None or club is None:
        return False
    if getattr(membership, "club_id", None) != getattr(club, "id", None):
        return False
    if getattr(membership, "status", None) != MembershipStatus.ACTIVE:
        return False
    if getattr(club, "status", None) != ClubStatus.ACTIVE:
        return False
    now = _utc(at or datetime.now(timezone.utc))
    start = getattr(membership, "start_date", None)
    end = getattr(membership, "end_date", None)
    if start is None or end is None:
        return False
    return _utc(start) <= now < _utc(end)


def marketplace_split(
    *, gross_amount: Any, server_platform_fee_rate: Any
) -> tuple[Decimal, Decimal]:
    """Derive the seller/platform split from a server-controlled fee rate."""
    gross = positive_money(gross_amount)
    rate = Decimal(str(server_platform_fee_rate))
    if not rate.is_finite() or rate < 0 or rate > 1:
        raise ClubMarketplaceIntegrityError("Invalid server platform fee rate")
    platform_fee = money(gross * rate)
    return platform_fee, money(gross - platform_fee)


def purchase_allows_download(
    purchase: Any,
    *,
    product: Any,
    authenticated_user_id: int,
    authoritative_payment_confirmed: bool,
    payment_refunded: bool = False,
) -> bool:
    """Authorize a digital download without trusting a token alone."""
    if not authoritative_payment_confirmed or payment_refunded:
        return False
    if purchase is None or product is None or not bool(getattr(product, "is_active", False)):
        return False
    if int(getattr(purchase, "buyer_id", -1)) != int(authenticated_user_id):
        return False
    if getattr(purchase, "product_id", None) != getattr(product, "id", None):
        return False
    count = int(getattr(purchase, "download_count", 0) or 0)
    maximum = int(getattr(purchase, "max_downloads", 0) or 0)
    return maximum > 0 and count < maximum


def review_is_allowed(
    *, buyer_user_id: int, seller_user_id: int, has_confirmed_purchase: bool
) -> bool:
    return int(buyer_user_id) != int(seller_user_id) and bool(has_confirmed_purchase)
