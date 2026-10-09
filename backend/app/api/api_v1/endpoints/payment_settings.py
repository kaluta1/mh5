"""Admin > Finance & Payments API (mounted at /admin/finance).

Reading needs an administrator. EVERY configuration change, every credential
action and the connection test need the explicit `manage_payment_settings`
permission, which is never implied by is_admin or the 'all' wildcard; a change
also needs the administrator's current password in the same request.

No response carries a secret: not a credential, not its ciphertext, not the
encryption key. A credential is reported as CONFIGURED / NOT CONFIGURED only.
Credential fields are write-only: a blank field keeps the stored value, and
deleting a credential is a separate, explicit action.

Nothing here sends money. Cashout transactions and their actions live in
endpoints/cashouts.py (/admin/cashouts).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.client_ip import client_ip
from app.core.rate_limit import _is_rate_limited
from app.db.session import get_db
from app.models.accounting import AuditTrail
from app.models.affiliate import PayoutWalletChange
from app.models.payment_config import PayoutWalletVerification
from app.models.user import User
from app.services import cashout_engine, cashout_service, payment_config as config

router = APIRouter()

CONNECTION_TEST_LIMIT, CONNECTION_TEST_WINDOW = 6, 600        # per administrator

# Actions written by the cashout services (cashout_service._audit).
FINANCIAL_AUDIT_TABLES = ("affiliate_cashout_requests",)
MEMBER_FINANCIAL_ACTIONS = ("PAYOUT_WALLET_CHANGED", "PAYOUT_WALLET_CHANGE_REQUESTED", "CASHOUT_METHOD_CHANGED")


def _http_error(exc: config.PaymentConfigError) -> HTTPException:
    if exc.code in ("FORBIDDEN", "REAUTH_REQUIRED"):
        code = status.HTTP_403_FORBIDDEN
    elif exc.code in ("INVALID_VALUE", "INVALID_FIELD"):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc), "field": exc.field})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: Dict[str, Any] = Field(..., max_length=60)
    current_password: str = Field(default="", max_length=256)
    # Required to switch on automatic payouts or USD settlement.
    confirmation: Optional[str] = Field(default=None, max_length=60)


class CredentialsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Blank or absent = keep the stored value. Nothing is deleted here.
    values: Dict[str, Optional[str]] = Field(..., max_length=10)
    current_password: str = Field(default="", max_length=256)


class ReauthBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(default="", max_length=256)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _permissions(user: User) -> dict:
    return {"can_manage": config.has_permission(user, config.PERMISSION_MANAGE),
            "can_process": config.has_permission(user, config.PERMISSION_PROCESS)}


@router.get("/overview")
def overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    provider = config.provider_view(db)
    settings_data = config.settings_view(db)
    warnings = []
    if not provider["encryption_key_configured"]:
        warnings.append({"code": "ENCRYPTION_KEY_MISSING", "level": "warning",
                         "message": "PAYMENT_SETTINGS_ENCRYPTION_KEY is not set on the server: credentials "
                                    "cannot be stored in the Admin Panel and stored ones cannot be read."})
    if any(c["stored"] == "CONFIGURED" and c["stored_readable"] is False for c in provider["credentials"]):
        warnings.append({"code": "CREDENTIAL_UNREADABLE", "level": "critical",
                         "message": "A stored credential cannot be decrypted (the encryption key is missing "
                                    "or was changed). Store it again."})
    webhook = config.webhook_health(db)
    if webhook["status"] == "SIGNATURE_REJECTIONS":
        warnings.append({"code": "IPN_SIGNATURE_REJECTIONS", "level": "critical",
                         "message": "Recent payment callbacks were rejected because their signature did not "
                                    "verify. Check that the IPN secret matches the provider dashboard."})
    return {
        "permissions": _permissions(current_user),
        "providers": [
            {"key": provider["provider"], "name": provider["display_name"], "role": "Crypto pay-in and payout",
             "enabled": provider["enabled"], "environment": provider["environment"],
             "payin_status": provider["payin_status"], "payout_status": provider["payout_status"],
             "custody_status": provider["custody_status"], "connection_status": provider["connection"]["status"]},
            {"key": "usd_manual", "name": "USD settlement (manual)", "role": "USD cashout",
             "enabled": settings_data["effective"]["usd_settlement"], "environment": None,
             "payin_status": None, "payout_status": "NO PROVIDER CONFIGURED", "custody_status": None,
             "connection_status": None},
        ],
        "server_switches": settings_data["server_switches"],
        "effective": settings_data["effective"],
        "engine": cashout_engine.engine_status(db),
        "webhook_status": webhook["status"],
        "configuration_version": settings_data["version"],
        "warnings": warnings,
    }


@router.get("/provider")
def provider(db: Session = Depends(get_db)):
    return config.provider_view(db)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return config.settings_view(db)


@router.get("/webhook")
def webhook(db: Session = Depends(get_db)):
    return config.webhook_health(db)


@router.get("/audit")
def configuration_audit(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                        db: Session = Depends(get_db)):
    return config.audit_view(db, skip=skip, limit=limit)


@router.get("/financial-audit")
def financial_audit(user_id: Optional[int] = None, cashout_id: Optional[int] = None, skip: int = Query(0, ge=0),
                    limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """Cashout and payout wallet events (who, what, when). Addresses are masked."""
    query = db.query(AuditTrail).filter(or_(AuditTrail.table_name.in_(FINANCIAL_AUDIT_TABLES),
                                            AuditTrail.action.in_(MEMBER_FINANCIAL_ACTIONS)))
    if cashout_id is not None:
        query = query.filter(AuditTrail.table_name == "affiliate_cashout_requests",
                             AuditTrail.record_id == cashout_id)
    if user_id is not None:
        query = query.filter(AuditTrail.user_id == user_id)
    total = query.count()
    rows = query.order_by(AuditTrail.id.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [{
        "id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None, "action": r.action,
        "table": r.table_name, "record_id": r.record_id, "actor_id": r.user_id,
        "old_values": r.old_values or {}, "new_values": r.new_values or {}, "ip_address": r.ip_address,
    } for r in rows]}


@router.get("/wallet-history")
def wallet_history(user_id: Optional[int] = None, skip: int = Query(0, ge=0),
                   limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """Accepted payout wallet changes, newest first, and confirmations still pending."""
    query = db.query(PayoutWalletChange)
    pending = db.query(PayoutWalletVerification).filter(PayoutWalletVerification.consumed_at.is_(None),
                                                        PayoutWalletVerification.revoked_at.is_(None))
    if user_id is not None:
        query = query.filter(PayoutWalletChange.user_id == user_id)
        pending = pending.filter(PayoutWalletVerification.user_id == user_id)
    total = query.count()
    rows = query.order_by(PayoutWalletChange.id.desc()).offset(skip).limit(limit).all()
    mask = cashout_service.mask_address
    return {
        "total": total,
        "items": [{"id": r.id, "user_id": r.user_id, "old_wallet": mask(r.old_address),
                   "new_wallet": mask(r.new_address), "payout_currency": r.currency,
                   "changed_at": r.changed_at.isoformat(), "payable_from": r.payable_from.isoformat(),
                   "verified_by": r.verification_method, "ip_address": r.ip_address} for r in rows],
        "pending": [{"id": r.id, "user_id": r.user_id, "wallet": mask(r.address), "payout_currency": r.currency,
                     "requested_at": r.requested_at.isoformat(), "expires_at": r.expires_at.isoformat()}
                    for r in pending.order_by(PayoutWalletVerification.id.desc()).limit(100).all()],
    }


@router.get("/reconciliation")
def reconciliation(read_provider: bool = False, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_active_user)):
    """What is owed, by state, the internal discrepancies, and (only with
    read_provider=true, for an administrator who may manage payments) the
    balance the provider reports. Read-only."""
    if read_provider and not config.has_permission(current_user, config.PERMISSION_MANAGE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"code": "FORBIDDEN",
                                    "message": f"The {config.PERMISSION_MANAGE} permission is required."})
    return cashout_engine.reconciliation_report(db, read_provider=read_provider)


# ---------------------------------------------------------------------------
# Change (permission + current password, validated and audited in payment_config)
# ---------------------------------------------------------------------------

@router.put("/settings")
def update_settings(body: SettingsBody, request: Request, db: Session = Depends(get_db),
                    actor: User = Depends(get_current_active_user)):
    try:
        config.update_settings(db, actor, body.changes, password=body.current_password,
                               confirmation=body.confirmation, ip=client_ip(request))
    except config.PaymentConfigError as exc:
        db.rollback()
        raise _http_error(exc) from None
    return config.settings_view(db)


@router.put("/credentials")
def store_credentials(body: CredentialsBody, request: Request, db: Session = Depends(get_db),
                      actor: User = Depends(get_current_active_user)):
    try:
        written = config.set_credentials(db, actor, body.values, password=body.current_password,
                                         ip=client_ip(request))
    except config.PaymentConfigError as exc:
        db.rollback()
        raise _http_error(exc) from None
    return {"stored": written, "provider": config.provider_view(db)}


@router.post("/credentials/{name}/delete")
def delete_credential(name: str, body: ReauthBody, request: Request, db: Session = Depends(get_db),
                      actor: User = Depends(get_current_active_user)):
    try:
        deleted = config.delete_credential(db, actor, name, password=body.current_password, ip=client_ip(request))
    except config.PaymentConfigError as exc:
        db.rollback()
        raise _http_error(exc) from None
    return {"deleted": deleted, "provider": config.provider_view(db)}


@router.post("/connection-test")
def connection_test(request: Request, db: Session = Depends(get_db),
                    actor: User = Depends(get_current_active_user)):
    """Read-only provider check: documented GET requests and the payout login
    (whose session is discarded at once). Creates no payment, starts no
    payout, confirms nothing and moves no funds."""
    # Each run logs in to the provider with the payout account. Bounded so that
    # a wrong stored password can never be replayed into an account lock-out.
    if _is_rate_limited(f"connection-test:{actor.id}", CONNECTION_TEST_LIMIT, CONNECTION_TEST_WINDOW):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail={"code": "RATE_LIMITED",
                                    "message": "Too many connection tests. Try again in a few minutes."})
    try:
        return config.run_connection_test(db, actor, ip=client_ip(request))
    except config.PaymentConfigError as exc:
        db.rollback()
        raise _http_error(exc) from None
