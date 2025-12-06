"""
Payment API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

from app.api import deps
from app.models.user import User
from app.models.payment import Deposit, DepositStatus, ProductType
from app.services.crypto_payment import crypto_payment_service, CryptoPaymentError
from app.services.payment_scheduler import check_payment_now
from app.core.config import settings
from app.crud import crud_deposit
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# Schemas
class PaymentRecipient(BaseModel):
    username_or_email: str
    product_code: str  # "kyc", "efm_membership"
    amount: float


class CreatePaymentRequest(BaseModel):
    amount: float
    currency: str = "usd"
    pay_currency: str = "btc"  # Crypto to pay with
    product_code: str  # "kyc", "efm_membership", etc.
    recipients: Optional[list[PaymentRecipient]] = None  # For multi-user payments
    

class CreateInvoiceRequest(BaseModel):
    amount: float
    currency: str = "usd"
    product_code: str


class PaymentResponse(BaseModel):
    deposit_id: int  # Local deposit ID for status checks
    payment_id: int  # External payment provider ID
    pay_address: str
    pay_amount: float
    pay_currency: str
    price_amount: float
    price_currency: str
    order_id: str
    status: str


class InvoiceResponse(BaseModel):
    invoice_id: str
    invoice_url: str
    order_id: str


@router.get("/verify-user")
async def verify_user_exists(
    username_or_email: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Check if a user exists by username or email"""
    user = db.query(User).filter(
        (User.username == username_or_email) | (User.email == username_or_email)
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "username": user.username or user.email.split('@')[0],
        "email": user.email,
        "display_name": user.full_name or user.username or user.email.split('@')[0]
    }


@router.get("/currencies")
async def get_available_currencies():
    """Get list of available cryptocurrencies for payment"""
    try:
        currencies = await crypto_payment_service.get_available_currencies()
        # Filter to supported currencies
        supported = ["btc", "eth", "usdt", "sol", "bnb", "matic", "trx"]
        return {
            "currencies": [c for c in currencies if c.lower() in supported]
        }
    except CryptoPaymentError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e.message))


@router.get("/estimate")
async def get_payment_estimate(
    amount: float,
    currency_from: str = "usd",
    currency_to: str = "btc"
):
    """Get estimated crypto amount for a fiat amount"""
    try:
        estimate = await crypto_payment_service.get_estimate(amount, currency_from, currency_to)
        return estimate
    except CryptoPaymentError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e.message))


@router.post("/create", response_model=PaymentResponse)
async def create_crypto_payment(
    request: CreatePaymentRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Create a crypto payment for a product
    Returns payment address and amount to send
    """
    # Generate unique order ID
    order_id = f"{current_user.id}_{request.product_code}_{uuid.uuid4().hex[:8]}"
    
    # Get product info
    product = crud_deposit.product_type.get_by_code(db, code=request.product_code)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Validate minimum amount
    if request.product_code == "efm_membership" and request.amount < 100:
        raise HTTPException(status_code=400, detail="Minimum amount for EFM membership is $100")
    
    try:
        # Add $0.5 fee buffer to avoid network fees issues
        amount_with_fees = request.amount + 0.5
        
        # Create payment with crypto provider
        payment = await crypto_payment_service.create_payment(
            price_amount=amount_with_fees,
            price_currency=request.currency,
            pay_currency=request.pay_currency,
            order_id=order_id,
            order_description=f"{product.name} - {current_user.email}",
            ipn_callback_url=f"{settings.FRONTEND_URL.replace('localhost:3000', 'mh5-sbe4.onrender.com')}/api/v1/payments/webhook",
            success_url=f"{settings.FRONTEND_URL}/dashboard/kyc?payment=success",
            cancel_url=f"{settings.FRONTEND_URL}/dashboard/kyc?payment=cancelled"
        )
        
        # Create deposit record in database
        deposit = Deposit(
            user_id=current_user.id,
            product_type_id=product.id,
            amount=request.amount,
            currency=request.currency.upper(),
            crypto_currency=request.pay_currency.upper(),
            crypto_amount=payment.get("pay_amount"),
            payment_address=payment.get("pay_address"),
            external_payment_id=str(payment.get("payment_id")),
            order_id=order_id,
            status=DepositStatus.PENDING
        )
        db.add(deposit)
        db.commit()
        db.refresh(deposit)
        
        return PaymentResponse(
            deposit_id=deposit.id,  # Local deposit ID
            payment_id=payment.get("payment_id"),
            pay_address=payment.get("pay_address"),
            pay_amount=payment.get("pay_amount"),
            pay_currency=payment.get("pay_currency"),
            price_amount=request.amount,
            price_currency=request.currency,
            order_id=order_id,
            status="waiting"
        )
        
    except CryptoPaymentError as e:
        logger.error(f"Crypto payment error: {e.message}")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e.message))


@router.post("/invoice", response_model=InvoiceResponse)
async def create_payment_invoice(
    request: CreateInvoiceRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Create a payment invoice (hosted page where user selects crypto)
    """
    order_id = f"{current_user.id}_{request.product_code}_{uuid.uuid4().hex[:8]}"
    
    product = crud_deposit.product_type.get_by_code(db, code=request.product_code)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    try:
        # Add $0.5 fee buffer to avoid network fees issues
        amount_with_fees = request.amount + 0.5
        
        invoice = await crypto_payment_service.create_invoice(
            price_amount=amount_with_fees,
            price_currency=request.currency,
            order_id=order_id,
            order_description=f"{product.name} - {current_user.email}",
            ipn_callback_url=f"{settings.FRONTEND_URL.replace('localhost:3000', 'mh5-sbe4.onrender.com')}/api/v1/payments/webhook",
            success_url=f"{settings.FRONTEND_URL}/dashboard/kyc?payment=success",
            cancel_url=f"{settings.FRONTEND_URL}/dashboard/kyc?payment=cancelled"
        )
        
        # Create deposit record
        deposit = Deposit(
            user_id=current_user.id,
            product_type_id=product.id,
            amount=request.amount,
            currency=request.currency.upper(),
            external_payment_id=str(invoice.get("id")),
            order_id=order_id,
            status=DepositStatus.PENDING
        )
        db.add(deposit)
        db.commit()
        
        return InvoiceResponse(
            invoice_id=str(invoice.get("id")),
            invoice_url=invoice.get("invoice_url"),
            order_id=order_id
        )
        
    except CryptoPaymentError as e:
        logger.error(f"Invoice creation error: {e.message}")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e.message))


@router.get("/status/{payment_id}")
async def get_payment_status(
    payment_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Get status of a payment"""
    try:
        status = await crypto_payment_service.get_payment_status(payment_id)
        return status
    except CryptoPaymentError as e:
        raise HTTPException(status_code=e.status_code or 500, detail=str(e.message))


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: Session = Depends(deps.get_db)
):
    """
    Webhook endpoint for payment notifications (IPN)
    Called by payment provider when payment status changes
    """
    try:
        payload = await request.json()
        signature = request.headers.get("x-nowpayments-sig", "")
        
        # Verify signature
        if not crypto_payment_service.verify_ipn_signature(payload, signature):
            logger.warning("Invalid IPN signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        payment_status = payload.get("payment_status")
        order_id = payload.get("order_id")
        payment_id = payload.get("payment_id")
        
        logger.info(f"IPN received: order={order_id}, status={payment_status}")
        
        # Find deposit by order_id
        deposit = crud_deposit.deposit.get_by_order_id(db, order_id=order_id)
        if not deposit:
            logger.warning(f"Deposit not found for order: {order_id}")
            return {"status": "ok"}
        
        # Update deposit status based on payment status
        if payment_status == "finished":
            deposit.status = DepositStatus.VALIDATED
            deposit.validated_at = datetime.utcnow()
        elif payment_status == "partially_paid":
            deposit.status = DepositStatus.PARTIALLY_PAID
        elif payment_status in ["failed", "expired", "refunded"]:
            deposit.status = DepositStatus.FAILED
        elif payment_status in ["waiting", "confirming", "sending"]:
            deposit.status = DepositStatus.PENDING
        
        # Update payment details
        deposit.crypto_amount = payload.get("actually_paid")
        deposit.external_payment_id = str(payment_id)
        
        db.commit()
        logger.info(f"Deposit {deposit.id} updated to {deposit.status}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/check/{deposit_id}")
async def check_and_refresh_payment(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Manually check and refresh payment status.
    Called when user clicks "I have paid" button.
    """
    # Get deposit and verify ownership
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check payment status
    result = await check_payment_now(db, deposit_id)
    
    return {
        "deposit_id": deposit_id,
        "status": result.get("status"),
        "payment_status": result.get("payment_status"),
        "is_confirmed": result.get("is_confirmed", False),
        "error": result.get("error")
    }


@router.get("/deposit/{deposit_id}")
async def get_deposit_status(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Get the current status of a deposit"""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "deposit_id": deposit.id,
        "status": deposit.status.value,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
        "amount": deposit.amount,
        "currency": deposit.currency,
        "created_at": deposit.created_at.isoformat() if deposit.created_at else None,
        "validated_at": deposit.validated_at.isoformat() if deposit.validated_at else None
    }
