"""
Payment API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

from app.api import deps
from app.models.user import User
from app.models.payment import Deposit, DepositStatus, ProductType
from app.services.onchain_payment import onchain_payment_service, OnchainPaymentError
from app.core.config import settings
from app.crud import crud_deposit
from app.services.commission_distribution import process_payment_validation
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
    product_code: str  # "kyc", "efm_membership", etc.
    recipients: Optional[list[PaymentRecipient]] = None  # For multi-user payments


class VerifyPaymentRequest(BaseModel):
    order_id: str
    tx_hash: str


class PaymentResponse(BaseModel):
    deposit_id: int  # Local deposit ID for status checks
    order_id: str  # Order ID for smart contract payment
    contract_address: str  # Payment contract address
    token_address: str  # USDT token address
    amount_wei: str  # Amount in wei (as string for precision)
    chain_id: int  # BSC chain ID
    price_amount: float  # Amount in USD
    price_currency: str
    status: str


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
    # Only USDT on BSC is supported
    return {
        "currencies": ["usdt"]
    }


@router.post("/create", response_model=PaymentResponse)
async def create_payment(
    request: CreatePaymentRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Create a payment order for smart contract payment
    Returns order_id and payment details for frontend wallet integration
    """
    # Generate unique order ID (bytes32 format)
    order_id = onchain_payment_service.build_order_id()
    
    # Get product info
    product = crud_deposit.product_type.get_by_code(db, code=request.product_code)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Validate minimum amount
    if request.product_code == "efm_membership" and request.amount < 100:
        raise HTTPException(status_code=400, detail="Minimum amount for EFM membership is $100")
    
    try:
        # Convert amount to wei
        amount_wei = onchain_payment_service.to_wei(request.amount, settings.BSC_USDT_DECIMALS)
        
        # Create deposit record in database
        deposit = Deposit(
            user_id=current_user.id,
            product_type_id=product.id,
            amount=request.amount,
            currency=request.currency.upper(),
            crypto_currency="USDT",
            crypto_amount=str(amount_wei),
            order_id=order_id,
            status=DepositStatus.PENDING
        )
        db.add(deposit)
        db.commit()
        db.refresh(deposit)
        
        return PaymentResponse(
            deposit_id=deposit.id,
            order_id=order_id,
            contract_address=settings.BSC_PAYMENT_CONTRACT,
            token_address=settings.BSC_USDT_ADDRESS,
            amount_wei=str(amount_wei),
            chain_id=settings.BSC_CHAIN_ID,
            price_amount=request.amount,
            price_currency=request.currency,
            status="pending"
        )
        
    except Exception as e:
        logger.error(f"Payment creation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify", response_model=dict)
async def verify_payment(
    request: VerifyPaymentRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Verify a payment transaction on the blockchain
    Called after user submits transaction hash
    """
    try:
        # Find deposit by order_id
        deposit = crud_deposit.deposit.get_by_order_id(db, order_id=request.order_id)
        if not deposit:
            raise HTTPException(status_code=404, detail="Deposit not found")
        
        # Verify ownership
        if deposit.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Already validated
        if deposit.status == DepositStatus.VALIDATED:
            return {
                "valid": True,
                "deposit_id": deposit.id,
                "status": "validated",
                "message": "Payment already verified"
            }
        
        # Get expected amount in wei
        expected_amount_wei = int(deposit.crypto_amount) if deposit.crypto_amount else 0
        
        # Verify payment on blockchain
        payment_details = onchain_payment_service.verify_payment(
            order_id=request.order_id,
            tx_hash=request.tx_hash,
            expected_amount_wei=expected_amount_wei,
            token_address=settings.BSC_USDT_ADDRESS
        )
        
        # Update deposit status (single commit after commissions + accounting succeed)
        deposit.status = DepositStatus.VALIDATED
        deposit.validated_at = datetime.utcnow()
        deposit.external_payment_id = request.tx_hash
        deposit.payment_address = payment_details.payer

        logger.info(f"Processing commission distribution for deposit {deposit.id}")
        ok = process_payment_validation(db, deposit, defer_commit=True)
        if not ok:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=(
                    "Payment verification failed while recording commissions or accounting "
                    "(e.g. chart of accounts). The deposit was not finalized; retry after fixing configuration."
                ),
            )
        db.commit()

        return {
            "valid": True,
            "deposit_id": deposit.id,
            "status": "validated",
            "payer": payment_details.payer,
            "tx_hash": request.tx_hash
        }
        
    except OnchainPaymentError as e:
        logger.error(f"Payment verification error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Payment verification error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check/{deposit_id}")
async def check_payment_status(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Check payment status by deposit ID
    """
    # Get deposit and verify ownership
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "deposit_id": deposit_id,
        "status": deposit.status.value,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
        "order_id": deposit.order_id,
        "tx_hash": deposit.external_payment_id if deposit.external_payment_id else None
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


@router.get("/check-status/{deposit_id}")
async def get_payment_status(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Get payment status and details for a deposit
    """
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "deposit_id": deposit.id,
        "status": deposit.status.value,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
        "order_id": deposit.order_id,
        "tx_hash": deposit.external_payment_id if deposit.external_payment_id else None,
        "amount": float(deposit.amount) if deposit.amount else 0,
        "currency": deposit.currency or "usd",
        "contract_address": settings.BSC_PAYMENT_CONTRACT,
        "token_address": settings.BSC_USDT_ADDRESS,
        "chain_id": settings.BSC_CHAIN_ID
    }


@router.get("/invoice/{deposit_id}", response_class=HTMLResponse)
async def get_invoice(
    deposit_id: int,
    token: Optional[str] = None,
    lang: Optional[str] = "fr",
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user_optional)
):
    """
    Generate an invoice for a validated deposit.
    Returns HTML that can be printed/saved as PDF.
    Accepts token as query parameter for direct browser access.
    """
    # If token is provided as query param, decode it manually
    if token and not current_user:
        from jose import jwt, JWTError
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                current_user = db.query(User).filter(User.id == int(user_id)).first()
        except JWTError:
            pass
    
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if deposit.status != DepositStatus.VALIDATED:
        raise HTTPException(status_code=400, detail="Invoice only available for validated payments")
    
    # Use user's preferred language if no lang parameter provided
    user_lang = lang or getattr(current_user, 'preferred_language', 'fr') or 'fr'
    
    # Get product info
    product = db.query(ProductType).filter(ProductType.id == deposit.product_type_id).first()
    product_name = product.name if product else "Service"
    
    # Translations
    translations = {
        "fr": {
            "invoice": "FACTURE",
            "invoice_number": "N°",
            "date": "Date",
            "paid": "PAYÉ",
            "billed_to": "Facturé à",
            "issuer": "Émetteur",
            "description": "Description",
            "quantity": "Quantité",
            "unit_price": "Prix unitaire",
            "total": "Total",
            "subtotal": "Sous-total",
            "vat": "TVA (0%)",
            "thank_you": "Merci pour votre confiance!",
            "payment_method": "Paiement effectué par cryptomonnaie",
            "reference": "Référence",
            "online_services": "Services en ligne"
        },
        "en": {
            "invoice": "INVOICE",
            "invoice_number": "No.",
            "date": "Date",
            "paid": "PAID",
            "billed_to": "Billed to",
            "issuer": "Issuer",
            "description": "Description",
            "quantity": "Quantity",
            "unit_price": "Unit price",
            "total": "Total",
            "subtotal": "Subtotal",
            "vat": "VAT (0%)",
            "thank_you": "Thank you for your trust!",
            "payment_method": "Payment made by cryptocurrency",
            "reference": "Reference",
            "online_services": "Online services"
        },
        "es": {
            "invoice": "FACTURA",
            "invoice_number": "N°",
            "date": "Fecha",
            "paid": "PAGADO",
            "billed_to": "Facturado a",
            "issuer": "Emisor",
            "description": "Descripción",
            "quantity": "Cantidad",
            "unit_price": "Precio unitario",
            "total": "Total",
            "subtotal": "Subtotal",
            "vat": "IVA (0%)",
            "thank_you": "¡Gracias por su confianza!",
            "payment_method": "Pago realizado con criptomoneda",
            "reference": "Referencia",
            "online_services": "Servicios en línea"
        },
        "de": {
            "invoice": "RECHNUNG",
            "invoice_number": "Nr.",
            "date": "Datum",
            "paid": "BEZAHLT",
            "billed_to": "Rechnungsempfänger",
            "issuer": "Aussteller",
            "description": "Beschreibung",
            "quantity": "Menge",
            "unit_price": "Einzelpreis",
            "total": "Gesamt",
            "subtotal": "Zwischensumme",
            "vat": "MwSt. (0%)",
            "thank_you": "Vielen Dank für Ihr Vertrauen!",
            "payment_method": "Zahlung per Kryptowährung",
            "reference": "Referenz",
            "online_services": "Online-Dienste"
        }
    }
    
    t = translations.get(user_lang, translations["fr"])
    
    # Generate invoice HTML
    invoice_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{t["invoice"]} #{deposit.id}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 40px; color: #333; }}
            .invoice {{ max-width: 800px; margin: 0 auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 40px; padding-bottom: 20px; border-bottom: 2px solid #1e40af; }}
            .logo {{ font-size: 28px; font-weight: bold; color: #1e40af; }}
            .invoice-info {{ text-align: right; }}
            .invoice-info h2 {{ font-size: 24px; color: #1e40af; margin-bottom: 5px; }}
            .invoice-info p {{ color: #666; font-size: 14px; }}
            .parties {{ display: flex; justify-content: space-between; margin-bottom: 40px; }}
            .party {{ width: 45%; }}
            .party h3 {{ font-size: 12px; color: #666; text-transform: uppercase; margin-bottom: 10px; }}
            .party p {{ font-size: 14px; line-height: 1.6; }}
            .items {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
            .items th {{ background: #f8f9fa; padding: 12px; text-align: left; font-size: 12px; text-transform: uppercase; color: #666; border-bottom: 2px solid #e9ecef; }}
            .items td {{ padding: 15px 12px; border-bottom: 1px solid #e9ecef; }}
            .items .amount {{ text-align: right; }}
            .total {{ text-align: right; margin-top: 20px; }}
            .total-row {{ display: flex; justify-content: flex-end; gap: 40px; padding: 10px 0; }}
            .total-row.final {{ font-size: 18px; font-weight: bold; color: #1e40af; border-top: 2px solid #1e40af; padding-top: 15px; }}
            .footer {{ margin-top: 60px; padding-top: 20px; border-top: 1px solid #e9ecef; text-align: center; color: #666; font-size: 12px; }}
            .status {{ display: inline-block; padding: 5px 15px; background: #d4edda; color: #155724; border-radius: 20px; font-size: 12px; font-weight: 600; }}
            @media print {{ body {{ padding: 20px; }} }}
        </style>
    </head>
    <body>
        <div class="invoice">
            <div class="header">
                <div class="logo">MyHigh5</div>
                <div class="invoice-info">
                    <h2>{t["invoice"]}</h2>
                    <p>{t["invoice_number"]} {deposit.id:06d}</p>
                    <p>{t["date"]}: {deposit.validated_at.strftime('%d/%m/%Y') if deposit.validated_at else deposit.created_at.strftime('%d/%m/%Y')}</p>
                    <span class="status">{t["paid"]}</span>
                </div>
            </div>
            
            <div class="parties">
                <div class="party">
                    <h3>{t["billed_to"]}</h3>
                    <p><strong>{current_user.full_name or current_user.username}</strong></p>
                    <p>{current_user.email}</p>
                </div>
                <div class="party">
                    <h3>{t["issuer"]}</h3>
                    <p><strong>MyHigh5</strong></p>
                    <p>{t["online_services"]}</p>
                    <p>infos@myhigh5.com</p>
                </div>
            </div>
            
            <table class="items">
                <thead>
                    <tr>
                        <th>{t["description"]}</th>
                        <th>{t["quantity"]}</th>
                        <th class="amount">{t["unit_price"]}</th>
                        <th class="amount">{t["total"]}</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>{product_name}</td>
                        <td>1</td>
                        <td class="amount">${float(deposit.amount):.2f}</td>
                        <td class="amount">${float(deposit.amount):.2f}</td>
                    </tr>
                </tbody>
            </table>
            
            <div class="total">
                <div class="total-row">
                    <span>{t["subtotal"]}:</span>
                    <span>${float(deposit.amount):.2f}</span>
                </div>
                <div class="total-row">
                    <span>{t["vat"]}:</span>
                    <span>$0.00</span>
                </div>
                <div class="total-row final">
                    <span>{t["total"]}:</span>
                    <span>${float(deposit.amount):.2f} USD</span>
                </div>
            </div>
            
            <div class="footer">
                <p>{t["thank_you"]}</p>
                <p style="margin-top: 10px;">{t["payment_method"]}</p>
                <p style="margin-top: 5px;">{t["reference"]}: {deposit.external_payment_id or deposit.id}</p>
            </div>
        </div>
        <script>window.print();</script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=invoice_html)
