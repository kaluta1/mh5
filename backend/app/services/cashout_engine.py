"""Automatic crypto payout engine for members who chose Crypto Cashout.

OFF BY DEFAULT. engine_enabled() is true only when ALL of these hold:
  * the SERVER master switch CRYPTO_AUTO_PAYOUT_ENABLED is explicitly "true";
  * in Admin > Finance & Payments the provider, Crypto Cashout and Automatic
    payouts are on;
  * every payout credential is present in the ONE source selected there.
With the server switch off, run_cycle() returns immediately: it reads no
member, writes no row, reserves nothing and never calls the provider. With the
server switch on but automatic payouts paused by an administrator, a cycle
only reconciles payouts that were already handed to the provider (so nothing
stays reserved for ever) and starts no new one.

Every limit below is read from app.services.payment_config at the start of a
cycle. Changing a setting never releases a reservation and never sends
anything by itself.

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
     cashout, no recent failed payout and not too many of them, the minimum
     interval since the member's last payout, whole available rows >= the
     configured minimum and <= the maximum single payout, the daily amount and
     count limits, the amount sent >= the provider's minimum, the network fee
     within its allowed share, provider balance less the configured reserve
     >= amount + network fee
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

MyHigh5 charges no fee on a crypto cashout. Network fee policy COMPANY_PAYS:
the member receives the full commission amount and the fee is paid from the
provider balance. MEMBER_PAYS: the provider's fee estimate is deducted from
the amount sent. Whether the provider adds its fee on top of the amount or
takes it out of it is an account setting at the provider that has NOT been
verified; the balance check always assumes the more expensive case.

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

from app.models.accounting import JournalEntry
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
from app.services import payment_config
from app.services.commission_payout_service import _intent_reference
from app.services.financial_integrity import money

logger = logging.getLogger(__name__)

PROVIDER_PAID = {"FINISHED"}
PROVIDER_NOT_PAID = {"FAILED", "REJECTED"}


# Handed to the provider (or possibly): what the daily limits count.
SENT_STATUSES = (CashoutStatus.PROCESSING.value, CashoutStatus.UNKNOWN.value, CashoutStatus.COMPLETED.value)
RETRY_WINDOW = timedelta(days=7)
STALE_PROCESSING_AFTER = timedelta(hours=24)


class NowPaymentsPayoutProvider:
    """The real provider. Every method is one HTTP call, made with the payout
    credentials resolved for this run."""

    def __init__(self, credentials):
        self._credentials = credentials

    def balance(self, currency: str) -> Decimal:
        return nowpayments.custody_balance_sync(currency, self._credentials)

    def minimum(self, currency: str) -> Decimal:
        return nowpayments.payout_min_amount_sync(currency, self._credentials)

    def network_fee(self, currency: str, amount: Decimal) -> Decimal:
        return nowpayments.payout_fee_estimate_sync(currency, amount, self._credentials)

    def create_payout(self, *, address: str, amount: Decimal, currency: str, external_id: str) -> dict:
        return nowpayments.create_single_payout_sync(wallet_address=address, amount=amount, currency=currency,
                                                     external_id=external_id, credentials=self._credentials)

    def payout_status(self, batch_id: str) -> str:
        return nowpayments.payout_status_sync(batch_id, self._credentials)


def engine_enabled(db: Session, *, config=None) -> bool:
    config = config or payment_config.load(db)
    return bool(config.auto_payout_allowed) and payment_config.resolve_credentials(db, config).payout_ready


def engine_status(db: Session) -> dict:
    config = payment_config.load(db)
    credentials = payment_config.resolve_credentials(db, config)
    return {"enabled": bool(config.auto_payout_allowed) and credentials.payout_ready,
            "server_switch": payment_config.crypto_master_switch(),
            "provider_enabled": bool(config.provider_enabled),
            "crypto_cashout_enabled": bool(config.crypto_cashout_enabled),
            "automatic_payouts": bool(config.crypto_auto_payout_enabled),
            "provider_credentials_ready": credentials.payout_ready, "missing": credentials.payout_missing,
            "credential_source": credentials.payout_source}


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
            cs.complete(db, cashout, settlement_reference=batch_id,
                        cash_account=payment_config.load(db).treasury_account, actor_id=None, now=now)
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

def _crypto_cashouts(db: Session, user_id: Optional[int] = None):
    query = db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.cashout_method == cs.METHOD_CRYPTO)
    return query if user_id is None else query.filter(AffiliateCashoutRequest.user_id == user_id)


def _recently_failed(db: Session, user_id: int, now: datetime, config) -> bool:
    since = now - timedelta(hours=max(0, int(config.retry_backoff_hours)))
    return (_crypto_cashouts(db, user_id)
            .filter(AffiliateCashoutRequest.status == CashoutStatus.FAILED.value,
                    AffiliateCashoutRequest.processed_at > since).first()) is not None


def _retry_limit_reached(db: Session, user_id: int, now: datetime, config) -> bool:
    failed = (_crypto_cashouts(db, user_id)
              .filter(AffiliateCashoutRequest.status == CashoutStatus.FAILED.value,
                      AffiliateCashoutRequest.processed_at > now - RETRY_WINDOW).count())
    return failed >= int(config.retry_max_attempts)


def _paid_recently(db: Session, user_id: int, now: datetime, config) -> bool:
    hours = int(config.min_hours_between_payouts)
    if hours <= 0:
        return False
    return (_crypto_cashouts(db, user_id)
            .filter(AffiliateCashoutRequest.status.in_(SENT_STATUSES),
                    AffiliateCashoutRequest.requested_at > now - timedelta(hours=hours)).first()) is not None


def day_usage(db: Session, now: datetime) -> tuple[Decimal, int]:
    """(amount, count) of crypto payouts handed to the provider in the last 24 hours."""
    total, count = (db.query(func.coalesce(func.sum(AffiliateCashoutRequest.gross_amount), 0),
                             func.count(AffiliateCashoutRequest.id))
                    .filter(AffiliateCashoutRequest.cashout_method == cs.METHOD_CRYPTO,
                            AffiliateCashoutRequest.status.in_(SENT_STATUSES),
                            AffiliateCashoutRequest.requested_at > now - timedelta(hours=24)).one())
    return money(total or 0), int(count or 0)


def _blocker(db: Session, user: User, now: datetime, config) -> Optional[str]:
    """Why this member cannot be paid right now (None = may be paid)."""
    if not user.is_active or getattr(user, "is_deleted", False):
        return "ACCOUNT_UNAVAILABLE"
    if user.cashout_method != cs.METHOD_CRYPTO:
        return "METHOD_NOT_CRYPTO"
    wallet = cs.wallet_state(user, now, config=config)
    if not wallet.payable:
        return f"WALLET_{wallet.status}"
    if not fe.evaluate(db, user, fe.FinancialOperation.WITHDRAWAL).allowed:
        return "ELIGIBILITY_HOLD"
    return None


def process_member(db: Session, user_id: int, provider, *, facts: dict, config=None,
                   now: Optional[datetime] = None) -> str:
    """Pay one member if every condition holds. Returns a result code. Commits
    its own steps; the provider is called at most once."""
    now = now or datetime.utcnow()
    config = config or payment_config.load(db)
    if not engine_enabled(db, config=config):
        return "ENGINE_DISABLED"
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None:
        db.rollback()
        return "ACCOUNT_UNAVAILABLE"
    blocker = _blocker(db, user, now, config)
    if blocker is None and cs.active_cashout(db, user.id) is not None:
        blocker = "CASHOUT_IN_PROGRESS"
    if blocker is None and _recently_failed(db, user.id, now, config):
        blocker = "RETRY_BACKOFF"
    if blocker is None and _retry_limit_reached(db, user.id, now, config):
        blocker = "RETRY_LIMIT_REACHED"
    if blocker is None and _paid_recently(db, user.id, now, config):
        blocker = "PAYOUT_INTERVAL"
    if blocker is not None:
        db.rollback()
        return blocker

    cs.release_pending(db, user, now=now, config=config)
    rows = cs.available_rows(db, user.id)
    amount = cs.rows_total(rows)
    fee = money(facts["network_fee"])
    member_pays = config.network_fee_policy == payment_config.FEE_MEMBER_PAYS
    send = money(amount - fee) if member_pays else amount

    def stop(code: str) -> str:
        db.commit()                                 # keeps PENDING -> APPROVED; reserves nothing
        return code

    if "day_count" not in facts:                    # a caller outside run_cycle
        facts["day_total"], facts["day_count"] = day_usage(db, now)
    if amount < cs.crypto_minimum(config=config):
        return stop("BELOW_MINIMUM")
    if amount > money(config.max_single_payout_usd):
        return stop("EXCEEDS_SINGLE_LIMIT")
    if (facts["day_count"] >= int(config.max_daily_payout_count)
            or money(facts["day_total"] + amount) > money(config.max_daily_payout_usd)):
        return stop("DAILY_LIMIT_REACHED")
    if send <= 0 or fee > money(amount * Decimal(config.max_network_fee_percent) / Decimal("100")):
        return stop("NETWORK_FEE_TOO_HIGH")
    if send < facts["minimum"]:
        return stop("BELOW_PROVIDER_MINIMUM")
    if facts["balance"] - money(config.provider_balance_reserve_usd) < amount + fee:
        return stop("INSUFFICIENT_PROVIDER_BALANCE")

    wallet = cs.wallet_state(user, now, config=config)
    intent_ref = _intent_reference(user.id, None)
    cashout = cs.reserve(db, user, rows, method=cs.METHOD_CRYPTO, fee=Decimal("0.00"), intent_ref=intent_ref,
                         now=now, wallet=wallet.address, currency=wallet.currency, net=send, network_fee=fee,
                         network_fee_policy=config.network_fee_policy)
    if cashout is None:
        return "CASHOUT_IN_PROGRESS"                # another worker reserved first
    cashout_id = int(cashout.id)

    # Committed intent. Re-check the CURRENT state immediately before provider I/O.
    user = db.query(User).filter(User.id == user_id).with_for_update().one()
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    current = payment_config.load(db)
    blocker = None if engine_enabled(db, config=current) else "ENGINE_DISABLED"
    blocker = blocker or _blocker(db, user, now, current)
    if blocker is None and cs.wallet_state(user, now, config=current).address != cashout.wallet_snapshot:
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
        result = provider.create_payout(address=address, amount=send, currency=currency,
                                        external_id=intent_ref.split(":", 1)[1])
    except nowpayments.NowPaymentsError as exc:
        code = exc.status_code
        refused = code is not None and 400 <= code < 500 and code not in (408, 429)
        logger.warning("Cashout %s: provider create failed (status %s)", cashout_id, code)
    except Exception:  # noqa: BLE001 - no answer: the outcome is unknown
        logger.error("Cashout %s: provider create raised", cashout_id)

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
    """Reconcile, then pay eligible members. A no-op while the server master
    switch is off; reconcile-only while an administrator paused payouts."""
    from app.core.config import settings

    if not payment_config.crypto_master_switch():
        return {"enabled": False, "reconciled": {}, "members": {}}
    now = now or datetime.utcnow()
    config = payment_config.load(db)
    credentials = payment_config.resolve_credentials(db, config)
    if not (config.provider_enabled and credentials.payout_ready):
        return {"enabled": False, "reconciled": {}, "members": {}}
    provider = provider or NowPaymentsPayoutProvider(credentials)
    report = {"enabled": bool(config.auto_payout_allowed),
              "reconciled": dict(reconcile_open(db, provider, now=now)), "members": {}}
    if not report["enabled"]:
        return report
    user_ids = candidate_user_ids(db, int(limit or settings.CASHOUT_ENGINE_BATCH_LIMIT))
    db.rollback()
    if not user_ids:
        return report
    currency = config.crypto_payout_currency
    try:
        facts = {"balance": Decimal(provider.balance(currency)), "minimum": Decimal(provider.minimum(currency)),
                 "network_fee": money(provider.network_fee(currency, cs.crypto_minimum(config=config)))}
    except Exception:  # noqa: BLE001 - without the provider's facts nothing is reserved
        logger.warning("Cashout cycle stopped: provider balance / minimum / fee could not be read")
        report["stopped"] = "PROVIDER_FACTS_UNAVAILABLE"
        return report
    facts["day_total"], facts["day_count"] = day_usage(db, now)
    db.rollback()
    results: Counter = Counter()
    for user_id in user_ids:
        try:
            outcome = process_member(db, user_id, provider, facts=facts, config=config, now=now)
        except Exception:  # noqa: BLE001 - one member's failure never stops the others
            db.rollback()
            logger.exception("Cashout cycle: member %s failed", user_id)
            outcome = "ERROR"
        results[outcome] += 1
        if outcome in ("SUBMITTED", "OUTCOME_UNKNOWN"):
            # Assume the money left (or may have): never count it for the next member.
            sent = (db.query(AffiliateCashoutRequest.gross_amount)
                    .filter(AffiliateCashoutRequest.user_id == user_id)
                    .order_by(AffiliateCashoutRequest.id.desc()).first())
            gross = money(sent[0] if sent else 0)
            facts["balance"] -= gross + facts["network_fee"]
            facts["day_total"] = money(facts["day_total"] + gross)
            facts["day_count"] += 1
            db.rollback()
    report["members"] = dict(results)
    return report


# ---------------------------------------------------------------------------
# Liability vs provider balance, and what does not add up
# ---------------------------------------------------------------------------

def discrepancies(db: Session, *, now: Optional[datetime] = None, limit: int = 200) -> list[dict]:
    """Internal inconsistencies an administrator must look at. Read-only; it
    compares the cashout rows with the commission rows and the journal. It
    does not, and cannot, prove what the provider holds."""
    now = now or datetime.utcnow()
    out: list[dict] = []

    def add(kind: str, severity: str, message: str, **ref) -> None:
        if len(out) < limit:
            out.append({"type": kind, "severity": severity, "message": message, **ref})

    open_rows = (db.query(AffiliateCashoutRequest)
                 .filter(AffiliateCashoutRequest.status.in_(ACTIVE_CASHOUT_STATUSES))
                 .order_by(AffiliateCashoutRequest.id).all())
    intents = set()
    for cashout in open_rows:
        intent = cs._intent(cashout)
        intents.add(intent)
        reserved = (db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0))
                    .filter(AffiliateCommission.user_id == cashout.user_id,
                            AffiliateCommission.payout_reference == intent,
                            AffiliateCommission.status == CommissionStatus.APPROVED).scalar())
        if money(reserved or 0) != money(cashout.gross_amount):
            add("RESERVATION_MISMATCH", "critical",
                f"Cashout #{cashout.id}: reserved commissions (${money(reserved or 0):.2f}) do not equal the "
                f"cashout amount (${money(cashout.gross_amount):.2f}).", cashout_id=cashout.id,
                user_id=cashout.user_id)
        if cashout.status == CashoutStatus.UNKNOWN.value:
            add("UNKNOWN_OUTCOME", "critical",
                f"Cashout #{cashout.id}: the provider outcome is unknown. Check the provider, then record it "
                "as sent or not sent.", cashout_id=cashout.id, user_id=cashout.user_id)
        elif (cashout.status == CashoutStatus.PROCESSING.value
              and cashout.requested_at < now - STALE_PROCESSING_AFTER):
            add("STALE_PROCESSING", "warning",
                f"Cashout #{cashout.id} has been processing for more than 24 hours.", cashout_id=cashout.id,
                user_id=cashout.user_id)
    orphans = (db.query(AffiliateCommission.payout_reference, AffiliateCommission.user_id,
                        func.sum(AffiliateCommission.commission_amount))
               .filter(AffiliateCommission.status == CommissionStatus.APPROVED,
                       AffiliateCommission.payout_reference.isnot(None))
               .group_by(AffiliateCommission.payout_reference, AffiliateCommission.user_id).all())
    for reference, user_id, total in orphans:
        if reference not in intents:
            add("ORPHAN_RESERVATION", "critical",
                f"Member {user_id}: ${money(total or 0):.2f} of commissions is reserved for a cashout that is "
                "not open.", user_id=user_id)
    completed = (db.query(AffiliateCashoutRequest.id, AffiliateCashoutRequest.user_id)
                 .filter(AffiliateCashoutRequest.status == CashoutStatus.COMPLETED.value,
                         AffiliateCashoutRequest.cashout_method.isnot(None))
                 .order_by(AffiliateCashoutRequest.id.desc()).limit(500).all())
    posted = {d for (d,) in db.query(JournalEntry.description)
              .filter(JournalEntry.description.in_([f"Affiliate Cashout #{cid}" for cid, _ in completed])).all()} \
        if completed else set()
    for cashout_id, user_id in completed:
        if f"Affiliate Cashout #{cashout_id}" not in posted:
            add("MISSING_JOURNAL", "critical", f"Cashout #{cashout_id} is completed but has no journal entry.",
                cashout_id=cashout_id, user_id=user_id)
    return out


def reconciliation_report(db: Session, *, provider=None, read_provider: bool = False,
                          now: Optional[datetime] = None) -> dict:
    """What MyHigh5 owes in commissions, by state, next to what the provider
    says it holds. The provider is asked only when `read_provider` is true and
    its credentials exist; otherwise its balance is reported as not verified.
    An internal balance is never treated as proof of the provider's funds."""
    def total(*criteria) -> Decimal:
        value = db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0)).filter(*criteria).scalar()
        return money(value or 0)

    config = payment_config.load(db)
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
    credentials = payment_config.resolve_credentials(db, config)
    if read_provider and credentials.get("PAYOUT_API_KEY"):
        try:
            balance = Decimal((provider or NowPaymentsPayoutProvider(credentials))
                              .balance(config.crypto_payout_currency))
            provider_state = "READ"
        except Exception:  # noqa: BLE001
            provider_state = "UNAVAILABLE"
    unpaid = money(owed["pending"] + owed["available"] + owed["reserved"])
    day_total, day_count = day_usage(db, now or datetime.utcnow())
    items = discrepancies(db)
    if balance is not None and balance < crypto_members:
        items.insert(0, {"type": "PROVIDER_BALANCE_SHORT", "severity": "critical",
                         "message": f"The provider balance ({balance}) is lower than what is owed to Crypto "
                                    f"Cashout members (${crypto_members:.2f})."})
    return {
        "owed": {k: float(v) for k, v in owed.items()},
        "owed_total": float(unpaid),
        "owed_to_crypto_cashout_members": float(crypto_members),
        "open_cashouts": {str(k): int(v) for k, v in open_by_state.items()},
        "provider_balance_state": provider_state,
        "provider_balance": float(balance) if balance is not None else None,
        "provider_covers_crypto_members": (balance >= crypto_members) if balance is not None else None,
        "last_24_hours": {"crypto_payout_amount": float(day_total), "crypto_payout_count": day_count,
                          "amount_limit": float(config.max_daily_payout_usd),
                          "count_limit": int(config.max_daily_payout_count)},
        "discrepancies": items,
        "engine": engine_status(db),
    }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class CashoutScheduler:
    """Runs run_cycle periodically. While the engine is off each tick returns
    before opening a database session."""

    def __init__(self, check_interval_seconds: Optional[int] = None):
        # Used until the configured interval can be read (and while the server switch is off).
        self.check_interval = int(check_interval_seconds or 900)
        self.running = False
        self._task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Cashout scheduler started (server master switch: %s)", payment_config.crypto_master_switch())

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
            await asyncio.sleep(await self._interval())

    async def _interval(self) -> int:
        if not payment_config.crypto_master_switch():
            return self.check_interval
        try:
            return await asyncio.to_thread(self._configured_interval)
        except Exception:  # noqa: BLE001
            return self.check_interval

    @staticmethod
    def _configured_interval() -> int:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            return max(60, int(payment_config.load(db).payout_interval_seconds))
        finally:
            db.close()

    async def _run_cycle(self):
        if not payment_config.crypto_master_switch():
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
