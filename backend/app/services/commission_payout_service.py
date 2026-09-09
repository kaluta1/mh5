"""Durable, replay-safe affiliate commission payouts via NOWPayments."""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus
from app.models.user import User
from app.services.accounting_service import accounting_service
from app.services.financial_integrity import money, positive_money
from app.services.nowpayments_service import (
    payout_config_status,
    payouts_configured,
    send_single_payout_sync,
)
from app.services.wallet_validation import normalize_payout_currency, validate_payout_address

logger = logging.getLogger(__name__)

MIN_MANUAL_WITHDRAWAL_USD = Decimal("100.00")
_INTENT_PREFIX = "intent:"
_ACTIVE_INTENT_STATUSES = ("requested", "processing", "unknown")
_REQUIRED_PAYOUT_ACCOUNTS = ("1001", "2001", "2002", "4005")


def _validated_payout_target(user: User) -> tuple[str, str]:
    wallet = str(user.usdt_wallet_address or "").strip()
    if not wallet:
        raise ValueError("Configure your payout wallet in Settings before withdrawing.")
    currency = normalize_payout_currency(user.payout_currency)
    if currency != "usdtbsc":
        raise ValueError(
            "Only USDT on BSC payouts are enabled until the ledger has separate accounts per network"
        )
    return validate_payout_address(wallet, currency), currency


def _intent_reference(user_id: int, idempotency_key: Optional[str]) -> str:
    if idempotency_key:
        normalized = idempotency_key.strip()
        if not normalized or len(normalized) > 128:
            raise ValueError("Invalid Idempotency-Key")
        digest = hashlib.sha256(f"{user_id}:{normalized}".encode("utf-8")).hexdigest()[:48]
    else:
        digest = uuid.uuid4().hex
    return f"{_INTENT_PREFIX}{digest}"


def _provider_reference(cashout: AffiliateCashoutRequest) -> Optional[str]:
    raw = str(cashout.payout_reference or "")
    marker = ";provider:"
    return raw.split(marker, 1)[1] if marker in raw else None


def _cashout_result(cashout: AffiliateCashoutRequest, *, marked: int) -> dict:
    return {
        "gross_amount": float(cashout.gross_amount),
        "fee": float(cashout.fee),
        "net_amount": float(cashout.net_amount),
        "payout_reference": _provider_reference(cashout),
        "commissions_marked_paid": marked,
        "status": cashout.status,
    }


def _assert_payout_accounts(db: Session) -> None:
    present = {
        row[0]
        for row in db.query(ChartOfAccounts.account_code)
        .filter(ChartOfAccounts.account_code.in_(_REQUIRED_PAYOUT_ACCOUNTS))
        .all()
    }
    missing = sorted(set(_REQUIRED_PAYOUT_ACCOUNTS) - present)
    if missing:
        raise ValueError(f"Payout accounting is not configured; missing accounts: {', '.join(missing)}")


def _find_cashout_by_intent(db: Session, intent_ref: str) -> Optional[AffiliateCashoutRequest]:
    return (
        db.query(AffiliateCashoutRequest)
        .filter(
            or_(
                AffiliateCashoutRequest.payout_reference == intent_ref,
                AffiliateCashoutRequest.payout_reference.like(f"{intent_ref};provider:%"),
            )
        )
        .order_by(AffiliateCashoutRequest.id.desc())
        .first()
    )


def _reserve_cashout(
    db: Session,
    *,
    user_id: int,
    gross: Decimal,
    fee: Decimal,
    net: Decimal,
    intent_ref: str,
    commission_ids: Optional[list[int]] = None,
) -> tuple[AffiliateCashoutRequest, list[int], bool]:
    """Reserve whole commission rows and durably commit an intent before provider I/O."""
    locked_user = db.query(User).filter(User.id == user_id).with_for_update().one()
    existing = _find_cashout_by_intent(db, intent_ref)
    if existing:
        return existing, [], False

    other_active = (
        db.query(AffiliateCashoutRequest.id)
        .filter(
            AffiliateCashoutRequest.user_id == user_id,
            AffiliateCashoutRequest.status.in_(_ACTIVE_INTENT_STATUSES),
        )
        .first()
    )
    if other_active:
        raise ValueError("Another payout is awaiting provider reconciliation")

    query = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.user_id == user_id,
            AffiliateCommission.status == CommissionStatus.APPROVED,
            AffiliateCommission.payout_reference.is_(None),
        )
        .order_by(AffiliateCommission.transaction_date.asc(), AffiliateCommission.id.asc())
        .with_for_update()
    )
    if commission_ids is not None:
        query = query.filter(AffiliateCommission.id.in_(commission_ids))
    available_rows = query.all()

    selected: list[AffiliateCommission] = []
    selected_total = Decimal("0.00")
    for commission in available_rows:
        if selected_total >= gross:
            break
        amount = positive_money(commission.commission_amount)
        selected.append(commission)
        selected_total = money(selected_total + amount)

    if selected_total < gross:
        raise ValueError(f"Insufficient approved balance. Available whole rows: ${selected_total:.2f}")
    if selected_total != gross:
        raise ValueError(
            "Withdrawal amount must equal a whole-commission FIFO total; partial commission rows cannot be paid"
        )

    _assert_payout_accounts(db)
    for commission in selected:
        commission.payout_reference = intent_ref

    cashout = AffiliateCashoutRequest(
        user_id=locked_user.id,
        gross_amount=gross,
        fee=fee,
        net_amount=net,
        payout_method="nowpayments_crypto",
        wallet_snapshot=locked_user.usdt_wallet_address,
        payout_reference=intent_ref,
        status="requested",
        requested_at=datetime.utcnow(),
    )
    db.add(cashout)
    db.commit()
    db.refresh(cashout)
    return cashout, [int(row.id) for row in selected], True


def _post_cashout_accounting(
    db: Session,
    *,
    cashout: AffiliateCashoutRequest,
    commissions: Iterable[AffiliateCommission],
) -> None:
    description = f"Affiliate Cashout #{cashout.id}"
    if db.query(JournalEntry.id).filter(JournalEntry.description == description).first():
        return

    level_one = Decimal("0.00")
    indirect = Decimal("0.00")
    for commission in commissions:
        amount = money(commission.commission_amount)
        if commission.level == 1:
            level_one += amount
        else:
            indirect += amount

    lines: list[dict] = []
    if level_one:
        lines.append({"account_code": "2001", "debit": level_one, "credit": 0, "description": description})
    if indirect:
        lines.append({"account_code": "2002", "debit": indirect, "credit": 0, "description": description})
    lines.append(
        {
            "account_code": "1001",
            "debit": 0,
            "credit": money(cashout.net_amount),
            "description": f"USDT payout for {description}",
        }
    )
    if money(cashout.fee) > 0:
        lines.append(
            {
                "account_code": "4005",
                "debit": 0,
                "credit": money(cashout.fee),
                "description": f"Cashout fee for {description}",
            }
        )
    accounting_service.create_journal_entry(
        db,
        description=description,
        lines=lines,
        date=datetime.utcnow(),
        commit=False,
    )


def _execute_cashout_intent(
    db: Session,
    *,
    cashout_id: int,
    commission_ids: list[int],
    currency: str,
) -> dict:
    cashout = db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id).one()
    intent_ref = str(cashout.payout_reference)
    wallet = str(cashout.wallet_snapshot or "").strip()
    net = money(cashout.net_amount)

    cashout.status = "processing"
    db.commit()

    try:
        provider_result = send_single_payout_sync(
            wallet_address=wallet,
            amount_usd=float(net),
            currency=currency,
        )
        provider_ref = str(
            provider_result.get("id") or provider_result.get("batch_withdrawal_id") or ""
        )
        if not provider_ref:
            raise RuntimeError("Payout provider returned no durable reference")
    except Exception as exc:
        db.rollback()
        uncertain = (
            db.query(AffiliateCashoutRequest)
            .filter(AffiliateCashoutRequest.id == cashout_id)
            .with_for_update()
            .one()
        )
        uncertain.status = "unknown"
        uncertain.processed_at = datetime.utcnow()
        db.commit()
        logger.exception("Payout intent %s requires provider reconciliation", cashout_id)
        raise ValueError(
            "Payout outcome is unknown; funds remain reserved and must be reconciled before retry"
        ) from exc

    db.rollback()
    cashout = (
        db.query(AffiliateCashoutRequest)
        .filter(AffiliateCashoutRequest.id == cashout_id)
        .with_for_update()
        .one()
    )
    commissions = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.id.in_(commission_ids),
            AffiliateCommission.payout_reference == intent_ref,
        )
        .with_for_update()
        .all()
    )
    if len(commissions) != len(commission_ids):
        db.rollback()
        raise ValueError("Reserved commissions changed; payout requires manual reconciliation")

    now = datetime.utcnow()
    for commission in commissions:
        commission.status = CommissionStatus.PAID
        commission.paid_date = now
        commission.payout_reference = provider_ref
    _post_cashout_accounting(db, cashout=cashout, commissions=commissions)
    cashout.status = "completed"
    cashout.processed_at = now
    cashout.payout_reference = f"{intent_ref};provider:{provider_ref}"
    db.commit()
    return _cashout_result(cashout, marked=len(commissions))


def trigger_commission_payout_sync(
    db: Session,
    beneficiary: User,
    commission: AffiliateCommission,
) -> bool:
    """Safely auto-pay one commission through a committed payout intent."""
    if commission.status == CommissionStatus.PAID:
        return True
    if not payouts_configured() or not (beneficiary.usdt_wallet_address or "").strip():
        return False
    _wallet, payout_currency = _validated_payout_target(beneficiary)

    locked = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.id == commission.id)
        .with_for_update()
        .one()
    )
    if locked.status == CommissionStatus.PENDING:
        locked.status = CommissionStatus.APPROVED
    if locked.status != CommissionStatus.APPROVED or locked.payout_reference:
        db.rollback()
        return locked.status == CommissionStatus.PAID

    gross = positive_money(locked.commission_amount)
    intent_ref = _intent_reference(beneficiary.id, f"commission:{locked.id}")
    cashout, ids, created = _reserve_cashout(
        db,
        user_id=beneficiary.id,
        gross=gross,
        fee=Decimal("0.00"),
        net=gross,
        intent_ref=intent_ref,
        commission_ids=[int(locked.id)],
    )
    if not created:
        return cashout.status == "completed"
    result = _execute_cashout_intent(
        db,
        cashout_id=int(cashout.id),
        commission_ids=ids,
        currency=payout_currency,
    )
    return result["status"] == "completed"


def process_commission_payouts_sync(db: Session, commissions: List[AffiliateCommission]) -> int:
    paid = 0
    for commission in commissions:
        beneficiary = db.query(User).filter(User.id == commission.user_id).first()
        if not beneficiary:
            continue
        try:
            if trigger_commission_payout_sync(db, beneficiary, commission):
                paid += 1
        except ValueError:
            logger.exception("Commission %s payout stopped for reconciliation", commission.id)
    return paid


def pay_pending_commissions_for_user_sync(db: Session, user_id: int) -> int:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.usdt_wallet_address:
        return 0
    pending = (
        db.query(AffiliateCommission)
        .filter(
            AffiliateCommission.user_id == user_id,
            AffiliateCommission.status.in_([CommissionStatus.PENDING, CommissionStatus.APPROVED]),
            AffiliateCommission.payout_reference.is_(None),
        )
        .order_by(AffiliateCommission.transaction_date.asc())
        .all()
    )
    return process_commission_payouts_sync(db, pending)


def retry_failed_payouts_sync(db: Session, *, user_id: Optional[int] = None, limit: int = 50) -> int:
    """Retry only unreserved legacy APPROVED rows; unknown intents are never auto-retried."""
    query = db.query(AffiliateCommission).filter(
        AffiliateCommission.status == CommissionStatus.APPROVED,
        AffiliateCommission.payout_reference.is_(None),
    )
    if user_id is not None:
        query = query.filter(AffiliateCommission.user_id == user_id)
    rows = query.order_by(AffiliateCommission.transaction_date.asc()).limit(limit).all()
    return process_commission_payouts_sync(db, rows)


def get_approved_balance_sync(db: Session, user_id: int) -> Decimal:
    from app.services.financial_balances import get_commission_balance

    return get_commission_balance(db, user_id).available


def process_manual_withdrawal_sync(
    db: Session,
    user: User,
    gross_amount: Decimal,
    *,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Reserve exact FIFO rows, commit, call the provider, then post the result."""
    from app.accounting.distribution_formulas import cashout_fee_and_net

    gross = positive_money(gross_amount)
    if gross < MIN_MANUAL_WITHDRAWAL_USD:
        raise ValueError(f"Minimum withdrawal is ${MIN_MANUAL_WITHDRAWAL_USD:.2f}.")
    _wallet, payout_currency = _validated_payout_target(user)
    if not payouts_configured():
        missing = ", ".join(payout_config_status().get("missing") or [])
        raise ValueError("Crypto payouts are not enabled. Missing: " + (missing or "provider credentials"))

    fee_result = cashout_fee_and_net(gross)
    fee = money(fee_result.fee)
    net = positive_money(fee_result.net_to_member)
    intent_ref = _intent_reference(user.id, idempotency_key)
    cashout, commission_ids, created = _reserve_cashout(
        db,
        user_id=user.id,
        gross=gross,
        fee=fee,
        net=net,
        intent_ref=intent_ref,
    )
    if not created:
        return _cashout_result(cashout, marked=0)

    return _execute_cashout_intent(
        db,
        cashout_id=int(cashout.id),
        commission_ids=commission_ids,
        currency=payout_currency,
    )
