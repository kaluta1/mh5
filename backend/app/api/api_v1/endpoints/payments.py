"""
Payment API Endpoints — member checkout through NOWPayments or SoncoPay.

The gateway of a NEW payment is checkout_routing.new_payment_gateway: SoncoPay
when it is the ready default, otherwise NOWPayments while its checkout is
allowed, otherwise none (the member is told payments are unavailable; no
deposit is created). It is written on the deposit and never changes: every
later read of that deposit (sync, check, scheduler, webhook) uses the same
gateway, whatever the switches say.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
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
from app.services import checkout_routing, kyc_fee, soncopay_payments, soncopay_settings
from app.services.soncopay_client import SoncoPayError
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
from app.core.rate_limit import _is_rate_limited
from app.crud import crud_deposit
from app.services.financial_integrity import (
    FinancialIntegrityError,
    authoritative_product_terms,
    validate_client_purchase_terms,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_SYNCABLE_DEPOSIT_STATUSES = (DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID)
PAYMENT_PROVIDER_UNAVAILABLE = "The payment provider could not process this request. Please try again in a few minutes."
CHECKOUT_UNAVAILABLE = {"code": "CHECKOUT_UNAVAILABLE", "message": checkout_routing.UNAVAILABLE_MESSAGE}


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
    # nowpayments: pay_address/pay_amount are shown. soncopay: the member continues on checkout_url.
    provider: str = "nowpayments"
    checkout_url: Optional[str] = None


def _idempotent_order_id(user_id: int, key: str) -> str:
    normalized = key.strip()
    if not normalized or len(normalized) > 128:
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    digest = hashlib.sha256(f"{user_id}:{normalized}".encode("utf-8")).hexdigest()[:40]
    return f"mh5-idem-{digest}"


def _stored_payment_response(deposit: Deposit) -> PaymentResponse:
    if soncopay_payments.is_soncopay(deposit):
        return _soncopay_response(deposit)
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


def _soncopay_response(deposit: Deposit) -> PaymentResponse:
    return PaymentResponse(
        deposit_id=deposit.id,
        order_id=deposit.order_id or "",
        payment_id=deposit.external_payment_id or "",
        payment_status=deposit.provider_status or deposit.status.value,
        pay_address="",
        pay_amount="",
        pay_currency="",
        price_amount=float(deposit.amount),
        price_currency=(deposit.currency or "USD").lower(),
        invoice_url=deposit.provider_checkout_url,
        status=deposit.status.value,
        provider="soncopay",
        checkout_url=deposit.provider_checkout_url,
    )


async def _attach_soncopay_checkout(db: Session, deposit_id: int, description: str) -> PaymentResponse:
    """Create the SoncoPay payment of a SoncoPay deposit (or find it again: the
    same order_id returns the same payment). On any failure the deposit is
    marked failed and the member gets a fixed sentence."""
    try:
        deposit = await soncopay_payments.create_checkout(db, deposit_id, description=description)
        db.commit()
    except (SoncoPayError, FinancialIntegrityError) as exc:
        db.rollback()
        deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
        if deposit.status == DepositStatus.PENDING and not deposit.external_payment_id:
            deposit.status = DepositStatus.FAILED
        db.commit()
        logger.error("SoncoPay checkout for deposit %s failed (%s)", deposit_id, type(exc).__name__)
        raise HTTPException(status_code=502, detail=PAYMENT_PROVIDER_UNAVAILABLE) from exc
    db.refresh(deposit)
    return _soncopay_response(deposit)


@router.get("/checkout-gateway")
async def checkout_gateway(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Which gateway a new payment uses now, so the payment dialog shows the right step.
    "none" (available false) when no gateway can take a new payment."""
    gateway = checkout_routing.new_payment_gateway(db)
    if gateway is None:
        return {"provider": "none", "available": False, "message": checkout_routing.UNAVAILABLE_MESSAGE}
    return {"provider": gateway, "available": True}


# Recipient confirmation in the purchase dialog. A signed-in member may check
# a handful of names; nobody may walk the member list with it.
VERIFY_USER_LIMIT, VERIFY_USER_WINDOW = 30, 600        # lookups per member per 10 minutes


@router.get("/verify-user")
async def verify_user_exists(
    username_or_email: str = Query(..., min_length=1, max_length=254),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Confirm that the member a purchase is meant for exists.

    Returns ONLY what the purchase dialog shows to confirm the recipient: the
    public username and display name. Never another member's email address or
    internal id, and never an email-derived name."""
    if _is_rate_limited(f"payments-verify-user:{current_user.id}", VERIFY_USER_LIMIT, VERIFY_USER_WINDOW):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many lookups. Please try again in a few minutes.")
    wanted = username_or_email.strip()
    if not wanted or any(ord(ch) < 32 for ch in wanted):
        raise HTTPException(status_code=404, detail="User not found")
    user = db.query(User).filter((User.username == wanted) | (User.email == wanted)).first()

    if not user or not user.is_active or getattr(user, "is_deleted", False):
        raise HTTPException(status_code=404, detail="User not found")

    is_self = user.id == current_user.id
    # A member without a username is shown a neutral label, not a piece of their email address.
    username = user.username or (user.email.split("@")[0] if is_self else "member")
    return {
        "username": username,
        "display_name": user.full_name or username,
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

    from app.services.new_model_reference_data import REFERRAL_POOL_PRODUCT_CODE
    from app.services.referral_pool_service import RETIRED_MESSAGE as POOL_RETIRED_MESSAGE

    if product_code == REFERRAL_POOL_PRODUCT_CODE:
        # Retired 2026-09-28: no deposit, seat or provider invoice is created.
        raise HTTPException(status_code=410, detail=POOL_RETIRED_MESSAGE)

    if product_code in kyc_fee.RETIRED_KYC_PRODUCT_CODES:
        # One KYC product is sold (kyc_fee.PRODUCT_CODE, priced by the member KYC fee).
        # The older product would take a different price for the same verification.
        raise HTTPException(status_code=409, detail={
            "code": "KYC_PRODUCT_NOT_SOLD",
            "message": "This product is not sold. Pay the identity verification fee from the KYC page."})

    if product_code == kyc_fee.PRODUCT_CODE and kyc_fee.is_free(db):
        # Free KYC: there is nothing to pay, so no deposit and no provider invoice.
        raise HTTPException(status_code=409, detail={
            "code": "KYC_FEE_NOT_REQUIRED", "message": "Identity verification is free. No payment is needed."})

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
            if soncopay_payments.is_soncopay(existing) and existing.status == DepositStatus.FAILED:
                # SoncoPay returns the same payment for the same order_id: a retry is safe.
                return await _attach_soncopay_checkout(
                    db, int(existing.id), f"MyHigh5 {product.name} - deposit {int(existing.id)}")
            raise HTTPException(status_code=409, detail="Payment creation is already in progress")
        return _stored_payment_response(existing)

    # No gateway can take a NEW payment: refused before anything is created or any provider is contacted
    # (no deposit, no seat, no KYC lock). An idempotent replay above is answered as before.
    if checkout_routing.new_payment_gateway(db) is None:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=CHECKOUT_UNAVAILABLE)

    # Child/Teen Safety Phase 10: a NEW payment (deposit row, seat reservation,
    # provider invoice) only for a member the central gate allows. An idempotent
    # replay above creates nothing new and is answered as before.
    from app.services.financial_eligibility import FinancialEligibilityHold, FinancialOperation, http_error, require

    try:
        require(db, current_user, FinancialOperation.PAYMENT, subject={"product_code": product_code})
    except FinancialEligibilityHold as exc:
        raise http_error(exc) from None

    pay_currency = normalize_pay_currency(
        request.pay_currency
        or settings.NOWPAYMENTS_DEFAULT_PAY_CURRENCY
        or "usdtbsc"
    ) or "usdtbsc"

    from app.services.new_model_ledger import model_version_for_new_event

    if product_code == kyc_fee.PRODUCT_CODE:
        # A NEW KYC payment only for an attempt the member needs and does not
        # already hold or is not already paying for (an idempotent replay above
        # is answered as before). The member's row stays locked until the
        # deposit below is committed: two requests arriving together cannot
        # both create one.
        refusal = kyc_fee.payment_refusal(db, current_user.id, lock=True)
        if refusal:
            db.rollback()
            raise HTTPException(status_code=409, detail={"code": refusal[0], "message": refusal[1]})

    # The gateway is chosen ONCE, here, and stays with the deposit (decided again: a switch may have moved).
    gateway = checkout_routing.new_payment_gateway(db)
    environment = soncopay_settings.checkout_environment(db) if gateway == "soncopay" else None
    if gateway is None or (gateway == "soncopay" and environment is None):
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=CHECKOUT_UNAVAILABLE)
    deposit = Deposit(
        user_id=current_user.id,
        product_type_id=product.id,
        amount=expected_amount,
        currency=expected_currency,
        order_id=order_id,
        status=DepositStatus.PENDING,
        # Stamped once at creation: decides old vs new business model deterministically.
        business_model_version=model_version_for_new_event(db),
        payment_provider=gateway,
        provider_environment=environment,
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
    # ASCII only: the provider echoes this text in its signed callbacks, and a
    # non-ASCII character is serialized differently by different JSON writers.
    order_description = f"MyHigh5 {product.name} - deposit {deposit_id}".encode("ascii", "replace").decode("ascii")
    # Commit/refresh starts a new read transaction; release it before the
    # bounded provider call so Neon never sees an idle transaction here.
    db.rollback()

    if gateway == "soncopay":
        return await _attach_soncopay_checkout(db, deposit_id, order_description)

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
        # The provider's own answer stays in the server log; the member gets a fixed sentence.
        raise HTTPException(status_code=502, detail=PAYMENT_PROVIDER_UNAVAILABLE) from exc
    except Exception as exc:
        deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
        deposit.status = DepositStatus.FAILED
        db.commit()
        logger.error("Payment creation error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=PAYMENT_PROVIDER_UNAVAILABLE) from exc

    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
    provider_payment_id = str(provider_payload.get("payment_id") or "")
    if (db.query(Deposit.id).filter(Deposit.external_payment_id == provider_payment_id,
                                    Deposit.id != deposit_id).first()) is not None:
        # One provider payment belongs to one deposit. Never attach it twice.
        deposit.status = DepositStatus.FAILED
        db.commit()
        logger.error("NOWPayments returned a payment id that another deposit already holds (deposit %s)", deposit_id)
        raise HTTPException(status_code=502, detail=PAYMENT_PROVIDER_UNAVAILABLE)
    deposit.external_payment_id = provider_payment_id
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
    """Ask the deposit's gateway and update the local deposit status (manual refresh / I've paid button)."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    if soncopay_payments.is_soncopay(deposit):
        try:
            return await soncopay_payments.sync_deposit(db, deposit)
        except SoncoPayError as exc:
            db.rollback()
            logger.warning("SoncoPay sync failed for deposit %s (%s)", deposit_id, exc.stage)
            raise HTTPException(status_code=400, detail=PAYMENT_PROVIDER_UNAVAILABLE) from exc

    try:
        payload = await sync_deposit_with_provider(db, deposit)
        db.commit()
        return payload
    except NowPaymentsError as exc:
        db.rollback()
        logger.warning("NOWPayments sync failed for deposit %s: %s", deposit_id, exc)
        raise HTTPException(status_code=400, detail=PAYMENT_PROVIDER_UNAVAILABLE) from exc


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

    if soncopay_payments.is_soncopay(deposit):
        if _should_sync_deposit_with_provider(deposit):
            try:
                payload = await soncopay_payments.sync_deposit(db, deposit)
                return {"deposit_id": deposit_id, "status": payload["status"],
                        "is_confirmed": payload["is_confirmed"], "order_id": payload["order_id"],
                        "payment_id": payload["payment_id"]}
            except SoncoPayError:
                db.rollback()
                deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    elif _should_sync_deposit_with_provider(deposit):
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
    """Get payment status and pay-in details for a deposit, from its own gateway."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()

    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")

    if deposit.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    if soncopay_payments.is_soncopay(deposit):
        if _should_sync_deposit_with_provider(deposit):
            try:
                return await soncopay_payments.sync_deposit(db, deposit)
            except SoncoPayError as exc:
                db.rollback()
                logger.warning("SoncoPay sync failed for deposit %s (%s)", deposit_id, exc.stage)
                deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
        return soncopay_payments.status_payload(deposit)

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
    lang: Optional[str] = "en",
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

    user_lang = lang or getattr(current_user, "preferred_language", "en") or "en"
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


# ---------------------------------------------------------------------------
# Crypto Cashout: the member's acceptance of the network fee terms
#
# The network fee of a crypto payout is paid by the beneficiary (the provider
# takes it out of the amount). A member is paid automatically only after
# accepting that, together with the highest fee they accept. Both calls answer
# with the member's cashout summary; neither moves money or starts a payout.
# ---------------------------------------------------------------------------

class CashoutFeeTermsAccept(BaseModel):
    # The terms exactly as they were shown to the member; a mismatch is refused.
    version: int = Field(..., ge=1, le=100000)
    cap_percent: Decimal = Field(..., ge=0, le=100, max_digits=6, decimal_places=3)
    cap_usd: Decimal = Field(..., ge=0, le=100000, max_digits=12, decimal_places=2)
    accept: bool = False


FEE_TERMS_LIMIT, FEE_TERMS_WINDOW = 10, 600            # changes per member per 10 minutes


def _fee_terms_guard(user: User) -> None:
    if _is_rate_limited(f"payments-fee-terms:{user.id}", FEE_TERMS_LIMIT, FEE_TERMS_WINDOW):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many requests. Please try again in a few minutes.")


@router.post("/cashout-fee-terms/accept")
def accept_cashout_fee_terms(body: CashoutFeeTermsAccept, request: Request, db: Session = Depends(deps.get_db),
                             current_user: User = Depends(deps.get_current_user)):
    from app.core.client_ip import client_ip
    from app.services import cashout_service

    _fee_terms_guard(current_user)
    if body.accept is not True:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "ACCEPTANCE_REQUIRED", "message": "Confirm that you accept the terms."})
    try:
        cashout_service.accept_fee_terms(db, current_user, version=body.version, cap_percent=body.cap_percent,
                                         cap_usd=body.cap_usd, ip=client_ip(request))
    except cashout_service.CashoutError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"code": exc.code, "message": str(exc)}) from None
    db.refresh(current_user)
    return cashout_service.summary(db, current_user)


@router.post("/cashout-fee-terms/withdraw")
def withdraw_cashout_fee_terms(request: Request, db: Session = Depends(deps.get_db),
                               current_user: User = Depends(deps.get_current_user)):
    from app.core.client_ip import client_ip
    from app.services import cashout_service

    _fee_terms_guard(current_user)
    cashout_service.withdraw_fee_consent(db, current_user, ip=client_ip(request))
    db.refresh(current_user)
    return cashout_service.summary(db, current_user)
