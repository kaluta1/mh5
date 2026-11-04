"""Internal wallet payments (Prompt 5, 2026-11-03): pay an approved platform product with commission
earnings already recorded for the member. Not a stored-value account, not a deposit wallet, not crypto.

Source of funds (never a parallel balance): the member's affiliate_commissions rows that are APPROVED,
not reserved for a cashout or payout (payout_reference NULL), payable under the existing hold rules
(historical review hold, 14-day card chargeback hold: commission_payout_hold.payable_clause), plus the
unused remainder of a row a previous wallet payment used in part. PENDING, missed, cancelled, paid,
reserved and held rows are never spendable. USD only; no conversion.

A payment uses whole rows oldest first (remainders first); the last row may be used in part:
  * a row used in full becomes PAID (paid in kind; payout_reference 'iwp:<reference>');
  * a row used in part stays APPROVED with payout_reference 'iwp-rem'. What is left of it (its open
    amount, commission_usage.open_amount) stays available to BOTH a later wallet payment and a cashout or
    payout, whichever takes it first (2026-11-04 fix: before, a remainder could only be spent).
How much of each row a payment used is kept in internal_wallet_payment_lines.

Accounting (existing ledger, no cash): the commission liability is settled into clearing account 1050
(Dr 2001 direct / 2002 indirect, Cr 1050); the purchase is the existing payment record (deposits,
payment_provider 'internal_wallet', never SoncoPay) and is posted and fulfilled by the existing product
code with 1050 in place of cash (new_model_payments.funding_account): Dr 1050 / Cr <product account>.
1050 nets to zero. Revenue and any commission follow the product's own existing rules, once.

Concurrency: the member row is locked, then the spendable commission rows (FOR UPDATE, the same rows a
cashout locks), so a wallet payment, a cashout and an automatic payout can never use the same money.
Idempotency: (member, idempotency key) is unique; a repeat returns the first result.
Switch: settings.INTERNAL_WALLET_PAYMENTS_ENABLED (default OFF) is checked on every path.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.internal_wallet import InternalWalletPayment, InternalWalletPaymentLine
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services.commission_usage import REMAINDER_MARK, unreserved_clause, wallet_used
from app.services.financial_integrity import money

logger = logging.getLogger(__name__)

PAID_PREFIX = "iwp:"
SOURCE_TYPE = "INTERNAL_WALLET_PAYMENT"
POSTING_SETTLEMENT = "SETTLEMENT"
CLEARING_ACCOUNT = "1050"
MAX_QUANTITY = 10_000


class WalletError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def enabled() -> bool:
    return bool(getattr(settings, "INTERNAL_WALLET_PAYMENTS_ENABLED", False))


def _require_enabled() -> None:
    if not enabled():
        raise WalletError("WALLET_PAYMENTS_DISABLED", "Paying with MyHigh5 earnings is not available.", 403)


# ---------------------------------------------------------------- spendable funds (from the commission rows)

def _spendable_query(db: Session, user_id: int):
    from app.services.commission_payout_hold import payable_clause

    return (db.query(AffiliateCommission)
            .filter(AffiliateCommission.user_id == user_id,
                    AffiliateCommission.status == CommissionStatus.APPROVED,
                    unreserved_clause(),
                    payable_clause()))


def _used(db: Session, commission_ids) -> dict:
    return wallet_used(db, commission_ids)


def spendable_rows(db: Session, user_id: int, *, lock: bool = False) -> List[Tuple[AffiliateCommission, Decimal]]:
    """(row, amount still usable), remainders first, then oldest first."""
    q = _spendable_query(db, user_id).order_by(
        (AffiliateCommission.payout_reference == REMAINDER_MARK).desc().nullslast(),
        AffiliateCommission.transaction_date.asc(), AffiliateCommission.id.asc())
    rows = q.with_for_update(of=AffiliateCommission).all() if lock else q.all()
    used = _used(db, [r.id for r in rows])
    out = []
    for row in rows:
        left = money(money(row.commission_amount) - used.get(int(row.id), Decimal("0.00")))
        if left > 0:
            out.append((row, left))
    return out


def spendable_balance(db: Session, user_id: int) -> Decimal:
    return money(sum((left for _row, left in spendable_rows(db, user_id)), Decimal("0.00")))


def remainder_total(db: Session, user_id: int) -> Decimal:
    """Open amounts of rows a wallet payment used in part. Spendable AND cashable (whichever comes first);
    already included in spendable_balance and in the cashout balance, never to be added to either."""
    return money(sum((left for row, left in spendable_rows(db, user_id) if row.payout_reference == REMAINDER_MARK),
                     Decimal("0.00")))


# ---------------------------------------------------------------- product policy (one place)

@dataclass(frozen=True)
class Terms:
    product_code: str
    name: str
    quantity: int
    unit_price: Decimal
    amount: Decimal
    product_type: Optional[ProductType]
    eligible: bool
    reason: Optional[str] = None
    message: Optional[str] = None


NOT_ELIGIBLE = {
    # code: (reason, message)
    "kyc": ("NOT_APPLICABLE", "Identity verification is paid before KYC is approved; wallet payments need approved KYC."),
    "kyc_verification_fee": ("NOT_APPLICABLE", "Identity verification is paid before KYC is approved."),
    "annual_membership": ("RETIRED", "This membership is not sold."),
    "efm_membership": ("RETIRED", "This membership is not sold."),
    "mfm_membership": ("RETIRED", "This membership is not sold."),
    "founding_membership": ("RETIRED", "Founding membership is retired."),
}


def policy_overview(db: Session) -> list:
    """Every product and whether earnings may pay for it now (for administrators and the checkout)."""
    out = []
    for p in db.query(ProductType).order_by(ProductType.code.asc()).all():
        t = product_terms(db, None, p.code, 1)
        out.append({"product_code": p.code, "name": p.name, "eligible": t.eligible, "reason": t.reason,
                    "message": t.message, "unit_price": str(t.unit_price) if t.unit_price else None})
    out.append({"product_code": "annual_ads", "name": "Annual Ads", "eligible": False, "reason": "NOT_SOLD_HERE",
                "message": "Annual Ads are bought on the Annual Ads platform; integration belongs to a later phase.",
                "unit_price": None})
    out.append({"product_code": "marketplace_order", "name": "Marketplace purchases", "eligible": False,
                "reason": "SETTLEMENT_NOT_AVAILABLE",
                "message": "Marketplace payments need a contracted custodian; an internal debit is never a substitute.",
                "unit_price": None})
    return out


def product_terms(db: Session, user: Optional[User], product_code: str, quantity: int) -> Terms:
    """Server-side price and eligibility of `quantity` x `product_code`. Never trusts a client amount."""
    from app.services import ad_campaigns, referral_pool_units
    from app.services.new_model_reference_data import REFERRAL_POOL_PRODUCT_CODE

    code = (product_code or "").strip()
    product = db.query(ProductType).filter(ProductType.code == code).first()
    name = product.name if product is not None else code
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1 or quantity > MAX_QUANTITY:
        return Terms(code, name, 0, Decimal("0"), Decimal("0"), product, False, "INVALID_QUANTITY",
                     f"Choose a quantity between 1 and {MAX_QUANTITY}.")
    if product is None or not getattr(product, "is_active", True):
        return Terms(code, name, quantity, Decimal("0"), Decimal("0"), product, False, "UNKNOWN_PRODUCT",
                     "This product is not sold.")
    if (product.currency or "USD").upper() != "USD":
        return Terms(code, name, quantity, Decimal("0"), Decimal("0"), product, False, "UNSUPPORTED_CURRENCY",
                     "Only USD-priced products can be paid with earnings.")
    if code == REFERRAL_POOL_PRODUCT_CODE:
        unit = referral_pool_units.UNIT_PRICE
        if money(product.price) != unit:
            return Terms(code, name, quantity, unit, Decimal("0"), product, False, "PRICE_NOT_CONFIGURED",
                         "The Referral Pool unit price is not configured as 100.00 USD.")
        if not referral_pool_units.sales_open(db):
            return Terms(code, name, quantity, unit, money(unit * quantity), product, False, "PRODUCT_DISABLED",
                         "Referral Pool sales are not open.")
        return Terms(code, name, quantity, unit, money(unit * quantity), product, True)
    if code == ad_campaigns.AD_CREDIT_PRODUCT_CODE:
        unit = Decimal("1.00")
        cfg = ad_campaigns.get_settings(db)
        if money(product.price) != unit:
            return Terms(code, name, quantity, unit, Decimal("0"), product, False, "PRICE_NOT_CONFIGURED",
                         "Advertiser credit is not configured at a face value of 1.00 USD.")
        if not cfg.funding_enabled or ad_campaigns.pricing_state(cfg) != "CONFIGURED":
            return Terms(code, name, quantity, unit, money(unit * quantity), product, False, "PRODUCT_DISABLED",
                         "Advertiser credit cannot be bought yet.")
        return Terms(code, name, quantity, unit, money(unit * quantity), product, True)
    reason, message = NOT_ELIGIBLE.get(code, ("NOT_ELIGIBLE", "This product cannot be paid with earnings."))
    return Terms(code, name, quantity, money(product.price or 0), Decimal("0"), product, False, reason, message)


# ---------------------------------------------------------------- member eligibility

def member_check(db: Session, user: User) -> Optional[Tuple[str, str]]:
    """None when the member may spend earnings now; otherwise (code, message). KYC is the one money rule."""
    from app.services import financial_eligibility as fe
    from app.services.kyc_eligibility import is_approved

    if not is_approved(db, user.id):
        return "KYC_REQUIRED", "Approved identity verification (KYC) is required to pay with your earnings."
    for operation in (fe.FinancialOperation.PAYMENT, fe.FinancialOperation.WITHDRAWAL):
        if not fe.evaluate(db, user, operation).allowed:
            return "ACCOUNT_HOLD", "Your account cannot make this payment right now. Contact support."
    return None


def eligibility(db: Session, user: User) -> dict:
    problem = member_check(db, user)
    return {"enabled": enabled(), "kyc_approved": problem is None or problem[0] != "KYC_REQUIRED",
            "allowed": enabled() and problem is None, "reason": None if problem is None else problem[0],
            "message": None if problem is None else problem[1], "currency": "USD",
            "spendable": str(spendable_balance(db, user.id)),
            # Part of `spendable` (and of the cashout balance): the same money, shown once, usable once.
            "partly_spent_remainder": str(remainder_total(db, user.id)),
            "wallet_only_remainder": "0.00"}       # retired meaning (kept for older clients): nothing is wallet-only


def preview(db: Session, user: User, product_code: str, quantity: int) -> dict:
    terms = product_terms(db, user, product_code, quantity)
    balance = spendable_balance(db, user.id)
    problem = member_check(db, user)
    reason = ("WALLET_PAYMENTS_DISABLED" if not enabled() else problem[0] if problem
              else terms.reason if not terms.eligible else "INSUFFICIENT_BALANCE" if balance < terms.amount else None)
    message = ("Paying with MyHigh5 earnings is not available." if reason == "WALLET_PAYMENTS_DISABLED"
               else problem[1] if problem else terms.message if not terms.eligible
               else "You do not have enough eligible available commission earnings for this purchase."
               if reason == "INSUFFICIENT_BALANCE" else None)
    return {"product_code": terms.product_code, "product_name": terms.name, "quantity": terms.quantity,
            "unit_price": str(terms.unit_price), "amount": str(terms.amount), "currency": "USD",
            "available": str(balance), "remaining_after": str(money(balance - terms.amount)) if reason is None else None,
            "allowed": reason is None, "reason": reason, "message": message}


# ---------------------------------------------------------------- pay (atomic)

def _audit(db: Session, payment: InternalWalletPayment, action: str, actor_id: Optional[int], new: dict) -> None:
    db.add(AuditTrail(table_name="internal_wallet_payments", record_id=payment.id, action=action, old_values=None,
                      new_values={k: (str(v) if isinstance(v, Decimal) else v) for k, v in new.items()},
                      user_id=actor_id))


def _settle(db: Session, payment: InternalWalletPayment, draws) -> int:
    """Dr 2001 (direct) / 2002 (indirect) for the commission used, Cr 1050 clearing."""
    from app.services.new_model_ledger import Line, post_entry

    direct = money(sum((take for row, take, _left in draws if (row.level or 1) == 1), Decimal("0.00")))
    indirect = money(sum((take for row, take, _left in draws if (row.level or 1) != 1), Decimal("0.00")))
    lines = []
    if direct:
        lines.append(Line("2001", debit=direct, description=f"Commission earnings spent - {payment.reference}"))
    if indirect:
        lines.append(Line("2002", debit=indirect, description=f"Commission earnings spent - {payment.reference}"))
    lines.append(Line(CLEARING_ACCOUNT, credit=money(direct + indirect),
                      description=f"Internal wallet settlement - {payment.reference}"))
    entry = post_entry(db, source_type=SOURCE_TYPE, source_id=payment.id, posting_type=POSTING_SETTLEMENT, lines=lines,
                       description=f"Internal wallet payment {payment.reference} - user {payment.user_id} - "
                                   f"{payment.product_code} x{payment.quantity}")
    return entry.id


def _fulfilled(db: Session, terms: Terms, deposit: Deposit) -> bool:
    from app.models.advertising_v2 import AdvCreditMovement
    from app.models.business_model import ReferralPoolPurchase
    from app.services import ad_campaigns
    from app.services.new_model_reference_data import REFERRAL_POOL_PRODUCT_CODE

    if terms.product_code == REFERRAL_POOL_PRODUCT_CODE:
        purchase = db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit.id).first()
        return purchase is not None and purchase.status == "PAID"
    if terms.product_code == ad_campaigns.AD_CREDIT_PRODUCT_CODE:
        return db.query(AdvCreditMovement.id).filter(AdvCreditMovement.idempotency_key == f"deposit:{deposit.id}").first() \
            is not None
    return False


def pay(db: Session, user: User, *, product_code: str, quantity: int, idempotency_key: str,
        expected_amount=None, now: Optional[datetime] = None) -> Tuple[InternalWalletPayment, bool]:
    """Pay in full with earnings, atomically, in the caller's transaction (the caller commits, or rolls back
    on any error: then nothing at all was written). Returns (payment, replayed)."""
    from app.services import referral_pool_units
    from app.services.new_model_payments import INTERNAL_WALLET_PROVIDER, process_new_model_deposit
    from app.services.new_model_reference_data import NEW_MODEL_VERSION, REFERRAL_POOL_PRODUCT_CODE

    now = now or datetime.utcnow()
    _require_enabled()
    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 80:
        raise WalletError("IDEMPOTENCY_KEY_REQUIRED", "A payment key of 8 to 80 characters is required.", 400)
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()          # 1. lock the member
    existing = (db.query(InternalWalletPayment)
                .filter(InternalWalletPayment.user_id == locked.id, InternalWalletPayment.idempotency_key == key).first())
    if existing is not None:
        if existing.product_code != product_code or existing.quantity != quantity:
            raise WalletError("IDEMPOTENCY_CONFLICT", "This payment key was already used for another purchase.")
        return existing, True                                                            # a retry: same result
    _require_enabled()                                                                   # 3. switch, again
    problem = member_check(db, locked)                                                   # 2. KYC + account, again
    if problem:
        raise WalletError(problem[0], problem[1], 403)
    terms = product_terms(db, locked, product_code, quantity)                            # 4-6. product + price
    if not terms.eligible:
        raise WalletError(terms.reason or "NOT_ELIGIBLE", terms.message or "This product cannot be paid with earnings.")
    if expected_amount is not None and money(expected_amount) != terms.amount:
        raise WalletError("PRICE_CHANGED", f"The price is now {terms.amount} USD. Review and confirm again.")
    rows = spendable_rows(db, locked.id, lock=True)                                      # 7. funds, locked
    balance = money(sum((left for _r, left in rows), Decimal("0.00")))
    if balance < terms.amount:                                                           # 8. full payment only
        raise WalletError("INSUFFICIENT_BALANCE",
                          "You do not have enough eligible available commission earnings for this purchase.")
    draws, need = [], terms.amount
    for row, left in rows:
        if need <= 0:
            break
        take = min(left, need)
        draws.append((row, take, left))
        need = money(need - take)

    reference = f"IWP-{uuid.uuid4().hex[:20].upper()}"
    payment = InternalWalletPayment(reference=reference, user_id=locked.id, idempotency_key=key,
                                    product_code=terms.product_code, product_type_id=terms.product_type.id,
                                    quantity=quantity, amount=terms.amount, currency="USD", status="COMPLETED",
                                    balance_before=balance, completed_at=now)
    db.add(payment)
    db.flush()
    deposit = Deposit(user_id=locked.id, product_type_id=terms.product_type.id, amount=terms.amount, currency="USD",
                      status=DepositStatus.PENDING, order_id=reference, payment_provider=INTERNAL_WALLET_PROVIDER,
                      business_model_version=NEW_MODEL_VERSION,
                      admin_notes=f"Paid with MyHigh5 commission earnings ({reference}); no cash, no provider")
    db.add(deposit)
    db.flush()
    payment.deposit_id = deposit.id
    if terms.product_code == REFERRAL_POOL_PRODUCT_CODE:
        try:
            referral_pool_units.create_purchase(db, user=locked, deposit=deposit, quantity=quantity)
        except referral_pool_units.UnitsError as exc:
            raise WalletError(exc.code, str(exc)) from None
    payment.settlement_journal_entry_id = _settle(db, payment, draws)                    # 10. balanced entry
    for row, take, left in draws:                                                        # 9. consume the funds
        db.add(InternalWalletPaymentLine(payment_id=payment.id, commission_id=row.id, amount=take, status="ACTIVE"))
        if take == left:
            row.status, row.paid_date, row.payout_reference = CommissionStatus.PAID, now, f"{PAID_PREFIX}{reference}"
        else:
            row.payout_reference = REMAINDER_MARK
    deposit.status, deposit.validated_at = DepositStatus.VALIDATED, now                  # 12. paid
    db.flush()
    process_new_model_deposit(db, deposit)                                               # existing fulfilment
    if not _fulfilled(db, terms, deposit):
        raise WalletError("FULFILMENT_FAILED", "The purchase could not be completed; nothing was charged.")
    _audit(db, payment, "WALLET_PAYMENT_COMPLETED", locked.id,
           {"reference": reference, "product": terms.product_code, "quantity": quantity, "amount": terms.amount,
            "balance_before": balance, "deposit_id": deposit.id,
            "commissions": [{"id": int(r.id), "amount": str(t)} for r, t, _l in draws]})
    db.flush()
    return payment, False


def record_failure(db: Session, user: User, *, product_code: str, quantity: int, code: str
                   ) -> Optional[InternalWalletPayment]:
    """After a rollback: keep a FAILED attempt for the member's history (no key: a retry may still succeed)."""
    try:
        product = db.query(ProductType).filter(ProductType.code == product_code).first()
        terms_amount = Decimal("0.01")
        if product is not None and product.price:
            terms_amount = max(Decimal("0.01"), money(Decimal(str(product.price)) * max(1, int(quantity or 1))))
        row = InternalWalletPayment(reference=f"IWP-{uuid.uuid4().hex[:20].upper()}", user_id=user.id,
                                    idempotency_key=None, product_code=(product_code or "?")[:50],
                                    product_type_id=product.id if product is not None else None,
                                    quantity=max(1, int(quantity or 1)) if isinstance(quantity, int) else 1,
                                    amount=terms_amount, currency="USD", status="FAILED", failure_code=code[:40])
        db.add(row)
        db.commit()
        return row
    except Exception:  # noqa: BLE001 - history only
        db.rollback()
        logger.exception("Failed wallet payment attempt could not be recorded")
        return None


# ---------------------------------------------------------------- refunds (finance administrators)

def _restore_rows(db: Session, payment: InternalWalletPayment) -> int:
    lines = (db.query(InternalWalletPaymentLine)
             .filter(InternalWalletPaymentLine.payment_id == payment.id, InternalWalletPaymentLine.status == "ACTIVE").all())
    rows = {r.id: r for r in db.query(AffiliateCommission)
            .filter(AffiliateCommission.id.in_([ln.commission_id for ln in lines])).with_for_update().all()}
    for ln in lines:
        row = rows[ln.commission_id]
        ok = (row.status == CommissionStatus.APPROVED and row.payout_reference == REMAINDER_MARK) or \
             (row.status == CommissionStatus.PAID and str(row.payout_reference or "").startswith(PAID_PREFIX))
        if not ok:
            raise WalletError("REFUND_REVIEW_REQUIRED",
                              f"Commission #{row.id} changed after this payment ({row.status.value}); review by hand.")
    for ln in lines:
        ln.status = "REVERSED"
    db.flush()
    used = _used(db, rows.keys())
    for row in rows.values():
        still = used.get(int(row.id), Decimal("0.00"))
        if still <= 0:
            row.status, row.paid_date, row.payout_reference = CommissionStatus.APPROVED, None, None
        elif still < money(row.commission_amount):
            row.status, row.paid_date, row.payout_reference = CommissionStatus.APPROVED, None, REMAINDER_MARK
    db.flush()
    return len(lines)


def refund(db: Session, actor: User, payment_id: int, *, reason: str, now: Optional[datetime] = None) -> InternalWalletPayment:
    """Full refund of a COMPLETED payment by a finance administrator (permission and password checked by the
    caller). The product is reversed through its existing full-refund path, the settlement is reversed by a
    compensating entry and the commission earnings become spendable again. Never a provider refund. Refused
    (nothing written) where the product's effects cannot be safely undone: such cases need a manual review."""
    from app.models.business_model import ReferralPoolAssignment, ReferralPoolPurchase, ReferralPoolUnit
    from app.models.accounting import JournalEntry
    from app.services import ad_campaigns
    from app.services.new_model_ledger import reverse_entry
    from app.services.new_model_payments import reverse_new_model_deposit
    from app.services.new_model_reference_data import REFERRAL_POOL_PRODUCT_CODE

    now = now or datetime.utcnow()
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise WalletError("REASON_REQUIRED", "Give the reason for the refund.", 400)
    payment = (db.query(InternalWalletPayment).filter(InternalWalletPayment.id == payment_id)
               .with_for_update().first())
    if payment is None:
        raise WalletError("NOT_FOUND", "Payment not found.", 404)
    if payment.status == "REFUNDED":
        raise WalletError("ALREADY_REFUNDED", "This payment was already refunded.")
    if payment.status != "COMPLETED":
        raise WalletError("NOT_REFUNDABLE", "Only a completed payment can be refunded.")
    db.query(User).filter(User.id == payment.user_id).with_for_update().one()
    deposit = db.get(Deposit, payment.deposit_id)
    if payment.product_code == ad_campaigns.AD_CREDIT_PRODUCT_CODE:
        raise WalletError("REFUND_POLICY_NOT_APPROVED",
                          "Advertiser credit stays as credit: no advertiser refund policy is approved.")
    if payment.product_code == REFERRAL_POOL_PRODUCT_CODE:
        purchase = db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit.id).first()
        units = ([u for (u,) in db.query(ReferralPoolUnit.id).filter(ReferralPoolUnit.purchase_id == purchase.id)]
                 if purchase is not None else [])
        if units and db.query(ReferralPoolAssignment.id).filter(ReferralPoolAssignment.unit_id.in_(units)).first():
            raise WalletError("REFUND_REVIEW_REQUIRED",
                              "These Referral Pool units already received assignments; they need a manual review.")
    try:
        reverse_new_model_deposit(db, deposit, reason=f"Internal wallet refund {payment.reference}: {reason}"[:300])
    except WalletError:
        raise
    except Exception as exc:  # noqa: BLE001 - e.g. a commission of this purchase is in a payout
        raise WalletError("REFUND_REVIEW_REQUIRED", f"The purchase cannot be reversed automatically: {exc}") from None
    deposit.provider_status = "refunded"
    _restore_rows(db, payment)
    settlement = db.get(JournalEntry, payment.settlement_journal_entry_id)
    reversal = reverse_entry(db, settlement, reason=f"Internal wallet refund {payment.reference}")
    payment.status, payment.refunded_at, payment.refunded_by_user_id = "REFUNDED", now, actor.id
    payment.refund_reason, payment.refund_journal_entry_id = reason[:300], reversal.id
    _audit(db, payment, "WALLET_PAYMENT_REFUNDED", actor.id, {"reason": reason[:300], "journal": reversal.id})
    db.flush()
    return payment


# ---------------------------------------------------------------- views

def payment_payload(db: Session, p: InternalWalletPayment, *, detail: bool = False) -> dict:
    out = {"id": p.id, "reference": p.reference, "user_id": p.user_id, "product_code": p.product_code,
           "quantity": p.quantity, "amount": str(money(p.amount)), "currency": p.currency, "status": p.status,
           "failure_code": p.failure_code, "created_at": p.created_at.isoformat() if p.created_at else None,
           "completed_at": p.completed_at.isoformat() if p.completed_at else None,
           "refunded_at": p.refunded_at.isoformat() if p.refunded_at else None, "refund_reason": p.refund_reason,
           "deposit_id": p.deposit_id}
    if detail:
        out["lines"] = [{"commission_id": ln.commission_id, "amount": str(money(ln.amount)), "status": ln.status}
                        for ln in db.query(InternalWalletPaymentLine).filter(InternalWalletPaymentLine.payment_id == p.id)
                        .order_by(InternalWalletPaymentLine.id.asc())]
        out["settlement_journal_entry_id"] = p.settlement_journal_entry_id
        out["refund_journal_entry_id"] = p.refund_journal_entry_id
        out["balance_before"] = str(p.balance_before) if p.balance_before is not None else None
    return out


def member_summary(db: Session, user: User, *, limit: int = 50) -> dict:
    rows = (db.query(InternalWalletPayment).filter(InternalWalletPayment.user_id == user.id)
            .order_by(InternalWalletPayment.id.desc()).limit(min(max(1, limit), 200)).all())
    spent = (db.query(func.coalesce(func.sum(InternalWalletPayment.amount), 0))
             .filter(InternalWalletPayment.user_id == user.id, InternalWalletPayment.status == "COMPLETED").scalar())
    refunded = (db.query(func.coalesce(func.sum(InternalWalletPayment.amount), 0))
                .filter(InternalWalletPayment.user_id == user.id, InternalWalletPayment.status == "REFUNDED").scalar())
    from app.services.financial_balances import get_commission_balance

    balance = get_commission_balance(db, user.id)
    return {**eligibility(db, user), "reserved_for_payouts": str(balance.reserved),
            "total_spent": str(money(spent or 0)), "total_refunded": str(money(refunded or 0)),
            "payments": [payment_payload(db, p) for p in rows]}


def admin_list(db: Session, *, user_id: Optional[int] = None, product_code: Optional[str] = None,
               status: Optional[str] = None, limit: int = 200) -> list:
    q = db.query(InternalWalletPayment)
    if user_id:
        q = q.filter(InternalWalletPayment.user_id == user_id)
    if product_code:
        q = q.filter(InternalWalletPayment.product_code == product_code)
    if status:
        q = q.filter(InternalWalletPayment.status == status)
    return [payment_payload(db, p) for p in q.order_by(InternalWalletPayment.id.desc()).limit(min(limit, 500))]


def reconciliation(db: Session) -> dict:
    """Read-only checks: clearing 1050 nets to zero; every completed payment has its settlement, its validated
    internal-wallet payment record and active lines adding up to its amount; refunded ones have none active;
    no commission row is used beyond its amount; no wallet payment created a SoncoPay record."""
    from app.models.accounting import ChartOfAccounts, JournalLine

    problems = []
    clearing = (db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0) - func.coalesce(func.sum(JournalLine.credit_amount), 0))
                .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
                .filter(ChartOfAccounts.account_code == CLEARING_ACCOUNT).scalar())
    if money(clearing or 0) != 0:
        problems.append({"type": "CLEARING_NOT_ZERO", "message": f"Account 1050 balance is {money(clearing)}"})
    for p in db.query(InternalWalletPayment).filter(InternalWalletPayment.status.in_(("COMPLETED", "REFUNDED"))):
        active = money(db.query(func.coalesce(func.sum(InternalWalletPaymentLine.amount), 0))
                       .filter(InternalWalletPaymentLine.payment_id == p.id,
                               InternalWalletPaymentLine.status == "ACTIVE").scalar() or 0)
        expected = money(p.amount) if p.status == "COMPLETED" else Decimal("0.00")
        if active != expected:
            problems.append({"type": "LINES_MISMATCH", "payment": p.reference,
                             "message": f"Commission used {active} vs {expected}"})
        dep = db.get(Deposit, p.deposit_id) if p.deposit_id else None
        if dep is None or dep.payment_provider != "internal_wallet" or dep.status != DepositStatus.VALIDATED:
            problems.append({"type": "PAYMENT_RECORD", "payment": p.reference, "message": "Payment record missing or wrong"})
        if p.settlement_journal_entry_id is None:
            problems.append({"type": "NO_SETTLEMENT", "payment": p.reference, "message": "No settlement entry"})
    over = (db.query(InternalWalletPaymentLine.commission_id, func.sum(InternalWalletPaymentLine.amount),
                     AffiliateCommission.commission_amount)
            .join(AffiliateCommission, AffiliateCommission.id == InternalWalletPaymentLine.commission_id)
            .filter(InternalWalletPaymentLine.status == "ACTIVE")
            .group_by(InternalWalletPaymentLine.commission_id, AffiliateCommission.commission_amount).all())
    for cid, used, amount in over:
        if money(used) > money(amount):
            problems.append({"type": "OVERUSED_COMMISSION", "message": f"Commission #{cid} used {money(used)} of {money(amount)}"})
    counts = dict(db.query(InternalWalletPayment.status, func.count(InternalWalletPayment.id))
                  .group_by(InternalWalletPayment.status).all())
    return {"ok": not problems, "problems": problems, "clearing_balance": str(money(clearing or 0)),
            "payments_by_status": {k: int(v) for k, v in counts.items()}, "enabled": enabled(), "read_only": True}


# ---------------------------------------------------------------- notifications

def notify(db: Session, payment: InternalWalletPayment, kind: str) -> bool:
    """One email per payment and outcome (COMPLETED / FAILED / REFUNDED / REFUND_REVIEW). Payment emails only
    while the feature is switched on. Never raises; idempotent by key."""
    try:
        if kind in ("COMPLETED", "FAILED") and not enabled():
            return False
        user = db.query(User).filter(User.id == payment.user_id).first()
        if user is None or not user.email or not user.is_active:
            return False
        from app.models.email import EmailDelivery
        from app.services.email import email_service
        from app.services.email_events import EmailEvent

        # The email service commits on its own: called only after the payment's own commit (never inside it).
        reference, amount, product, quantity, failure = (payment.reference, str(money(payment.amount)),
                                                         payment.product_code, payment.quantity, payment.failure_code)
        key = f"iwp:{reference}:{kind}"
        if db.query(EmailDelivery.id).filter(EmailDelivery.idempotency_key == key).first() is not None:
            return False                                                  # already recorded once
        delivery = email_service.enqueue(
            db, event=EmailEvent.BILLING_WALLET_PAYMENT_UPDATE, recipient=user.email, idempotency_key=key,
            user_id=user.id, context={"kind": kind, "reference": reference, "amount": amount, "product": product,
                                      "quantity": quantity, "failure_code": failure or ""})
        return delivery is not None
    except Exception:  # noqa: BLE001
        logger.exception("Wallet payment email %s could not be queued", payment.reference)
        return False
