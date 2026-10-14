"""Kaluta KYC settings an authorised administrator changes in the Admin Panel,
and the limit on provider sessions within one KYC attempt.

Settings (Admin > KYC):
  * Kaluta API key and webhook secret: stored ONLY as AES-256-GCM ciphertext in
    payment_credentials (provider "kaluta"), with the dedicated
    PAYMENT_SETTINGS_ENCRYPTION_KEY and a purpose of their own, so a KYC
    ciphertext can never be read as a payment credential or the other way
    round. A saved value is never shown again, logged, audited or returned:
    the Admin Panel only learns whether one is saved and readable. Saving
    replaces; a blank field keeps what is saved.
  * Kaluta KYC on/off (kyc_settings.kaluta_enabled). Switching it on is
    refused unless an API key and a webhook secret are in force.
  * The Member KYC Verification Fee lives in app.services.kyc_fee, under the
    same permission.
A value saved here is used instead of the server environment; anything not
saved here comes from the environment, as before (KALUTA_KYC_ENABLED,
KALUTA_API_KEY, KALUTA_WEBHOOK_SECRET).

Every change needs the explicit `manage_kyc_settings` permission (never
implied by is_admin, the 'all' wildcard or manage_payment_settings, and
assigned to nobody by the migration) and the administrator's current
password, and writes one audit_trails row that names what changed, never a
value of a secret.

Sessions: a provider session that runs out (24 hours) does not use up the
member's attempt. A new session is opened inside the SAME attempt, without a
payment, up to SESSIONS_PER_ATTEMPT sessions per attempt (each one may be
charged to MyHigh5 by the provider). After that, an administrator holding the
permission can allow one more session at a time (grant_session), up to
MAX_GRANTED_SESSIONS per attempt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification, KycSettings
from app.models.payment_config import PaymentCredential
from app.services import admin_security, payment_config, payment_crypto
from app.services.kaluta_kyc import active_kyc_provider, kaluta_kyc_service, resolve_kaluta_urls

logger = logging.getLogger(__name__)

PERMISSION = admin_security.PERMISSION_MANAGE_KYC
PROVIDER = "kaluta"
_PURPOSE = "mh5-kyc:kaluta-credential:"
ROW_ID = 1

SESSIONS_PER_ATTEMPT = 3
MAX_GRANTED_SESSIONS = 3

AUDIT_SETTINGS = "KYC_SETTINGS_CHANGED"
AUDIT_SESSION_GRANTED = "KYC_SESSION_GRANTED"
SOURCE_ADMIN, SOURCE_ENV = "admin_panel", "environment"
OPEN_STATUSES = (KYCStatus.PENDING, KYCStatus.IN_PROGRESS, KYCStatus.EXPIRED)


@dataclass(frozen=True)
class CredentialSpec:
    name: str
    label: str
    attribute: str          # on kaluta_kyc_service
    env: str
    min_length: int


CREDENTIALS: Dict[str, CredentialSpec] = {c.name: c for c in (
    CredentialSpec("API_KEY", "Kaluta API key", "api_key", "KALUTA_API_KEY", 16),
    CredentialSpec("WEBHOOK_SECRET", "Kaluta webhook secret", "webhook_secret", "KALUTA_WEBHOOK_SECRET", 16),
)}


class KycSettingsError(ValueError):
    def __init__(self, code: str, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.field = field


# ---------------------------------------------------------------------------
# Who may
# ---------------------------------------------------------------------------

def has_permission(user) -> bool:
    return payment_config.has_permission(user, PERMISSION)


def authorize(actor, password: Optional[str]) -> None:
    """The explicit permission first, then the current password."""
    if not has_permission(actor):
        raise KycSettingsError("FORBIDDEN", f"The {PERMISSION} permission is required.")
    try:
        payment_config.require_reauth(actor, password)
    except payment_config.PaymentConfigError as exc:
        raise KycSettingsError(exc.code, str(exc)) from None


# ---------------------------------------------------------------------------
# The values in force
# ---------------------------------------------------------------------------

def _row(db: Session, *, lock: bool = False) -> Optional[KycSettings]:
    query = db.query(KycSettings).filter(KycSettings.id == ROW_ID)
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


def _env(spec: CredentialSpec) -> Optional[str]:
    return str(getattr(settings, spec.env, "") or "").strip() or None


def admin_values(db: Session) -> Dict[str, Any]:
    """What the Admin Panel saved and can be used: only the names that are set.
    A stored secret that cannot be decrypted is not used (the environment then
    applies, and the Admin Panel says the saved value is not readable)."""
    row = _row(db)
    out: Dict[str, Any] = {}
    if row is not None and row.kaluta_enabled is not None:
        out["enabled"] = bool(row.kaluta_enabled)
    stored = _stored(db)
    for name, spec in CREDENTIALS.items():
        value = _decrypt(stored.get(name))
        if value:
            out[spec.attribute] = value
    return out


def apply(db: Session) -> None:
    """Hand the Admin Panel values to the Kaluta service before a KYC request.
    If they cannot be read, the server environment decides (as before)."""
    try:
        values = admin_values(db)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("KYC settings could not be read (%s); the server environment applies", type(exc).__name__)
        values = {}
    kaluta_kyc_service.use_admin_values(values)


def kaluta_enabled(db: Session) -> bool:
    """Is Kaluta KYC switched on now (the Admin Panel, else KALUTA_KYC_ENABLED)?"""
    apply(db)
    row_value = kaluta_kyc_service._admin_values.get("enabled")
    return bool(settings.KALUTA_KYC_ENABLED if row_value is None else row_value)


def _url_shaped(value: Optional[str]) -> bool:
    return bool(value) and str(value).strip().lower().startswith(("http://", "https://"))


def _clean(spec: CredentialSpec, value: Any) -> str:
    text = str(value or "").strip()
    if any(ch.isspace() for ch in text):
        raise KycSettingsError("INVALID_VALUE", f"{spec.label}: must not contain spaces.", field=spec.name)
    if _url_shaped(text):
        # The known mistake: the webhook URL pasted where the signing secret belongs.
        raise KycSettingsError("INVALID_VALUE", f"{spec.label}: this looks like a URL, not a secret.", field=spec.name)
    if len(text) < spec.min_length or len(text) > 512:
        raise KycSettingsError("INVALID_VALUE", f"{spec.label}: the value is too short or too long.", field=spec.name)
    return text


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
    stored = _stored(db)
    credentials: List[dict] = []
    for name, spec in CREDENTIALS.items():
        saved = stored.get(name)
        readable = _decrypt(saved) is not None
        environment = _env(spec) is not None
        in_use = SOURCE_ADMIN if readable else (SOURCE_ENV if environment else None)
        credentials.append({
            "name": name, "label": spec.label,
            "saved": saved is not None, "saved_readable": readable if saved is not None else None,
            "saved_at": saved.set_at.isoformat() if saved is not None and saved.set_at else None,
            "environment_configured": environment, "in_use": in_use, "configured": in_use is not None,
        })
    enabled_saved = row is not None and row.kaluta_enabled is not None
    webhook_url, redirect_url = resolve_kaluta_urls()
    return {
        "provider": active_kyc_provider(),
        "enabled": bool(row.kaluta_enabled) if enabled_saved else bool(settings.KALUTA_KYC_ENABLED),
        "enabled_source": SOURCE_ADMIN if enabled_saved else SOURCE_ENV,
        "credentials": credentials,
        "ready_to_enable": all(c["configured"] for c in credentials),
        "webhook_url": webhook_url or None,
        "redirect_url": redirect_url or None,
        "encryption_key_configured": payment_crypto.key_configured(),
        "sessions_per_attempt": SESSIONS_PER_ATTEMPT,
        "version": int(row.version) if row is not None else 0,
        "can_change": has_permission(actor),
        "permission": PERMISSION,
        "last_change": _last_change(db),
    }


def update(db: Session, actor, *, password: Optional[str], enabled: Optional[bool] = None,
           credentials: Optional[Dict[str, Optional[str]]] = None, expected_version: Optional[int] = None,
           ip: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Switch Kaluta KYC on or off and/or REPLACE the API key / webhook secret.
    A blank or absent credential keeps the saved one. Commits once; on any
    refusal nothing is changed."""
    now = now or datetime.utcnow()
    if not has_permission(actor):
        raise KycSettingsError("FORBIDDEN", f"The {PERMISSION} permission is required.")
    unknown = sorted(set(credentials or {}) - set(CREDENTIALS))
    if unknown:
        raise KycSettingsError("INVALID_FIELD", "Unknown setting: " + ", ".join(unknown))
    cleaned = {name: _clean(CREDENTIALS[name], value) for name, value in (credentials or {}).items()
               if str(value or "").strip()}
    if enabled is None and not cleaned:
        raise KycSettingsError("NOTHING_TO_CHANGE", "Nothing to save.")
    authorize(actor, password)
    if cleaned and not payment_crypto.key_configured():
        raise KycSettingsError("ENCRYPTION_KEY_MISSING",
                               "PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured on the server, so a key or "
                               "secret cannot be stored securely. Nothing was changed.")

    row = _row(db, lock=True)
    if row is None:
        # The first save creates the single row. Two first saves at once: the
        # second waits for the first, then finds its row (and is refused as stale).
        if db.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert

            db.execute(insert(KycSettings.__table__).values(id=ROW_ID, version=0, created_at=now, updated_at=now)
                       .on_conflict_do_nothing(index_elements=["id"]))
        else:
            db.add(KycSettings(id=ROW_ID, kaluta_enabled=None, version=0))
            db.flush()
        row = _row(db, lock=True)
    if expected_version is not None and int(expected_version) != int(row.version):
        db.rollback()
        raise KycSettingsError("STALE", "The KYC settings were changed by somebody else. Reload and try again.")

    stored = _stored(db)
    changed: List[str] = []
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

    old_enabled = row.kaluta_enabled
    if enabled is not None and (old_enabled is None or bool(old_enabled) != bool(enabled)):
        if enabled:
            refusal = _enable_refusal(db)
            if refusal:
                db.rollback()
                raise KycSettingsError("NOT_READY", refusal)
        row.kaluta_enabled = bool(enabled)
        changed.append("KALUTA_ENABLED")

    if not changed:
        db.rollback()
        return view(db, actor)
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    db.add(AuditTrail(
        table_name="kyc_settings", record_id=ROW_ID, action=AUDIT_SETTINGS, user_id=actor.id, ip_address=(ip or None),
        # Which settings changed, and the on/off switch. Never a key or a secret.
        old_values={"kaluta_enabled": old_enabled},
        new_values={"kaluta_enabled": row.kaluta_enabled, "changed": sorted(changed), "version": int(row.version)}))
    db.commit()
    apply(db)
    return view(db, actor)


def _enable_refusal(db: Session) -> Optional[str]:
    """Why Kaluta KYC must not be switched on now (None when it may be)."""
    if active_kyc_provider() != "kaluta":
        return "This server uses another KYC provider (KYC_PROVIDER). Nothing was changed."
    saved = _stored(db)
    for name, spec in CREDENTIALS.items():
        value = _decrypt(saved.get(name)) or _env(spec)
        if not value:
            return f"Save the {spec.label} before switching Kaluta KYC on. Nothing was changed."
        if _url_shaped(value):
            return f"The {spec.label} in force looks like a URL, not a secret. Nothing was changed."
    return None


# ---------------------------------------------------------------------------
# Provider sessions within one attempt
# ---------------------------------------------------------------------------

def session_allowance(verification) -> int:
    return SESSIONS_PER_ATTEMPT + int(getattr(verification, "attempt_sessions_granted", 0) or 0)


def sessions_left(verification) -> int:
    if verification is None:
        return SESSIONS_PER_ATTEMPT
    return max(0, session_allowance(verification) - int(verification.attempt_sessions_count or 0))


def grant_session(db: Session, actor, verification_id: int, *, password: Optional[str],
                  ip: Optional[str] = None) -> dict:
    """Allow ONE more provider session for a member whose open attempt used every
    session it had. No payment, no new attempt. Commits."""
    authorize(actor, password)
    row = (db.query(KYCVerification).filter(KYCVerification.id == verification_id)
           .with_for_update().populate_existing().first())
    if row is None:
        db.rollback()
        raise KycSettingsError("NOT_FOUND", "Verification not found.")
    if row.status not in OPEN_STATUSES:
        db.rollback()
        raise KycSettingsError("NOT_OPEN", "This verification has no open attempt. Nothing was changed.")
    if sessions_left(row) > 0:
        db.rollback()
        raise KycSettingsError("NOT_NEEDED", "The member can still open a session for this attempt. Nothing was changed.")
    if int(row.attempt_sessions_granted or 0) >= MAX_GRANTED_SESSIONS:
        db.rollback()
        raise KycSettingsError("GRANT_LIMIT", f"At most {MAX_GRANTED_SESSIONS} extra sessions can be allowed for one "
                                              "attempt. Nothing was changed.")
    old = int(row.attempt_sessions_granted or 0)
    row.attempt_sessions_granted = old + 1
    db.add(KYCAuditLog(verification_id=row.id, action="kyc_session_granted",
                       details=f"One more provider session allowed for attempt {row.attempts_count} "
                               f"({old + 1} extra in total)",
                       old_status=getattr(row.status, "value", row.status), new_status=getattr(row.status, "value", row.status),
                       performed_by_user_id=actor.id, performed_by_admin=True, timestamp=datetime.utcnow(),
                       ip_address=(ip or None)))
    db.add(AuditTrail(table_name="kyc_verifications", record_id=row.id, action=AUDIT_SESSION_GRANTED,
                      user_id=actor.id, ip_address=(ip or None),
                      old_values={"attempt_sessions_granted": old},
                      new_values={"attempt_sessions_granted": old + 1}))
    db.commit()
    return {"verification_id": row.id, "sessions_left": sessions_left(row),
            "attempt_sessions_granted": int(row.attempt_sessions_granted)}
