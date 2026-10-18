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
from decimal import ROUND_UP, Decimal
from typing import Iterable, List, Optional

from sqlalchemy import or_
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
from app.models.payment_config import CashoutFeeConsent, PayoutWalletVerification
from app.models.user import User
from app.services import financial_eligibility as fe
from app.services import payment_config, payment_crypto, reauth
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
# Administrator approval of the wallet (payout_wallet_approval).
WALLET_PENDING_APPROVAL, WALLET_REJECTED = "PENDING_APPROVAL", "REJECTED"

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


# Every administrator action below locks the cashout row with
# populate_existing(): the copy the caller loaded may be older than the lock
# (two administrators with the same cashout open), and without it SQLAlchemy
# keeps the older values of an object it already holds. The decision is made on
# the row as it is under the lock.

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
    approval_id: Optional[int] = None     # the administrator approval this wallet is paid under

    @property
    def payable(self) -> bool:
        return self.status == WALLET_VERIFIED and self.approval_id is not None


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
    # Owner rule 2026-10-18: an administrator approves every wallet and every change.
    from app.services import payout_wallet_approval as approvals

    session = object_session(user)
    submission = approvals.current(session, user.id) if session is not None else None
    if submission is None or not approvals._same(submission.address, address) or submission.currency != currency:
        # A wallet saved before approvals existed: it must be submitted again.
        return WalletState(WALLET_UNVERIFIED, address=address, currency=currency)
    if submission.status == approvals.REJECTED:
        return WalletState(WALLET_REJECTED, address=address, currency=currency)
    if submission.status != approvals.APPROVED:
        return WalletState(WALLET_PENDING_APPROVAL, address=address, currency=currency)
    payable_from = verified_at + config.wallet_hold
    if now < payable_from:
        return WalletState(WALLET_ON_HOLD, address=address, currency=currency, payable_from=payable_from,
                           approval_id=submission.id)
    return WalletState(WALLET_VERIFIED, address=address, currency=currency, payable_from=payable_from,
                       approval_id=submission.id)


def _token_hash(raw: str, user_id: int, address: str, currency: str) -> str:
    return hashlib.sha256(f"{raw}|{user_id}|{address}|{currency}".encode("utf-8")).hexdigest()


def _crypto_payout_open(db: Session, user_id: int) -> bool:
    return db.query(AffiliateCashoutRequest.id).filter(
        AffiliateCashoutRequest.user_id == user_id,
        AffiliateCashoutRequest.cashout_method == METHOD_CRYPTO,
        AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES)).first() is not None


def _apply_wallet(db: Session, locked: User, *, address: str, currency: str, method: str, config: PaymentConfig,
                  ip: Optional[str], now: datetime) -> int:
    """Make this address the member's payout wallet, start its hold and submit it
    for administrator approval. Returns the approval row id. No commit."""
    from app.services import payout_wallet_approval as approvals

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
    submission = approvals.submit(db, locked, address=address, currency=currency, method=method,
                                  wallet_change_id=change.id, ip=ip, now=now)
    if not locked.cashout_method and config.crypto_cashout_enabled:
        # Setting a USDT payout wallet is the member's choice of automatic crypto payouts
        # (owner rule 2026-10-18: no separate withdrawal request). An explicit choice is kept.
        locked.cashout_method = METHOD_CRYPTO
        locked.cashout_method_changed_at = now
        _audit(db, record_id=locked.id, action="CASHOUT_METHOD_CHANGED", actor_id=locked.id, table="users",
               old={"cashout_method": None}, new={"cashout_method": METHOD_CRYPTO, "by": "PAYOUT_WALLET_SET"})
    return int(submission.id)


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
    try:
        # Counted with every other endpoint that asks for the password (app.services.reauth).
        reauth.verify(db, user, password)
    except reauth.ReauthError as exc:
        if exc.code == reauth.LOCKED:
            raise CashoutError("PASSWORD_LOCKED", str(exc)) from None
        raise CashoutError("PASSWORD_REQUIRED", "Enter your current password to change the payout wallet.") from None
    normalized = normalize_payout_currency(currency)
    if normalized != config.crypto_payout_currency:
        raise CashoutError("NETWORK_NOT_ENABLED",
                           f"Only {network_label(config.crypto_payout_currency)} payouts are enabled.")
    new_address = validate_payout_address(address, normalized)

    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    old_address = (locked.usdt_wallet_address or "").strip() or None
    if old_address == new_address and locked.payout_wallet_verified_at is not None:
        state = wallet_state(locked, now, config=config)
        if state.status not in (WALLET_REJECTED, WALLET_UNVERIFIED):
            db.rollback()                                  # nothing to change; the hold is not restarted
            return WalletChangeResult(state)
        # A rejected (or never approved) address may be submitted again for a new decision.
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
        approval_id = _apply_wallet(db, locked, address=new_address, currency=normalized,
                                    method=VERIFIED_BY_PASSWORD, config=config, ip=ip, now=now)
        db.commit()
        db.refresh(locked)
        from app.services import payout_notifications

        payout_notifications.wallet_submitted(db, locked, approval_id)
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
    approval_id = _apply_wallet(db, locked, address=match.address, currency=match.currency,
                                method=VERIFIED_BY_EMAIL, config=config, ip=ip, now=now)
    db.commit()
    db.refresh(locked)
    from app.services import payout_notifications

    payout_notifications.wallet_submitted(db, locked, approval_id)
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
    from app.services.commission_payout_hold import payable_clause

    rows = (db.query(AffiliateCommission)
            .filter(AffiliateCommission.user_id == user.id,
                    AffiliateCommission.status == CommissionStatus.PENDING,
                    AffiliateCommission.payout_reference.is_(None),
                    payable_clause())          # a held historical row stays exactly as it is
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


def active_pooled_cashout(db: Session, user_id: int) -> Optional[AffiliateCashoutRequest]:
    """An open cashout of several commissions (a USD request, or a crypto payout
    written before individual payouts). At most one per member (database index);
    while it is open no individual payout of that member starts."""
    return (db.query(AffiliateCashoutRequest)
            .filter(AffiliateCashoutRequest.user_id == user_id,
                    AffiliateCashoutRequest.commission_id.is_(None),
                    AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES))
            .order_by(AffiliateCashoutRequest.id.desc()).first())


def available_rows(db: Session, user_id: int) -> List[AffiliateCommission]:
    """Unreserved APPROVED rows that may be paid (never a held historical row), oldest first, locked."""
    from app.services.commission_payout_hold import payable_clause

    return (db.query(AffiliateCommission)
            .filter(AffiliateCommission.user_id == user_id,
                    AffiliateCommission.status == CommissionStatus.APPROVED,
                    AffiliateCommission.payout_reference.is_(None),
                    payable_clause())
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
            net: Optional[Decimal] = None, destination_ciphertext: Optional[str] = None,
            beneficiary_fee: Optional[dict] = None,
            audit_extra: Optional[dict] = None, commission_id: Optional[int] = None,
            wallet_approval_id: Optional[int] = None) -> Optional[AffiliateCashoutRequest]:
    """Reserve these whole rows for ONE new cashout and commit. Returns None
    (after a rollback, with nothing reserved) when the database refused it
    because the member already has an open cashout or the intent exists.

    `fee` is the MyHigh5 fee. `net` is what the member receives; it defaults
    to gross - fee and may only be lower (a network fee the member bears).
    `beneficiary_fee` carries the full-precision figures of a payout whose
    network fee the beneficiary bears (see beneficiary_fee_plan). `audit_extra`
    is added to the audit record only (e.g. the configuration version)."""
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
        network_fee_policy=network_fee_policy, destination_ciphertext=destination_ciphertext,
        commission_id=commission_id, wallet_approval_id=wallet_approval_id,
        **(beneficiary_fee or {}))
    db.add(cashout)
    try:
        db.flush()
        _audit(db, record_id=cashout.id, action="CASHOUT_RESERVED", actor_id=user.id, old=None,
               new={"method": method, "gross": str(gross), "fee": str(fee), "net": str(net),
                    "commission_ids": [int(r.id) for r in rows], "wallet": mask_address(wallet),
                    "wallet_approval_id": wallet_approval_id,
                    "network_fee_policy": network_fee_policy, **(audit_extra or {}),
                    **{name: (_exact(value) if isinstance(value, Decimal) else value)
                       for name, value in (beneficiary_fee or {}).items()}})
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
    cashout fee. Once per cashout.

    A network fee the BENEFICIARY bears is not a line here: the whole amount
    was handed to the provider, which took its fee out of it, so the whole
    amount left the treasury and the whole liability is settled. It is neither
    income nor an expense of MyHigh5 and never touches 5005; what the provider
    kept and what the beneficiary received are kept on the cashout itself."""
    description = f"Affiliate Cashout #{cashout.id}"
    if db.query(JournalEntry.id).filter(JournalEntry.description == description).first():
        return
    needed = {cash_account, "2001", "2002", "4005"}
    accounts = dict(db.query(ChartOfAccounts.account_code, ChartOfAccounts.is_active)
                    .filter(ChartOfAccounts.account_code.in_(needed)).all())
    if needed - set(accounts):
        raise CashoutError("LEDGER_NOT_CONFIGURED",
                           "Payout accounting is not configured; missing accounts: "
                           + ", ".join(sorted(needed - set(accounts))))
    # A NEW entry is never posted to an account that was switched off, and is
    # never redirected to another one. Entries already posted are not touched.
    inactive = sorted(code for code, active in accounts.items() if active is False)
    if inactive:
        raise CashoutError("LEDGER_ACCOUNT_INACTIVE",
                           "Payout accounting cannot post to an inactive account: " + ", ".join(inactive))
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
# Network fee of a crypto payout that MyHigh5 pays (policy COMPANY_PAYS)
#
# The cashout's own entry debits the commission liability and credits the
# treasury account with what the member received. When MyHigh5 also bears the
# network fee, the provider takes that fee from the same balance, so a second
# entry records it:   Dr 5005 network fee expense / Cr treasury (1001).
#
# Only an ACTUAL fee is ever posted: the amount the provider reported for the
# finished payout (and only when it says the fee came from our balance), or
# the amount an authorised administrator reads from the provider's statement.
# The estimate taken when the payout was created is never posted. Nothing is
# posted for a payout that is not completed. One record per cashout.
#
# The payout currency is a US-dollar stablecoin that this ledger carries at
# 1 USDT = 1 USD (as the payout itself is), so no conversion is applied; a
# payout in any other kind of currency is refused here. The ledger keeps
# cents: the fee is rounded half-up to the cent and the exact reported figure
# is kept in the audit trail.
# ---------------------------------------------------------------------------

FEE_SOURCE_PROVIDER, FEE_SOURCE_ADMIN = "PROVIDER_REPORTED", "ADMIN_RECORDED"
FEE_POSTED, FEE_NONE, FEE_NOT_RECORDED, FEE_NOT_APPLICABLE = "POSTED", "NONE", "NOT_RECORDED", "NOT_APPLICABLE"
_FEE_AUDIT_ACTIONS = ("CASHOUT_NETWORK_FEE_POSTED", "CASHOUT_NETWORK_FEE_NONE")


def network_fee_description(cashout_id: int) -> str:
    return f"Network fee - Affiliate Cashout #{cashout_id}"


def network_fee_applies(cashout: AffiliateCashoutRequest) -> bool:
    return (cashout.cashout_method == METHOD_CRYPTO and cashout.status == CashoutStatus.COMPLETED.value
            and cashout.network_fee_policy == payment_config.FEE_COMPANY_PAYS)


def network_fee_state(db: Session, cashout: AffiliateCashoutRequest) -> dict:
    """What the books say about this payout's network fee."""
    estimate = str(money(cashout.network_fee)) if cashout.network_fee is not None else None
    out = {"status": FEE_NOT_APPLICABLE, "amount": None, "source": None, "reported": None, "estimate": estimate}
    if not network_fee_applies(cashout):
        return out
    record = (db.query(AuditTrail)
              .filter(AuditTrail.table_name == "affiliate_cashout_requests", AuditTrail.record_id == cashout.id,
                      AuditTrail.action.in_(_FEE_AUDIT_ACTIONS)).order_by(AuditTrail.id.desc()).first())
    if record is None:
        return {**out, "status": FEE_NOT_RECORDED}
    values = record.new_values or {}
    posted = record.action == "CASHOUT_NETWORK_FEE_POSTED"
    return {**out, "status": FEE_POSTED if posted else FEE_NONE, "amount": values.get("amount"),
            "source": values.get("source"), "reported": values.get("reported_amount")}


def record_network_fee(db: Session, cashout: AffiliateCashoutRequest, *, amount, source: str,
                       actor_id: Optional[int], now: datetime, reference: Optional[str] = None,
                       reported_by: Optional[str] = None) -> str:
    """Record the network fee MyHigh5 actually paid for one completed crypto
    cashout: Dr 5005 / Cr the treasury account, in the caller's transaction.
    Returns POSTED, or NONE when the fee is zero or rounds to no cents (the
    figure is still recorded; no entry is posted). Once per cashout. No commit.
    The cashout row must be locked by the caller."""
    if cashout.cashout_method != METHOD_CRYPTO or cashout.status != CashoutStatus.COMPLETED.value:
        raise CashoutError("NOT_COMPLETED", "A network fee is recorded only for a completed crypto payout.")
    if cashout.network_fee_policy != payment_config.FEE_COMPANY_PAYS:
        raise CashoutError("FEE_NOT_COMPANY_PAID",
                           "The member bore the network fee of this payout; MyHigh5 has no expense to record.")
    try:
        exact = Decimal(str(amount))
    except Exception as exc:  # noqa: BLE001
        raise CashoutError("INVALID_FEE", "The network fee is not a number.") from exc
    if not exact.is_finite() or exact < 0:
        raise CashoutError("INVALID_FEE", "The network fee cannot be negative.")
    if exact > money(cashout.gross_amount):
        raise CashoutError("INVALID_FEE", "The network fee cannot be larger than the payout itself.")
    currency = payment_config.SUPPORTED_PAYOUT_CURRENCIES.get(str(cashout.payout_currency or ""))
    if currency is None or currency.get("currency") != "USDT":
        raise CashoutError("FEE_CURRENCY_UNSUPPORTED",
                           "This payout was not made in a US-dollar stablecoin; its fee needs a manual journal entry.")
    description = network_fee_description(cashout.id)
    already = (db.query(JournalEntry.id).filter(JournalEntry.description == description).first() is not None
               or db.query(AuditTrail.id).filter(AuditTrail.table_name == "affiliate_cashout_requests",
                                                 AuditTrail.record_id == cashout.id,
                                                 AuditTrail.action.in_(_FEE_AUDIT_ACTIONS)).first() is not None)
    if already:
        raise CashoutError("FEE_ALREADY_RECORDED", "The network fee of this payout has already been recorded.")
    fee = money(exact)
    details = {"source": source, "amount": str(fee), "reported_amount": str(exact),
               "estimate": str(money(cashout.network_fee)) if cashout.network_fee is not None else None,
               "reference": (str(reference).strip()[:200] or None) if reference else None,
               "fee_paid_by": reported_by, "payout_currency": cashout.payout_currency,
               "valuation": "1 USDT = 1 USD (ledger convention, no market rate applied)"}
    if fee <= 0:
        db.flush()
        _audit(db, record_id=cashout.id, action="CASHOUT_NETWORK_FEE_NONE", actor_id=actor_id, old=None, new=details)
        return FEE_NONE
    treasury = currency["treasury_account"]
    needed = {payment_config.NETWORK_FEE_EXPENSE_ACCOUNT, treasury}
    accounts = dict(db.query(ChartOfAccounts.account_code, ChartOfAccounts.is_active)
                    .filter(ChartOfAccounts.account_code.in_(needed)).all())
    if needed - set(accounts):
        raise CashoutError("LEDGER_NOT_CONFIGURED",
                           "Network fee accounting is not configured; missing accounts: "
                           + ", ".join(sorted(needed - set(accounts))))
    inactive = sorted(code for code, active in accounts.items() if active is False)
    if inactive:
        raise CashoutError("LEDGER_ACCOUNT_INACTIVE",
                           "Network fee accounting cannot post to an inactive account: " + ", ".join(inactive))
    accounting_service.create_journal_entry(db, description=description, date=now, commit=False, lines=[
        {"account_code": payment_config.NETWORK_FEE_EXPENSE_ACCOUNT, "debit": fee, "credit": 0,
         "description": description},
        {"account_code": treasury, "debit": 0, "credit": fee, "description": description},
    ])
    db.flush()
    _audit(db, record_id=cashout.id, action="CASHOUT_NETWORK_FEE_POSTED", actor_id=actor_id, old=None,
           new={**details, "expense_account": payment_config.NETWORK_FEE_EXPENSE_ACCOUNT,
                "treasury_account": treasury})
    return FEE_POSTED


def record_provider_network_fee(db: Session, cashout: AffiliateCashoutRequest, details: dict,
                                now: datetime) -> str:
    """Post the fee the PROVIDER reported for a payout that has just been
    completed, if and only if it says the fee came from our balance. Runs in
    a savepoint and never raises: a payout is completed whether or not its fee
    can be booked (an unbooked fee stays listed for an administrator)."""
    if not network_fee_applies(cashout):
        return FEE_NOT_APPLICABLE
    reported, payer = details.get("fee"), str(details.get("fee_paid_by") or "").strip().lower()
    if reported in (None, ""):
        return "NOT_REPORTED"
    if not payer or payer not in payment_config.company_fee_payer_values():
        return "PAYER_NOT_CONFIRMED"
    try:
        with db.begin_nested():
            return record_network_fee(db, cashout, amount=reported, source=FEE_SOURCE_PROVIDER, actor_id=None,
                                      now=now, reference=cashout.provider_batch_id, reported_by=payer)
    except CashoutError as exc:
        logger.warning("Cashout %s: the provider's network fee was not posted (%s)", cashout.id, exc.code)
        return exc.code
    except Exception:  # noqa: BLE001
        logger.exception("Cashout %s: the provider's network fee could not be posted", cashout.id)
        return "ERROR"


def record_network_fee_by_admin(db: Session, cashout: AffiliateCashoutRequest, *, admin: User, amount,
                                reference: str, now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """An authorised administrator records the network fee read from the
    provider's statement (zero = the provider charged none). Commits."""
    now = now or datetime.utcnow()
    _require_processor(admin)
    reference = str(reference or "").strip()
    if len(reference) < 3:
        raise CashoutError("REFERENCE_REQUIRED", "Say where the fee was read (the provider's payout id or statement).")
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .populate_existing().with_for_update().one())
    try:
        record_network_fee(db, locked, amount=amount, source=FEE_SOURCE_ADMIN, actor_id=admin.id, now=now,
                           reference=reference)
    except Exception:
        db.rollback()
        raise
    db.commit()
    return locked


def network_fee_summary(db: Session, *, limit: int = 200) -> dict:
    """Totals of the fees booked, and the completed company-paid payouts whose
    fee has not been recorded yet."""
    rows = (db.query(AffiliateCashoutRequest.id, AffiliateCashoutRequest.user_id, AffiliateCashoutRequest.network_fee)
            .filter(AffiliateCashoutRequest.cashout_method == METHOD_CRYPTO,
                    AffiliateCashoutRequest.status == CashoutStatus.COMPLETED.value,
                    AffiliateCashoutRequest.network_fee_policy == payment_config.FEE_COMPANY_PAYS)
            .order_by(AffiliateCashoutRequest.id.desc()).limit(2000).all())
    recorded = {record_id: (action, new_values or {}) for record_id, action, new_values in
                db.query(AuditTrail.record_id, AuditTrail.action, AuditTrail.new_values)
                .filter(AuditTrail.table_name == "affiliate_cashout_requests",
                        AuditTrail.action.in_(_FEE_AUDIT_ACTIONS)).all()}
    posted = [Decimal(str(values.get("amount") or 0)) for action, values in recorded.values()
              if action == "CASHOUT_NETWORK_FEE_POSTED"]
    # The ledger keeps cents; the exact figures stay comparable with the provider's statement here.
    reported = sum((Decimal(str(values.get("reported_amount") or 0)) for _, values in recorded.values()), Decimal("0"))
    missing = [{"cashout_id": cid, "user_id": uid,
                "estimate": float(money(estimate)) if estimate is not None else None}
               for cid, uid, estimate in rows if cid not in recorded]
    return {"expense_account": payment_config.NETWORK_FEE_EXPENSE_ACCOUNT,
            "posted_count": len(posted), "posted_total": float(sum(posted, Decimal("0.00"))),
            "reported_total": format(reported, "f"),
            "rounding_difference": format(reported - sum(posted, Decimal("0.00")), "f"),
            "confirmed_none_count": sum(1 for action, _ in recorded.values() if action == "CASHOUT_NETWORK_FEE_NONE"),
            "not_recorded_count": len(missing), "not_recorded": missing[:limit],
            "automatic_posting": bool(payment_config.company_fee_payer_values())}


# ---------------------------------------------------------------------------
# Network fee of a crypto payout that the BENEFICIARY pays (owner decision:
# policy MEMBER_PAYS, provider fee behaviour DEDUCTED_BY_PROVIDER)
#
# The fee is taken in exactly ONE place. The whole commission amount is handed
# to the provider, the provider takes its fee out of it, and the beneficiary
# receives the rest. This application never subtracts the fee itself, so it
# cannot be taken twice; amount_to_send() is the only function that decides
# what is handed over and it refuses every other provider fee behaviour.
#
# A member is paid only after accepting the network fee terms, which state the
# highest ESTIMATE they accept. The provider's estimate for THEIR payout, raised
# by the configured safety margin, is checked against it before anything is
# reserved. That is a check on an estimate: the actual fee is decided by the
# provider when it sends, is known only afterwards, and CAN be higher. Nothing
# here guarantees the actual fee of a payout, including the first one.
#
# So the exposure is kept small instead, by two different things:
#
#   The recording gate (temporary). A payout's actual fee counts as reconciled
#   only when the fee, who bore it and the amount are VERIFIED (by the
#   provider's own report once its values are confirmed, or by an administrator
#   against named evidence). No further payout is created while more payouts
#   than the configured number (default 0) are still at the provider or
#   completed without that. A missing fee is never taken to be zero. Nothing is
#   wrong yet: the gate lifts by itself as soon as the fee is verified.
#
#   The suspension (persistent). A CONFIRMED inconsistency (the fee charged to
#   MyHigh5, an amount that does not agree, a fee above the member's limit)
#   stops all payouts and stays until an administrator reviews it and
#   reactivates them. Recording a fee afterwards never lifts it.
#
# Nothing more is ever taken from the member.
#
# Books: the cashout's own entry (Dr 2001 / Cr 1001, the whole amount) is the
# only one. No entry is posted for the fee and account 5005 is not used.
# ---------------------------------------------------------------------------

CHARGED_TO_PAYOUT, CHARGED_TO_BALANCE = "PAYOUT_AMOUNT", "PROVIDER_BALANCE"
FLAG_MODE_MISMATCH, FLAG_AMOUNT_MISMATCH, FLAG_CAP_EXCEEDED = (
    "PROVIDER_FEE_MODE_MISMATCH", "PROVIDER_AMOUNT_MISMATCH", "FEE_CAP_EXCEEDED")
# A flag that means the provider did not behave as configured: no further payout until a person has looked.
SUSPENDING_FLAGS = (FLAG_MODE_MISMATCH, FLAG_AMOUNT_MISMATCH, FLAG_CAP_EXCEEDED)
_EXACT = Decimal("0.00000001")

# How far the ACTUAL fee of a completed payout has been verified. Only the two
# VERIFIED values count as a reconciliation; everything else, and nothing at
# all, keeps the payout among the unreconciled ones.
RECONCILED_BY_PROVIDER, RECONCILED_BY_ADMIN = "PROVIDER_VERIFIED", "ADMIN_VERIFIED"
UNVERIFIED_PROVIDER, UNVERIFIED_ADMIN = "PROVIDER_UNVERIFIED", "ADMIN_UNVERIFIED"
VERIFIED_RECONCILIATIONS = (RECONCILED_BY_PROVIDER, RECONCILED_BY_ADMIN)
# Where an administrator read the figures. OTHER is recorded but never verifies.
EVIDENCE_STATEMENT, EVIDENCE_EXPLORER, EVIDENCE_SUPPORT, EVIDENCE_OTHER, EVIDENCE_PROVIDER_API = (
    "PROVIDER_STATEMENT", "BLOCKCHAIN_EXPLORER", "PROVIDER_SUPPORT", "OTHER", "PROVIDER_API")
ADMIN_EVIDENCE = (EVIDENCE_STATEMENT, EVIDENCE_EXPLORER, EVIDENCE_SUPPORT, EVIDENCE_OTHER)
_VERIFYING_EVIDENCE = (EVIDENCE_STATEMENT, EVIDENCE_EXPLORER, EVIDENCE_SUPPORT)


def _exact(value) -> Optional[str]:
    """A provider-precision figure as plain text (never a float)."""
    if value is None:
        return None
    text = format(Decimal(str(value)).quantize(_EXACT), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _provider_number(value, what: str) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except Exception as exc:  # noqa: BLE001
        raise CashoutError("INVALID_FEE", f"The {what} is not a number.") from exc
    if not number.is_finite() or number < 0:
        raise CashoutError("INVALID_FEE", f"The {what} cannot be negative.")
    if number != number.quantize(_EXACT):
        raise CashoutError("INVALID_FEE", f"The {what} has more than 8 decimal places.")
    return number


def amount_to_send(mode: Optional[str], gross: Decimal) -> Decimal:
    """What is handed to the provider for a payout of `gross`. The ONLY place
    that decides it. DEDUCTED_BY_PROVIDER: the whole amount, because the
    provider takes its fee out of it. Every other behaviour is refused, so a
    fee is never subtracted here and then taken again by the provider."""
    if mode != payment_config.FEE_MODE_DEDUCTED:
        raise CashoutError("PROVIDER_FEE_MODE_UNVERIFIED",
                           "The provider's fee behaviour is not confirmed; no payout is created.")
    return money(gross)


def fee_terms(config: PaymentConfig) -> dict:
    """The network fee terms a member is asked to accept."""
    return {"available": config.fee_rules_gate() is None, "version": int(config.fee_terms_version),
            "cap_percent": _exact(config.member_fee_cap_percent), "cap_usd": _exact(config.member_fee_cap_usd),
            "valid_days": int(config.fee_consent_valid_days),
            "minimum_received": float(money(config.min_net_payout_usd)),
            "provider": config.provider_display_name,
            # What the limit is, and what it is not: said by the server so every screen says the same.
            "limit_applies_to": "ESTIMATE", "actual_fee_guaranteed": False}


def active_fee_consent(db: Session, user_id: int, config: PaymentConfig,
                       now: Optional[datetime] = None) -> Optional[CashoutFeeConsent]:
    """The member's acceptance of the CURRENT terms, if it is still in force."""
    now = now or datetime.utcnow()
    row = (db.query(CashoutFeeConsent)
           .filter(CashoutFeeConsent.user_id == user_id, CashoutFeeConsent.revoked_at.is_(None))
           .order_by(CashoutFeeConsent.id.desc()).first())
    if row is None or int(row.terms_version) != int(config.fee_terms_version):
        return None
    if row.expires_at is not None and now >= row.expires_at:
        return None
    return row


def member_fee_cap(config: PaymentConfig, consent: CashoutFeeConsent, gross: Decimal) -> Decimal:
    """The highest network fee this member may bear on a payout of `gross`:
    the LOWEST of every limit that is set, in the terms they accepted and in
    the configuration now in force."""
    limits = [Decimal(gross) * Decimal(str(percent)) / Decimal("100")
              for percent in (config.member_fee_cap_percent, consent.cap_percent) if Decimal(str(percent)) > 0]
    limits += [Decimal(str(amount)) for amount in (config.member_fee_cap_usd, consent.cap_usd)
               if Decimal(str(amount)) > 0]
    if not limits:
        raise CashoutError("FEE_LIMITS_NOT_CONFIGURED", "No member network fee limit is set.")
    return min(limits).quantize(_EXACT)


def adjusted_estimate(estimate: Decimal, margin_percent) -> Decimal:
    """The provider's estimate raised by the safety margin: estimate x (1 +
    margin / 100), rounded UP at the provider's precision so that rounding
    never works against the member. Decimal only. Still an estimate."""
    if margin_percent is None:
        raise CashoutError("FEE_SAFETY_MARGIN_NOT_SET", "The safety margin on the fee estimate is not set.")
    margin = Decimal(str(margin_percent))
    if not margin.is_finite() or margin < 0:
        raise CashoutError("FEE_SAFETY_MARGIN_NOT_SET", "The safety margin on the fee estimate is not usable.")
    raised = Decimal(str(estimate)) * (Decimal("100") + margin) / Decimal("100")
    return raised.quantize(_EXACT, rounding=ROUND_UP)


def beneficiary_fee_plan(config: PaymentConfig, consent: CashoutFeeConsent, gross: Decimal,
                         estimate: Decimal) -> tuple[Optional[str], dict]:
    """Check the provider's estimate for THIS payout, raised by the safety
    margin, against every limit. Returns (why it may not be sent or None, the
    figures to store). Three different figures, never mixed: the provider's
    ESTIMATE, the ADJUSTED estimate that is compared with the limits, and
    (later, from the provider) the ACTUAL fee. The margin changes what is
    checked, never what is sent: the whole amount is handed to the provider."""
    gross, estimate = money(gross), Decimal(str(estimate))
    cap = member_fee_cap(config, consent, gross)
    adjusted = adjusted_estimate(estimate, config.fee_estimate_margin_percent)
    plan = {"provider_fee_mode": config.provider_fee_mode, "network_fee_estimate": estimate.quantize(_EXACT),
            "fee_estimate_adjusted": adjusted,
            "fee_margin_percent": Decimal(str(config.fee_estimate_margin_percent)),
            "fee_cap": cap, "fee_consent_id": int(consent.id)}
    if gross - adjusted <= 0 or adjusted > gross * Decimal(config.max_network_fee_percent) / Decimal("100"):
        return "NETWORK_FEE_TOO_HIGH", plan
    if adjusted > cap:
        return "NETWORK_FEE_ABOVE_MEMBER_LIMIT", plan
    if gross - adjusted < money(config.min_net_payout_usd):
        return "BELOW_MINIMUM_RECEIVED", plan
    plan["amount_sent"] = amount_to_send(config.provider_fee_mode, gross)
    return None, plan


def fee_reconciled(cashout: AffiliateCashoutRequest) -> bool:
    """Has the ACTUAL fee of this payout been verified? A missing fee is never
    taken to be zero, and a figure nobody verified does not count."""
    return (cashout.network_fee_actual is not None and cashout.net_received is not None
            and cashout.fee_reconciliation in VERIFIED_RECONCILIATIONS)


def reconciliation_exposure(db: Session) -> dict:
    """Beneficiary-paid crypto payouts whose actual fee is NOT verified yet:
    those still on their way (reserved, at the provider, or of unknown outcome)
    and those completed without a verified fee. An unknown reconciliation
    state counts as unreconciled."""
    paid_by_member = (AffiliateCashoutRequest.cashout_method == METHOD_CRYPTO,
                      AffiliateCashoutRequest.network_fee_policy == payment_config.FEE_MEMBER_PAYS)
    in_flight = (db.query(AffiliateCashoutRequest.id)
                 .filter(*paid_by_member, AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES)).count())
    # Spelled out with IS NULL on purpose: "NOT (x IN (...))" is neither true nor
    # false for a row whose reconciliation was never recorded, and such a row
    # would silently drop out of the count.
    unverified = or_(AffiliateCashoutRequest.fee_reconciliation.is_(None),
                     AffiliateCashoutRequest.fee_reconciliation.notin_(VERIFIED_RECONCILIATIONS),
                     AffiliateCashoutRequest.network_fee_actual.is_(None),
                     AffiliateCashoutRequest.net_received.is_(None))
    completed = (db.query(AffiliateCashoutRequest.id)
                 .filter(*paid_by_member, AffiliateCashoutRequest.status == CashoutStatus.COMPLETED.value,
                         unverified).count())
    return {"in_flight": int(in_flight), "completed_unreconciled": int(completed),
            "total": int(in_flight) + int(completed)}


def recording_gate(db: Session, config: PaymentConfig) -> Optional[str]:
    """Why no FURTHER payout may be created because of earlier ones (None =
    one may). The caller holds the settings lock (payment_config.lock_settings),
    so two workers cannot both pass it for different members."""
    if reconciliation_exposure(db)["total"] > int(config.max_unreconciled_payouts):
        return "FEE_RECONCILIATION_PENDING"
    return None


def suspend_if_inconsistent(db: Session, cashout: AffiliateCashoutRequest) -> Optional[str]:
    """Called when a beneficiary-paid payout has just been completed. A
    CONFIRMED inconsistency (the fee charged to MyHigh5, an amount that does
    not agree, a fee above the member's limit) suspends all payouts until an
    administrator reactivates them. Returns the suspension reason, if any.

    A fee that is only missing or not verified yet is NOT a suspension: the
    payout stays among the unreconciled ones and the recording gate blocks
    further payouts until it is verified, then lets them go again by itself.
    No commit."""
    if not member_fee_applies(cashout) or cashout.fee_flag not in SUSPENDING_FLAGS:
        return None
    payment_config.suspend_payouts(db, reason=cashout.fee_flag, cashout_id=int(cashout.id))
    return cashout.fee_flag


def accept_fee_terms(db: Session, user: User, *, version: int, cap_percent, cap_usd,
                     ip: Optional[str] = None, now: Optional[datetime] = None) -> CashoutFeeConsent:
    """The member accepts the network fee terms and limits they were SHOWN.
    Commits. Refused when the terms are not on offer, or are no longer the
    ones shown. Moves no money and starts no payout."""
    now = now or datetime.utcnow()
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    config = payment_config.load(db)
    if config.fee_rules_gate() is not None:
        db.rollback()
        raise CashoutError("FEE_TERMS_UNAVAILABLE", "The network fee terms cannot be accepted at the moment.")
    try:
        shown = (int(version), Decimal(str(cap_percent)), Decimal(str(cap_usd)))
    except Exception:  # noqa: BLE001
        shown = None
    current = (int(config.fee_terms_version), Decimal(str(config.member_fee_cap_percent)),
               Decimal(str(config.member_fee_cap_usd)))
    if shown != current:
        db.rollback()
        raise CashoutError("FEE_TERMS_CHANGED", "The network fee terms have changed. Review them and accept again.")
    existing = active_fee_consent(db, locked.id, config, now)
    if existing is not None and (Decimal(str(existing.cap_percent)), Decimal(str(existing.cap_usd))) == current[1:]:
        db.rollback()
        return existing                             # already accepted: nothing new
    (db.query(CashoutFeeConsent)
     .filter(CashoutFeeConsent.user_id == locked.id, CashoutFeeConsent.revoked_at.is_(None))
     .update({CashoutFeeConsent.revoked_at: now, CashoutFeeConsent.revoked_reason: "REPLACED"},
             synchronize_session=False))
    days = int(config.fee_consent_valid_days)
    consent = CashoutFeeConsent(user_id=locked.id, terms_version=current[0], cap_percent=current[1],
                                cap_usd=current[2], accepted_at=now,
                                expires_at=now + timedelta(days=days) if days > 0 else None, ip_address=ip)
    db.add(consent)
    db.flush()
    _audit(db, record_id=locked.id, action="CASHOUT_FEE_TERMS_ACCEPTED", actor_id=locked.id, table="users", ip=ip,
           old=None, new={"consent_id": int(consent.id), "terms_version": current[0],
                          "cap_percent": _exact(current[1]), "cap_usd": _exact(current[2]),
                          "expires_at": consent.expires_at.isoformat() if consent.expires_at else None})
    db.commit()
    db.refresh(consent)
    return consent


def withdraw_fee_consent(db: Session, user: User, *, ip: Optional[str] = None,
                         now: Optional[datetime] = None) -> bool:
    """The member withdraws their acceptance: no further crypto payout is
    created for them until they accept again. A payout already handed to the
    provider is not affected. Commits. True when there was one to withdraw."""
    now = now or datetime.utcnow()
    locked = db.query(User).filter(User.id == user.id).with_for_update().one()
    changed = (db.query(CashoutFeeConsent)
               .filter(CashoutFeeConsent.user_id == locked.id, CashoutFeeConsent.revoked_at.is_(None))
               .update({CashoutFeeConsent.revoked_at: now, CashoutFeeConsent.revoked_reason: "WITHDRAWN"},
                       synchronize_session=False))
    if changed:
        _audit(db, record_id=locked.id, action="CASHOUT_FEE_TERMS_WITHDRAWN", actor_id=locked.id, table="users",
               ip=ip, old=None, new={"consents": int(changed)})
    db.commit()
    return bool(changed)


def member_fee_applies(cashout: AffiliateCashoutRequest) -> bool:
    return (cashout.cashout_method == METHOD_CRYPTO and cashout.status == CashoutStatus.COMPLETED.value
            and cashout.network_fee_policy == payment_config.FEE_MEMBER_PAYS)


def record_member_fee(db: Session, cashout: AffiliateCashoutRequest, *, amount, charged_to: str, source: str,
                      actor_id: Optional[int], now: datetime, evidence: str, verified: bool = False,
                      received=None, reference: Optional[str] = None,
                      reported_by: Optional[str] = None) -> Optional[str]:
    """Record the ACTUAL network fee of one completed beneficiary-paid payout
    and what the beneficiary therefore received. Posts NO journal entry and
    takes nothing more from anyone. Returns the flag raised (None = it adds
    up). No commit; the cashout row is locked by the caller.

    `charged_to` says where the provider took the fee from. PAYOUT_AMOUNT is
    the configured behaviour. PROVIDER_BALANCE means the provider charged
    MyHigh5 instead: the beneficiary received the whole amount, the fee is
    recorded and flagged, and the treasury account is overstated by it until
    accounting decides, with the owner, how to book it.

    `evidence` names where the figures were read. `verified` says that the
    fee, who bore it AND the amount received (`received`, required then) were
    each checked against that evidence; only then does the payout count as
    reconciled. A figure recorded without that stays UNVERIFIED and may be
    replaced once by a verified one; a verified figure is never changed."""
    if not member_fee_applies(cashout):
        raise CashoutError("NOT_COMPLETED",
                           "An actual network fee is recorded only for a completed beneficiary-paid crypto payout.")
    replacing = cashout.network_fee_actual is not None
    if replacing and (fee_reconciled(cashout) or not verified):
        raise CashoutError("FEE_ALREADY_RECORDED", "The network fee of this payout has already been recorded.")
    if charged_to not in (CHARGED_TO_PAYOUT, CHARGED_TO_BALANCE):
        raise CashoutError("CHARGED_TO_REQUIRED",
                           "Say where the provider took the fee from: PAYOUT_AMOUNT or PROVIDER_BALANCE.")
    if evidence not in (*ADMIN_EVIDENCE, EVIDENCE_PROVIDER_API):
        raise CashoutError("EVIDENCE_REQUIRED", "Say where the figures were read: " + ", ".join(ADMIN_EVIDENCE) + ".")
    exact = _provider_number(amount, "network fee")
    gross = money(cashout.gross_amount)
    currency = payment_config.SUPPORTED_PAYOUT_CURRENCIES.get(str(cashout.payout_currency or ""))
    if currency is None or currency.get("currency") != "USDT":
        raise CashoutError("FEE_CURRENCY_UNSUPPORTED",
                           "This payout was not made in a US-dollar stablecoin; its fee cannot be recorded here.")
    if exact >= gross:
        raise CashoutError("INVALID_FEE", "The network fee cannot be as large as the payout itself.")
    flag: Optional[str] = None
    if charged_to == CHARGED_TO_BALANCE:
        net = gross
        flag = FLAG_MODE_MISMATCH if exact > 0 else None
    else:
        net = gross - exact
        if cashout.fee_cap is not None and exact > Decimal(str(cashout.fee_cap)):
            flag = FLAG_CAP_EXCEEDED
    by_provider = source == FEE_SOURCE_PROVIDER
    if verified:
        if not by_provider and evidence not in _VERIFYING_EVIDENCE:
            raise CashoutError("EVIDENCE_REQUIRED",
                               "A verified figure needs the provider's statement, a blockchain explorer or the "
                               "provider's support as its evidence.")
        if received in (None, ""):
            raise CashoutError("RECEIVED_REQUIRED",
                               "A verified figure needs the amount the beneficiary received, read from the evidence.")
        if _provider_number(received, "amount received") != net:
            raise CashoutError("AMOUNTS_DO_NOT_ADD_UP",
                               "The amount received does not equal the payout less the fee. Check the evidence; "
                               "if it really differs, record the figures as not verified and review the payout.")
    old = ({"network_fee": _exact(cashout.network_fee_actual), "net_received": _exact(cashout.net_received),
            "reconciliation": cashout.fee_reconciliation, "evidence": cashout.fee_evidence} if replacing else None)
    cashout.network_fee_actual = exact
    cashout.net_received = net
    cashout.network_fee_source = source
    cashout.fee_evidence = evidence
    cashout.fee_reconciliation = ((RECONCILED_BY_PROVIDER if by_provider else RECONCILED_BY_ADMIN) if verified
                                  else (UNVERIFIED_PROVIDER if by_provider else UNVERIFIED_ADMIN))
    cashout.fee_flag = flag or cashout.fee_flag
    db.flush()
    _audit(db, record_id=cashout.id, action="CASHOUT_MEMBER_FEE_RECORDED", actor_id=actor_id, old=old,
           new={"source": source, "charged_to": charged_to, "gross": str(gross), "network_fee": _exact(exact),
                "net_received": _exact(net), "estimate": _exact(cashout.network_fee_estimate),
                "estimate_adjusted": _exact(cashout.fee_estimate_adjusted),
                "fee_cap": _exact(cashout.fee_cap), "amount_sent": _exact(cashout.amount_sent),
                "reconciliation": cashout.fee_reconciliation, "evidence": evidence, "verified": bool(verified),
                "flag": cashout.fee_flag, "fee_paid_by": reported_by,
                "reference": (str(reference).strip()[:200] or None) if reference else None,
                "payout_currency": cashout.payout_currency,
                "valuation": "1 USDT = 1 USD (ledger convention, no market rate applied)"})
    return cashout.fee_flag


def _flag(db: Session, cashout: AffiliateCashoutRequest, flag: str, **details) -> None:
    cashout.fee_flag = flag
    db.flush()
    _audit(db, record_id=cashout.id, action="CASHOUT_FEE_FLAGGED", actor_id=None, old=None,
           new={"flag": flag, **details})


def record_provider_member_fee(db: Session, cashout: AffiliateCashoutRequest, details: dict,
                               now: datetime) -> str:
    """Apply what the PROVIDER reports about a beneficiary-paid payout that
    has just been completed. Runs in a savepoint and never raises: a payout is
    completed whether or not its fee can be recorded.

    The provider documents neither the values of `fee_paid_by`, nor the unit
    of `fee`, nor whether `amount` is what it was asked to send or what the
    beneficiary received. So nothing is recorded unless the payer value was
    confirmed with it (NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES / ..._COMPANY_
    VALUES), and what is recorded counts as VERIFIED only when the meaning of
    `amount` was confirmed too (NOWPAYMENTS_PAYOUT_AMOUNT_MEANS) and the
    reported amount agrees with it. Everything short of that leaves the payout
    unreconciled for an administrator."""
    if not member_fee_applies(cashout):
        return FEE_NOT_APPLICABLE
    reported, payer = details.get("fee"), str(details.get("fee_paid_by") or "").strip().lower()
    try:
        with db.begin_nested():
            sent = Decimal(str(cashout.amount_sent)) if cashout.amount_sent is not None else None
            try:
                paid = Decimal(str(details.get("amount"))) if details.get("amount") not in (None, "") else None
                paid = paid if paid is not None and paid.is_finite() else None
            except Exception:  # noqa: BLE001
                paid = None
            if sent is not None and paid is not None and paid > sent:
                # More left than was asked for: whatever the cause, it is not the configured behaviour.
                _flag(db, cashout, FLAG_AMOUNT_MISMATCH, amount_sent=_exact(sent), provider_amount=_exact(paid))
            if payer and payer in payment_config.company_fee_payer_values():
                if reported in (None, ""):
                    _flag(db, cashout, FLAG_MODE_MISMATCH, fee_paid_by=payer)
                    return FLAG_MODE_MISMATCH
                record_member_fee(db, cashout, amount=reported, charged_to=CHARGED_TO_BALANCE,
                                  source=FEE_SOURCE_PROVIDER, actor_id=None, now=now,
                                  evidence=EVIDENCE_PROVIDER_API, reference=cashout.provider_batch_id,
                                  reported_by=payer)
                return cashout.fee_flag or FEE_POSTED
            if reported in (None, ""):
                return "NOT_REPORTED"
            if not payer or payer not in payment_config.receiver_fee_payer_values():
                return "PAYER_NOT_CONFIRMED"
            fee = _provider_number(reported, "network fee")
            # Is the amount the provider reports the one its confirmed meaning predicts?
            meaning = payment_config.payout_amount_semantics()
            expected = None if sent is None or not meaning else (sent if meaning == "REQUESTED" else sent - fee)
            agrees = expected is not None and paid is not None and paid == expected
            if expected is not None and paid is not None and not agrees and cashout.fee_flag is None:
                _flag(db, cashout, FLAG_AMOUNT_MISMATCH, amount_sent=_exact(sent), provider_amount=_exact(paid),
                      expected_amount=_exact(expected), amount_means=meaning)
            verified = bool(agrees and cashout.fee_flag is None and sent is not None and sent > fee)
            record_member_fee(db, cashout, amount=reported, charged_to=CHARGED_TO_PAYOUT,
                              source=FEE_SOURCE_PROVIDER, actor_id=None, now=now, evidence=EVIDENCE_PROVIDER_API,
                              verified=verified, received=(money(cashout.gross_amount) - fee) if verified else None,
                              reference=cashout.provider_batch_id, reported_by=payer)
            return cashout.fee_flag or ("RECORDED" if verified else "RECORDED_UNVERIFIED")
    except CashoutError as exc:
        logger.warning("Cashout %s: the provider's network fee was not recorded (%s)", cashout.id, exc.code)
        return exc.code
    except Exception:  # noqa: BLE001
        logger.exception("Cashout %s: the provider's network fee could not be recorded", cashout.id)
        return "ERROR"


def record_member_fee_by_admin(db: Session, cashout: AffiliateCashoutRequest, *, admin: User, amount,
                               charged_to: Optional[str], reference: str, evidence: Optional[str] = None,
                               verified: bool = False, received=None,
                               now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """An authorised administrator records the actual network fee of a
    beneficiary-paid payout, where the provider took it from, and WHERE the
    figures were read. Commits. Marked verified (with the amount received)
    the payout counts as reconciled; otherwise the figures are kept as
    unverified and it does not. A fee that does not add up suspends payouts.
    Recording a fee never lifts a suspension."""
    now = now or datetime.utcnow()
    _require_processor(admin)
    reference = str(reference or "").strip()
    if len(reference) < 3:
        raise CashoutError("REFERENCE_REQUIRED", "Say where the fee was read (the provider's payout id or statement).")
    evidence = str(evidence or "").strip().upper()
    if evidence not in ADMIN_EVIDENCE:
        raise CashoutError("EVIDENCE_REQUIRED", "Say where the figures were read: " + ", ".join(ADMIN_EVIDENCE) + ".")
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .populate_existing().with_for_update().one())
    try:
        flag = record_member_fee(db, locked, amount=amount, charged_to=str(charged_to or "").strip().upper(),
                                 source=FEE_SOURCE_ADMIN, actor_id=admin.id, now=now, evidence=evidence,
                                 verified=bool(verified), received=received, reference=reference)
        if flag in SUSPENDING_FLAGS:
            payment_config.suspend_payouts(db, reason=flag, cashout_id=int(locked.id), now=now)
    except Exception:
        db.rollback()
        raise
    db.commit()
    return locked


def reactivate_payouts(db: Session, admin: User, *, password: Optional[str], confirmation: Optional[str],
                       note: Optional[str], ip: Optional[str] = None) -> PaymentConfig:
    """Lift a payout suspension after an administrator's review. Commits.
    Refused while a completed payout's actual fee is still missing or
    unverified beyond what the configuration allows: the payout that caused
    the suspension has to be reconciled first (the recording gate would hold
    payouts back anyway). Everything else is checked by payment_config."""
    # Who is asking comes first: nothing about the payouts is told to anyone else.
    if not payment_config.has_permission(admin, payment_config.PERMISSION_MANAGE):
        raise payment_config.PaymentConfigError(
            "FORBIDDEN", f"The {payment_config.PERMISSION_MANAGE} permission is required.")
    payment_config.require_activation(admin, "lift a payout suspension")
    payment_config.require_reauth(admin, password)
    config = payment_config.load(db)
    if config.suspended_reason:
        pending = reconciliation_exposure(db)["completed_unreconciled"]
        if pending > int(config.max_unreconciled_payouts):
            db.rollback()
            raise payment_config.PaymentConfigError(
                "UNSAFE_ACTIVATION",
                f"Resolve this first: {pending} completed payout(s) have no verified actual network fee.")
        unreviewed = unreviewed_flagged_count(db)
        if unreviewed:
            db.rollback()
            raise payment_config.PaymentConfigError(
                "UNSAFE_ACTIVATION",
                f"Resolve this first: {unreviewed} flagged payout(s) have not been reviewed (Flagged Payout Review).")
    return payment_config.reactivate_payouts(db, admin, password=password, confirmation=confirmation, note=note,
                                             ip=ip)


# ---------------------------------------------------------------------------
# Review of a flagged payout (a reconciliation exception)
#
# A completed beneficiary-paid payout that did not add up carries a flag. An
# administrator who may process cashouts looks at it and records that they
# did: who, when, and a written note of what they found. That is ALL a review
# is. It does not clear the flag, does not verify the payout's actual fee (the
# recording gate still counts it until the fee is verified), does not lift a
# payout suspension (only an explicit reactivation does, and that is refused
# while a flagged payout is unreviewed) and does not allow a new payout. The
# cashout's amounts, its journal entry and its earlier audit records are not
# touched.
#
# One review per flag. Sending the same review again changes nothing; a
# different one is refused. If the payout is later flagged for something else,
# the earlier review no longer covers it and it is pending again.
# ---------------------------------------------------------------------------

REVIEW_NOT_REQUIRED, REVIEW_PENDING, REVIEW_DONE = "NOT_REQUIRED", "PENDING", "REVIEWED"
REVIEW_NOTE_MIN, REVIEW_NOTE_MAX = 20, 500
FLAG_MESSAGES = {
    FLAG_MODE_MISMATCH: "The provider charged its network fee to the MyHigh5 balance instead of taking it out of "
                        "the payout.",
    FLAG_AMOUNT_MISMATCH: "The amount the provider reports for this payout does not agree with what it was asked "
                          "to send.",
    FLAG_CAP_EXCEEDED: "The network fee the provider took is higher than the limit the member accepted.",
}
# What happened to the fee of one payout, oldest first (shown with a flagged payout).
_FEE_EVENT_ACTIONS = ("CASHOUT_RESERVED", "CASHOUT_COMPLETED", "CASHOUT_PROVIDER_EVIDENCE", "CASHOUT_FEE_FLAGGED",
                      "CASHOUT_MEMBER_FEE_RECORDED", "CASHOUT_FEE_EXCEPTION_REVIEWED")


def fee_review_state(cashout: AffiliateCashoutRequest) -> str:
    """NOT_REQUIRED (no flag), REVIEWED (the CURRENT flag was reviewed) or PENDING."""
    if not cashout.fee_flag:
        return REVIEW_NOT_REQUIRED
    if cashout.fee_reviewed_at is not None and cashout.fee_review_flag == cashout.fee_flag:
        return REVIEW_DONE
    return REVIEW_PENDING


def fee_review_view(cashout: AffiliateCashoutRequest) -> dict:
    state = fee_review_state(cashout)
    recorded = cashout.fee_reviewed_at is not None
    return {"state": state, "flag": cashout.fee_flag,
            "message": FLAG_MESSAGES.get(cashout.fee_flag or "", cashout.fee_flag),
            "reviewed_flag": cashout.fee_review_flag if recorded else None,
            "reviewed_by": cashout.fee_reviewed_by if recorded else None,
            "reviewed_at": cashout.fee_reviewed_at.isoformat() if recorded else None,
            "note": cashout.fee_review_note if recorded else None,
            # An earlier review exists but the payout has been flagged for something else since.
            "superseded": bool(recorded and state == REVIEW_PENDING)}


def _flagged(db: Session):
    return db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.cashout_method == METHOD_CRYPTO,
                                                    AffiliateCashoutRequest.fee_flag.isnot(None))


# Spelled out with IS NULL: "a <> b" is neither true nor false when a is NULL.
_REVIEW_PENDING = or_(AffiliateCashoutRequest.fee_reviewed_at.is_(None),
                      AffiliateCashoutRequest.fee_review_flag.is_(None),
                      AffiliateCashoutRequest.fee_review_flag != AffiliateCashoutRequest.fee_flag)


def unreviewed_flagged_count(db: Session) -> int:
    return int(_flagged(db).filter(_REVIEW_PENDING).count())


def _review_note(note: Optional[str]) -> str:
    text = " ".join(str(note or "").split())
    if len(text) < REVIEW_NOTE_MIN:
        raise CashoutError("REVIEW_NOTE_REQUIRED",
                           "Describe what you checked and what you found "
                           f"(at least {REVIEW_NOTE_MIN} characters).")
    if len(text) > REVIEW_NOTE_MAX or any(ord(ch) < 32 for ch in text):
        raise CashoutError("REVIEW_NOTE_REQUIRED", f"The review note may have at most {REVIEW_NOTE_MAX} characters.")
    if len(set(text.lower().replace(" ", ""))) < 5:
        raise CashoutError("REVIEW_NOTE_REQUIRED", "The review note does not say what was found.")
    return text


def review_fee_exception(db: Session, cashout: AffiliateCashoutRequest, *, admin: User, password: Optional[str],
                         note: Optional[str], ip: Optional[str] = None,
                         now: Optional[datetime] = None) -> AffiliateCashoutRequest:
    """An authorised administrator records that they reviewed a flagged
    payout. Commits. Needs the process_cashouts permission, the
    administrator's current password and a written note.

    It records the review and nothing else: the flag, the reconciliation of
    the actual fee, a payout suspension, the recording gate, the cashout's
    amounts and its journal entry are all left exactly as they are, and no
    payout is created or allowed by it."""
    now = now or datetime.utcnow()
    _require_processor(admin)
    try:
        payment_config.require_reauth(admin, password)
    except payment_config.PaymentConfigError as exc:
        raise CashoutError("REAUTH_REQUIRED", "Enter your current password to confirm this review.") from exc
    text = _review_note(note)
    # populate_existing: the caller's copy of the row may be older than the lock.
    locked = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout.id)
              .populate_existing().with_for_update().one())
    state = fee_review_state(locked)
    if state == REVIEW_NOT_REQUIRED:
        db.rollback()
        raise CashoutError("NOT_FLAGGED", "This payout is not flagged; there is nothing to review.")
    if state == REVIEW_DONE:
        same = int(locked.fee_reviewed_by or 0) == int(admin.id) and locked.fee_review_note == text
        db.rollback()
        if same:
            return locked                           # the same review sent again: nothing new is recorded
        raise CashoutError("ALREADY_REVIEWED",
                           f"This payout was already reviewed by administrator #{locked.fee_reviewed_by}. "
                           "A review is recorded once and is not replaced.")
    previous = ({"reviewed_flag": locked.fee_review_flag, "reviewed_by": locked.fee_reviewed_by,
                 "reviewed_at": locked.fee_reviewed_at.isoformat(), "note": locked.fee_review_note}
                if locked.fee_reviewed_at is not None else None)
    locked.fee_review_flag = locked.fee_flag
    locked.fee_review_note = text
    locked.fee_reviewed_by = admin.id
    locked.fee_reviewed_at = now
    db.flush()
    _audit(db, record_id=locked.id, action="CASHOUT_FEE_EXCEPTION_REVIEWED", actor_id=admin.id, old=previous, ip=ip,
           new={"flag": locked.fee_flag, "note": text, "reviewed_at": now.isoformat(),
                # The state of the payout WHEN it was reviewed; the review changed none of it.
                "reconciliation": locked.fee_reconciliation, "fee_reconciled": fee_reconciled(locked),
                "network_fee": _exact(locked.network_fee_actual), "net_received": _exact(locked.net_received),
                "fee_cap": _exact(locked.fee_cap), "amount_sent": _exact(locked.amount_sent),
                "payouts_suspended": bool(payment_config.load(db).suspended_reason),
                "effect": "RECORD_ONLY"})
    db.commit()
    return locked


def fee_exception_view(cashout: AffiliateCashoutRequest, *, flagged: Optional[dict] = None,
                       username: Optional[str] = None, suspended_by: Optional[int] = None) -> dict:
    """One flagged payout: what was expected, what happened, what the evidence
    is and whether it was reviewed. Exact figures, as text."""
    fee = member_fee_view(cashout)
    sent = Decimal(str(cashout.amount_sent)) if cashout.amount_sent is not None else None
    estimate = Decimal(str(cashout.network_fee_estimate)) if cashout.network_fee_estimate is not None else None
    actual = Decimal(str(cashout.network_fee_actual)) if cashout.network_fee_actual is not None else None
    cap = Decimal(str(cashout.fee_cap)) if cashout.fee_cap is not None else None
    received = Decimal(str(cashout.net_received)) if cashout.net_received is not None else None
    expected = sent - estimate if sent is not None and estimate is not None else None
    return {
        "cashout_id": cashout.id, "user_id": cashout.user_id, "username": username, "status": cashout.status,
        "processed_at": cashout.processed_at.isoformat() if cashout.processed_at else None,
        "payout_currency": cashout.payout_currency, "destination": mask_address(cashout.wallet_snapshot),
        "provider_batch_id": cashout.provider_batch_id, "provider_status": cashout.provider_status,
        "flag": cashout.fee_flag, "flag_message": FLAG_MESSAGES.get(cashout.fee_flag or "", cashout.fee_flag),
        # What the provider reported when the flag was raised (amounts as it sent them).
        "flag_details": {k: v for k, v in (flagged or {}).items() if k != "flag"},
        "caused_suspension": suspended_by is not None and int(suspended_by) == int(cashout.id),
        "expected": {"amount_sent": fee["amount_sent"], "network_fee_estimate": fee["estimate"],
                     "network_fee_estimate_adjusted": fee["estimate_adjusted"], "fee_cap": fee["fee_cap"],
                     "received": _exact(expected)},
        "actual": {"network_fee": fee["actual"], "received": fee["net_received"],
                   "fee_above_estimate": _exact(actual - estimate) if actual is not None and estimate is not None
                   and actual > estimate else None,
                   "fee_above_cap": _exact(actual - cap) if actual is not None and cap is not None and actual > cap
                   else None,
                   "received_difference": _exact(received - expected) if received is not None and expected is not None
                   and received != expected else None},
        "evidence": {"source": fee["source"], "evidence": fee["evidence"], "reconciliation": fee["reconciliation"],
                     "reconciled": fee["reconciled"], "recorded": fee["status"] == "RECORDED"},
        "provider_fee_mode": fee["provider_fee_mode"], "gross": fee["gross"],
        "review": fee_review_view(cashout),
    }


def fee_exceptions(db: Session, *, state: Optional[str] = None, skip: int = 0, limit: int = 50) -> dict:
    """Flagged payouts, newest first, with the counts by review state. Read-only."""
    query = _flagged(db)
    pending = unreviewed_flagged_count(db)
    total = int(query.count())
    wanted = str(state or "").strip().upper()
    if wanted == REVIEW_PENDING:
        query = query.filter(_REVIEW_PENDING)
    elif wanted == REVIEW_DONE:
        query = query.filter(AffiliateCashoutRequest.fee_reviewed_at.isnot(None),
                             AffiliateCashoutRequest.fee_review_flag == AffiliateCashoutRequest.fee_flag)
    matching = int(query.count())
    rows = query.order_by(AffiliateCashoutRequest.id.desc()).offset(skip).limit(limit).all()
    ids = [int(r.id) for r in rows]
    names = dict(db.query(User.id, User.username).filter(User.id.in_({r.user_id for r in rows})).all()) if rows else {}
    flagged: dict = {}
    if ids:
        for record_id, values in (db.query(AuditTrail.record_id, AuditTrail.new_values)
                                  .filter(AuditTrail.table_name == "affiliate_cashout_requests",
                                          AuditTrail.record_id.in_(ids), AuditTrail.action == "CASHOUT_FEE_FLAGGED")
                                  .order_by(AuditTrail.id.asc()).all()):
            flagged[int(record_id)] = values or {}      # the latest one wins
    suspended_by = payment_config.load(db).suspended_cashout_id
    return {"total": matching, "flagged_count": total, "pending_count": pending,
            "reviewed_count": total - pending,
            "payout_suspension": payment_config.suspension_view(db),
            "items": [fee_exception_view(r, flagged=flagged.get(int(r.id)), username=names.get(r.user_id),
                                         suspended_by=suspended_by) for r in rows]}


def fee_exception_events(db: Session, cashout_id: int) -> List[dict]:
    """The audit records about one payout's fee, oldest first. Read-only."""
    rows = (db.query(AuditTrail)
            .filter(AuditTrail.table_name == "affiliate_cashout_requests", AuditTrail.record_id == cashout_id,
                    AuditTrail.action.in_(_FEE_EVENT_ACTIONS)).order_by(AuditTrail.id.asc()).all())
    return [{"id": r.id, "action": r.action, "actor_id": r.user_id,
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "old_values": r.old_values or {}, "new_values": r.new_values or {}} for r in rows]


def member_fee_view(cashout: AffiliateCashoutRequest) -> dict:
    """Gross, estimate, actual fee and amount received of one payout, exact."""
    paid_by_member = cashout.network_fee_policy == payment_config.FEE_MEMBER_PAYS
    recorded = cashout.network_fee_actual is not None
    return {"applies": bool(paid_by_member and cashout.cashout_method == METHOD_CRYPTO),
            "provider_fee_mode": cashout.provider_fee_mode,
            "gross": str(money(cashout.gross_amount)), "amount_sent": _exact(cashout.amount_sent),
            "estimate": _exact(cashout.network_fee_estimate),
            "estimate_adjusted": _exact(cashout.fee_estimate_adjusted),
            "margin_percent": _exact(cashout.fee_margin_percent),
            "actual": _exact(cashout.network_fee_actual),
            "net_received": _exact(cashout.net_received), "fee_cap": _exact(cashout.fee_cap),
            "source": cashout.network_fee_source, "flag": cashout.fee_flag,
            "reconciliation": cashout.fee_reconciliation, "evidence": cashout.fee_evidence,
            "reconciled": fee_reconciled(cashout),
            "status": (FEE_NOT_APPLICABLE if not member_fee_applies(cashout)
                       else "RECORDED" if recorded else FEE_NOT_RECORDED)}


def member_fee_summary(db: Session, *, limit: int = 200) -> dict:
    """Beneficiary-paid payouts: what was paid out, what the provider kept,
    what the beneficiaries received, and what is still to record or to look at."""
    rows = (db.query(AffiliateCashoutRequest)
            .filter(AffiliateCashoutRequest.cashout_method == METHOD_CRYPTO,
                    AffiliateCashoutRequest.status == CashoutStatus.COMPLETED.value,
                    AffiliateCashoutRequest.network_fee_policy == payment_config.FEE_MEMBER_PAYS)
            .order_by(AffiliateCashoutRequest.id.desc()).limit(2000).all())
    recorded = [r for r in rows if r.network_fee_actual is not None]
    zero = Decimal("0")
    return {"exposure": reconciliation_exposure(db),
            "verified_count": sum(1 for r in rows if fee_reconciled(r)),
            "not_verified": [{"cashout_id": r.id, "user_id": r.user_id, "reconciliation": r.fee_reconciliation,
                              "actual": _exact(r.network_fee_actual)}
                             for r in recorded if not fee_reconciled(r)][:limit],
            "amount_meaning_confirmed": bool(payment_config.payout_amount_semantics()),
            "completed_count": len(rows),
            "gross_total": format(sum((money(r.gross_amount) for r in rows), zero), "f"),
            "recorded_count": len(recorded),
            "fee_total": _exact(sum((Decimal(str(r.network_fee_actual)) for r in recorded), zero)),
            "received_total": _exact(sum((Decimal(str(r.net_received)) for r in recorded), zero)),
            "not_recorded_count": len(rows) - len(recorded),
            "not_recorded": [{"cashout_id": r.id, "user_id": r.user_id, "estimate": _exact(r.network_fee_estimate)}
                             for r in rows if r.network_fee_actual is None][:limit],
            "flagged": [{"cashout_id": r.id, "user_id": r.user_id, "flag": r.fee_flag,
                         "actual": _exact(r.network_fee_actual), "fee_cap": _exact(r.fee_cap),
                         "review": fee_review_state(r)}
                        for r in rows if r.fee_flag][:limit],
            "flagged_unreviewed_count": unreviewed_flagged_count(db),
            "automatic_recording": bool(payment_config.receiver_fee_payer_values())}


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
              .populate_existing().with_for_update().one())
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
              .populate_existing().with_for_update().one())
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
              .populate_existing().with_for_update().one())
    if locked.cashout_method != METHOD_CRYPTO or locked.status != CashoutStatus.UNKNOWN.value:
        db.rollback()
        raise CashoutError("NOT_UNCERTAIN", "Only a crypto cashout with an unknown outcome can be resolved here.")
    outcome = str(outcome or "").strip().upper()
    if outcome == "SENT":
        complete(db, locked, settlement_reference=(reference or locked.provider_batch_id or ""),
                 cash_account=payment_config.load(db).treasury_account, actor_id=admin.id, now=now)
        # Settled by hand: nothing is known about its actual fee yet, so it counts
        # as unreconciled and the recording gate holds further payouts back.
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
        "beneficiary_fee": member_fee_view(cashout),
        "commission_id": cashout.commission_id,
        "tx_hash": cashout.tx_hash,
        "explorer_url": explorer_url(cashout),
    }
    if admin:
        out.update({"user_id": cashout.user_id, "provider_status": cashout.provider_status,
                    "failure_code": cashout.failure_code, "provider_batch_id": cashout.provider_batch_id,
                    "last_checked_at": cashout.last_checked_at.isoformat() if cashout.last_checked_at else None,
                    "reviewed_by": cashout.reviewed_by,
                    "reviewed_at": cashout.reviewed_at.isoformat() if cashout.reviewed_at else None,
                    "has_destination_details": bool(cashout.destination_ciphertext),
                    "fee_review": fee_review_view(cashout),
                    "wallet_approval_id": cashout.wallet_approval_id})
    return out


def _wallet_approval_view(db: Session, user: User) -> Optional[dict]:
    """The member's own view of their wallet's approval: status, when, and the
    reason of a rejection. The administrator is never named."""
    from app.services import payout_wallet_approval as approvals

    row = approvals.current(db, user.id)
    if row is None:
        return None
    return {"status": row.status, "wallet": mask_address(row.address), "network": network_label(row.currency),
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "reason": row.decision_note if row.status == approvals.REJECTED else None}


def explorer_url(cashout: AffiliateCashoutRequest) -> Optional[str]:
    asset = payment_config.SUPPORTED_PAYOUT_CURRENCIES.get(str(cashout.payout_currency or ""), {})
    if not cashout.tx_hash or not asset.get("explorer_tx"):
        return None
    return asset["explorer_tx"] + cashout.tx_hash


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
    # Never a held historical row (they are neither available nor payable).
    payable = money(balance.available + (balance.pending_payable if ready else Decimal("0.00")))
    unpaid = money(balance.available + balance.pending_payable)
    crypto_min, usd_min = crypto_minimum(config=config), usd_minimum(config=config)
    minimum = crypto_min if method == METHOD_CRYPTO else usd_min if method == METHOD_USD else None
    open_cashout = active_cashout(db, user.id)
    eligibility = fe.evaluate(db, user, fe.FinancialOperation.WITHDRAWAL)

    from app.services.cashout_engine import engine_enabled

    engine_on = engine_enabled(db, config=config) and config.fee_gate() is None
    terms = fee_terms(config)
    consent = active_fee_consent(db, user.id, config, now)
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
    elif method == METHOD_CRYPTO and wallet.status == WALLET_PENDING_APPROVAL:
        status = "WALLET_APPROVAL_PENDING"
    elif method == METHOD_CRYPTO and wallet.status == WALLET_REJECTED:
        status = "WALLET_REJECTED"
    elif method == METHOD_CRYPTO and wallet.status == WALLET_ON_HOLD:
        status = "WALLET_ON_HOLD"
    elif method == METHOD_CRYPTO and terms["available"] and consent is None:
        status = "FEE_TERMS_REQUIRED"
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
            # PENDING that may be paid; held historical rows are only in "held".
            "pending": float(balance.pending_payable),
            "available": float(balance.available),
            "reserved": float(balance.reserved),
            "paid": float(balance.paid_lifetime),
            "held": float(balance.held),
            "available_unpaid": float(unpaid),
            "awaiting_wallet_approval": float(unpaid) if wallet.status == WALLET_PENDING_APPROVAL else 0.0,
            "processing": float(balance.reserved),
        },
        "wallet_approval": _wallet_approval_view(db, user),
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
                       "note": (f"No MyHigh5 fee. You pay the blockchain network fee: {config.provider_display_name} "
                                "deducts it from the amount sent and you receive the rest. The fee shown before "
                                "a payout is an estimate; the actual fee may differ."
                                if member_pays else
                                "No MyHigh5 fee. The blockchain network fee is paid by MyHigh5."),
                       "terms": {**terms, "accepted": consent is not None,
                                 "accepted_at": consent.accepted_at.isoformat() if consent is not None else None,
                                 "expires_at": (consent.expires_at.isoformat()
                                                if consent is not None and consent.expires_at else None)}},
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
