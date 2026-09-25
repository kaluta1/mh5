"""Verified guardian consent workflow (Child/Teen Safety s.4, s.12, s.13, s.14, s.32).

This is the one place that answers: "does this minor have valid, verified
guardian consent for scope X at time T?" (check_consent / consent_requirement).

Workflow (only when the Phase 3 gate returns PARENTAL_CONSENT_REQUIRED):
  registration -> PendingRegistration (no account, no password, token hashes only)
  -> guardian notified with a single-use link -> guardian responds (states the
     relationship, grants specific scopes, or declines)
  -> guardian authority VERIFIED only by a configured verification process (B)
  -> minor receives a single-use completion link, sets a password
  -> account created ONCE through the normal atomic registration transaction.

Two distinct concepts (never confused):
  A. CONTACT / INBOX CONTROL: the guardian used the single-use emailed link
     (GuardianRelationship.responded_at). It authenticates the workflow only.
  B. GUARDIAN AUTHORITY VERIFICATION: a configured MyHigh5 guardian
     verification process (GUARDIAN_ACCEPTED_VERIFICATION_METHODS, empty =
     none, fail closed). Currently only ADMIN_DOCUMENT_REVIEW exists: an
     authorized admin attests that evidence was reviewed outside the
     application (no document is stored). No method is claimed to be legally
     sufficient in any jurisdiction; s.13 leaves that to "applicable law and
     risk", and jurisdiction policy may later permit, strengthen or disallow it.
Consent is authorization-valid only under B (check_consent).

Never inferred: guardian from minor, sponsor, nominator, adult account, email
ownership or KYC. KYC is never read.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import FrozenSet, Iterable, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.age_safety_config import get_age_safety_config
from app.core.child_safety import (
    AgeAssuranceLevel,
    AgeReviewStatus,
    AgeSafetyEventType,
    AgeTier,
    ConsentRequirement,
    ConsentStatus,
    DobSource,
    GuardianConsentScope,
    GuardianContactConfirmation,
    GuardianRelationshipType,
    GuardianVerificationMethod,
    GuardianVerificationStatus,
    JurisdictionStatus,
    PendingRegistrationStatus,
    PolicyOperation,
    PolicyOutcome,
    RegistrationDecision,
)
from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.age_safety import AgeSafetyEvent, UserAgeProfile
from app.models.guardian import Guardian, GuardianConsent, GuardianRelationship, PendingRegistration
from app.models.user import User
from app.services.age_gate import enforcement_enabled, safety_hash
from app.services.age_policy_engine import AgeAndContestPolicyEngine, DobEvidence

_OPEN = (PendingRegistrationStatus.AWAITING_GUARDIAN.value, PendingRegistrationStatus.APPROVED.value)


class GuardianFlowError(ValueError):
    """Safe, generic failure (the code is machine-readable; no internal detail)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Tokens and configuration
# ---------------------------------------------------------------------------

def _new_token() -> Tuple[str, str]:
    """(raw token for the email link, SHA-256 hash to store). 256 bits of entropy."""
    raw = secrets.token_urlsafe(32)
    return raw, token_hash(raw)


def token_hash(raw: Optional[str]) -> Optional[str]:
    if not raw or len(raw) > 200:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def accepted_verification_methods() -> FrozenSet[GuardianVerificationMethod]:
    """Guardian AUTHORITY verification methods enabled in this deployment.
    Anything that is not a GuardianVerificationMethod is ignored. In particular
    contact/inbox confirmation (e.g. an 'EMAIL_LINK_CONFIRMATION' value) can
    never be enabled as authority verification. Empty = none (fail closed)."""
    accepted = set()
    for item in (getattr(settings, "GUARDIAN_ACCEPTED_VERIFICATION_METHODS", "") or "").split(","):
        item = item.strip().upper()
        if item:
            try:
                accepted.add(GuardianVerificationMethod(item))
            except ValueError:
                continue  # unknown or non-authority values are ignored (fail closed)
    return frozenset(accepted)


def contact_confirmed(rel: GuardianRelationship) -> bool:
    """A. Contact/inbox control only: the guardian used the single-use emailed link."""
    return rel.responded_at is not None


def authority_verified(rel: GuardianRelationship, at: Optional[datetime] = None) -> bool:
    """B. Guardian authority verified by a configured MyHigh5 guardian verification
    process (at time `at` if given). Contact confirmation alone is never enough."""
    if rel.verified_at is None or rel.verification_method not in {m.value for m in GuardianVerificationMethod}:
        return False
    if at is None:
        return rel.verification_status == GuardianVerificationStatus.VERIFIED.value
    if rel.verified_at > at or (rel.revoked_at is not None and rel.revoked_at <= at):
        return False
    # Historical question: a relationship revoked AFTER `at` was still verified at `at`.
    return rel.verification_status in (GuardianVerificationStatus.VERIFIED.value,
                                       GuardianVerificationStatus.REVOKED.value)


def _event(db: Session, event_type: AgeSafetyEventType, now: datetime, *, user_id: Optional[int] = None,
           details: Optional[dict] = None, risk: bool = False) -> None:
    db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=event_type.value, user_id=user_id,
                          risk_flag=risk, details=details))


def _audit(db: Session, table: str, record_id: int, action: str, actor_id: Optional[int], new: dict,
           old: Optional[dict] = None) -> None:
    db.add(AuditTrail(table_name=table, record_id=record_id, action=action, old_values=old, new_values=new,
                      user_id=actor_id))


def get_or_create_guardian(db: Session, email: str) -> Guardian:
    normalized = (email or "").strip().lower()
    email_hash = safety_hash("guardian_email", normalized)
    guardian = db.query(Guardian).filter(Guardian.email_hash == email_hash).first()
    if guardian is None:
        guardian = Guardian(email=normalized, email_hash=email_hash)
        db.add(guardian)
        db.flush()
    return guardian


# ---------------------------------------------------------------------------
# Pending registration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PendingCreation:
    created: bool
    guardian_token: Optional[str] = None      # raw token, only for the email link; never stored


def create_pending_registration(db: Session, *, email: str, username: Optional[str], date_of_birth: date,
                                country: Optional[str], region: Optional[str], continent: Optional[str],
                                sponsor_code: Optional[str], guardian_email: str, jurisdiction_code: Optional[str],
                                policy_id: Optional[int], policy_version: Optional[int],
                                now: Optional[datetime] = None) -> PendingCreation:
    """Create a pending registration awaiting guardian consent. No user, sponsor,
    pool assignment or financial row is created. If an open request already
    exists for this email, nothing new is created (the caller answers the same
    way, so the response does not reveal it)."""
    now = now or datetime.utcnow()
    cfg = get_age_safety_config()
    email_hash = safety_hash("email", email)
    expire_open_for_email(db, email_hash, now)
    if db.query(PendingRegistration.id).filter(PendingRegistration.email_hash == email_hash,
                                                PendingRegistration.status.in_(_OPEN)).first():
        return PendingCreation(False)

    raw, hashed = _new_token()
    pending = PendingRegistration(
        created_at=now, updated_at=now, status=PendingRegistrationStatus.AWAITING_GUARDIAN.value,
        email=email.strip().lower(), email_hash=email_hash, username=username, date_of_birth=date_of_birth,
        country=country, region=region, continent=continent, sponsor_code=sponsor_code,
        terms_accepted_at=now, jurisdiction_code=jurisdiction_code, policy_id=policy_id, policy_version=policy_version,
        expires_at=now + timedelta(hours=cfg.pending_registration_ttl_hours),
        guardian_token_hash=hashed, guardian_token_expires_at=now + timedelta(hours=cfg.guardian_token_ttl_hours),
    )
    db.add(pending)
    db.flush()
    guardian = get_or_create_guardian(db, guardian_email)
    db.add(GuardianRelationship(created_at=now, updated_at=now, guardian_id=guardian.id,
                                pending_registration_id=pending.id,
                                verification_status=GuardianVerificationStatus.PENDING.value, requested_at=now,
                                jurisdiction_code=jurisdiction_code, policy_id=policy_id, policy_version=policy_version))
    _event(db, AgeSafetyEventType.GUARDIAN_CONSENT_REQUESTED, now, details={"pending_registration_id": pending.id})
    try:
        db.commit()
    except IntegrityError:          # concurrent request for the same email
        db.rollback()
        return PendingCreation(False)
    return PendingCreation(True, raw)


def expire_open_for_email(db: Session, email_hash: str, now: datetime) -> None:
    for pending in db.query(PendingRegistration).filter(PendingRegistration.email_hash == email_hash,
                                                         PendingRegistration.status.in_(_OPEN),
                                                         PendingRegistration.expires_at <= now):
        _expire(db, pending, now)
    db.flush()


def _expire(db: Session, pending: PendingRegistration, now: datetime) -> None:
    pending.status = PendingRegistrationStatus.EXPIRED.value
    pending.updated_at = now
    for rel in db.query(GuardianRelationship).filter(GuardianRelationship.pending_registration_id == pending.id):
        if rel.verification_status in (GuardianVerificationStatus.PENDING.value,
                                       GuardianVerificationStatus.VERIFICATION_REQUIRED.value):
            rel.verification_status = GuardianVerificationStatus.EXPIRED.value
            rel.status_reason = "PENDING_REGISTRATION_EXPIRED"
    _event(db, AgeSafetyEventType.PENDING_REGISTRATION_EXPIRED, now, details={"pending_registration_id": pending.id})


def _pending_relationship(db: Session, pending: PendingRegistration) -> Optional[GuardianRelationship]:
    return (db.query(GuardianRelationship)
            .filter(GuardianRelationship.pending_registration_id == pending.id)
            .order_by(GuardianRelationship.id.desc()).first())


def _by_guardian_token(db: Session, raw: str, now: datetime, lock: bool = False) -> Optional[PendingRegistration]:
    hashed = token_hash(raw)
    if not hashed:
        return None
    q = db.query(PendingRegistration).filter(PendingRegistration.guardian_token_hash == hashed)
    pending = (q.with_for_update() if lock else q).first()
    if (pending is None or pending.status != PendingRegistrationStatus.AWAITING_GUARDIAN.value
            or pending.guardian_token_used_at is not None
            or pending.guardian_token_expires_at is None or pending.guardian_token_expires_at <= now
            or pending.expires_at <= now):
        return None
    return pending


def guardian_request_summary(db: Session, raw_token: str, now: Optional[datetime] = None) -> Optional[dict]:
    """What the guardian sees before deciding: minimal, no DOB, email or age."""
    now = now or datetime.utcnow()
    pending = _by_guardian_token(db, raw_token, now)
    if pending is None:
        return None
    return {"username": pending.username, "available_scopes": [s.value for s in GuardianConsentScope],
            "required_scope": GuardianConsentScope.ACCOUNT_PARTICIPATION.value,
            "expires_at": pending.guardian_token_expires_at.isoformat()}


@dataclass(frozen=True)
class GuardianResponse:
    status: str                                   # DECLINED | VERIFICATION_REQUIRED | APPROVED
    completion_token: Optional[str] = None        # raw, for the minor's email only
    minor_email: Optional[str] = None


def guardian_respond(db: Session, raw_token: str, *, approve: bool,
                     relationship_type: Optional[GuardianRelationshipType],
                     scopes: Iterable[GuardianConsentScope], now: Optional[datetime] = None) -> Optional[GuardianResponse]:
    """Record the guardian's decision. Single use: the token is consumed on any
    decision. Returns None for an invalid/used/expired token (callers answer
    generically)."""
    now = now or datetime.utcnow()
    scopes = list(dict.fromkeys(scopes))
    if approve:
        if relationship_type is None:
            raise GuardianFlowError("RELATIONSHIP_REQUIRED", "Please state your relationship to the applicant.")
        if GuardianConsentScope.ACCOUNT_PARTICIPATION not in scopes:
            raise GuardianFlowError("ACCOUNT_SCOPE_REQUIRED", "Account participation consent is required to approve.")
    pending = _by_guardian_token(db, raw_token, now, lock=True)
    if pending is None:
        return None
    rel = _pending_relationship(db, pending)
    pending.guardian_token_used_at = now
    pending.updated_at = now
    rel.responded_at = now
    rel.updated_at = now
    if not approve:
        rel.verification_status = GuardianVerificationStatus.REJECTED.value
        rel.status_reason = "DECLINED_BY_GUARDIAN"
        pending.status = PendingRegistrationStatus.DECLINED.value
        _event(db, AgeSafetyEventType.GUARDIAN_REJECTED, now, details={"pending_registration_id": pending.id})
        db.commit()
        return GuardianResponse("DECLINED")

    # Using the emailed link is CONTACT/INBOX confirmation only (responded_at above).
    # It never sets a verification method and never verifies authority: guardian
    # authority always needs a separate, configured verification process.
    rel.relationship_type = relationship_type.value
    for scope in scopes:
        db.add(GuardianConsent(created_at=now, updated_at=now, relationship_id=rel.id,
                               guardian_reference=rel.guardian_id, pending_registration_id=pending.id,
                               jurisdiction=pending.jurisdiction_code, consent_scope=scope.value,
                               verification_method=None,   # set once, when authority is verified
                               consent_timestamp=now,
                               policy_id=pending.policy_id, policy_version=pending.policy_version,
                               withdrawal_status=ConsentStatus.GRANTED.value))
    _event(db, AgeSafetyEventType.GUARDIAN_RESPONDED, now,
           details={"pending_registration_id": pending.id, "scopes": [s.value for s in scopes],
                    "contact_confirmation": GuardianContactConfirmation.EMAIL_LINK.value})
    rel.verification_status = GuardianVerificationStatus.VERIFICATION_REQUIRED.value
    rel.status_reason = "AUTHORITY_VERIFICATION_REQUIRED"
    db.commit()
    return GuardianResponse("VERIFICATION_REQUIRED")


def _mark_verified(db: Session, rel: GuardianRelationship, pending: Optional[PendingRegistration],
                   method: GuardianVerificationMethod, *, actor_id: Optional[int], now: datetime) -> Optional[str]:
    rel.verification_status = GuardianVerificationStatus.VERIFIED.value
    rel.verification_method = method.value
    rel.verified_at = now
    rel.verified_by_user_id = actor_id
    rel.status_reason = None
    # s.13 verification_method on each consent of this relationship (set once).
    db.query(GuardianConsent).filter(GuardianConsent.relationship_id == rel.id,
                                     GuardianConsent.verification_method.is_(None)) \
        .update({"verification_method": method.value}, synchronize_session=False)
    _event(db, AgeSafetyEventType.GUARDIAN_VERIFIED, now,
           details={"relationship_id": rel.id, "method": method.value})
    if pending is None or pending.status != PendingRegistrationStatus.AWAITING_GUARDIAN.value:
        return None
    cfg = get_age_safety_config()
    raw, hashed = _new_token()
    pending.status = PendingRegistrationStatus.APPROVED.value
    pending.completion_token_hash = hashed
    pending.completion_token_expires_at = now + timedelta(hours=cfg.completion_token_ttl_hours)
    pending.expires_at = max(pending.expires_at, pending.completion_token_expires_at)
    pending.updated_at = now
    return raw


def admin_verify_relationship(db: Session, rel: GuardianRelationship, *, method: GuardianVerificationMethod,
                              admin_id: int, note: str, now: Optional[datetime] = None) -> GuardianResponse:
    now = now or datetime.utcnow()
    if rel.verification_status != GuardianVerificationStatus.VERIFICATION_REQUIRED.value:
        raise GuardianFlowError("NOT_AWAITING_VERIFICATION", "This guardian relationship is not awaiting verification.")
    if not contact_confirmed(rel) or rel.relationship_type is None:
        raise GuardianFlowError("NOT_AWAITING_VERIFICATION", "The guardian has not responded to the request.")
    if method not in accepted_verification_methods():
        raise GuardianFlowError("METHOD_NOT_ACCEPTED", "This verification method is not accepted in this deployment.")
    pending = db.query(PendingRegistration).filter(PendingRegistration.id == rel.pending_registration_id) \
        .with_for_update().first() if rel.pending_registration_id else None
    if pending is not None and (pending.status != PendingRegistrationStatus.AWAITING_GUARDIAN.value
                                or pending.expires_at <= now):
        raise GuardianFlowError("PENDING_NOT_OPEN", "The related registration is no longer open.")
    completion = _mark_verified(db, rel, pending, method, actor_id=admin_id, now=now)
    _audit(db, "guardian_relationships", rel.id, "GUARDIAN_VERIFIED", admin_id,
           {"method": method.value, "note": note}, {"status": GuardianVerificationStatus.VERIFICATION_REQUIRED.value})
    db.commit()
    return GuardianResponse("APPROVED" if completion else "VERIFIED", completion, pending.email if pending else None)


def admin_reject_relationship(db: Session, rel: GuardianRelationship, *, admin_id: int, note: str,
                              now: Optional[datetime] = None) -> None:
    now = now or datetime.utcnow()
    if rel.verification_status not in (GuardianVerificationStatus.PENDING.value,
                                       GuardianVerificationStatus.VERIFICATION_REQUIRED.value):
        raise GuardianFlowError("NOT_AWAITING_VERIFICATION", "This guardian relationship cannot be rejected now.")
    old = rel.verification_status
    rel.verification_status = GuardianVerificationStatus.REJECTED.value
    rel.status_reason = "REJECTED_BY_REVIEW"
    if rel.pending_registration_id:
        pending = db.query(PendingRegistration).filter(PendingRegistration.id == rel.pending_registration_id).first()
        if pending is not None and pending.status in _OPEN:
            pending.status = PendingRegistrationStatus.DECLINED.value
    _event(db, AgeSafetyEventType.GUARDIAN_REJECTED, now, details={"relationship_id": rel.id})
    _audit(db, "guardian_relationships", rel.id, "GUARDIAN_REJECTED", admin_id, {"note": note}, {"status": old})
    db.commit()


# ---------------------------------------------------------------------------
# Consent query (the central question for later phases)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConsentCheck:
    valid: bool
    reason: str
    consent_id: Optional[int] = None
    relationship_id: Optional[int] = None
    policy_version: Optional[int] = None
    verification_method: Optional[str] = None


def check_consent(db: Session, *, scope: GuardianConsentScope, at: datetime, minor_user_id: Optional[int] = None,
                  pending_registration_id: Optional[int] = None) -> ConsentCheck:
    """Was there valid, VERIFIED guardian consent for exactly this scope at time `at`?
    Works for past times too (history is preserved), so a later phase can see
    that consent was valid at X but is not valid now."""
    q = db.query(GuardianConsent, GuardianRelationship).join(
        GuardianRelationship, GuardianRelationship.id == GuardianConsent.relationship_id)
    if minor_user_id is not None:
        q = q.filter(GuardianConsent.minor_user_id == minor_user_id)
    elif pending_registration_id is not None:
        q = q.filter(GuardianConsent.pending_registration_id == pending_registration_id)
    else:
        return ConsentCheck(False, "NO_SUBJECT")
    rows = q.filter(GuardianConsent.consent_scope == scope.value).order_by(GuardianConsent.id.desc()).all()
    if not rows:
        return ConsentCheck(False, "NO_CONSENT")
    reason = "NO_CONSENT"
    for consent, rel in rows:
        # The consent must belong to the same subject as the relationship it rests on.
        if ((consent.minor_user_id is not None and rel.minor_user_id != consent.minor_user_id)
                or (consent.pending_registration_id is not None
                    and rel.pending_registration_id != consent.pending_registration_id)
                or consent.guardian_reference != rel.guardian_id):
            reason = "SUBJECT_MISMATCH"
            continue
        if consent.consent_timestamp > at:
            reason = "NOT_YET_GRANTED"
            continue
        if rel.revoked_at is not None and rel.revoked_at <= at:
            reason = "GUARDIAN_AUTHORITY_REVOKED"
            continue
        if not authority_verified(rel, at):
            # Contact/inbox confirmation alone never gets past this point.
            reason = "GUARDIAN_AUTHORITY_NOT_VERIFIED"
            continue
        if consent.withdrawn_at is not None and consent.withdrawn_at <= at:
            reason = "WITHDRAWN"
            continue
        if consent.expires_at is not None and consent.expires_at <= at:
            reason = "EXPIRED"
            continue
        return ConsentCheck(True, "VALID", consent.id, rel.id, consent.policy_version, consent.verification_method)
    return ConsentCheck(False, reason)


def consent_requirement(db: Session, user: User, scope: GuardianConsentScope, *, on: date,
                        at: Optional[datetime] = None) -> Tuple[ConsentRequirement, ConsentCheck]:
    """Current requirement for this user and scope, from CURRENT age/policy state
    (dynamic across birthdays and policy versions). Adults never rely on
    guardian consent (history is kept, not deleted). Unknown age, jurisdiction
    or policy is UNDETERMINED and treated as consent required."""
    at = at or datetime.utcnow()
    check = check_consent(db, scope=scope, at=at, minor_user_id=user.id)
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()
    ctx = AgeAndContestPolicyEngine(db).context_for_user(user, on, profile)
    if ctx.legal_adult:
        return ConsentRequirement.NOT_REQUIRED_ADULT, check
    if (not ctx.age_known or ctx.jurisdiction.status != JurisdictionStatus.RESOLVED or not ctx.policy.found):
        return (ConsentRequirement.SATISFIED if check.valid else ConsentRequirement.UNDETERMINED), check
    if ctx._age >= ctx.policy.policy.parental_consent_age:
        return ConsentRequirement.NOT_REQUIRED_BY_POLICY, check
    return (ConsentRequirement.SATISFIED if check.valid else ConsentRequirement.REQUIRED_MISSING), check


# ---------------------------------------------------------------------------
# Withdrawal
# ---------------------------------------------------------------------------

def guardian_for_user(db: Session, user: User) -> Optional[Guardian]:
    """A logged-in user acts as a guardian only if their VERIFIED account email is
    the guardian contact email. An ordinary adult account is never a guardian."""
    if user is None or not getattr(user, "email_verified", False):
        return None
    return db.query(Guardian).filter(Guardian.email_hash == safety_hash("guardian_email", (user.email or "").lower())).first()


def withdraw_consent(db: Session, consent: GuardianConsent, *, actor_id: Optional[int], reason: str,
                     now: Optional[datetime] = None) -> GuardianConsent:
    """Withdraw one scope. Effective from now for future decisions; the grant
    facts (who, what, when, under which policy) are kept."""
    now = now or datetime.utcnow()
    if consent.withdrawal_status == ConsentStatus.WITHDRAWN.value:
        raise GuardianFlowError("ALREADY_WITHDRAWN", "This consent was already withdrawn.")
    consent.withdrawal_status = ConsentStatus.WITHDRAWN.value
    consent.withdrawn_at = now
    consent.withdrawn_by_user_id = actor_id
    consent.withdrawal_reason = reason
    consent.updated_at = now
    _event(db, AgeSafetyEventType.CONSENT_WITHDRAWN, now, user_id=consent.minor_user_id,
           details={"consent_id": consent.id, "scope": consent.consent_scope})
    _audit(db, "guardian_consents", consent.id, "CONSENT_WITHDRAWN", actor_id,
           {"scope": consent.consent_scope, "reason": reason}, {"withdrawal_status": ConsentStatus.GRANTED.value})
    db.commit()
    db.refresh(consent)
    return consent


def grant_additional_scope(db: Session, rel: GuardianRelationship, scope: GuardianConsentScope, *,
                           actor_id: Optional[int], now: Optional[datetime] = None) -> GuardianConsent:
    """A verified guardian grants (or re-grants after withdrawal) one scope for an
    existing minor account. A new record is added; history is never rewritten."""
    now = now or datetime.utcnow()
    if rel.verification_status != GuardianVerificationStatus.VERIFIED.value or rel.minor_user_id is None:
        raise GuardianFlowError("GUARDIAN_NOT_VERIFIED", "Guardian authority is not verified for this account.")
    consent = GuardianConsent(created_at=now, updated_at=now, relationship_id=rel.id,
                              guardian_reference=rel.guardian_id, minor_user_id=rel.minor_user_id,
                              jurisdiction=rel.jurisdiction_code, consent_scope=scope.value,
                              verification_method=rel.verification_method, consent_timestamp=now,
                              policy_id=rel.policy_id, policy_version=rel.policy_version,
                              withdrawal_status=ConsentStatus.GRANTED.value)
    db.add(consent)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise GuardianFlowError("ALREADY_GRANTED", "This consent is already granted.") from exc
    _event(db, AgeSafetyEventType.CONSENT_GRANTED, now, user_id=rel.minor_user_id,
           details={"consent_id": consent.id, "scope": scope.value})
    _audit(db, "guardian_consents", consent.id, "CONSENT_GRANTED", actor_id, {"scope": scope.value})
    db.commit()
    db.refresh(consent)
    return consent


# ---------------------------------------------------------------------------
# Registration completion (the only place a pending registration becomes a user)
# ---------------------------------------------------------------------------

def _by_completion_token(db: Session, raw: str, now: datetime) -> Optional[PendingRegistration]:
    hashed = token_hash(raw)
    if not hashed:
        return None
    pending = (db.query(PendingRegistration).filter(PendingRegistration.completion_token_hash == hashed)
               .with_for_update().first())
    if (pending is None or pending.status != PendingRegistrationStatus.APPROVED.value
            or pending.completion_token_used_at is not None
            or pending.completion_token_expires_at is None or pending.completion_token_expires_at <= now):
        return None
    return pending


def complete_registration(db: Session, raw_token: str, password: str, *, today: date,
                          now: Optional[datetime] = None) -> User:
    """Create the minor's account exactly once, through the normal atomic
    registration transaction (crud_user.create_with_sponsor). Raises
    GuardianFlowError with a generic code on any failure; nothing partial
    remains."""
    from app.crud import user as crud_user
    from app.schemas.user import UserRegister

    now = now or datetime.utcnow()
    pending = _by_completion_token(db, raw_token, now)
    if pending is None:
        raise GuardianFlowError("INVALID_TOKEN", "This link is invalid or has expired.")

    consent = check_consent(db, scope=GuardianConsentScope.ACCOUNT_PARTICIPATION, at=now,
                            pending_registration_id=pending.id)
    engine = AgeAndContestPolicyEngine(db)
    ctx = engine.build_context(dob_evidence=DobEvidence(pending.date_of_birth, AgeAssuranceLevel.SELF_DECLARED_DOB),
                               jurisdiction_value=pending.country, on=today)
    outcome = engine.evaluate(ctx, PolicyOperation.ACCOUNT_CREATION).outcome
    enforced = enforcement_enabled(db, PolicyOperation.ACCOUNT_CREATION, ctx.jurisdiction.code)
    if ctx.age_tier in (AgeTier.UNDER_13, AgeTier.UNKNOWN):
        decision = None                      # platform baseline (s.2) still applies
    elif enforced and outcome == PolicyOutcome.ALLOWED:
        decision = RegistrationDecision.ALLOWED
    elif consent.valid and (outcome == PolicyOutcome.REQUIRES_GUARDIAN_CONSENT or not enforced):
        decision = RegistrationDecision.ALLOWED_WITH_GUARDIAN_CONSENT
    else:
        decision = None
    if decision is None:
        db.rollback()
        raise GuardianFlowError("NOT_ELIGIBLE", "This registration can no longer be completed. Please contact support.")

    try:
        obj = UserRegister(email=pending.email, username=pending.username, password=password,
                           date_of_birth=pending.date_of_birth, accept_terms=True, country=pending.country,
                           region=pending.region, continent=pending.continent)
    except Exception:
        db.rollback()
        raise
    if crud_user.get_by_email(db, email=obj.email) or (obj.username and crud_user.get_by_username(db, username=obj.username)):
        db.rollback()
        raise GuardianFlowError("ACCOUNT_CONFLICT", "This registration can no longer be completed. Please contact support.")

    def before_commit(session: Session, user: User) -> None:
        session.add(UserAgeProfile(
            user_id=user.id, dob_source=DobSource.SELF_DECLARED_REGISTRATION.value,
            assurance_level=AgeAssuranceLevel.SELF_DECLARED_DOB.value,
            jurisdiction_code=ctx.jurisdiction.code, jurisdiction_status=ctx.jurisdiction.status.value,
            registration_decision=decision.value, registration_policy_outcome=outcome.value,
            registration_enforced=enforced, registration_policy_id=ctx.policy.policy_id,
            registration_policy_version=ctx.policy.policy_version, review_status=AgeReviewStatus.NONE.value,
            terms_accepted_at=pending.terms_accepted_at))
        session.query(GuardianRelationship).filter(GuardianRelationship.pending_registration_id == pending.id) \
            .update({"minor_user_id": user.id}, synchronize_session=False)
        session.query(GuardianConsent).filter(GuardianConsent.pending_registration_id == pending.id) \
            .update({"minor_user_id": user.id}, synchronize_session=False)
        pending.status = PendingRegistrationStatus.COMPLETED.value
        pending.completion_token_used_at = now
        pending.completed_user_id = user.id
        pending.completed_at = now
        pending.updated_at = now
        for event_type in (AgeSafetyEventType.DOB_CAPTURED, AgeSafetyEventType.TERMS_ACCEPTED,
                           AgeSafetyEventType.PENDING_REGISTRATION_COMPLETED):
            _event(session, event_type, now, user_id=user.id,
                   details={"pending_registration_id": pending.id, "decision": decision.value})
        session.flush()

    try:
        return crud_user.create_with_sponsor(db, obj_in=obj, sponsor_code=pending.sponsor_code,
                                             before_commit=before_commit)
    except IntegrityError as exc:
        db.rollback()
        raise GuardianFlowError("ACCOUNT_CONFLICT", "This registration can no longer be completed. Please contact support.") from exc


# ---------------------------------------------------------------------------
# Expiration / retention (foundation; not scheduled in this phase)
# ---------------------------------------------------------------------------

def expire_and_purge(db: Session, *, now: Optional[datetime] = None) -> dict:
    """Expire lapsed open requests, then remove personal data from closed pending
    registrations older than the retention period. Guardian relationships and
    consent records are NEVER deleted (they are the consent history)."""
    now = now or datetime.utcnow()
    cfg = get_age_safety_config()
    expired = 0
    for pending in db.query(PendingRegistration).filter(PendingRegistration.status.in_(_OPEN),
                                                         PendingRegistration.expires_at <= now):
        _expire(db, pending, now)
        expired += 1
    cutoff = now - timedelta(days=cfg.pending_data_retention_days)
    purged = 0
    closed = (PendingRegistrationStatus.EXPIRED.value, PendingRegistrationStatus.DECLINED.value,
              PendingRegistrationStatus.CANCELLED.value, PendingRegistrationStatus.COMPLETED.value)
    for pending in db.query(PendingRegistration).filter(PendingRegistration.status.in_(closed),
                                                         PendingRegistration.data_purged_at.is_(None),
                                                         PendingRegistration.updated_at <= cutoff):
        pending.email = None
        pending.username = None
        pending.date_of_birth = None
        pending.sponsor_code = None
        pending.country = pending.region = pending.continent = None
        pending.guardian_token_hash = None
        pending.completion_token_hash = None
        pending.data_purged_at = now
        purged += 1
    db.commit()
    return {"expired": expired, "purged": purged}


# ---------------------------------------------------------------------------
# Legacy minor accounts (identify, flag; never auto-modify)
# ---------------------------------------------------------------------------

_MINOR_TIERS = (AgeTier.UNDER_13, AgeTier.TEEN_13_15, AgeTier.TEEN_16_17)


def identify_minor_accounts(db: Session, *, on: date) -> List[dict]:
    """Read-only: accounts whose CURRENT computed tier is a minor tier. Returns
    ids and states only (no DOB, email or names). Nothing is written."""
    engine = AgeAndContestPolicyEngine(db)
    out = []
    profiles = {p.user_id: p for p in db.query(UserAgeProfile).all()}
    verified = {r.minor_user_id for r in db.query(GuardianRelationship).filter(
        GuardianRelationship.verification_status == GuardianVerificationStatus.VERIFIED.value,
        GuardianRelationship.minor_user_id.isnot(None))}
    for user in db.query(User).filter(User.date_of_birth.isnot(None)).all():
        tier = engine.resolve_age_tier(engine.calculate_age(user.date_of_birth, on))
        if tier in _MINOR_TIERS:
            p = profiles.get(user.id)
            out.append({"user_id": user.id, "age_tier": tier.value,
                        "dob_source": p.dob_source if p else DobSource.LEGACY_PROFILE.value,
                        "review_status": p.review_status if p else AgeReviewStatus.NONE.value,
                        "has_verified_guardian": user.id in verified})
    return out


def flag_for_child_safety_review(db: Session, user: User, *, admin_id: int, note: str, today: date,
                                 now: Optional[datetime] = None) -> UserAgeProfile:
    """Mark ONE account for child-safety review (s.5 AGE_REVIEW_REQUIRED). Nothing
    else changes: no guardian, consent, DOB, status or verification is created."""
    from app.services.dob_service import get_or_create_profile

    now = now or datetime.utcnow()
    engine = AgeAndContestPolicyEngine(db)
    tier = engine.resolve_age_tier(engine.calculate_age(user.date_of_birth, today)) if user.date_of_birth else AgeTier.UNKNOWN
    profile = get_or_create_profile(db, user)
    old = profile.review_status
    profile.review_status = AgeReviewStatus.AGE_REVIEW_REQUIRED.value
    profile.review_reason = "LEGACY_UNDER_MINIMUM_AGE" if tier == AgeTier.UNDER_13 else "LEGACY_MINOR_REVIEW"
    profile.review_updated_at = now
    _event(db, AgeSafetyEventType.LEGACY_REVIEW_FLAGGED, now, user_id=user.id,
           details={"age_tier": tier.value, "reason": profile.review_reason})
    db.flush()
    _audit(db, "user_age_profiles", profile.id, "CHILD_SAFETY_REVIEW_FLAGGED", admin_id,
           {"reason": profile.review_reason, "note": note}, {"review_status": old})
    db.commit()
    db.refresh(profile)
    return profile
