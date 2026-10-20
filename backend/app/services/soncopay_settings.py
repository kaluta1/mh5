"""SoncoPay customer payment collection: the settings a Super Admin manages in
the Admin Panel (Finance & Payments > SoncoPay Configuration).

The database is the ONLY source: no SoncoPay value is read from the server
environment, so no SSH access or .env change is needed, or has any effect.

Settings, all saved with ONE form:
  * SoncoPay on/off and its environment (Test or Live), in
    checkout_gateway_settings (one row). No row = off, Test.
  * The default customer checkout gateway (NOWPayments or SoncoPay). No row =
    NOWPayments. SoncoPay cannot be made the default until its checkout is
    implemented (CHECKOUT_IMPLEMENTED); NOWPayments checkout is never switched
    off from here.
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

The SoncoPay webhook is NOT operational: its signature scheme is not yet
confirmed by SoncoPay's documentation, so every callback is refused
(WEBHOOK_OPERATIONAL) and no payment event is processed. There is no
connection test either (CONNECTION_TEST_AVAILABLE) until a documented,
side-effect-free endpoint is known.
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

# What is not built yet, said in one place. Each gate opens only with the
# implementation that makes it safe.
CHECKOUT_IMPLEMENTED = False          # SoncoPay checkout (payment creation) exists
WEBHOOK_OPERATIONAL = False           # verified SoncoPay webhook signatures exist
CONNECTION_TEST_AVAILABLE = False     # a documented, side-effect-free SoncoPay endpoint is known
NOT_DOCUMENTED = ("SoncoPay's API documentation has not been provided yet, so there is no documented "
                  "endpoint to test against.")

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


def default_checkout_provider(db: Session) -> str:
    """The gateway new customer checkouts use by default. NOWPayments unless
    SoncoPay checkout exists, is on and was chosen (fail closed to NOWPayments)."""
    state = _state(_row(db))
    if state["default_provider"] == PROVIDER and CHECKOUT_IMPLEMENTED and state["enabled"]:
        return PROVIDER
    return NOWPAYMENTS


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
        if not _decrypt(stored.get(spec.name)):
            return f"Save the {spec.label} first."
    return None


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
    row = _row(db)
    state = _state(row)
    stored = _stored(db)
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
        "default_provider": state["default_provider"],
        "default_provider_in_force": default_checkout_provider(db),
        "checkout_providers": [
            {"provider": NOWPAYMENTS, "label": "NOWPayments", "available": True},
            {"provider": PROVIDER, "label": "SoncoPay", "available": CHECKOUT_IMPLEMENTED,
             "note": None if CHECKOUT_IMPLEMENTED else "SoncoPay checkout is not implemented yet."},
        ],
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
        if new_default == PROVIDER and not CHECKOUT_IMPLEMENTED:
            raise refuse("CHECKOUT_NOT_AVAILABLE", "SoncoPay cannot be the default checkout yet: its checkout is "
                                                   "not implemented.", FIELD_DEFAULT)
        changed.append(FIELD_DEFAULT)
    if new_default == PROVIDER and not new_enabled:
        raise refuse("DEFAULT_PROVIDER_OFF", "SoncoPay is the default checkout: make NOWPayments the default "
                                             "before switching SoncoPay off.", FIELD_ENABLED)

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
