from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from app.models.affiliate import CommissionType, CommissionStatus


# Affiliate Tree schemas
class AffiliateTreeBase(BaseModel):
    user_id: int
    sponsor_id: Optional[int] = None
    level: int
    referral_code: str
    is_active: bool = True


class AffiliateTreeCreate(BaseModel):
    sponsor_id: Optional[int] = None
    referral_code: str


class AffiliateTreeUpdate(BaseModel):
    is_active: Optional[bool] = None


class AffiliateTree(AffiliateTreeBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    joined_at: Optional[datetime] = None


class AffiliateTreeResponse(AffiliateTree):
    """Réponse avec informations utilisateur"""
    user_name: Optional[str] = None
    sponsor_name: Optional[str] = None
    direct_referrals_count: int = 0
    total_commissions_earned: float = 0.0


# Commission Rate schemas
class CommissionRateBase(BaseModel):
    level: int
    commission_type: CommissionType
    rate_percentage: float
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    is_active: bool = True


class CommissionRateCreate(CommissionRateBase):
    pass


class CommissionRateUpdate(BaseModel):
    rate_percentage: Optional[float] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    is_active: Optional[bool] = None


class CommissionRate(CommissionRateBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


# Affiliate Commission schemas
class AffiliateCommissionBase(BaseModel):
    user_id: int
    source_user_id: int
    product_type_id: Optional[int] = None  # Lien vers le type de produit
    commission_type: CommissionType
    level: int
    base_amount: Optional[float] = None  # Montant de base de la transaction
    commission_rate: Optional[float] = None  # Taux appliqué (si pourcentage)
    commission_amount: float  # Commission calculée
    deposit_id: Optional[int] = None  # Référence vers le dépôt d'origine
    reference_id: Optional[str] = None  # Legacy
    reference_type: Optional[str] = None  # Legacy
    status: CommissionStatus = CommissionStatus.PENDING


class AffiliateCommissionCreate(BaseModel):
    """Schéma de création simplifié"""
    user_id: int
    source_user_id: int
    product_type_id: Optional[int] = None
    commission_type: CommissionType
    level: int
    base_amount: Optional[float] = None
    commission_rate: Optional[float] = None
    commission_amount: float
    deposit_id: Optional[int] = None


class AffiliateCommissionUpdate(BaseModel):
    status: Optional[CommissionStatus] = None


class AffiliateCommission(AffiliateCommissionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    transaction_date: Optional[datetime] = None
    paid_date: Optional[datetime] = None


class AffiliateCommissionResponse(AffiliateCommission):
    """Réponse avec informations utilisateur et produit"""
    user_name: Optional[str] = None
    source_user_name: Optional[str] = None
    product_type_name: Optional[str] = None
    product_type_code: Optional[str] = None


# Referral Link schemas
class ReferralLinkBase(BaseModel):
    user_id: int
    link_code: str
    campaign_name: Optional[str] = None
    target_url: Optional[str] = None
    is_active: bool = True


class ReferralLinkCreate(BaseModel):
    campaign_name: Optional[str] = None
    target_url: Optional[str] = None


class ReferralLinkUpdate(BaseModel):
    campaign_name: Optional[str] = None
    target_url: Optional[str] = None
    is_active: Optional[bool] = None


class ReferralLink(ReferralLinkBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    total_clicks: int = 0
    total_conversions: int = 0


# Referral Click schemas
class ReferralClickBase(BaseModel):
    link_id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    converted: bool = False
    converted_user_id: Optional[int] = None


class ReferralClickCreate(ReferralClickBase):
    pass


class ReferralClick(ReferralClickBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    click_date: Optional[datetime] = None
    conversion_date: Optional[datetime] = None


# Founding Member schemas
class FoundingMemberBase(BaseModel):
    user_id: int
    founding_fee: float
    founding_membership_ratio: float
    is_active: bool = True


class FoundingMemberCreate(FoundingMemberBase):
    pass


class FoundingMemberUpdate(BaseModel):
    is_active: Optional[bool] = None


class FoundingMember(FoundingMemberBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    founding_date: Optional[datetime] = None


# Revenue Share schemas
class RevenueShareBase(BaseModel):
    user_id: int
    source_type: str
    total_revenue: float
    share_percentage: float
    share_amount: float
    period_start: datetime
    period_end: datetime
    is_paid: bool = False


class RevenueShareCreate(RevenueShareBase):
    pass


class RevenueShareUpdate(BaseModel):
    is_paid: Optional[bool] = None


class RevenueShare(RevenueShareBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    distribution_date: Optional[datetime] = None


class RevenueShareResponse(RevenueShare):
    """Réponse avec informations utilisateur"""
    user_name: Optional[str] = None


# Response schemas complexes
class LevelStats(BaseModel):
    """Statistiques par niveau d'affiliation"""
    level: int
    rate: float
    affiliates_count: int = 0
    commissions: float = 0.0


class AffiliateStats(BaseModel):
    """Statistiques d'affiliation d'un utilisateur"""
    total_affiliates: int = 0
    direct_referrals: int = 0
    indirect_referrals: int = 0
    total_commissions: float = 0.0
    pending_commissions: float = 0.0
    revenue_shared: float = 0.0
    referral_code: Optional[str] = None
    referral_link: Optional[str] = None
    clicks: int = 0
    conversions: int = 0
    conversion_rate: float = 0.0
    is_founding_member: bool = False
    level_stats: List[LevelStats] = []


class AffiliateGenealogy(BaseModel):
    """Généalogie d'affiliation sur plusieurs niveaux"""
    user_id: int
    user_name: str
    level: int
    direct_referrals: List['AffiliateGenealogy'] = []
    total_descendants: int = 0
    total_commissions: float = 0.0


class CommissionSummary(BaseModel):
    """Résumé des commissions par type et niveau"""
    commission_type: CommissionType
    level: int
    total_amount: float = 0.0
    total_transactions: int = 0
    pending_amount: float = 0.0
    paid_amount: float = 0.0
