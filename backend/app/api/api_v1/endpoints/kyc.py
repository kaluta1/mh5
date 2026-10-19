from typing import List, Optional, Union
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request, Header, BackgroundTasks, Body, Query
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
import json
import logging

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.api import deps
from app.core.config import settings
from app.crud import crud_kyc
from app.crud import crud_deposit
from app.models.user import User
from app.models.geography import Country
from app.services.shufti_pro import (
    shufti_pro_service,
    kyc_flags_from_shufti_payload,
    normalize_country_iso2_for_shufti,
    resolve_shufti_callback_and_redirect_urls,
)
from app.core.client_ip import client_ip
from app.services import kyc_fee, kyc_settings
from app.services.kaluta_kyc import (
    UNAVAILABLE_MESSAGE,
    WEBHOOK_MAX_BODY_BYTES,
    active_kyc_provider,
    is_kaluta_active,
    kaluta_kyc_service,
    parse_provider_time,
)
from app.services.kyc_provider_dispatch import (
    check_kyc_session_validity,
    generate_kyc_reference,
    handle_kaluta_webhook,
    initiate_kyc_session,
    provider_for_verification,
    sync_verification_from_provider,
    verification_provider_enum,
)
from app.services import financial_eligibility as _fe
from app.models.kyc import KYCStatus, DocumentType, VerificationProvider
from app.schemas.kyc import (
    KYCVerification, KYCVerificationCreate, KYCVerificationUpdate,
    KYCDocument, KYCDocumentCreate, KYCDocumentUpdate,
    KYCDocumentWithPublicUrls,
    KYCVerificationAdminDetail,
    KYCAuditLog, KYCSubmissionRequest, KYCStatusResponse,
    KYCStatistics, KYCVerificationWithDocuments, KYCVerificationComplete,
    ShuftiProWebhookData, KYCWebhookResponse, KYCInitiateRequest,
)
from app.services.email import email_service
from app.services import kyc_notifications
from app.services.email_events import EmailEvent
from app.services.payment_accounting import payment_accounting
from app.services.proof_of_address_match import (
    normalized_address_key,
    evaluate_proof_of_address,
)
from app.core.storage import (
    iter_s3_object,
    parse_kyc_document_reference,
    resolve_kyc_document_for_serving,
    store_kyc_proof_file,
)
from app.core.security import create_kyc_document_view_token, verify_kyc_document_view_token
from app.models.kyc import KYCDocument as KYCDocumentModel, KYCVerification as KYCVerificationModel

logger = logging.getLogger(__name__)

router = APIRouter()


def _shufti_urls_for_client_error() -> dict:
    """Help operators align Shufti Backoffice allowlists with URLs this server sends."""
    cb = (shufti_pro_service.callback_url or "").strip()
    rd = (shufti_pro_service.redirect_url or "").strip()
    hosts: List[str] = []
    for u in (cb, rd):
        if not u:
            continue
        try:
            h = urlparse(u).hostname
            if h:
                hosts.append(h)
        except Exception:
            pass
    return {
        "callback_url": cb or None,
        "redirect_url": rd or None,
        "domains_to_register_in_shufti": sorted(set(hosts)),
        "hint": (
            "In Shufti Backoffice: Settings → Callback and Redirect URLs — add each listed domain "
            "(host only) for BOTH Callback and Redirect types. If you use www and apex separately, register BOTH. "
            "Also check Shufti settings for iframe / hosted verification domain allowlist (parent page must be allowed). "
            "Sandbox vs live keys must match where domains were registered. After changes, restart the API on your VPS."
        ),
    }


@router.get("/deployment/shufti-urls")
def get_shufti_deployment_urls(
    *,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Debug: URLs and hosts this server will send to Shufti (no secrets).
    Call while logged in; compare with Shufti Backoffice allowlists.
    """
    cb, rd = resolve_shufti_callback_and_redirect_urls()
    hosts: List[str] = []
    for u in (cb, rd):
        if not u:
            continue
        try:
            h = urlparse(u).hostname
            if h:
                hosts.append(h)
        except Exception:
            pass
    cid = (settings.SHUFTI_CLIENT_ID or "").strip()
    return {
        "callback_url": cb or None,
        "redirect_url": rd or None,
        "domains_to_register_in_shufti": sorted(set(hosts)),
        "env_FRONTEND_URL": (settings.FRONTEND_URL or "").strip() or None,
        "env_BACKEND_PUBLIC_URL": (settings.BACKEND_PUBLIC_URL or "").strip() or None,
        "env_SHUFTI_CALLBACK_URL_set": bool((settings.SHUFTI_CALLBACK_URL or "").strip()),
        "env_SHUFTI_REDIRECT_URL_set": bool((settings.SHUFTI_REDIRECT_URL or "").strip()),
        "shufti_client_id_prefix": (cid[:10] + "…") if len(cid) > 10 else (cid or None),
        "checklist": [
            "VPS: same values must exist in the process environment (systemd EnvironmentFile / docker env), not only local .env.",
            "Nginx: POST /api/v1/kyc/webhook/shufti-pro must reach FastAPI (test with curl from outside).",
            "Shufti Backoffice: register every hostname listed under domains_to_register_in_shufti for Callback AND Redirect.",
            "If INVALID persists inside iframe, try 'Open in new tab' on KYC page or add iframe/parent-site allowlist in Shufti.",
        ],
    }


def _shufti_country_iso2_for_user(db: Session, user: User) -> Optional[str]:
    """
    Shufti requires ISO 3166-1 alpha-2. User.country is often a full name; prefer countries.code via country_id.
    """
    if user.country_id:
        row = db.query(Country).filter(Country.id == user.country_id).first()
        if row and row.code:
            iso = normalize_country_iso2_for_shufti(row.code)
            if iso:
                return iso
    return normalize_country_iso2_for_shufti(user.country)


def _profile_full_name(user: User) -> Optional[str]:
    if user.full_name and str(user.full_name).strip():
        return str(user.full_name).strip()
    parts = [user.first_name or "", user.last_name or ""]
    joined = " ".join(p for p in parts if p).strip()
    return joined or None


def _public_file_url(stored: Optional[str]) -> Optional[str]:
    """Turn DB-stored path into a browser-openable URL (S3 already absolute; /media/... needs public API origin)."""
    if not stored or not str(stored).strip():
        return None
    s = str(stored).strip()
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return s
    base = (settings.BACKEND_PUBLIC_URL or "").strip().rstrip("/")
    if s.startswith("/") and base:
        return f"{base}{s}"
    return s


_KYC_DOCUMENT_SIDES = {"front": "front_image_url", "back": "back_image_url"}


def _admin_document_view_url(
    document_id: int, side: str, stored: Optional[str], viewer_user_id: int
) -> Optional[str]:
    """KYC files get a short-lived signed admin URL; any other stored value keeps
    its previous display behavior."""
    if parse_kyc_document_reference(stored) is None:
        return _public_file_url(stored)
    token = create_kyc_document_view_token(viewer_user_id, document_id, side)
    return _public_file_url(
        f"{settings.API_V1_STR}/kyc/admin/documents/{document_id}/{side}?{urlencode({'token': token})}"
    )


def _guard_kyc_initiation(db: Session, user: User) -> None:
    """Child/Teen Safety Phase 10: KYC collects identity documents and may send
    them to an external provider. Only for a person the central gate allows
    (KYC never grants age, guardian or financial eligibility by itself)."""
    try:
        _fe.require(db, user, _fe.FinancialOperation.KYC_INITIATION)
    except _fe.FinancialEligibilityHold as exc:
        raise _fe.http_error(exc) from None


def _session_expired_locally(verification) -> bool:
    """Has the provider session of an OPEN verification run out, by the expiry
    the provider gave when it was created (or that its expiry event set)? An
    EXPIRED verification (older records) is an open attempt whose session ended.
    False when no expiry is known."""
    if verification is None:
        return False
    if verification.status == KYCStatus.EXPIRED:
        return True
    return bool(verification.expires_at is not None
                and verification.status in (KYCStatus.PENDING, KYCStatus.IN_PROGRESS)
                and verification.expires_at <= datetime.utcnow())


# A new attempt (a new payment unless KYC is free) starts only from these.
_NEW_ATTEMPT_STATUSES = (KYCStatus.REJECTED, KYCStatus.REQUIRES_REVIEW)
# The attempt is open: continued, or given a fresh provider session, for free.
_OPEN_ATTEMPT_STATUSES = (KYCStatus.PENDING, KYCStatus.IN_PROGRESS, KYCStatus.EXPIRED)


def _attempt_view(verification, per_attempt: int) -> dict:
    return {
        "attempts_count": verification.attempts_count,
        "max_attempts": verification.max_attempts,
        "attempts_remaining": max(0, verification.max_attempts - verification.attempts_count),
        "sessions_remaining": kyc_settings.sessions_left(verification, per_attempt=per_attempt),
    }


def _refuse_closed(verification) -> None:
    if verification and verification.status == KYCStatus.PENDING_PROOF_OF_ADDRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete the proof-of-address step before restarting identity verification.",
        )
    if verification and verification.status == KYCStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your identity is already verified")


@router.post("/initiate")
async def initiate_shufti_verification(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    language: str = "FR",
    force_new: bool = Query(
        False,
        description="Skip reusing an in-flight Shufti session and request a fresh verification URL (fixes stale INVALID iframe).",
    ),
    payload: KYCInitiateRequest = Body(default_factory=KYCInitiateRequest),
):
    """
    Start or continue a KYC verification (Kaluta by default, Shufti Pro legacy).

    Rules:
    - ONE record per member.
    - APPROVED / PENDING_PROOF_OF_ADDRESS: refused.
    - PENDING / IN_PROGRESS: the open session is handed out again while it is valid.
    - Session ran out (expiry time passed, an expiry event, or EXPIRED): a fresh
      session for the SAME attempt: no payment, no new attempt, within the
      session limit of the attempt (the sessions-per-attempt setting in
      Admin > KYC plus what an administrator allowed). force_new also opens a fresh session and counts.
    - REJECTED / REQUIRES_REVIEW: a NEW attempt (attempt limit applies). It is
      paid with a paid, unused KYC payment, or free while the member KYC fee is
      0; a free attempt never uses a payment the member already made.
    """
    _guard_kyc_initiation(db, current_user)
    kyc_settings.apply(db)
    if is_kaluta_active() and not kaluta_kyc_service.configured():
        # Switched off or without a key: refused before an attempt is opened or a payment used.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Kaluta KYC is temporarily disabled." if not kaluta_kyc_service.enabled
                            else "Kaluta KYC is not configured (no API key saved in Admin > KYC).")
    per_attempt = kyc_settings.sessions_per_attempt(db)
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    _refuse_closed(verification)

    # Adresse résidentielle (obligatoire pour un nouveau cycle ; réutilisable si session verrouillée)
    raw_in = (payload.residential_address or "").strip()
    if raw_in and len(raw_in) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If provided, residential address must be at least 2 characters.",
        )

    # The open session is handed out again while it is valid (no lock: the
    # provider may be asked over the network; a decision found there is applied
    # under the verification's own lock).
    if (
        not force_new
        and verification
        and verification.status in (KYCStatus.PENDING, KYCStatus.IN_PROGRESS)
        and not _session_expired_locally(verification)
        and verification.reference_id
    ):
        reference = verification.reference_id
        validity_check = await check_kyc_session_validity(verification)
        if validity_check.get("is_completed"):
            synced = await sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=verification)
            if synced and synced.get("needs_proof_of_address"):
                return {
                    "verification_url": None,
                    "reference": reference,
                    "verification_id": verification.id,
                    "reused": True,
                    "provider": provider_for_verification(verification),
                    "status": "pending_proof_of_address",
                    "kyc_step": 2,
                    "needs_proof_of_address": True,
                    "message": "Identity verification accepted. Upload proof of address to finish KYC.",
                }
            if synced and synced.get("fully_approved"):
                return {
                    "verification_url": None,
                    "reference": reference,
                    "verification_id": verification.id,
                    "reused": True,
                    "provider": provider_for_verification(verification),
                    "status": "approved",
                    "kyc_step": 0,
                    "needs_proof_of_address": False,
                    "message": "KYC verification complete.",
                }
            if synced and synced.get("status") == "rejected":
                # The attempt has ended. A new one is a separate decision of the
                # member (and a new payment unless KYC is free): never opened here.
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
                    "code": "KYC_ATTEMPT_ENDED",
                    "message": "This verification attempt has ended. Reload the page to see the result."})
            db.refresh(verification)
        elif validity_check.get("is_valid"):
            verification_url = validity_check.get("verification_url") or verification.verification_url
            if verification_url:
                return {
                    "verification_url": verification_url,
                    "reference": reference,
                    "verification_id": verification.id,
                    "reused": True,
                    "provider": provider_for_verification(verification),
                    "status": "in_progress",
                    **_attempt_view(verification, per_attempt),
                }

    # From here on the member's row is locked until the next commit: two requests
    # at once are decided one after the other, so one paid payment opens one
    # attempt and the session limit cannot be passed by asking twice.
    db.query(User.id).filter(User.id == current_user.id).with_for_update().first()
    verification = (db.query(KYCVerificationModel).filter(KYCVerificationModel.user_id == current_user.id)
                    .populate_existing().first())
    _refuse_closed(verification)

    new_attempt = verification is None or verification.status in _NEW_ATTEMPT_STATUSES
    if new_attempt and verification is not None and verification.attempts_count >= verification.max_attempts:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You have reached the maximum number of attempts ({verification.max_attempts}). Please contact support."
        )

    valid_payment = None
    if new_attempt and not kyc_fee.is_free(db):
        # A paid, unused payment opens the attempt whatever the (non-zero) fee is now.
        valid_payment = crud_deposit.deposit.get_valid_deposit_for_product(
            db, user_id=current_user.id, product_code="kyc"
        )
        if not valid_payment:
            fee_amount, fee_currency = kyc_fee.member_fee(db)
            available_count = crud_deposit.deposit.count_valid_deposits_for_product(
                db, user_id=current_user.id, product_code="kyc"
            )
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": "Payment is required to complete KYC verification",
                    "available_attempts": available_count,
                    "price": float(fee_amount),
                    "currency": fee_currency
                }
            )
    # KYC is free (fee 0): no payment is looked for, and a paid one the member
    # holds is left exactly as it is (paid, unused) for a later paid attempt.

    if not new_attempt and kyc_settings.sessions_left(verification, per_attempt=per_attempt) <= 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "code": "KYC_SESSION_LIMIT_REACHED",
            "message": ("Your verification link was renewed the maximum number of times for this attempt. "
                        "Please contact support: they can allow one more. You will not be charged again."),
        })

    addr = raw_in
    if not new_attempt and len(addr) < 2 and verification.verified_address:
        addr = (verification.verified_address or "").strip()
    if new_attempt and len(addr) < 2:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Residential address is required (at least 2 characters) before starting verification.",
        )
    if (
        verification
        and not new_attempt
        and verification.residential_address_locked_at
        and verification.verified_address
        and len(addr) >= 2
        and normalized_address_key(addr) != normalized_address_key(verification.verified_address)
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Residential address is locked for this verification. "
                "To use a different address, complete or abandon this cycle and start a new paid verification."
            ),
        )

    reference = generate_kyc_reference(current_user.id)
    active_provider = verification_provider_enum()
    now = datetime.utcnow()

    if verification is None:
        verification = KYCVerificationModel(user_id=current_user.id, status=KYCStatus.PENDING, attempts_count=1,
                                            reference_id=reference, provider=active_provider, submitted_at=now,
                                            attempt_sessions_count=0, attempt_sessions_granted=0)
        db.add(verification)
    elif new_attempt:
        verification.attempts_count += 1
        verification.attempt_sessions_count = 0
        verification.attempt_sessions_granted = 0
        verification.residential_address_locked_at = None
        verification.identity_verified = False
        verification.document_verified = False
        verification.face_verified = False
        verification.address_verified = False
    if new_attempt:
        verification.submitted_at = now
    if valid_payment is not None:
        valid_payment.is_used = True
        valid_payment.used_at = now
    # One provider session of this attempt is taken now, before the provider is
    # asked, so that a second request cannot pass the limit meanwhile.
    verification.attempt_sessions_count = int(verification.attempt_sessions_count or 0) + 1
    verification.reference_id = reference
    verification.provider = active_provider
    verification.verification_url = None
    verification.status = KYCStatus.PENDING
    verification.processed_at = None
    verification.rejection_reason = None
    verification.rejection_details = None
    verification.expires_at = None
    if len(addr) >= 2:
        verification.verified_address = addr
    db.commit()
    db.refresh(verification)

    if new_attempt:
        # What this attempt cost stays with the verification, whatever the fee becomes later.
        crud_kyc.kyc_verification._create_audit_log(
            db, verification.id, "kyc_attempt_fee",
            f"Attempt {verification.attempts_count}: {kyc_fee.attempt_fee_note(valid_payment)}",
            current_user.id, False,
        )

    # Appeler le provider KYC actif (Kaluta ou Shufti legacy)
    lang = (language or "en").strip().lower()
    if len(lang) > 2:
        lang = lang[:2]

    # The dispatcher's contract is keyword-only and requires the live request
    # session (it re-checks KYC_INITIATION eligibility right before any
    # provider I/O). Omitting it raised TypeError here since c30a215.
    result = await initiate_kyc_session(
        db=db,
        user=current_user,
        reference=reference,
        language=lang,
        country_iso=_shufti_country_iso2_for_user(db, current_user),
        residential_address=addr if len(addr) >= 2 else None,
    )

    if not result.get("success"):
        if result.get("no_session_created"):
            # The provider refused before opening anything (or was not asked):
            # the session taken for this request is given back.
            row = (db.query(KYCVerificationModel).filter(KYCVerificationModel.id == verification.id)
                   .with_for_update().populate_existing().first())
            if row is not None and int(row.attempt_sessions_count or 0) > 0:
                row.attempt_sessions_count = int(row.attempt_sessions_count) - 1
            db.commit()
        err = result.get("error", "Verification could not be started")
        err_l = (err or "").lower()
        if is_kaluta_active():
            if "not configured" in err_l or "kaluta_api_key" in err_l or "disabled" in err_l:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=err,
                )
            # The provider refused or could not be reached. Nothing of its answer is
            # shown; the same paid attempt can be started again later.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=UNAVAILABLE_MESSAGE,
            )
        # Shufti misconfiguration / bad credentials — clearer than generic 500
        if (
            "shufti pro is not configured" in err_l
            or "authorization keys" in err_l
            or "shufti_client_id" in err_l
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=err,
            )
        if (
            "callback domain" in err_l
            or "redirect domain" in err_l
            or "not registered" in err_l
            or "callback url is not configured" in err_l
            or "redirect url is not configured" in err_l
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": err, **_shufti_urls_for_client_error()},
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=err,
        )

    verification_url = result.get("verification_url")
    external_id = result.get("session_id") or result.get("reference") or reference

    # Mettre à jour avec l'URL et le statut IN_PROGRESS
    if verification.residential_address_locked_at is None:
        update_data = KYCVerificationUpdate(
            status=KYCStatus.IN_PROGRESS,
            external_verification_id=external_id,
            verification_url=verification_url,
            residential_address_locked_at=datetime.utcnow(),
        )
    else:
        update_data = KYCVerificationUpdate(
            status=KYCStatus.IN_PROGRESS,
            external_verification_id=external_id,
            verification_url=verification_url,
        )
    # When the provider's session ends (24 hours for Kaluta). None for a provider that does not say.
    update_data.expires_at = parse_provider_time(result.get("expires_at"))
    crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
    if active_provider == VerificationProvider.KALUTA:
        crud_kyc.kyc_verification._create_audit_log(
            db, verification.id, "kaluta_session_created",
            f"Provider session {external_id} opened (attempt {verification.attempts_count}, "
            f"session {verification.attempt_sessions_count} of {kyc_settings.session_allowance(verification, per_attempt=per_attempt)})",
            current_user.id, False,
        )

    return {
        "verification_url": verification_url,
        "reference": reference,
        "verification_id": verification.id,
        "reused": False,
        "provider": active_kyc_provider(),
        "status": "new",
        **_attempt_view(verification, per_attempt),
    }


class KycFeeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: str = Field(..., max_length=20)
    current_password: str = Field(default="", max_length=256)
    # The fee the administrator was shown; the change is refused if it has moved since.
    expected_amount: Optional[str] = Field(default=None, max_length=20)


def _kyc_fee_http_error(exc: kyc_fee.KycFeeError) -> HTTPException:
    code = {"FORBIDDEN": status.HTTP_403_FORBIDDEN, "REAUTH_REQUIRED": status.HTTP_403_FORBIDDEN,
            "REAUTH_LOCKED": status.HTTP_429_TOO_MANY_REQUESTS,
            "INVALID_VALUE": status.HTTP_422_UNPROCESSABLE_ENTITY}.get(exc.code, status.HTTP_409_CONFLICT)
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})


@router.get("/fee")
def get_member_kyc_fee(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """What one new verification attempt costs a member now (0 = free)."""
    return kyc_fee.fee_view(db)


@router.get("/admin/fee")
def get_admin_kyc_fee(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    return {**kyc_fee.fee_view(db), "max_amount": f"{kyc_fee.MAX_FEE:.2f}",
            "can_change": kyc_settings.has_permission(current_user), "permission": kyc_settings.PERMISSION,
            "last_change": kyc_fee.last_change(db)}


@router.put("/admin/fee")
def set_admin_kyc_fee(
    body: KycFeeBody,
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    """Set the Member KYC Verification Fee (USD). 0 = free KYC. Applies to
    attempts paid from now on; existing payments keep their amount."""
    try:
        kyc_fee.set_member_fee(db, current_user, body.amount, password=body.current_password,
                               ip=client_ip(request), expected_amount=body.expected_amount)
    except kyc_fee.KycFeeError as exc:
        db.rollback()
        raise _kyc_fee_http_error(exc) from None
    return get_admin_kyc_fee(db=db, current_user=current_user)


class KycSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Absent or null = keep. A key or secret is write-only: blank keeps the saved one.
    enabled: Optional[bool] = None
    api_key: Optional[str] = Field(default=None, max_length=512)
    webhook_secret: Optional[str] = Field(default=None, max_length=512)
    # The Member KYC Verification Fee in USD ("10.00"; 0 = free) and the provider
    # sessions one attempt may open. Validated by app.services.kyc_settings.
    member_fee: Optional[str] = Field(default=None, max_length=20)
    sessions_per_attempt: Optional[Union[StrictInt, str]] = Field(default=None)
    current_password: str = Field(default="", max_length=256)
    # What the administrator was shown; the change is refused if it has moved since.
    expected_version: Optional[int] = Field(default=None, ge=0)
    expected_fee: Optional[str] = Field(default=None, max_length=20)


class KycSessionGrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(default="", max_length=256)


def _kyc_settings_http_error(exc: kyc_settings.KycSettingsError) -> HTTPException:
    code = {"FORBIDDEN": status.HTTP_403_FORBIDDEN, "REAUTH_REQUIRED": status.HTTP_403_FORBIDDEN,
            "REAUTH_LOCKED": status.HTTP_429_TOO_MANY_REQUESTS, "NOT_FOUND": status.HTTP_404_NOT_FOUND,
            "INVALID_VALUE": status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_FIELD": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "NOTHING_TO_CHANGE": status.HTTP_422_UNPROCESSABLE_ENTITY}.get(exc.code, status.HTTP_409_CONFLICT)
    detail = {"code": exc.code, "message": str(exc)}
    if exc.field:
        detail["field"] = exc.field
    return HTTPException(status_code=code, detail=detail)


@router.get("/admin/settings")
def get_admin_kyc_settings(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    """Kaluta KYC settings as the Admin Panel shows them (the database is their
    only source): on/off, whether a key and a secret are saved, never their
    values, the member fee and the sessions per attempt."""
    return kyc_settings.view(db, current_user)


@router.put("/admin/settings")
def set_admin_kyc_settings(
    body: KycSettingsBody,
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    """Save the KYC settings form: Kaluta on/off, replace its API key or webhook
    secret, the member fee, the sessions per attempt (manage_kyc_settings +
    current password; secrets stored encrypted; audited without their values;
    one commit, nothing changed on any refusal)."""
    try:
        return kyc_settings.update(
            db, current_user, password=body.current_password, enabled=body.enabled,
            credentials={"API_KEY": body.api_key, "WEBHOOK_SECRET": body.webhook_secret},
            member_fee=body.member_fee, sessions=body.sessions_per_attempt,
            expected_version=body.expected_version, expected_fee=body.expected_fee, ip=client_ip(request))
    except kyc_settings.KycSettingsError as exc:
        db.rollback()
        raise _kyc_settings_http_error(exc) from None


@router.post("/admin/verification/{verification_id}/grant-session")
def grant_kyc_session(
    verification_id: int,
    body: KycSessionGrantBody,
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    """Allow ONE more provider session for a member whose open attempt used every
    session it had (no payment, no new attempt; audited)."""
    try:
        return kyc_settings.grant_session(db, current_user, verification_id, password=body.current_password,
                                          ip=client_ip(request))
    except kyc_settings.KycSettingsError as exc:
        db.rollback()
        raise _kyc_settings_http_error(exc) from None


@router.get("/redirect")
async def shufti_redirect(
    status: Optional[str] = None,
    reference: Optional[str] = None
):
    """
    Endpoint de redirection Shufti Pro.
    Redirige vers le frontend après la vérification.
    """
    frontend_url = settings.FRONTEND_URL
    query = {"status": (status or "completed")[:40]}
    if reference:
        query["reference"] = reference[:200]
    redirect_target = f"{frontend_url}/dashboard/kyc?{urlencode(query)}"
    return RedirectResponse(url=redirect_target)


@router.get("/status-detailed")
async def get_kyc_status_detailed(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Récupérer le statut KYC détaillé de l'utilisateur actuel.
    Synchronise avec Shufti Pro si une vérification est en cours.
    """
    kyc_settings.apply(db)
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)

    fee_amount, fee_currency = kyc_fee.member_fee(db)
    kyc_is_free = fee_amount <= 0

    if not verification:
        paid = crud_deposit.deposit.count_valid_deposits_for_product(
            db, user_id=current_user.id, product_code="kyc"
        )
        return {
            "status": None,
            "can_start": True,
            "message": "No KYC verification found",
            # The fee is shown before the member starts.
            "available_payments": paid,
            "has_valid_payment": paid > 0,
            "needs_payment": paid == 0 and not kyc_is_free,
            "kyc_price": float(fee_amount),
            "kyc_currency": fee_currency,
            "kyc_is_free": kyc_is_free,
            "kyc_retry_policy": kyc_fee.RETRY_POLICY,
        }
    
    # Si en cours, synchroniser avec le provider KYC actif
    if verification.status in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS] and verification.reference_id:
        await sync_verification_from_provider(db, crud_kyc=crud_kyc, verification=verification)
        db.refresh(verification)

    # Déterminer si l'utilisateur peut démarrer/reprendre une vérification
    max_attempts_reached = verification.attempts_count >= verification.max_attempts
    # A NEW attempt only after a decision. A session that ran out (EXPIRED on
    # older records) leaves the attempt open: it is continued, not restarted.
    can_restart = verification.status in [
        KYCStatus.REJECTED,
        KYCStatus.REQUIRES_REVIEW,
    ] and not max_attempts_reached
    can_continue = verification.status in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS, KYCStatus.EXPIRED]
    session_expired = _session_expired_locally(verification)
    sessions_remaining = (kyc_settings.sessions_left(verification, per_attempt=kyc_settings.sessions_per_attempt(db))
                          if can_continue else None)
    needs_proof_of_address = verification.status == KYCStatus.PENDING_PROOF_OF_ADDRESS
    if verification.status == KYCStatus.APPROVED:
        kyc_step = 0
    elif needs_proof_of_address:
        kyc_step = 2
    elif can_continue:
        kyc_step = 1
    else:
        kyc_step = 1
    
    # Vérifier le statut de paiement pour les tentatives futures
    available_payments = crud_deposit.deposit.count_valid_deposits_for_product(
        db, user_id=current_user.id, product_code="kyc"
    )
    has_valid_payment = available_payments > 0
    
    # Si can_restart mais pas de paiement, indiquer qu'il faut payer
    needs_payment = can_restart and not has_valid_payment and not kyc_is_free
    
    return {
        "status": verification.status.value if verification.status else None,
        "submitted_at": verification.submitted_at,
        "processed_at": verification.processed_at,
        "rejection_reason": verification.rejection_reason,
        "identity_verified": verification.identity_verified,
        "document_verified": verification.document_verified,
        "face_verified": verification.face_verified,
        "address_verified": verification.address_verified,
        "declared_residential_address": verification.verified_address,
        "residential_address_locked": bool(verification.residential_address_locked_at),
        "needs_proof_of_address": needs_proof_of_address,
        "kyc_step": kyc_step,
        "can_restart": can_restart and (has_valid_payment or kyc_is_free),  # paid, or KYC is free
        "can_continue": can_continue,
        # A link whose session has run out is not shown; "continue" then opens a fresh session
        # for the same attempt (no payment), while the attempt has sessions left.
        "verification_url": (verification.verification_url
                             if can_continue and not session_expired else None),
        "session_expired": session_expired,
        "sessions_remaining": sessions_remaining,
        "session_limit_reached": bool(can_continue and session_expired and sessions_remaining == 0),
        "attempts_count": verification.attempts_count,
        "max_attempts": verification.max_attempts,
        "attempts_remaining": max(0, verification.max_attempts - verification.attempts_count),
        "max_attempts_reached": max_attempts_reached,
        # Informations de paiement
        "available_payments": available_payments,
        "has_valid_payment": has_valid_payment,
        "needs_payment": needs_payment,
        "kyc_price": float(fee_amount),
        "kyc_currency": fee_currency,
        "kyc_is_free": kyc_is_free,
        "kyc_retry_policy": kyc_fee.RETRY_POLICY,
        "provider": provider_for_verification(verification),
        "kyc_provider": active_kyc_provider(),
    }


@router.post("/submit", response_model=KYCVerification)
def submit_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    kyc_data: KYCSubmissionRequest
) -> KYCVerification:
    """
    Soumettre une nouvelle demande de vérification KYC
    """
    _guard_kyc_initiation(db, current_user)
    # Vérifier si l'utilisateur a déjà une vérification en cours
    existing_verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    if existing_verification and existing_verification.status in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A KYC verification is already in progress for this user"
        )
    
    # Créer la nouvelle vérification
    verification_create = KYCVerificationCreate(
        user_id=current_user.id,
        status=KYCStatus.PENDING,
        verified_first_name=kyc_data.first_name,
        verified_last_name=kyc_data.last_name,
        verified_date_of_birth=kyc_data.date_of_birth,
        verified_nationality=kyc_data.nationality,
        verified_address=kyc_data.address,
        reference_id=f"KYC_{current_user.id}_{int(datetime.utcnow().timestamp())}"
    )
    
    verification = crud_kyc.kyc_verification.create(db=db, obj_in=verification_create)
    
    # Créer le document associé avec les URLs uploadées
    document_create = KYCDocumentCreate(
        verification_id=verification.id,
        document_type=kyc_data.document_type,
        document_number=kyc_data.document_number,
        issuing_country=kyc_data.issuing_country,
        front_image_url=kyc_data.document_front if kyc_data.document_front else None,
        back_image_url=kyc_data.document_back if kyc_data.document_back else None,
        selfie_image_url=kyc_data.selfie if kyc_data.selfie else None
    )
    
    crud_kyc.kyc_document.create(db=db, obj_in=document_create)
    
    return verification


@router.get("/status", response_model=KYCStatusResponse)
def get_kyc_status(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> KYCStatusResponse:
    """
    Récupérer le statut de vérification KYC de l'utilisateur actuel
    Returns 404 if no verification exists (for backward compatibility)
    For a more user-friendly response, use /status-detailed instead
    """
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No KYC verification found for this user"
        )
    
    return KYCStatusResponse(
        verification_id=verification.id,
        status=verification.status,
        identity_verified=verification.identity_verified,
        address_verified=verification.address_verified,
        document_verified=verification.document_verified,
        face_verified=verification.face_verified,
        submitted_at=verification.submitted_at,
        processed_at=verification.processed_at,
        rejection_reason=verification.rejection_reason,
        expires_at=verification.expires_at
    )


@router.get("/submission", response_model=KYCSubmissionRequest)
def get_kyc_submission(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> KYCSubmissionRequest:
    """
    Récupérer les données de soumission KYC de l'utilisateur actuel
    """
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No KYC verification found for this user"
        )
    
    # Récupérer le document associé
    documents = crud_kyc.kyc_document.get_by_verification(db, verification_id=verification.id)
    document = documents[0] if documents else None
    
    return KYCSubmissionRequest(
        first_name=verification.verified_first_name or "",
        last_name=verification.verified_last_name or "",
        date_of_birth=verification.verified_date_of_birth or datetime.utcnow(),
        nationality=verification.verified_nationality or "",
        address=verification.verified_address or "",
        document_type=document.document_type if document else DocumentType.PASSPORT,
        document_number=document.document_number or "" if document else "",
        issuing_country=document.issuing_country or "" if document else "",
        document_front=document.front_image_url or "" if document else "",
        document_back=document.back_image_url or "" if document else "",
        selfie=document.selfie_image_url or "" if document else ""
    )


@router.get("/verification/{verification_id}", response_model=KYCVerificationWithDocuments)
def get_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    current_user: User = Depends(deps.get_current_active_user)
) -> KYCVerificationWithDocuments:
    """
    Récupérer les détails d'une vérification KYC avec ses documents
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC verification not found"
        )
    
    # Vérifier que l'utilisateur peut accéder à cette vérification
    if verification.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this verification"
        )
    
    # Récupérer les documents associés
    documents = crud_kyc.kyc_document.get_by_verification(db, verification_id=verification_id)
    
    return KYCVerificationWithDocuments(
        **verification.__dict__,
        documents=documents
    )


@router.post("/verification/{verification_id}/upload-document")
def upload_kyc_document(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    document_type: DocumentType = Form(...),
    front_image: UploadFile = File(...),
    back_image: Optional[UploadFile] = File(None),
    selfie_image: Optional[UploadFile] = File(None)
):
    """
    Télécharger des documents pour une vérification KYC
    """
    _guard_kyc_initiation(db, current_user)
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC verification not found"
        )
    
    if verification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this verification"
        )
    
    if verification.status not in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Documents cannot be uploaded for this verification"
        )
    
    # TODO: Implémenter le stockage des fichiers (S3, local, etc.)
    # Pour l'instant, on simule les URLs
    front_url = f"/uploads/kyc/{verification_id}/{document_type.value}_front_{front_image.filename}"
    back_url = f"/uploads/kyc/{verification_id}/{document_type.value}_back_{back_image.filename}" if back_image else None
    selfie_url = f"/uploads/kyc/{verification_id}/selfie_{selfie_image.filename}" if selfie_image else None
    
    # Mettre à jour ou créer le document
    existing_document = crud_kyc.kyc_document.get_by_type(
        db, verification_id=verification_id, document_type=document_type
    )
    
    if existing_document:
        document_update = KYCDocumentUpdate(
            front_image_url=front_url,
            back_image_url=back_url,
            selfie_image_url=selfie_url
        )
        crud_kyc.kyc_document.update(db=db, db_obj=existing_document, obj_in=document_update)
    else:
        document_create = KYCDocumentCreate(
            verification_id=verification_id,
            document_type=document_type,
            front_image_url=front_url,
            back_image_url=back_url,
            selfie_image_url=selfie_url
        )
        crud_kyc.kyc_document.create(db=db, obj_in=document_create)
    
    # Mettre à jour le statut de la vérification
    if verification.status == KYCStatus.PENDING:
        verification_update = KYCVerificationUpdate(status=KYCStatus.IN_PROGRESS)
        crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=verification_update)
    
    return {"message": "Documents uploaded successfully"}


# Endpoints administrateur
@router.get("/admin/verifications", response_model=List[KYCVerification])
def list_kyc_verifications(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
    status_filter: Optional[KYCStatus] = None,
    skip: int = 0,
    limit: int = 10
) -> List[KYCVerification]:
    """
    Lister toutes les vérifications KYC (admin seulement)
    """
    if status_filter:
        return crud_kyc.kyc_verification.get_by_status(
            db, status=status_filter, skip=skip, limit=limit
        )
    else:
        return crud_kyc.kyc_verification.get_multi(db, skip=skip, limit=limit)


@router.get("/admin/pending", response_model=List[KYCVerification])
def get_pending_verifications(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
    skip: int = 0,
    limit: int = 10
) -> List[KYCVerification]:
    """
    Récupérer les vérifications en attente (admin seulement)
    """
    return crud_kyc.kyc_verification.get_pending_verifications(db, skip=skip, limit=limit)


@router.get("/admin/verification/{verification_id}/detail", response_model=KYCVerificationAdminDetail)
def admin_kyc_verification_detail(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    current_user: User = Depends(deps.get_current_admin_user),
) -> KYCVerificationAdminDetail:
    """
    Détail KYC pour l’admin : tous les documents (dont justificatif de domicile) avec URLs publiques pour affichage.
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC verification not found",
        )

    u = db.query(User).filter(User.id == verification.user_id).first()
    documents = crud_kyc.kyc_document.get_by_verification(db, verification_id=verification_id)

    out_docs: List[KYCDocumentWithPublicUrls] = []
    for d in documents:
        base_doc = KYCDocument.model_validate(d)
        out_docs.append(
            KYCDocumentWithPublicUrls(
                **base_doc.model_dump(),
                front_public_url=_admin_document_view_url(d.id, "front", d.front_image_url, current_user.id),
                back_public_url=_admin_document_view_url(d.id, "back", d.back_image_url, current_user.id),
            )
        )

    base_v = KYCVerification.model_validate(verification)
    return KYCVerificationAdminDetail(
        **base_v.model_dump(),
        documents=out_docs,
        user_email=u.email if u else None,
        user_full_name=(str(u.full_name).strip() if u and u.full_name else None),
        sessions_per_attempt=kyc_settings.sessions_per_attempt(db),
    )


@router.get("/admin/documents/{document_id}/{side}", include_in_schema=False)
def admin_view_kyc_document(
    *,
    db: Session = Depends(deps.get_db),
    document_id: int,
    side: str,
    token: str = Query(""),
):
    """
    Serve one KYC document file to an admin. Authorized by the short-lived
    signed token issued in the admin verification detail (the admin UI loads
    it via <img src>/<a href>, which cannot carry a bearer header). The token's
    user must still be an active admin. Every failure is an identical 404.
    """
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    column = _KYC_DOCUMENT_SIDES.get(side)
    viewer_id = verify_kyc_document_view_token(token, document_id, side) if column else None
    if viewer_id is None:
        raise not_found
    viewer = db.query(User).filter(User.id == viewer_id).first()
    if not viewer or not viewer.is_active or not viewer.is_admin:
        raise not_found

    document = db.query(KYCDocumentModel).filter(KYCDocumentModel.id == document_id).first()
    if not document:
        raise not_found
    verification = (
        db.query(KYCVerificationModel)
        .filter(KYCVerificationModel.id == document.verification_id)
        .first()
    )
    if not verification:
        raise not_found

    source, ref, content_type, inline = resolve_kyc_document_for_serving(
        getattr(document, column), verification.user_id
    )
    if not source or not ref:
        raise not_found

    headers = {
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Disposition": "inline" if inline else "attachment",
    }
    if source == "local":
        return FileResponse(ref, media_type=content_type, headers=headers)
    bucket = (settings.S3_BUCKET_NAME or settings.AWS_S3_BUCKET or "").strip()
    return StreamingResponse(iter_s3_object(bucket, ref), media_type=content_type, headers=headers)


@router.post("/admin/verification/{verification_id}/approve", response_model=KYCVerification)
def approve_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.get_current_admin_user)
) -> KYCVerification:
    """
    Approuver une vérification KYC (admin seulement)
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC verification not found"
        )
    
    if verification.status not in [
        KYCStatus.PENDING,
        KYCStatus.IN_PROGRESS,
        KYCStatus.PENDING_PROOF_OF_ADDRESS,
        KYCStatus.REQUIRES_REVIEW,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification cannot be approved"
        )
    
    result = crud_kyc.kyc_verification.approve_verification(
        db, verification_id=verification_id, admin_user_id=current_user.id
    )
    payment_accounting.post_kyc_verification_recognition_for_user(db, result.user_id)
    
    # Envoyer l'email de confirmation KYC approuvé
    verified_user = db.query(User).filter(User.id == verification.user_id).first()
    if verified_user:
        email_service.enqueue(
            db,
            event=EmailEvent.KYC_APPROVED,
            recipient=verified_user.email,
            user_id=verified_user.id,
            lang=getattr(verified_user, 'preferred_language', None),
            idempotency_key=f"kyc.approved:{verification.id}:{int(verification.attempts_count or 0)}",
        )
    
    return result


@router.post("/admin/verification/{verification_id}/reject", response_model=KYCVerification)
def reject_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.get_current_admin_user),
    reason: str = Form(...),
    details: Optional[str] = Form(None)
) -> KYCVerification:
    """
    Rejeter une vérification KYC (admin seulement)
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC verification not found"
        )
    
    if verification.status not in [
        KYCStatus.PENDING,
        KYCStatus.IN_PROGRESS,
        KYCStatus.PENDING_PROOF_OF_ADDRESS,
        KYCStatus.REQUIRES_REVIEW,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification cannot be rejected"
        )
    
    result = crud_kyc.kyc_verification.reject_verification(
        db, verification_id=verification_id, reason=reason, 
        details=details, admin_user_id=current_user.id
    )
    
    # Envoyer l'email de notification KYC rejeté
    rejected_user = db.query(User).filter(User.id == verification.user_id).first()
    if rejected_user:
        email_service.enqueue(
            db,
            event=EmailEvent.KYC_REJECTED,
            recipient=rejected_user.email,
            user_id=rejected_user.id,
            lang=getattr(rejected_user, 'preferred_language', None),
            context={"reason": reason},
            idempotency_key=f"kyc.rejected:{verification.id}:{int(verification.attempts_count or 0)}",
        )
    
    return result


@router.get("/admin/statistics", response_model=KYCStatistics)
def get_kyc_statistics(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
    days: int = 30
) -> KYCStatistics:
    """
    Récupérer les statistiques KYC (admin seulement)
    """
    return crud_kyc.kyc_verification.get_statistics(db, days=days)


@router.get("/admin/verification/{verification_id}/audit", response_model=List[KYCAuditLog])
def get_verification_audit_logs(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    current_user: User = Depends(deps.get_current_admin_user)
) -> List[KYCAuditLog]:
    """
    Récupérer les logs d'audit d'une vérification (admin seulement)
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC verification not found"
        )
    
    return crud_kyc.kyc_audit_log.get_by_verification(db, verification_id=verification_id)


@router.post("/proof-of-address")
async def submit_proof_of_address(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    document_type: DocumentType = Form(...),
    name_on_document: str = Form(...),
    address_as_shown_on_document: str = Form(...),
    document_front: UploadFile = File(...),
    document_back: Optional[UploadFile] = File(None),
):
    """
    Étape 2 : fichiers justificatif (image ou PDF) + texte saisi ; correspondance heuristique avec l’adresse verrouillée.
    """
    _guard_kyc_initiation(db, current_user)
    name_on_document = (name_on_document or "").strip()
    address_as_shown_on_document = (address_as_shown_on_document or "").strip()
    if len(name_on_document) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name_on_document must be at least 2 characters.",
        )
    if len(address_as_shown_on_document) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="address_as_shown_on_document must be at least 8 characters.",
        )
    if document_type not in (
        DocumentType.UTILITY_BILL,
        DocumentType.ADDRESS_PROOF,
        DocumentType.BANK_STATEMENT,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_type must be utility_bill, address_proof, or bank_statement.",
        )

    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    if not verification or verification.status != KYCStatus.PENDING_PROOF_OF_ADDRESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proof of address can only be submitted after identity verification is accepted.",
        )
    locked = (verification.verified_address or "").strip()
    if not locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No residential address on file; restart KYC from step 1.",
        )

    ok, reason = evaluate_proof_of_address(
        locked_residential_address=locked,
        profile_full_name=_profile_full_name(current_user),
        name_on_document=name_on_document,
        address_as_shown_on_document=address_as_shown_on_document,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": reason, "message": "Proof of address does not match your profile or declared address."},
        )

    try:
        front_info = await store_kyc_proof_file(document_front, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    back_url: Optional[str] = None
    if document_back is not None and (document_back.filename or "").strip():
        try:
            back_info = await store_kyc_proof_file(document_back, current_user.id)
            back_url = back_info["url"]
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    front_url = front_info["url"]

    # Persist submitted text + marker in DB (URLs go to front_image_url / back_image_url).
    poa_notes = json.dumps(
        {
            "source": "proof_of_address_auto",
            "name_on_document": name_on_document,
            "address_as_shown_on_document": address_as_shown_on_document,
        },
        ensure_ascii=False,
    )

    existing = crud_kyc.kyc_document.get_by_type(
        db, verification_id=verification.id, document_type=document_type
    )
    now = datetime.utcnow()
    if existing:
        crud_kyc.kyc_document.update(
            db,
            db_obj=existing,
            obj_in=KYCDocumentUpdate(
                front_image_url=front_url,
                back_image_url=back_url,
                is_verified=True,
                verification_notes=poa_notes,
                verified_at=now,
            ),
        )
    else:
        created_doc = crud_kyc.kyc_document.create(
            db,
            obj_in=KYCDocumentCreate(
                verification_id=verification.id,
                document_type=document_type,
                front_image_url=front_url,
                back_image_url=back_url,
            ),
        )
        crud_kyc.kyc_document.update(
            db,
            db_obj=created_doc,
            obj_in=KYCDocumentUpdate(
                is_verified=True,
                verification_notes=poa_notes,
                verified_at=now,
            ),
        )

    crud_kyc.kyc_verification.finalize_proof_of_address_auto(db, verification_id=verification.id)
    payment_accounting.post_kyc_verification_recognition_for_user(db, verification.user_id)
    # The approval is committed: tell the member (the main approval path; it used to send nothing).
    kyc_notifications.notify_status(db, verification.id)

    return {
        "success": True,
        "status": "approved",
        "verification_id": verification.id,
        "message": "KYC complete.",
    }


# Webhook pour Shufti Pro
@router.post("/webhook/shufti-pro", response_model=KYCWebhookResponse)
async def shufti_pro_webhook(
    *,
    request: Request,
    db: Session = Depends(deps.get_db),
):
    """
    Webhook pour recevoir les résultats de Shufti Pro
    """
    if active_kyc_provider() != "shufti_pro":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not enabled")

    raw = await request.body()
    signature = request.headers.get("signature", "")
    if not shufti_pro_service.verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    try:
        webhook_data = ShuftiProWebhookData.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload") from exc

    # Trouver la vérification par référence
    verification = crud_kyc.kyc_verification.get_by_reference(
        db, reference_id=webhook_data.reference
    )
    
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification not found"
        )
    
    # Traiter les résultats selon l'événement
    if webhook_data.event == "verification.accepted":
        if verification.status in (KYCStatus.PENDING_PROOF_OF_ADDRESS, KYCStatus.APPROVED):
            return KYCWebhookResponse(success=True, message="Webhook already processed", verification_id=verification.id)
        wh_raw = webhook_data.model_dump()
        flags = kyc_flags_from_shufti_payload(wh_raw, overall_accepted=True)
        crud_kyc.kyc_verification.apply_shufti_identity_accepted(
            db,
            verification=verification,
            flags=flags,
            external_verification_id=webhook_data.reference,
            provider_response=str(webhook_data.verification_result),
            webhook_data=str(wh_raw),
        )
        kyc_notifications.notify_status(db, verification.id)          # committed: proof of address expected

    elif webhook_data.event == "verification.declined":
        if verification.status == KYCStatus.REJECTED:
            return KYCWebhookResponse(success=True, message="Webhook already processed", verification_id=verification.id)
        if verification.status in (KYCStatus.PENDING_PROOF_OF_ADDRESS, KYCStatus.APPROVED):
            return KYCWebhookResponse(success=True, message="Stale webhook ignored", verification_id=verification.id)
        # Rejeter automatiquement
        reason = webhook_data.declined_reason or "Verification failed"
        crud_kyc.kyc_verification.reject_verification(
            db, verification_id=verification.id, reason=reason
        )

        wh_raw = webhook_data.model_dump()
        flags = kyc_flags_from_shufti_payload(wh_raw, overall_accepted=False)
        # Mettre à jour avec les données du webhook
        update_data = KYCVerificationUpdate(
            external_verification_id=webhook_data.reference,
            provider_response=str(webhook_data.verification_result),
            webhook_data=str(webhook_data.model_dump()),
            rejection_reason=reason,
            identity_verified=flags["identity_verified"],
            document_verified=flags["document_verified"],
            face_verified=flags["face_verified"],
        )
        crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
        # Committed: REJECTED. The provider's reason is never emailed.
        kyc_notifications.notify_status(db, verification.id)

    return KYCWebhookResponse(
        success=True,
        message="Webhook processed successfully",
        verification_id=verification.id
    )


@router.post("/webhook/kaluta")
async def kaluta_kyc_webhook(
    request: Request,
    db: Session = Depends(deps.get_db),
):
    """
    Kaluta KYC webhook (session.approved, session.rejected, session.expired, …).
    Verifies X-Kaluta-Signature with the webhook secret saved in Admin > KYC (refused when none is saved).
    """
    if not kyc_settings.kaluta_enabled(db):
        logger.warning("Kaluta KYC webhook received while Kaluta KYC is switched off — rejecting")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kaluta KYC integration is temporarily disabled.",
        )
    declared = request.headers.get("content-length") or ""
    if declared.isdigit() and int(declared) > WEBHOOK_MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
    raw = await request.body()
    signature = request.headers.get("x-kaluta-signature") or ""

    # Nothing in the body is read, and nothing is looked up, before the signature holds.
    if not kaluta_kyc_service.verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    outcome = handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=payload, ip=client_ip(request))
    # Acknowledged whatever it changed: a duplicate, a late event or an event for
    # a session this server no longer tracks must not be delivered again. (An
    # error while applying it is NOT caught: the provider then retries.)
    return {"ok": True, "result": outcome}


@router.get("/deployment/kaluta-urls")
def get_kaluta_deployment_urls(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
):
    """Debug: Kaluta webhook/redirect URLs this server uses (no secrets)."""
    kyc_settings.apply(db)
    webhook, redirect = kaluta_kyc_service.webhook_url, kaluta_kyc_service.redirect_url
    return {
        "kyc_provider": active_kyc_provider(),
        "webhook_url": webhook or None,
        "redirect_url": redirect or None,
        "api_key_configured": kaluta_kyc_service.configured(),
        "webhook_secret_configured": bool(kaluta_kyc_service.webhook_secret),
        "checklist": [
            "Save the Kaluta API key and webhook secret in Admin > KYC (the server environment is not used).",
            "Register webhook URL in Kaluta Dashboard → Webhooks.",
            "Ensure POST /api/v1/kyc/webhook/kaluta is reachable from the public internet.",
        ],
    }
