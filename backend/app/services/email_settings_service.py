"""Email settings, secret resolution and the send policy (EMAIL-1).

Everything that decides WHETHER an email may go out lives here, in one place:

    1. the event exists in the registry          (email_events)
    2. the provider is enabled and has a key
    3. Emergency Stop is not active
    4. non-critical event -> the normal master switch is on
    5. the event's own switch is on

Four separate controls, never collapsed into one boolean:
    resend_enabled   may the provider be used?
    email_enabled    should normal (non-critical) email go out?
    emergency_stop   should ANY email go out?
    event switch     should this event go out?

API key resolution, per send (no restart needed after a change):
    Admin override (encrypted in email_settings) -> RESEND_API_KEY -> none
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import formataddr, parseaddr
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.email import EmailEventSetting, EmailSettings
from app.services import email_crypto
from app.services.email_events import EMAIL_EVENTS, EmailEventDefinition

logger = logging.getLogger(__name__)

PERMISSION_MANAGE_EMAIL_SETTINGS = "manage_email_settings"
SETTINGS_ROW_ID = 1

KEY_SOURCE_OVERRIDE = "admin_override"
KEY_SOURCE_ENV = "environment"
KEY_SOURCE_NONE = "none"

# Suppression / failure reasons recorded on a delivery.
REASON_PROVIDER_DISABLED = "provider_disabled"
REASON_PROVIDER_UNCONFIGURED = "provider_unconfigured"
REASON_EMERGENCY_STOP = "emergency_stop"
REASON_MASTER_DISABLED = "master_disabled"
REASON_EVENT_DISABLED = "event_disabled"
REASON_INVALID_RECIPIENT = "invalid_recipient"
REASON_RATE_LIMITED = "rate_limited"

_EMAIL_RE = re.compile(r"^[^@\s<>\"',;]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                       r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")


def valid_email(address: Optional[str]) -> bool:
    text = (address or "").strip()
    return bool(text) and len(text) <= 320 and "\n" not in text and "\r" not in text and bool(_EMAIL_RE.match(text))


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------

def can_manage_email_settings(user) -> bool:
    """Only a role that EXPLICITLY holds manage_email_settings. Never implied by
    is_admin or by the 'all' wildcard, and never assigned automatically."""
    if user is None or not getattr(user, "is_active", True):
        return False
    role = getattr(user, "role", None)
    if role is None:
        return False
    names = {p.name for p in (role.permissions or [])}
    if getattr(role, "inherit_from", None) is not None:
        names |= set(role.inherit_from.get_all_permissions())
    return PERMISSION_MANAGE_EMAIL_SETTINGS in names


# ---------------------------------------------------------------------------
# Settings row
# ---------------------------------------------------------------------------

def get_settings(db: Session) -> EmailSettings:
    """The single configuration row. A missing row means defaults (a transient,
    unsaved object); it is created on the first change."""
    row = db.query(EmailSettings).filter(EmailSettings.id == SETTINGS_ROW_ID).first()
    if row is None:
        row = EmailSettings(email_enabled=True, emergency_stop=False, resend_enabled=True)
    return row


def get_settings_for_update(db: Session) -> EmailSettings:
    row = db.query(EmailSettings).filter(EmailSettings.id == SETTINGS_ROW_ID).first()
    if row is None:
        row = EmailSettings(id=SETTINGS_ROW_ID, email_enabled=True, emergency_stop=False, resend_enabled=True)
        db.add(row)
        db.flush()
    return row


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def _env_api_key() -> str:
    return (os.getenv("RESEND_API_KEY") or settings.RESEND_API_KEY or "").strip()


def resolve_api_key(row: EmailSettings) -> Tuple[Optional[str], str]:
    """(key, source). An override that cannot be decrypted (the encryption key is
    missing or was changed) is ignored with a warning, never guessed."""
    if row.resend_api_key_ciphertext:
        try:
            return email_crypto.decrypt_secret(row.resend_api_key_ciphertext), KEY_SOURCE_OVERRIDE
        except email_crypto.EmailCryptoError:
            logger.error("Resend API key override cannot be decrypted; falling back to the environment key")
    env_key = _env_api_key()
    if env_key:
        return env_key, KEY_SOURCE_ENV
    return None, KEY_SOURCE_NONE


def override_readable(row: EmailSettings) -> bool:
    if not row.resend_api_key_ciphertext:
        return True
    try:
        email_crypto.decrypt_secret(row.resend_api_key_ciphertext)
        return True
    except email_crypto.EmailCryptoError:
        return False


def set_api_key_override(db: Session, row: EmailSettings, api_key: str, *, actor_id: Optional[int],
                         now: Optional[datetime] = None) -> None:
    row.resend_api_key_ciphertext = email_crypto.encrypt_secret(api_key)
    row.resend_api_key_last4 = api_key[-4:]
    row.resend_api_key_updated_at = now or datetime.utcnow()
    row.resend_api_key_updated_by = actor_id
    row.updated_by = actor_id


def clear_api_key_override(row: EmailSettings, *, actor_id: Optional[int], now: Optional[datetime] = None) -> None:
    row.resend_api_key_ciphertext = None
    row.resend_api_key_last4 = None
    row.resend_api_key_updated_at = now or datetime.utcnow()
    row.resend_api_key_updated_by = actor_id
    row.updated_by = actor_id


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------

def _env_sender() -> Tuple[str, str]:
    name, address = parseaddr(settings.EMAIL_FROM or "")
    return (name or settings.EMAIL_FROM_NAME or "MyHigh5"), address


def effective_sender(row: EmailSettings) -> Tuple[str, str]:
    env_name, env_address = _env_sender()
    return (row.from_name or env_name), (row.from_address or env_address)


def from_header(row: EmailSettings) -> str:
    name, address = effective_sender(row)
    return formataddr((name, address))


def support_address(row: EmailSettings) -> str:
    return row.support_address or _env_sender()[1] or "infos@myhigh5.com"


def allowed_from_domains() -> List[str]:
    """Domains an Admin may send from: EMAIL_ALLOWED_FROM_DOMAINS, or the domain
    of EMAIL_FROM when that variable is empty. A newly verified domain is added
    through configuration, not through a code change."""
    raw = (os.getenv("EMAIL_ALLOWED_FROM_DOMAINS") or settings.EMAIL_ALLOWED_FROM_DOMAINS or "").strip()
    domains = [d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()]
    if not domains:
        env_address = _env_sender()[1]
        if "@" in env_address:
            domains = [env_address.rsplit("@", 1)[1].lower()]
    return domains


def from_address_allowed(address: str) -> bool:
    domains = allowed_from_domains()
    if not domains:
        return True
    return address.rsplit("@", 1)[-1].lower() in domains


# ---------------------------------------------------------------------------
# Event switches
# ---------------------------------------------------------------------------

def event_overrides(db: Session) -> Dict[str, bool]:
    return {r.event_key: bool(r.enabled) for r in db.query(EmailEventSetting).all()}


def event_enabled(db: Session, definition: EmailEventDefinition) -> bool:
    row = db.query(EmailEventSetting).filter(EmailEventSetting.event_key == definition.key).first()
    return bool(row.enabled) if row is not None else definition.default_enabled


def set_event_enabled(db: Session, definition: EmailEventDefinition, enabled: bool, *,
                      actor_id: Optional[int]) -> bool:
    """Store the override; returns the previous effective value."""
    row = db.query(EmailEventSetting).filter(EmailEventSetting.event_key == definition.key).first()
    previous = bool(row.enabled) if row is not None else definition.default_enabled
    if row is None:
        db.add(EmailEventSetting(event_key=definition.key, enabled=enabled, updated_by=actor_id))
    else:
        row.enabled = enabled
        row.updated_by = actor_id
    return previous


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SendDecision:
    allowed: bool
    reason: Optional[str] = None
    # FAILED: the system could not send (provider). SUPPRESSED: a switch said no.
    status: Optional[str] = None
    api_key: Optional[str] = None


def provider_decision(row: EmailSettings) -> SendDecision:
    if not row.resend_enabled:
        return SendDecision(False, REASON_PROVIDER_DISABLED, "FAILED")
    key, _source = resolve_api_key(row)
    if not key:
        return SendDecision(False, REASON_PROVIDER_UNCONFIGURED, "FAILED")
    return SendDecision(True, api_key=key)


def evaluate(db: Session, definition: Optional[EmailEventDefinition], *,
             row: Optional[EmailSettings] = None) -> SendDecision:
    """The one send policy. `definition=None` is the Admin test email: it needs
    a usable provider and no Emergency Stop, and has no switch of its own."""
    row = row or get_settings(db)
    provider = provider_decision(row)
    if not provider.allowed:
        return provider
    if row.emergency_stop:
        return SendDecision(False, REASON_EMERGENCY_STOP, "SUPPRESSED")
    if definition is None:
        return provider
    if not definition.critical and not row.email_enabled:
        return SendDecision(False, REASON_MASTER_DISABLED, "SUPPRESSED")
    if not event_enabled(db, definition):
        return SendDecision(False, REASON_EVENT_DISABLED, "SUPPRESSED")
    return provider


# ---------------------------------------------------------------------------
# Audit (who / what / when - never a secret, a ciphertext or a token)
# ---------------------------------------------------------------------------

_FORBIDDEN_AUDIT_KEYS = ("key", "secret", "cipher", "token", "password", "payload")


def audit(db: Session, *, actor_id: Optional[int], action: str, old: Optional[dict] = None,
          new: Optional[dict] = None, ip: Optional[str] = None, record_id: int = SETTINGS_ROW_ID) -> None:
    for values in (old or {}), (new or {}):
        for name in values:
            if any(part in name.lower() for part in _FORBIDDEN_AUDIT_KEYS):
                raise ValueError(f"refusing to audit a sensitive field: {name}")
    db.add(AuditTrail(table_name="email_settings", record_id=record_id, action=action, old_values=old or None,
                      new_values=new or None, user_id=actor_id, ip_address=(ip or None)))


def known_event_keys() -> List[str]:
    return list(EMAIL_EVENTS)
