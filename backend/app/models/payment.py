"""
Payment models - Deposit, Payment Methods, Product Types
"""
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, Numeric, Enum as SQLEnum, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.affiliate import AffiliateCommission


class PaymentMethodCategory(str, Enum):
    """Catégorie de méthode de paiement"""
    CRYPTO = "crypto"
    BANK = "bank"
    CARD = "card"


class CryptoNetwork(str, Enum):
    """Réseaux crypto supportés"""
    BSC = "bsc"           # Binance Smart Chain
    SOLANA = "solana"
    BITCOIN = "bitcoin"
    ETHEREUM = "ethereum"


class DepositStatus(str, Enum):
    """Statut d'un dépôt"""
    PENDING = "pending"           # En attente de confirmation
    VALIDATED = "validated"       # Validé/Confirmé
    REJECTED = "rejected"         # Rejeté
    EXPIRED = "expired"           # Expiré
    PARTIALLY_PAID = "partially_paid"  # Paiement partiel
    FAILED = "failed"             # Échec


class PaymentMethod(Base):
    """
    Méthodes de paiement disponibles
    Ex: USDT BSC, USDT SOL, BTC, SOL, Carte bancaire, Virement
    """
    __tablename__ = "payment_methods"
    
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # usdt_bsc, btc, card, bank
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # USDT (BSC), Bitcoin, etc.
    category: Mapped[PaymentMethodCategory] = mapped_column(
        SQLEnum(PaymentMethodCategory), 
        nullable=False
    )
    
    # Pour crypto uniquement
    network: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # bsc, solana, bitcoin
    token_symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # USDT, BTC, SOL
    wallet_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Adresse de réception
    
    # Configuration
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    min_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    max_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    
    # Instructions pour l'utilisateur
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relations
    deposits: Mapped[list["Deposit"]] = relationship("Deposit", back_populates="payment_method")


class ProductType(Base):
    """
    Types de produits payables avec configuration des commissions d'affiliation.
    Ex: KYC, Subscription Club, EFM Membership, Founding Membership
    """
    __tablename__ = "product_types"
    
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # kyc, founding_membership, annual_membership
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Prix par défaut
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    
    # Durée de validité en jours (365 pour 1 an, 0 pour one-time)
    validity_days: Mapped[int] = mapped_column(Integer, default=365)
    
    # Configuration
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Pour les produits qui consomment des tentatives (comme KYC)
    is_consumable: Mapped[bool] = mapped_column(Boolean, default=True)  # True = 1 paiement = 1 utilisation
    
    # ============================================
    # CONFIGURATION COMMISSIONS D'AFFILIATION
    # ============================================
    
    # Activer les commissions pour ce produit
    has_affiliate_commission: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Commission Niveau 1 (parrainage direct)
    affiliate_direct_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # Montant fixe (ex: 20$)
    affiliate_direct_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)  # OU pourcentage (ex: 0.20)
    
    # Commission Niveaux 2-10 (parrainages indirects)
    affiliate_indirect_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # Montant fixe (ex: 2$)
    affiliate_indirect_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)  # OU pourcentage (ex: 0.02)
    
    # Relations
    deposits: Mapped[list["Deposit"]] = relationship("Deposit", back_populates="product_type")
    affiliate_commissions: Mapped[list["AffiliateCommission"]] = relationship("AffiliateCommission", back_populates="product_type")


class Deposit(Base):
    """
    Dépôts/Paiements des utilisateurs
    """
    __tablename__ = "deposits"
    
    # Relations
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    product_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_types.id"), nullable=False)
    payment_method_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    
    # Montant en fiat
    amount: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    
    # Montant en crypto (si paiement crypto)
    crypto_currency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # BTC, ETH, USDT
    crypto_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    payment_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Adresse de paiement
    
    # Statut
    status: Mapped[DepositStatus] = mapped_column(
        SQLEnum(DepositStatus, values_callable=lambda x: [e.value for e in x]), 
        default=DepositStatus.PENDING
    )
    
    # Références
    order_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)  # Notre référence interne
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # ID du provider
    
    # Pour crypto - transaction
    tx_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    from_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Dates
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Date d'expiration du crédit
    
    # Utilisation (pour produits consommables comme KYC)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Notes admin
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], backref="deposits")
    product_type: Mapped["ProductType"] = relationship("ProductType", back_populates="deposits")
    payment_method: Mapped[Optional["PaymentMethod"]] = relationship("PaymentMethod", back_populates="deposits")
    validator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[validated_by])
    
    def is_valid(self) -> bool:
        """Vérifie si le dépôt est valide et utilisable"""
        if self.status != DepositStatus.VALIDATED:
            return False
        if self.is_used:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True
    
    def mark_as_used(self):
        """Marque le dépôt comme utilisé"""
        self.is_used = True
        self.used_at = datetime.utcnow()


# Import User pour les relations (éviter import circulaire)
from app.models.user import User
