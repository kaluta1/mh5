from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Numeric, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base


class CommissionType(str, enum.Enum):
    AD_REVENUE = "ad_revenue"
    CLUB_MEMBERSHIP = "club_membership"
    SHOP_PURCHASE = "shop_purchase"
    CONTEST_PARTICIPATION = "contest_participation"


class CommissionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


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
    
    commission_type: Mapped[CommissionType] = mapped_column(SQLEnum(CommissionType), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # Niveau d'affiliation
    
    # Montants
    min_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # Montant de base
    commission_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)  # Taux appliqué
    commission_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # Commission calculée
    
    # Références
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ID transaction source
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Type de référence
    
    status: Mapped[CommissionStatus] = mapped_column(SQLEnum(CommissionStatus), default=CommissionStatus.PENDING)
    transaction_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    source_user: Mapped["User"] = relationship("User", foreign_keys=[source_user_id])


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
