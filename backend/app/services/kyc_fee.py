"""The Member KYC Verification Fee.

ONE figure: what a member pays MyHigh5 for one verification attempt, in USD.
It is the price of the existing `kyc` product (product_types), the same row
the payment flow already charges from, so nothing here is a second price list.
What the KYC provider charges MyHigh5 is not configured, stored or calculated
anywhere in this module.

Rules:
  * 0 means KYC is free: an attempt starts without a payment, and no KYC
    payment can be created. A paid, unused KYC payment the member already
    holds is NOT used for a free attempt: it stays paid and unused (nothing
    about it changes) and opens a later attempt if the fee is no longer 0.
  * A payment keeps the amount it was created with (deposits.amount). Changing
    the fee never re-prices a payment that exists, paid or not, and a paid,
    unused payment still opens one attempt whatever the (non-zero) fee is now.
  * Retry: every NEW attempt (after a rejection or a review) costs the fee in
    force when that attempt is paid for; it is free while the fee is 0.
    Continuing an open attempt, or replacing a provider session that ran out,
    costs nothing and is not a new attempt (app.services.kyc_settings limits
    the sessions of one attempt). The attempt limit (max_attempts) applies.
  * One payment at a time: a member who already holds a paid, unused KYC
    payment, has a KYC payment in progress, has an attempt open, or is verified
    cannot be charged again. Requests arriving together are decided one after
    the other (the member's row is locked while a payment is being created).

A change needs the explicit `manage_kyc_settings` permission and the
administrator's current password, and writes one audit_trails row.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.kyc import KYCStatus, KYCVerification
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User

PRODUCT_CODE = "kyc"
DEFAULT_FEE = Decimal("10.00")          # used only when the product row does not exist
MAX_FEE = Decimal("1000.00")
AUDIT_ACTION = "KYC_MEMBER_FEE_CHANGED"
RETRY_POLICY = ("Each new verification attempt costs the fee shown when you pay for it. "
                "Continuing an attempt you already started, or renewing a verification link that expired, "
                "costs nothing.")
_CENT = Decimal("0.01")
# An invoice nobody paid is closed one hour after it was created (the existing
# policy of payment_scheduler). Until then it counts as a payment in progress.
OPEN_INVOICE_WINDOW = timedelta(hours=1)


class KycFeeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _product(db: Session, *, lock: bool = False) -> Optional[ProductType]:
    query = db.query(ProductType).filter(ProductType.code == PRODUCT_CODE)
    if lock:
        query = query.with_for_update().populate_existing()
    return query.first()


def member_fee(db: Session) -> Tuple[Decimal, str]:
    """(amount, currency) a member pays for one new attempt, now."""
    product = _product(db)
    if product is None or product.price is None:
        return DEFAULT_FEE, "USD"
    return Decimal(str(product.price)).quantize(_CENT), (product.currency or "USD").upper()


def is_free(db: Session) -> bool:
    return member_fee(db)[0] <= 0


def fee_view(db: Session) -> dict:
    amount, currency = member_fee(db)
    return {"amount": f"{amount:.2f}", "currency": currency, "is_free": amount <= 0,
            "retry_policy": RETRY_POLICY}


def parse_fee(value: Any) -> Decimal:
    """A fee an administrator typed: 0 to MAX_FEE, at most two decimals."""
    if isinstance(value, bool) or value is None:
        raise KycFeeError("INVALID_VALUE", "Enter the fee as a number.")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise KycFeeError("INVALID_VALUE", "Enter the fee as a number.") from None
    if not amount.is_finite():
        raise KycFeeError("INVALID_VALUE", "Enter the fee as a number.")
    if amount < 0:
        raise KycFeeError("INVALID_VALUE", "The fee cannot be negative. Use 0 for free KYC.")
    if amount > MAX_FEE:
        raise KycFeeError("INVALID_VALUE", f"The fee cannot be more than {MAX_FEE:.2f} USD.")
    if amount != amount.quantize(_CENT):
        raise KycFeeError("INVALID_VALUE", "The fee has at most two decimals.")
    return amount.quantize(_CENT)


def set_member_fee(db: Session, actor, value: Any, *, password: Optional[str], ip: Optional[str] = None,
                   expected_amount: Any = None) -> dict:
    """Change the fee for attempts paid from now on. Payments that exist keep their amount."""
    from app.services import admin_security, payment_config

    if not payment_config.has_permission(actor, admin_security.PERMISSION_MANAGE_KYC):
        raise KycFeeError("FORBIDDEN", f"The {admin_security.PERMISSION_MANAGE_KYC} permission is required.")
    amount = parse_fee(value)
    try:
        payment_config.require_reauth(actor, password)
    except payment_config.PaymentConfigError as exc:
        raise KycFeeError(exc.code, str(exc)) from None

    product = _product(db, lock=True)
    if product is None:
        db.rollback()
        raise KycFeeError("PRODUCT_MISSING", "The KYC product is not set up on this server. Nothing was changed.")
    current = Decimal(str(product.price)).quantize(_CENT)
    if expected_amount is not None and parse_fee(expected_amount) != current:
        db.rollback()
        raise KycFeeError("STALE", "The fee was changed by somebody else. Reload and try again.")
    if amount != current:
        product.price = amount
        db.add(AuditTrail(table_name="product_types", record_id=int(product.id), action=AUDIT_ACTION,
                          old_values={"price": f"{current:.2f}"}, new_values={"price": f"{amount:.2f}"},
                          user_id=getattr(actor, "id", None), ip_address=(ip or None)))
    db.commit()
    return fee_view(db)


def last_change(db: Session) -> Optional[dict]:
    row = (db.query(AuditTrail).filter(AuditTrail.action == AUDIT_ACTION)
           .order_by(AuditTrail.id.desc()).first())
    if row is None:
        return None
    return {"at": row.timestamp.isoformat() if row.timestamp else None, "by_user_id": row.user_id,
            "old_amount": (row.old_values or {}).get("price"), "new_amount": (row.new_values or {}).get("price")}


def payment_refusal(db: Session, user_id: int, *, lock: bool = False,
                    now: Optional[datetime] = None) -> Optional[Tuple[str, str]]:
    """Why a NEW KYC payment must not be created for this member, as (code,
    message); None when one may be. A member is never charged for an attempt
    they do not need or already hold.

    `lock` holds the member's row until the caller commits: with it, two
    requests arriving together are decided one after the other, and the second
    sees the payment the first created."""
    if lock:
        db.query(User.id).filter(User.id == user_id).with_for_update().first()
    if is_free(db):
        return "KYC_FEE_NOT_REQUIRED", "Identity verification is free. No payment is needed."
    verification = db.query(KYCVerification).filter(KYCVerification.user_id == user_id).first()
    if verification is not None:
        if verification.status in (KYCStatus.APPROVED, KYCStatus.PENDING_PROOF_OF_ADDRESS):
            return "KYC_ALREADY_VERIFIED", "Your identity is already verified. No payment is needed."
        # EXPIRED: the provider session ran out; the attempt itself is still open (renewed for free).
        if verification.status in (KYCStatus.PENDING, KYCStatus.IN_PROGRESS, KYCStatus.EXPIRED):
            return "KYC_ATTEMPT_OPEN", "You already have a verification in progress. No new payment is needed."
        if (verification.attempts_count or 0) >= (verification.max_attempts or 0):
            return "KYC_ATTEMPTS_EXHAUSTED", "You have used every verification attempt. Please contact support."
    from app.crud import crud_deposit

    if crud_deposit.deposit.get_valid_deposit_for_product(db, user_id=user_id, product_code=PRODUCT_CODE):
        return "KYC_ALREADY_PAID", "You already paid for a verification attempt that you have not used yet."
    product = _product(db)
    if product is not None:
        recent = (now or datetime.utcnow()) - OPEN_INVOICE_WINDOW
        in_progress = (db.query(Deposit.id)
                       .filter(Deposit.user_id == user_id, Deposit.product_type_id == product.id)
                       .filter((Deposit.status == DepositStatus.PARTIALLY_PAID)
                               | ((Deposit.status == DepositStatus.PENDING) & (Deposit.created_at >= recent)))
                       .first())
        if in_progress is not None:
            return ("KYC_PAYMENT_IN_PROGRESS",
                    "You already have a KYC payment in progress. Complete it from your wallet, "
                    "or start a new one after it expires (one hour).")
    return None


def attempt_fee_note(deposit: Optional[Deposit]) -> str:
    """What the attempt that is starting cost, for the verification's audit log."""
    if deposit is None:
        return "no fee (member KYC fee was 0; no paid KYC payment was used)"
    return f"paid with deposit {deposit.id}: {Decimal(str(deposit.amount)):.2f} {(deposit.currency or 'USD').upper()}"
