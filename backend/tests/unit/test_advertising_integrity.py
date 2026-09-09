from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.advertising import AdCampaignStatus, AdFormat, CostModel
from app.schemas.advertising import AdCampaignCreate, AdCreativeCreate
from app.services.advertising_integrity import (
    AdvertisingIntegrityError,
    campaign_is_servable,
    normalize_destination_url,
    server_event_cost,
    validate_schedule,
    validate_transition,
)


def test_destination_url_allows_public_http_and_https():
    assert normalize_destination_url("https://Example.com/path?q=1") == "https://example.com/path?q=1"
    assert normalize_destination_url("http://example.com") == "http://example.com/"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,bad",
        "file:///etc/passwd",
        "http://localhost/a",
        "http://127.0.0.1/a",
        "http://10.0.0.1/a",
        "http://169.254.169.254/latest/meta-data",
        "https://intranet/path",
        "https://service.internal/path",
        "https://user:pass@example.com",
        "//example.com/no-scheme",
    ],
)
def test_destination_url_rejects_unsafe_targets(url):
    with pytest.raises(AdvertisingIntegrityError):
        normalize_destination_url(url)


def test_destination_url_enforces_domain_blocklist():
    with pytest.raises(AdvertisingIntegrityError):
        normalize_destination_url("https://ads.bad.example/path", {"bad.example"})


def test_schedule_and_decimal_budget_validation():
    start = datetime.now(timezone.utc)
    validate_schedule(start, start + timedelta(days=1))
    with pytest.raises(AdvertisingIntegrityError):
        validate_schedule(start, start)
    with pytest.raises(ValidationError):
        AdCampaignCreate(
            name="Campaign",
            budget_amount=Decimal("5.00"),
            daily_budget=Decimal("6.00"),
            cost_model=CostModel.CPC,
            start_date=start,
            end_date=start + timedelta(days=1),
        )


def test_creative_dto_rejects_unsafe_destination_and_has_no_owner_or_cost_input():
    with pytest.raises(ValidationError):
        AdCreativeCreate(
            name="Creative",
            ad_format=AdFormat.IN_FEED,
            landing_url="javascript:alert(1)",
        )
    assert "campaign_id" not in AdCreativeCreate.model_fields
    assert "cost" not in AdCreativeCreate.model_fields


def test_campaign_create_cannot_set_owner_status_spend_or_remaining_balance():
    fields = AdCampaignCreate.model_fields
    assert "advertiser_id" not in fields
    assert "status" not in fields
    assert "spent_amount" not in fields
    assert "remaining_budget" not in fields


def test_unfinished_native_router_stays_fail_closed_while_annualads_is_reachable(app):
    routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    assert ("POST", "/api/v1/advertising/campaigns") not in routes
    assert ("POST", "/api/v1/webhooks/sponsor-payment") in routes
    assert ("GET", "/api/v1/sponsor-embed/sso-token") in routes


def test_campaign_lifecycle_is_deterministic_and_terminal():
    validate_transition(AdCampaignStatus.DRAFT, AdCampaignStatus.PENDING_APPROVAL)
    validate_transition(AdCampaignStatus.PENDING_APPROVAL, AdCampaignStatus.ACTIVE)
    validate_transition(AdCampaignStatus.ACTIVE, AdCampaignStatus.PAUSED)
    validate_transition(AdCampaignStatus.PAUSED, AdCampaignStatus.ACTIVE)
    validate_transition(AdCampaignStatus.ACTIVE, AdCampaignStatus.COMPLETED)
    with pytest.raises(AdvertisingIntegrityError):
        validate_transition(AdCampaignStatus.REJECTED, AdCampaignStatus.ACTIVE)
    with pytest.raises(AdvertisingIntegrityError):
        validate_transition(AdCampaignStatus.COMPLETED, AdCampaignStatus.ACTIVE)


def test_server_rates_drive_cpc_and_cpm_spend_without_float():
    assert server_event_cost(CostModel.CPC, server_rate=Decimal("0.02")) == Decimal("0.02")
    assert server_event_cost(CostModel.CPM, server_rate=Decimal("0.25"), units=1000) == Decimal("0.25")
    with pytest.raises(AdvertisingIntegrityError):
        server_event_cost(CostModel.CPA, server_rate=Decimal("1.00"))


def test_ad_serving_requires_active_approved_scheduled_funded_campaign():
    now = datetime.now(timezone.utc)
    base = dict(
        status=AdCampaignStatus.ACTIVE,
        start_at=now - timedelta(minutes=1),
        end_at=now + timedelta(minutes=1),
        remaining_budget=Decimal("1.00"),
        creative_active=True,
        creative_approved=True,
        now=now,
    )
    assert campaign_is_servable(**base)
    assert not campaign_is_servable(**{**base, "status": AdCampaignStatus.PAUSED})
    assert not campaign_is_servable(**{**base, "creative_approved": False})
    assert not campaign_is_servable(**{**base, "remaining_budget": Decimal("0")})
    assert not campaign_is_servable(**{**base, "end_at": now})
