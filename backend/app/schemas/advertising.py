"""Safe DTOs for the dormant native-ad domain."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.advertising import AdCampaignStatus, AdFormat, CostModel
from app.services.advertising_integrity import normalize_destination_url, validate_schedule


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AdCampaignBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    budget_amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    daily_budget: Optional[Decimal] = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    cost_model: CostModel
    targeting_criteria: Optional[dict[str, Any]] = None
    geographic_targeting: Optional[dict[str, Any]] = None
    demographic_targeting: Optional[dict[str, Any]] = None
    start_date: datetime
    end_date: Optional[datetime] = None

    @model_validator(mode="after")
    def valid_terms(self):
        validate_schedule(self.start_date, self.end_date)
        if self.daily_budget is not None and self.daily_budget > self.budget_amount:
            raise ValueError("Daily budget cannot exceed total budget")
        return self


class AdCampaignCreate(AdCampaignBase):
    pass


class AdCampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    targeting_criteria: Optional[dict[str, Any]] = None
    geographic_targeting: Optional[dict[str, Any]] = None
    demographic_targeting: Optional[dict[str, Any]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class AdCampaign(AdCampaignBase, ORMModel):
    id: int
    advertiser_id: int
    remaining_budget: Decimal
    spent_amount: Decimal = Decimal("0.00")
    status: AdCampaignStatus = AdCampaignStatus.DRAFT
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdCampaignWithAdvertiser(AdCampaign):
    advertiser_name: Optional[str] = None
    advertiser_email: Optional[str] = None


class AdCreativeBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    ad_format: AdFormat
    title: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    content_url: Optional[str] = Field(default=None, max_length=500)
    call_to_action: Optional[str] = Field(default=None, max_length=50)
    landing_url: str = Field(max_length=500)

    @field_validator("landing_url")
    @classmethod
    def safe_destination(cls, value: str) -> str:
        return normalize_destination_url(value)


class AdCreativeCreate(AdCreativeBase):
    pass


class AdCreativeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    content_url: Optional[str] = Field(default=None, max_length=500)
    call_to_action: Optional[str] = Field(default=None, max_length=50)
    landing_url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None

    @field_validator("landing_url")
    @classmethod
    def safe_destination(cls, value: Optional[str]) -> Optional[str]:
        return normalize_destination_url(value) if value is not None else None


class AdCreative(AdCreativeBase, ORMModel):
    id: int
    campaign_id: int
    is_active: bool
    created_at: Optional[datetime] = None


class AdPlacementBase(BaseModel):
    page_type: str = Field(min_length=1, max_length=50)
    position: str = Field(min_length=1, max_length=50)
    targeting_criteria: Optional[dict[str, Any]] = None
    base_cpm: Decimal = Field(ge=0)
    base_price: Decimal = Field(ge=0)
    is_active: bool = True


class AdPlacementCreate(AdPlacementBase):
    pass


class AdPlacementUpdate(BaseModel):
    targeting_criteria: Optional[dict[str, Any]] = None
    base_cpm: Optional[Decimal] = Field(default=None, ge=0)
    base_price: Optional[Decimal] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class AdPlacement(AdPlacementBase, ORMModel):
    id: int
    created_at: Optional[datetime] = None


class AdImpression(ORMModel):
    id: int
    campaign_id: int
    creative_id: int
    placement_id: int
    user_id: Optional[int] = None
    page_url: str
    page_type: str
    cost: Decimal
    timestamp: Optional[datetime] = None


class AdClick(ORMModel):
    id: int
    impression_id: int
    cost: Decimal
    conversion_tracked: bool = False
    timestamp: Optional[datetime] = None


class AdRevenueShare(ORMModel):
    id: int
    user_id: int
    source_type: str
    source_id: Optional[int] = None
    total_revenue: Decimal
    participant_share: Decimal
    direct_sponsor_share: Decimal
    affiliate_share: Decimal
    platform_share: Decimal
    period_start: datetime
    period_end: datetime
    calculated_at: Optional[datetime] = None
    distributed_at: Optional[datetime] = None


class AdRevenueShareWithUser(AdRevenueShare):
    user_name: Optional[str] = None
    user_email: Optional[str] = None


class AdBudgetTransaction(ORMModel):
    id: int
    campaign_id: Optional[int] = None
    transaction_type: str
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    description: Optional[str] = None
    reference_id: Optional[str] = None
    created_at: Optional[datetime] = None


class AdPerformanceMetrics(ORMModel):
    id: int
    campaign_id: int
    creative_id: Optional[int] = None
    total_impressions: int = 0
    total_clicks: int = 0
    conversions: int = 0
    total_spent: Decimal = Decimal("0.00")
    cost_per_click: Optional[Decimal] = None
    avg_cpm: Optional[Decimal] = None
    ctr: Optional[Decimal] = None
    conversion_rate: Optional[Decimal] = None
    date: datetime
    updated_at: Optional[datetime] = None


class CampaignDashboard(BaseModel):
    campaign: AdCampaign
    total_impressions: int = 0
    total_clicks: int = 0
    total_conversions: int = 0
    total_spent: Decimal = Decimal("0.00")
    average_ctr: Decimal = Decimal("0")
    daily_metrics: list[AdPerformanceMetrics] = Field(default_factory=list)


class AdvertiserStats(BaseModel):
    total_campaigns: int = 0
    active_campaigns: int = 0
    total_spent: Decimal = Decimal("0.00")
    total_impressions: int = 0
    total_clicks: int = 0
    average_ctr: Decimal = Decimal("0")
    top_performing_campaigns: list[AdCampaign] = Field(default_factory=list)


class NativeAdResponse(BaseModel):
    creative_id: int
    campaign_id: int
    placement_id: int
    creative_type: str
    creative_content: Optional[str] = None
    creative_url: Optional[str] = None
    call_to_action: Optional[str] = None
    landing_url: str
    tracking_token: str


class AdRevenueReport(BaseModel):
    period_start: datetime
    period_end: datetime
    total_revenue: Decimal = Decimal("0.00")
    participant_revenue: Decimal = Decimal("0.00")
    affiliate_revenue: Decimal = Decimal("0.00")
    platform_revenue: Decimal = Decimal("0.00")
    top_earning_users: list[dict[str, Any]] = Field(default_factory=list)
    revenue_by_source: list[dict[str, Any]] = Field(default_factory=list)
