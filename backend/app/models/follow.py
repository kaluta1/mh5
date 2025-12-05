from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, ForeignKey, Boolean, DateTime, String
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User

class Follow(Base):
    __tablename__ = "follow"
    
    follower_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    following_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Notifications
    notify_new_posts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_contests: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relations
    follower: Mapped["User"] = relationship("User", foreign_keys=[follower_id], back_populates="following")
    following: Mapped["User"] = relationship("User", foreign_keys=[following_id], back_populates="followers")

class Affiliation(Base):
    __tablename__ = "affiliation"
    
    # Utilisateur qui fait la promotion (affilié)
    affiliate_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Utilisateur référé
    referred_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Code de parrainage utilisé
    referral_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Statut de l'affiliation
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Commissions gagnées
    total_commission_earned: Mapped[float] = mapped_column(Integer, default=0, nullable=False)  # en centimes
    
    # Date de première transaction du référé (pour valider l'affiliation)
    first_transaction_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    affiliate: Mapped["User"] = relationship("User", foreign_keys=[affiliate_id], back_populates="affiliations_made")
    referred_user: Mapped["User"] = relationship("User", foreign_keys=[referred_user_id], back_populates="referred_by")

class ReferralCode(Base):
    __tablename__ = "referral_code"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    
    # Configuration du code
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = illimité
    current_uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Taux de commission (en pourcentage)
    commission_rate: Mapped[float] = mapped_column(Integer, default=500, nullable=False)  # 5.00% = 500 (en centièmes)
    
    # Dates de validité
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="referral_codes")
