"""Dual cashout of affiliate commissions: the member's choice, the payout
wallet, USD cashout requests, and the shared reserve / complete / release
steps that the automatic crypto engine (cashout_engine) also uses.

Business rules (owner requirement, 2026-10-08)
----------------------------------------------
* The affiliate program itself is unchanged: commissions are accrued for the
  DIRECT sponsor only, by new_model_revenue.accrue_direct_commission. Nothing
  here creates, resizes or re-rates a commission.
* A member chooses ONE cashout method:
    CRYPTO  minimum $1; paid automatically to the member's verified crypto
            wallet by the payout engine (off by default).
    USD     minimum $100; the member asks for it explicitly; the existing
            withdrawal fee applies (1%, minimum $20, maximum $1,000 -
            accounting.distribution_formulas.cashout_fee_and_net).
* Commissions are paid as whole rows, oldest first. A balance is never a
  stored number: it is always derived from the commission rows
  (financial_balances.get_commission_balance).

Lifecycle of a commission row
-----------------------------
  PENDING     earned, but the member has no usable payout destination yet
  APPROVED    available                       (payout_reference IS NULL)
  APPROVED    reserved for one cashout        (payout_reference = that cashout's intent)
  PAID        paid by that cashout            (payout_reference = the settlement reference)
  CANCELLED   reversed (refund of the source payment)

Lifecycle of a cashout (affiliate_cashout_requests)
---------------------------------------------------
  requested -> processing -> completed
                          -> failed      (confirmed NOT paid: reservation released)
                          -> unknown     (outcome uncertain: stays reserved until a
                                          person or the provider's status settles it)
  requested -> cancelled                 (nothing was sent: reservation released)

A member has at most one cashout in requested / processing / unknown (a
partial unique index enforces it). Money is only ever in one place: a
reserved row is not available, and it becomes available again only through
release_reservation, which runs when the cashout is recorded as not paid.

What this module does NOT establish: that the provider actually holds the
crypto. The ledger liability (accounts 2001/2002) and these rows say what is
OWED; whether the provider balance covers it is checked separately
(cashout_engine.reconciliation_report).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounting.distribution_formulas import cashout_fee_and_net
from app.core.config import settings
from app.core.security import verify_password
from app.models.accounting import AuditTrail, ChartOfAccounts, JournalEntry
from app.models.affiliate import (
    ACTIVE_CASHOUT_STATUSES,
    AffiliateCashoutRequest,
    AffiliateCommission,
    CashoutStatus,
    CommissionStatus,
    PayoutWalletChange,
)
from app.models.user import User
from app.services import financial_eligibility as fe
from app.services.accounting_service import accounting_service
from app.services.commission_payout_service import _find_cashout_by_intent, _intent_reference
from app.services.financial_balances import CommissionBalance, get_commission_balance
from app.services.financial_integrity import money, positive_money
from app.services.wallet_validation import normalize_payout_currency, validate_payout_address

logger = logging.getLogger(__name__)

METHOD_CRYPTO = "CRYPTO"
METHOD_USD = "USD"
CASHOUT_METHODS = (METHOD_CRYPTO, METHOD_USD)

# The only network the ledger has a treasury account for (1001, USDT on BSC).
CRYPTO_PAYOUT_CURRENCY = "usdtbsc"
CRYPTO_TREASURY_ACCOUNT = "1001"

WALLET_MISSING, WALLET_INVALID, WALLET_UNVERIFIED = "MISSING", "INVALID", "UNVERIFIED"
WALLET_ON_HOLD, WALLET_VERIFIED = "ON_HOLD", "VERIFIED"


class CashoutError(ValueError):
    """A cashout action that cannot be carried out. `code` is stable and safe
    to show; nothing was changed unless the docstring of the caller says so."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def crypto_minimum() -> Decimal:
    return positive_money(settings.CRYPTO_CASHOUT_MIN_USD)


def usd_minimum() -> Decimal:
    return positive_money(settings.USD_CASHOUT_MIN_USD)


def wallet_hold() -> timedelta:
    return timedelta(hours=max(0, int(settings.PAYOUT_WALLET_HOLD_HOURS)))


def mask_address(address: Optional[str]) -> Optional[str]:
    text = (address or "").strip()
    if not text:
        return None
    return text if len(text) < 12 else f"{text[:6]}...{text[-4:]}"


def _audit(db: Session, *, record_id: int, action: str, actor_id: Optional[int], old: Optional[dict],
           new: Optional[dict], table: str = "affiliate_cashout_requests", ip: Optional[str] = None) -> None:
    db.add(AuditTrail(table_name=table, record_id=record_id, action=action, old_values=old, new_values=new,
                      user_id=actor_id, ip_address=ip))


# ---------------------------------------------------------------------------
# Payout wallet
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WalletState:
    status: str
    address: Optional[str] = None
    currency: Optional[str] = None
    payable_from: Optional[datetime] = None

    @property
    def payable(self) -> bool:
        return self.status == WALLET_VERIFIED


def wallet_state(user: User, now: Optional[datetime] = None) -> WalletState:
    """Can the engine pay to this member's wallet right now?"""
    now = now or datetime.utcnow()
    address = (user.usdt_wallet_address or "").strip()
    if not address:
        return WalletState(WALLET_MISSING)
    try:
        currency = normalize_payout_currency(user.payout_currency)
        if currency != CRYPTO_PAYOUT_CURRENCY:
            raise ValueError("network not enabled")
        address = validate_payout_address(address, currency)
    except ValueError:
        return WalletState(WALLET_INVALID, address=address, currency=user.payout_currency)
    verified_at = user.payout_wallet_verified_at
    if verified_at is None:
        return WalletState(WALLET_UNVERIFIED, address=address, currency=currency)
    payable_from = verified_at + wallet_hold()
    if now < payable_from:
        return WalletState(WALLET_ON_HOLD, address=address, currency=currency, payable_from=payable_from)
    return WalletState(WALLET_VERIFIED, address=address, currency=currency, payable_from=payable_from)


def change_payout_wallet(db: Session, user: User, *, address: str, currency: Optional[str], password: str,
                         ip: Optional[str] = None, now: Optional[datetime] = None) -> WalletState:
    """Set the member's payout wallet. Commits.

    Authorised by the member's CURRENT password (a stolen session alone cannot
    redirect payouts). The wallet is then on hold for PAYOUT_WALLET_HOLD_HOURS
    before anything is paid to it. Nothing is ever paid as a result of this
    call. Refused while a crypto payout of the member is in progress."""
    now = now or datetime.utcnow()
    if not password or not verify_password(password, user.hashed_password):
        raise CashoutError("PASSWORD_REQUIRED", "Enter your current password to change the payout wallet.")
    normalized = normalize_payout_currency(currency)
    if normalized != CRYPTO_PAYOUT_CURRENCY:
        raise CashoutError("NETWORK_NOT_ENABLED", "Only USDT on BSC (BEP20) payouts are enabled.")
    new_address = validate_payout_address(address, normalized)

    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    old_address = (locked.usdt_wallet_address or "").strip() or None
    if old_address == new_address and locked.payout_wallet_verified_at is not None:
        state = wallet_state(locked, now)         # nothing to change; the hold is not restarted
        db.rollback()
        return state
    if (db.query(AffiliateCashoutRequest.id)
            .filter(AffiliateCashoutRequest.user_id == locked.id,
                    AffiliateCashoutRequest.cashout_method == METHOD_CRYPTO,
                    AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES)).first()):
        db.rollback()
        raise CashoutError("PAYOUT_IN_PROGRESS", "A payout is in progress. Try again when it has finished.")
    recent = (db.query(PayoutWalletChange)
              .filter(PayoutWalletChange.user_id == locked.id,
                      PayoutWalletChange.changed_at > now - timedelta(hours=24)).count())
    if recent >= int(settings.PAYOUT_WALLET_MAX_CHANGES_PER_DAY):
        db.rollback()
        raise CashoutError("TOO_MANY_CHANGES", "The payout wallet was changed too often. Try again tomorrow.")

    locked.usdt_wallet_address = new_address
    locked.payout_currency = normalized
    locked.payout_wallet_verified_at = now
    change = PayoutWalletChange(user_id=locked.id, old_address=old_address, new_address=new_address,
                                currency=normalized, changed_at=now, payable_from=now + wallet_hold(),
                                ip_address=ip)
    db.add(change)
    db.flush()
    _audit(db, record_id=locked.id, action="PAYOUT_WALLET_CHANGED", actor_id=locked.id, table="users", ip=ip,
           old={"wallet": mask_address(old_address)},
           new={"wallet": mask_address(new_address), "currency": normalized,
                "payable_from": change.payable_from.isoformat()})
    db.commit()
    db.refresh(locked)
    return wallet_state(locked, now)


# ---------------------------------------------------------------------------
# Member preference
# ---------------------------------------------------------------------------

def set_cashout_method(db: Session, user: User, method: str, *, now: Optional[datetime] = None) -> str:
    """Record the member's choice. Commits. Moves no money and starts no
    payout: an open cashout keeps the method it was created with, and the
    balance is the same rows whichever method is chosen."""
    now = now or datetime.utcnow()
    method = str(method or "").strip().upper()
    if method not in CASHOUT_METHODS:
        raise CashoutError("INVALID_METHOD", "Choose Crypto Cashout or USD Cashout.")
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    previous = locked.cashout_method
    if previous != method:
        locked.cashout_method = method
        locked.cashout_method_changed_at = now
        db.flush()
        _audit(db, record_id=locked.id, action="CASHOUT_METHOD_CHANGED", actor_id=locked.id, table="users",
               old={"cashout_method": previous}, new={"cashout_method": method})
    db.commit()
    return method


def destination_ready(user: User, now: Optional[datetime] = None) -> bool:
    """Is there somewhere this member's commissions can be paid to?"""
    if user.cashout_method == METHOD_USD:
        return True
    if user.cashout_method == METHOD_CRYPTO:
        return wallet_state(user, now).payable
    return False


def release_pending(db: Session, user: User, *, now: Optional[datetime] = None) -> int:
    """PENDING -> APPROVED once the member has a usable destination. The row's
    amount is not touched. No commit."""
    if not destination_ready(user, now):
        return 0
    rows = (db.query(AffiliateCommission)
            .filter(AffiliateCommission.user_id == user.id,
                    AffiliateCommission.status == CommissionStatus.PENDING,
                    AffiliateCommission.payout_reference.is_(None))
            .with_for_update().all())
    for row in rows:
        row.status = CommissionStatus.APPROVED
    if rows:
        db.flush()
    return len(rows)


# ---------------------------------------------------------------------------
# Reserve / release / complete (shared with the crypto engine)
# ---------------------------------------------------------------------------

def active_cashout(db: Session, user_id: int) -> Optional[AffiliateCashoutRequest]:
    return (db.query(AffiliateCashoutRequest)
            .filter(AffiliateCashoutRequest.user_id == user_id,
                    AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES))
            .order_by(AffiliateCashoutRequest.id.desc()).first())


def available_rows(db: Session, user_id: int) -> List[AffiliateCommission]:
    """Unreserved APPROVED rows, oldest first, locked."""
    return (db.query(AffiliateCommission)
            .filter(AffiliateCommission.user_id == user_id,
                    AffiliateCommission.status == CommissionStatus.APPROVED,
                    AffiliateCommission.payout_reference.is_(None))
            .order_by(AffiliateCommission.transaction_date.asc(), AffiliateCommission.id.asc())
            .with_for_update().all())


def rows_total(rows: Iterable[AffiliateCommission]) -> Decimal:
    total = Decimal("0.00")
    for row in rows:
        total = money(total + positive_money(row.commission_amount))
    return total


def reserve(db: Session, user: User, rows: List[AffiliateCommission], *, method: str, fee: Decimal,
            intent_ref: str, now: datetime, wallet: Optional[str] = None,
            currency: Optional[str] = None) -> Optional[AffiliateCashoutRequest]:
    """Reserve these whole rows for ONE new cashout and commit. Returns None
    (after a rollback, with nothing reserved) when the database refused it
    because the member already has an open cashout or the intent exists."""
    gross = rows_total(rows)
    net = money(gross - fee)
    if gross <= 0 or net <= 0:
        raise CashoutError("NOTHING_TO_PAY", "There is nothing to pay out.")
    for row in rows:
        row.payout_reference = intent_ref
    cashout = AffiliateCashoutRequest(
        user_id=user.id, gross_amount=gross, fee=money(fee), net_amount=net,
        status=CashoutStatus.REQUESTED.value, cashout_method=method,
        payout_method="nowpayments_crypto" if method == METHOD_CRYPTO else "usd_manual",
        wallet_snapshot=wallet, payout_currency=currency, payout_reference=intent_ref, requested_at=now)
    db.add(cashout)
    try:
        db.flush()
        _audit(db, record_id=cashout.id, action="CASHOUT_RESERVED", actor_id=user.id, old=None,
               new={"method": method, "gross": str(gross), "fee": str(money(fee)), "net": str(net),
                    "commission_ids": [int(r.id) for r in rows], "wallet": mask_address(wallet)})
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(cashout)
    return cashout


def _intent(cashout: AffiliateCashoutRequest) -> str:
    return str(cashout.payout_reference or "").split(";provider:", 1)[0]


def reserved_rows(db: Session, cashout: AffiliateCashoutRequest) -> List[AffiliateCommission]:
    return (db.query(AffiliateCommission)
            .filter(AffiliateCommission.user_id == cashout.user_id,
                    AffiliateCommission.payout_reference == _intent(cashout))
            .order_by(AffiliateCommission.id.asc()).with_for_update().all())


def release_reservation(db: Session, cashout: AffiliateCashoutRequest, *, status: str, failure_code: str,
                        actor_id: Optional[int], now: datetime) -> int:
    """Record that this cashout was NOT paid and make its commissions available
    again. Only from an open state, so the same amount can never be released
    (or paid) twice. No commit."""
    if cashout.status not in ACTIVE_CASHOUT_STATUSES:
        raise CashoutError("NOT_OPEN", "This cashout is already closed.")
    if status not in (CashoutStatus.FAILED.value, CashoutStatus.CANCELLED.value):
        raise ValueError("release_reservation closes a cashout as failed or cancelled")
    rows = reserved_rows(db, cashout)
    for row in rows:
        if row.status == CommissionStatus.APPROVED:
            row.payout_reference = None
    old = {"status": cashout.status}
    cashout.status = status
    cashout.failure_code = failure_code
    cashout.processed_at = now
    db.flush()
    _audit(db, record_id=cashout.id, action="CASHOUT_RELEASED", actor_id=actor_id, old=old,
           new={"status": status, "failure_code": failure_code, "commissions_released": len(rows)})
    return len(rows)


def _post_journal(db: Session, cashout: AffiliateCashoutRequest, rows: List[AffiliateCommission],
                  cash_account: str, now: datetime) -> None:
    """Dr commissions payable (2001 direct / 2002 historical indirect), Cr the
    account the money left from, Cr 4005 cashout fee. Once per cashout."""
    description = f"Affiliate Cashout #{cashout.id}"
    if db.query(JournalEntry.id).filter(JournalEntry.description == description).first():
        return
    needed = {cash_account, "2001", "2002", "4005"}
    present = {code for (code,) in db.query(ChartOfAccounts.account_code)
               .filter(ChartOfAccounts.account_code.in_(needed)).all()}
    if needed - present:
        raise CashoutError("LEDGER_NOT_CONFIGURED",
                           "Payout accounting is not configured; missing accounts: " + ", ".join(sorted(needed - present)))
    direct = sum((money(r.commission_amount) for r in rows if r.level == 1), Decimal("0.00"))
    indirect = sum((money(r.commission_amount) for r in rows if r.level != 1), Decimal("0.00"))
    lines: list[dict] = []
    if direct:
        lines.append({"account_code": "2001", "debit": direct, "credit": 0, "description": description})
    if indirect:
        lines.append({"account_code": "2002", "debit": indirect, "credit": 0, "description": description})
    lines.append({"account_code": cash_account, "debit": 0, "credit": money(cashout.net_amount),
                  "description": f"Payout for {description}"})
    if money(cashout.fee) > 0:
        lines.append({"account_code": "4005", "debit": 0, "credit": money(cashout.fee),
                      "description": f"Cashout fee for {description}"})
    accounting_service.create_journal_entry(db, description=description, lines=lines, date=now, commit=False)


def complete(db: Session, cashout: AffiliateCashoutRequest, *, settlement_reference: str, cash_account: str,
             actor_id: Optional[int], now: datetime) -> int:
    """Record that this cashout WAS paid: its commissions become PAID and the
    journal is posted, in the caller's transaction. Only from an open state,
    and only if the reserved rows still add up to the cashout. No commit."""
    if cashout.status not in ACTIVE_CASHOUT_STATUSES:
        raise CashoutError("NOT_OPEN", "This cashout is already closed.")
    reference = str(settlement_reference or "").strip()
    if not reference:
        raise CashoutError("REFERENCE_REQUIRED", "A settlement reference is required.")
    rows = [r for r in reserved_rows(db, cashout) if r.status == CommissionStatus.APPROVED]
    if not rows or rows_total(rows) != money(cashout.gross_amount):
        raise CashoutError("RESERVATION_CHANGED",
                           "The reserved commissions no longer match this cashout; it needs manual reconciliation.")
    intent = _intent(cashout)
    _post_journal(db, cashout, rows, cash_account, now)
    for row in rows:
        row.status = CommissionStatus.PAID
        row.paid_date = now
        row.payout_reference = reference
    old = {"status": cashout.status}
    cashout.status = CashoutStatus.COMPLETED.value
    cashout.processed_at = now
    cashout.failure_code = None
    cashout.settlement_reference = reference
    cashout.payout_reference = f"{intent};provider:{reference}"
    db.flush()
    _audit(db, record_id=cashout.id, action="CASHOUT_COMPLETED", actor_id=actor_id, old=old,
           new={"status": cashout.status, "reference": reference, "commissions_paid": len(rows),
                "net": str(money(cashout.net_amount)), "fee": str(money(cashout.fee))})
    return len(rows)


# ---------------------------------------------------------------------------
# USD cashout (member request; settlement is recorded by an administrator)
# ---------------------------------------------------------------------------

def request_usd_cashout(db: Session, user: User, *, idempotency_key: Optional[str] = None,
                        amount: Optional[Decimal] = None,
                        now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """Reserve the member's whole available balance for a USD cashout request.
    Commits. Nothing is sent to any provider: the request is tracked until an
    administrator records its settlement or cancels it."""
    now = now or datetime.utcnow()
    intent_ref = _intent_reference(user.id, idempotency_key)
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    existing = _find_cashout_by_intent(db, intent_ref)
    if existing is not None:
        db.rollback()
        return existing                           # replay of the same request: nothing new
    if locked.cashout_method != METHOD_USD:
        db.rollback()
        raise CashoutError("METHOD_NOT_USD", "Choose USD Cashout as your cashout method first.")
    decision = fe.evaluate(db, locked, fe.FinancialOperation.WITHDRAWAL)
    if not decision.allowed:
        fe.record_decision(db, decision, user_id=locked.id, commit=True)
        raise fe.FinancialEligibilityHold(decision)
    if active_cashout(db, locked.id) is not None:
        db.rollback()
        raise CashoutError("CASHOUT_IN_PROGRESS", "You already have a cashout in progress.")
    release_pending(db, locked, now=now)
    rows = available_rows(db, locked.id)
    gross = rows_total(rows)
    minimum = usd_minimum()
    if gross < minimum:
        db.commit()                               # keeps PENDING -> APPROVED; reserves nothing
        raise CashoutError("BELOW_MINIMUM", f"USD Cashout needs an available balance of at least ${minimum:.2f}.")
    if amount is not None and money(amount) != gross:
        db.commit()
        raise CashoutError("AMOUNT_MISMATCH",
                           f"USD Cashout pays your whole available balance (${gross:.2f}).")
    fee = money(cashout_fee_and_net(gross).fee)
    cashout = reserve(db, locked, rows, method=METHOD_USD, fee=fee, intent_ref=intent_ref, now=now)
    if cashout is None:
        raise CashoutError("CASHOUT_IN_PROGRESS", "You already have a cashout in progress.")
    return cashout


def cancel_request(db: Session, cashout: AffiliateCashoutRequest, *, actor: User, reason: str,
                   now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """Cancel a cashout that is still only REQUESTED (nothing sent). Commits.
    The member may cancel their own; an administrator any."""
    now = now or datetime.utcnow()
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .with_for_update().one())
    if locked.user_id != actor.id and not actor.is_admin:
        db.rollback()
        raise CashoutError("FORBIDDEN", "Not allowed.")
    if locked.status != CashoutStatus.REQUESTED.value:
        db.rollback()
        raise CashoutError("NOT_CANCELLABLE", "Only a request that has not been processed can be cancelled.")
    release_reservation(db, locked, status=CashoutStatus.CANCELLED.value,
                        failure_code=("CANCELLED_BY_MEMBER" if locked.user_id == actor.id else "CANCELLED_BY_ADMIN"),
                        actor_id=actor.id, now=now)
    locked.reviewed_by = actor.id if actor.is_admin else None
    locked.reviewed_at = now
    _audit(db, record_id=locked.id, action="CASHOUT_CANCEL_REASON", actor_id=actor.id, old=None,
           new={"reason_present": bool((reason or "").strip())})
    db.commit()
    return locked


def usd_settlement_available() -> bool:
    return bool(settings.USD_CASHOUT_SETTLEMENT_ENABLED and (settings.USD_CASHOUT_SETTLEMENT_ACCOUNT or "").strip())


def settle_usd_cashout(db: Session, cashout: AffiliateCashoutRequest, *, admin: User, reference: str,
                       now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """Administrator records that a USD cashout was paid outside the platform.
    Commits. Refused until a USD payout channel is configured."""
    now = now or datetime.utcnow()
    if not admin.is_admin:
        raise CashoutError("FORBIDDEN", "Not allowed.")
    if not usd_settlement_available():
        raise CashoutError("USD_SETTLEMENT_DISABLED",
                           "USD settlement is not enabled: no USD payout channel is configured.")
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .with_for_update().one())
    if locked.cashout_method != METHOD_USD or locked.status != CashoutStatus.REQUESTED.value:
        db.rollback()
        raise CashoutError("NOT_SETTLEABLE", "Only an open USD cashout request can be settled.")
    member = db.query(User).filter(User.id == locked.user_id).with_for_update().one()
    decision = fe.evaluate(db, member, fe.FinancialOperation.WITHDRAWAL)
    if not decision.allowed:
        fe.record_decision(db, decision, user_id=member.id, actor_id=admin.id,
                           subject={"cashout_id": int(locked.id)}, commit=True)
        raise fe.FinancialEligibilityHold(decision)
    complete(db, locked, settlement_reference=reference,
             cash_account=settings.USD_CASHOUT_SETTLEMENT_ACCOUNT.strip(), actor_id=admin.id, now=now)
    locked.reviewed_by = admin.id
    locked.reviewed_at = now
    db.commit()
    return locked


def resolve_uncertain(db: Session, cashout: AffiliateCashoutRequest, *, admin: User, outcome: str,
                      reference: Optional[str] = None, now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """Administrator settles a crypto cashout whose provider outcome is unknown,
    after checking the provider: SENT (with the provider's reference) or
    NOT_SENT. Commits. Never calls the provider."""
    now = now or datetime.utcnow()
    if not admin.is_admin:
        raise CashoutError("FORBIDDEN", "Not allowed.")
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .with_for_update().one())
    if locked.cashout_method != METHOD_CRYPTO or locked.status != CashoutStatus.UNKNOWN.value:
        db.rollback()
        raise CashoutError("NOT_UNCERTAIN", "Only a crypto cashout with an unknown outcome can be resolved here.")
    outcome = str(outcome or "").strip().upper()
    if outcome == "SENT":
        complete(db, locked, settlement_reference=(reference or locked.provider_batch_id or ""),
                 cash_account=CRYPTO_TREASURY_ACCOUNT, actor_id=admin.id, now=now)
    elif outcome == "NOT_SENT":
        release_reservation(db, locked, status=CashoutStatus.FAILED.value,
                            failure_code="RESOLVED_NOT_SENT_BY_ADMIN", actor_id=admin.id, now=now)
    else:
        db.rollback()
        raise CashoutError("INVALID_OUTCOME", "Outcome must be SENT or NOT_SENT.")
    locked.reviewed_by = admin.id
    locked.reviewed_at = now
    db.commit()
    return locked


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------

def cashout_dict(cashout: AffiliateCashoutRequest, *, admin: bool = False) -> dict:
    out = {
        "id": cashout.id,
        "method": cashout.cashout_method or METHOD_CRYPTO,
        "status": cashout.status,
        "gross_amount": float(cashout.gross_amount),
        "fee": float(cashout.fee),
        "net_amount": float(cashout.net_amount),
        "destination": mask_address(cashout.wallet_snapshot),
        "payout_currency": cashout.payout_currency,
        "reference": cashout.settlement_reference or cashout.provider_batch_id,
        "requested_at": cashout.requested_at.isoformat() if cashout.requested_at else None,
        "processed_at": cashout.processed_at.isoformat() if cashout.processed_at else None,
    }
    if admin:
        out.update({"user_id": cashout.user_id, "provider_status": cashout.provider_status,
                    "failure_code": cashout.failure_code, "provider_batch_id": cashout.provider_batch_id,
                    "last_checked_at": cashout.last_checked_at.isoformat() if cashout.last_checked_at else None,
                    "reviewed_by": cashout.reviewed_by})
    return out


def history(db: Session, user_id: int, *, limit: int = 50) -> List[dict]:
    rows = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.user_id == user_id)
            .order_by(AffiliateCashoutRequest.id.desc()).limit(limit).all())
    return [cashout_dict(r) for r in rows]


def summary(db: Session, user: User, *, now: Optional[datetime] = None) -> dict:
    """Everything the member's cashout panel shows. Read-only."""
    now = now or datetime.utcnow()
    balance: CommissionBalance = get_commission_balance(db, user.id)
    method = user.cashout_method
    wallet = wallet_state(user, now)
    ready = destination_ready(user, now)
    # What the next cashout would pay: available, plus PENDING once a destination exists.
    payable = money(balance.available + (balance.pending if ready else Decimal("0.00")))
    minimum = crypto_minimum() if method == METHOD_CRYPTO else usd_minimum() if method == METHOD_USD else None
    open_cashout = active_cashout(db, user.id)
    eligibility = fe.evaluate(db, user, fe.FinancialOperation.WITHDRAWAL)

    from app.services.cashout_engine import engine_enabled

    if open_cashout is not None:
        status = "IN_PROGRESS"
    elif not eligibility.allowed:
        status = "ACCOUNT_HOLD"
    elif method is None:
        status = "METHOD_REQUIRED"
    elif method == METHOD_CRYPTO and wallet.status in (WALLET_MISSING, WALLET_INVALID, WALLET_UNVERIFIED):
        status = "WALLET_REQUIRED"
    elif method == METHOD_CRYPTO and wallet.status == WALLET_ON_HOLD:
        status = "WALLET_ON_HOLD"
    elif payable < minimum:
        status = "BELOW_MINIMUM"
    elif method == METHOD_CRYPTO:
        status = "AUTOMATIC_PAYOUT_PENDING" if engine_enabled() else "AUTOMATIC_PAYOUT_NOT_ACTIVE"
    else:
        status = "READY_TO_REQUEST"

    usd_fee = cashout_fee_and_net(payable) if payable >= usd_minimum() else None
    return {
        "cashout_method": method,
        "status": status,
        "balances": {
            "total_earned": float(balance.earned_lifetime),
            "pending": float(balance.pending),
            "available": float(balance.available),
            "reserved": float(balance.reserved),
            "paid": float(balance.paid_lifetime),
        },
        "payable_amount": float(payable),
        "minimum": float(minimum) if minimum is not None else None,
        "minimums": {"CRYPTO": float(crypto_minimum()), "USD": float(usd_minimum())},
        "fees": {
            "CRYPTO": {"platform_fee": 0.0,
                       "note": "No MyHigh5 fee. The blockchain network fee is paid by MyHigh5."},
            "USD": {"rule": "1% of the amount, minimum $20, maximum $1,000",
                    "fee": float(usd_fee.fee) if usd_fee else None,
                    "net_amount": float(usd_fee.net_to_member) if usd_fee else None},
        },
        "destination": {
            "type": method,
            "wallet": mask_address(wallet.address),
            "wallet_status": wallet.status,
            "payout_currency": wallet.currency or CRYPTO_PAYOUT_CURRENCY,
            "payable_from": wallet.payable_from.isoformat() if wallet.payable_from else None,
        },
        "crypto_payouts_active": engine_enabled(),
        "usd_settlement_active": usd_settlement_available(),
        "eligibility_status": eligibility.outcome.value,
        "eligibility_next_step": eligibility.next_step,
        "active_cashout": cashout_dict(open_cashout) if open_cashout is not None else None,
    }
