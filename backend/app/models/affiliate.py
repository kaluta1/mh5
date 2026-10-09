from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Column, Index, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Numeric, Enum as SQLEnum, text
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
    FOUNDING_MEMBERSHIP_FEE = "FOUNDING_MEMBERSHIP_FEE"    # historical: Founding Member fee (retired program)
    ANNUAL_MEMBERSHIP_FEE = "ANNUAL_MEMBERSHIP_FEE"        # annual membership fee (direct sponsor only)
    MONTHLY_REVENUE_POOL = "MONTHLY_REVENUE_POOL"          # 10% revenus nets mensuels (pool FM)
    ANNUAL_PROFIT_POOL = "ANNUAL_PROFIT_POOL"              # 20% profits annuels après taxes


class CommissionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class CashoutStatus(str, enum.Enum):
    REQUESTED = "requested"      # reserved; nothing sent anywhere yet
    PROCESSING = "processing"    # handed to the payout provider / being settled
    UNKNOWN = "unknown"          # provider outcome uncertain: never retried automatically
    COMPLETED = "completed"      # paid; commissions PAID and the journal posted
    FAILED = "failed"            # confirmed not paid; the reservation was released
    CANCELLED = "cancelled"      # withdrawn before anything was sent; reservation released


# A member has at most one cashout in these states (enforced by a partial
# unique index, uq_cashout_one_active_per_user).
ACTIVE_CASHOUT_STATUSES = ("requested", "processing", "unknown")


class CommissionRule(Base):
    __tablename__ = "commission_rules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    commission_type: Mapped[CommissionType] = mapped_column(SQLEnum(CommissionType), nullable=False)
    
    # Configuration des pourcentages
    # LEGACY table of the retired commission engine; the active program reads
    # revenue_policies (NEW_V2) and is direct referrals only. Stored rows keep
    # the historical 10-level values for audit; a NEW row defaults to no
    # indirect percentage and a single level (application-side defaults only,
    # no schema change).
    direct_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=10.0)    # Ex: 10.0 pour 10%
    indirect_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)   # historical rows: 1.0
    max_levels: Mapped[int] = mapped_column(Integer, default=1)                      # historical rows: 10
    
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
    # 1 = direct. New rows are always 1 (the program is direct referrals only);
    # 2-10 exist only on historical rows of the retired 10-level program.
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    
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
    payout_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # NEW_V2 direct-commission provenance (NULL on legacy 10-level rows).
    business_model_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    revenue_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    source_user: Mapped["User"] = relationship("User", foreign_keys=[source_user_id])
    product_type: Mapped[Optional["ProductType"]] = relationship("ProductType", back_populates="affiliate_commissions")
    deposit: Mapped[Optional["Deposit"]] = relationship("Deposit")


class AffiliateCashoutRequest(Base):
    """Audit trail for affiliate commission payouts (auto or manual)."""
    __tablename__ = "affiliate_cashout_requests"
    __table_args__ = (
        # The database itself refuses a second open cashout for a member, so two
        # workers (or a worker and a request) can never both reserve.
        Index("uq_cashout_one_active_per_user", "user_id", unique=True,
              postgresql_where=text("status IN ('requested', 'processing', 'unknown')"),
              sqlite_where=text("status IN ('requested', 'processing', 'unknown')")),
        Index("uq_cashout_payout_reference", "payout_reference", unique=True),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    gross_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    fee: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    net_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CashoutStatus.PROCESSING.value)
    payout_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="nowpayments_crypto")
    wallet_snapshot: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payout_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Dual cashout (NULL on rows written before it).
    cashout_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)      # CRYPTO / USD
    payout_currency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)     # e.g. usdtbsc
    provider_batch_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # provider's payout id
    provider_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)     # last status it reported
    failure_code: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    settlement_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Crypto: the provider's network fee estimate when the payout was sent, and
    # who bears it (COMPANY_PAYS / MEMBER_PAYS). `fee` stays the MyHigh5 fee.
    network_fee: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    network_fee_policy: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # USD: the member's payout destination details, AES-256-GCM ciphertext only.
    destination_ciphertext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class PayoutWalletChange(Base):
    """Append-only history of a member's payout destination. One row per
    accepted change; rows are never updated or deleted."""
    __tablename__ = "payout_wallet_changes"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    old_address: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    new_address: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    payable_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)   # end of the security hold
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    # How the member proved the change: EMAIL (confirmation link) or PASSWORD.
    verification_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


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
