from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Numeric, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.contest import Contest

class TransactionType(str, enum.Enum):
    ENTRY_FEE = "entry_fee"
    PRIZE_PAYOUT = "prize_payout"
    COMMISSION = "commission"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    REFUND = "refund"

class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class UserTransaction(Base):
    __tablename__ = "transactions"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contest_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest.id"), nullable=True)
    
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    
    transaction_type: Mapped[TransactionType] = mapped_column(SQLEnum(TransactionType), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
    
    # Informations de paiement
    payment_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    contest: Mapped[Optional["Contest"]] = relationship("Contest", back_populates="transactions")

class Wallet(Base):
    __tablename__ = "wallet"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    
    # Soldes gelés pour les transactions en attente
    frozen_balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00, nullable=False)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="wallet")
