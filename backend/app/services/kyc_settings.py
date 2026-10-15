"""Kaluta KYC settings an authorised administrator manages in the Admin Panel,
and the limit on provider sessions within one KYC attempt.

The database is the ONLY source of these settings. The server environment
(KALUTA_KYC_ENABLED, KALUTA_API_KEY, KALUTA_WEBHOOK_SECRET) is not read: no
SSH access or .env change is needed, or has any effect.

Settings (Admin > KYC), all saved with ONE form:
  * Kaluta KYC on/off (kyc_settings.kaluta_enabled). No row or NULL = OFF.
    Switching it on is refused unless an API key and a webhook secret are
    saved and readable.
  * Kaluta API key and webhook secret: stored ONLY as AES-256-GCM ciphertext in
    payment_credentials (provider "kaluta"), with the dedicated
    PAYMENT_SETTINGS_ENCRYPTION_KEY and a purpose of their own, so a KYC
    ciphertext can never be read as a payment credential or the other way
    round. A saved value is never shown again, logged, audited or returned:
    the Admin Panel only learns whether one is saved and readable. Saving
    replaces; a blank field keeps what is saved.
  * The Member KYC Verification Fee (USD): the price of the `kyc` product,
    app.services.kyc_fee. New payments use it; existing ones keep their amount.
  * Sessions per attempt (kyc_settings.sessions_per_attempt, 1 to 10; NULL =
    the default of 3).

Missing or unreadable settings fail closed: Kaluta KYC is off, a member cannot
start a verification (503, nothing paid or consumed) and every webhook is
refused.

Every change needs the explicit `manage_kyc_settings` permission (or a Super
Admin; never implied by is_admin, the 'all' wildcard or
manage_payment_settings) and the administrator's current password, and writes
one audit_trails row that names what changed, never a value of a secret.

Sessions: a provider session that runs out (24 hours) does not use up the
member's attempt. A new session is opened inside the SAME attempt, without a
payment, up to the sessions-per-attempt setting (each one may be charged to
MyHigh5 by the provider). After that, an administrator holding the permission
can allow one more session at a time (grant_session), up to
MAX_GRANTED_SESSIONS per attempt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.kyc import KYCAuditLog, KYCStatus, KYCVerification, KycSettings
from app.models.payment_config import PaymentCredential
from app.services import admin_security, kyc_fee, payment_config, payment_crypto
from app.services.kaluta_kyc import active_kyc_provider, kaluta_kyc_service, resolve_kaluta_urls

logger = logging.getLogger(__name__)

PERMISSION = admin_security.PERMISSION_MANAGE_KYC
PROVIDER = "kaluta"
_PURPOSE = "mh5-kyc:kaluta-credential:"
ROW_ID = 1

DEFAULT_SESSIONS_PER_ATTEMPT = 3
SESSIONS_PER_ATTEMPT = DEFAULT_SESSIONS_PER_ATTEMPT    # the limit while nothing is saved
MIN_SESSIONS_PER_ATTEMPT, MAX_SESSIONS_PER_ATTEMPT = 1, 10
MAX_GRANTED_SESSIONS = 3

AUDIT_SETTINGS = "KYC_SETTINGS_CHANGED"
AUDIT_SESSION_GRANTED = "KYC_SESSION_GRANTED"
SOURCE_DATABASE = "database"
OPEN_STATUSES = (KYCStatus.PENDING, KYCStatus.IN_PROGRESS, KYCStatus.EXPIRED)
FIELD_FEE, FIELD_SESSIONS = "MEMBER_FEE", "SESSIONS_PER_ATTEMPT"


@dataclass(frozen=True)
class CredentialSpec:
    name: str
    label: str
    attribute: str          # on kaluta_kyc_service
    min_length: int


CREDENTIALS: Dict[str, CredentialSpec] = {c.name: c for c in (
    CredentialSpec("API_KEY", "Kaluta API key", "api_key", 16),
    CredentialSpec("WEBHOOK_SECRET", "Kaluta webhook secret", "webhook_secret", 16),
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
# The values in force (database only)
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


def saved_values(db: Session) -> Dict[str, Any]:
    """The settings in force: Kaluta on only when the database says so, and only
    the key / secret that are saved AND readable. Nothing else is consulted."""
    row = _row(db)
    out: Dict[str, Any] = {"enabled": bool(row is not None and row.kaluta_enabled)}
    stored = _stored(db)
    for name, spec in CREDENTIALS.items():
        value = _decrypt(stored.get(name))
        if value:
            out[spec.attribute] = value
    return out


def apply(db: Session) -> None:
    """Hand the database settings to the Kaluta service before a KYC request.
    If they cannot be read, Kaluta KYC is treated as off (fail closed)."""
    try:
        values = saved_values(db)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("KYC settings could not be read (%s); Kaluta KYC is treated as off", type(exc).__name__)
        values = {}
    kaluta_kyc_service.use_settings(values)


def kaluta_enabled(db: Session) -> bool:
    """Is Kaluta KYC switched on now (Admin > KYC)?"""
    apply(db)
    return kaluta_kyc_service.enabled


def _sessions_value(row: Optional[KycSettings]) -> int:
    value = getattr(row, "sessions_per_attempt", None) if row is not None else None
    if value is None or not MIN_SESSIONS_PER_ATTEMPT <= int(value) <= MAX_SESSIONS_PER_ATTEMPT:
        return DEFAULT_SESSIONS_PER_ATTEMPT
    return int(value)


def sessions_per_attempt(db: Session) -> int:
    """Provider sessions one attempt may open (the saved setting, else the default)."""
    try:
        row = _row(db)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("KYC settings could not be read (%s); the default session limit applies", type(exc).__name__)
        return DEFAULT_SESSIONS_PER_ATTEMPT
    return _sessions_value(row)


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


def parse_sessions(value: Any) -> int:
    """Sessions per attempt an administrator typed: a whole number, 1 to 10."""
    bad = KycSettingsError("INVALID_VALUE", "Sessions per attempt: enter a whole number.", field=FIELD_SESSIONS)
    if isinstance(value, bool) or value is None:
        raise bad
    if isinstance(value, float):
        if not value.is_integer():
            raise bad
        value = int(value)
    text = str(value).strip()
    if not text.isdigit() or len(text) > 3:
        raise bad
    number = int(text)
    if not MIN_SESSIONS_PER_ATTEMPT <= number <= MAX_SESSIONS_PER_ATTEMPT:
        raise KycSettingsError("INVALID_VALUE", f"Sessions per attempt: from {MIN_SESSIONS_PER_ATTEMPT} to "
                                                f"{MAX_SESSIONS_PER_ATTEMPT}.", field=FIELD_SESSIONS)
    return number


def _parse_fee(value: Any) -> Decimal:
    try:
        return kyc_fee.parse_fee(value)
    except kyc_fee.KycFeeError as exc:
        raise KycSettingsError(exc.code, f"KYC fee: {exc}", field=FIELD_FEE) from None


def _given(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


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
        credentials.append({
            "name": name, "label": spec.label,
            "configured": readable,
            "saved": saved is not None, "saved_readable": readable if saved is not None else None,
            "saved_at": saved.set_at.isoformat() if saved is not None and saved.set_at else None,
        })
    webhook_url, redirect_url = resolve_kaluta_urls()
    return {
        "source": SOURCE_DATABASE,
        "provider": active_kyc_provider(),
        "enabled": bool(row is not None and row.kaluta_enabled),
        "credentials": credentials,
        "ready_to_enable": all(c["configured"] for c in credentials),
        "webhook_url": webhook_url or None,
        "redirect_url": redirect_url or None,
        "encryption_key_configured": payment_crypto.key_configured(),
        "member_fee": {**kyc_fee.fee_view(db), "max_amount": f"{kyc_fee.MAX_FEE:.2f}",
                       "product_configured": kyc_fee._product(db) is not None,
                       "last_change": kyc_fee.last_change(db)},
        "sessions_per_attempt": _sessions_value(row),
        "sessions_per_attempt_min": MIN_SESSIONS_PER_ATTEMPT,
        "sessions_per_attempt_max": MAX_SESSIONS_PER_ATTEMPT,
        "sessions_per_attempt_default": DEFAULT_SESSIONS_PER_ATTEMPT,
        "version": int(row.version) if row is not None else 0,
        "can_change": has_permission(actor),
        "permission": PERMISSION,
        "last_change": _last_change(db),
    }


def update(db: Session, actor, *, password: Optional[str], enabled: Optional[bool] = None,
           credentials: Optional[Dict[str, Optional[str]]] = None, member_fee: Any = None,
           sessions: Any = None, expected_version: Optional[int] = None, expected_fee: Any = None,
           ip: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Save the Admin Panel form: Kaluta on/off, REPLACE the API key / webhook
    secret, the member fee and the sessions per attempt. Absent (None) keeps a
    value; a blank credential keeps the saved one. Everything is validated
    first and saved in ONE commit; on any refusal nothing is changed."""
    now = now or datetime.utcnow()
    if not has_permission(actor):
        raise KycSettingsError("FORBIDDEN", f"The {PERMISSION} permission is required.")
    unknown = sorted(set(credentials or {}) - set(CREDENTIALS))
    if unknown:
        raise KycSettingsError("INVALID_FIELD", "Unknown setting: " + ", ".join(unknown))
    cleaned = {name: _clean(CREDENTIALS[name], value) for name, value in (credentials or {}).items()
               if str(value or "").strip()}
    fee_amount = _parse_fee(member_fee) if _given(member_fee) else None
    sessions_value = parse_sessions(sessions) if _given(sessions) else None
    if enabled is None and not cleaned and fee_amount is None and sessions_value is None:
        raise KycSettingsError("NOTHING_TO_CHANGE", "Nothing to save.")
    authorize(actor, password)
    if cleaned and not payment_crypto.key_configured():
        raise KycSettingsError("ENCRYPTION_KEY_MISSING",
                               "PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured on the server, so a key or "
                               "secret cannot be stored securely. Nothing was changed.")

    row = _row(db, lock=True)
    if row is None:
        # The first save creates the single row (Kaluta off). Two first saves at
        # once: the second waits for the first, then finds its row (and is refused as stale).
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

    old = {"kaluta_enabled": bool(row.kaluta_enabled), "sessions_per_attempt": _sessions_value(row),
           "member_fee": kyc_fee.fee_view(db)["amount"]}
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

    if sessions_value is not None and sessions_value != old["sessions_per_attempt"]:
        row.sessions_per_attempt = sessions_value
        changed.append(FIELD_SESSIONS)

    if fee_amount is not None:
        try:
            if kyc_fee.stage_member_fee(db, actor, fee_amount, ip=ip, expected_amount=expected_fee):
                changed.append(FIELD_FEE)
        except kyc_fee.KycFeeError as exc:
            db.rollback()
            raise KycSettingsError(exc.code, str(exc), field=FIELD_FEE) from None

    if enabled is not None and bool(enabled) != old["kaluta_enabled"]:
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
        # Which settings changed and the values that are not secret. Never a key or a secret.
        old_values=old,
        new_values={"kaluta_enabled": bool(row.kaluta_enabled), "sessions_per_attempt": _sessions_value(row),
                    "member_fee": f"{fee_amount:.2f}" if FIELD_FEE in changed else old["member_fee"],
                    "changed": sorted(changed), "version": int(row.version)}))
    db.commit()
    apply(db)
    return view(db, actor)


def _enable_refusal(db: Session) -> Optional[str]:
    """Why Kaluta KYC must not be switched on now (None when it may be)."""
    if active_kyc_provider() != "kaluta":
        return "This server uses another KYC provider (KYC_PROVIDER). Nothing was changed."
    saved = _stored(db)
    for name, spec in CREDENTIALS.items():
        value = _decrypt(saved.get(name))
        if not value:
            return f"Save the {spec.label} before switching Kaluta KYC on. Nothing was changed."
        if _url_shaped(value):
            return f"The saved {spec.label} looks like a URL, not a secret. Nothing was changed."
    return None


# ---------------------------------------------------------------------------
# Provider sessions within one attempt
# ---------------------------------------------------------------------------

def session_allowance(verification, *, per_attempt: int) -> int:
    """Sessions this attempt may open: the setting plus what an administrator allowed."""
    return int(per_attempt) + int(getattr(verification, "attempt_sessions_granted", 0) or 0)


def sessions_left(verification, *, per_attempt: int) -> int:
    if verification is None:
        return int(per_attempt)
    return max(0, session_allowance(verification, per_attempt=per_attempt)
               - int(verification.attempt_sessions_count or 0))


def grant_session(db: Session, actor, verification_id: int, *, password: Optional[str],
                  ip: Optional[str] = None) -> dict:
    """Allow ONE more provider session for a member whose open attempt used every
    session it had. No payment, no new attempt. Commits."""
    authorize(actor, password)
    per_attempt = sessions_per_attempt(db)
    row = (db.query(KYCVerification).filter(KYCVerification.id == verification_id)
           .with_for_update().populate_existing().first())
    if row is None:
        db.rollback()
        raise KycSettingsError("NOT_FOUND", "Verification not found.")
    if row.status not in OPEN_STATUSES:
        db.rollback()
        raise KycSettingsError("NOT_OPEN", "This verification has no open attempt. Nothing was changed.")
    if sessions_left(row, per_attempt=per_attempt) > 0:
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
    return {"verification_id": row.id, "sessions_left": sessions_left(row, per_attempt=per_attempt),
            "attempt_sessions_granted": int(row.attempt_sessions_granted)}
