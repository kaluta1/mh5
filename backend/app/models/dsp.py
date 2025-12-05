from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text, DateTime, Boolean, Numeric, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum
from app.db.base_class import Base


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    PURCHASE = "purchase"
    COMMISSION = "commission"
    REVENUE_SHARE = "revenue_share"
    CLUB_PAYMENT = "club_payment"
    REFUND = "refund"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DSPWallet(Base):
    __tablename__ = "dsp_wallets"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Solde en Digital Shopping Points
    balance_dsp: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    
    # Soldes gelés (en attente de confirmation)
    frozen_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    
    # Statistiques
    total_earned: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    total_spent: Mapped[float] = mapped_column(Numeric(15, 2), default=0.0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="dsp_wallet")
    transactions: Mapped[List["DSPTransaction"]] = relationship("DSPTransaction", back_populates="wallet")


class DSPTransaction(Base):
    __tablename__ = "dsp_transactions"
    wallet_id: Mapped[int] = mapped_column(Integer, ForeignKey("dsp_wallets.id"), nullable=False)
    
    transaction_type: Mapped[TransactionType] = mapped_column(SQLEnum(TransactionType), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Solde avant et après transaction
    balance_before: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    status: Mapped[TransactionStatus] = mapped_column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    wallet: Mapped["DSPWallet"] = relationship("DSPWallet", back_populates="transactions")


class DSPExchangeRate(Base):
    __tablename__ = "dsp_exchange_rates"
    
    # Taux de change DSP vers monnaie fiduciaire
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # USD, EUR, CAD, etc.
    rate_to_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)  # 1 DSP = X currency
    
    effective_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DigitalProduct(Base):
    __tablename__ = "digital_products"
    seller_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Prix (au moins 50% en DSP)
    price_dsp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    price_cad: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    price_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    
    # Fichier téléchargeable
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # en bytes
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Métadonnées
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    preview_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Statistiques
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    fee_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    seller: Mapped["User"] = relationship("User")
    purchases: Mapped[List["DigitalPurchase"]] = relationship("DigitalPurchase", back_populates="product")


class DigitalPurchase(Base):
    __tablename__ = "digital_purchases"
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("digital_products.id"), nullable=False)
    buyer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Montants payés
    total_paid: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    dsp_paid: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    fiat_paid: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Frais de plateforme (20%)
    platform_fee: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    seller_earnings: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    
    # Téléchargement
    download_token: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    max_downloads: Mapped[int] = mapped_column(Integer, default=5)
    
    purchase_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    first_download_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_download_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    product: Mapped["DigitalProduct"] = relationship("DigitalProduct", back_populates="purchases")
    buyer: Mapped["User"] = relationship("User")


class ProductReview(Base):
    __tablename__ = "product_reviews"
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("digital_products.id"), nullable=False)
    reviewer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 étoiles
    review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relations
    product: Mapped["DigitalProduct"] = relationship("DigitalProduct")
    reviewer: Mapped["User"] = relationship("User")
