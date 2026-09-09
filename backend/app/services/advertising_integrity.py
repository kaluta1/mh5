"""Fail-closed rules shared by native-ad creation, serving, and tracking.

The internal native-ad router is intentionally not enabled until its payment
link is durable.  Keeping these rules outside an endpoint prevents a future
router activation from reintroducing client-controlled pricing or unsafe URLs.
"""
from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from app.models.advertising import AdCampaignStatus, CostModel
from app.services.financial_integrity import money


class AdvertisingIntegrityError(ValueError):
    pass


TERMINAL_CAMPAIGN_STATUSES = {
    AdCampaignStatus.COMPLETED,
    AdCampaignStatus.CANCELLED,
    AdCampaignStatus.REJECTED,
    AdCampaignStatus.REMOVED,
}

VALID_TRANSITIONS = {
    AdCampaignStatus.DRAFT: {AdCampaignStatus.PENDING_APPROVAL, AdCampaignStatus.CANCELLED},
    AdCampaignStatus.PENDING_APPROVAL: {
        AdCampaignStatus.ACTIVE,
        AdCampaignStatus.REJECTED,
        AdCampaignStatus.CANCELLED,
    },
    AdCampaignStatus.ACTIVE: {
        AdCampaignStatus.PAUSED,
        AdCampaignStatus.COMPLETED,
        AdCampaignStatus.CANCELLED,
        AdCampaignStatus.REMOVED,
    },
    AdCampaignStatus.PAUSED: {
        AdCampaignStatus.ACTIVE,
        AdCampaignStatus.COMPLETED,
        AdCampaignStatus.CANCELLED,
        AdCampaignStatus.REMOVED,
    },
    AdCampaignStatus.COMPLETED: set(),
    AdCampaignStatus.CANCELLED: set(),
    AdCampaignStatus.REJECTED: set(),
    AdCampaignStatus.REMOVED: set(),
}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def validate_schedule(start_at: datetime, end_at: datetime | None) -> None:
    if end_at is not None and _aware_utc(start_at) >= _aware_utc(end_at):
        raise AdvertisingIntegrityError("Campaign start must be before campaign end")


def validate_transition(current: AdCampaignStatus, target: AdCampaignStatus) -> None:
    if target == current:
        return
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise AdvertisingIntegrityError(f"Invalid campaign transition: {current.value} -> {target.value}")


def normalize_destination_url(value: str, blocked_domains: Iterable[str] = ()) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 500:
        raise AdvertisingIntegrityError("Destination URL is missing or too long")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise AdvertisingIntegrityError("Destination URL is malformed") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise AdvertisingIntegrityError("Destination URL must use HTTP or HTTPS")
    if parsed.username or parsed.password:
        raise AdvertisingIntegrityError("Destination URL must not contain credentials")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise AdvertisingIntegrityError("Local destination URLs are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is None and "." not in host:
        raise AdvertisingIntegrityError("Internal-only destination hosts are not allowed")
    if address and not address.is_global:
        raise AdvertisingIntegrityError("Internal destination addresses are not allowed")
    blocked = {str(domain).strip().rstrip(".").lower() for domain in blocked_domains}
    if any(host == domain or host.endswith(f".{domain}") for domain in blocked if domain):
        raise AdvertisingIntegrityError("Destination domain is blocked")
    rendered_host = f"[{host}]" if address and address.version == 6 else host
    netloc = rendered_host if port is None else f"{rendered_host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, parsed.fragment))


def server_event_cost(cost_model: CostModel, *, server_rate: Decimal, units: int = 1) -> Decimal:
    if units <= 0:
        raise AdvertisingIntegrityError("Billable units must be positive")
    rate = money(server_rate)
    if rate <= 0:
        raise AdvertisingIntegrityError("Server pricing is unavailable")
    if cost_model == CostModel.CPC:
        return money(rate * units)
    if cost_model == CostModel.CPM:
        return money(rate * Decimal(units) / Decimal("1000"))
    raise AdvertisingIntegrityError("This cost model is not event-billable")


def campaign_is_servable(
    *,
    status: AdCampaignStatus,
    start_at: datetime,
    end_at: datetime | None,
    remaining_budget: Decimal,
    creative_active: bool,
    creative_approved: bool,
    now: datetime | None = None,
) -> bool:
    instant = _aware_utc(now or datetime.now(timezone.utc))
    if status != AdCampaignStatus.ACTIVE or not creative_active or not creative_approved:
        return False
    if instant < _aware_utc(start_at) or (end_at is not None and instant >= _aware_utc(end_at)):
        return False
    return money(remaining_budget) > 0
