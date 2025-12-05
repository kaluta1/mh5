from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Numeric, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base


class AdCampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AdFormat(str, enum.Enum):
    IN_FEED = "in_feed"
    NATIVE_VIDEO = "native_video"
    PROMOTED_TRENDING = "promoted_trending"
    INTERACTIVE = "interactive"
    RECOMMENDED_CONTENT = "recommended_content"
    SPONSORED_POST = "sponsored_post"


class CostModel(str, enum.Enum):
    CPC = "cpc"  # Cost Per Click
    CPM = "cpm"  # Cost Per Mille (1000 impressions)
    CPA = "cpa"  # Cost Per Action


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"
    advertiser_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Budget et coûts
    remaining_budget: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    daily_budget: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    spent_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    
    cost_model: Mapped[CostModel] = mapped_column(SQLEnum(CostModel), nullable=False)
    budget_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)  # Montant d'enchère
    
    # Ciblage
    targeting_criteria: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    geographic_targeting: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    demographic_targeting: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    status: Mapped[AdCampaignStatus] = mapped_column(SQLEnum(AdCampaignStatus), default=AdCampaignStatus.DRAFT)
    
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    advertiser: Mapped["User"] = relationship("User")
    creatives: Mapped[List["AdCreative"]] = relationship("AdCreative", back_populates="campaign")
    impressions: Mapped[List["AdImpression"]] = relationship("AdImpression", back_populates="campaign")


class AdCreative(Base):
    __tablename__ = "ad_creatives"
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_campaigns.id"), nullable=False)
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ad_format: Mapped[AdFormat] = mapped_column(SQLEnum(AdFormat), nullable=False)
    
    # Contenu créatif
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Image/Vidéo
    call_to_action: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    landing_url: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Métadonnées
    dimensions: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # ex: "1200x628"
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Pour vidéos (secondes)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    campaign: Mapped["AdCampaign"] = relationship("AdCampaign", back_populates="creatives")


class AdPlacement(Base):
    __tablename__ = "ad_placements"
    
    page_type: Mapped[str] = mapped_column(String(50), nullable=False)  # contest, profile, home, etc.
    position: Mapped[str] = mapped_column(String(50), nullable=False)  # header, sidebar, in_feed, etc.
    
    # Critères de ciblage pour ce placement
    targeting_criteria: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Tarification
    base_cpm: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdImpression(Base):
    __tablename__ = "ad_impressions"
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_campaigns.id"), nullable=False)
    creative_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_creatives.id"), nullable=False)
    placement_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_placements.id"), nullable=False)
    
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Contexte de l'impression
    page_url: Mapped[str] = mapped_column(String(500), nullable=False)
    page_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Données techniques
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Coût de l'impression
    cost: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    campaign: Mapped["AdCampaign"] = relationship("AdCampaign", back_populates="impressions")
    creative: Mapped["AdCreative"] = relationship("AdCreative")
    placement: Mapped["AdPlacement"] = relationship("AdPlacement")
    user: Mapped[Optional["User"]] = relationship("User")
    click: Mapped[Optional["AdClick"]] = relationship("AdClick", back_populates="impression", uselist=False)


class AdClick(Base):
    __tablename__ = "ad_clicks"
    impression_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_impressions.id"), nullable=False, unique=True)
    
    # Coût du clic
    cost: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Suivi de conversion
    conversion_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_per_impression: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    
    # Relations
    impression: Mapped["AdImpression"] = relationship("AdImpression", back_populates="click")


class AdRevenueShare(Base):
    __tablename__ = "ad_revenue_shares"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Source des revenus
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # contest_page, profile_page, etc.
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # ID du concours, profil, etc.
    
    # Revenus générés
    total_revenue: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    
    # Distribution (selon les règles: 40% participant, 10% sponsor direct, 1% x 10 niveaux)
    participant_share: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # 40%
    direct_sponsor_share: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # 10%
    affiliate_share: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # 10% total (1% x 10)
    platform_share: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # Reste
    
    # Période
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    distributed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User")


class AdBudgetTransaction(Base):
    __tablename__ = "ad_budget_transactions"
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_campaigns.id"), nullable=False)
    
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)  # deposit, spend, refund
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Solde avant et après
    balance_before: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    campaign: Mapped["AdCampaign"] = relationship("AdCampaign")


class AdPerformanceMetrics(Base):
    __tablename__ = "ad_performance_metrics"
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("ad_campaigns.id"), nullable=False)
    creative_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ad_creatives.id"), nullable=True)
    
    # Métriques de performance
    total_impressions: Mapped[int] = mapped_column(Integer, default=0)
    total_clicks: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    
    # Coûts
    total_spent: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    cost_per_click: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    avg_cpm: Mapped[Optional[float]] = mapped_column(Numeric(8, 4), nullable=True)
    
    # Taux calculés
    ctr: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)  # Click Through Rate
    conversion_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    
    # Période des métriques
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    campaign: Mapped["AdCampaign"] = relationship("AdCampaign")
    creative: Mapped[Optional["AdCreative"]] = relationship("AdCreative")
