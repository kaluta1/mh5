"""
Auto-payout affiliate commissions via NOWPayments after accrual or wallet registration.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus
from app.models.user import User
from app.services.nowpayments_service import NowPaymentsError, payouts_configured, send_single_payout_sync

logger = logging.getLogger(__name__)

MIN_MANUAL_WITHDRAWAL_USD = Decimal("100")


def _mark_commission_paid(
    db: Session,
    commission: AffiliateCommission,
    user: User,
    payout_ref: str,
    *,
    create_cashout_row: bool = True,
) -> None:
    now = datetime.utcnow()
    commission.status = CommissionStatus.PAID
    commission.paid_date = now
    commission.payout_reference = payout_ref

    if create_cashout_row:
        cashout = AffiliateCashoutRequest(
            user_id=user.id,
            gross_amount=float(commission.commission_amount),
            fee=0.0,
            net_amount=float(commission.commission_amount),
            payout_method="nowpayments_crypto",
            wallet_snapshot=user.usdt_wallet_address,
            payout_reference=payout_ref,
            status="processing",
            requested_at=now,
            processed_at=now,
        )
        db.add(cashout)


def trigger_commission_payout_sync(
    db: Session,
    beneficiary: User,
    commission: AffiliateCommission,
) -> bool:
    """
    Attempt immediate NOWPayments payout for one commission.
    Returns True when marked PAID; False when skipped or left APPROVED for retry.
    """
    if commission.status == CommissionStatus.PAID:
        return True

    wallet = (beneficiary.usdt_wallet_address or "").strip()
    if not wallet:
        return False

    if not payouts_configured():
        logger.debug("Payout API not configured — commission %s stays APPROVED", commission.id)
        return False

    if float(commission.commission_amount or 0) <= 0:
        return False

    currency = (beneficiary.payout_currency or "usdtbsc").strip() or "usdtbsc"

    try:
        result = send_single_payout_sync(
            wallet_address=wallet,
            amount_usd=float(commission.commission_amount),
            currency=currency,
        )
        payout_ref = str(result.get("id") or result.get("batch_withdrawal_id") or "")
        _mark_commission_paid(db, commission, beneficiary, payout_ref)
        logger.info(
            "Commission %s paid to user %s ($%.2f, ref=%s)",
            commission.id,
            beneficiary.id,
            float(commission.commission_amount),
            payout_ref,
        )
        return True
    except NowPaymentsError as exc:
        logger.exception(
            "NOWPayments payout failed for commission %s (user=%s): %s",
            commission.id,
            beneficiary.id,
            exc,
        )
        return False
    except Exception:
        logger.exception(
            "Unexpected payout failure for commission %s (user=%s)",
            commission.id,
            beneficiary.id,
        )
        return False


def process_commission_payouts_sync(
    db: Session,
    commissions: List[AffiliateCommission],
) -> int:
    """Pay all eligible commissions in a batch. Returns count marked PAID."""
    paid = 0
    for commission in commissions:
        if commission.status not in (CommissionStatus.APPROVED, CommissionStatus.PENDING):
            continue
        beneficiary = db.query(User).filter(User.id == commission.user_id).first()
        if not beneficiary or not beneficiary.usdt_wallet_address:
            continue
        if commission.status == CommissionStatus.PENDING:
            commission.status = CommissionStatus.APPROVED
        if trigger_commission_payout_sync(db, beneficiary, commission):
            paid += 1
    if paid:
        db.flush()
    return paid


def pay_pending_commissions_for_user_sync(db: Session, user_id: int) -> int:
    """Pay all APPROVED/PENDING commissions when user adds a wallet."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.usdt_wallet_address:
        return 0

    pending = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.user_id == user_id,
            AffiliateCommission.status.in_([CommissionStatus.PENDING, CommissionStatus.APPROVED]),
        )
        .order_by(AffiliateCommission.transaction_date.asc())
        .all()
    )
    return process_commission_payouts_sync(db, pending)


def retry_failed_payouts_sync(db: Session, *, user_id: Optional[int] = None, limit: int = 50) -> int:
    """Retry APPROVED commissions that failed payout (admin)."""
    q = db.query(AffiliateCommission).filter(AffiliateCommission.status == CommissionStatus.APPROVED)
    if user_id is not None:
        q = q.filter(AffiliateCommission.user_id == user_id)
    commissions = q.order_by(AffiliateCommission.transaction_date.asc()).limit(limit).all()
    return process_commission_payouts_sync(db, commissions)


def get_approved_balance_sync(db: Session, user_id: int) -> Decimal:
    from sqlalchemy import func

    total = (
        db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0))
        .filter(
            AffiliateCommission.user_id == user_id,
            AffiliateCommission.status == CommissionStatus.APPROVED,
        )
        .scalar()
    )
    return Decimal(str(total or 0))


def process_manual_withdrawal_sync(
    db: Session,
    user: User,
    gross_amount: Decimal,
) -> dict:
    """
    Batch-withdraw APPROVED commissions: min $100, 1% fee (min $20, max $1000).
    Marks FIFO APPROVED rows PAID after successful NOWPayments payout of net amount.
    """
    from app.accounting.distribution_formulas import cashout_fee_and_net

    gross = Decimal(str(gross_amount)).quantize(Decimal("0.01"))
    if gross < MIN_MANUAL_WITHDRAWAL_USD:
        raise ValueError(f"Minimum withdrawal is ${MIN_MANUAL_WITHDRAWAL_USD}.")

    wallet = (user.usdt_wallet_address or "").strip()
    if not wallet:
        raise ValueError("Configure your payout wallet in Settings before withdrawing.")

    if not payouts_configured():
        raise ValueError("Crypto payouts are not enabled on this server yet.")

    available = get_approved_balance_sync(db, user.id)
    if gross > available:
        raise ValueError(f"Insufficient approved balance. Available: ${available:.2f}")

    fee_result = cashout_fee_and_net(gross)
    net = fee_result.net_to_member
    if net <= 0:
        raise ValueError("Withdrawal amount too small after fees.")

    currency = (user.payout_currency or "usdtbsc").strip() or "usdtbsc"

    try:
        result = send_single_payout_sync(
            wallet_address=wallet,
            amount_usd=float(net),
            currency=currency,
        )
    except NowPaymentsError as exc:
        raise ValueError(f"Payout failed: {exc}") from exc

    payout_ref = str(result.get("id") or result.get("batch_withdrawal_id") or "")

    # Mark APPROVED commissions PAID (FIFO) until gross amount covered
    remaining = gross
    marked = 0
    rows = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.user_id == user.id,
            AffiliateCommission.status == CommissionStatus.APPROVED,
        )
        .order_by(AffiliateCommission.transaction_date.asc())
        .all()
    )
    for commission in rows:
        if remaining <= 0:
            break
        amt = Decimal(str(commission.commission_amount or 0))
        if amt <= 0:
            continue
        _mark_commission_paid(db, commission, user, payout_ref, create_cashout_row=False)
        remaining -= amt
        marked += 1

    cashout = AffiliateCashoutRequest(
        user_id=user.id,
        gross_amount=float(gross),
        fee=float(fee_result.fee),
        net_amount=float(net),
        payout_method="nowpayments_crypto",
        wallet_snapshot=wallet,
        payout_reference=payout_ref,
        status="completed",
        requested_at=datetime.utcnow(),
        processed_at=datetime.utcnow(),
    )
    db.add(cashout)
    db.flush()

    return {
        "gross_amount": float(gross),
        "fee": float(fee_result.fee),
        "net_amount": float(net),
        "payout_reference": payout_ref,
        "commissions_marked_paid": marked,
        "status": "completed",
    }
