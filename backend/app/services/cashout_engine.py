"""Automatic crypto payout engine for members who chose Crypto Cashout.

OFF BY DEFAULT. engine_enabled() is true only when CRYPTO_AUTO_PAYOUT_ENABLED
is explicitly "true" AND the provider's payout credentials are all present.
While it is false, run_cycle() returns immediately: it reads no member, writes
no row, reserves nothing and never calls the provider.

One cycle
---------
1. Reconcile: for every crypto cashout already handed to the provider, ask
   the provider for its status. FINISHED -> the commissions become PAID and the
   journal is posted. FAILED / REJECTED -> the reservation is released. Anything
   else is left as it is.
2. Read the provider's facts once: its custody balance, its minimum payout and
   its network fee. If they cannot be read, the cycle stops (nothing reserved).
3. For each member who chose CRYPTO, under a lock on the member row:
     payable wallet (verified, hold elapsed), financial eligibility, no open
     cashout, no recent failed payout, whole available rows >= $1 and >= the
     provider's minimum, provider balance >= amount + network fee
   -> reserve the rows and COMMIT the intent
   -> re-check the same conditions, mark it processing, COMMIT
   -> ask the provider to create the payout (once).

Provider answers
----------------
  refused with a 4xx          nothing exists at the provider: released, FAILED
  created and confirmed       stays reserved and PROCESSING until step 1 of a
                              later cycle sees FINISHED
  created, confirmation failed / timeout / 5xx / no answer
                              UNKNOWN: stays reserved, is never sent again by
                              the engine; resolved by the provider's status
                              (when a payout id is known) or by an administrator

The member receives the full commission amount. MyHigh5 charges no fee on a
crypto cashout and the network fee is paid from the provider balance.

A row here says what is OWED. reconciliation_report() compares that with the
balance the provider reports; it does not assume the money is there.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.affiliate import (
    ACTIVE_CASHOUT_STATUSES,
    AffiliateCashoutRequest,
    AffiliateCommission,
    CashoutStatus,
    CommissionStatus,
)
from app.models.user import User
from app.services import cashout_service as cs
from app.services import financial_eligibility as fe
from app.services import nowpayments_service as nowpayments
from app.services.commission_payout_service import _intent_reference
from app.services.financial_integrity import money

logger = logging.getLogger(__name__)

# A payout is not attempted when the network fee would exceed this share of it.
MAX_NETWORK_FEE_SHARE = Decimal("0.25")
PROVIDER_PAID = {"FINISHED"}
PROVIDER_NOT_PAID = {"FAILED", "REJECTED"}


class NowPaymentsPayoutProvider:
    """The real provider. Every method is one HTTP call."""

    def balance(self, currency: str) -> Decimal:
        return nowpayments.custody_balance_sync(currency)

    def minimum(self, currency: str) -> Decimal:
        return nowpayments.payout_min_amount_sync(currency)

    def network_fee(self, currency: str, amount: Decimal) -> Decimal:
        return nowpayments.payout_fee_estimate_sync(currency, amount)

    def create_payout(self, *, address: str, amount: Decimal, currency: str, external_id: str) -> dict:
        return nowpayments.create_single_payout_sync(wallet_address=address, amount=amount, currency=currency,
                                                     external_id=external_id)

    def payout_status(self, batch_id: str) -> str:
        return nowpayments.payout_status_sync(batch_id)


def engine_enabled() -> bool:
    return bool(settings.CRYPTO_AUTO_PAYOUT_ENABLED) and nowpayments.payouts_configured()


def engine_status() -> dict:
    config = nowpayments.payout_config_status()
    return {"enabled": engine_enabled(), "flag": bool(settings.CRYPTO_AUTO_PAYOUT_ENABLED),
            "provider_credentials_ready": bool(config["payouts_ready"]), "missing": config["missing"]}


# ---------------------------------------------------------------------------
# Reconciliation of payouts already at the provider
# ---------------------------------------------------------------------------

def reconcile_cashout(db: Session, cashout_id: int, provider, *, now: Optional[datetime] = None) -> str:
    """Apply the provider's status to one crypto cashout. Commits."""
    now = now or datetime.utcnow()
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    if (cashout.cashout_method != cs.METHOD_CRYPTO or not cashout.provider_batch_id
            or cashout.status not in (CashoutStatus.PROCESSING.value, CashoutStatus.UNKNOWN.value)):
        db.rollback()
        return "SKIPPED"
    batch_id = str(cashout.provider_batch_id)
    db.rollback()                                   # no lock is held while waiting for the provider
    try:
        status = str(provider.payout_status(batch_id) or "").upper()
    except Exception:  # noqa: BLE001 - not knowing is not a result
        logger.warning("Cashout %s: provider status could not be read", cashout_id)
        return "STATUS_UNAVAILABLE"
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    if cashout.status not in (CashoutStatus.PROCESSING.value, CashoutStatus.UNKNOWN.value):
        db.rollback()
        return "SKIPPED"
    cashout.provider_status = status[:30] or None
    cashout.last_checked_at = now
    if status in PROVIDER_PAID:
        try:
            cs.complete(db, cashout, settlement_reference=batch_id, cash_account=cs.CRYPTO_TREASURY_ACCOUNT,
                        actor_id=None, now=now)
        except cs.CashoutError as exc:
            db.rollback()
            logger.error("Cashout %s was paid by the provider but cannot be posted: %s", cashout_id, exc.code)
            return "PAID_BUT_NOT_POSTED"
        db.commit()
        return "COMPLETED"
    if status in PROVIDER_NOT_PAID:
        cs.release_reservation(db, cashout, status=CashoutStatus.FAILED.value,
                               failure_code=f"PROVIDER_{status}", actor_id=None, now=now)
        db.commit()
        return "FAILED"
    db.commit()
    return "PENDING"


def reconcile_open(db: Session, provider, *, now: Optional[datetime] = None) -> Counter:
    ids = [row.id for row in db.query(AffiliateCashoutRequest.id)
           .filter(AffiliateCashoutRequest.cashout_method == cs.METHOD_CRYPTO,
                   AffiliateCashoutRequest.provider_batch_id.isnot(None),
                   AffiliateCashoutRequest.status.in_([CashoutStatus.PROCESSING.value, CashoutStatus.UNKNOWN.value]))
           .order_by(AffiliateCashoutRequest.id).all()]
    db.rollback()
    results: Counter = Counter()
    for cashout_id in ids:
        results[reconcile_cashout(db, cashout_id, provider, now=now)] += 1
    return results


# ---------------------------------------------------------------------------
# One member
# ---------------------------------------------------------------------------

def _recently_failed(db: Session, user_id: int, now: datetime) -> bool:
    since = now - timedelta(hours=max(0, int(settings.CASHOUT_RETRY_BACKOFF_HOURS)))
    return (db.query(AffiliateCashoutRequest.id)
            .filter(AffiliateCashoutRequest.user_id == user_id,
                    AffiliateCashoutRequest.cashout_method == cs.METHOD_CRYPTO,
                    AffiliateCashoutRequest.status == CashoutStatus.FAILED.value,
                    AffiliateCashoutRequest.processed_at > since).first()) is not None


def _blocker(db: Session, user: User, now: datetime) -> Optional[str]:
    """Why this member cannot be paid right now (None = may be paid)."""
    if not user.is_active or getattr(user, "is_deleted", False):
        return "ACCOUNT_UNAVAILABLE"
    if user.cashout_method != cs.METHOD_CRYPTO:
        return "METHOD_NOT_CRYPTO"
    wallet = cs.wallet_state(user, now)
    if not wallet.payable:
        return f"WALLET_{wallet.status}"
    if not fe.evaluate(db, user, fe.FinancialOperation.WITHDRAWAL).allowed:
        return "ELIGIBILITY_HOLD"
    return None


def process_member(db: Session, user_id: int, provider, *, facts: dict, now: Optional[datetime] = None) -> str:
    """Pay one member if every condition holds. Returns a result code. Commits
    its own steps; the provider is called at most once."""
    now = now or datetime.utcnow()
    if not engine_enabled():
        return "ENGINE_DISABLED"
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None:
        db.rollback()
        return "ACCOUNT_UNAVAILABLE"
    blocker = _blocker(db, user, now)
    if blocker is None and cs.active_cashout(db, user.id) is not None:
        blocker = "CASHOUT_IN_PROGRESS"
    if blocker is None and _recently_failed(db, user.id, now):
        blocker = "RETRY_BACKOFF"
    if blocker is not None:
        db.rollback()
        return blocker

    cs.release_pending(db, user, now=now)
    rows = cs.available_rows(db, user.id)
    amount = cs.rows_total(rows)
    if amount < cs.crypto_minimum():
        db.commit()                                 # keeps PENDING -> APPROVED; reserves nothing
        return "BELOW_MINIMUM"
    if amount < facts["minimum"]:
        db.commit()
        return "BELOW_PROVIDER_MINIMUM"
    fee = facts["network_fee"]
    if fee > money(amount * MAX_NETWORK_FEE_SHARE):
        db.commit()
        return "NETWORK_FEE_TOO_HIGH"
    if facts["balance"] < amount + fee:
        db.commit()
        return "INSUFFICIENT_PROVIDER_BALANCE"

    wallet = cs.wallet_state(user, now)
    intent_ref = _intent_reference(user.id, None)
    cashout = cs.reserve(db, user, rows, method=cs.METHOD_CRYPTO, fee=Decimal("0.00"), intent_ref=intent_ref,
                         now=now, wallet=wallet.address, currency=wallet.currency)
    if cashout is None:
        return "CASHOUT_IN_PROGRESS"                # another worker reserved first
    cashout_id = int(cashout.id)

    # Committed intent. Re-check the CURRENT state immediately before provider I/O.
    user = db.query(User).filter(User.id == user_id).with_for_update().one()
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    blocker = None if engine_enabled() else "ENGINE_DISABLED"
    blocker = blocker or _blocker(db, user, now)
    if blocker is None and cs.wallet_state(user, now).address != cashout.wallet_snapshot:
        blocker = "WALLET_CHANGED"
    if blocker is not None:
        cs.release_reservation(db, cashout, status=CashoutStatus.CANCELLED.value, failure_code=blocker,
                               actor_id=None, now=now)
        db.commit()
        return blocker
    cashout.status = CashoutStatus.PROCESSING.value
    address, currency = str(cashout.wallet_snapshot), str(cashout.payout_currency)
    db.commit()

    refused = False
    result: Optional[dict] = None
    try:
        result = provider.create_payout(address=address, amount=amount, currency=currency,
                                        external_id=intent_ref.split(":", 1)[1])
    except nowpayments.NowPaymentsError as exc:
        code = exc.status_code
        refused = code is not None and 400 <= code < 500 and code not in (408, 429)
        logger.warning("Cashout %s: provider create failed (status %s)", cashout_id, code)
    except Exception:  # noqa: BLE001 - no answer: the outcome is unknown
        logger.exception("Cashout %s: provider create raised", cashout_id)

    db.rollback()
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    if result is not None and result.get("batch_id"):
        cashout.provider_batch_id = str(result["batch_id"])[:100]
        cashout.provider_status = (str(result.get("status") or "")[:30] or None)
        cashout.last_checked_at = now
        if not result.get("verified"):
            cashout.status = CashoutStatus.UNKNOWN.value
            cashout.failure_code = "PROVIDER_CONFIRMATION_FAILED"
            db.commit()
            return "OUTCOME_UNKNOWN"
        db.commit()
        return "SUBMITTED"
    if refused:
        cs.release_reservation(db, cashout, status=CashoutStatus.FAILED.value, failure_code="PROVIDER_REFUSED",
                               actor_id=None, now=now)
        db.commit()
        return "PROVIDER_REFUSED"
    cashout.status = CashoutStatus.UNKNOWN.value
    cashout.failure_code = "PROVIDER_OUTCOME_UNKNOWN"
    cashout.processed_at = now
    db.commit()
    return "OUTCOME_UNKNOWN"


# ---------------------------------------------------------------------------
# One cycle
# ---------------------------------------------------------------------------

def candidate_user_ids(db: Session, limit: int) -> list[int]:
    """Members who chose CRYPTO and have unreserved commission rows."""
    rows = (db.query(AffiliateCommission.user_id)
            .join(User, User.id == AffiliateCommission.user_id)
            .filter(User.cashout_method == cs.METHOD_CRYPTO,
                    AffiliateCommission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PENDING]),
                    AffiliateCommission.payout_reference.is_(None))
            .group_by(AffiliateCommission.user_id)
            .order_by(func.min(AffiliateCommission.transaction_date).asc(), AffiliateCommission.user_id.asc())
            .limit(limit).all())
    return [int(r.user_id) for r in rows]


def run_cycle(db: Session, *, provider=None, now: Optional[datetime] = None, limit: Optional[int] = None) -> dict:
    """Reconcile, then pay eligible members. A no-op while the engine is off."""
    if not engine_enabled():
        return {"enabled": False, "reconciled": {}, "members": {}}
    now = now or datetime.utcnow()
    provider = provider or NowPaymentsPayoutProvider()
    report = {"enabled": True, "reconciled": dict(reconcile_open(db, provider, now=now)), "members": {}}
    user_ids = candidate_user_ids(db, int(limit or settings.CASHOUT_ENGINE_BATCH_LIMIT))
    db.rollback()
    if not user_ids:
        return report
    currency = cs.CRYPTO_PAYOUT_CURRENCY
    try:
        facts = {"balance": Decimal(provider.balance(currency)), "minimum": Decimal(provider.minimum(currency)),
                 "network_fee": money(provider.network_fee(currency, cs.crypto_minimum()))}
    except Exception:  # noqa: BLE001 - without the provider's facts nothing is reserved
        logger.warning("Cashout cycle stopped: provider balance / minimum / fee could not be read")
        report["stopped"] = "PROVIDER_FACTS_UNAVAILABLE"
        return report
    results: Counter = Counter()
    for user_id in user_ids:
        try:
            outcome = process_member(db, user_id, provider, facts=facts, now=now)
        except Exception:  # noqa: BLE001 - one member's failure never stops the others
            db.rollback()
            logger.exception("Cashout cycle: member %s failed", user_id)
            outcome = "ERROR"
        results[outcome] += 1
        if outcome in ("SUBMITTED", "OUTCOME_UNKNOWN"):
            # Assume the money left (or may have): never count it for the next member.
            paid = (db.query(AffiliateCashoutRequest.net_amount)
                    .filter(AffiliateCashoutRequest.user_id == user_id)
                    .order_by(AffiliateCashoutRequest.id.desc()).first())
            facts["balance"] -= money(paid[0] if paid else 0) + facts["network_fee"]
            db.rollback()
    report["members"] = dict(results)
    return report


# ---------------------------------------------------------------------------
# Liability vs provider balance
# ---------------------------------------------------------------------------

def reconciliation_report(db: Session, *, provider=None, read_provider: bool = False) -> dict:
    """What MyHigh5 owes in commissions, by state, next to what the provider
    says it holds. The provider is asked only when `read_provider` is true and
    its credentials exist; otherwise its balance is reported as not verified."""
    def total(*criteria) -> Decimal:
        value = db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0)).filter(*criteria).scalar()
        return money(value or 0)

    approved = AffiliateCommission.status == CommissionStatus.APPROVED
    owed = {
        "pending": total(AffiliateCommission.status == CommissionStatus.PENDING),
        "available": total(approved, AffiliateCommission.payout_reference.is_(None)),
        "reserved": total(approved, AffiliateCommission.payout_reference.isnot(None)),
    }
    crypto_members = total(approved | (AffiliateCommission.status == CommissionStatus.PENDING),
                           AffiliateCommission.user_id.in_(
                               db.query(User.id).filter(User.cashout_method == cs.METHOD_CRYPTO)))
    open_by_state = dict(db.query(AffiliateCashoutRequest.status, func.count(AffiliateCashoutRequest.id))
                         .filter(AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES))
                         .group_by(AffiliateCashoutRequest.status).all())
    balance: Optional[Decimal] = None
    provider_state = "NOT_VERIFIED"
    if read_provider and nowpayments.payouts_configured():
        try:
            balance = Decimal((provider or NowPaymentsPayoutProvider()).balance(cs.CRYPTO_PAYOUT_CURRENCY))
            provider_state = "READ"
        except Exception:  # noqa: BLE001
            provider_state = "UNAVAILABLE"
    unpaid = money(owed["pending"] + owed["available"] + owed["reserved"])
    return {
        "owed": {k: float(v) for k, v in owed.items()},
        "owed_total": float(unpaid),
        "owed_to_crypto_cashout_members": float(crypto_members),
        "open_cashouts": {str(k): int(v) for k, v in open_by_state.items()},
        "provider_balance_state": provider_state,
        "provider_balance": float(balance) if balance is not None else None,
        "provider_covers_crypto_members": (balance >= crypto_members) if balance is not None else None,
        "engine": engine_status(),
    }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class CashoutScheduler:
    """Runs run_cycle periodically. While the engine is off each tick returns
    before opening a database session."""

    def __init__(self, check_interval_seconds: Optional[int] = None):
        self.check_interval = int(check_interval_seconds or settings.CASHOUT_ENGINE_INTERVAL_SECONDS)
        self.running = False
        self._task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Cashout scheduler started (interval: %ss, engine enabled: %s)", self.check_interval,
                    engine_enabled())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cashout scheduler stopped")

    async def _loop(self):
        await asyncio.sleep(30)
        while self.running:
            try:
                await self._run_cycle()
            except Exception:  # noqa: BLE001
                logger.exception("Cashout cycle failed")
            await asyncio.sleep(self.check_interval)

    async def _run_cycle(self):
        if not engine_enabled():
            return {"enabled": False}
        return await asyncio.to_thread(self._run_once)

    @staticmethod
    def _run_once() -> dict:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            report = run_cycle(db)
            logger.info("Cashout cycle: %s", report)
            return report
        finally:
            db.close()
