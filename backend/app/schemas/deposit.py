"""
Schemas for Deposits, Payment Methods, Product Types
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# Payment Method Schemas
class PaymentMethodBase(BaseModel):
    code: str
    name: str
    category: str
    network: Optional[str] = None
    token_symbol: Optional[str] = None
    wallet_address: Optional[str] = None
    is_active: bool = True
    instructions: Optional[str] = None


class PaymentMethodResponse(PaymentMethodBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Product Type Schemas
class ProductTypeBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    price: float
    currency: str = "USD"
    validity_days: int = 365
    is_active: bool = True
    is_consumable: bool = True


class ProductTypeResponse(ProductTypeBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Deposit Schemas
class DepositBase(BaseModel):
    amount: float
    currency: str = "USD"


class DepositCreate(DepositBase):
    user_id: int
    product_type_id: int
    payment_method_id: int
    tx_hash: Optional[str] = None
    from_address: Optional[str] = None


class DepositUpdate(BaseModel):
    status: Optional[str] = None
    tx_hash: Optional[str] = None
    admin_notes: Optional[str] = None
    validated_by: Optional[int] = None


class DepositResponse(DepositBase):
    id: int
    user_id: int
    product_type_id: int
    payment_method_id: int
    status: str
    reference: str
    tx_hash: Optional[str] = None
    from_address: Optional[str] = None
    validated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_used: bool
    used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DepositDetailResponse(DepositResponse):
    product_type: Optional[ProductTypeResponse] = None
    payment_method: Optional[PaymentMethodResponse] = None
    
    class Config:
        from_attributes = True


# Request schemas
class InitiateDepositRequest(BaseModel):
    """Demande pour initier un dépôt"""
    product_code: str  # kyc, subscription_club, etc.
    payment_method_code: str  # usdt_bsc, btc, card, etc.
    quantity: int = 1  # Nombre d'unités (ex: 2 tentatives KYC)


class SubmitDepositRequest(BaseModel):
    """Soumettre un dépôt crypto pour validation"""
    deposit_reference: str
    tx_hash: str
    from_address: Optional[str] = None


# Response schemas
class InitiateDepositResponse(BaseModel):
    """Réponse à l'initiation d'un dépôt"""
    reference: str
    amount: float
    currency: str
    payment_method: PaymentMethodResponse
    product_type: ProductTypeResponse
    wallet_address: Optional[str] = None
    instructions: Optional[str] = None
    expires_in_minutes: int = 60  # Temps pour effectuer le paiement


class KYCPaymentStatusResponse(BaseModel):
    """Statut du paiement KYC d'un utilisateur"""
    has_valid_payment: bool
    available_attempts: int
    total_purchased: int
    total_used: int
    next_expiry: Optional[datetime] = None
