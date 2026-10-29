"""SoncoPay customer payments: checkout, webhook verification, status reading
and reconciliation. Built from the official API v1 documentation
(soncopay.com/developers) and the official SDK 2.11.2 webhook verifier.

The rules, in one place:

  * A deposit's gateway is fixed when it is created (deposits.payment_provider)
    and never changes. A SoncoPay deposit is only ever read, confirmed or
    reconciled here; NOWPayments code refuses it, and nothing here touches a
    NOWPayments deposit. Only deposits whose provider is "soncopay" are matched.
  * A deposit also keeps its environment (provider_environment, test | live):
    it is always read with THAT environment's key, and a payment whose livemode
    does not match is refused. Test and Live never mix.
  * Nothing is credited from a browser redirect or from a webhook body alone.
    A webhook is verified (timestamped signature over the raw body, 5 minute
    window, the delivery id processed at most once) and is then only a reason
    to READ the payment from SoncoPay (GET /v1/payments/{id}); the deposit is
    changed from that authoritative answer, under a row lock.
  * The provider's payment must match the deposit: payment id, order id,
    amount, currency and livemode. Any difference refuses the whole answer.
  * A paid payment goes through the SAME idempotent confirmation as
    NOWPayments (commission_distribution.process_payment_validation): a
    deposit already validated is never validated again, so membership, KYC
    and commissions are created once whatever arrives twice.
  * Status mapping (SoncoPay -> deposit):
        new, waiting, confirming, underpaid  -> pending (no benefit)
        paid                                 -> validated (late payments too)
        partially_paid                       -> partially_paid (no benefit)
        expired                              -> expired
        failed                               -> failed
        refunded                             -> the existing full-refund reversal
        partially_refunded                   -> refused for manual reconciliation
                                                (as for NOWPayments)
    An unknown status changes nothing.
  * Owner decision 2026-10-29: USDT on BNB Smart Chain (BEP20) only. Every
    payment is created with that method chosen (method crypto, asset USDT,
    network BSC), and a paid payment in any other asset or network (the
    payer changed it on the payment page, or SoncoPay switched a wrong-asset
    payment to what arrived) is never confirmed: the deposit stays pending
    with provider_status paid_other_asset for an administrator.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.checkout_gateway import SoncoPayWebhookEvent
from app.models.payment import Deposit, DepositStatus
from app.services import soncopay_settings
from app.services.financial_integrity import FinancialIntegrityError, money, normalize_fiat_currency
from app.services.soncopay_client import SoncoPayClient, SoncoPayError

logger = logging.getLogger(__name__)

PROVIDER = "soncopay"
NOWPAYMENTS = "nowpayments"
# The only asset and network a member pays in (documented: method crypto, asset USDT, network BSC).
PAY_METHOD, PAY_ASSET, PAY_NETWORK = "crypto", "USDT", "BSC"
PAY_LABEL = "USDT on BNB Smart Chain (BEP20)"
OTHER_ASSET_STATUS = "paid_other_asset"

STATUS_TO_DEPOSIT = {
    "new": DepositStatus.PENDING,
    "waiting": DepositStatus.PENDING,
    "confirming": DepositStatus.PENDING,
    "underpaid": DepositStatus.PENDING,
    "paid": DepositStatus.VALIDATED,
    "partially_paid": DepositStatus.PARTIALLY_PAID,
    "expired": DepositStatus.EXPIRED,
    "failed": DepositStatus.FAILED,
}

# What the member is shown (payment dialog), from the provider's own status.
MEMBER_STATE = {
    "new": "pending", "waiting": "pending", "confirming": "awaiting_confirmation", "paid": "paid",
    "underpaid": "partial", "partially_paid": "partial", "expired": "expired", "failed": "failed",
    "refunded": "refunded", "partially_refunded": "refunded", OTHER_ASSET_STATUS: "awaiting_confirmation",
}

# Webhook
SIGNATURE_HEADER = "x-soncopay-signature"
SIGNATURE_V2_HEADER = "x-soncopay-signature-v2"
DELIVERY_HEADER = "x-soncopay-delivery-id"
TOLERANCE_SECONDS = 300
MAX_WEBHOOK_BYTES = 64 * 1024


class CheckoutClosed(SoncoPayError):
    """SoncoPay may not open a NEW payment now (switched off, other environment, key missing)."""

    def __init__(self):
        super().__init__("SoncoPay is not taking new payments", stage="create")


def is_soncopay(deposit: Any) -> bool:
    return str(getattr(deposit, "payment_provider", "") or "") == PROVIDER


def provider_of(deposit: Any) -> str:
    return PROVIDER if is_soncopay(deposit) else NOWPAYMENTS


def client_for(db: Session, environment: Optional[str]) -> SoncoPayClient:
    """The client of ONE environment, with that environment's key (never the other's)."""
    key = soncopay_settings.api_key(db, environment or "")
    if not key:
        raise SoncoPayError(f"The SoncoPay {str(environment or '?').title()} API key is not saved", stage="config")
    return SoncoPayClient(key, environment)


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


# ---------------------------------------------------------------------------
# Identity: the provider's payment must be THIS deposit
# ---------------------------------------------------------------------------

def check_identity(deposit: Deposit, payment: Mapping[str, Any]) -> None:
    """Raise FinancialIntegrityError unless the SoncoPay payment is this deposit's payment."""
    if not is_soncopay(deposit):
        raise FinancialIntegrityError("Not a SoncoPay deposit")
    payment_id = str(payment.get("id") or "")
    if not payment_id.startswith("pay_"):
        raise FinancialIntegrityError("SoncoPay answer has no payment id")
    if deposit.external_payment_id and payment_id != str(deposit.external_payment_id):
        raise FinancialIntegrityError("SoncoPay payment id does not match the deposit")
    if str(payment.get("order_id") or "") != str(deposit.order_id or ""):
        raise FinancialIntegrityError("SoncoPay order_id does not match the deposit")
    if payment.get("amount") is None or money(payment.get("amount")) != money(deposit.amount):
        raise FinancialIntegrityError("SoncoPay amount does not match the deposit")
    if normalize_fiat_currency(payment.get("currency")) != normalize_fiat_currency(deposit.currency or "USD"):
        raise FinancialIntegrityError("SoncoPay currency does not match the deposit")
    livemode = payment.get("livemode")
    if not isinstance(livemode, bool) or livemode != (deposit.provider_environment == "live"):
        raise FinancialIntegrityError("SoncoPay test/live mode does not match the deposit")


# ---------------------------------------------------------------------------
# Applying the provider's answer (caller holds the deposit row lock; no commit)
# ---------------------------------------------------------------------------

def apply_payment(db: Session, deposit: Deposit, payment: Mapping[str, Any]) -> bool:
    """Apply one authoritative SoncoPay payment to its deposit. False when the
    confirmation (commissions/accounting) failed: the caller rolls back.
    Raises FinancialIntegrityError when the payment is not this deposit's."""
    check_identity(deposit, payment)
    status = str(payment.get("status") or "").strip().lower()
    if not deposit.external_payment_id:
        deposit.external_payment_id = str(payment["id"])
    deposit.provider_status = status[:40] or None
    expires = _parse_time(payment.get("expires_at"))
    if expires is not None:
        deposit.provider_expires_at = expires
    if payment.get("checkout_url") and not deposit.provider_checkout_url:
        deposit.provider_checkout_url = str(payment["checkout_url"])

    if status == "partially_refunded":
        # A Referral Pool deposit with units: this SIGNED event's cumulative refunded amount
        # refunds exactly the units it covers (P7). Anything else: reconcile manually, exactly like
        # a NOWPayments partial refund. Never treated as a full refund.
        from app.services import referral_pool_units

        refunded = payment.get("refunded_amount")
        if refunded is not None and referral_pool_units.on_provider_refund(
                db, deposit, refunded, source="soncopay") is not None:
            return True
        raise FinancialIntegrityError("Partial refunds are not supported; reconcile this provider event manually")
    if status == "refunded":
        from app.services.financial_reversal import reverse_provider_refund

        # A full refund is reversed once by the existing path (which also refuses an amount
        # that is not the whole deposit).
        refunded = payment.get("refunded_amount")
        return reverse_provider_refund(db, deposit, {"refund_amount": refunded if refunded is not None
                                                     else payment.get("amount")}, defer_commit=True)

    if deposit.status == DepositStatus.VALIDATED:
        return True                                  # never confirmed twice
    from app.services.financial_reversal import is_reversed_deposit

    if is_reversed_deposit(deposit):
        logger.warning("Deposit %s was reversed; SoncoPay status %s ignored", deposit.id, status)
        return True

    target = STATUS_TO_DEPOSIT.get(status)
    if target is None:
        logger.warning("Deposit %s: unknown SoncoPay status %r, nothing changed", deposit.id, status[:40])
        return True
    if target == DepositStatus.VALIDATED and not paid_in_usdt_bsc(payment):
        deposit.provider_status = OTHER_ASSET_STATUS
        logger.error("Deposit %s: SoncoPay reports it paid in %s on %s, not USDT on BSC; not confirmed",
                     deposit.id, str(payment.get("asset") or "?")[:12], str(payment.get("network") or "?")[:20])
        return True
    if target == DepositStatus.VALIDATED:
        deposit.status = DepositStatus.VALIDATED
        deposit.validated_at = datetime.utcnow()
        if payment.get("tx_hash"):
            deposit.tx_hash = str(payment["tx_hash"])[:255]
        if payment.get("late"):
            logger.info("Deposit %s paid after its expiry (SoncoPay late payment)", deposit.id)
        from app.services.commission_distribution import process_payment_validation

        return bool(process_payment_validation(db, deposit, defer_commit=True))
    if target != deposit.status:
        deposit.status = target
        if target == DepositStatus.EXPIRED:
            from app.services.payment_scheduler import _release_pool_seat_for_deposit

            _release_pool_seat_for_deposit(db, deposit.id)
    return True


def paid_in_usdt_bsc(payment: Mapping[str, Any]) -> bool:
    """The payment was made in USDT on BSC: its asset and network say so (both fields are part of
    the documented payment object, and become those of the asset received when SoncoPay switches a
    wrong-asset payment). A missing field is not USDT on BSC."""
    return (str(payment.get("asset") or "").strip().upper() == PAY_ASSET
            and str(payment.get("network") or "").strip().upper() == PAY_NETWORK)


def status_payload(deposit: Deposit) -> Dict[str, Any]:
    """What a member's payment page shows. Never a key, a secret or the provider's raw answer."""
    word = str(deposit.provider_status or "")
    state = MEMBER_STATE.get(word, "paid" if deposit.status == DepositStatus.VALIDATED else "pending")
    if deposit.status == DepositStatus.VALIDATED:
        state = "paid"
    return {
        "deposit_id": deposit.id,
        "provider": PROVIDER,
        "status": deposit.status.value,
        "payment_status": word or deposit.status.value,
        "payment_state": state,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
        "order_id": deposit.order_id,
        "payment_id": deposit.external_payment_id,
        "checkout_url": deposit.provider_checkout_url,
        "invoice_url": deposit.provider_checkout_url,
        "expires_at": deposit.provider_expires_at.isoformat() if deposit.provider_expires_at else None,
        "pay_address": None,
        "pay_amount": None,
        "pay_currency": None,
        "price_amount": float(deposit.amount) if deposit.amount else 0,
        "price_currency": (deposit.currency or "usd").lower(),
        "tx_hash": deposit.tx_hash,
    }


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def return_url(deposit_id: int) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/wallet?payment=soncopay&deposit={int(deposit_id)}"


async def create_checkout(db: Session, deposit_id: int, *, description: str) -> Deposit:
    """Create (or, for the same order_id, find again) the SoncoPay payment of a
    SoncoPay deposit and attach it. No transaction is held while SoncoPay
    answers. Raises SoncoPayError or FinancialIntegrityError; the caller marks
    the deposit failed."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).one()
    if not is_soncopay(deposit):
        raise FinancialIntegrityError("Not a SoncoPay deposit")
    environment, order_id = deposit.provider_environment, str(deposit.order_id)
    if soncopay_settings.checkout_environment(db) != environment:
        # SoncoPay was switched off (or moved to the other environment, or lost its key) since the
        # deposit was written: no SoncoPay payment is opened. Checked right before the call.
        db.rollback()
        raise CheckoutClosed()
    amount, currency = f"{money(deposit.amount):.2f}", normalize_fiat_currency(deposit.currency or "USD")
    client = client_for(db, environment)
    db.rollback()
    request = dict(amount=amount, currency=currency, order_id=order_id,
                   description=description.encode("ascii", "replace").decode("ascii")[:200],
                   return_url=return_url(deposit_id), callback_url=soncopay_settings.webhook_url(),
                   metadata={"deposit_id": int(deposit_id)})
    try:
        payment = await client.create_payment(**request, method=PAY_METHOD, asset=PAY_ASSET, network=PAY_NETWORK)
    except SoncoPayError as exc:
        if exc.status_code != 422 or exc.code != "payer_required":
            raise
        # Documented: choosing the method by API needs every payer field the account requires, and
        # nothing is created when one is missing. The payer then chooses on SoncoPay's page; only a
        # payment made in USDT on BSC is ever confirmed (paid_in_usdt_bsc).
        logger.warning("Deposit %s: SoncoPay needs payer details to preselect USDT on BSC; "
                       "created without a preselected method", deposit_id)
        payment = await client.create_payment(**request)
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
    payment_id = str(payment.get("id") or "")
    holder = (db.query(Deposit.id).filter(Deposit.payment_provider == PROVIDER, Deposit.external_payment_id == payment_id,
                                          Deposit.id != deposit_id).first())
    if holder is not None:
        raise FinancialIntegrityError("SoncoPay returned a payment that another deposit already holds")
    # The payment just created must be this order, at this price, in this mode.
    check_identity(deposit, payment)
    if not str(payment.get("checkout_url") or "").startswith("https://"):
        raise FinancialIntegrityError("SoncoPay returned no secure checkout page")
    deposit.external_payment_id = payment_id
    deposit.provider_checkout_url = str(payment["checkout_url"])
    deposit.provider_status = str(payment.get("status") or "new")[:40]
    deposit.provider_expires_at = _parse_time(payment.get("expires_at"))
    if deposit.status == DepositStatus.FAILED and not deposit.validated_at:
        deposit.status = DepositStatus.PENDING        # a retried creation that now succeeded
    return deposit


# ---------------------------------------------------------------------------
# Reading the payment (member "check status", scheduler, webhook)
# ---------------------------------------------------------------------------

async def fetch_payment(db: Session, deposit: Deposit, payment_id: Optional[str] = None) -> Dict[str, Any]:
    """GET /v1/payments/{id} with the deposit's own environment key. Releases the transaction first.
    `payment_id` is used only when the deposit has none yet (its creation answer was lost);
    the answer is then bound to the deposit by check_identity (order id, amount, mode)."""
    payment_id = str(deposit.external_payment_id or payment_id or "")
    if not payment_id:
        raise SoncoPayError("This SoncoPay deposit has no payment yet", stage="read")
    client = client_for(db, deposit.provider_environment)
    db.rollback()
    return await client.retrieve_payment(payment_id)


def apply_locked(db: Session, deposit_id: int, payment: Mapping[str, Any]) -> Tuple[str, Deposit]:
    """Lock the deposit, apply the payment. No commit. Returns (outcome, deposit)."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().populate_existing().one()
    try:
        ok = apply_payment(db, deposit, payment)
    except FinancialIntegrityError:
        db.rollback()
        logger.error("SoncoPay answer for deposit %s does not match the deposit; nothing applied", deposit_id)
        return "IDENTITY_REJECTED", deposit
    if not ok:
        db.rollback()
        logger.warning("Confirmation failed for SoncoPay deposit %s; nothing applied", deposit_id)
        return "ERROR", deposit
    return "SYNCED", deposit


async def sync_deposit(db: Session, deposit: Deposit) -> Dict[str, Any]:
    """Read the payment and apply it. Commits. Raises SoncoPayError when SoncoPay cannot answer."""
    deposit_id = int(deposit.id)
    if not deposit.external_payment_id:
        return status_payload(deposit)
    payment = await fetch_payment(db, deposit)
    outcome, deposit = apply_locked(db, deposit_id, payment)
    if outcome == "SYNCED":
        db.commit()
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).one()
    return status_payload(deposit)


async def reconcile_one(db: Session, deposit_id: int) -> str:
    """Scheduler: one SoncoPay deposit, its own transaction. The provider is
    authoritative: nothing is expired here without its answer, and a deposit
    it cannot be asked about is left for the next pass."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    if deposit is None or not is_soncopay(deposit) or not deposit.external_payment_id:
        db.rollback()
        return "SKIPPED"
    try:
        payment = await fetch_payment(db, deposit)
    except SoncoPayError as exc:
        logger.error("SoncoPay status unavailable for deposit %s (%s)", deposit_id, exc.stage)
        return "PROVIDER_UNAVAILABLE"
    outcome, _deposit = apply_locked(db, deposit_id, payment)
    if outcome == "SYNCED":
        db.commit()
    return outcome


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def _header(headers: Mapping[str, str], name: str) -> str:
    getter = getattr(headers, "get", None)
    value = getter(name) if getter else None
    if value is None and getter:
        value = getter(name.title())
    return str(value or "").strip()


def timestamped_signature(headers: Mapping[str, str]) -> Optional[str]:
    """The t=...,v1=... signature, wherever SoncoPay put it (X-SoncoPay-Signature for
    accounts on the timestamped format, X-SoncoPay-Signature-V2 while on legacy)."""
    for name in (SIGNATURE_V2_HEADER, SIGNATURE_HEADER):
        value = _header(headers, name)
        if value.startswith("t="):
            return value
    return None


def verify_signature(raw: bytes, header: Optional[str], secret: str, *, now: Optional[float] = None,
                     tolerance: int = TOLERANCE_SECONDS) -> bool:
    """HMAC-SHA256 hex of "<t>." + raw body, keyed with the signing secret, compared in
    constant time, the timestamp within `tolerance` seconds. The legacy signature (no
    timestamp, replayable) is never accepted."""
    if not header or not secret:
        return False
    timestamp, macs = None, []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value.strip()
        elif key == "v1" and value:
            macs.append(value.strip().lower())
    try:
        ts = int(timestamp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if not macs or abs((time.time() if now is None else now) - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("ascii") + raw, hashlib.sha256).hexdigest()
    matched = False
    for mac in macs:
        matched = hmac.compare_digest(mac.encode("ascii", "replace"), expected.encode("ascii")) or matched
    return matched


def signing_environment(db: Session, raw: bytes, headers: Mapping[str, str], *,
                        now: Optional[float] = None) -> Optional[str]:
    """The environment whose signing secret signed this delivery, or None."""
    header = timestamped_signature(headers)
    if header is None:
        return None
    for environment, secret in soncopay_settings.webhook_secrets(db).items():
        if verify_signature(raw, header, secret, now=now):
            return environment
    return None


class WebhookResult:
    def __init__(self, status_code: int, body: Dict[str, Any]):
        self.status_code = status_code
        self.body = body


def _find_deposit(db: Session, payment_id: str, order_id: str) -> Optional[Deposit]:
    """Only SoncoPay deposits are ever matched (never a NOWPayments one)."""
    query = db.query(Deposit).filter(Deposit.payment_provider == PROVIDER)
    if payment_id:
        found = query.filter(Deposit.external_payment_id == payment_id).first()
        if found is not None:
            return found
    if order_id:
        return query.filter(Deposit.order_id == order_id).first()
    return None


def _already_processed(db: Session, delivery_id: str) -> bool:
    return db.query(SoncoPayWebhookEvent.id).filter(SoncoPayWebhookEvent.delivery_id == delivery_id).first() is not None


def _record(db: Session, *, delivery_id: str, event: str, environment: str, payment_id: Optional[str],
            deposit_id: Optional[int], outcome: str) -> bool:
    """Write the delivery and commit. False when another worker already recorded it."""
    db.add(SoncoPayWebhookEvent(delivery_id=delivery_id, event=event[:64], environment=environment,
                                payment_id=(payment_id or None) and payment_id[:64], deposit_id=deposit_id,
                                outcome=outcome))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


async def handle_webhook(db: Session, raw: bytes, headers: Mapping[str, str], *,
                         now: Optional[float] = None) -> WebhookResult:
    if len(raw) > MAX_WEBHOOK_BYTES:
        return WebhookResult(413, {"detail": "Payload too large"})
    if not soncopay_settings.WEBHOOK_OPERATIONAL:
        return WebhookResult(503, {"code": "SONCOPAY_WEBHOOK_NOT_OPERATIONAL",
                                   "message": "SoncoPay webhooks are not accepted yet."})
    if not soncopay_settings.webhook_secrets(db):
        db.rollback()
        # Nothing can be verified: SoncoPay keeps the delivery and retries (about three days).
        return WebhookResult(503, {"detail": "SoncoPay webhook signing secret is not configured"})
    environment = signing_environment(db, raw, headers, now=now)
    db.rollback()
    if environment is None:
        return WebhookResult(400, {"detail": "invalid signature"})
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return WebhookResult(400, {"detail": "invalid JSON"})
    if not isinstance(body, dict) or not isinstance(body.get("event"), str):
        return WebhookResult(400, {"detail": "no event"})
    delivery_id = _header(headers, DELIVERY_HEADER)[:128]
    if not delivery_id:
        return WebhookResult(400, {"detail": "missing X-SoncoPay-Delivery-Id"})
    event = body["event"]
    data = body.get("data") if isinstance(body.get("data"), dict) else {}

    if _already_processed(db, delivery_id):
        db.rollback()
        return WebhookResult(200, {"ok": True, "duplicate": True})
    if event.startswith(("payout.", "payout_destination.")):
        # Only a reason to look: the payout cycle reads every open payout and destination back from
        # SoncoPay (app.services.soncopay_payouts). Nothing in the body is applied.
        if _record(db, delivery_id=delivery_id, event=event, environment=environment, payment_id=None,
                   deposit_id=None, outcome="PAYOUT_SYNC_REQUESTED"):
            from app.services import cashout_engine

            cashout_engine.request_cycle()
        return WebhookResult(200, {"ok": True})
    if not event.startswith("payment."):
        # Refund, invoice and ping events: acknowledged, never acted on.
        _record(db, delivery_id=delivery_id, event=event, environment=environment, payment_id=None,
                deposit_id=None, outcome="ACKNOWLEDGED")
        return WebhookResult(200, {"ok": True})

    livemode = data.get("livemode")
    if isinstance(livemode, bool) and livemode != (environment == "live"):
        logger.error("SoncoPay webhook %s: livemode does not match the signing environment", delivery_id[:40])
        return WebhookResult(400, {"detail": "test/live mode does not match the signature"})
    payment_id, order_id = str(data.get("id") or "")[:64], str(data.get("order_id") or "")[:100]
    deposit = _find_deposit(db, payment_id, order_id)
    if deposit is None:
        logger.warning("SoncoPay webhook %s for an unknown payment", event[:40])
        _record(db, delivery_id=delivery_id, event=event, environment=environment, payment_id=payment_id,
                deposit_id=None, outcome="UNKNOWN_PAYMENT")
        return WebhookResult(200, {"ok": True})
    deposit_id = int(deposit.id)
    if deposit.provider_environment != environment:
        db.rollback()
        logger.error("SoncoPay webhook for deposit %s was signed by the %s secret; the deposit is %s",
                     deposit_id, environment, deposit.provider_environment)
        return WebhookResult(409, {"detail": "environment does not match the payment"})
    if payment_id and deposit.external_payment_id and payment_id != deposit.external_payment_id:
        db.rollback()
        logger.error("SoncoPay webhook payment id does not match deposit %s", deposit_id)
        return WebhookResult(409, {"detail": "payment does not match the order"})

    # The webhook only says "look": the payment itself is read from SoncoPay.
    try:
        payment = await fetch_payment(db, deposit, payment_id)
    except SoncoPayError as exc:
        logger.error("SoncoPay webhook: payment of deposit %s could not be read (%s)", deposit_id, exc.stage)
        return WebhookResult(503, {"detail": "payment status unavailable, retry later"})
    outcome, deposit = apply_locked(db, deposit_id, payment)
    if outcome == "IDENTITY_REJECTED":
        return WebhookResult(409, {"detail": "payment does not match the order"})
    if outcome != "SYNCED":
        return WebhookResult(500, {"detail": "payment could not be processed"})
    db.add(SoncoPayWebhookEvent(delivery_id=delivery_id, event=event[:64], environment=environment,
                                payment_id=str(payment.get("id"))[:64], deposit_id=deposit_id, outcome="PROCESSED"))
    try:
        db.commit()                                   # deposit change + delivery record together
    except IntegrityError:
        db.rollback()                                 # another worker processed this delivery first
        return WebhookResult(200, {"ok": True, "duplicate": True})
    logger.info("SoncoPay webhook %s processed for deposit %s: %s", event[:40], deposit_id,
                deposit.status.value)
    return WebhookResult(200, {"ok": True})


# ---------------------------------------------------------------------------
# Connection test (Admin): GET /v1/methods, no side effect
# ---------------------------------------------------------------------------

async def connection_test(db: Session, environment: str) -> Dict[str, Any]:
    try:
        client = client_for(db, environment)
    except SoncoPayError as exc:
        db.rollback()
        return {"ok": False, "environment": environment, "error": str(exc), "code": None}
    db.rollback()
    try:
        answer = await client.account_methods()
    except SoncoPayError as exc:
        return {"ok": False, "environment": environment, "code": exc.code, "status_code": exc.status_code,
                "error": "SoncoPay refused the key." if exc.status_code in (401, 403)
                else "SoncoPay could not be reached or answered with an error."}
    methods = answer.get("payment_methods") or answer.get("methods") or []
    return {"ok": True, "environment": environment, "methods": len(methods) if isinstance(methods, list) else 0}


def soncopay_filter():
    """SQL condition: a deposit that is NOT SoncoPay (NULL = NOWPayments/older)."""
    return or_(Deposit.payment_provider.is_(None), Deposit.payment_provider != PROVIDER)

