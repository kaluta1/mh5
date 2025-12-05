from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Numeric, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base


class ClubStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class MembershipType(str, enum.Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"


class AdminPermission(str, enum.Enum):
    CONTENT_MANAGEMENT = "content_management"
    MEMBER_MANAGEMENT = "member_management"
    FINANCIAL_MANAGEMENT = "financial_management"
    SETTINGS_MANAGEMENT = "settings_management"


class FanClub(Base):
    __tablename__ = "fan_clubs"
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Tarification
    premium_fee: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    annual_discount_percentage: Mapped[float] = mapped_column(Numeric(5, 2), default=20.00)  # 20% par défaut
    
    # Configuration
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    max_members: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Multi-signature pour les admins
    multisig_threshold: Mapped[int] = mapped_column(Integer, default=1)  # Nombre minimum d'admins requis
    
    status: Mapped[ClubStatus] = mapped_column(SQLEnum(ClubStatus), default=ClubStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])
    admins: Mapped[List["ClubAdmin"]] = relationship("ClubAdmin", back_populates="club")
    memberships: Mapped[List["ClubMembership"]] = relationship("ClubMembership", back_populates="club")
    content: Mapped[List["ClubContent"]] = relationship("ClubContent", back_populates="club")
    wallet: Mapped[Optional["ClubWallet"]] = relationship("ClubWallet", back_populates="club", uselist=False)


class ClubAdmin(Base):
    __tablename__ = "club_admins"
    club_id: Mapped[int] = mapped_column(Integer, ForeignKey("fan_clubs.id"), nullable=False)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    permissions: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array des permissions
    can_approve_transactions: Mapped[bool] = mapped_column(Boolean, default=False)
    
    appointed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    club: Mapped["FanClub"] = relationship("FanClub", back_populates="admins")
    admin: Mapped["User"] = relationship("User")


class ClubMembership(Base):
    __tablename__ = "club_memberships"
    club_id: Mapped[int] = mapped_column(Integer, ForeignKey("fan_clubs.id"), nullable=False)
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    membership_type: Mapped[MembershipType] = mapped_column(SQLEnum(MembershipType), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(SQLEnum(MembershipStatus), default=MembershipStatus.ACTIVE)
    
    start_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Paiement
    amount_paid: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    fee_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # Montant payé en DSP
    payment_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)  # Montant payé en monnaie fiduciaire
    
    auto_renewal: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relations
    club: Mapped["FanClub"] = relationship("FanClub", back_populates="memberships")
    member: Mapped["User"] = relationship("User")


class ClubWallet(Base):
    __tablename__ = "club_wallets"
    club_id: Mapped[int] = mapped_column(Integer, ForeignKey("fan_clubs.id"), nullable=False, unique=True)
    
    # Soldes
    balance_cad: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    fiat_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00)
    
    # Revenus accumulés
    total_membership_fee: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    total_ad_revenue: Mapped[float] = mapped_column(Numeric(15, 2), default=0.00)
    
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    club: Mapped["FanClub"] = relationship("FanClub", back_populates="wallet")
    transactions: Mapped[List["ClubTransaction"]] = relationship("ClubTransaction", back_populates="wallet")


class ClubTransaction(Base):
    __tablename__ = "club_transactions"
    wallet_id: Mapped[int] = mapped_column(Integer, ForeignKey("club_wallets.id"), nullable=False)
    
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)  # deposit, withdrawal, fee, revenue
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)  # DSP, USD, EUR, etc.
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Multi-signature
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approvals_count: Mapped[int] = mapped_column(Integer, default=0)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    wallet: Mapped["ClubWallet"] = relationship("ClubWallet", back_populates="transactions")
    approvals: Mapped[List["TransactionApproval"]] = relationship("TransactionApproval", back_populates="transaction")


class TransactionApproval(Base):
    __tablename__ = "transaction_approvals"
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("club_transactions.id"), nullable=False)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    signature: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relations
    transaction: Mapped["ClubTransaction"] = relationship("ClubTransaction", back_populates="approvals")
    admin: Mapped["User"] = relationship("User")


class ClubContent(Base):
    __tablename__ = "club_content"
    club_id: Mapped[int] = mapped_column(Integer, ForeignKey("fan_clubs.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), default="text")  # text, image, video, file
    
    # Pour le contenu premium
    is_premium: Mapped[bool] = mapped_column(Boolean, default=True)
    preview_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Premier paragraphe pour non-membres
    
    # Engagement
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relations
    club: Mapped["FanClub"] = relationship("FanClub", back_populates="content")
    author: Mapped["User"] = relationship("User")
    comments: Mapped[List["ClubContentComment"]] = relationship("ClubContentComment", back_populates="content")


class ClubContentComment(Base):
    __tablename__ = "club_content_comments"
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("club_content.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    content: Mapped["ClubContent"] = relationship("ClubContent", back_populates="comments")
    user: Mapped["User"] = relationship("User")


class ClubContentLike(Base):
    __tablename__ = "club_content_likes"
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("club_content.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    content: Mapped["ClubContent"] = relationship("ClubContent")
    user: Mapped["User"] = relationship("User")
