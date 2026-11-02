"""SoncoPay payment and payout readiness, and SoncoPay payment reconciliation (Prompt 3, 2026-11-02).

Everything here only READS:
  * payment_reconciliation()  local SoncoPay deposits against the signed webhook deliveries
                              recorded for them (soncopay_webhook_events).
  * readiness()               one line per readiness item (READY | BLOCKED | NOT_VERIFIED |
                              NOT_APPLICABLE) with its evidence, and whether it is a code,
                              provider or operational item.

Nothing is created, sent, registered or changed, at MyHigh5 or at SoncoPay. With
read_provider=True the provider is asked through its documented read-only calls
(GET /v1/methods, GET /v1/balances); no payment, payout or destination is created.
Being READY everywhere never switches anything on: activation stays a separate,
explicit owner decision (AUTOMATIC_PAYOUT_ACTIVATED and the Admin switches).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.checkout_gateway import SoncoPayWebhookEvent
from app.models.payment import Deposit, DepositStatus

logger = logging.getLogger(__name__)

READY, BLOCKED, NOT_VERIFIED, NOT_APPLICABLE = "READY", "BLOCKED", "NOT_VERIFIED", "NOT_APPLICABLE"
CODE, PROVIDER, OPERATIONAL = "code", "provider", "operational"

# A pending deposit whose SoncoPay payment expired this long ago and that never received a final status
# is reported: either a webhook delivery was missed or the status scheduler could not read it.
MISSING_EVENT_AFTER = timedelta(hours=2)
PAID_WORDS = ("paid",)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() + "Z" if value is not None else None


# ---------------------------------------------------------------------------
# Payment reconciliation (read-only)
# ---------------------------------------------------------------------------

def payment_reconciliation(db: Session, *, now: Optional[datetime] = None, limit: int = 200) -> dict:
    """Local SoncoPay deposits next to the signed deliveries recorded for them. Read-only; calls nobody.

    Problems listed:
      PAID_NOT_CONFIRMED        SoncoPay's last status is "paid" but the deposit is not validated
                                (its confirmation failed and was rolled back) -> look at it
      PAID_OTHER_ASSET          paid in another asset/network than chosen: never confirmed automatically
      CONFIRMED_NOT_PAID        validated SoncoPay deposit whose last provider status is not "paid"
                                (and not a refund) -> local/provider mismatch
      MISSING_PROVIDER_EVENT    still pending well after its payment expired: no final status arrived
      UNKNOWN_PAYMENT_EVENT     a signed payment delivery for a payment MyHigh5 does not know
      DUPLICATE_PAYMENT_ID      two deposits hold the same SoncoPay payment id
    """
    from app.services.soncopay_payments import OTHER_ASSET_STATUS, PROVIDER as SP

    now = now or datetime.utcnow()
    problems: List[Dict[str, Any]] = []

    def add(kind: str, severity: str, message: str, **ref) -> None:
        if len(problems) < limit:
            problems.append({"type": kind, "severity": severity, "message": message, **ref})

    base = db.query(Deposit).filter(Deposit.payment_provider == SP)
    by_status = {(s.value if hasattr(s, "value") else str(s)): int(n) for s, n in
                 base.with_entities(Deposit.status, func.count(Deposit.id)).group_by(Deposit.status).all()}
    by_environment = {str(e or "unknown"): int(n) for e, n in
                      base.with_entities(Deposit.provider_environment, func.count(Deposit.id))
                      .group_by(Deposit.provider_environment).all()}

    for d in (base.filter(Deposit.provider_status.in_(PAID_WORDS), Deposit.status != DepositStatus.VALIDATED)
              .order_by(Deposit.id.desc()).limit(limit).all()):
        add("PAID_NOT_CONFIRMED", "critical",
            f"Deposit #{d.id}: SoncoPay reports it paid but it is not confirmed ({d.status.value}).",
            deposit_id=d.id, user_id=d.user_id)
    for d in (base.filter(Deposit.provider_status == OTHER_ASSET_STATUS).order_by(Deposit.id.desc())
              .limit(limit).all()):
        add("PAID_OTHER_ASSET", "warning",
            f"Deposit #{d.id} was paid in another asset or network than the member chose; it is not "
            "confirmed automatically.", deposit_id=d.id, user_id=d.user_id)
    for d in (base.filter(Deposit.status == DepositStatus.VALIDATED,
                          Deposit.provider_status.isnot(None),
                          ~Deposit.provider_status.in_(PAID_WORDS + ("refunded", "partially_refunded")))
              .order_by(Deposit.id.desc()).limit(limit).all()):
        add("CONFIRMED_NOT_PAID", "critical",
            f"Deposit #{d.id} is confirmed but SoncoPay's last status is {str(d.provider_status)[:40]!r}.",
            deposit_id=d.id, user_id=d.user_id)
    for d in (base.filter(Deposit.status == DepositStatus.PENDING, Deposit.external_payment_id.isnot(None),
                          Deposit.provider_expires_at.isnot(None),
                          Deposit.provider_expires_at < now - MISSING_EVENT_AFTER)
              .order_by(Deposit.id.desc()).limit(limit).all()):
        add("MISSING_PROVIDER_EVENT", "warning",
            f"Deposit #{d.id} is still pending although its SoncoPay payment expired at "
            f"{_iso(d.provider_expires_at)}; no final status was received.", deposit_id=d.id, user_id=d.user_id)
    for pid, n in (base.filter(Deposit.external_payment_id.isnot(None))
                   .with_entities(Deposit.external_payment_id, func.count(Deposit.id))
                   .group_by(Deposit.external_payment_id).having(func.count(Deposit.id) > 1).limit(limit).all()):
        add("DUPLICATE_PAYMENT_ID", "critical", f"{n} deposits hold the same SoncoPay payment {str(pid)[:24]}.")

    events = db.query(SoncoPayWebhookEvent)
    outcomes = {str(o): int(n) for o, n in events.with_entities(SoncoPayWebhookEvent.outcome,
                                                                func.count(SoncoPayWebhookEvent.id))
                .group_by(SoncoPayWebhookEvent.outcome).all()}
    for e in (events.filter(SoncoPayWebhookEvent.outcome == "UNKNOWN_PAYMENT")
              .order_by(SoncoPayWebhookEvent.id.desc()).limit(min(limit, 50)).all()):
        add("UNKNOWN_PAYMENT_EVENT", "warning",
            f"Signed SoncoPay delivery {str(e.event)[:40]} at {_iso(e.created_at)} names a payment MyHigh5 does "
            "not know.", event_id=e.id)
    last = events.order_by(SoncoPayWebhookEvent.id.desc()).first()
    validated = by_status.get(DepositStatus.VALIDATED.value, 0)
    with_event = (db.query(func.count(func.distinct(SoncoPayWebhookEvent.deposit_id)))
                  .filter(SoncoPayWebhookEvent.outcome == "PROCESSED").scalar() or 0)
    db.rollback()
    return {
        "deposits": {"by_status": by_status, "by_environment": by_environment,
                     "validated": validated, "with_processed_webhook": int(with_event)},
        "webhooks": {"total": sum(outcomes.values()), "by_outcome": outcomes,
                     "last_received_at": _iso(last.created_at) if last is not None else None,
                     "last_event": last.event if last is not None else None},
        "problems": problems,
        "critical": sum(1 for p in problems if p["severity"] == "critical"),
        "checked_at": _iso(now),
    }


# ---------------------------------------------------------------------------
# Readiness (read-only)
# ---------------------------------------------------------------------------

def _item(key: str, label: str, status: str, kind: str, evidence: str, **extra) -> dict:
    return {"key": key, "label": label, "status": status, "kind": kind, "evidence": evidence, **extra}


async def _provider_facts(db: Session) -> dict:
    """Documented read-only SoncoPay calls. Never raises."""
    from app.services import soncopay_payments, soncopay_payouts, soncopay_settings

    facts: Dict[str, Any] = {}
    if soncopay_settings.api_key(db, "live"):
        try:
            methods = await soncopay_payments.account_methods(db)
            # USDT BSC is always listed by account_methods; only a successful read of GET /v1/methods
            # (the cache filled) verifies the account's methods.
            if soncopay_payments._methods_cache.get("methods") is not None:
                facts["methods"] = methods
            else:
                facts["methods_error"] = "METHODS_UNREADABLE"
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            facts["methods_error"] = getattr(exc, "code", None) or type(exc).__name__
    db.rollback()
    if soncopay_payouts.ready(db):
        try:
            facts["usdt_available"] = str(soncopay_payouts.SoncoPayPayoutProvider(db).balance("usdtbsc"))
        except Exception as exc:  # noqa: BLE001
            facts["balance_error"] = getattr(exc, "code", None) or type(exc).__name__
    db.rollback()
    return facts


async def readiness(db: Session, *, read_provider: bool = False, now: Optional[datetime] = None) -> dict:
    """The sixteen Prompt 3 readiness items. READY only with evidence; nothing is activated."""
    from app.core.config import settings
    from app.models.affiliate import PayoutWalletApproval
    from app.models.advertising_v2 import AdvSettings
    from app.models.checkout_gateway import SoncoPayPayoutDestination
    from app.services import (cashout_engine, kyc_fee, payment_config, soncopay_payouts, soncopay_settings)

    now = now or datetime.utcnow()
    state = soncopay_settings.current_state(db)
    checkout_env = soncopay_settings.checkout_environment(db)
    secrets = soncopay_settings.webhook_secrets(db)
    live_key = bool(soncopay_settings.api_key(db, "live"))
    payout_blockers = [b["code"] for b in soncopay_payouts.blockers(db)]
    authorization = soncopay_payouts.authorization(db)
    published = soncopay_payouts.published_limits(db)
    fee, fee_currency = kyc_fee.member_fee(db)
    approvals = {str(s): int(n) for s, n in db.query(PayoutWalletApproval.status, func.count(PayoutWalletApproval.id))
                 .group_by(PayoutWalletApproval.status).all()}
    destinations = db.query(SoncoPayPayoutDestination).all()
    payable = [r for r in destinations if soncopay_payouts.destination_problem(r, r.address, now) is None]
    waiting = [r for r in destinations
               if soncopay_payouts.destination_problem(r, r.address, now) == "DESTINATION_WAITING_PERIOD"]
    confirmed = [r for r in destinations if r.dashboard_confirmed_at is not None]
    adv = db.query(AdvSettings).first()
    engine = cashout_engine.engine_status(db)
    reconciliation = payment_reconciliation(db, now=now)
    payout_problems = cashout_engine.discrepancies(db, now=now)
    db.rollback()
    facts = await _provider_facts(db) if read_provider else {}

    items: List[dict] = []
    items.append(_item(
        "merchant_configuration", "SoncoPay merchant configuration",
        READY if (state["enabled"] and state["environment"] == "live" and live_key and "live" in secrets)
        else BLOCKED, OPERATIONAL,
        f"enabled={state['enabled']}, environment={state['environment']}, live key saved={live_key}, "
        f"webhook secrets saved for {sorted(secrets) or 'none'}. Keys are never shown."))
    if "methods" in facts:
        codes = [m.get("code") for m in facts["methods"] if isinstance(m, dict)]
        items.append(_item("payment_methods", "Payment method availability", READY if codes else BLOCKED, PROVIDER,
                           f"GET /v1/methods for the MyHigh5 Live account lists {len(codes)} method(s): "
                           f"{', '.join(map(str, codes[:12]))}{'…' if len(codes) > 12 else ''}.", methods=codes))
    else:
        items.append(_item("payment_methods", "Payment method availability", NOT_VERIFIED, PROVIDER,
                           facts.get("methods_error") and f"SoncoPay could not be read ({facts['methods_error']})."
                           or "Not read now. Checkout offers only the methods SoncoPay lists for this account "
                              "(GET /v1/methods); run with provider read to verify."))
    items.append(_item(
        "checkout_integration", "Checkout integration",
        READY if soncopay_settings.CHECKOUT_IMPLEMENTED and checkout_env == "live" else BLOCKED, CODE,
        f"Checkout implemented; new checkouts open in: {checkout_env or 'none (closed)'}. A payment is confirmed "
        "only from SoncoPay's own payment record, never from the browser return."))
    items.append(_item(
        "webhook_verification", "Webhook verification",
        READY if soncopay_settings.WEBHOOK_OPERATIONAL and "live" in secrets else BLOCKED, CODE,
        "HMAC-SHA256 timestamped signature (t=,v1=, 300 s tolerance, legacy unsigned format refused), delivery id "
        "unique, payment re-read from SoncoPay and matched on payment id, order id, amount, currency and mode. "
        f"Deliveries recorded: {reconciliation['webhooks']['total']} "
        f"(last {reconciliation['webhooks']['last_received_at'] or 'never'})."))
    items.append(_item(
        "kyc_fee_payment", "KYC fee payment readiness",
        READY if (checkout_env == "live" and fee == Decimal("5.00")) else BLOCKED, CODE,
        f"KYC fee {fee} {fee_currency}; one paid attempt per fee; paying never approves identity. Not yet "
        "proven with a real payment (owner-approved test after the final audit)."))
    items.append(_item(
        "commission_integration", "Commission integration", READY, CODE,
        "Direct-referral commission accrues once at the confirmation of a validated deposit, only for a "
        "KYC-approved sponsor; otherwise a missed (non-payable) record. Replays find the existing decision."))
    items.append(_item(
        "payout_worker", "Payout worker",
        READY if not payment_config.payout_activation_switch() else BLOCKED, CODE,
        f"Code complete; payout provider {engine.get('payout_provider')}; server switch "
        f"CRYPTO_AUTO_PAYOUT_ENABLED={engine.get('server_switch')}, AUTOMATIC_PAYOUT_ACTIVATED="
        f"{engine.get('activation')}. Internal payout discrepancies: {len(payout_problems)}."))
    items.append(_item(
        "wallet_approval", "Wallet approval",
        READY if approvals.get("APPROVED", 0) > 0 else BLOCKED, OPERATIONAL,
        f"Wallet approvals by status: {approvals or 'none'}. The first approved wallet is needed for the "
        "controlled payout test.", approvals=approvals))
    items.append(_item(
        "destination_registration", "Provider destination registration",
        READY if any(r.destination_id for r in destinations) else BLOCKED, PROVIDER,
        f"{len(destinations)} destination(s); {sum(1 for r in destinations if r.destination_id)} registered with "
        f"SoncoPay; {len(confirmed)} confirmed in the SoncoPay dashboard."
        + (" Registration starts only after the payout authorization is recorded." if payout_blockers else "")))
    items.append(_item(
        "waiting_period", "Provider waiting period (24 h)",
        READY if payable else (NOT_APPLICABLE if not confirmed else BLOCKED), PROVIDER,
        f"{len(payable)} destination(s) past the 24-hour wait, {len(waiting)} waiting. The wait is never shortened."))
    items.append(_item(
        "payout_authorization", "Provider payout authorization",
        READY if authorization is not None else BLOCKED, OPERATIONAL,
        (f"Recorded {authorization['authorized_at']} by user {authorization['authorized_by']}."
         if authorization is not None else
         "SONCOPAY_PAYOUTS_NOT_AUTHORIZED: a Super Admin must record SoncoPay Compliance's written approval "
         f"(phrase \"{soncopay_payouts.CONFIRM_AUTHORIZATION}\").")))
    if "usdt_available" in facts:
        bal = Decimal(facts["usdt_available"])
        items.append(_item("provider_balance", "Provider balance (USDT BSC available)",
                           READY if bal >= Decimal("10.00") else BLOCKED, OPERATIONAL,
                           f"Available {bal} USDT (at least 10.00 plus fee needed for one payout).",
                           balance=str(bal)))
    else:
        items.append(_item("provider_balance", "Provider balance (USDT BSC available)", NOT_VERIFIED, OPERATIONAL,
                           facts.get("balance_error") and f"Balance unreadable ({facts['balance_error']})."
                           or "Readable only once payouts are authorized (GET /v1/balances, read-only)."))
    items.append(_item(
        "financial_reconciliation", "Financial reconciliation",
        READY if reconciliation["critical"] == 0 and not any(p["severity"] == "critical" for p in payout_problems)
        else BLOCKED, CODE,
        f"SoncoPay payments: {reconciliation['critical']} critical / {len(reconciliation['problems'])} total "
        f"problems; payouts: {len(payout_problems)} discrepancies. Read-only."))
    items.append(_item(
        "monitoring_notifications", "Monitoring and notifications", READY, CODE,
        "Admin readiness, payment reconciliation, payout reconciliation and wallet queue; member emails for "
        "wallet submitted/changed/approved/rejected, missing wallet, destination confirmation and waiting "
        "period, payout blocked or awaiting, completed and failed (idempotent, once per event)."))
    payments_live = checkout_env == "live"
    items.append(_item(
        "live_payment_activation", "Live payment activation",
        READY if payments_live and reconciliation["deposits"]["validated"] > 0 else
        (NOT_VERIFIED if payments_live else BLOCKED), OPERATIONAL,
        f"SoncoPay Live checkout open={payments_live}; confirmed SoncoPay payments: "
        f"{reconciliation['deposits']['validated']}. A real end-to-end payment is still to be proven "
        "(owner-approved KYC fee test)."))
    items.append(_item(
        "live_payout_activation", "Live payout activation", BLOCKED, OPERATIONAL,
        f"AUTOMATIC_PAYOUT_ACTIVATED={payment_config.payout_activation_switch()} (stays OFF until the owner "
        "approves a controlled payout). Blockers: " + (", ".join(payout_blockers) or "none at SoncoPay level")
        + "."))

    switches = {
        "automatic_payout_activated": payment_config.payout_activation_switch(),
        "crypto_auto_payout_enabled": payment_config.crypto_master_switch(),
        "advertising_funding_enabled": bool(adv.funding_enabled) if adv is not None else False,
        "advertising_campaigns_enabled": bool(adv.campaigns_enabled) if adv is not None else False,
        "annual_ads_enabled": bool(settings.ANNUALADS_ENABLED),
        "marketplace_enabled": bool(settings.MARKETPLACE_ENABLED),
    }
    limits = soncopay_payouts.provider_limit_view(db, now)
    db.rollback()
    return {
        "checked_at": _iso(now), "provider_read": bool(read_provider),
        "items": items,
        "counts": {s: sum(1 for i in items if i["status"] == s) for s in (READY, BLOCKED, NOT_VERIFIED, NOT_APPLICABLE)},
        "switches": switches,
        "limits": {**limits, "business_minimum_usd": f"{payment_config.load(db).crypto_min_usd:.2f}",
                   "published_fee": str(published["fee"]) if published else None,
                   "published_minimum": str(published["minimum"]) if published else None},
        "payment_reconciliation": reconciliation,
    }
