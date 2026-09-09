from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from app.models.dsp import TransactionType, TransactionStatus


# DSP Wallet schemas
class DSPWalletBase(BaseModel):
    user_id: int
    balance_dsp: Decimal = Decimal("0.00")
    frozen_balance: Decimal = Decimal("0.00")
    total_earned: Decimal = Decimal("0.00")
    total_spent: Decimal = Decimal("0.00")


class DSPWalletCreate(DSPWalletBase):
    pass


class DSPWalletUpdate(BaseModel):
    balance_dsp: Optional[Decimal] = None
    frozen_balance: Optional[Decimal] = None


class DSPWallet(DSPWalletBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None


class DSPWalletResponse(DSPWallet):
    """Réponse wallet avec informations utilisateur"""
    user_name: Optional[str] = None
    available_balance: Decimal = Decimal("0.00")  # balance_dsp - frozen_balance


# DSP Transaction schemas
class DSPTransactionBase(BaseModel):
    wallet_id: int
    transaction_type: TransactionType
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    description: Optional[str] = None
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    status: TransactionStatus = TransactionStatus.PENDING


class DSPTransactionCreate(BaseModel):
    transaction_type: TransactionType
    amount: Decimal
    description: Optional[str] = None
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None


class DSPTransactionUpdate(BaseModel):
    status: Optional[TransactionStatus] = None


class DSPTransaction(DSPTransactionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


# DSP Exchange Rate schemas
class DSPExchangeRateBase(BaseModel):
    currency: str
    rate_to_cad: Decimal
    rate_to_usd: Decimal
    is_active: bool = True


class DSPExchangeRateCreate(DSPExchangeRateBase):
    pass


class DSPExchangeRateUpdate(BaseModel):
    rate_to_cad: Optional[Decimal] = None
    rate_to_usd: Optional[Decimal] = None
    is_active: Optional[bool] = None


class DSPExchangeRate(DSPExchangeRateBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    effective_date: Optional[datetime] = None


# Digital Product schemas
class DigitalProductBase(BaseModel):
    title: str
    description: str
    category: str
    price_dsp: Decimal
    price_cad: Optional[Decimal] = None
    price_usd: Optional[Decimal] = None
    currency: str = "USD"
    file_url: str
    file_size: Optional[int] = None
    file_type: str
    tags: Optional[str] = None
    preview_url: Optional[str] = None
    is_active: bool = True


class DigitalProductCreate(DigitalProductBase):
    pass


class DigitalProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price_dsp: Optional[Decimal] = None
    price_cad: Optional[Decimal] = None
    price_usd: Optional[Decimal] = None
    file_url: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    tags: Optional[str] = None
    preview_url: Optional[str] = None
    is_active: Optional[bool] = None


class DigitalProduct(DigitalProductBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    seller_id: int
    downloads: int = 0
    views: int = 0
    average_rating: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DigitalProductWithSeller(DigitalProduct):
    """Produit avec informations vendeur"""
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None
    total_sales: int = 0


# Digital Purchase schemas
class DigitalPurchaseBase(BaseModel):
    product_id: int
    buyer_id: int
    total_paid: Decimal
    dsp_paid: Decimal
    fiat_paid: Decimal
    platform_fee: Decimal
    seller_earnings: Decimal
    download_token: str
    max_downloads: int = 5


class DigitalPurchaseCreate(BaseModel):
    product_id: int
    payment_method: str  # dsp_only, mixed, fiat_only


class DigitalPurchaseUpdate(BaseModel):
    download_count: Optional[int] = None


class DigitalPurchase(DigitalPurchaseBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    download_count: int = 0
    purchase_date: Optional[datetime] = None
    first_download_date: Optional[datetime] = None
    last_download_date: Optional[datetime] = None


class DigitalPurchaseWithProduct(DigitalPurchase):
    """Achat avec informations produit"""
    product_title: Optional[str] = None
    product_file_type: Optional[str] = None
    seller_name: Optional[str] = None


# Product Review schemas
class ProductReviewBase(BaseModel):
    product_id: int
    reviewer_id: int
    rating: int  # 1-5
    review_text: Optional[str] = None
    is_verified_purchase: bool = False


class ProductReviewCreate(ProductReviewBase):
    pass


class ProductReviewUpdate(BaseModel):
    rating: Optional[int] = None
    review_text: Optional[str] = None


class ProductReview(ProductReviewBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


class ProductReviewWithReviewer(ProductReview):
    """Avis avec informations reviewer"""
    reviewer_name: Optional[str] = None
    reviewer_profile_picture: Optional[str] = None


# Response schemas complexes
class DSPEarningsSummary(BaseModel):
    """Résumé des gains DSP d'un utilisateur"""
    total_earned: Decimal = Decimal("0.00")
    sales_earnings: Decimal = Decimal("0.00")
    affiliate_commissions: Decimal = Decimal("0.00")
    contest_rewards: Decimal = Decimal("0.00")
    ad_revenue_share: Decimal = Decimal("0.00")
    referral_bonuses: Decimal = Decimal("0.00")
    current_month_earnings: Decimal = Decimal("0.00")


class DigitalProductStats(BaseModel):
    """Statistiques d'un produit digital"""
    product: DigitalProduct
    total_sales: int = 0
    total_revenue: Decimal = Decimal("0.00")
    average_rating: float = 0.0
    total_reviews: int = 0
    conversion_rate: float = 0.0
    recent_sales: List[DigitalPurchase] = []


class DSPMarketplace(BaseModel):
    """Page marketplace DSP"""
    featured_products: List[DigitalProductWithSeller] = []
    categories: List[str] = []
    top_sellers: List[dict] = []  # {"seller_name": str, "total_sales": int}
    recent_products: List[DigitalProductWithSeller] = []


class DSPTransactionHistory(BaseModel):
    """Historique des transactions DSP avec pagination"""
    transactions: List[DSPTransaction] = []
    total_count: int = 0
    total_earned: Decimal = Decimal("0.00")
    total_spent: Decimal = Decimal("0.00")
    current_balance: Decimal = Decimal("0.00")
