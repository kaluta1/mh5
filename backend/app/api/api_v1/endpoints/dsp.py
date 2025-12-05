from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import crud_dsp
from app.schemas.dsp import (
    DSPWallet, DSPWalletResponse,
    DSPTransaction, DSPTransactionCreate,
    DSPExchangeRate,
    DigitalProduct, DigitalProductCreate, DigitalProductUpdate,
    DigitalPurchase, DigitalPurchaseCreate,
    ProductReview, ProductReviewCreate
)

router = APIRouter()


@router.get("/wallet", response_model=DSPWalletResponse)
def get_my_wallet(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer le portefeuille DSP de l'utilisateur.
    """
    wallet = crud_dsp.dsp_wallet.get_or_create_wallet(
        db=db, user_id=current_user.id
    )
    return wallet


@router.get("/wallet/transactions", response_model=List[DSPTransaction])
def get_wallet_transactions(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50,
    transaction_type: Optional[str] = None
):
    """
    Récupérer l'historique des transactions DSP.
    """
    transactions = crud_dsp.dsp_transaction.get_user_transactions(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        transaction_type=transaction_type
    )
    return transactions


@router.post("/wallet/transfer", response_model=DSPTransaction, status_code=status.HTTP_201_CREATED)
def transfer_dsp(
    *,
    db: Session = Depends(deps.get_db),
    transfer_data: dict,  # {"to_user_id": int, "amount": float, "description": str}
    current_user = Depends(deps.get_current_active_user)
):
    """
    Transférer des DSP à un autre utilisateur.
    """
    result = crud_dsp.dsp_transaction.transfer_dsp(
        db=db,
        from_user_id=current_user.id,
        to_user_id=transfer_data["to_user_id"],
        amount=transfer_data["amount"],
        description=transfer_data.get("description", "")
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result["transaction"]


@router.get("/exchange-rates", response_model=List[DSPExchangeRate])
def get_exchange_rates(
    db: Session = Depends(deps.get_db),
    currency: Optional[str] = None
):
    """
    Récupérer les taux de change DSP actuels.
    """
    rates = crud_dsp.dsp_exchange_rate.get_current_rates(
        db=db, currency=currency
    )
    return rates


@router.post("/exchange", response_model=DSPTransaction, status_code=status.HTTP_201_CREATED)
def exchange_currency(
    *,
    db: Session = Depends(deps.get_db),
    exchange_data: dict,  # {"from_currency": str, "to_currency": str, "amount": float}
    current_user = Depends(deps.get_current_active_user)
):
    """
    Échanger des devises contre des DSP ou vice versa.
    """
    result = crud_dsp.dsp_transaction.exchange_currency(
        db=db,
        user_id=current_user.id,
        from_currency=exchange_data["from_currency"],
        to_currency=exchange_data["to_currency"],
        amount=exchange_data["amount"]
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result["transaction"]


# Boutique digitale
@router.get("/products", response_model=List[DigitalProduct])
def get_digital_products(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 50,
    category: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Récupérer les produits digitaux disponibles.
    """
    products = crud_dsp.digital_product.get_available_products(
        db=db,
        skip=skip,
        limit=limit,
        category=category,
        search=search
    )
    return products


@router.get("/products/{product_id}", response_model=DigitalProduct)
def get_digital_product(
    product_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer un produit digital par ID.
    """
    product = crud_dsp.digital_product.get(db=db, id=product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produit non trouvé"
        )
    return product


@router.post("/products", response_model=DigitalProduct, status_code=status.HTTP_201_CREATED)
def create_digital_product(
    *,
    db: Session = Depends(deps.get_db),
    product_in: DigitalProductCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer un nouveau produit digital (vendeurs vérifiés seulement).
    """
    if not current_user.identity_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vérification d'identité requise pour vendre"
        )
    
    product = crud_dsp.digital_product.create_with_seller(
        db=db, obj_in=product_in, seller_id=current_user.id
    )
    return product


@router.put("/products/{product_id}", response_model=DigitalProduct)
def update_digital_product(
    *,
    db: Session = Depends(deps.get_db),
    product_id: int,
    product_in: DigitalProductUpdate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Mettre à jour un produit digital (propriétaire seulement).
    """
    product = crud_dsp.digital_product.get(db=db, id=product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produit non trouvé"
        )
    
    if product.seller_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    product = crud_dsp.digital_product.update(db=db, db_obj=product, obj_in=product_in)
    return product


@router.post("/purchase", response_model=DigitalPurchase, status_code=status.HTTP_201_CREATED)
def purchase_digital_product(
    *,
    db: Session = Depends(deps.get_db),
    purchase_in: DigitalPurchaseCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Acheter un produit digital avec des DSP.
    """
    result = crud_dsp.digital_purchase.create_purchase(
        db=db,
        buyer_id=current_user.id,
        product_id=purchase_in.product_id,
        payment_method=purchase_in.payment_method
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result["purchase"]


@router.get("/purchases", response_model=List[DigitalPurchase])
def get_my_purchases(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les achats de l'utilisateur.
    """
    purchases = crud_dsp.digital_purchase.get_user_purchases(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return purchases


@router.get("/sales", response_model=List[DigitalPurchase])
def get_my_sales(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les ventes de l'utilisateur.
    """
    sales = crud_dsp.digital_purchase.get_seller_sales(
        db=db, seller_id=current_user.id, skip=skip, limit=limit
    )
    return sales


@router.post("/products/{product_id}/reviews", response_model=ProductReview, status_code=status.HTTP_201_CREATED)
def create_product_review(
    *,
    db: Session = Depends(deps.get_db),
    product_id: int,
    review_in: ProductReviewCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer un avis sur un produit (acheteurs seulement).
    """
    # Vérifier que l'utilisateur a acheté le produit
    has_purchased = crud_dsp.digital_purchase.has_user_purchased(
        db=db, user_id=current_user.id, product_id=product_id
    )
    
    if not has_purchased:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez acheter le produit pour laisser un avis"
        )
    
    review = crud_dsp.product_review.create_with_reviewer(
        db=db, obj_in=review_in, product_id=product_id, reviewer_id=current_user.id
    )
    return review


@router.get("/products/{product_id}/reviews", response_model=List[ProductReview])
def get_product_reviews(
    product_id: int,
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 20
):
    """
    Récupérer les avis d'un produit.
    """
    reviews = crud_dsp.product_review.get_product_reviews(
        db=db, product_id=product_id, skip=skip, limit=limit
    )
    return reviews


@router.get("/earnings", response_model=dict)
def get_dsp_earnings(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les gains DSP de l'utilisateur (ventes, commissions, etc.).
    """
    earnings = crud_dsp.dsp_transaction.get_user_earnings_summary(
        db=db, user_id=current_user.id
    )
    return earnings
