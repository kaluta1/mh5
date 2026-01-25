from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Numeric, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.payment import ProductType, Deposit


class CommissionType(str, enum.Enum):
    # Commissions d'affiliation standard
    AD_REVENUE = "AD_REVENUE"                              # Revenus publicitaires
    CLUB_MEMBERSHIP = "CLUB_MEMBERSHIP"                    # Abonnement club
    SHOP_PURCHASE = "SHOP_PURCHASE"                        # Achat boutique
    CONTEST_PARTICIPATION = "CONTEST_PARTICIPATION"        # Participation concours
    KYC_PAYMENT = "KYC_PAYMENT"                            # Paiement KYC
    EFM_MEMBERSHIP = "EFM_MEMBERSHIP"                      # Abonnement EFM
    
    # Commissions Founding Members
    FOUNDING_MEMBERSHIP_FEE = "FOUNDING_MEMBERSHIP_FEE"    # 100$ fee - 20$ direct, 2$ indirect L2-10
    ANNUAL_MEMBERSHIP_FEE = "ANNUAL_MEMBERSHIP_FEE"        # 50$/an - 10$ direct, 1$ indirect L2-10
    MONTHLY_REVENUE_POOL = "MONTHLY_REVENUE_POOL"          # 10% revenus nets mensuels (pool FM)
    ANNUAL_PROFIT_POOL = "ANNUAL_PROFIT_POOL"              # 20% profits annuels après taxes


class CommissionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class CommissionRule(Base):
    __tablename__ = "commission_rules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    commission_type: Mapped[CommissionType] = mapped_column(SQLEnum(CommissionType), nullable=False)
    
    # Configuration des pourcentages
    direct_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=10.0)    # Ex: 10.0 pour 10%
    indirect_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=1.0)   # Ex: 1.0 pour 1%
    max_levels: Mapped[int] = mapped_column(Integer, default=10)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AffiliateTree(Base):
    __tablename__ = "affiliate_tree"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    sponsor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Niveau dans l'arbre d'affiliation (1-10)
    level: Mapped[int] = mapped_column(Integer, default=1)
    
    # Chemin hiérarchique pour optimiser les requêtes
    path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    join_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    sponsor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[sponsor_id])


class CommissionRate(Base):
    __tablename__ = "commission_rates"
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10
    commission_type: Mapped[CommissionType] = mapped_column(SQLEnum(CommissionType), nullable=False)
    rate_percentage: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # Ex: 0.1000 pour 10%
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AffiliateCommission(Base):
    __tablename__ = "affiliate_commissions"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)  # Bénéficiaire
    source_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)  # Générateur
    
    # Lien vers le type de produit (nouvelle approche)
    product_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("product_types.id"), nullable=True)
    
    # Type de commission (pour rétrocompatibilité et cas spéciaux comme les pools)
    commission_type: Mapped[CommissionType] = mapped_column(SQLEnum(CommissionType), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # Niveau d'affiliation (1 = direct, 2-10 = indirect)
    
    # Montants
    base_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # Montant de base de la transaction
    commission_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)  # Taux appliqué (si pourcentage)
    commission_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # Commission calculée
    
    # Références vers la transaction d'origine
    deposit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("deposits.id"), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ID transaction source (legacy)
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Type de référence (legacy)
    
    status: Mapped[CommissionStatus] = mapped_column(SQLEnum(CommissionStatus), default=CommissionStatus.PENDING)
    transaction_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    source_user: Mapped["User"] = relationship("User", foreign_keys=[source_user_id])
    product_type: Mapped[Optional["ProductType"]] = relationship("ProductType", back_populates="affiliate_commissions")
    deposit: Mapped[Optional["Deposit"]] = relationship("Deposit")


class ReferralLink(Base):
    __tablename__ = "referral_links"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Code unique pour le lien de parrainage
    referral_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # Statistiques
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    user: Mapped["User"] = relationship("User")


class ReferralClick(Base):
    __tablename__ = "referral_clicks"
    referral_link_id: Mapped[int] = mapped_column(Integer, ForeignKey("referral_links.id"), nullable=False)
    
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    referer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    clicked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    converted: Mapped[bool] = mapped_column(Boolean, default=False)
    converted_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relations
    referral_link: Mapped["ReferralLink"] = relationship("ReferralLink")
    converted_user: Mapped[Optional["User"]] = relationship("User")


class FoundingMember(Base):
    __tablename__ = "founding_members"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Ratio de membership fondateur
    founding_membership_ratio: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    
    # Date d'adhésion comme membre fondateur
    founding_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    user: Mapped["User"] = relationship("User")


class RevenueShare(Base):
    __tablename__ = "revenue_shares"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Type de partage de revenus
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ad_revenue, founding_member, etc.
    
    # Montants
    total_revenue: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)  # Revenus totaux de la période
    share_percentage: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # Pourcentage de partage
    share_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # Montant du partage
    
    # Période
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    distribution_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relations
    user: Mapped["User"] = relationship("User")
