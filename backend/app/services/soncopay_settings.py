"""SoncoPay customer payment collection: the settings a Super Admin manages in
the Admin Panel (Finance & Payments > SoncoPay Configuration).

The database is the ONLY source: no SoncoPay value is read from the server
environment, so no SSH access or .env change is needed, or has any effect.

Settings, all saved with ONE form:
  * SoncoPay on/off and its environment (Test or Live), in
    checkout_gateway_settings (one row). No row = off, Test.
  * The default customer checkout gateway (NOWPayments or SoncoPay). No row =
    NOWPayments. Only a gateway that can take a new payment may be chosen.
    The choice is kept as it is when that gateway is later switched off or
    stops being ready: new payments are then unavailable (never sent to the
    other gateway) until it is ready again or another ready gateway is chosen
    (app.services.checkout_routing). A payment keeps the gateway it was
    created with. NOWPayments checkout is never switched off from here.
  * An API key and a webhook signing secret PER ENVIRONMENT, stored ONLY as
    AES-256-GCM ciphertext in payment_credentials (provider "soncopay") with
    the dedicated PAYMENT_SETTINGS_ENCRYPTION_KEY and a purpose of their own
    that names the environment: a Test value can never be read as a Live one,
    nor as a NOWPayments or Kaluta credential. A saved value is never shown
    again, logged, audited or returned: the Admin Panel learns whether one is
    saved and readable, and the last four characters of an API key. Saving
    replaces; a blank field keeps what is saved.

Who may: viewing needs a Super Admin or the manage_payment_settings
permission. Every change needs a Super Admin and the current password, and
writes one audit_trails row that names what changed, never a secret.

Separation: nothing here reads or writes payment_settings, the NOWPayments
credentials or the payout engine. Changing these settings can never change
NOWPayments checkout or automatic commission payouts. SoncoPay is used for
customer payment collection only: no payout permission exists for it.

Checkout, webhook and status reading are in app.services.soncopay_payments
(the API in app.services.soncopay_client). The connection test reads GET
/v1/methods, which has no side effect.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.checkout_gateway import CheckoutGatewaySettings
from app.models.payment_config import PaymentCredential
from app.services import payment_config, payment_crypto, super_admin

logger = logging.getLogger(__name__)

PROVIDER = "soncopay"
NOWPAYMENTS = "nowpayments"
CHECKOUT_PROVIDERS = (NOWPAYMENTS, PROVIDER)
DEFAULT_CHECKOUT_PROVIDER = NOWPAYMENTS
ENVIRONMENTS = ("test", "live")
DEFAULT_ENVIRONMENT = "test"
ROW_ID = 1
_PURPOSE = "mh5-payments:soncopay-credential:"
VIEW_PERMISSION = payment_config.PERMISSION_MANAGE
WEBHOOK_PATH = "/api/v1/webhooks/soncopay"

# What is built, said in one place (all three implemented 2026-10-21 against the
# official API v1 documentation). Turning one back to False closes it again.
CHECKOUT_IMPLEMENTED = True           # SoncoPay checkout (payment creation, app.services.soncopay_payments)
WEBHOOK_OPERATIONAL = True            # timestamped signatures verified (app.services.soncopay_payments)
CONNECTION_TEST_AVAILABLE = True      # GET /v1/methods: documented, no side effect
NOT_DOCUMENTED = "The connection test is not available."
KEY_PREFIX = {"test": "sp_test_", "live": "sp_live_"}

# Switching to the Live environment is said on purpose.
CONFIRM_LIVE = "USE SONCOPAY LIVE"

AUDIT_SETTINGS = "SONCOPAY_SETTINGS_CHANGED"
FIELD_ENABLED, FIELD_ENVIRONMENT, FIELD_DEFAULT = "SONCOPAY_ENABLED", "SONCOPAY_ENVIRONMENT", "DEFAULT_CHECKOUT_PROVIDER"


@dataclass(frozen=True)
class CredentialSpec:
    name: str
    environment: str
    kind: str               # api_key | webhook_secret
    label: str
    min_length: int


CREDENTIALS: Dict[str, CredentialSpec] = {c.name: c for c in (
    CredentialSpec("TEST_API_KEY", "test", "api_key", "Test API key", 16),
    CredentialSpec("TEST_WEBHOOK_SECRET", "test", "webhook_secret", "Test webhook signing secret", 16),
    CredentialSpec("LIVE_API_KEY", "live", "api_key", "Live API key", 16),
    CredentialSpec("LIVE_WEBHOOK_SECRET", "live", "webhook_secret", "Live webhook signing secret", 16),
)}


def credential_name(environment: str, kind: str) -> str:
    return f"{environment.upper()}_{kind.upper()}"


class SoncoPaySettingsError(ValueError):
    def __init__(self, code: str, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.field = field


# ---------------------------------------------------------------------------
# Who may
# ---------------------------------------------------------------------------

def can_view(user) -> bool:
    return super_admin.is_super_admin(user) or payment_config.has_permission(user, VIEW_PERMISSION)


def can_change(user) -> bool:
    """Sensitive payment credentials: a Super Admin only."""
    return super_admin.is_super_admin(user)


def _authorize(actor, password: Optional[str]) -> None:
    if not can_change(actor):
        raise SoncoPaySettingsError("SUPER_ADMIN_REQUIRED", "Only a Super Admin can change the SoncoPay settings.")
    try:
        payment_config.require_reauth(actor, password)
    except payment_config.PaymentConfigError as exc:
        raise SoncoPaySettingsError(exc.code, str(exc)) from None


# ---------------------------------------------------------------------------
# The values in force (database only)
# ---------------------------------------------------------------------------

def _row(db: Session, *, lock: bool = False) -> Optional[CheckoutGatewaySettings]:
    query = db.query(CheckoutGatewaySettings).filter(CheckoutGatewaySettings.id == ROW_ID)
    if lock:
        query = query.with_for_update().populate_existing()
    return query.first()


def _stored(db: Session) -> Dict[str, PaymentCredential]:
    return {r.name: r for r in db.query(PaymentCredential).filter(PaymentCredential.provider == PROVIDER).all()
            if r.name in CREDENTIALS}


def _decrypt(row: Optional[PaymentCredential]) -> Optional[str]:
    if row is None:
        return None
    try:
        return payment_crypto.decrypt(row.ciphertext, _PURPOSE + row.name) or None
    except payment_crypto.PaymentCryptoError:
        return None


def _state(row: Optional[CheckoutGatewaySettings]) -> Dict[str, Any]:
    if row is None:
        return {"enabled": False, "environment": DEFAULT_ENVIRONMENT, "default_provider": DEFAULT_CHECKOUT_PROVIDER}
    environment = row.soncopay_environment if row.soncopay_environment in ENVIRONMENTS else DEFAULT_ENVIRONMENT
    default = row.default_provider if row.default_provider in CHECKOUT_PROVIDERS else DEFAULT_CHECKOUT_PROVIDER
    return {"enabled": bool(row.soncopay_enabled), "environment": environment, "default_provider": default}


def current_state(db: Session) -> Dict[str, Any]:
    """SoncoPay on/off, its environment and the STORED default gateway (no row = off, Test, NOWPayments)."""
    return _state(_row(db))


def default_checkout_provider(db: Session) -> Optional[str]:
    """The gateway new customer checkouts use: the stored default while it can take a
    payment, otherwise None. Never the other gateway (app.services.checkout_routing)."""
    from app.services import checkout_routing

    return checkout_routing.new_payment_gateway(db)


def webhook_url() -> Optional[str]:
    base = (settings.BACKEND_PUBLIC_URL or "").strip().rstrip("/")
    return f"{base}{WEBHOOK_PATH}" if base else None


def _url_shaped(value: Optional[str]) -> bool:
    return bool(value) and str(value).strip().lower().startswith(("http://", "https://"))


def _clean(spec: CredentialSpec, value: Any) -> str:
    text = str(value or "").translate(dict.fromkeys(map(ord, "​‌‍⁠﻿"))).strip()
    if any(ch.isspace() for ch in text):
        raise SoncoPaySettingsError("INVALID_VALUE", f"{spec.label}: must not contain spaces.", field=spec.name)
    if _url_shaped(text):
        # The known mistake: the webhook URL pasted where the signing secret belongs.
        raise SoncoPaySettingsError("INVALID_VALUE", f"{spec.label}: this looks like a URL, not a key or secret.",
                                    field=spec.name)
    if len(text) < spec.min_length or len(text) > 512:
        raise SoncoPaySettingsError("INVALID_VALUE", f"{spec.label}: the value is too short or too long.",
                                    field=spec.name)
    if spec.kind == "api_key" and not text.startswith(KEY_PREFIX[spec.environment]):
        # A Live key saved as the Test key (or the reverse) would mix real and test money.
        raise SoncoPaySettingsError("INVALID_VALUE", f"{spec.label}: a SoncoPay {spec.environment.title()} key "
                                                     f"starts with {KEY_PREFIX[spec.environment]}.", field=spec.name)
    return text


def _masked(spec: CredentialSpec, value: Optional[str]) -> Optional[str]:
    """An API key's last four characters, to tell which key is saved. A signing secret: nothing."""
    if not value or spec.kind != "api_key":
        return None
    return "••••" + value[-4:]


def _environment_ready(stored: Dict[str, PaymentCredential], environment: str) -> Optional[str]:
    """Why this environment's credentials cannot be used (None when they can)."""
    for kind in ("api_key", "webhook_secret"):
        spec = CREDENTIALS[credential_name(environment, kind)]
        value = _decrypt(stored.get(spec.name))
        if not value:
            return f"Save the {spec.label} first."
        if kind == "api_key" and not value.startswith(KEY_PREFIX[environment]):
            return f"The saved {spec.label} does not start with {KEY_PREFIX[environment]}: save the right key."
    return None


def api_key(db: Session, environment: str) -> Optional[str]:
    """The API key of one environment, for the server-side SoncoPay client only. Never returned to a browser."""
    if environment not in ENVIRONMENTS:
        return None
    value = _decrypt(_stored(db).get(credential_name(environment, "api_key")))
    return value if value and value.startswith(KEY_PREFIX[environment]) else None


def webhook_secrets(db: Session) -> Dict[str, str]:
    """The signing secret of each environment that has one: {"test": ..., "live": ...}."""
    stored = _stored(db)
    out: Dict[str, str] = {}
    for environment in ENVIRONMENTS:
        value = _decrypt(stored.get(credential_name(environment, "webhook_secret")))
        if value:
            out[environment] = value
    return out


def checkout_problem(db: Session) -> Optional[str]:
    """Why SoncoPay cannot take a NEW payment now (None = it can)."""
    if not CHECKOUT_IMPLEMENTED:
        return "SoncoPay checkout is not implemented."
    state = _state(_row(db))
    if not state["enabled"]:
        return "SoncoPay is switched off."
    problem = _environment_ready(_stored(db), state["environment"])
    return f"{state['environment'].title()} environment: {problem}" if problem else None


def checkout_environment(db: Session) -> Optional[str]:
    """The environment a NEW SoncoPay payment would use, or None when SoncoPay must not
    take new payments (off, not implemented, or that environment not ready)."""
    if checkout_problem(db) is not None:
        return None
    return _state(_row(db))["environment"]


# ---------------------------------------------------------------------------
# Admin Panel
# ---------------------------------------------------------------------------

def _last_change(db: Session) -> Optional[dict]:
    row = (db.query(AuditTrail).filter(AuditTrail.action == AUDIT_SETTINGS)
           .order_by(AuditTrail.id.desc()).first())
    if row is None:
        return None
    return {"at": row.timestamp.isoformat() if row.timestamp else None, "by_user_id": row.user_id,
            "changed": sorted((row.new_values or {}).get("changed") or [])}


def view(db: Session, actor) -> dict:
    """Everything the Admin Panel shows. Never the value of a key or secret."""
    from app.services import checkout_routing

    row = _row(db)
    state = _state(row)
    stored = _stored(db)
    gateways = checkout_routing.states(db)
    effective = checkout_routing.effective_default(db)
    credentials: List[dict] = []
    for name, spec in CREDENTIALS.items():
        saved = stored.get(name)
        value = _decrypt(saved)
        credentials.append({
            "name": name, "environment": spec.environment, "kind": spec.kind, "label": spec.label,
            "configured": value is not None,
            "saved": saved is not None, "saved_readable": (value is not None) if saved is not None else None,
            "saved_at": saved.set_at.isoformat() if saved is not None and saved.set_at else None,
            "masked": _masked(spec, value),
        })
    return {
        "provider": PROVIDER,
        "source": "database",
        "enabled": state["enabled"],
        "environment": state["environment"],
        "environments": list(ENVIRONMENTS),
        # The default a Super Admin chose (kept as it is) and the one in force for new payments:
        # the chosen one while it is ready, otherwise "none" (never the other gateway).
        "default_provider": state["default_provider"],
        "default_provider_in_force": effective.gateway or "none",
        "default_unavailable_reason": effective.reason,
        # Each gateway: its master switch, whether it can take a new payment now (and why not),
        # and what it does. "available" = may be chosen as the default now.
        "gateways": [
            {"provider": g.gateway, "label": checkout_routing.LABELS[g.gateway], "enabled": g.enabled,
             "ready": g.ready, "reason": g.reason, "environment": g.environment,
             "incoming": "Member payments",
             "outgoing": ("Automatic USDT BEP20 commission payouts (managed in Crypto Cashout)"
                          if g.gateway == NOWPAYMENTS else "Not supported")}
            for g in gateways.values()],
        "checkout_providers": [
            {"provider": g.gateway, "label": checkout_routing.LABELS[g.gateway], "available": g.ready,
             "note": g.reason}
            for g in gateways.values()],
        "credentials": credentials,
        "ready": {env: _environment_ready(stored, env) is None for env in ENVIRONMENTS},
        "webhook_url": webhook_url(),
        "webhook_operational": WEBHOOK_OPERATIONAL,
        "connection_test": {"available": CONNECTION_TEST_AVAILABLE,
                            "reason": None if CONNECTION_TEST_AVAILABLE else NOT_DOCUMENTED},
        "live_confirmation": CONFIRM_LIVE,
        "encryption_key_configured": payment_crypto.key_configured(),
        "version": int(row.version) if row is not None else 0,
        "can_change": can_change(actor),
        "last_change": _last_change(db),
    }


def update(db: Session, actor, *, password: Optional[str], enabled: Optional[bool] = None,
           environment: Optional[str] = None, default_provider: Optional[str] = None,
           credentials: Optional[Dict[str, Optional[str]]] = None, confirmation: Optional[str] = None,
           expected_version: Optional[int] = None, ip: Optional[str] = None,
           now: Optional[datetime] = None) -> dict:
    """Save the Admin Panel form. Absent (None) keeps a setting; a blank
    credential keeps the saved one. Everything is validated first and saved in
    ONE commit; on any refusal nothing is changed."""
    now = now or datetime.utcnow()
    if not can_change(actor):
        raise SoncoPaySettingsError("SUPER_ADMIN_REQUIRED", "Only a Super Admin can change the SoncoPay settings.")
    unknown = sorted(set(credentials or {}) - set(CREDENTIALS))
    if unknown:
        raise SoncoPaySettingsError("INVALID_FIELD", "Unknown setting: " + ", ".join(unknown))
    if environment is not None and environment not in ENVIRONMENTS:
        raise SoncoPaySettingsError("INVALID_VALUE", "The environment is Test or Live.", field=FIELD_ENVIRONMENT)
    if default_provider is not None and default_provider not in CHECKOUT_PROVIDERS:
        raise SoncoPaySettingsError("INVALID_VALUE", "The default checkout is NOWPayments or SoncoPay.",
                                    field=FIELD_DEFAULT)
    cleaned = {name: _clean(CREDENTIALS[name], value) for name, value in (credentials or {}).items()
               if str(value or "").strip()}
    if enabled is None and environment is None and default_provider is None and not cleaned:
        raise SoncoPaySettingsError("NOTHING_TO_CHANGE", "Nothing to save.")
    _authorize(actor, password)
    if cleaned and not payment_crypto.key_configured():
        raise SoncoPaySettingsError("ENCRYPTION_KEY_MISSING",
                                    "PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured on the server, so a key or "
                                    "secret cannot be stored securely. Nothing was changed.")

    def refuse(code: str, message: str, field: Optional[str] = None) -> SoncoPaySettingsError:
        db.rollback()
        return SoncoPaySettingsError(code, message + " Nothing was changed.", field=field)

    row = _row(db, lock=True)
    if row is None:
        # The first save creates the single row (the defaults). Two first saves at once:
        # the second waits for the first, then finds its row (and is refused as stale).
        if db.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert

            db.execute(insert(CheckoutGatewaySettings.__table__)
                       .values(id=ROW_ID, version=0, created_at=now, updated_at=now)
                       .on_conflict_do_nothing(index_elements=["id"]))
        else:
            db.add(CheckoutGatewaySettings(id=ROW_ID, version=0))
            db.flush()
        row = _row(db, lock=True)
    if expected_version is not None and int(expected_version) != int(row.version):
        raise refuse("STALE", "The SoncoPay settings were changed by somebody else. Reload and try again.")

    old = _state(row)
    changed: List[str] = []
    stored = _stored(db)
    for name, value in cleaned.items():
        ciphertext = payment_crypto.encrypt(value, _PURPOSE + name)
        existing = stored.get(name)
        if existing is None:
            db.add(PaymentCredential(provider=PROVIDER, name=name, ciphertext=ciphertext, set_at=now,
                                     set_by=actor.id))
        else:
            existing.ciphertext, existing.set_at, existing.set_by = ciphertext, now, actor.id
        changed.append(name)
    db.flush()
    stored = _stored(db)

    new_environment = environment if environment is not None else old["environment"]
    new_enabled = bool(enabled) if enabled is not None else old["enabled"]
    new_default = default_provider if default_provider is not None else old["default_provider"]

    if new_environment != old["environment"]:
        if new_environment == "live" and (confirmation or "").strip() != CONFIRM_LIVE:
            raise refuse("CONFIRMATION_REQUIRED", f'To switch SoncoPay to Live, type "{CONFIRM_LIVE}".',
                         FIELD_ENVIRONMENT)
        changed.append(FIELD_ENVIRONMENT)
    if new_enabled != old["enabled"]:
        changed.append(FIELD_ENABLED)
    if new_enabled and (FIELD_ENABLED in changed or FIELD_ENVIRONMENT in changed or cleaned):
        # On, in the environment it will use: that environment's key and secret must be saved and readable.
        problem = _environment_ready(stored, new_environment)
        if problem:
            raise refuse("NOT_READY", f"SoncoPay cannot be on in {new_environment.title()} yet. {problem}",
                         FIELD_ENABLED)
    if new_default != old["default_provider"]:
        # Only a gateway that can take a new payment NOW, as it will be after this save, may become
        # the default (checked here, on the server, whatever the form sent).
        if new_default == PROVIDER and not CHECKOUT_IMPLEMENTED:
            raise refuse("CHECKOUT_NOT_AVAILABLE", "SoncoPay cannot be the default checkout yet: its checkout is "
                                                   "not implemented.", FIELD_DEFAULT)
        if new_default == PROVIDER:
            problem = _environment_ready(stored, new_environment)
            if not new_enabled or problem:
                reason = problem or "Switch SoncoPay on first."
                raise refuse("NOT_READY", "SoncoPay can be the default checkout only while it is on and the "
                                          f"{new_environment.title()} key and secret are saved. {reason}", FIELD_DEFAULT)
        else:
            # Lock order: this row first (above), then the NOWPayments settings row, SHARED: switching
            # NOWPayments off waits until this save is done (and is then reflected at once in the
            # effective default). payment_config never locks this row, so the two cannot deadlock.
            problem = payment_config.nowpayments_checkout_problem(db, payment_config.load_shared(db))
            if problem:
                raise refuse("NOT_READY", f"NOWPayments can be the default checkout only while it can take new "
                                          f"payments. {problem}", FIELD_DEFAULT)
        changed.append(FIELD_DEFAULT)
    # Switching off the gateway that is the default is allowed: the default stays as chosen, and no
    # new payment is possible until it is on again or a Super Admin chooses a ready gateway. Nothing
    # is chosen automatically.

    if not changed:
        db.rollback()
        return view(db, actor)
    row.soncopay_environment = new_environment
    row.soncopay_enabled = new_enabled
    row.default_provider = new_default
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    new = _state(row)
    db.add(AuditTrail(
        table_name="checkout_gateway_settings", record_id=ROW_ID, action=AUDIT_SETTINGS, user_id=actor.id,
        ip_address=(ip or None), timestamp=now,
        # Which settings changed and the values that are not secret. Never a key or a secret.
        old_values=old, new_values={**new, "changed": sorted(changed), "version": int(row.version)}))
    db.commit()
    logger.info("SoncoPay settings changed by account %s: %s", actor.id, ", ".join(sorted(changed)))
    return view(db, actor)
