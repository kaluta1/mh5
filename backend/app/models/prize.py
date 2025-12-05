from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Numeric, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.contest import Contest
    from app.models.user import User

class PrizeType(str, enum.Enum):
    CASH = "cash"
    GIFT_CARD = "gift_card"
    PHYSICAL_ITEM = "physical_item"
    DIGITAL_ITEM = "digital_item"
    EXPERIENCE = "experience"
    CREDITS = "credits"

class Prize(Base):
    __tablename__ = "prize"
    
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False)
    
    # Position du prix (1er, 2ème, 3ème, etc.)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Type et valeur du prix
    prize_type: Mapped[PrizeType] = mapped_column(SQLEnum(PrizeType), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    
    # Description du prix
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Image du prix
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Informations de livraison pour les prix physiques
    requires_shipping: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shipping_info: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Relations
    contest: Mapped["Contest"] = relationship("Contest", back_populates="prizes")
    winner: Mapped[Optional["PrizeWinner"]] = relationship("PrizeWinner", back_populates="prize", uselist=False)

class PrizeWinner(Base):
    __tablename__ = "prize_winner"
    
    prize_id: Mapped[int] = mapped_column(Integer, ForeignKey("prize.id"), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contest_entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_entry.id"), nullable=False)
    
    # Statut de la remise du prix
    is_claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Informations de livraison
    delivery_address: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Notes administratives
    admin_notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    # Relations
    prize: Mapped["Prize"] = relationship("Prize", back_populates="winner")
    user: Mapped["User"] = relationship("User")
    contest_entry: Mapped["ContestEntry"] = relationship("ContestEntry")

class Commission(Base):
    __tablename__ = "commission"
    
    # Utilisateur qui reçoit la commission
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Transaction ou concours lié à la commission
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True)
    contest_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest.id"), nullable=True)
    
    # Montant de la commission
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    
    # Taux de commission appliqué (en pourcentage)
    commission_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    
    # Type de commission
    commission_type: Mapped[str] = mapped_column(String(50), nullable=False)  # referral, contest_fee, etc.
    
    # Statut du paiement
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="commissions")
    transaction: Mapped[Optional["UserTransaction"]] = relationship("UserTransaction")
    contest: Mapped[Optional["Contest"]] = relationship("Contest")
