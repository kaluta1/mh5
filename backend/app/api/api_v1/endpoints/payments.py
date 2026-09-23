"""
Payment API Endpoints — NOWPayments crypto checkout.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal
import hashlib
import logging

from app.api import deps
from app.models.user import User
from app.models.payment import Deposit, DepositStatus, ProductType
from app.services.nowpayments_service import (
    NowPaymentsError,
    build_order_id,
    create_payment as now_create_payment,
    deposit_status_payload,
    get_available_currencies,
    normalize_pay_currency,
    sync_deposit_with_provider,
)
from app.core.config import settings
from app.crud import crud_deposit
from app.services.financial_integrity import (
    FinancialIntegrityError,
    authoritative_product_terms,
    validate_client_purchase_terms,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_SYNCABLE_DEPOSIT_STATUSES = (DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID)


def _should_sync_deposit_with_provider(deposit: Deposit) -> bool:
    return bool(deposit.external_payment_id and deposit.status in _SYNCABLE_DEPOSIT_STATUSES)


class PaymentRecipient(BaseModel):
    username_or_email: str
    product_code: str
    amount: Decimal = Field(gt=0)


class CreatePaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: str = "usd"
    product_code: str
    pay_currency: Optional[str] = None
    recipients: Optional[list[PaymentRecipient]] = None


class PaymentResponse(BaseModel):
    deposit_id: int
    order_id: str
    payment_id: str
    payment_status: str
    pay_address: str
    pay_amount: str
    pay_currency: str
    price_amount: float
    price_currency: str
    invoice_url: Optional[str] = None
    status: str


def _idempotent_order_id(user_id: int, key: str) -> str:
    normalized = key.strip()
    if not normalized or len(normalized) > 128:
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    digest = hashlib.sha256(f"{user_id}:{normalized}".encode("utf-8")).hexdigest()[:40]
    return f"mh5-idem-{digest}"


def _stored_payment_response(deposit: Deposit) -> PaymentResponse:
    return PaymentResponse(
        deposit_id=deposit.id,
        order_id=deposit.order_id or "",
        payment_id=deposit.external_payment_id or "",
        payment_status=deposit.status.value,
        pay_address=deposit.payment_address or "",
        pay_amount=deposit.crypto_amount or "",
        pay_currency=(deposit.crypto_currency or "").lower(),
        price_amount=float(deposit.amount),
        price_currency=(deposit.currency or "USD").lower(),
        invoice_url=None,
        status=deposit.status.value,
    )


@router.get("/verify-user")
async def verify_user_exists(
    username_or_email: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Check if a user exists by username or email."""
    user = db.query(User).filter(
        (User.username == username_or_email) | (User.email == username_or_email)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "username": user.username or user.email.split("@")[0],
        "email": user.email,
        "display_name": user.full_name or user.username or user.email.split("@")[0],
    }


@router.get("/currencies")
async def get_payment_currencies():
    """List cryptocurrencies available via NOWPayments."""
    try:
        currencies = await get_available_currencies()
        if not currencies:
            default = (settings.NOWPAYMENTS_DEFAULT_PAY_CURRENCY or "usdtbsc").lower()
            return {"currencies": [default]}
        return {"currencies": currencies}
    except NowPaymentsError as exc:
        logger.error("NOWPayments currencies error: %s", exc)
        default = (settings.NOWPAYMENTS_DEFAULT_PAY_CURRENCY or "usdtbsc").lower()
        return {"currencies": [default]}


@router.post("/create", response_model=PaymentResponse)
async def create_payment(
    request: CreatePaymentRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """Create a NOWPayments invoice and local pending deposit."""
    product_code = request.product_code.strip().lower()
    product = crud_deposit.product_type.get_by_code(db, code=product_code)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    from app.services.legacy_business_model import (
        RETIRED_MESSAGE,
        is_legacy_founding_product,
        legacy_business_model_enabled,
    )

    if is_legacy_founding_product(product_code) and not legacy_business_model_enabled():
        raise HTTPException(status_code=410, detail=f"Founding membership enrollment: {RETIRED_MESSAGE}")

    try:
        expected_amount, expected_currency = authoritative_product_terms(product)
        validate_client_purchase_terms(
            submitted_amount=request.amount,
            submitted_currency=request.currency,
            expected_amount=expected_amount,
            expected_currency=expected_currency,
        )
        if request.recipients:
            if len(request.recipients) != 1:
                raise FinancialIntegrityError(
                    "Multi-recipient checkout is unavailable until orders have item-level accounting"
                )
            recipient = request.recipients[0]
            identity = recipient.username_or_email.strip().lower()
            own_identities = {
                str(current_user.email or "").strip().lower(),
                str(current_user.username or "").strip().lower(),
            }
            if identity not in own_identities:
                raise FinancialIntegrityError(
                    "Third-party purchases are unavailable until payer and beneficiary are audited separately"
                )
            if recipient.product_code.strip().lower() != product_code:
                raise FinancialIntegrityError("Recipient product does not match the order product")
            validate_client_purchase_terms(
                submitted_amount=recipient.amount,
                submitted_currency=request.currency,
                expected_amount=expected_amount,
                expected_currency=expected_currency,
            )
    except FinancialIntegrityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    order_id = _idempotent_order_id(current_user.id, idempotency_key) if idempotency_key else build_order_id()
    existing = crud_deposit.deposit.get_by_order_id(db, order_id=order_id)
    if existing:
        if (
            existing.user_id != current_user.id
            or existing.product_type_id != product.id
            or Decimal(str(existing.amount)) != expected_amount
        ):
            raise HTTPException(status_code=409, detail="Idempotency key is already used for another order")
        if not existing.external_payment_id:
            raise HTTPException(status_code=409, detail="Payment creation is already in progress")
        return _stored_payment_response(existing)

    pay_currency = normalize_pay_currency(
        request.pay_currency
        or settings.NOWPAYMENTS_DEFAULT_PAY_CURRENCY
        or "usdtbsc"
    ) or "usdtbsc"

    deposit = Deposit(
        user_id=current_user.id,
        product_type_id=product.id,
        amount=expected_amount,
        currency=expected_currency,
        order_id=order_id,
        status=DepositStatus.PENDING,
    )
    db.add(deposit)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = crud_deposit.deposit.get_by_order_id(db, order_id=order_id)
        if duplicate and duplicate.external_payment_id:
            return _stored_payment_response(duplicate)
        raise HTTPException(status_code=409, detail="Payment creation is already in progress") from exc
    db.refresh(deposit)
    deposit_id = int(deposit.id)
    order_description = f"MyHigh5 {product.name} — deposit {deposit_id}"
    # Commit/refresh starts a new read transaction; release it before the
    # bounded provider call so Neon never sees an idle transaction here.
    db.rollback()

    try:
        provider_payload = await now_create_payment(
            price_amount=expected_amount,
            price_currency=expected_currency,
            order_id=order_id,
            order_description=order_description,
            pay_currency=pay_currency,
            success_url=f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/wallet?payment=success",
            cancel_url=f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/wallet?payment=cancelled",
        )
    except NowPaymentsError as exc:
        deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
        deposit.status = DepositStatus.FAILED
        db.commit()
        logger.error("NOWPayments create error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
        deposit.status = DepositStatus.FAILED
        db.commit()
        logger.error("Payment creation error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
    deposit.external_payment_id = str(provider_payload.get("payment_id") or "")
    deposit.payment_address = provider_payload.get("pay_address")
    deposit.crypto_amount = (
        str(provider_payload.get("pay_amount"))
        if provider_payload.get("pay_amount") is not None
        else None
    )
    deposit.crypto_currency = (
        str(provider_payload.get("pay_currency")).upper()
        if provider_payload.get("pay_currency")
        else pay_currency.upper()
    )
    db.commit()
    db.refresh(deposit)

    status_payload = deposit_status_payload(deposit, provider_payload)
    return PaymentResponse(
        deposit_id=deposit.id,
        order_id=order_id,
        payment_id=deposit.external_payment_id or "",
        payment_status=str(provider_payload.get("payment_status") or "waiting"),
        pay_address=str(status_payload.get("pay_address") or ""),
        pay_amount=str(status_payload.get("pay_amount") or ""),
        pay_currency=str(status_payload.get("pay_currency") or pay_currency),
        price_amount=float(expected_amount),
        price_currency=expected_currency,
        invoice_url=provider_payload.get("invoice_url"),
        status="pending",
    )


@router.post("/sync/{deposit_id}")
async def sync_payment(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Poll NOWPayments and update local deposit status (manual refresh / I've paid button)."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        payload = await sync_deposit_with_provider(db, deposit)
        db.commit()
        return payload
    except NowPaymentsError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/check/{deposit_id}")
async def check_payment_status(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Check payment status by deposit ID."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    if _should_sync_deposit_with_provider(deposit):
        try:
            payload = await sync_deposit_with_provider(db, deposit)
            db.commit()
            return {
                "deposit_id": deposit_id,
                "status": payload["status"],
                "is_confirmed": payload["is_confirmed"],
                "order_id": deposit.order_id,
                "payment_id": deposit.external_payment_id,
            }
        except NowPaymentsError:
            db.rollback()

    return {
        "deposit_id": deposit_id,
        "status": deposit.status.value,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
        "order_id": deposit.order_id,
        "payment_id": deposit.external_payment_id,
    }


@router.get("/deposit/{deposit_id}")
async def get_deposit_status(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Get the current status of a deposit."""
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
        "validated_at": deposit.validated_at.isoformat() if deposit.validated_at else None,
    }


@router.get("/check-status/{deposit_id}")
async def get_payment_status(
    deposit_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Get payment status and NOWPayments pay-in details for a deposit."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    if _should_sync_deposit_with_provider(deposit):
        try:
            payload = await sync_deposit_with_provider(db, deposit)
            db.commit()
            return payload
        except NowPaymentsError as exc:
            db.rollback()
            logger.warning("NOWPayments sync failed for deposit %s: %s", deposit_id, exc)

    return deposit_status_payload(deposit)


@router.get("/invoice/{deposit_id}", response_class=HTMLResponse)
async def get_invoice(
    deposit_id: int,
    lang: Optional[str] = "fr",
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Generate an invoice for a validated deposit."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    if deposit.status != DepositStatus.VALIDATED:
        raise HTTPException(status_code=400, detail="Invoice only available for validated payments")

    from app.services.invoice_renderer import render_invoice_html

    user_lang = lang or getattr(current_user, "preferred_language", "fr") or "fr"
    product = db.query(ProductType).filter(ProductType.id == deposit.product_type_id).first()
    product_name = product.name if product else "Service"
    billed_user = deposit.user or current_user

    invoice_html = render_invoice_html(
        deposit,
        billed_user=billed_user,
        product_name=product_name,
        lang=user_lang,
        include_print_script=True,
    )
    return HTMLResponse(content=invoice_html)
