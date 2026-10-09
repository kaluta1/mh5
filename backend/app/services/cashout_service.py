"""Dual cashout of affiliate commissions: the member's choice, the payout
wallet, USD cashout requests, and the shared reserve / complete / release
steps that the automatic crypto engine (cashout_engine) also uses.

Business rules (owner requirement, 2026-10-08)
----------------------------------------------
* The affiliate program itself is unchanged: commissions are accrued for the
  DIRECT sponsor only, by new_model_revenue.accrue_direct_commission. Nothing
  here creates, resizes or re-rates a commission.
* A member chooses ONE cashout method:
    CRYPTO  paid automatically to the member's verified crypto wallet by the
            payout engine (off by default).
    USD     the member asks for it explicitly; the withdrawal fee applies.
* Every threshold, fee, hold and switch comes from ONE place,
  app.services.payment_config (Admin > Finance & Payments). The defaults are
  the rules the owner gave: crypto minimum $1, USD minimum $100, USD fee 1%
  (minimum $20, maximum $1,000), wallet hold 72 hours.
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

Payout wallet
-------------
A wallet is set or changed with the account password and, unless an
administrator switched that requirement off, takes effect only when the
member opens a one-time link sent to the account's email address. The link is
single-use, expires, and is bound to the exact address and network. Nothing is
paid to a wallet during the security hold that follows, and never to a wallet
saved before these rules (payout_wallet_verified_at IS NULL).

What this module does NOT establish: that the provider actually holds the
crypto. The ledger liability (accounts 2001/2002) and these rows say what is
OWED; whether the provider balance covers it is checked separately
(cashout_engine.reconciliation_report).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

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
from app.models.payment_config import PayoutWalletVerification
from app.models.user import User
from app.services import financial_eligibility as fe
from app.services import payment_config, payment_crypto
from app.services.accounting_service import accounting_service
from app.services.commission_payout_service import _find_cashout_by_intent, _intent_reference
from app.services.financial_balances import CommissionBalance, get_commission_balance
from app.services.financial_integrity import money, positive_money
from app.services.payment_config import PERMISSION_PROCESS, PaymentConfig
from app.services.wallet_validation import PAYOUT_CURRENCY_OPTIONS, normalize_payout_currency, validate_payout_address

logger = logging.getLogger(__name__)

METHOD_CRYPTO = "CRYPTO"
METHOD_USD = "USD"
CASHOUT_METHODS = (METHOD_CRYPTO, METHOD_USD)

WALLET_MISSING, WALLET_INVALID, WALLET_UNVERIFIED = "MISSING", "INVALID", "UNVERIFIED"
WALLET_ON_HOLD, WALLET_VERIFIED = "ON_HOLD", "VERIFIED"

VERIFIED_BY_EMAIL, VERIFIED_BY_PASSWORD = "EMAIL", "PASSWORD"
MAX_DESTINATION_LENGTH = 500


class CashoutError(ValueError):
    """A cashout action that cannot be carried out. `code` is stable and safe
    to show; nothing was changed unless the docstring of the caller says so."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Policy (always the central configuration)
# ---------------------------------------------------------------------------

def _config(db: Optional[Session], config: Optional[PaymentConfig] = None) -> PaymentConfig:
    if config is not None:
        return config
    return payment_config.load(db) if db is not None else payment_config.default_config()


def crypto_minimum(db: Optional[Session] = None, config: Optional[PaymentConfig] = None) -> Decimal:
    return positive_money(_config(db, config).crypto_min_usd)


def usd_minimum(db: Optional[Session] = None, config: Optional[PaymentConfig] = None) -> Decimal:
    return positive_money(_config(db, config).usd_min_usd)


def wallet_hold(db: Optional[Session] = None, config: Optional[PaymentConfig] = None) -> timedelta:
    return _config(db, config).wallet_hold


def mask_address(address: Optional[str]) -> Optional[str]:
    text = (address or "").strip()
    if not text:
        return None
    return text if len(text) < 12 else f"{text[:6]}...{text[-4:]}"


def network_label(currency: Optional[str]) -> str:
    return (PAYOUT_CURRENCY_OPTIONS.get(str(currency or "")) or {}).get("label") or str(currency or "").upper()


def _audit(db: Session, *, record_id: int, action: str, actor_id: Optional[int], old: Optional[dict],
           new: Optional[dict], table: str = "affiliate_cashout_requests", ip: Optional[str] = None) -> None:
    db.add(AuditTrail(table_name=table, record_id=record_id, action=action, old_values=old, new_values=new,
                      user_id=actor_id, ip_address=ip))


def _require_processor(actor: User) -> None:
    if not payment_config.has_permission(actor, PERMISSION_PROCESS):
        raise CashoutError("FORBIDDEN", f"The {PERMISSION_PROCESS} permission is required.")


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


@dataclass(frozen=True, repr=False)
class WalletChangeResult:
    state: WalletState                    # the wallet in force after the call
    pending: bool = False                 # a confirmation email is expected
    verification_id: Optional[int] = None
    token: Optional[str] = None           # one-time token for that email only; never returned by an API

    def __repr__(self) -> str:
        return f"WalletChangeResult(status={self.state.status}, pending={self.pending})"


def wallet_state(user: User, now: Optional[datetime] = None, *,
                 config: Optional[PaymentConfig] = None) -> WalletState:
    """Can the engine pay to this member's wallet right now?"""
    now = now or datetime.utcnow()
    config = _config(object_session(user), config)
    address = (user.usdt_wallet_address or "").strip()
    if not address:
        return WalletState(WALLET_MISSING)
    try:
        currency = normalize_payout_currency(user.payout_currency)
        if currency != config.crypto_payout_currency:
            raise ValueError("network not enabled")
        address = validate_payout_address(address, currency)
    except ValueError:
        return WalletState(WALLET_INVALID, address=address, currency=user.payout_currency)
    verified_at = user.payout_wallet_verified_at
    if verified_at is None:
        return WalletState(WALLET_UNVERIFIED, address=address, currency=currency)
    payable_from = verified_at + config.wallet_hold
    if now < payable_from:
        return WalletState(WALLET_ON_HOLD, address=address, currency=currency, payable_from=payable_from)
    return WalletState(WALLET_VERIFIED, address=address, currency=currency, payable_from=payable_from)


def _token_hash(raw: str, user_id: int, address: str, currency: str) -> str:
    return hashlib.sha256(f"{raw}|{user_id}|{address}|{currency}".encode("utf-8")).hexdigest()


def _crypto_payout_open(db: Session, user_id: int) -> bool:
    return db.query(AffiliateCashoutRequest.id).filter(
        AffiliateCashoutRequest.user_id == user_id,
        AffiliateCashoutRequest.cashout_method == METHOD_CRYPTO,
        AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES)).first() is not None


def _apply_wallet(db: Session, locked: User, *, address: str, currency: str, method: str, config: PaymentConfig,
                  ip: Optional[str], now: datetime) -> None:
    """Make this address the member's payout wallet and start its hold. No commit."""
    old_address = (locked.usdt_wallet_address or "").strip() or None
    locked.usdt_wallet_address = address
    locked.payout_currency = currency
    locked.payout_wallet_verified_at = now
    change = PayoutWalletChange(user_id=locked.id, old_address=old_address, new_address=address,
                                currency=currency, changed_at=now, payable_from=now + config.wallet_hold,
                                ip_address=ip, verification_method=method)
    db.add(change)
    db.flush()
    _audit(db, record_id=locked.id, action="PAYOUT_WALLET_CHANGED", actor_id=locked.id, table="users", ip=ip,
           old={"wallet": mask_address(old_address)},
           new={"wallet": mask_address(address), "currency": currency, "verified_by": method,
                "payable_from": change.payable_from.isoformat()})


def change_payout_wallet(db: Session, user: User, *, address: str, currency: Optional[str], password: str,
                         ip: Optional[str] = None, now: Optional[datetime] = None) -> WalletChangeResult:
    """Ask to set the member's payout wallet. Commits.

    Authorised by the member's CURRENT password (a stolen session alone cannot
    redirect payouts). With email verification required (the default) nothing
    changes yet: a pending confirmation is recorded and the caller emails its
    one-time link (send_wallet_confirmation); the wallet in force stays as it
    is until the link is opened. Otherwise the wallet is set at once. Either
    way a security hold follows before anything is paid to it, nothing is ever
    paid as a result of this call, and the number of requests is limited.
    Refused while a crypto payout of the member is in progress."""
    now = now or datetime.utcnow()
    config = payment_config.load(db)
    if not password or not verify_password(password, user.hashed_password):
        raise CashoutError("PASSWORD_REQUIRED", "Enter your current password to change the payout wallet.")
    normalized = normalize_payout_currency(currency)
    if normalized != config.crypto_payout_currency:
        raise CashoutError("NETWORK_NOT_ENABLED",
                           f"Only {network_label(config.crypto_payout_currency)} payouts are enabled.")
    new_address = validate_payout_address(address, normalized)

    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    old_address = (locked.usdt_wallet_address or "").strip() or None
    if old_address == new_address and locked.payout_wallet_verified_at is not None:
        state = wallet_state(locked, now, config=config)   # nothing to change; the hold is not restarted
        db.rollback()
        return WalletChangeResult(state)
    if _crypto_payout_open(db, locked.id):
        db.rollback()
        raise CashoutError("PAYOUT_IN_PROGRESS", "A payout is in progress. Try again when it has finished.")
    since = now - timedelta(hours=24)
    applied = (db.query(PayoutWalletChange)
               .filter(PayoutWalletChange.user_id == locked.id, PayoutWalletChange.changed_at > since).count())
    asked = (db.query(PayoutWalletVerification)
             .filter(PayoutWalletVerification.user_id == locked.id,
                     PayoutWalletVerification.requested_at > since).count())
    if max(applied, asked) >= int(config.wallet_max_changes_per_day):
        db.rollback()
        raise CashoutError("TOO_MANY_CHANGES", "The payout wallet was changed too often. Try again tomorrow.")

    if not config.wallet_email_verification_required:
        _apply_wallet(db, locked, address=new_address, currency=normalized, method=VERIFIED_BY_PASSWORD,
                      config=config, ip=ip, now=now)
        db.commit()
        db.refresh(locked)
        return WalletChangeResult(wallet_state(locked, now, config=config))

    # Newest request only: an earlier unused link stops working.
    (db.query(PayoutWalletVerification)
     .filter(PayoutWalletVerification.user_id == locked.id, PayoutWalletVerification.consumed_at.is_(None),
             PayoutWalletVerification.revoked_at.is_(None))
     .update({PayoutWalletVerification.revoked_at: now}, synchronize_session=False))
    raw = secrets.token_urlsafe(32)
    verification = PayoutWalletVerification(
        user_id=locked.id, address=new_address, currency=normalized,
        token_hash=_token_hash(raw, locked.id, new_address, normalized), requested_at=now,
        expires_at=now + timedelta(minutes=int(config.wallet_verification_ttl_minutes)), ip_address=ip)
    db.add(verification)
    db.flush()
    _audit(db, record_id=locked.id, action="PAYOUT_WALLET_CHANGE_REQUESTED", actor_id=locked.id, table="users",
           ip=ip, old={"wallet": mask_address(old_address)},
           new={"wallet": mask_address(new_address), "currency": normalized,
                "expires_at": verification.expires_at.isoformat()})
    verification_id = int(verification.id)
    db.commit()
    db.refresh(locked)
    return WalletChangeResult(wallet_state(locked, now, config=config), pending=True,
                              verification_id=verification_id, token=raw)


def _link_invalid() -> CashoutError:
    # One answer for every reason (unknown, used, replaced, expired, other account).
    return CashoutError("LINK_INVALID", "This confirmation link is not valid or has expired. "
                                        "Request a new one in Settings > Payout wallet.")


def confirm_payout_wallet(db: Session, user: User, token: str, *, ip: Optional[str] = None,
                          now: Optional[datetime] = None) -> WalletState:
    """Apply the wallet change a one-time link confirms. Commits.

    The link works once, only for the signed-in account it was issued to, only
    before it expires, and only for the exact address and network it was
    issued for. The security hold starts now."""
    now = now or datetime.utcnow()
    raw = str(token or "").strip()
    if not 20 <= len(raw) <= 200:
        raise _link_invalid()
    config = payment_config.load(db)
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    candidates = (db.query(PayoutWalletVerification)
                  .filter(PayoutWalletVerification.user_id == locked.id,
                          PayoutWalletVerification.consumed_at.is_(None),
                          PayoutWalletVerification.revoked_at.is_(None))
                  .order_by(PayoutWalletVerification.id.desc()).all())
    match = next((row for row in candidates
                  if hmac.compare_digest(row.token_hash, _token_hash(raw, locked.id, row.address, row.currency))),
                 None)
    if match is None or now >= match.expires_at:
        db.rollback()
        raise _link_invalid()
    if match.currency != config.crypto_payout_currency:
        db.rollback()
        raise CashoutError("NETWORK_NOT_ENABLED",
                           f"Only {network_label(config.crypto_payout_currency)} payouts are enabled.")
    if _crypto_payout_open(db, locked.id):
        db.rollback()
        raise CashoutError("PAYOUT_IN_PROGRESS", "A payout is in progress. Try again when it has finished.")
    consumed = (db.query(PayoutWalletVerification)
                .filter(PayoutWalletVerification.id == match.id, PayoutWalletVerification.consumed_at.is_(None),
                        PayoutWalletVerification.revoked_at.is_(None))
                .update({PayoutWalletVerification.consumed_at: now}, synchronize_session=False))
    if consumed != 1:
        db.rollback()
        raise _link_invalid()
    _apply_wallet(db, locked, address=match.address, currency=match.currency, method=VERIFIED_BY_EMAIL,
                  config=config, ip=ip, now=now)
    db.commit()
    db.refresh(locked)
    return wallet_state(locked, now, config=config)


def pending_wallet(db: Session, user_id: int, now: Optional[datetime] = None) -> Optional[dict]:
    """The wallet change waiting for its email confirmation, if any (masked)."""
    now = now or datetime.utcnow()
    row = (db.query(PayoutWalletVerification)
           .filter(PayoutWalletVerification.user_id == user_id, PayoutWalletVerification.consumed_at.is_(None),
                   PayoutWalletVerification.revoked_at.is_(None), PayoutWalletVerification.expires_at > now)
           .order_by(PayoutWalletVerification.id.desc()).first())
    if row is None:
        return None
    return {"wallet": mask_address(row.address), "payout_currency": row.currency,
            "network": network_label(row.currency), "expires_at": row.expires_at.isoformat()}


def send_wallet_confirmation(db: Session, user: User, result: WalletChangeResult) -> bool:
    """Queue the confirmation email of a pending wallet change. Call AFTER
    change_payout_wallet returned (its transaction is committed). True when
    the email was queued; never raises."""
    if not result.pending or not result.token or not result.verification_id:
        return False
    from app.services.email import email_service
    from app.services.email_events import EmailEvent

    row = (db.query(PayoutWalletVerification)
           .filter(PayoutWalletVerification.id == result.verification_id).first())
    if row is None:
        return False
    minutes = max(1, int((row.expires_at - row.requested_at).total_seconds() // 60))
    delivery = email_service.enqueue(
        db, event=EmailEvent.PAYOUT_WALLET_CONFIRMATION, recipient=user.email,
        idempotency_key=f"payout-wallet-confirmation:{row.id}", user_id=user.id,
        context={"link_credential": result.token, "wallet": mask_address(row.address),
                 "network": network_label(row.currency), "minutes": minutes})
    return delivery is not None and delivery.status == "QUEUED"


# ---------------------------------------------------------------------------
# Member preference
# ---------------------------------------------------------------------------

def method_available(config: PaymentConfig, method: Optional[str]) -> bool:
    if method == METHOD_CRYPTO:
        return bool(config.crypto_cashout_enabled)
    if method == METHOD_USD:
        return bool(config.usd_cashout_enabled)
    return False


def set_cashout_method(db: Session, user: User, method: str, *, now: Optional[datetime] = None) -> str:
    """Record the member's choice. Commits. Moves no money and starts no
    payout: an open cashout keeps the method it was created with, and the
    balance is the same rows whichever method is chosen."""
    now = now or datetime.utcnow()
    method = str(method or "").strip().upper()
    if method not in CASHOUT_METHODS:
        raise CashoutError("INVALID_METHOD", "Choose Crypto Cashout or USD Cashout.")
    if not method_available(payment_config.load(db), method):
        raise CashoutError("METHOD_UNAVAILABLE", "This cashout method is not available at the moment.")
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


def destination_ready(user: User, now: Optional[datetime] = None, *,
                      config: Optional[PaymentConfig] = None) -> bool:
    """Is there somewhere this member's commissions can be paid to?"""
    if user.cashout_method == METHOD_USD:
        return True
    if user.cashout_method == METHOD_CRYPTO:
        return wallet_state(user, now, config=config).payable
    return False


def release_pending(db: Session, user: User, *, now: Optional[datetime] = None,
                    config: Optional[PaymentConfig] = None) -> int:
    """PENDING -> APPROVED once the member has a usable destination. The row's
    amount is not touched. No commit."""
    if not destination_ready(user, now, config=config):
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
            intent_ref: str, now: datetime, wallet: Optional[str] = None, currency: Optional[str] = None,
            network_fee: Optional[Decimal] = None, network_fee_policy: Optional[str] = None,
            net: Optional[Decimal] = None,
            destination_ciphertext: Optional[str] = None) -> Optional[AffiliateCashoutRequest]:
    """Reserve these whole rows for ONE new cashout and commit. Returns None
    (after a rollback, with nothing reserved) when the database refused it
    because the member already has an open cashout or the intent exists.

    `fee` is the MyHigh5 fee. `net` is what the member receives; it defaults
    to gross - fee and may only be lower (a network fee the member bears)."""
    gross = rows_total(rows)
    fee = money(fee)
    net = money(gross - fee) if net is None else money(net)
    if gross <= 0 or net <= 0 or fee < 0 or net > money(gross - fee):
        raise CashoutError("NOTHING_TO_PAY", "There is nothing to pay out.")
    for row in rows:
        row.payout_reference = intent_ref
    cashout = AffiliateCashoutRequest(
        user_id=user.id, gross_amount=gross, fee=fee, net_amount=net,
        status=CashoutStatus.REQUESTED.value, cashout_method=method,
        payout_method="nowpayments_crypto" if method == METHOD_CRYPTO else "usd_manual",
        wallet_snapshot=wallet, payout_currency=currency, payout_reference=intent_ref, requested_at=now,
        network_fee=money(network_fee) if network_fee is not None else None,
        network_fee_policy=network_fee_policy, destination_ciphertext=destination_ciphertext)
    db.add(cashout)
    try:
        db.flush()
        _audit(db, record_id=cashout.id, action="CASHOUT_RESERVED", actor_id=user.id, old=None,
               new={"method": method, "gross": str(gross), "fee": str(fee), "net": str(net),
                    "commission_ids": [int(r.id) for r in rows], "wallet": mask_address(wallet),
                    "network_fee_policy": network_fee_policy})
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
    account the money left from (the amount less the MyHigh5 fee), Cr 4005
    cashout fee. Once per cashout. A network fee the member bears is part of
    what left the account, not MyHigh5 income."""
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
    lines.append({"account_code": cash_account, "debit": 0,
                  "credit": money(money(cashout.gross_amount) - money(cashout.fee)),
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

def _seal_destination(config: PaymentConfig, destination: Optional[str]) -> Optional[str]:
    text = str(destination or "").strip()
    if not text:
        if config.usd_destination_required:
            raise CashoutError("DESTINATION_REQUIRED", "Enter where your USD Cashout should be paid.")
        return None
    if len(text) > MAX_DESTINATION_LENGTH:
        raise CashoutError("DESTINATION_TOO_LONG",
                           f"Payout destination details may have at most {MAX_DESTINATION_LENGTH} characters.")
    if not payment_crypto.key_configured():
        # Never stored in the clear, and never silently dropped.
        raise CashoutError("CONFIGURATION_REQUIRED",
                           "Payout destination details cannot be stored securely yet. Please contact support.")
    return payment_crypto.encrypt(text, payment_crypto.PURPOSE_USD_DESTINATION)


def request_usd_cashout(db: Session, user: User, *, idempotency_key: Optional[str] = None,
                        amount: Optional[Decimal] = None, destination: Optional[str] = None,
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
    config = payment_config.load(db)
    if not config.usd_cashout_enabled:
        db.rollback()
        raise CashoutError("METHOD_UNAVAILABLE", "USD Cashout requests are not available at the moment.")
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
    try:
        sealed = _seal_destination(config, destination)
    except CashoutError:
        db.rollback()
        raise
    release_pending(db, locked, now=now, config=config)
    rows = available_rows(db, locked.id)
    gross = rows_total(rows)
    minimum = usd_minimum(config=config)
    if gross < minimum:
        db.commit()                               # keeps PENDING -> APPROVED; reserves nothing
        raise CashoutError("BELOW_MINIMUM", f"USD Cashout needs an available balance of at least ${minimum:.2f}.")
    if amount is not None and money(amount) != gross:
        db.commit()
        raise CashoutError("AMOUNT_MISMATCH",
                           f"USD Cashout pays your whole available balance (${gross:.2f}).")
    fee, net = config.usd_fee(gross)
    if net <= 0:
        db.commit()
        raise CashoutError("BELOW_MINIMUM", "The withdrawal fee would leave nothing to pay out.")
    cashout = reserve(db, locked, rows, method=METHOD_USD, fee=fee, intent_ref=intent_ref, now=now,
                      destination_ciphertext=sealed)
    if cashout is None:
        raise CashoutError("CASHOUT_IN_PROGRESS", "You already have a cashout in progress.")
    return cashout


def cancel_request(db: Session, cashout: AffiliateCashoutRequest, *, actor: User, reason: str,
                   now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """Cancel a cashout that is still only REQUESTED (nothing sent). Commits.
    The member may cancel their own USD request (unless an administrator
    switched that off); an authorized administrator may cancel any."""
    now = now or datetime.utcnow()
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .with_for_update().one())
    own = locked.user_id == actor.id
    privileged = payment_config.has_permission(actor, PERMISSION_PROCESS)
    if not own and not privileged:
        db.rollback()
        raise CashoutError("FORBIDDEN", "Not allowed.")
    if locked.status != CashoutStatus.REQUESTED.value:
        db.rollback()
        raise CashoutError("NOT_CANCELLABLE", "Only a request that has not been processed can be cancelled.")
    if own and not privileged:
        if locked.cashout_method != METHOD_USD:
            db.rollback()
            raise CashoutError("NOT_CANCELLABLE", "Only a USD Cashout request can be cancelled.")
        if not payment_config.load(db).usd_member_cancellation_allowed:
            db.rollback()
            raise CashoutError("CANCELLATION_NOT_ALLOWED", "Please contact support to cancel this request.")
    release_reservation(db, locked, status=CashoutStatus.CANCELLED.value,
                        failure_code=("CANCELLED_BY_MEMBER" if own else "CANCELLED_BY_ADMIN"),
                        actor_id=actor.id, now=now)
    locked.reviewed_by = actor.id if not own else None
    locked.reviewed_at = now
    locked.destination_ciphertext = None          # no longer needed once nothing will be paid
    _audit(db, record_id=locked.id, action="CASHOUT_CANCEL_REASON", actor_id=actor.id, old=None,
           new={"reason_present": bool((reason or "").strip())})
    db.commit()
    return locked


def usd_settlement_available(db: Optional[Session] = None, config: Optional[PaymentConfig] = None) -> bool:
    return _config(db, config).usd_settlement_allowed


def settle_usd_cashout(db: Session, cashout: AffiliateCashoutRequest, *, admin: User, reference: str,
                       now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """An authorized administrator records that a USD cashout was paid outside
    the platform, with the external payment reference as evidence. Commits.
    Refused until USD settlement is enabled (server switch, Admin switch and a
    settlement ledger account)."""
    now = now or datetime.utcnow()
    _require_processor(admin)
    config = payment_config.load(db)
    if not config.usd_settlement_allowed:
        raise CashoutError("USD_SETTLEMENT_DISABLED",
                           "USD settlement is not enabled: no USD payout channel is configured.")
    reference = str(reference or "").strip()
    if len(reference) < int(config.usd_reference_min_length):
        raise CashoutError("REFERENCE_REQUIRED", "Enter the external payment reference "
                           f"(at least {config.usd_reference_min_length} characters).")
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .with_for_update().one())
    if locked.cashout_method != METHOD_USD or locked.status != CashoutStatus.REQUESTED.value:
        db.rollback()
        raise CashoutError("NOT_SETTLEABLE", "Only an open USD cashout request can be settled.")
    if (db.query(AffiliateCashoutRequest.id)
            .filter(AffiliateCashoutRequest.settlement_reference == reference,
                    AffiliateCashoutRequest.id != locked.id).first()):
        db.rollback()
        raise CashoutError("REFERENCE_ALREADY_USED", "This payment reference is already recorded on another cashout.")
    member = db.query(User).filter(User.id == locked.user_id).with_for_update().one()
    decision = fe.evaluate(db, member, fe.FinancialOperation.WITHDRAWAL)
    if not decision.allowed:
        fe.record_decision(db, decision, user_id=member.id, actor_id=admin.id,
                           subject={"cashout_id": int(locked.id)}, commit=True)
        raise fe.FinancialEligibilityHold(decision)
    complete(db, locked, settlement_reference=reference, cash_account=config.usd_settlement_account.strip(),
             actor_id=admin.id, now=now)
    locked.reviewed_by = admin.id
    locked.reviewed_at = now
    db.commit()
    return locked


def resolve_uncertain(db: Session, cashout: AffiliateCashoutRequest, *, admin: User, outcome: str,
                      reference: Optional[str] = None, now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """An authorized administrator settles a crypto cashout whose provider
    outcome is unknown, after checking the provider: SENT (with the provider's
    reference) or NOT_SENT. Commits. Never calls the provider."""
    now = now or datetime.utcnow()
    _require_processor(admin)
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .with_for_update().one())
    if locked.cashout_method != METHOD_CRYPTO or locked.status != CashoutStatus.UNKNOWN.value:
        db.rollback()
        raise CashoutError("NOT_UNCERTAIN", "Only a crypto cashout with an unknown outcome can be resolved here.")
    outcome = str(outcome or "").strip().upper()
    if outcome == "SENT":
        complete(db, locked, settlement_reference=(reference or locked.provider_batch_id or ""),
                 cash_account=payment_config.load(db).treasury_account, actor_id=admin.id, now=now)
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


def reveal_usd_destination(db: Session, cashout: AffiliateCashoutRequest, *, admin: User,
                           ip: Optional[str] = None) -> Optional[str]:
    """The member's payout destination details, for the administrator who is
    about to pay the request. Every reveal is audited. Commits."""
    _require_processor(admin)
    if not cashout.destination_ciphertext:
        return None
    try:
        text = payment_crypto.decrypt(cashout.destination_ciphertext, payment_crypto.PURPOSE_USD_DESTINATION)
    except payment_crypto.PaymentCryptoError:
        raise CashoutError("CONFIGURATION_REQUIRED",
                           "The destination details cannot be decrypted (PAYMENT_SETTINGS_ENCRYPTION_KEY is "
                           "missing or was changed).") from None
    _audit(db, record_id=cashout.id, action="CASHOUT_DESTINATION_VIEWED", actor_id=admin.id, old=None, new=None,
           ip=ip)
    db.commit()
    return text


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
        "network_fee": float(cashout.network_fee) if cashout.network_fee is not None else None,
        "network_fee_policy": cashout.network_fee_policy,
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
                    "reviewed_by": cashout.reviewed_by,
                    "reviewed_at": cashout.reviewed_at.isoformat() if cashout.reviewed_at else None,
                    "has_destination_details": bool(cashout.destination_ciphertext)})
    return out


def history(db: Session, user_id: int, *, limit: int = 50) -> List[dict]:
    rows = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.user_id == user_id)
            .order_by(AffiliateCashoutRequest.id.desc()).limit(limit).all())
    return [cashout_dict(r) for r in rows]


def summary(db: Session, user: User, *, now: Optional[datetime] = None) -> dict:
    """Everything the member's cashout panel shows. Read-only."""
    now = now or datetime.utcnow()
    config = payment_config.load(db)
    balance: CommissionBalance = get_commission_balance(db, user.id)
    method = user.cashout_method
    wallet = wallet_state(user, now, config=config)
    pending = pending_wallet(db, user.id, now)
    ready = destination_ready(user, now, config=config)
    # What the next cashout would pay: available, plus PENDING once a destination exists.
    payable = money(balance.available + (balance.pending if ready else Decimal("0.00")))
    crypto_min, usd_min = crypto_minimum(config=config), usd_minimum(config=config)
    minimum = crypto_min if method == METHOD_CRYPTO else usd_min if method == METHOD_USD else None
    open_cashout = active_cashout(db, user.id)
    eligibility = fe.evaluate(db, user, fe.FinancialOperation.WITHDRAWAL)

    from app.services.cashout_engine import engine_enabled

    engine_on = engine_enabled(db, config=config)
    if open_cashout is not None:
        status = "IN_PROGRESS"
    elif not eligibility.allowed:
        status = "ACCOUNT_HOLD"
    elif method is None:
        status = "METHOD_REQUIRED"
    elif not method_available(config, method):
        status = "METHOD_UNAVAILABLE"
    elif method == METHOD_CRYPTO and wallet.status in (WALLET_MISSING, WALLET_INVALID, WALLET_UNVERIFIED):
        status = "WALLET_CONFIRMATION_PENDING" if pending is not None else "WALLET_REQUIRED"
    elif method == METHOD_CRYPTO and wallet.status == WALLET_ON_HOLD:
        status = "WALLET_ON_HOLD"
    elif payable < minimum:
        status = "BELOW_MINIMUM"
    elif method == METHOD_CRYPTO:
        status = "AUTOMATIC_PAYOUT_PENDING" if engine_on else "AUTOMATIC_PAYOUT_NOT_ACTIVE"
    else:
        status = "READY_TO_REQUEST"

    usd_fee = config.usd_fee(payable) if payable >= usd_min else None
    member_pays = config.network_fee_policy == payment_config.FEE_MEMBER_PAYS
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
        "minimums": {"CRYPTO": float(crypto_min), "USD": float(usd_min)},
        "methods": {
            "CRYPTO": {"available": bool(config.crypto_cashout_enabled)},
            "USD": {"available": bool(config.usd_cashout_enabled),
                    "destination_required": bool(config.usd_destination_required),
                    "destination_note": config.usd_destination_note,
                    "cancellation_allowed": bool(config.usd_member_cancellation_allowed)},
        },
        "fees": {
            "CRYPTO": {"platform_fee": 0.0, "network_fee_policy": config.network_fee_policy,
                       "note": ("No MyHigh5 fee. The blockchain network fee is deducted from the amount sent."
                                if member_pays else
                                "No MyHigh5 fee. The blockchain network fee is paid by MyHigh5.")},
            "USD": {"rule": config.usd_fee_rule(),
                    "fee": float(usd_fee[0]) if usd_fee else None,
                    "net_amount": float(usd_fee[1]) if usd_fee else None},
        },
        "destination": {
            "type": method,
            "wallet": mask_address(wallet.address),
            "wallet_status": wallet.status,
            "payout_currency": wallet.currency or config.crypto_payout_currency,
            "network": network_label(wallet.currency or config.crypto_payout_currency),
            "payable_from": wallet.payable_from.isoformat() if wallet.payable_from else None,
            "hold_hours": int(config.wallet_hold_hours),
            "email_verification_required": bool(config.wallet_email_verification_required),
            "pending_wallet": pending,
        },
        "crypto_payouts_active": engine_on,
        "usd_settlement_active": config.usd_settlement_allowed,
        "eligibility_status": eligibility.outcome.value,
        "eligibility_next_step": eligibility.next_step,
        "active_cashout": cashout_dict(open_cashout) if open_cashout is not None else None,
    }
