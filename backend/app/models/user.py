from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Boolean, String, Integer, ForeignKey, Table, Column, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.media import Media
    from app.models.contest import ContestEntry


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"
    PENDING_VERIFICATION = "pending_verification"

# Table d'association pour les permissions des rôles
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(Base):
    """Modèle pour les permissions individuelles."""
    __tablename__ = "permissions"
    
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Pour grouper les permissions (user, moderator, admin)
    
    # Relations
    roles: Mapped[List["Role"]] = relationship("Role", secondary=role_permissions, back_populates="permissions")

class User(Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    
    # Informations de profil étendues pour MyFav
    username: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    # Informations démographiques
    gender: Mapped[Optional[Gender]] = mapped_column(SQLEnum(Gender), nullable=True)
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Localisation géographique (stockée directement, pas de références externes)
    continent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Anciens IDs (conservés pour compatibilité, dépréciés)
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cities.id"), nullable=True)
    country_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("countries.id"), nullable=True)
    region_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("regions.id"), nullable=True)
    continent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("continents.id"), nullable=True)
    
    # Vérification d'identité (Shufti)
    shufti_verification_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Statut et métadonnées
    status: Mapped[UserStatus] = mapped_column(SQLEnum(UserStatus), default=UserStatus.PENDING_VERIFICATION)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Code de parrainage personnel
    personal_referral_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    
    # Langue préférée (en, fr, es, de)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    
    # Parrain (qui a référé cet utilisateur)
    sponsor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relations géographiques (dépréciées - les données sont maintenant stockées directement)
    # city_rel: Mapped[Optional["City"]] = relationship("City")
    # country_rel: Mapped[Optional["Country"]] = relationship("Country")
    # region_rel: Mapped[Optional["Region"]] = relationship("Region")
    # continent_rel: Mapped[Optional["Continent"]] = relationship("Continent")
    
    # Relations de parrainage direct
    sponsor: Mapped[Optional["User"]] = relationship("User", remote_side="User.id", foreign_keys=[sponsor_id], back_populates="referrals")
    referrals: Mapped[List["User"]] = relationship("User", foreign_keys="User.sponsor_id", back_populates="sponsor")
    
    # Rôle unique de l'utilisateur
    role_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("roles.id"), nullable=True)
    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="users")
    medias: Mapped[List["Media"]] = relationship("Media", back_populates="user")
    
    # Relations concours
    contest_entries: Mapped[List["ContestEntry"]] = relationship("ContestEntry", back_populates="user")
    contestants: Mapped[List["Contestant"]] = relationship("Contestant", back_populates="user")
    votes_cast: Mapped[List["Vote"]] = relationship("Vote", foreign_keys="Vote.voter_id", back_populates="voter")
    my_favorites: Mapped[List["MyFavorites"]] = relationship("MyFavorites", back_populates="user")
    contest_comments: Mapped[List["ContestComment"]] = relationship("ContestComment", back_populates="user")
    contest_likes: Mapped[List["ContestLike"]] = relationship("ContestLike", back_populates="user")
    page_views: Mapped[List["PageView"]] = relationship("PageView", back_populates="user")
    notifications: Mapped[List["Notification"]] = relationship("Notification", back_populates="user")
    
    # Relations financières DSP et affiliation
    dsp_wallet: Mapped[Optional["DSPWallet"]] = relationship("DSPWallet", back_populates="user", uselist=False)
    transactions: Mapped[List["UserTransaction"]] = relationship("UserTransaction", back_populates="user")
    wallet: Mapped[Optional["Wallet"]] = relationship("Wallet", back_populates="user", uselist=False)
    commissions: Mapped[List["Commission"]] = relationship("Commission", back_populates="user")
    affiliate_tree: Mapped[Optional["AffiliateTree"]] = relationship("AffiliateTree", foreign_keys="AffiliateTree.user_id", back_populates="user", uselist=False)
    sponsored_users: Mapped[List["AffiliateTree"]] = relationship("AffiliateTree", foreign_keys="AffiliateTree.sponsor_id", back_populates="sponsor")
    commissions_earned: Mapped[List["AffiliateCommission"]] = relationship("AffiliateCommission", foreign_keys="AffiliateCommission.user_id", back_populates="user")
    commissions_generated: Mapped[List["AffiliateCommission"]] = relationship("AffiliateCommission", foreign_keys="AffiliateCommission.source_user_id", back_populates="source_user")
    referral_links: Mapped[List["ReferralLink"]] = relationship("ReferralLink", back_populates="user")
    revenue_shares: Mapped[List["RevenueShare"]] = relationship("RevenueShare", back_populates="user")
    
    # Relations clubs
    owned_clubs: Mapped[List["FanClub"]] = relationship("FanClub", foreign_keys="FanClub.owner_id", back_populates="owner")
    club_memberships: Mapped[List["ClubMembership"]] = relationship("ClubMembership", back_populates="member")
    club_admin_roles: Mapped[List["ClubAdmin"]] = relationship("ClubAdmin", back_populates="admin")
    club_content: Mapped[List["ClubContent"]] = relationship("ClubContent", back_populates="author")
    
    # Relations boutique digitale
    digital_products: Mapped[List["DigitalProduct"]] = relationship("DigitalProduct", back_populates="seller")
    digital_purchases: Mapped[List["DigitalPurchase"]] = relationship("DigitalPurchase", back_populates="buyer")
    product_reviews: Mapped[List["ProductReview"]] = relationship("ProductReview", back_populates="reviewer")
    
    # Relations publicitaires
    ad_campaigns: Mapped[List["AdCampaign"]] = relationship("AdCampaign", back_populates="advertiser")
    ad_revenue_shares: Mapped[List["AdRevenueShare"]] = relationship("AdRevenueShare", back_populates="user")
    
    # Relations KYC
    kyc_verifications: Mapped[List["KYCVerification"]] = relationship("KYCVerification", back_populates="user")
    
    # Relations commentaires et likes
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="user")
    likes: Mapped[List["Like"]] = relationship("Like", back_populates="user")
    
    # Relations de suivi (follow/followers)
    following: Mapped[List["Follow"]] = relationship("Follow", foreign_keys="Follow.follower_id", back_populates="follower")
    followers: Mapped[List["Follow"]] = relationship("Follow", foreign_keys="Follow.following_id", back_populates="following")
    
    # Relations d'affiliation
    affiliations_made: Mapped[List["Affiliation"]] = relationship("Affiliation", foreign_keys="Affiliation.affiliate_id", back_populates="affiliate")
    referred_by: Mapped[List["Affiliation"]] = relationship("Affiliation", foreign_keys="Affiliation.referred_user_id", back_populates="referred_user")
    referral_codes: Mapped[List["ReferralCode"]] = relationship("ReferralCode", back_populates="user")

class Role(Base):
    """Modèle pour les rôles utilisateurs."""
    __tablename__ = "roles"
    
    name: Mapped[str] = mapped_column(String(64), index=True, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Rôles système non supprimables
    inherit_from_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("roles.id"), nullable=True)  # Héritage de permissions
    
    # Relations
    users: Mapped[List["User"]] = relationship("User", back_populates="role", foreign_keys="User.role_id")
    permissions: Mapped[List["Permission"]] = relationship("Permission", secondary=role_permissions, back_populates="roles")
    inherit_from: Mapped[Optional["Role"]] = relationship("Role", remote_side="Role.id", foreign_keys=[inherit_from_id])
    
    def get_all_permissions(self) -> List[str]:
        """Récupère toutes les permissions incluant celles héritées."""
        perms = set(p.name for p in self.permissions)
        if self.inherit_from:
            perms.update(self.inherit_from.get_all_permissions())
        return list(perms)
    
    def has_permission(self, permission_name: str) -> bool:
        """Vérifie si le rôle a une permission donnée."""
        return permission_name in self.get_all_permissions()
