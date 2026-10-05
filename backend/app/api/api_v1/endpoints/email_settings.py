"""Admin > Email Settings API (mounted at /admin/email-settings).

Reading (overview, provider status, events, delivery log) needs an
administrator. EVERY change, the API-key override and the test email need the
explicit `manage_email_settings` permission, which is never implied by
is_admin or the 'all' wildcard.

No response carries a secret: not the API key, not its ciphertext, not the
environment key. The override exposes its last four characters only.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.email import DELIVERY_STATUSES, EmailDelivery
from app.models.user import User
from app.services import email_crypto, email_outbox, email_settings_service as svc
from app.services.email_events import EMAIL_EVENTS, TEST_EMAIL_KEY, UnknownEmailEvent, all_events, get_event

router = APIRouter()

EMERGENCY_STOP_PHRASE = "STOP ALL EMAIL"
OUTBOX_STALLED_AFTER_SECONDS = 300


def require_email_manager(current_user: User = Depends(get_current_active_user)) -> User:
    if not svc.can_manage_email_settings(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="The manage_email_settings permission is required.")
    return current_user


def _ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _client_ip

    return _client_ip(request)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MasterSwitchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


class EmergencyStopBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: StrictBool
    confirmation: Optional[str] = Field(default=None, max_length=40)


class ProviderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resend_enabled: Optional[StrictBool] = None
    from_name: Optional[str] = Field(default=None, max_length=120)
    from_address: Optional[str] = Field(default=None, max_length=320)
    reply_to: Optional[str] = Field(default=None, max_length=320)
    support_address: Optional[str] = Field(default=None, max_length=320)
    admin_alert_recipients: Optional[List[str]] = Field(default=None, max_length=20)


class ApiKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=10, max_length=200)


class EventSwitchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool
    # Required to switch OFF a security-critical event.
    confirm_critical: StrictBool = False


class TestEmailBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Exactly one address. A list or a comma-separated value is rejected.
    recipient: str = Field(min_length=3, max_length=320)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def _provider_view(row) -> dict:
    _key, source = svc.resolve_api_key(row)
    name, address = svc.effective_sender(row)
    has_override = bool(row.resend_api_key_ciphertext)
    return {
        "resend_enabled": bool(row.resend_enabled),
        "configured": source != svc.KEY_SOURCE_NONE,
        "key_source": source,
        "environment_key_configured": bool(svc._env_api_key()),
        "override_configured": has_override,
        "override_readable": svc.override_readable(row),
        "override_last4": row.resend_api_key_last4 if has_override else None,
        "override_updated_at": row.resend_api_key_updated_at.isoformat() if row.resend_api_key_updated_at else None,
        "override_updated_by": row.resend_api_key_updated_by,
        "encryption_key_configured": email_crypto.settings_key_configured(),
        "from_name": row.from_name, "from_address": row.from_address,
        "effective_from_name": name, "effective_from_address": address,
        "reply_to": row.reply_to, "support_address": row.support_address,
        "effective_support_address": svc.support_address(row),
        "admin_alert_recipients": list(row.admin_alert_recipients or []),
        "allowed_from_domains": svc.allowed_from_domains(),
    }


def _warnings(row, provider: dict, stats: dict, overrides: dict) -> List[dict]:
    out: List[dict] = []
    if row.emergency_stop:
        out.append({"code": "EMERGENCY_STOP", "level": "critical",
                    "message": "Emergency Stop is active: no email is being sent, including security email."})
    if not provider["resend_enabled"]:
        out.append({"code": "PROVIDER_DISABLED", "level": "critical",
                    "message": "The Resend provider is disabled: no email can be sent."})
    elif not provider["configured"]:
        out.append({"code": "PROVIDER_UNCONFIGURED", "level": "critical",
                    "message": "No Resend API key is configured: no email can be sent."})
    if provider["override_configured"] and not provider["override_readable"]:
        out.append({"code": "OVERRIDE_UNREADABLE", "level": "critical",
                    "message": "The stored API key override cannot be decrypted "
                               "(EMAIL_SETTINGS_ENCRYPTION_KEY is missing or was changed). Save the key again."})
    if not provider["encryption_key_configured"]:
        out.append({"code": "ENCRYPTION_KEY_MISSING", "level": "critical",
                    "message": "Configuration required: EMAIL_SETTINGS_ENCRYPTION_KEY is not set on the server. "
                               "No email can be queued and an API key override cannot be stored until it is "
                               "configured."})
    if stats["oldest_due_seconds"] > OUTBOX_STALLED_AFTER_SECONDS:
        out.append({"code": "OUTBOX_STALLED", "level": "critical",
                    "message": "Queued email is not being sent: nothing is draining the outbox. Check that the "
                               + ("Celery worker and beat are running." if email_outbox.outbox_executor() == "celery"
                                  else "backend scheduler is running.")})
    if not row.email_enabled:
        out.append({"code": "MASTER_DISABLED", "level": "warning",
                    "message": "The email system is switched off: only security-critical email is sent."})
    critical_off = [d.label for d in all_events() if d.critical and not overrides.get(d.key, d.default_enabled)]
    if critical_off:
        out.append({"code": "CRITICAL_EVENT_DISABLED", "level": "warning",
                    "message": "Security-critical email switched off: " + ", ".join(critical_off) + "."})
    if stats["failed_24h"]:
        out.append({"code": "RECENT_FAILURES", "level": "warning",
                    "message": f"{stats['failed_24h']} email(s) failed in the last 24 hours."})
    return out


@router.get("/overview")
def overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    row = svc.get_settings(db)
    overrides = svc.event_overrides(db)
    provider = _provider_view(row)
    stats = email_outbox.health(db)
    critical = [{"key": d.key, "label": d.label, "enabled": overrides.get(d.key, d.default_enabled)}
                for d in all_events() if d.critical]
    configured = provider["encryption_key_configured"]
    sending = provider["resend_enabled"] and provider["configured"] and not row.emergency_stop and configured
    return {
        "status": ("stopped" if row.emergency_stop else "configuration_required" if not configured
                   else "unavailable" if not sending
                   else "critical_only" if not row.email_enabled else "active"),
        "encryption_key_configured": configured,
        "outbox_executor": email_outbox.outbox_executor(),
        "email_enabled": bool(row.email_enabled),
        "emergency_stop": bool(row.emergency_stop),
        "provider": {k: provider[k] for k in ("resend_enabled", "configured", "key_source")},
        "critical_events": critical,
        "critical_email_active": sending and all(c["enabled"] for c in critical),
        "stats": stats,
        "warnings": _warnings(row, provider, stats, overrides),
        "can_manage": svc.can_manage_email_settings(current_user),
        "emergency_stop_phrase": EMERGENCY_STOP_PHRASE,
    }


@router.get("/provider")
def provider(db: Session = Depends(get_db)):
    return _provider_view(svc.get_settings(db))


@router.put("/master")
def set_master(body: MasterSwitchBody, request: Request, db: Session = Depends(get_db),
               actor: User = Depends(require_email_manager)):
    row = svc.get_settings_for_update(db)
    old = bool(row.email_enabled)
    row.email_enabled = body.enabled
    row.updated_by = actor.id
    svc.audit(db, actor_id=actor.id, action="EMAIL_MASTER_SWITCH", old={"email_enabled": old},
              new={"email_enabled": body.enabled}, ip=_ip(request))
    db.commit()
    return {"email_enabled": bool(row.email_enabled)}


@router.put("/emergency-stop")
def set_emergency_stop(body: EmergencyStopBody, request: Request, db: Session = Depends(get_db),
                       actor: User = Depends(require_email_manager)):
    if body.active and (body.confirmation or "").strip() != EMERGENCY_STOP_PHRASE:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f'Type "{EMERGENCY_STOP_PHRASE}" to confirm.')
    row = svc.get_settings_for_update(db)
    old = bool(row.emergency_stop)
    row.emergency_stop = body.active
    row.updated_by = actor.id
    svc.audit(db, actor_id=actor.id, action="EMAIL_EMERGENCY_STOP", old={"emergency_stop": old},
              new={"emergency_stop": body.active}, ip=_ip(request))
    db.commit()
    return {"emergency_stop": bool(row.emergency_stop)}


def _clean_address(value: Optional[str], field: str) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    if not svc.valid_email(text):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"{field} is not a valid email address.")
    return text


@router.put("/provider")
def update_provider(body: ProviderBody, request: Request, db: Session = Depends(get_db),
                    actor: User = Depends(require_email_manager)):
    row = svc.get_settings_for_update(db)
    data = body.model_dump(exclude_unset=True)
    old, new = {}, {}

    def change(name: str, value):
        current = getattr(row, name)
        if current != value:
            old[name], new[name] = current, value
            setattr(row, name, value)

    if "resend_enabled" in data and data["resend_enabled"] is not None:
        change("resend_enabled", bool(data["resend_enabled"]))
    if "from_name" in data:
        name = (data["from_name"] or "").strip()
        if any(ch in name for ch in "\r\n<>\""):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="The sender name contains characters that are not allowed.")
        change("from_name", name or None)
    if "from_address" in data:
        address = _clean_address(data["from_address"], "The sender address")
        if address and not svc.from_address_allowed(address):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The sender address must use a verified sending domain ("
                       + ", ".join(svc.allowed_from_domains()) + ").")
        change("from_address", address)
    if "reply_to" in data:
        change("reply_to", _clean_address(data["reply_to"], "The reply-to address"))
    if "support_address" in data:
        change("support_address", _clean_address(data["support_address"], "The support address"))
    if "admin_alert_recipients" in data:
        recipients = []
        for item in data["admin_alert_recipients"] or []:
            address = _clean_address(item, "An admin alert recipient")
            if address and address.lower() not in [r.lower() for r in recipients]:
                recipients.append(address)
        change("admin_alert_recipients", recipients or None)
    if new:
        row.updated_by = actor.id
        svc.audit(db, actor_id=actor.id, action="EMAIL_PROVIDER_UPDATE", old=old, new=new, ip=_ip(request))
        db.commit()
    return _provider_view(row)


@router.put("/provider/api-key")
def set_api_key(body: ApiKeyBody, request: Request, db: Session = Depends(get_db),
                actor: User = Depends(require_email_manager)):
    api_key = body.api_key.strip()
    if len(api_key) < 10 or any(ch.isspace() for ch in api_key):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The API key is not valid.")
    if not email_crypto.settings_key_configured():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="EMAIL_SETTINGS_ENCRYPTION_KEY is not configured on the server, so a key "
                                   "cannot be stored securely.")
    row = svc.get_settings_for_update(db)
    had = bool(row.resend_api_key_ciphertext)
    svc.set_api_key_override(db, row, api_key, actor_id=actor.id)
    svc.audit(db, actor_id=actor.id, action="EMAIL_API_OVERRIDE_REPLACED" if had else "EMAIL_API_OVERRIDE_ADDED",
              old={"override": "configured" if had else "none"}, new={"override": "configured"}, ip=_ip(request))
    db.commit()
    return _provider_view(row)


@router.delete("/provider/api-key")
def remove_api_key(request: Request, db: Session = Depends(get_db), actor: User = Depends(require_email_manager)):
    row = svc.get_settings_for_update(db)
    had = bool(row.resend_api_key_ciphertext)
    if had:
        svc.clear_api_key_override(row, actor_id=actor.id)
        svc.audit(db, actor_id=actor.id, action="EMAIL_API_OVERRIDE_REMOVED", old={"override": "configured"},
                  new={"override": "none"}, ip=_ip(request))
        db.commit()
    return _provider_view(row)


@router.get("/events")
def events(db: Session = Depends(get_db)):
    overrides = svc.event_overrides(db)
    return {"events": [{
        "key": d.key, "label": d.label, "category": d.category.value, "classification": d.classification.value,
        "recipient": d.recipient, "critical": d.critical, "default_enabled": d.default_enabled,
        "enabled": overrides.get(d.key, d.default_enabled), "overridden": d.key in overrides,
        "phase": d.phase.value, "trigger_implemented": d.trigger_implemented,
        "disable_warning": d.disable_warning,
    } for d in all_events()], "count": len(EMAIL_EVENTS)}


@router.put("/events/{event_key}")
def set_event(event_key: str, body: EventSwitchBody, request: Request, db: Session = Depends(get_db),
              actor: User = Depends(require_email_manager)):
    try:
        definition = get_event(event_key)
    except UnknownEmailEvent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown email event.")
    if definition.critical and not body.enabled and not body.confirm_critical:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "CRITICAL_EVENT_CONFIRMATION_REQUIRED",
            "message": definition.disable_warning or "This is a security-critical email.",
        })
    previous = svc.set_event_enabled(db, definition, body.enabled, actor_id=actor.id)
    svc.audit(db, actor_id=actor.id, action="EMAIL_EVENT_SWITCH",
              old={"event": definition.key, "enabled": previous},
              new={"event": definition.key, "enabled": body.enabled, "critical": definition.critical},
              ip=_ip(request))
    db.commit()
    return {"key": definition.key, "enabled": body.enabled}


@router.get("/deliveries")
def deliveries(
    db: Session = Depends(get_db),
    event: Optional[str] = Query(None, max_length=80),
    category: Optional[str] = Query(None, max_length=20),
    delivery_status: Optional[str] = Query(None, alias="status", max_length=20),
    provider_name: Optional[str] = Query(None, alias="provider", max_length=30),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
):
    query = db.query(EmailDelivery)
    if event:
        query = query.filter(EmailDelivery.event_key == event)
    if category:
        query = query.filter(EmailDelivery.category == category.upper())
    if delivery_status:
        if delivery_status.upper() not in DELIVERY_STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown status.")
        query = query.filter(EmailDelivery.status == delivery_status.upper())
    if provider_name:
        query = query.filter(EmailDelivery.provider == provider_name)
    if date_from:
        query = query.filter(EmailDelivery.created_at >= date_from.replace(tzinfo=None))
    if date_to:
        query = query.filter(EmailDelivery.created_at < date_to.replace(tzinfo=None) + timedelta(days=1))
    total = query.count()
    rows = query.order_by(EmailDelivery.id.desc()).offset((page - 1) * limit).limit(limit).all()

    def label(key: str) -> str:
        if key == TEST_EMAIL_KEY:
            return "Test email"
        return EMAIL_EVENTS[key].label if key in EMAIL_EVENTS else key

    # Deliberately no payload, no token, no address and no provider request.
    return {"total": total, "page": page, "limit": limit, "items": [{
        "id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
        "event_key": r.event_key, "event_label": label(r.event_key), "category": r.category,
        "recipient": r.recipient_masked, "provider": r.provider, "status": r.status,
        "attempts": r.attempt_count, "provider_message_id": r.provider_message_id,
        "failure_category": r.failure_category, "failure_code": r.failure_code,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "next_attempt_at": r.next_attempt_at.isoformat() if r.next_attempt_at else None,
    } for r in rows]}


@router.post("/test")
def send_test(body: TestEmailBody, request: Request, db: Session = Depends(get_db),
              actor: User = Depends(require_email_manager)):
    recipient = body.recipient.strip()
    if not svc.valid_email(recipient):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Enter exactly one valid email address.")
    row = email_outbox.send_test_email(db, recipient=recipient, actor_id=actor.id)
    svc.audit(db, actor_id=actor.id, action="EMAIL_TEST_SENT",
              new={"delivery_id": row.id, "recipient": row.recipient_masked, "status": row.status},
              ip=_ip(request))
    db.commit()
    return {"delivery_id": row.id, "status": row.status, "success": row.status == "SENT",
            "failure_category": row.failure_category, "recipient": row.recipient_masked}
