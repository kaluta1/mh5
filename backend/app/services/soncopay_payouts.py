"""SoncoPay automatic USDT BEP20 commission payouts (owner decision 2026-10-29: SoncoPay is the only
provider; NOWPayments is discontinued). Built only from the official API v1 specification
(https://soncopay.com/openapi.json) and developer documentation (soncopay.com/developers):

  POST /v1/payouts                 {destination_id, amount, reference, asset}. `amount` is what the
                                   address RECEIVES; the network fee is ADDED and taken from our balance.
                                   `reference` makes the call idempotent (same reference -> same payout).
  GET  /v1/payouts[/{id}]          status, amount, fee, address, tx_hash, error
  GET  /v1/payout-fees             network fees ("USDT:BSC") and min_payout_usd
  GET  /v1/balances                balances, reserved, available, on_hold (per asset)
  /v1/payout-destinations          saved addresses. In live mode an API-key payout goes ONLY to a saved
                                   destination that a person confirmed in the dashboard (or that SoncoPay's
                                   automatic confirmation activated), after the security waiting period
                                   (`usable`, `usable_from`). At most 50 open destinations per mode.

The rules, in one place:
  * Nothing is registered or paid until the owner has recorded that SoncoPay allows member commission
    payouts from the merchant account (authorize()), SoncoPay is enabled in LIVE mode and its Live key
    is saved. Test mode is never used for payouts: a simulated payout would mark a real commission paid.
  * Each approved member wallet (one wallet approval) becomes one destination row. QUEUED rows are
    registered while SoncoPay has a free slot; a full account leaves them QUEUED. No destination of
    another member is ever disabled to free a slot. A member's own superseded destination (their
    approval changed) is disabled at SoncoPay and never paid to again.
  * A payout goes only to the ACTIVE, usable destination of the member's CURRENT approval, at exactly
    its address. Anything else keeps the commission unpaid and retried every cycle.
  * The member bears the network fee: the address receives the commission less the fee SoncoPay
    publishes for USDT:BSC (payment_config.FEE_MODE_ADDED). The payout's reported amount and fee are
    checked after completion; any difference suspends payouts for review.
  * The server activation (AUTOMATIC_PAYOUT_ACTIVATED) and the readiness are checked again inside
    create_payout, before any request. A refusal SoncoPay documents as "nothing created" is a refusal;
    no answer (timeout, 5xx) is an UNKNOWN outcome that is looked up, never sent again.
  * Webhooks (payout.*, payout_destination.*) are only a reason to look: they wake the payout cycle,
    which reads everything back from SoncoPay.
"""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.checkout_gateway import CheckoutGatewaySettings, SoncoPayPayoutDestination
from app.models.user import User
from app.services import payment_config, soncopay_settings
from app.services.soncopay_client import API_BASE, USER_AGENT

logger = logging.getLogger(__name__)

ENVIRONMENT = "live"
ASSET, NETWORK = "USDT", "BSC"
FEE_KEY = f"{ASSET}:{NETWORK}"
PAYOUT_CURRENCY = "usdtbsc"
DESTINATION_LIMIT = 50                      # documented: at most 50 open destinations per mode
OPEN_PROVIDER_STATUSES = ("pending_confirmation", "active")
REGISTRATIONS_PER_CYCLE = 10
ACTIVE_RECHECK = timedelta(hours=1)
CONFIRM_AUTHORIZATION = "SONCOPAY ALLOWS MEMBER PAYOUTS"
AUDIT_AUTHORIZED = "SONCOPAY_PAYOUTS_AUTHORIZED"
AUDIT_REVOKED = "SONCOPAY_PAYOUTS_AUTHORIZATION_REVOKED"
AUDIT_DESTINATION = "SONCOPAY_DESTINATION_CHANGED"
EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")

QUEUED, PENDING, ACTIVE, DISABLED, REJECTED, SUPERSEDED = (
    "QUEUED", "PENDING_CONFIRMATION", "ACTIVE", "DISABLED", "REJECTED", "SUPERSEDED")
LIVE_STATES = (QUEUED, PENDING, ACTIVE)

# SoncoPay payout status -> the engine's vocabulary (cashout_engine.PROVIDER_*).
#   completed                       paid (tx_hash filled in)
#   failed / rejected / expired     final, "the amount and the fee are back in your balance"
#   everything else                 still in progress (unknown is checked by SoncoPay's team and
#                                   "never sent again automatically")
STATUS_MAP = {"completed": "FINISHED", "failed": "REJECTED", "rejected": "REJECTED", "expired": "REJECTED"}

# Documented refusals that create nothing, and what they mean for MyHigh5 (not the member's fault).
PLATFORM_FAULTS = {
    "payout_velocity_exceeded": "PROVIDER_VELOCITY_LIMIT",
    "payout_funds_on_hold": "PROVIDER_FUNDS_ON_HOLD",
    "policy_denied": "PROVIDER_POLICY_DENIED",
    "destination_required": "DESTINATION_NOT_USABLE",
    "destination_not_confirmed": "DESTINATION_NOT_USABLE",
    "destination_cooling_down": "DESTINATION_NOT_USABLE",
    "destination_disabled": "DESTINATION_NOT_USABLE",
    "destination_mode_mismatch": "DESTINATION_NOT_USABLE",
    "destination_not_found": "DESTINATION_NOT_USABLE",
    "destination_currency_mismatch": "DESTINATION_NOT_USABLE",
    "payout_method_not_allowed": "PAYOUT_METHOD_NOT_ALLOWED",
    "payout_method_unavailable": "PAYOUT_METHOD_NOT_ALLOWED",
}
AUTH_CODES = ("api_key_scope", "api_key_invalid", "api_key_revoked", "api_key_not_allowed")
# Outcomes after which no other member can be paid in this cycle either.
STOP_CYCLE = ("PROVIDER_VELOCITY_LIMIT", "PROVIDER_FUNDS_ON_HOLD", "PROVIDER_POLICY_DENIED",
              "PAYOUT_METHOD_NOT_ALLOWED", "SONCOPAY_PAYOUTS_NOT_READY", "NOT_ACTIVATED")


class PayoutRefused(Exception):
    """SoncoPay refused, or MyHigh5 refused before asking: NOTHING was created. Shaped like
    nowpayments_service.NowPaymentsError for the engine (status_code, code, stage, ip_refused), plus
    `platform_fault`: the refusal is MyHigh5's or SoncoPay's, not the member's."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, code: Optional[str] = None,
                 stage: Optional[str] = None, ip_refused: bool = False, platform_fault: Optional[str] = None,
                 extra: Optional[dict] = None):
        super().__init__(message)
        self.status_code, self.code, self.stage = status_code, code, stage
        self.ip_refused, self.platform_fault = ip_refused, platform_fault
        self.extra = extra or {}


class PayoutUnavailable(Exception):
    """No usable answer (network error, timeout, 5xx). For a payout creation the outcome is UNKNOWN."""

    def __init__(self, message: str, *, stage: Optional[str] = None):
        super().__init__(message)
        self.stage = stage


def _transport() -> Optional[httpx.BaseTransport]:
    """Tests replace this with an httpx.MockTransport. Never set in production."""
    return None


def _decimal(value: Any, what: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise PayoutUnavailable(f"SoncoPay {what} is not a number", stage="read") from None
    if not number.is_finite() or number < 0:
        raise PayoutUnavailable(f"SoncoPay {what} is not usable", stage="read")
    return number


def _time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def same_address(left: Optional[str], right: Optional[str]) -> bool:
    left, right = str(left or "").strip(), str(right or "").strip()
    return bool(EVM_ADDRESS.match(left)) and left.lower() == right.lower()


# ---------------------------------------------------------------------------
# HTTP client (synchronous: the payout engine runs in a worker thread)
# ---------------------------------------------------------------------------

class PayoutClient:
    READ_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
    CREATE_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

    def __init__(self, api_key: str, *, base_url: str = API_BASE):
        key = (api_key or "").strip()
        if not key.startswith(soncopay_settings.KEY_PREFIX[ENVIRONMENT]):
            raise PayoutRefused("The SoncoPay Live API key is not a live key", stage="config",
                                platform_fault="SONCOPAY_PAYOUTS_NOT_READY")
        self.__key = key
        self.base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        return "SoncoPayPayoutClient(environment='live')"

    def _request(self, method: str, path: str, *, stage: str, body: Optional[dict] = None,
                 params: Optional[dict] = None, retry: bool = True) -> Dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT, "X-Api-Key": self.__key}
        timeout = self.CREATE_TIMEOUT if stage == "create" else self.READ_TIMEOUT
        attempts = 3 if retry else 1
        with httpx.Client(timeout=timeout, transport=_transport()) as client:
            for attempt in range(attempts):
                try:
                    response = client.request(method, self.base_url + path, headers=headers, json=body,
                                              params=params)
                except httpx.HTTPError as exc:
                    if attempt + 1 < attempts:
                        time.sleep(min(0.5 * 2 ** attempt, 2.0) + random.random() / 10)
                        continue
                    logger.warning("SoncoPay payouts %s: no answer (%s)", stage, type(exc).__name__)
                    raise PayoutUnavailable("SoncoPay could not be reached", stage=stage) from None
                if response.status_code >= 500:
                    if attempt + 1 < attempts:
                        time.sleep(min(0.5 * 2 ** attempt, 2.0))
                        continue
                    raise PayoutUnavailable(f"SoncoPay answered HTTP {response.status_code}", stage=stage)
                if response.status_code >= 400:
                    try:
                        answer = response.json()
                    except ValueError:
                        answer = {}
                    answer = answer if isinstance(answer, dict) else {}
                    code = str(answer.get("code") or "")[:60] or None
                    logger.warning("SoncoPay payouts %s refused: HTTP %s code=%s", stage, response.status_code, code)
                    raise _refusal(response.status_code, code, stage, answer)
                try:
                    answer = response.json()
                except ValueError:
                    raise PayoutUnavailable("SoncoPay answered with something that is not JSON", stage=stage) from None
                if not isinstance(answer, dict):
                    raise PayoutUnavailable("SoncoPay answered with an unexpected document", stage=stage)
                return answer
        raise PayoutUnavailable("SoncoPay could not be reached", stage=stage)    # pragma: no cover

    # -- reads ----------------------------------------------------------------
    def balances(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/balances", stage="read")

    def payout_fees(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/payout-fees", stage="read")

    def list_destinations(self, *, status: Optional[str] = None) -> Dict[str, Any]:
        params = {"kind": "crypto"}
        if status:
            params["status"] = status
        return self._request("GET", "/v1/payout-destinations", stage="read", params=params)

    def all_destinations(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/payout-destinations", stage="read")

    def get_destination(self, destination_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/payout-destinations/{_safe_id(destination_id, 'pd_')}", stage="read")

    def get_payout(self, payout_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/payouts/{_safe_id(payout_id, 'po_')}", stage="read")

    def list_payouts(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        return self._request("GET", "/v1/payouts", stage="read", params={"limit": int(limit), "offset": int(offset)})

    # -- writes (never retried here: the engine decides) ------------------------
    def create_destination(self, *, address: str, label: str) -> Dict[str, Any]:
        return self._request("POST", "/v1/payout-destinations", stage="destination", retry=False,
                             body={"kind": "crypto", "asset": ASSET, "network": NETWORK, "address": address,
                                   "label": label[:80]})

    def disable_destination(self, destination_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/v1/payout-destinations/{_safe_id(destination_id, 'pd_')}",
                             stage="destination", retry=False)

    def create_payout(self, *, destination_id: str, amount: Decimal, reference: str) -> Dict[str, Any]:
        return self._request("POST", "/v1/payouts", stage="create", retry=False,
                             body={"destination_id": destination_id, "asset": ASSET, "amount": format(amount, "f"),
                                   "reference": reference[:120]})


def _safe_id(value: str, prefix: str) -> str:
    value = str(value or "")
    if not value.startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9_]{4,40}", value):
        raise PayoutUnavailable("Not a SoncoPay identifier", stage="read")
    return value


def _refusal(status: int, code: Optional[str], stage: str, answer: dict) -> PayoutRefused:
    extra = {k: answer[k] for k in ("destination_id", "usable_from", "field") if k in answer}
    if status == 401 or (status == 403 and code in AUTH_CODES):
        return PayoutRefused(f"SoncoPay refused the API key (HTTP {status})", status_code=status, code=code,
                             stage="auth", extra=extra)
    if status == 403 and code == "api_key_ip_not_allowed":
        return PayoutRefused("SoncoPay refused this server's IP address", status_code=status, code=code,
                             stage=stage, ip_refused=True, extra=extra)
    fault = PLATFORM_FAULTS.get(code or "")
    if fault is None and status == 429:
        fault = "PROVIDER_RATE_LIMITED"
    return PayoutRefused(f"SoncoPay refused the request (HTTP {status})", status_code=status, code=code,
                         stage=stage, platform_fault=fault, extra=extra)


# ---------------------------------------------------------------------------
# Readiness and the owner's authorization
# ---------------------------------------------------------------------------

def _settings_row(db: Session, *, lock: bool = False) -> Optional[CheckoutGatewaySettings]:
    query = db.query(CheckoutGatewaySettings).filter(CheckoutGatewaySettings.id == soncopay_settings.ROW_ID)
    return (query.with_for_update() if lock else query).first()


def blockers(db: Session) -> List[Dict[str, str]]:
    """Everything that stops SoncoPay payouts and destination registration (read-only, no HTTP)."""
    out: List[Dict[str, str]] = []
    row = _settings_row(db)
    state = soncopay_settings.current_state(db)
    if row is None or row.payouts_authorized_at is None:
        out.append({"code": "SONCOPAY_PAYOUTS_NOT_AUTHORIZED",
                    "message": "The owner has not recorded that SoncoPay allows member commission payouts from "
                               "this merchant account."})
    if not state["enabled"]:
        out.append({"code": "SONCOPAY_DISABLED", "message": "SoncoPay is switched off."})
    if state["environment"] != ENVIRONMENT:
        out.append({"code": "SONCOPAY_NOT_LIVE",
                    "message": "SoncoPay is in Test mode: payouts are made only in Live mode."})
    if not soncopay_settings.api_key(db, ENVIRONMENT):
        out.append({"code": "SONCOPAY_LIVE_KEY_MISSING", "message": "The SoncoPay Live API key is not saved."})
    return out


def ready(db: Session) -> bool:
    return not blockers(db)


def client(db: Session) -> PayoutClient:
    key = soncopay_settings.api_key(db, ENVIRONMENT)
    if not key or not ready(db):
        raise PayoutRefused("SoncoPay payouts are not ready", stage="config",
                            platform_fault="SONCOPAY_PAYOUTS_NOT_READY")
    return PayoutClient(key)


def authorization(db: Session) -> Optional[dict]:
    row = _settings_row(db)
    if row is None or row.payouts_authorized_at is None:
        return None
    return {"authorized_at": row.payouts_authorized_at.isoformat(), "authorized_by": row.payouts_authorized_by,
            "note": row.payouts_authorization_note}


def authorize(db: Session, actor: User, *, password: Optional[str], confirmation: str, note: str) -> dict:
    """The owner records that SoncoPay confirmed member (third-party) commission payouts are allowed
    from this merchant account. Super Admin, current password, typed phrase, a note naming the
    confirmation. Changes no payout switch. Commits."""
    from app.services import super_admin

    if not super_admin.is_super_admin(actor):
        raise PermissionError("Only a Super Admin can record the SoncoPay payout authorization.")
    payment_config.require_reauth(actor, password)
    if (confirmation or "").strip() != CONFIRM_AUTHORIZATION:
        raise ValueError(f'Type "{CONFIRM_AUTHORIZATION}" to confirm.')
    note = (note or "").strip()
    if len(note) < 10:
        raise ValueError("Say where SoncoPay confirmed it (at least 10 characters).")
    row = _settings_row(db, lock=True)
    if row is None:
        row = CheckoutGatewaySettings(id=soncopay_settings.ROW_ID)
        db.add(row)
        db.flush()
    row.payouts_authorized_at, row.payouts_authorized_by = datetime.utcnow(), int(actor.id)
    row.payouts_authorization_note = note[:500]
    db.add(AuditTrail(user_id=actor.id, action=AUDIT_AUTHORIZED, table_name="checkout_gateway_settings",
                      record_id=row.id, new_values={"note": note[:500]}))
    db.commit()
    return authorization(db)


def revoke(db: Session, actor: User, *, password: Optional[str]) -> None:
    """Withdraw the authorization: nothing more is registered or paid. Commits."""
    from app.services import super_admin

    if not super_admin.is_super_admin(actor):
        raise PermissionError("Only a Super Admin can withdraw the SoncoPay payout authorization.")
    payment_config.require_reauth(actor, password)
    row = _settings_row(db, lock=True)
    if row is not None and row.payouts_authorized_at is not None:
        old = {"authorized_at": row.payouts_authorized_at.isoformat(), "note": row.payouts_authorization_note}
        row.payouts_authorized_at = row.payouts_authorized_by = row.payouts_authorization_note = None
        db.add(AuditTrail(user_id=actor.id, action=AUDIT_REVOKED, table_name="checkout_gateway_settings",
                          record_id=row.id, old_values=old))
    db.commit()


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

def _audit(db: Session, row: SoncoPayPayoutDestination, old: Optional[str], why: str) -> None:
    db.add(AuditTrail(user_id=None, action=AUDIT_DESTINATION, table_name="soncopay_payout_destinations",
                      record_id=row.id, old_values={"status": old} if old else None,
                      new_values={"status": row.status, "usable": bool(row.usable), "reason": why,
                                  "destination_id": row.destination_id, "user_id": row.user_id,
                                  "wallet_approval_id": row.wallet_approval_id}))


def _current_approvals(db: Session, now: datetime) -> Dict[int, tuple]:
    """{approval id: (user id, address)} of every member whose CURRENT wallet is approved (on hold or
    payable) and who is paid in crypto."""
    from app.services import cashout_service as cs

    out: Dict[int, tuple] = {}
    users = (db.query(User).filter(User.cashout_method == cs.METHOD_CRYPTO, User.is_active.is_(True),
                                   User.usdt_wallet_address.isnot(None)).all())
    for user in users:
        if getattr(user, "is_deleted", False):
            continue
        state = cs.wallet_state(user, now)
        if state.approval_id and state.status in (cs.WALLET_VERIFIED, cs.WALLET_ON_HOLD):
            out[int(state.approval_id)] = (int(user.id), str(state.address))
    return out


def _apply_provider(row: SoncoPayPayoutDestination, data: dict, now: datetime) -> Optional[str]:
    """Copy SoncoPay's view of a destination onto its row. Returns a mismatch reason (and disables the
    row) when the destination is not this wallet."""
    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    if row.destination_id and data.get("id") and str(data["id"]) != row.destination_id:
        return "DESTINATION_ID_MISMATCH"
    if details and ("address" in details) and not same_address(details.get("address"), row.address):
        return "ADDRESS_MISMATCH"
    if details and str(details.get("network") or NETWORK).upper() != NETWORK:
        return "NETWORK_MISMATCH"
    if str(data.get("currency") or details.get("asset") or ASSET).upper() != ASSET:
        return "ASSET_MISMATCH"
    if isinstance(data.get("livemode"), bool) and data["livemode"] is not True:
        return "MODE_MISMATCH"
    status = str(data.get("status") or "").lower()
    row.status = {"pending_confirmation": PENDING, "active": ACTIVE, "disabled": DISABLED,
                  "rejected": REJECTED}.get(status, row.status)
    row.usable = bool(data.get("usable")) and row.status == ACTIVE
    row.usable_from = _time(data.get("usable_from") or data.get("usable_at")) or row.usable_from
    row.confirmed_at = _time(data.get("confirmed_at")) or row.confirmed_at
    row.checked_at = now
    return None


def sync_destinations(db: Session, api: PayoutClient, *, now: Optional[datetime] = None) -> Dict[str, int]:
    """One pass of the destination lifecycle. Commits after each change. Never disables a destination
    of another member, never pays anything."""
    from app.services.commission_payout_hold import payable_clause
    from app.models.affiliate import AffiliateCommission, CommissionStatus

    now = now or datetime.utcnow()
    report: Dict[str, int] = {}

    def count(key: str) -> None:
        report[key] = report.get(key, 0) + 1

    approvals = _current_approvals(db, now)
    rows = db.query(SoncoPayPayoutDestination).filter(SoncoPayPayoutDestination.environment == ENVIRONMENT).all()
    known = {int(r.wallet_approval_id) for r in rows}
    # 1. A newly approved wallet joins the queue.
    for approval_id, (user_id, address) in approvals.items():
        if approval_id not in known:
            row = SoncoPayPayoutDestination(user_id=user_id, wallet_approval_id=approval_id, address=address,
                                            environment=ENVIRONMENT, status=QUEUED, usable=False)
            db.add(row)
            db.flush()
            _audit(db, row, None, "WALLET_APPROVED")
            count("queued")
    db.commit()

    # 2. A destination whose approval is no longer the member's current one is never paid again; the
    #    member's own superseded destination is disabled at SoncoPay (it holds a slot).
    rows = (db.query(SoncoPayPayoutDestination)
            .filter(SoncoPayPayoutDestination.environment == ENVIRONMENT,
                    SoncoPayPayoutDestination.status.in_(LIVE_STATES)).all())
    for row in rows:
        if int(row.wallet_approval_id) in approvals and approvals[int(row.wallet_approval_id)][0] == row.user_id:
            continue
        old = row.status
        row.usable = False
        if row.destination_id:
            try:
                api.disable_destination(row.destination_id)
            except (PayoutRefused, PayoutUnavailable) as exc:
                if getattr(exc, "code", None) not in ("destination_not_found", "destination_disabled"):
                    row.last_error = "DISABLE_FAILED"
                    db.commit()
                    count("disable_failed")
                    continue
            row.disabled_at = now
        row.status, row.last_error = SUPERSEDED, None
        _audit(db, row, old, "WALLET_APPROVAL_CHANGED")
        db.commit()
        count("superseded")

    # 3. Read back what SoncoPay says about registered destinations not usable yet (and, now and then,
    #    the usable ones).
    rows = (db.query(SoncoPayPayoutDestination)
            .filter(SoncoPayPayoutDestination.environment == ENVIRONMENT,
                    SoncoPayPayoutDestination.status.in_((PENDING, ACTIVE)),
                    SoncoPayPayoutDestination.destination_id.isnot(None)).all())
    for row in rows:
        if row.usable and row.checked_at and row.checked_at > now - ACTIVE_RECHECK:
            continue
        try:
            data = api.get_destination(row.destination_id)
        except (PayoutRefused, PayoutUnavailable) as exc:
            row.last_error = (getattr(exc, "code", None) or "READ_FAILED")[:60]
            if getattr(exc, "code", None) == "destination_not_found":
                row.status, row.usable = DISABLED, False
            db.commit()
            count("read_failed")
            continue
        old, was_usable = row.status, row.usable
        problem = _apply_provider(row, data, now)
        if problem:
            row.status, row.usable, row.last_error = DISABLED, False, problem
            logger.error("SoncoPay destination %s does not match its wallet (%s)", row.id, problem)
        else:
            row.last_error = None
        if row.status != old or row.usable != was_usable:
            _audit(db, row, old, problem or "PROVIDER_STATUS")
            count("updated")
        db.commit()

    # 4. Register queued wallets while SoncoPay has a free slot: members with an available commission
    #    first, then the oldest approval.
    queued = (db.query(SoncoPayPayoutDestination)
              .filter(SoncoPayPayoutDestination.environment == ENVIRONMENT,
                      SoncoPayPayoutDestination.status == QUEUED).all())
    if not queued:
        return report
    waiting = {int(u) for (u,) in db.query(AffiliateCommission.user_id)
               .filter(AffiliateCommission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PENDING]),
                       AffiliateCommission.payout_reference.is_(None), payable_clause()).distinct().all()}
    queued.sort(key=lambda r: (0 if r.user_id in waiting else 1, r.id))
    db.rollback()
    try:
        listing = api.all_destinations()
    except (PayoutRefused, PayoutUnavailable):
        count("slots_unknown")
        return report
    items = listing.get("items") if isinstance(listing.get("items"), list) else []
    settings = listing.get("settings") if isinstance(listing.get("settings"), dict) else {}
    if settings.get("api_keys_can_create") is False:
        report["api_keys_cannot_create"] = 1
        return report
    open_count = sum(1 for i in items if isinstance(i, dict) and str(i.get("status")) in OPEN_PROVIDER_STATUSES)
    for row in queued[:REGISTRATIONS_PER_CYCLE]:
        if open_count >= DESTINATION_LIMIT:
            count("waiting_for_slot")
            continue
        row = db.query(SoncoPayPayoutDestination).filter(SoncoPayPayoutDestination.id == row.id).with_for_update().one()
        if row.status != QUEUED:
            db.rollback()
            continue
        try:
            data = api.create_destination(address=row.address, label=f"MyHigh5 member {row.user_id}")
        except PayoutRefused as exc:
            if exc.code == "destination_duplicate" and str(exc.extra.get("destination_id") or "").startswith("pd_"):
                data = _adopt(db, api, row, str(exc.extra["destination_id"]))
                if data is None:
                    db.commit()
                    count("duplicate_unusable")
                    continue
            elif exc.code == "destination_limit":
                row.last_error = "DESTINATION_LIMIT"
                db.commit()
                count("waiting_for_slot")
                open_count = DESTINATION_LIMIT
                continue
            elif exc.code == "destination_invalid":
                old = row.status
                row.status, row.last_error = REJECTED, "DESTINATION_INVALID"
                _audit(db, row, old, "DESTINATION_INVALID")
                db.commit()
                count("rejected")
                continue
            else:
                row.last_error = (exc.code or "REGISTRATION_REFUSED")[:60]
                db.commit()
                count("registration_refused")
                if exc.stage == "auth" or exc.ip_refused or exc.code == "api_key_not_allowed":
                    break
                continue
        except PayoutUnavailable:
            # No answer: the destination may exist. The next pass registers again and SoncoPay answers
            # destination_duplicate with its id, which is then adopted after checking the address.
            row.last_error = "REGISTRATION_NO_ANSWER"
            db.commit()
            count("registration_unknown")
            continue
        old = row.status
        row.destination_id = str(data.get("id") or "")[:40] or row.destination_id
        if not str(row.destination_id or "").startswith("pd_"):
            row.last_error = "NO_DESTINATION_ID"
            db.commit()
            continue
        row.registered_at = row.registered_at or now
        problem = _apply_provider(row, data, now)
        if row.status == QUEUED:
            row.status = PENDING
        if problem:
            row.status, row.usable, row.last_error = DISABLED, False, problem
        else:
            row.last_error = None
        _audit(db, row, old, problem or "REGISTERED")
        db.commit()
        open_count += 1
        count("registered")
    return report


def _adopt(db: Session, api: PayoutClient, row: SoncoPayPayoutDestination, destination_id: str) -> Optional[dict]:
    """SoncoPay already holds these details (an earlier registration whose answer was lost, or one made
    by hand). Used only when its address is this wallet's and no other row holds it."""
    taken = (db.query(SoncoPayPayoutDestination.id)
             .filter(SoncoPayPayoutDestination.destination_id == destination_id,
                     SoncoPayPayoutDestination.id != row.id).first())
    if taken is not None:
        row.last_error = "DUPLICATE_HELD_BY_ANOTHER_ROW"
        return None
    try:
        data = api.get_destination(destination_id)
    except (PayoutRefused, PayoutUnavailable):
        row.last_error = "DUPLICATE_UNREADABLE"
        return None
    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    if not same_address(details.get("address"), row.address):
        row.last_error = "DUPLICATE_ADDRESS_MISMATCH"
        return None
    return data


def destination_for(db: Session, user_id: int, approval_id: Optional[int], address: str) -> Optional[SoncoPayPayoutDestination]:
    if not approval_id:
        return None
    return (db.query(SoncoPayPayoutDestination)
            .filter(SoncoPayPayoutDestination.user_id == int(user_id),
                    SoncoPayPayoutDestination.wallet_approval_id == int(approval_id),
                    SoncoPayPayoutDestination.environment == ENVIRONMENT).first())


def destination_problem(row: Optional[SoncoPayPayoutDestination], address: str, now: datetime) -> Optional[str]:
    """Why this member cannot be paid to their SoncoPay destination now (None = they can)."""
    if row is None or row.status == QUEUED:
        return "DESTINATION_NOT_REGISTERED"
    if row.status == PENDING:
        return "DESTINATION_AWAITING_CONFIRMATION"
    if row.status != ACTIVE or not row.destination_id:
        return "DESTINATION_NOT_USABLE"
    if not same_address(row.address, address):
        return "DESTINATION_NOT_USABLE"
    if not row.usable:
        return "DESTINATION_WAITING_PERIOD"
    return None


# ---------------------------------------------------------------------------
# The payout provider used by app.services.cashout_engine
# ---------------------------------------------------------------------------

def _amount_fields(payout: dict) -> Dict[str, Any]:
    details = payout.get("destination") if isinstance(payout.get("destination"), dict) else {}
    masked = details.get("details") if isinstance(details.get("details"), dict) else {}
    out: Dict[str, Any] = {"provider": "soncopay",
                           "status": STATUS_MAP.get(str(payout.get("status") or "").lower(), "PROCESSING"),
                           "provider_status": str(payout.get("status") or "")[:30]}
    address = payout.get("address") or masked.get("address")
    if address:
        out["address"] = str(address)
    asset, network = str(payout.get("asset") or "").upper(), str(payout.get("network") or "").upper()
    if asset or network:
        out["currency"] = PAYOUT_CURRENCY if (asset, network) in ((ASSET, NETWORK), (ASSET, "")) else \
            f"{asset}:{network}".lower()
    for key in ("amount", "fee"):
        if payout.get(key) not in (None, ""):
            out[key] = str(payout[key])
    if payout.get("tx_hash"):
        out["hash"] = str(payout["tx_hash"])
    if payout.get("reference"):
        out["unique_external_id"] = str(payout["reference"])
    if payout.get("error"):
        out["error"] = str(payout["error"])[:200]
    return out


@dataclass
class _Facts:
    fee: Optional[Decimal] = None
    minimum: Optional[Decimal] = None


def published_fee_and_minimum(answer: dict) -> _Facts:
    """USDT:BSC fee and minimum from GET /v1/payout-fees. The minimum is the HIGHER of the account-wide
    min_payout_usd and the per-asset `limits[USDT:BSC].minimum` (read 2026-10-29: 0.5 and 2). The fee is
    `limits[USDT:BSC].fee`, else `fees[USDT:BSC]`; two different figures are not guessed between."""
    fees = answer.get("fees") if isinstance(answer.get("fees"), dict) else answer.get("payout_fees")
    limits = answer.get("limits") if isinstance(answer.get("limits"), dict) else answer.get("payout_limits")
    asset = limits.get(FEE_KEY) if isinstance(limits, dict) and isinstance(limits.get(FEE_KEY), dict) else {}
    if asset and asset.get("available") is False:
        raise PayoutUnavailable("SoncoPay reports USDT:BSC payouts as unavailable", stage="read")
    listed = fees.get(FEE_KEY) if isinstance(fees, dict) else None
    fee = asset.get("fee") if asset.get("fee") not in (None, "") else listed
    if fee is None:
        raise PayoutUnavailable("SoncoPay publishes no USDT:BSC payout fee for this account", stage="read")
    fee = _decimal(fee, "payout fee")
    if listed is not None and _decimal(listed, "payout fee") != fee:
        raise PayoutUnavailable("SoncoPay publishes two different USDT:BSC payout fees", stage="read")
    minimums = [_decimal(value, "minimum") for value in (answer.get("min_payout_usd"), asset.get("minimum"))
                if value not in (None, "")]
    if not minimums:
        raise PayoutUnavailable("SoncoPay publishes no minimum payout", stage="read")
    return _Facts(fee=fee, minimum=max(minimums))


# The last USDT:BSC fee and minimum read from SoncoPay, for the dashboards (the engine reads its own
# every cycle). Kept in this process only; a read that failed is not retried for LIMITS_RETRY seconds.
LIMITS_MAX_AGE, LIMITS_RETRY = 900.0, 300.0
_limits: Dict[str, Any] = {"facts": None, "read_at": None, "checked": 0.0}


def _remember(facts: _Facts) -> None:
    _limits.update(facts=facts, read_at=datetime.utcnow(), checked=time.monotonic())


def published_limits(db: Session) -> Optional[dict]:
    """{fee, minimum, read_at} of USDT:BSC payouts, at most LIMITS_MAX_AGE old; None when never read.
    Reads SoncoPay (one GET) only when the cached figures are older than that and a Live key is saved."""
    if time.monotonic() - _limits["checked"] > (LIMITS_MAX_AGE if _limits["facts"] else LIMITS_RETRY):
        _limits["checked"] = time.monotonic()
        key = soncopay_settings.api_key(db, ENVIRONMENT)
        if key:
            try:
                _remember(published_fee_and_minimum(PayoutClient(key).payout_fees()))
            except (PayoutRefused, PayoutUnavailable):
                logger.warning("SoncoPay payout fees could not be read for the dashboards")
    facts = _limits["facts"]
    if facts is None:
        return None
    return {"fee": facts.fee, "minimum": facts.minimum, "read_at": _limits["read_at"]}


class SoncoPayPayoutProvider:
    """The engine's provider interface (balance, minimum, network_fee, create_payout, payout_status,
    payout_details, find_payout, check_session, validate_address) on SoncoPay. One per cycle."""

    name = "soncopay"
    # Owner decision 2026-10-29 (Option A): commissions too small to clear SoncoPay's minimum plus fee on
    # their own are paid together, per member (cashout_engine.select_payout).
    accumulates_small_commissions = True

    def __init__(self, db: Session, api: Optional[PayoutClient] = None):
        self._db = db
        self._api = api
        self._facts = _Facts()

    def _client(self) -> PayoutClient:
        if self._api is None:
            self._api = client(self._db)
        return self._api

    def _fees(self) -> _Facts:
        if self._facts.fee is None:
            self._facts = published_fee_and_minimum(self._client().payout_fees())
            _remember(self._facts)
        return self._facts

    @staticmethod
    def _currency(currency: str) -> None:
        if str(currency or "").lower() != PAYOUT_CURRENCY:
            raise PayoutRefused("Only USDT on BSC is paid out", stage="config", platform_fault="PAYOUT_ASSET_NOT_SUPPORTED")

    def balance(self, currency: str) -> Decimal:
        self._currency(currency)
        answer = self._client().balances()
        # What may be spent is `available`; funds on hold are in `balances` too and are never counted.
        for key in ("available", "balances"):
            table = answer.get(key)
            if isinstance(table, dict):
                value = table.get(ASSET, "0")
                if isinstance(value, dict):
                    value = value.get("amount")
                return _decimal(value, "balance")
        return Decimal("0")

    def minimum(self, currency: str) -> Decimal:
        self._currency(currency)
        return self._fees().minimum

    def network_fee(self, currency: str, amount: Decimal) -> Decimal:
        self._currency(currency)
        return self._fees().fee

    def asset_problem(self, currency: str) -> Optional[str]:
        """USDT on BSC only; SoncoPay must publish a payout fee for USDT:BSC (the method is open)."""
        if str(currency or "").lower() != PAYOUT_CURRENCY:
            return "PAYOUT_ASSET_NOT_SUPPORTED"
        try:
            self._fees()
        except Exception:  # noqa: BLE001 - not verified is not sent
            return "PAYOUT_ASSET_UNVERIFIED"
        return None

    def check_session(self) -> None:
        self._client().balances()

    @staticmethod
    def validate_address(address: str, currency: str) -> bool:
        return str(currency or "").lower() == PAYOUT_CURRENCY and bool(EVM_ADDRESS.match(str(address or "").strip()))

    def destination_problem(self, user_id: int, address: str, approval_id: Optional[int],
                            now: Optional[datetime] = None) -> Optional[str]:
        row = destination_for(self._db, user_id, approval_id, address)
        problem = destination_problem(row, address, now or datetime.utcnow())
        self._db.rollback()
        return problem

    def create_payout(self, *, address: str, amount: Decimal, currency: str, external_id: str) -> dict:
        # Last line before money moves: whoever calls, nothing is sent without the activation and
        # the readiness, and only to the usable destination of exactly this address.
        if not payment_config.payout_activation_switch():
            raise PayoutRefused("Automatic payouts are not activated on this server", status_code=403,
                                code="PAYOUTS_NOT_ACTIVATED", stage="create", platform_fault="NOT_ACTIVATED")
        if not ready(self._db):
            self._db.rollback()
            raise PayoutRefused("SoncoPay payouts are not ready", stage="create",
                                platform_fault="SONCOPAY_PAYOUTS_NOT_READY")
        self._currency(currency)
        row = (self._db.query(SoncoPayPayoutDestination)
               .filter(SoncoPayPayoutDestination.environment == ENVIRONMENT,
                       SoncoPayPayoutDestination.status == ACTIVE, SoncoPayPayoutDestination.usable.is_(True),
                       SoncoPayPayoutDestination.destination_id.isnot(None)).all())
        matches = [r for r in row if same_address(r.address, address)]
        destination_id = matches[0].destination_id if len(matches) == 1 else None
        self._db.rollback()
        if destination_id is None:
            raise PayoutRefused("No usable SoncoPay destination for this address", stage="create",
                                platform_fault="DESTINATION_NOT_USABLE")
        amount = Decimal(str(amount))
        if not amount.is_finite() or amount <= 0:
            raise PayoutRefused("Invalid payout amount", stage="create")
        payout = self._client().create_payout(destination_id=destination_id, amount=amount, reference=external_id)
        payout_id = str(payout.get("id") or "")
        if not payout_id.startswith("po_"):
            raise PayoutUnavailable("SoncoPay returned no payout id", stage="create")
        fields = _amount_fields(payout)
        # The payout SoncoPay holds must be THIS one: same amount, USDT on BSC, same destination.
        verified = True
        if "amount" in fields and Decimal(fields["amount"]) != amount:
            verified = False
        if fields.get("currency") not in (None, PAYOUT_CURRENCY):
            verified = False
        if payout.get("destination_id") and str(payout["destination_id"]) != destination_id:
            verified = False
        if not verified:
            logger.error("SoncoPay payout %s does not match what was asked for", payout_id[:40])
        return {"batch_id": payout_id, "status": fields["status"], "verified": verified}

    def payout_details(self, payout_id: str) -> dict:
        return _amount_fields(self._client().get_payout(payout_id))

    def payout_status(self, payout_id: str) -> str:
        return self.payout_details(payout_id)["status"]

    def find_payout(self, reference: str) -> Optional[dict]:
        """Look the reference up in the recent payouts. Not finding it proves nothing."""
        for page in range(3):
            answer = self._client().list_payouts(limit=100, offset=page * 100)
            items = answer.get("items") if isinstance(answer.get("items"), list) else answer.get("data")
            if not isinstance(items, list) or not items:
                return None
            for item in items:
                if isinstance(item, dict) and str(item.get("reference") or "") == reference:
                    found = _amount_fields(item)
                    return {**found, "batch_id": str(item.get("id") or "")}
            if len(items) < 100:
                return None
        return None


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def _mask(address: Optional[str]) -> Optional[str]:
    address = str(address or "")
    return f"{address[:6]}…{address[-4:]}" if len(address) > 12 else address or None


def member_status(db: Session, user: User, now: Optional[datetime] = None) -> dict:
    """What a member is told about their payout destination (no provider call)."""
    from app.services import cashout_service as cs

    now = now or datetime.utcnow()
    state = cs.wallet_state(user, now)
    row = destination_for(db, user.id, state.approval_id, state.address or "") if state.approval_id else None
    problem = destination_problem(row, state.address or "", now) if state.approval_id else None
    messages = {
        None: "Your wallet is ready for automatic payouts.",
        "DESTINATION_NOT_REGISTERED": "Your approved wallet is waiting to be registered with SoncoPay.",
        "DESTINATION_AWAITING_CONFIRMATION": "Your approved wallet is waiting for confirmation by SoncoPay.",
        "DESTINATION_WAITING_PERIOD": "Your wallet is confirmed and in SoncoPay's security waiting period.",
        "DESTINATION_NOT_USABLE": "Your wallet cannot receive payouts at the moment; our team has been told.",
    }
    return {"provider": "soncopay", "network": "USDT on BNB Smart Chain (BEP20)",
            "wallet_status": state.status, "destination_state": problem or ("READY" if state.approval_id else None),
            "message": messages.get(problem) if state.approval_id else None,
            "usable_from": row.usable_from.isoformat() if row is not None and row.usable_from and not row.usable else None,
            "providers_ready": ready(db)}


def admin_view(db: Session, *, read_provider: bool = False) -> dict:
    rows = (db.query(SoncoPayPayoutDestination, User.username)
            .join(User, User.id == SoncoPayPayoutDestination.user_id)
            .order_by(SoncoPayPayoutDestination.id.desc()).limit(500).all())
    counts: Dict[str, int] = {}
    for row, _name in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    view = {
        "blockers": blockers(db), "authorization": authorization(db), "confirmation_phrase": CONFIRM_AUTHORIZATION,
        "asset": ASSET, "network": NETWORK, "destination_limit": DESTINATION_LIMIT, "counts": counts,
        "destinations": [{"id": r.id, "user_id": r.user_id, "username": name, "address": _mask(r.address),
                          "status": r.status, "usable": bool(r.usable),
                          "usable_from": r.usable_from.isoformat() if r.usable_from else None,
                          "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
                          "destination_id": r.destination_id, "last_error": r.last_error}
                         for r, name in rows],
        "provider": None,
    }
    if read_provider and ready(db):
        _limits["checked"] = 0.0                    # an explicit read refreshes the figures below too
        facts: Dict[str, Any] = {}
        try:
            api = client(db)
            balances = api.balances()
            facts["balance"] = {k: (balances.get(k) or {}).get(ASSET) for k in ("balances", "available", "reserved")
                                if isinstance(balances.get(k), dict)}
            fees = api.payout_fees()
            table = fees.get("fees") if isinstance(fees.get("fees"), dict) else fees.get("payout_fees")
            facts["fee"] = (table or {}).get(FEE_KEY) if isinstance(table, dict) else None
            facts["min_payout_usd"] = fees.get("min_payout_usd")
            published = published_fee_and_minimum(fees)
            _remember(published)
            facts["minimum"] = str(published.minimum)
            listing = api.all_destinations()
            items = listing.get("items") if isinstance(listing.get("items"), list) else []
            facts["open_destinations"] = sum(1 for i in items if isinstance(i, dict)
                                             and str(i.get("status")) in OPEN_PROVIDER_STATUSES)
            facts["settings"] = {k: v for k, v in (listing.get("settings") or {}).items()
                                 if k in ("cooldown_hours", "require_saved_destination", "api_auto_confirm",
                                          "second_confirmer", "api_keys_can_create", "waiver_requests")}
        except (PayoutRefused, PayoutUnavailable) as exc:
            facts["error"] = getattr(exc, "code", None) or str(exc)[:120]
        view["provider"] = facts
    view["accumulation"] = accumulation_view(db)
    db.rollback()
    return view


def accumulation_view(db: Session) -> dict:
    """Owner decision 2026-10-29 (Option A): the threshold from SoncoPay's last published USDT:BSC fee and
    minimum, every Crypto Cashout member's accumulating commissions against it, and the latest combined
    payouts with the commissions each carries."""
    from app.services import cashout_engine as engine

    published = published_limits(db)
    threshold = (engine.payout_threshold(payment_config.load(db), published["minimum"], published["fee"])
                 if published is not None else None)
    return {"threshold": f"{threshold:.2f}" if threshold is not None else None,
            "fee": str(published["fee"]) if published is not None else None,
            "minimum": str(published["minimum"]) if published is not None else None,
            "read_at": published["read_at"].isoformat() + "Z" if published is not None else None,
            "members": engine.accumulation_overview(db, threshold),
            "payouts": engine.accumulated_payouts(db)}
