from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from app.models.advertising import AdCampaignStatus, CostModel


# Ad Campaign schemas
class AdCampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    budget_amount: float
    daily_budget: Optional[float] = None
    cost_model: CostModel
    bid_amount: float
    targeting_criteria: Optional[dict] = None
    geographic_targeting: Optional[dict] = None
    demographic_targeting: Optional[dict] = None
    start_date: datetime
    end_date: Optional[datetime] = None


class AdCampaignCreate(AdCampaignBase):
    pass


class AdCampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    budget_amount: Optional[float] = None
    daily_budget: Optional[float] = None
    bid_amount: Optional[float] = None
    targeting_criteria: Optional[dict] = None
    geographic_targeting: Optional[dict] = None
    demographic_targeting: Optional[dict] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[AdCampaignStatus] = None


class AdCampaign(AdCampaignBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    advertiser_id: int
    remaining_budget: float
    spent_amount: float = 0.0
    status: AdCampaignStatus = AdCampaignStatus.DRAFT
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdCampaignWithAdvertiser(AdCampaign):
    """Campagne avec informations annonceur"""
    advertiser_name: Optional[str] = None
    advertiser_email: Optional[str] = None


# Ad Creative schemas
class AdCreativeBase(BaseModel):
    campaign_id: int
    creative_name: str
    creative_type: str  # banner, video, native, text
    creative_url: Optional[str] = None
    creative_content: Optional[str] = None
    call_to_action: Optional[str] = None
    landing_url: str
    is_active: bool = True


class AdCreativeCreate(AdCreativeBase):
    pass


class AdCreativeUpdate(BaseModel):
    creative_name: Optional[str] = None
    creative_url: Optional[str] = None
    creative_content: Optional[str] = None
    call_to_action: Optional[str] = None
    landing_url: Optional[str] = None
    is_active: Optional[bool] = None


class AdCreative(AdCreativeBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    total_impressions: int = 0
    total_clicks: int = 0
    ctr: float = 0.0


# Ad Placement schemas
class AdPlacementBase(BaseModel):
    page_type: str
    position: str
    targeting_criteria: Optional[dict] = None
    base_cpm: float
    base_price: float
    premium_multiplier: float = 1.0
    is_active: bool = True


class AdPlacementCreate(AdPlacementBase):
    pass


class AdPlacementUpdate(BaseModel):
    targeting_criteria: Optional[dict] = None
    base_cpm: Optional[float] = None
    base_price: Optional[float] = None
    premium_multiplier: Optional[float] = None
    is_active: Optional[bool] = None


class AdPlacement(AdPlacementBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


# Ad Impression schemas
class AdImpressionBase(BaseModel):
    campaign_id: int
    creative_id: int
    placement_id: int
    user_id: Optional[int] = None
    page_url: str
    page_type: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    cost: float


class AdImpressionCreate(AdImpressionBase):
    pass


class AdImpression(AdImpressionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    timestamp: Optional[datetime] = None


# Ad Click schemas
class AdClickBase(BaseModel):
    impression_id: int
    cost: float
    conversion_tracked: bool = False
    conversion_value: Optional[float] = None


class AdClickCreate(AdClickBase):
    pass


class AdClick(AdClickBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    timestamp: Optional[datetime] = None


# Ad Revenue Share schemas
class AdRevenueShareBase(BaseModel):
    user_id: int
    source_type: str
    source_id: Optional[int] = None
    total_revenue: float
    participant_share: float
    direct_sponsor_share: float
    affiliate_share: float
    platform_share: float
    period_start: datetime
    period_end: datetime


class AdRevenueShareCreate(AdRevenueShareBase):
    pass


class AdRevenueShareUpdate(BaseModel):
    distributed_at: Optional[datetime] = None


class AdRevenueShare(AdRevenueShareBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    calculated_at: Optional[datetime] = None
    distributed_at: Optional[datetime] = None


class AdRevenueShareWithUser(AdRevenueShare):
    """Partage de revenus avec informations utilisateur"""
    user_name: Optional[str] = None
    user_email: Optional[str] = None


# Ad Budget Transaction schemas
class AdBudgetTransactionBase(BaseModel):
    campaign_id: int
    transaction_type: str  # deposit, spend, refund
    amount: float
    balance_before: float
    balance_after: float
    description: Optional[str] = None
    reference_id: Optional[str] = None


class AdBudgetTransactionCreate(AdBudgetTransactionBase):
    pass


class AdBudgetTransaction(AdBudgetTransactionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


# Ad Performance Metrics schemas
class AdPerformanceMetricsBase(BaseModel):
    campaign_id: int
    creative_id: Optional[int] = None
    total_impressions: int = 0
    total_clicks: int = 0
    conversions: int = 0
    total_spent: float = 0.0
    total_revenue: float = 0.0
    ctr: float = 0.0
    cpc: float = 0.0
    cpm: float = 0.0
    roi: float = 0.0
    date: datetime


class AdPerformanceMetricsCreate(AdPerformanceMetricsBase):
    pass


class AdPerformanceMetricsUpdate(BaseModel):
    total_impressions: Optional[int] = None
    total_clicks: Optional[int] = None
    conversions: Optional[int] = None
    total_spent: Optional[float] = None
    total_revenue: Optional[float] = None
    ctr: Optional[float] = None
    cpc: Optional[float] = None
    cpm: Optional[float] = None
    roi: Optional[float] = None


class AdPerformanceMetrics(AdPerformanceMetricsBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    updated_at: Optional[datetime] = None


# Response schemas complexes
class CampaignDashboard(BaseModel):
    """Tableau de bord complet d'une campagne"""
    campaign: AdCampaign
    total_impressions: int = 0
    total_clicks: int = 0
    total_conversions: int = 0
    total_spent: float = 0.0
    average_ctr: float = 0.0
    average_cpc: float = 0.0
    average_cpm: float = 0.0
    roi: float = 0.0
    daily_metrics: List[AdPerformanceMetrics] = []


class AdvertiserStats(BaseModel):
    """Statistiques globales d'un annonceur"""
    total_campaigns: int = 0
    active_campaigns: int = 0
    total_spent: float = 0.0
    total_impressions: int = 0
    total_clicks: int = 0
    average_ctr: float = 0.0
    average_roi: float = 0.0
    top_performing_campaigns: List[AdCampaign] = []


class NativeAdResponse(BaseModel):
    """Réponse pour les publicités natives"""
    creative_id: int
    campaign_id: int
    placement_id: int
    creative_type: str
    creative_content: Optional[str] = None
    creative_url: Optional[str] = None
    call_to_action: Optional[str] = None
    landing_url: str
    tracking_pixel: str


class AdRevenueReport(BaseModel):
    """Rapport de revenus publicitaires"""
    period_start: datetime
    period_end: datetime
    total_revenue: float = 0.0
    participant_revenue: float = 0.0
    affiliate_revenue: float = 0.0
    platform_revenue: float = 0.0
    top_earning_users: List[dict] = []
    revenue_by_source: List[dict] = []
