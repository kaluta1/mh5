from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.schemas.token import Token
from app.schemas.user import UserRegister, User
from app.api.api_v1.endpoints.guardian import CompleteRegistrationBody
from app.schemas.password_reset import (
    EmailVerificationConfirm,
    PasswordChange,
    PasswordChangeResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    RegistrationAccepted,
    ResendVerificationRequest,
)
from app.core import rate_limit
from app.core.rate_limit import ROUTE_LIMIT_MESSAGE, rate_limit_response
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
    validate_access_token,
)
from app.core.config import settings
from app.db.session import get_db
from app.crud import user as crud_user
from app.api.deps import get_current_active_user, oauth2_scheme
from app.models.auth_security import PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET
from app.services import auth_security, auth_throttle, auth_tokens
from app.services.email import email_service
from app.services.email_events import EmailEvent
from app.services.email_verification import legacy_verify_redirect
from app.services import referral_shortener
from app.crud.crud_login_log import crud_login_log
from app.services.device_location import extract_login_info, get_location_info
import logging

logger = logging.getLogger(__name__)

# Public answers that are the same whatever the state of the account (or its
# absence). Nothing in them, in the status code or in the headers depends on it.
REGISTRATION_ACCEPTED_MESSAGE = ("Registration received. Check your inbox for an email from MyHigh5 to confirm "
                                 "your address.")
VERIFICATION_SENT_MESSAGE = ("If this address belongs to an account that still needs to be confirmed, "
                             "a new confirmation link has been sent.")
RESET_SENT_MESSAGE = "Si cet email existe, un lien de réinitialisation a été envoyé"
INVALID_LINK_MESSAGE = "This link is invalid, has expired or has already been used."


def client_ip(request: Request) -> str:
    """The one client address used by this module: the same value the rate
    limiting middleware keys on (trusted-proxy aware, app.core.client_ip)."""
    return rate_limit._client_ip(request)


def _registration_accepted(email: str) -> RegistrationAccepted:
    return RegistrationAccepted(message=REGISTRATION_ACCEPTED_MESSAGE, detail=REGISTRATION_ACCEPTED_MESSAGE,
                                email=email)


def _minute_bucket(now: Optional[datetime] = None) -> int:
    return int((now or datetime.utcnow()).timestamp() // 60)


def _queue_verification_email(db: Session, user) -> None:
    """A NEW verification link for an existing unverified account (resend).
    Durable limits per account and platform-wide; the answer to the caller is
    the same whether or not anything is queued."""
    if not auth_throttle.hit(db, auth_throttle.VERIFY_ACCOUNT, user.id):
        logger.info("Verification email not queued for user %s: account limit reached", user.id)
        return
    if not auth_throttle.hit(db, auth_throttle.VERIFY_GLOBAL, auth_throttle.GLOBAL_KEY):
        logger.error("Verification email not queued: platform-wide ceiling reached")
        return
    email_service.enqueue(
        db,
        event=EmailEvent.AUTH_EMAIL_VERIFICATION,
        recipient=user.email,
        user_id=user.id,
        lang=getattr(user, 'preferred_language', None),
        # One per account and minute: a double submit does not send twice.
        idempotency_key=f"auth.email_verification:user:{user.id}:resend:{_minute_bucket()}",
    )


router = APIRouter()


@router.get("/health")
def auth_health():
    """Lightweight probe for load balancers / uptime checks (no DB)."""
    return {"status": "ok", "service": "auth"}


@router.post("/register", response_model=RegistrationAccepted, status_code=status.HTTP_201_CREATED)
def register_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserRegister,
    background_tasks: BackgroundTasks,
    request: Request,
    sponsor_code: Optional[str] = Query(None, description="Code de parrainage du parrain"),
    lang: Optional[str] = Query("en", description="Langue préférée (fr, en, es, de)")
) -> Any:
    """
    Créer un nouvel utilisateur.

    - **sponsor_code**: Code de parrainage optionnel pour associer l'utilisateur à un parrain
    - **lang**: Langue préférée pour les communications

    The answer does not say whether the email address already has an account:
    a new address, an address with a verified account and an address with an
    unverified account all get the same 201 body. An existing account is never
    modified, replaced or emailed by a registration attempt.
    """
    # Usernames are public (profile URLs), so "taken" reveals nothing private.
    # It is checked BEFORE the email so that its answer cannot be used to tell
    # a new address from a registered one.
    if user_in.username:
        existing_user = crud_user.get_by_username(db, username=user_in.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce nom d'utilisateur est déjà pris."
            )

    email_taken = auth_security.email_in_use(db, user_in.email)

    # Child/teen safety age gate (s.4-6): decided server-side before any write, so a
    # blocked registration leaves no user, sponsor, pool assignment or financial row.
    from app.services import age_gate
    from app.services.age_policy_engine import utc_today

    gate = age_gate.evaluate_registration(
        db,
        date_of_birth=user_in.date_of_birth,
        country=user_in.country,
        email=user_in.email,
        ip=client_ip(request),
        on=utc_today(),
    )
    attempt = age_gate.record_attempt(db, gate)
    if gate.decision == age_gate.RegistrationDecision.PARENTAL_CONSENT_REQUIRED and user_in.guardian_email:
        # Phase 4 handoff: no account. A pending registration awaits verified guardian
        # consent. The answer is identical whether or not a request already exists.
        from app.services import guardian_consent, guardian_notifications

        if user_in.guardian_email.strip().lower() == user_in.email.strip().lower():
            return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={
                "detail": "Please enter your parent or guardian's own email address.",
                "code": "GUARDIAN_EMAIL_INVALID", "message": "Please enter your parent or guardian's own email address."})
        creation = None
        if not email_taken:
            # An address that already has an account can never complete a
            # pending registration: no request is opened and no guardian is
            # emailed. The answer below is the same.
            creation = guardian_consent.create_pending_registration(
                db, email=user_in.email, username=user_in.username, date_of_birth=user_in.date_of_birth,
                country=user_in.country, region=user_in.region, continent=user_in.continent,
                sponsor_code=sponsor_code or referral_shortener.get_sponsor_referral_code_from_request(request, db),
                guardian_email=user_in.guardian_email, jurisdiction_code=gate.context.jurisdiction.code,
                policy_id=gate.context.policy.policy_id, policy_version=gate.context.policy.policy_version,
            )
        if creation is not None and creation.created:
            guardian_notifications.send_guardian_request_email(
                db, user_in.guardian_email, creation.guardian_token, user_in.username)
        message = ("We've asked your parent or guardian to review your request. "
                   "Your account will be created only after they approve.")
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={
            "detail": message, "code": "REGISTRATION_PENDING_GUARDIAN",
            "decision": age_gate.RegistrationDecision.GUARDIAN_CONSENT_PENDING.value, "message": message})
    if not gate.allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
            if gate.decision == age_gate.RegistrationDecision.RETRY_LIMITED
            else status.HTTP_403_FORBIDDEN,
            content={
                "detail": gate.client_message,
                "code": "REGISTRATION_NOT_COMPLETED",
                "decision": gate.decision.value,
                "message": gate.client_message,
            },
        )

    if email_taken:
        # Same answer as a successful registration, and roughly the same work
        # (account creation is dominated by the password hash). Nothing is
        # created, changed or sent.
        get_password_hash(user_in.password)
        logger.info("Registration attempt for an address that already has an account: nothing changed")
        return _registration_accepted(user_in.email)

    # Créer l'utilisateur avec le parrain si un code est fourni (URL param or share-link cookie)
    effective_sponsor_code = sponsor_code
    if not effective_sponsor_code:
        effective_sponsor_code = referral_shortener.get_sponsor_referral_code_from_request(request, db)

    try:
        user = crud_user.create_with_sponsor(
            db,
            obj_in=user_in,
            sponsor_code=effective_sponsor_code,
            before_commit=lambda session, new_user: age_gate.apply_registration_state(session, new_user, gate, attempt),
            # Verify-before-login: recorded on the account itself, at creation.
            require_email_verification=True,
        )
    except IntegrityError as e:
        db.rollback()
        error_str = str(e.orig).lower()
        if 'username' in error_str and 'email' not in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce nom d'utilisateur est déjà pris."
            )
        if 'email' in error_str:
            # A concurrent registration for the same address won the race.
            return _registration_accepted(user_in.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erreur lors de la création du compte. Veuillez réessayer."
        )

    # Mettre à jour la langue préférée
    if lang and hasattr(user, 'preferred_language'):
        user.preferred_language = lang
        db.commit()

    # Verification email. The one-time link is created when the email is sent;
    # only its digest is ever stored. A failure to queue it never undoes the
    # registration: the account stays unverified and can ask for a new link
    # (POST /auth/resend-verification). The welcome email follows the first
    # successful verification, not registration.
    email_service.enqueue(
        db,
        event=EmailEvent.AUTH_EMAIL_VERIFICATION,
        recipient=user.email,
        user_id=user.id,
        lang=lang,
        context={"new_account": True},
        idempotency_key=f"auth.email_verification:user:{user.id}",
    )

    referral_shortener.record_signup_conversion_from_request(request, db, user.id)

    return _registration_accepted(user_in.email)


@router.post("/register/complete", response_model=User, status_code=status.HTTP_201_CREATED)
def complete_guardian_approved_registration(*, db: Session = Depends(get_db), payload: CompleteRegistrationBody):
    """Finish a guardian-approved registration (Phase 4). The single-use token
    comes from the minor's email. The account is created exactly once through the
    normal registration transaction. The password is chosen here and was never
    stored while the request was pending."""
    from pydantic import ValidationError

    from app.services import guardian_consent
    from app.services.age_policy_engine import utc_today

    try:
        return guardian_consent.complete_registration(db, payload.token, payload.password, today=utc_today())
    except guardian_consent.GuardianFlowError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.code == "INVALID_TOKEN" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    except ValidationError as exc:
        # Password rules (the value itself is never echoed).
        messages = [e.get("msg", "Invalid value") for e in exc.errors() if "password" in (e.get("loc") or ())]
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=messages or ["Invalid registration data"]) from exc


@router.get("/verify-email")
def verify_email_get() -> RedirectResponse:
    """Retired. Verification is never performed by a GET: mail scanners and
    link previewers fetch links, and a credential in a query string ends up in
    access logs. Old links land on the page that offers a new link. Whatever
    query string is supplied is ignored and never read."""
    return legacy_verify_redirect()


@router.post("/verify-email")
def verify_email(
    *,
    request: Request,
    db: Session = Depends(get_db),
    body: EmailVerificationConfirm,
) -> Any:
    """
    Confirm an email address with the one-time credential from the email.

    The credential is sent in the request BODY (the page takes it from the URL
    fragment). It works once, for one account, for a short time. Every refusal
    (unknown, expired, used, superseded by a newer link, wrong kind of token,
    account unavailable, already verified) gets the same answer.
    """
    ip = client_ip(request)
    if not auth_throttle.hit(db, auth_throttle.CONFIRM_IP, ip):
        return rate_limit_response(ROUTE_LIMIT_MESSAGE)
    try:
        user = auth_tokens.consume(db, body.token, PURPOSE_EMAIL_VERIFICATION)
    except auth_tokens.AuthTokenError as exc:
        db.rollback()
        logger.info("Email verification refused (%s)", exc.reason)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK_MESSAGE)

    user.email_verified = True
    auth_security.audit(db, user.id, auth_security.AUDIT_EMAIL_VERIFIED, ip=ip)
    db.commit()

    # Welcome: once per account, on its first verification. The key makes a
    # second one impossible; a failure here leaves the account verified.
    email_service.enqueue(
        db,
        event=EmailEvent.AUTH_WELCOME,
        recipient=user.email,
        user_id=user.id,
        lang=getattr(user, 'preferred_language', None),
        idempotency_key=f"auth.welcome:user:{user.id}",
    )

    return {"message": "Email vérifié avec succès", "code": "EMAIL_VERIFIED"}


@router.post("/resend-verification", response_model=PasswordResetResponse)
def resend_verification(
    *,
    request: Request,
    db: Session = Depends(get_db),
    body: ResendVerificationRequest,
) -> Any:
    """
    Ask for a new email verification link.

    Always the same answer. A link is sent only to an existing, active account
    whose address is not verified yet; it replaces (invalidates) the previous
    one. Limited per client address, per account and platform-wide.
    """
    if not auth_throttle.hit(db, auth_throttle.VERIFY_IP, client_ip(request)):
        return rate_limit_response(ROUTE_LIMIT_MESSAGE)
    user = auth_security.find_account(db, body.email)
    if user is not None and user.is_active and not user.email_verified:
        _queue_verification_email(db, user)
    return PasswordResetResponse(message=VERIFICATION_SENT_MESSAGE)


def log_login_attempt(
    db: Session,
    user_id: int,
    request: Request,
    is_successful: bool = True,
    failure_reason: Optional[str] = None
):
    """Log a login attempt - fast version without geolocation"""
    try:
        # Extract basic information (synchronous and fast)
        login_info = extract_login_info(request)
        
        # Do not retrieve location to avoid timeouts
        # Geolocation is optional and can be added later if needed
        location_info = {}
        
        # Create log quickly without waiting for geolocation
        crud_login_log.create(
            db,
            obj_in={
                "user_id": user_id,
                "ip_address": login_info.get("ip_address"),
                "user_agent": login_info.get("user_agent"),
                "device_info": login_info.get("device_info"),
                "location_info": location_info,  # Empty to avoid timeouts
                "is_successful": is_successful,
                "failure_reason": failure_reason
            }
        )
    except Exception as e:
        # Do not fail the login if logging fails
        logger.error(f"Error logging login attempt: {e}")


@router.post("/login", response_model=Token)
def login_access_token(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    try:
        user = crud_user.authenticate(
            db, email_or_username=form_data.username, password=form_data.password
        )
    except Exception as e:
        # Log database or other errors
        # The login identifier (an email address or a username) is not logged.
        logger.error("Error during authentication: %s", type(e).__name__, exc_info=True)
        # Re-raise to be handled by get_db() dependency or FastAPI error handler
        raise
    
    if not user:
        # Log failed login attempt in background (non-blocking)
        if request and background_tasks:
            try:
                background_tasks.add_task(
                    log_login_attempt,
                    db=db,
                    user_id=0,  # No user for a failure
                    request=request,
                    is_successful=False,
                    failure_reason="Email/Username or password incorrect"
                )
            except Exception as log_error:
                # Don't fail login if logging fails
                logger.warning(f"Failed to log login attempt: {log_error}")
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/Username or password incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact support.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify-before-login (accounts created under EMAIL-2 only; accounts that
    # predate the rule are not affected). This is reached ONLY with a correct
    # password: a wrong password, or an unknown identifier, got the ordinary
    # 401 above, so the answer says nothing to someone who merely knows an
    # email address. No token is issued.
    if auth_security.must_verify_email(user):
        if request and background_tasks:
            try:
                background_tasks.add_task(
                    log_login_attempt,
                    db=db,
                    user_id=user.id,
                    request=request,
                    is_successful=False,
                    failure_reason="Email not verified"
                )
            except Exception as log_error:
                logger.warning(f"Failed to log login attempt: {log_error}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": auth_security.EMAIL_NOT_VERIFIED_MESSAGE,
                "code": auth_security.EMAIL_NOT_VERIFIED_CODE,
                "message": auth_security.EMAIL_NOT_VERIFIED_MESSAGE,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Log successful login in background (non-blocking)
    if request and background_tasks:
        try:
            background_tasks.add_task(
                log_login_attempt,
                db=db,
                user_id=user.id,
                request=request,
                is_successful=True
            )
        except Exception as log_error:
            # Don't fail login if logging fails
            logger.warning(f"Failed to log successful login: {log_error}")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": create_access_token(
            subject=user.id, expires_delta=access_token_expires,
            security_version=user.security_version,
        ),
        "token_type": "bearer",
    }

@router.post("/password-reset-request", response_model=PasswordResetResponse)
def request_password_reset(
    *,
    request: Request,
    db: Session = Depends(get_db),
    password_reset: PasswordResetRequest,
    background_tasks: BackgroundTasks
) -> Any:
    """
    Demander une réinitialisation de mot de passe.

    Always the same answer, whether or not the address has an account. Durable
    limits (they survive restarts): per client address, per account, and a
    platform-wide ceiling. Only the per-address limit can answer 429, and it
    does not depend on the address typed in.
    """
    if not auth_throttle.hit(db, auth_throttle.RESET_IP, client_ip(request)):
        return rate_limit_response(ROUTE_LIMIT_MESSAGE)

    user = auth_security.find_account(db, password_reset.email)
    if user is not None and user.is_active:
        if not auth_throttle.hit(db, auth_throttle.RESET_ACCOUNT, user.id):
            logger.info("Password reset email not queued for user %s: account limit reached", user.id)
        elif not auth_throttle.hit(db, auth_throttle.RESET_GLOBAL, auth_throttle.GLOBAL_KEY):
            logger.error("Password reset email not queued: platform-wide ceiling reached")
        else:
            # The one-time link is created when the email is sent; only its
            # digest is stored. One email per account, session version and
            # minute: a double submit or a client retry does not send twice.
            email_service.enqueue(
                db,
                event=EmailEvent.AUTH_PASSWORD_RESET,
                recipient=user.email,
                user_id=user.id,
                lang=getattr(user, 'preferred_language', None),
                idempotency_key=(
                    f"auth.password_reset:user:{user.id}:sv{int(user.security_version or 0)}"
                    f":{_minute_bucket()}"
                ),
            )

    return PasswordResetResponse(message=RESET_SENT_MESSAGE)


@router.post("/password-reset-confirm", response_model=PasswordResetResponse)
def confirm_password_reset(
    *,
    request: Request,
    db: Session = Depends(get_db),
    password_reset: PasswordResetConfirm,
    background_tasks: BackgroundTasks
) -> Any:
    """
    Confirmer la réinitialisation de mot de passe avec le lien reçu par email.

    The credential works once. Using it sets the password, signs the account
    out everywhere (all access tokens issued before stop working) and revokes
    any other outstanding reset link, in one transaction. Every refusal gets
    the same answer.
    """
    ip = client_ip(request)
    if not auth_throttle.hit(db, auth_throttle.CONFIRM_IP, ip):
        return rate_limit_response(ROUTE_LIMIT_MESSAGE)
    try:
        user = auth_tokens.consume(db, password_reset.token, PURPOSE_PASSWORD_RESET)
    except auth_tokens.AuthTokenError as exc:
        db.rollback()
        logger.info("Password reset refused (%s)", exc.reason)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token invalide ou expiré")

    version = auth_security.set_password(db, user, password_reset.new_password,
                                         action=auth_security.AUDIT_PASSWORD_RESET, ip=ip)
    db.commit()

    # Security notice, after the commit: a failure to queue or send it never
    # undoes the reset. One per security version.
    email_service.enqueue(
        db,
        event=EmailEvent.AUTH_PASSWORD_CHANGED,
        recipient=user.email,
        user_id=user.id,
        lang=getattr(user, 'preferred_language', None),
        context={"ip_address": ip},
        idempotency_key=f"auth.password_changed:user:{user.id}:sv{version}",
    )

    return PasswordResetResponse(
        message="Mot de passe réinitialisé avec succès"
    )

@router.get("/me", response_model=User)
def read_user_me(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Récupérer les informations de l'utilisateur connecté.
    """
    return current_user


@router.post("/validate-token")
def validate_token(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Any:
    """
    Valide un token JWT et retourne l'ID utilisateur si valide.

    A token issued before the account's last password change or reset is not
    valid here either (same rule as every authenticated endpoint).
    """
    payload = validate_access_token(token)
    user_id = auth_security.access_token_user_id(token, db) if payload else None
    if not payload or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return {
        "valid": True,
        "user_id": user_id,
        "exp": payload.get("exp")
    }


@router.post("/change-password", response_model=PasswordChangeResponse)
def change_password(
    *,
    request: Request,
    db: Session = Depends(get_db),
    password_data: PasswordChange,
    current_user = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
) -> Any:
    """
    Changer le mot de passe de l'utilisateur connecté.
    Nécessite de fournir le mot de passe actuel.

    Every access token issued before the change stops working, the one used
    for this request included. The response carries a NEW access token so the
    device that made the change stays signed in; every other device has to
    sign in again with the new password.
    """
    # Vérifier le mot de passe actuel
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect"
        )

    # Vérifier que le nouveau mot de passe est différent
    if password_data.current_password == password_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nouveau mot de passe doit être différent de l'ancien"
        )

    ip = client_ip(request)
    version = auth_security.set_password(db, current_user, password_data.new_password,
                                         action=auth_security.AUDIT_PASSWORD_CHANGED, ip=ip)
    db.commit()

    # Security notice, after the commit: a failure to queue or send it never
    # undoes the change. One per security version.
    email_service.enqueue(
        db,
        event=EmailEvent.AUTH_PASSWORD_CHANGED,
        recipient=current_user.email,
        user_id=current_user.id,
        lang=getattr(current_user, 'preferred_language', None),
        context={"ip_address": ip},
        idempotency_key=f"auth.password_changed:user:{current_user.id}:sv{version}",
    )

    return PasswordChangeResponse(
        message="Mot de passe modifié avec succès",
        access_token=create_access_token(
            subject=current_user.id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            security_version=version,
        ),
        token_type="bearer",
    )
