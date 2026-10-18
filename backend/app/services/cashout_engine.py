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
cycle. Changing a setting never sends anything by itself. A cycle never pays
under values that are no longer in force: the configuration version it read is
compared with the one in force, under the settings lock, immediately before a
payout is reserved and again immediately before it is handed to the provider.
If the configuration changed in between (even if it was changed and approved
again), nothing more is reserved, a reservation not yet handed over is
released, and the cycle stops (CONFIGURATION_CHANGED); the next cycle starts
from the new configuration.

One cycle
---------
1. Reconcile: for every crypto cashout already handed to the provider, ask
   the provider for its status. The provider documents that ONLY "finished"
   and "rejected" are final:
     FINISHED  and the payout it describes is ours (same address, same unique
               reference) -> the commissions become PAID, the journal is posted
     REJECTED  -> the reservation is released
     FAILED    is NOT final ("processing may resume or the payout may be
               retried on NOWPayments' side"): the cashout stays reserved, is
               marked for review and keeps being checked; it is never re-sent
     anything else is left as it is.
   A cashout whose creation got no answer has no payout id; it is looked up in
   the provider's list of payouts by its unique reference. Not finding it
   proves nothing, so it stays reserved for an administrator.
2. Read the provider's facts once: the payout login, its custody balance, its
   minimum payout and its network fee. If any cannot be read, the cycle stops
   (nothing reserved).
3. For each member who chose CRYPTO, under a lock on the member row:
     payable wallet (verified, hold elapsed), financial eligibility, no open
     cashout, no recent failed payout and not too many of them, the minimum
     interval since the member's last payout, the member's acceptance of the
     network fee terms, whole available rows >= the configured minimum and
     <= the maximum single payout, the daily amount and count limits, the
     provider's fee estimate for this payout within the member's limit, the
     amount received >= the configured and the provider's minimum, provider
     balance less the configured reserve >= amount + network fee, the
     provider accepts the address
   -> reserve the rows and COMMIT the intent
   -> re-check the same conditions, mark it processing, COMMIT
   -> ask the provider to create the payout (once).

Provider answers
----------------
  refused with a 4xx          nothing exists at the provider: released, FAILED
                              (a refused LOGIN or a refused server IP is the
                              platform's problem, not the member's: released as
                              CANCELLED and the cycle stops)
  created and confirmed       stays reserved and PROCESSING until step 1 of a
                              later cycle sees FINISHED
  created, confirmation failed / timeout / 5xx / no answer
                              UNKNOWN: stays reserved, is never sent again by
                              the engine; resolved by the provider's status
                              (when a payout id is known) or by an administrator

MyHigh5 charges no fee on a crypto cashout. The network fee is paid by the
BENEFICIARY (owner decision): the whole commission amount is handed to the
provider, which takes its fee out of it, and the beneficiary receives the
rest. This engine never subtracts the fee itself, so it is taken once.

Whether the provider takes its fee out of the amount or from the MyHigh5
balance is a setting of the provider account, NOT verifiable from here. So no
payout is created unless an administrator recorded that it was confirmed
(provider fee behaviour DEDUCTED_BY_PROVIDER), the member fee limits are set
and approved, and the member accepted the fee terms. The provider's estimate
for each payout is checked against that member's limit before anything is
reserved; the balance check assumes the more expensive case. When a finished
payout shows that the provider behaved otherwise, the behaviour goes back to
UNVERIFIED and nothing more is sent. A payout under the retired COMPANY_PAYS
policy is never created.

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

from sqlalchemy import func, or_
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
from app.services.commission_payout_hold import held_clause
from app.services.financial_integrity import money

logger = logging.getLogger(__name__)

# The provider's two FINAL payout statuses. "FAILED" is deliberately in neither
# set: the provider may still process a failed payout.
PROVIDER_PAID = {"FINISHED"}
PROVIDER_NOT_PAID = {"REJECTED"}
PROVIDER_NOT_FINAL_FAILURE = {"FAILED"}
PROVIDER_IN_PROGRESS = {"CREATING", "WAITING", "PROCESSING", "SENDING"}


# Handed to the provider (or possibly): what the daily limits count.
SENT_STATUSES = (CashoutStatus.PROCESSING.value, CashoutStatus.UNKNOWN.value, CashoutStatus.COMPLETED.value)
RETRY_WINDOW = timedelta(days=7)
STALE_PROCESSING_AFTER = timedelta(hours=24)
LOCATE_WINDOW = timedelta(days=7)       # how long a payout without an id is looked for in the provider's list


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

    def payout_details(self, batch_id: str) -> dict:
        return nowpayments.payout_details_sync(batch_id, self._credentials)

    def find_payout(self, external_id: str) -> Optional[dict]:
        return nowpayments.find_payout_by_external_id_sync(external_id, self._credentials)

    def check_session(self) -> None:
        """Raises when the provider refuses the payout login."""
        nowpayments._engine_token_sync(self._credentials)

    def validate_address(self, address: str, currency: str) -> bool:
        return nowpayments.validate_payout_address_sync(address, currency, self._credentials)

    def currency_details(self, currency: str) -> dict:
        return nowpayments.currency_details_sync(currency, self._credentials)


def commission_intent_reference(db: Session, commission_id: int) -> str:
    """Deterministic idempotency key of the next payout attempt of ONE commission:
    intent:c<commission id>-a<attempt number>. The part after "intent:" is the
    provider's unique_external_id. Attempt n+1 exists only after attempt n was
    recorded as not paid (failed or cancelled), and the database refuses a second
    open or paid attempt of the same commission (uq_cashout_commission_live)."""
    attempts = (db.query(func.count(AffiliateCashoutRequest.id))
                .filter(AffiliateCashoutRequest.commission_id == int(commission_id)).scalar() or 0)
    return f"intent:c{int(commission_id)}-a{int(attempts) + 1}"


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

def external_reference(cashout: AffiliateCashoutRequest) -> str:
    """The unique reference this cashout was (or would be) sent to the provider with."""
    return cs._intent(cashout).split(":", 1)[-1]


def _provider_details(provider, batch_id: str) -> dict:
    """What the provider reports for one payout. A provider that can only
    report a status yields {"status"}; the evidence check then has nothing to
    compare and is skipped."""
    read = getattr(provider, "payout_details", None)
    if read is None:
        return {"status": str(provider.payout_status(batch_id) or "").upper()}
    details = dict(read(batch_id) or {})
    details["status"] = str(details.get("status") or "").upper()
    return details


def _same_address(left: Optional[str], right: Optional[str]) -> bool:
    left, right = str(left or "").strip(), str(right or "").strip()
    if left.lower().startswith("0x") and right.lower().startswith("0x"):
        return left.lower() == right.lower()        # EVM addresses differ only by checksum case
    return bool(left) and left == right


def evidence_problem(cashout: AffiliateCashoutRequest, details: dict) -> Optional[str]:
    """Why the payout the provider describes is NOT proof that this cashout
    was paid (None = it is this cashout's payout). Only fields the provider
    actually returned are compared."""
    if "address" in details and not _same_address(details.get("address"), cashout.wallet_snapshot):
        return "PROVIDER_ADDRESS_MISMATCH"
    reference = details.get("unique_external_id")
    if reference and str(reference) != external_reference(cashout):
        return "PROVIDER_REFERENCE_MISMATCH"
    currency = details.get("currency")
    if currency and cashout.payout_currency and str(currency).lower() != str(cashout.payout_currency).lower():
        return "PROVIDER_CURRENCY_MISMATCH"
    return None


def _locate_unknown(db: Session, cashout_id: int, provider, now: datetime) -> str:
    """A cashout whose creation got no answer has no payout id. Look for its
    unique reference in the provider's list of payouts; when exactly one
    payout to the same address carries it, attach that payout so the normal
    reconciliation takes over. Not finding it proves nothing: the cashout
    stays reserved for an administrator. Commits."""
    find = getattr(provider, "find_payout", None)
    cashout = db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id).one()
    reference, requested_at = external_reference(cashout), cashout.requested_at
    db.rollback()
    if find is None or not reference or requested_at < now - LOCATE_WINDOW:
        return "SKIPPED"                            # old: an administrator settles it by hand
    try:
        found = find(reference)
    except Exception:  # noqa: BLE001 - not knowing is not a result
        logger.warning("Cashout %s: the provider's list of payouts could not be read", cashout_id)
        return "STATUS_UNAVAILABLE"
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    if cashout.status != CashoutStatus.UNKNOWN.value or cashout.provider_batch_id:
        db.rollback()
        return "SKIPPED"
    cashout.last_checked_at = now
    if not found or not found.get("batch_id"):
        db.commit()
        return "NOT_LOCATED"
    if evidence_problem(cashout, found) is not None:
        cashout.failure_code = evidence_problem(cashout, found)
        db.commit()
        return "EVIDENCE_MISMATCH"
    cashout.provider_batch_id = str(found["batch_id"])[:100]
    cashout.provider_status = (str(found.get("status") or "")[:30] or None)
    db.flush()
    cs._audit(db, record_id=cashout.id, action="CASHOUT_PAYOUT_LOCATED", actor_id=None, old=None,
              new={"provider_batch_id": cashout.provider_batch_id, "provider_status": cashout.provider_status})
    db.commit()
    return "LOCATED"


def reconcile_cashout(db: Session, cashout_id: int, provider, *, now: Optional[datetime] = None) -> str:
    """Apply the provider's status to one crypto cashout. Commits."""
    now = now or datetime.utcnow()
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    if (cashout.cashout_method != cs.METHOD_CRYPTO
            or cashout.status not in (CashoutStatus.PROCESSING.value, CashoutStatus.UNKNOWN.value)):
        db.rollback()
        return "SKIPPED"
    if not cashout.provider_batch_id:
        unknown = cashout.status == CashoutStatus.UNKNOWN.value
        db.rollback()
        return _locate_unknown(db, cashout_id, provider, now) if unknown else "SKIPPED"
    batch_id = str(cashout.provider_batch_id)
    db.rollback()                                   # no lock is held while waiting for the provider
    try:
        details = _provider_details(provider, batch_id)
    except Exception:  # noqa: BLE001 - not knowing is not a result
        logger.warning("Cashout %s: provider status could not be read", cashout_id)
        return "STATUS_UNAVAILABLE"
    status = details["status"]
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    if cashout.status not in (CashoutStatus.PROCESSING.value, CashoutStatus.UNKNOWN.value):
        db.rollback()
        return "SKIPPED"
    cashout.provider_status = status[:30] or None
    cashout.last_checked_at = now
    if details.get("hash") and not cashout.tx_hash:
        cashout.tx_hash = str(details["hash"]).strip()[:150]     # the blockchain transaction
    problem = evidence_problem(cashout, details)
    if problem is not None:
        # The provider is describing a payout that is not this cashout's. Nothing
        # it says about it may pay or release anything here.
        cashout.status = CashoutStatus.UNKNOWN.value
        cashout.failure_code = problem
        db.commit()
        logger.error("Cashout %s: the provider payout does not match (%s)", cashout_id, problem)
        return "EVIDENCE_MISMATCH"
    if status in PROVIDER_NOT_FINAL_FAILURE:
        # Not final: the provider may still send it. Keep the money reserved.
        cashout.status = CashoutStatus.UNKNOWN.value
        cashout.failure_code = "PROVIDER_FAILED_NOT_FINAL"
        db.commit()
        _notify(db, cashout_id, "DELAYED")
        return "PROVIDER_FAILED"
    if status in PROVIDER_PAID:
        try:
            cs.complete(db, cashout, settlement_reference=batch_id,
                        cash_account=payment_config.load(db).treasury_account, actor_id=None, now=now)
        except cs.CashoutError as exc:
            db.rollback()
            logger.error("Cashout %s was paid by the provider but cannot be posted: %s", cashout_id, exc.code)
            return "PAID_BUT_NOT_POSTED"
        cs._audit(db, record_id=cashout_id, action="CASHOUT_PROVIDER_EVIDENCE", actor_id=None, old=None,
                  new={"provider_status": status, "provider_batch_id": batch_id,
                       "transaction_hash": details.get("hash"), "withdrawal_id": details.get("withdrawal_id"),
                       # Recorded for the books; not posted (see the network-fee accounting note in the runbook).
                       "provider_fee": details.get("fee"), "provider_fee_paid_by": details.get("fee_paid_by"),
                       "network_fee_estimate": (str(money(cashout.network_fee))
                                                if cashout.network_fee is not None else None),
                       "network_fee_policy": cashout.network_fee_policy})
        # Legacy company-paid payout: books the fee only when the provider reported
        # it AND said it came from our balance.
        cs.record_provider_network_fee(db, cashout, details, now)
        # Beneficiary-paid payout: records the actual fee (no entry is posted) and
        # checks that the provider behaved as configured. If it did not, no further
        # payout is created until a person has looked.
        cs.record_provider_member_fee(db, cashout, details, now)
        # A confirmed inconsistency suspends ALL payouts until an administrator
        # reviews it and reactivates them; nothing here ever lifts a suspension.
        # A fee that is only missing or unverified is left to the recording gate.
        cs.suspend_if_inconsistent(db, cashout)
        db.commit()
        _notify(db, cashout_id, "COMPLETED")
        return "COMPLETED"
    if status in PROVIDER_NOT_PAID:
        cs.release_reservation(db, cashout, status=CashoutStatus.FAILED.value,
                               failure_code=f"PROVIDER_{status}", actor_id=None, now=now)
        db.commit()
        _notify(db, cashout_id, "FAILED")
        return "FAILED"
    if cashout.failure_code == "PROVIDER_FAILED_NOT_FINAL" and status in PROVIDER_IN_PROGRESS:
        # The provider resumed a payout it had reported as failed.
        cashout.status = CashoutStatus.PROCESSING.value
        cashout.failure_code = None
    db.commit()
    return "PENDING"


def _notify(db: Session, cashout_id: int, kind: str) -> None:
    """Tell the member about a payout outcome. Called AFTER the outcome is
    committed; never raises (the email outbox is idempotent per payout and kind)."""
    try:
        from app.services import payout_notifications

        payout_notifications.payout_outcome(db, cashout_id, kind)
    except Exception:  # noqa: BLE001 - a notification never changes a payout
        logger.exception("Cashout %s: %s notification could not be queued", cashout_id, kind)
        db.rollback()


# A payout marked as being handed to the provider but carrying no provider id
# after this long: the worker stopped between the two (crash, restart). It may or
# may not exist at the provider, so it becomes UNKNOWN and is LOOKED FOR by its
# unique reference; it is never sent again.
INTERRUPTED_AFTER = timedelta(minutes=15)


def _mark_interrupted(db: Session, now: datetime) -> int:
    rows = (db.query(AffiliateCashoutRequest)
            .filter(AffiliateCashoutRequest.cashout_method == cs.METHOD_CRYPTO,
                    AffiliateCashoutRequest.status == CashoutStatus.PROCESSING.value,
                    AffiliateCashoutRequest.provider_batch_id.is_(None),
                    AffiliateCashoutRequest.requested_at < now - INTERRUPTED_AFTER)
            .with_for_update().all())
    for row in rows:
        row.status = CashoutStatus.UNKNOWN.value
        row.failure_code = "WORKER_INTERRUPTED"
        cs._audit(db, record_id=row.id, action="CASHOUT_INTERRUPTED", actor_id=None,
                  old={"status": CashoutStatus.PROCESSING.value},
                  new={"status": row.status, "reason": "no provider id after the hand-over; looked up, never resent"})
    db.commit()
    return len(rows)


def reconcile_open(db: Session, provider, *, now: Optional[datetime] = None) -> Counter:
    _mark_interrupted(db, now or datetime.utcnow())
    ids = [row.id for row in db.query(AffiliateCashoutRequest.id)
           .filter(AffiliateCashoutRequest.cashout_method == cs.METHOD_CRYPTO,
                   or_(AffiliateCashoutRequest.provider_batch_id.isnot(None),
                       AffiliateCashoutRequest.status == CashoutStatus.UNKNOWN.value),
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
    if blocker is None and cs.active_pooled_cashout(db, user.id) is not None:
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
    # Owner rule 2026-10-18: every commission is paid by its OWN payout (no
    # combining). This call pays the oldest available commission that can be paid
    # on its own; one below the minimum or above the single-payout limit stays
    # available and unpaid (never combined) and never holds the others back.
    available = cs.available_rows(db, user.id)
    if not available:
        db.commit()
        return "NOTHING_TO_PAY"
    own_minimum = cs.crypto_minimum(config=config)
    provider_minimum = Decimal(str(facts.get("minimum") or 0))
    ceiling = money(config.max_single_payout_usd)
    payable_rows = [r for r in available
                    if max(own_minimum, provider_minimum) <= money(r.commission_amount) <= ceiling]
    if not payable_rows:
        db.commit()
        amounts = [money(r.commission_amount) for r in available]
        if all(a > ceiling for a in amounts):
            return "EXCEEDS_SINGLE_LIMIT"
        if any(own_minimum <= a <= ceiling for a in amounts):
            return "BELOW_PROVIDER_MINIMUM"
        return "BELOW_MINIMUM"
    rows = payable_rows[:1]
    commission_id = int(rows[0].id)
    amount = cs.rows_total(rows)

    def stop(code: str) -> str:
        db.commit()                                 # keeps PENDING -> APPROVED; reserves nothing
        return code

    gate = config.fee_gate()
    if gate is not None:
        return stop(gate)                           # fail closed: the network fee rules are not in force
    if cs.active_fee_consent(db, user.id, config, now) is None:
        return stop("FEE_TERMS_REQUIRED")           # the member has not accepted the fee and its limit
    if "day_count" not in facts:                    # a caller outside run_cycle
        facts["day_total"], facts["day_count"] = day_usage(db, now)
    if amount < cs.crypto_minimum(config=config):
        return stop("BELOW_MINIMUM")
    if amount > money(config.max_single_payout_usd):
        return stop("EXCEEDS_SINGLE_LIMIT")
    if (facts["day_count"] >= int(config.max_daily_payout_count)
            or money(facts["day_total"] + amount) > money(config.max_daily_payout_usd)):
        return stop("DAILY_LIMIT_REACHED")

    # Ask the provider about THIS payout (its fee for this amount, and the
    # address). Nothing is reserved yet and no lock is held while waiting.
    wallet = cs.wallet_state(user, now, config=config)
    target, target_currency, approval_id = str(wallet.address), str(wallet.currency), wallet.approval_id
    db.commit()
    try:
        estimate = Decimal(str(provider.network_fee(target_currency, amount)))
        if not estimate.is_finite() or estimate < 0:
            raise ValueError("unusable fee estimate")
    except Exception:  # noqa: BLE001 - no estimate: the member's limit cannot be checked
        logger.warning("Cashout cycle: no network fee estimate for member %s's payout", user_id)
        return "FEE_ESTIMATE_UNAVAILABLE"
    validate = getattr(provider, "validate_address", None)
    if validate is not None:
        # The provider's own recommended first step.
        try:
            accepted = bool(validate(target, target_currency))
        except Exception:  # noqa: BLE001 - no answer: do not send to an unchecked address
            logger.warning("Cashout cycle: the provider could not validate member %s's address", user_id)
            return "ADDRESS_CHECK_UNAVAILABLE"
        if not accepted:
            return "PROVIDER_ADDRESS_INVALID"
    user = db.query(User).filter(User.id == user_id).with_for_update().one()
    wallet = cs.wallet_state(user, now, config=config)
    if ((wallet.address, wallet.currency, wallet.approval_id) != (target, target_currency, approval_id)
            or not wallet.payable or cs.active_pooled_cashout(db, user.id)):
        db.rollback()
        return "WALLET_CHANGED"
    rows = [row for row in cs.available_rows(db, user.id) if int(row.id) == commission_id]
    if cs.rows_total(rows) != amount:
        db.rollback()
        return "BALANCE_CHANGED"                    # paid, reserved or cancelled meanwhile
    consent = cs.active_fee_consent(db, user.id, config, now)
    if consent is None:
        return stop("FEE_TERMS_REQUIRED")
    problem, plan = cs.beneficiary_fee_plan(config, consent, amount, estimate)
    if problem is not None:
        return stop(problem)
    send = plan["amount_sent"]
    expected = amount - estimate
    adjusted = plan["fee_estimate_adjusted"]        # the estimate raised by the safety margin
    # Whether the provider's minimum applies before or after its fee is not
    # documented; both checks below assume the stricter reading.
    if amount - adjusted < facts["minimum"]:
        return stop("BELOW_PROVIDER_MINIMUM")
    if facts["balance"] - money(config.provider_balance_reserve_usd) < amount + adjusted:
        return stop("INSUFFICIENT_PROVIDER_BALANCE")
    # Recording gate. From here until the reservation is committed this worker
    # holds the settings lock, so the count of payouts whose actual fee is not
    # verified yet (across ALL members) and the suspension are decided by one
    # worker at a time: two workers cannot both pass for different members.
    locked_config = payment_config.lock_settings(db)
    blocked = locked_config.fee_gate()
    if blocked is None and int(locked_config.version) != int(config.version):
        # Every figure above (the member's limit, the margin, the minimums, the
        # daily limits) was checked against `config`. The configuration has been
        # changed since, possibly changed AND approved again, so those checks say
        # nothing about the values now in force. Nothing is reserved; the next
        # cycle starts from the new configuration.
        blocked = "CONFIGURATION_CHANGED"
    blocked = blocked or cs.recording_gate(db, locked_config)
    if blocked is not None:
        return stop(blocked)
    intent_ref = commission_intent_reference(db, commission_id)
    cashout = cs.reserve(db, user, rows, method=cs.METHOD_CRYPTO, fee=Decimal("0.00"), intent_ref=intent_ref,
                         now=now, wallet=wallet.address, currency=wallet.currency, net=money(expected),
                         network_fee=money(estimate), network_fee_policy=config.network_fee_policy,
                         beneficiary_fee=plan, audit_extra={"settings_version": int(locked_config.version)},
                         commission_id=commission_id, wallet_approval_id=approval_id)
    if cashout is None:
        return "ALREADY_RESERVED"                   # another worker reserved this commission first
    cashout_id = int(cashout.id)

    # Committed intent. Re-check the CURRENT state immediately before provider I/O.
    user = db.query(User).filter(User.id == user_id).with_for_update().one()
    cashout = (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id)
               .with_for_update().one())
    # Under the settings lock, so a configuration change is either seen here (and
    # the reservation is released) or waits until this payout has been marked as
    # handed over: it can never slip in between this check and that mark.
    current = payment_config.lock_settings(db)
    blocker = None if engine_enabled(db, config=current) else "ENGINE_DISABLED"
    blocker = blocker or current.fee_gate()
    if blocker is None and int(current.version) != int(config.version):
        blocker = "CONFIGURATION_CHANGED"           # reserved under values that are no longer in force
    blocker = blocker or _blocker(db, user, now, current)
    if blocker is None:
        still = cs.active_fee_consent(db, user.id, current, now)
        if still is None or int(still.id) != int(cashout.fee_consent_id or 0):
            blocker = "FEE_TERMS_REQUIRED"          # withdrawn or replaced since it was reserved
    if blocker is None:
        # The payout goes only to the exact wallet approval it was reserved under.
        state = cs.wallet_state(user, now, config=current)
        if state.address != cashout.wallet_snapshot or state.approval_id != cashout.wallet_approval_id:
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
    platform_fault: Optional[str] = None
    result: Optional[dict] = None
    try:
        result = provider.create_payout(address=address, amount=send, currency=currency,
                                        external_id=intent_ref.split(":", 1)[1])
    except nowpayments.NowPaymentsError as exc:
        code = exc.status_code
        refused = code is not None and 400 <= code < 500 and code not in (408, 429)
        if refused and getattr(exc, "ip_refused", False):
            platform_fault = "PROVIDER_IP_NOT_WHITELISTED"
        elif refused and getattr(exc, "stage", None) == "auth":
            platform_fault = "PROVIDER_AUTH_FAILED"
        logger.warning("Cashout %s: provider create failed (status %s, stage %s, code %s)", cashout_id, code,
                       getattr(exc, "stage", None), getattr(exc, "code", None))
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
            _notify(db, cashout_id, "DELAYED")
            return "OUTCOME_UNKNOWN"
        db.commit()
        return "SUBMITTED"
    if refused and platform_fault is not None:
        # Nothing was created and the member did nothing wrong: not a failed
        # attempt of theirs (it must not count towards their retry limit).
        cs.release_reservation(db, cashout, status=CashoutStatus.CANCELLED.value, failure_code=platform_fault,
                               actor_id=None, now=now)
        db.commit()
        return platform_fault
    if refused:
        cs.release_reservation(db, cashout, status=CashoutStatus.FAILED.value, failure_code="PROVIDER_REFUSED",
                               actor_id=None, now=now)
        db.commit()
        _notify(db, cashout_id, "FAILED")
        return "PROVIDER_REFUSED"
    cashout.status = CashoutStatus.UNKNOWN.value
    cashout.failure_code = "PROVIDER_OUTCOME_UNKNOWN"
    cashout.processed_at = now
    db.commit()
    _notify(db, cashout_id, "DELAYED")
    return "OUTCOME_UNKNOWN"


# ---------------------------------------------------------------------------
# One cycle
# ---------------------------------------------------------------------------

def candidate_user_ids(db: Session, limit: int) -> list[int]:
    """Members who chose CRYPTO and have unreserved commission rows that may be paid."""
    from app.services.commission_payout_hold import payable_clause

    rows = (db.query(AffiliateCommission.user_id)
            .join(User, User.id == AffiliateCommission.user_id)
            .filter(User.cashout_method == cs.METHOD_CRYPTO,
                    AffiliateCommission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PENDING]),
                    AffiliateCommission.payout_reference.is_(None),
                    payable_clause())
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
    config = payment_config.load(db)                # reconciliation may have suspended payouts
    blocked = config.fee_gate() or cs.recording_gate(db, config)
    db.rollback()
    if blocked is not None:
        report["stopped"] = blocked                 # fail closed: nothing new is reserved or sent
        return report
    user_ids = candidate_user_ids(db, int(limit or settings.CASHOUT_ENGINE_BATCH_LIMIT))
    db.rollback()
    if not user_ids:
        return report
    currency = config.crypto_payout_currency
    check_session = getattr(provider, "check_session", None)
    if check_session is not None:
        try:
            check_session()
        except Exception:  # noqa: BLE001 - a payout cannot be created without the login
            logger.warning("Cashout cycle stopped: the provider refused the payout login")
            report["stopped"] = "PROVIDER_AUTH_FAILED"
            return report
    problem = verify_payout_asset(provider, currency)
    if problem is not None:
        logger.warning("Cashout cycle stopped: payout asset not verified (%s)", problem)
        report["stopped"] = problem                 # fail closed: never send an unverified token
        return report
    try:
        # The network fee is asked for each payout, for its own amount (process_member).
        facts = {"balance": Decimal(provider.balance(currency)), "minimum": Decimal(provider.minimum(currency))}
    except Exception:  # noqa: BLE001 - without the provider's facts nothing is reserved
        logger.warning("Cashout cycle stopped: provider balance / minimum could not be read")
        report["stopped"] = "PROVIDER_FACTS_UNAVAILABLE"
        return report
    facts["day_total"], facts["day_count"] = day_usage(db, now)
    db.rollback()
    results: Counter = Counter()
    stop_all = ("PROVIDER_AUTH_FAILED", "PROVIDER_IP_NOT_WHITELISTED", "PAYOUTS_SUSPENDED",
                "FEE_RECONCILIATION_PENDING", "CONFIGURATION_CHANGED")
    for user_id in user_ids:
        # Each available commission of the member gets its own payout, one call each.
        for attempt in range(PAYOUTS_PER_MEMBER_PER_CYCLE):
            try:
                outcome = process_member(db, user_id, provider, facts=facts, config=config, now=now)
            except Exception:  # noqa: BLE001 - one member's failure never stops the others
                db.rollback()
                logger.exception("Cashout cycle: member %s failed", user_id)
                outcome = "ERROR"
            if attempt and outcome not in ("SUBMITTED", "OUTCOME_UNKNOWN", "PROVIDER_REFUSED", "ERROR") \
                    and outcome not in stop_all:
                # The member's first outcome is reported; after a payout, what stops the
                # next one (nothing left, a limit) is left for the next cycle.
                break
            results[outcome] += 1
            if outcome in ("SUBMITTED", "OUTCOME_UNKNOWN"):
                # Assume the money left (or may have): never count it for the next payout.
                sent = (db.query(AffiliateCashoutRequest.gross_amount, AffiliateCashoutRequest.network_fee_estimate)
                        .filter(AffiliateCashoutRequest.user_id == user_id)
                        .order_by(AffiliateCashoutRequest.id.desc()).first())
                gross = money(sent[0] if sent else 0)
                facts["balance"] -= gross + Decimal(str(sent[1] if sent and sent[1] is not None else 0))
                facts["day_total"] = money(facts["day_total"] + gross)
                facts["day_count"] += 1
                db.rollback()
            if outcome != "SUBMITTED":
                break                               # nothing more for this member in this cycle
        if outcome in stop_all:
            report["stopped"] = outcome             # the same refusal awaits every other member
            break
    report["members"] = dict(results)
    return report


# How many individual payouts one member may be handed in one cycle (each is one
# commission). A safety bound only; the next cycle continues with the rest.
PAYOUTS_PER_MEMBER_PER_CYCLE = 25

# USDT on BNB Smart Chain (BEP20), chain id 56. The ONLY asset automatic payouts
# send. The contract is compared with what the provider itself reports for its
# payout currency (GET /v1/full-currencies: network, smart_contract) before any
# payout of a cycle; anything else stops the cycle.
PAYOUT_ASSET = {"usdtbsc": {"network": "bsc", "chain_id": 56,
                            "contract": "0x55d398326f99059ff775485246999027b3197955"}}


def verify_payout_asset(provider, currency: str) -> Optional[str]:
    """None when the provider's payout currency is exactly USDT BEP20 (chain 56)."""
    expected = PAYOUT_ASSET.get(str(currency or "").lower())
    if expected is None:
        return "PAYOUT_ASSET_NOT_SUPPORTED"
    read = getattr(provider, "currency_details", None)
    if read is None:
        return None                                 # a test double without the lookup
    try:
        details = read(currency) or {}
    except Exception:  # noqa: BLE001 - not verified is not sent
        return "PAYOUT_ASSET_UNVERIFIED"
    network = str(details.get("network") or "").strip().lower()
    contract = str(details.get("smart_contract") or "").strip().lower()
    if network != expected["network"] or contract != expected["contract"]:
        return "PAYOUT_ASSET_MISMATCH"
    return None


# ---------------------------------------------------------------------------
# Liability vs provider balance, and what does not add up
# ---------------------------------------------------------------------------

def commission_payout_reconciliation(db: Session, *, limit: int = 200) -> dict:
    """Each NEW_V2 commission against its own payout attempts. Read-only.

    Problems listed:
      PAID_WITHOUT_PAYOUT      commission PAID, no completed payout of it
      PAYOUT_NOT_POSTED        completed payout, commission not PAID
      AMOUNT_MISMATCH          completed payout amount differs from the commission
      COMPLETED_WITHOUT_HASH   completed payout without a transaction hash
      RESERVED_WITHOUT_PAYOUT  commission reserved, no open payout of it"""
    from app.models.affiliate import PayoutWalletApproval  # noqa: F401  (model registry)

    commissions = (db.query(AffiliateCommission)
                   .filter(AffiliateCommission.business_model_version == "NEW_V2")
                   .order_by(AffiliateCommission.id.desc()).limit(limit).all())
    ids = [int(c.id) for c in commissions]
    attempts: dict = {}
    for row in (db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.commission_id.in_(ids or [0]))
                .order_by(AffiliateCashoutRequest.id.asc()).all()):
        attempts.setdefault(int(row.commission_id), []).append(row)
    items, problems = [], []
    for c in commissions:
        rows = attempts.get(int(c.id), [])
        completed = [r for r in rows if r.status == CashoutStatus.COMPLETED.value]
        open_rows = [r for r in rows if r.status in ACTIVE_CASHOUT_STATUSES]
        found = []
        status = c.status.value if hasattr(c.status, "value") else str(c.status)
        if status == "PAID" and rows and not completed:
            found.append("PAID_WITHOUT_PAYOUT")     # it had individual attempts, none of them completed
        if completed and status != "PAID":
            found.append("PAYOUT_NOT_POSTED")
        if completed and money(completed[-1].gross_amount) != money(c.commission_amount):
            found.append("AMOUNT_MISMATCH")
        if completed and not completed[-1].tx_hash:
            found.append("COMPLETED_WITHOUT_HASH")
        if (status == "APPROVED" and str(c.payout_reference or "").startswith("intent:c") and not open_rows):
            found.append("RESERVED_WITHOUT_PAYOUT")
        item = {"commission_id": c.id, "user_id": c.user_id, "amount": f"{money(c.commission_amount):.2f}",
                "status": status, "reserved": bool(c.payout_reference) and status == "APPROVED",
                "attempts": [{"cashout_id": r.id, "status": r.status, "failure_code": r.failure_code,
                              "wallet_approval_id": r.wallet_approval_id, "tx_hash": r.tx_hash,
                              "requested_at": r.requested_at.isoformat() if r.requested_at else None}
                             for r in rows],
                "problems": found}
        items.append(item)
        if found:
            problems.append(item)
    return {"items": items, "problems": problems, "checked": len(items)}


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
        if (cashout.status == CashoutStatus.UNKNOWN.value
                and cashout.failure_code == "PROVIDER_FAILED_NOT_FINAL"):
            add("PROVIDER_FAILED_NOT_FINAL", "critical",
                f"Cashout #{cashout.id}: the provider reports the payout as failed. That status is not final "
                "(the provider may still send it). Ask the provider's support whether it will be processed "
                "before recording it as not sent; do not create another payout for it.",
                cashout_id=cashout.id, user_id=cashout.user_id)
        elif (cashout.status == CashoutStatus.UNKNOWN.value
              and str(cashout.failure_code or "").endswith("_MISMATCH")):
            add("PROVIDER_EVIDENCE_MISMATCH", "critical",
                f"Cashout #{cashout.id}: the payout the provider reports does not match this cashout "
                f"({cashout.failure_code}). Check the provider by hand.",
                cashout_id=cashout.id, user_id=cashout.user_id)
        elif cashout.status == CashoutStatus.UNKNOWN.value:
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
    # A completed payout whose fee MyHigh5 paid is not reconciled until that fee is in the books.
    fees = cs.network_fee_summary(db)
    for row in fees["not_recorded"]:
        items.append({"type": "NETWORK_FEE_NOT_RECORDED", "severity": "warning",
                      "message": f"Cashout #{row['cashout_id']} is completed but the network fee MyHigh5 paid for it "
                                 "is not recorded: the treasury account is overstated by that fee until it is.",
                      "cashout_id": row["cashout_id"], "user_id": row["user_id"]})
    if fees["not_recorded_count"] > len(fees["not_recorded"]):
        items.append({"type": "NETWORK_FEE_NOT_RECORDED", "severity": "warning",
                      "message": f"{fees['not_recorded_count'] - len(fees['not_recorded'])} more completed payouts "
                                 "have no network fee recorded."})
    # Beneficiary-paid payouts: the actual fee is data, not a journal entry, but a
    # payout is not reconciled until it is known and adds up.
    member_fees = cs.member_fee_summary(db)
    flag_text = {
        cs.FLAG_MODE_MISMATCH: "the provider charged its network fee to the MyHigh5 balance instead of taking it "
                               "out of the payout: the treasury account is overstated by that fee and no entry was "
                               "posted for it",
        cs.FLAG_AMOUNT_MISMATCH: "the provider reports a larger amount than the one it was asked to send",
        cs.FLAG_CAP_EXCEEDED: "the network fee the provider took is higher than the limit the member accepted",
    }
    for row in member_fees["flagged"]:
        items.append({"type": row["flag"], "severity": "critical",
                      "message": f"Cashout #{row['cashout_id']}: {flag_text.get(row['flag'], row['flag'])}. "
                                 "New payouts are stopped until the provider's fee behaviour is confirmed again."
                                 + ("" if row.get("review") == cs.REVIEW_DONE
                                    else " Not reviewed yet (Flagged Payout Review)."),
                      "cashout_id": row["cashout_id"], "user_id": row["user_id"], "review": row.get("review")})
    suspension = payment_config.suspension_view(db)
    if suspension is not None:
        items.insert(0, {"type": "PAYOUTS_SUSPENDED", "severity": "critical",
                         "message": f"Crypto payouts are suspended: {suspension['message']} No payout is created "
                                    "until an administrator has reviewed it and reactivated payouts explicitly.",
                         "cashout_id": suspension["cashout_id"]})
    for row in member_fees["not_verified"]:
        items.append({"type": "MEMBER_FEE_NOT_VERIFIED", "severity": "warning",
                      "message": f"Cashout #{row['cashout_id']}: an actual network fee is recorded but was not "
                                 "verified (who bore it and the amount received were not confirmed against "
                                 "evidence). It does not count as reconciled.",
                      "cashout_id": row["cashout_id"], "user_id": row["user_id"]})
    for row in member_fees["not_recorded"]:
        items.append({"type": "MEMBER_FEE_NOT_RECORDED", "severity": "warning",
                      "message": f"Cashout #{row['cashout_id']} is completed but the network fee the provider took "
                                 "from it is not recorded: what the member received is not known yet.",
                      "cashout_id": row["cashout_id"], "user_id": row["user_id"]})
    if member_fees["not_recorded_count"] > len(member_fees["not_recorded"]):
        items.append({"type": "MEMBER_FEE_NOT_RECORDED", "severity": "warning",
                      "message": f"{member_fees['not_recorded_count'] - len(member_fees['not_recorded'])} more "
                                 "completed payouts have no actual network fee recorded."})
    gate = config.fee_gate()
    return {
        "beneficiary_fees": member_fees,
        "payout_suspension": suspension,
        "recording_gate": {"limit": int(config.max_unreconciled_payouts), **member_fees["exposure"],
                           "blocked": member_fees["exposure"]["total"] > int(config.max_unreconciled_payouts)},
        "network_fee_gate": ({"code": gate, "message": payment_config.FEE_GATE_MESSAGES[gate]}
                             if gate is not None else None),
        "owed": {k: float(v) for k, v in owed.items()},
        "owed_total": float(unpaid),
        # Part of owed_total: historical commissions held from every payout until reviewed.
        "held_for_review": float(total(AffiliateCommission.status.in_((CommissionStatus.PENDING, CommissionStatus.APPROVED)),
                                       held_clause())),
        "owed_to_crypto_cashout_members": float(crypto_members),
        "open_cashouts": {str(k): int(v) for k, v in open_by_state.items()},
        "provider_balance_state": provider_state,
        "provider_balance": float(balance) if balance is not None else None,
        "provider_covers_crypto_members": (balance >= crypto_members) if balance is not None else None,
        "last_24_hours": {"crypto_payout_amount": float(day_total), "crypto_payout_count": day_count,
                          "amount_limit": float(config.max_daily_payout_usd),
                          "count_limit": int(config.max_daily_payout_count)},
        "discrepancies": items,
        "network_fees": fees,
        "engine": engine_status(db),
    }


# ---------------------------------------------------------------------------
# Why crypto payouts are (not) being created: one answer for the Admin Panel
# ---------------------------------------------------------------------------

def crypto_payout_status(db: Session) -> dict:
    """EVERYTHING that currently stops a crypto payout from being created, each
    with the section of the Crypto Cashout page it belongs to and what an
    administrator has to do about it. Read-only: it calls nobody and changes
    nothing. The engine itself decides with payment_config.fee_gate() and
    cashout_service.recording_gate(); this only explains them, and lists every
    reason instead of the first."""
    from dataclasses import replace

    config = payment_config.load(db)
    credentials = payment_config.resolve_credentials(db, config)
    exposure = cs.reconciliation_exposure(db)
    limit = int(config.max_unreconciled_payouts)
    suspension = payment_config.suspension_view(db)
    blockers: list[dict] = []
    missing: list[dict] = []

    def block(code: str, section: str, message: str, action: str, *, temporary: bool = False) -> None:
        blockers.append({"code": code, "section": section, "message": message, "action": action,
                         "temporary": temporary})

    def need(field: str, section: str) -> None:
        missing.append({"field": field, "label": payment_config.FIELDS[field].label, "section": section})

    messages = payment_config.FEE_GATE_MESSAGES
    if suspension is not None:
        block("PAYOUTS_SUSPENDED", "suspension", f"Crypto payouts are suspended: {suspension['message']}",
              "Review the flagged payout, verify its actual network fee, restore the settings below, then "
              "reactivate explicitly in section E.")
    if not payment_config.crypto_master_switch():
        block("SERVER_SWITCH_OFF", "activation", "The server master switch CRYPTO_AUTO_PAYOUT_ENABLED is off.",
              "It is set on the server by the operator and cannot be changed here.")
    if not config.provider_enabled:
        block("PROVIDER_DISABLED", "provider", "The payment provider is switched off.",
              "Switch it on in NOWPayments Configuration.")
    if not credentials.payout_ready:
        block("PAYOUT_CREDENTIALS_MISSING", "provider",
              "Payout credentials are incomplete: " + ", ".join(credentials.payout_missing) + ".",
              "Configure them in NOWPayments Configuration and run the connection test.")
    if config.network_fee_policy != payment_config.FEE_MEMBER_PAYS:
        need("network_fee_policy", "provider")
        block("FEE_POLICY_NOT_BENEFICIARY_PAID", "provider", messages["FEE_POLICY_NOT_BENEFICIARY_PAID"],
              "Select MEMBER_PAYS in section A.")
    if config.provider_fee_mode != payment_config.FEE_MODE_DEDUCTED:
        need("provider_fee_mode", "provider")
        block("PROVIDER_FEE_MODE_UNVERIFIED", "provider", messages["PROVIDER_FEE_MODE_UNVERIFIED"],
              "Confirm with the provider that it takes its network fee out of the amount sent. Only then select "
              "DEDUCTED_BY_PROVIDER in section A and type the confirmation.")
    if Decimal(config.member_fee_cap_percent) <= 0 and Decimal(config.member_fee_cap_usd) <= 0:
        need("member_fee_cap_percent", "fee_limits")
        need("member_fee_cap_usd", "fee_limits")
        block("FEE_LIMITS_NOT_CONFIGURED", "fee_limits", messages["FEE_LIMITS_NOT_CONFIGURED"],
              "Set at least one member network fee limit in section B. The value is the business owner's decision.")
    if config.fee_estimate_margin_percent is None:
        need("fee_estimate_margin_percent", "safety")
        block("FEE_SAFETY_MARGIN_NOT_SET", "safety", messages["FEE_SAFETY_MARGIN_NOT_SET"],
              "Set the safety margin in section C. The value is the business owner's decision.")
    if not config.fee_terms_approved:
        block("FEE_LIMITS_NOT_APPROVED", "activation", messages["FEE_LIMITS_NOT_APPROVED"],
              "Save the settings of sections A to C first, then approve them in section D in a change of its own.")
    if not config.crypto_cashout_enabled:
        block("CRYPTO_CASHOUT_DISABLED", "activation", "Crypto Cashout is switched off.",
              "Switch it on in section D.")
    if not config.crypto_auto_payout_enabled:
        block("AUTOMATIC_PAYOUTS_OFF", "activation", "Automatic payouts are switched off.",
              "Switch them on in section D only when nothing else is listed here. It needs a successful "
              "connection test in the last 24 hours and the typed confirmation.")
    if exposure["total"] > limit:
        block("FEE_RECONCILIATION_PENDING", "safety", messages["FEE_RECONCILIATION_PENDING"],
              "Record the actual network fee of the earlier payout as verified in Cashout Transactions. No "
              "reactivation is needed.", temporary=True)

    approvable = replace(config, fee_terms_approved=True).fee_rules_gate()
    receiver, company = payment_config.receiver_fee_payer_values(), payment_config.company_fee_payer_values()
    meaning = payment_config.payout_amount_semantics()
    return {
        "can_create_payouts": not blockers,
        "configuration_version": int(config.version),
        "blockers": blockers,
        "missing_settings": missing,
        "provider_semantics": {
            "fee_mode": config.provider_fee_mode,
            "fee_mode_confirmed": config.provider_fee_mode == payment_config.FEE_MODE_DEDUCTED,
            # Set on the server once the provider has confirmed them; never assumed.
            "receiver_fee_values_confirmed": bool(receiver),
            "company_fee_values_confirmed": bool(company),
            "amount_meaning": meaning or None,
            # Only with all of these does the provider's own report verify a payout's actual fee.
            "automatic_verification": bool(receiver and meaning),
        },
        "approval": {"approved": bool(config.fee_terms_approved), "can_approve": approvable is None,
                     "blocked_by": ({"code": approvable, "message": messages[approvable]}
                                    if approvable is not None else None)},
        "suspension": suspension,
        "recording_gate": {"limit": limit, **exposure, "blocked": exposure["total"] > limit},
        "flagged_payouts": {"pending_review": cs.unreviewed_flagged_count(db)},
        "switches": {"server": payment_config.crypto_master_switch(), "provider": bool(config.provider_enabled),
                     "crypto_cashout": bool(config.crypto_cashout_enabled),
                     "automatic_payouts": bool(config.crypto_auto_payout_enabled),
                     "credentials_ready": credentials.payout_ready},
    }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

_ACTIVE_SCHEDULER: Optional["CashoutScheduler"] = None


def request_cycle() -> bool:
    """Ask the running scheduler for a cycle NOW (a commission became payable, a
    wallet was approved). Safe from any thread; never raises. The database is
    the queue: a request that is lost (no scheduler, restart) changes nothing,
    the next periodic tick finds the same payable commissions."""
    scheduler = _ACTIVE_SCHEDULER
    if scheduler is None or scheduler._wake is None or scheduler._loop_ref is None:
        return False
    try:
        scheduler._loop_ref.call_soon_threadsafe(scheduler._wake.set)
        return True
    except Exception:  # noqa: BLE001 - the periodic tick remains
        return False


class CashoutScheduler:
    """Runs run_cycle periodically, and promptly when request_cycle() is called.
    Every tick also queues the "commission earned, wallet missing" emails
    (payout_notifications.sweep), whatever the payout switches. While the engine
    is off the payout part returns before opening a database session."""

    # A requested cycle waits this long, so the transaction that asked for it
    # (a payment confirmation, a wallet approval) is committed first.
    REQUEST_DELAY_SECONDS = 3

    def __init__(self, check_interval_seconds: Optional[int] = None):
        # Used until the configured interval can be read (and while the server switch is off).
        self.check_interval = int(check_interval_seconds or 900)
        self.running = False
        self._task = None
        self._wake: Optional[asyncio.Event] = None
        self._loop_ref = None

    async def start(self):
        global _ACTIVE_SCHEDULER
        if self.running:
            return
        self.running = True
        self._wake = asyncio.Event()
        self._loop_ref = asyncio.get_running_loop()
        _ACTIVE_SCHEDULER = self
        self._task = asyncio.create_task(self._loop())
        logger.info("Cashout scheduler started (server master switch: %s)", payment_config.crypto_master_switch())

    async def stop(self):
        global _ACTIVE_SCHEDULER
        self.running = False
        if _ACTIVE_SCHEDULER is self:
            _ACTIVE_SCHEDULER = None
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
            await self._wait(await self._interval())

    async def _wait(self, seconds: int) -> None:
        """Sleep until the next tick, or until request_cycle() wakes the loop."""
        if self._wake is None:
            await asyncio.sleep(seconds)
            return
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return
        self._wake.clear()
        await asyncio.sleep(self.REQUEST_DELAY_SECONDS)

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
        try:
            await asyncio.to_thread(self._sweep_notifications)
        except Exception:  # noqa: BLE001 - emails never stop payouts
            logger.exception("Commission notification sweep failed")
        if not payment_config.crypto_master_switch():
            return {"enabled": False}
        return await asyncio.to_thread(self._run_once)

    @staticmethod
    def _sweep_notifications() -> int:
        from app.db.session import SessionLocal
        from app.services import payout_notifications

        db = SessionLocal()
        try:
            return payout_notifications.sweep(db)
        finally:
            db.close()

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
