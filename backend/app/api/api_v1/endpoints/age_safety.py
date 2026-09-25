"""Admin-only child-safety controls for Phase 3 (mounted at /admin/age-safety).

- enforcement: explicit per-operation/per-jurisdiction switch (audited);
- DOB change review queue: approve/reject pending changes (audited);
- administrator DOB correction (audited; never marks the age as verified);
- a user's derived age status (no DOB value is returned).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.api_v1.endpoints.admin import require_admin
from app.core.child_safety import PolicyOperation
from app.db.session import get_db
from app.models.age_safety import ChildSafetyEnforcement, DobChangeRecord, UserAgeProfile
from app.models.user import User
from app.schemas.user import validate_date_of_birth_value
from app.services import age_gate, dob_service
from app.services.age_policy_engine import AgeAndContestPolicyEngine, utc_today

router = APIRouter()


class EnforcementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: PolicyOperation
    jurisdiction: str = Field(min_length=1, max_length=10)
    enabled: bool
    reason: str = Field(min_length=5, max_length=500)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=5, max_length=500)


class AdminDobCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_of_birth: date
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("date_of_birth")
    @classmethod
    def _valid(cls, v: date) -> date:
        return validate_date_of_birth_value(v)


def _enforcement_dict(row: ChildSafetyEnforcement) -> dict:
    return {"id": row.id, "operation": row.operation, "jurisdiction": row.jurisdiction, "enabled": row.enabled,
            "reason": row.reason, "changed_at": row.changed_at.isoformat() if row.changed_at else None}


@router.get("/enforcement")
def list_enforcement(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(ChildSafetyEnforcement).order_by(ChildSafetyEnforcement.operation, ChildSafetyEnforcement.jurisdiction)
    return [_enforcement_dict(r) for r in rows]


@router.put("/enforcement")
def update_enforcement(body: EnforcementUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        row = age_gate.set_enforcement(db, operation=body.operation, jurisdiction=body.jurisdiction,
                                       enabled=body.enabled, reason=body.reason, actor_id=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _enforcement_dict(row)


@router.get("/dob-changes")
def list_dob_changes(status_filter: Optional[str] = Query("PENDING", alias="status", max_length=20),
                     db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = db.query(DobChangeRecord)
    if status_filter:
        q = q.filter(DobChangeRecord.status == status_filter.upper())
    return [
        {"id": r.id, "user_id": r.user_id, "status": r.status, "reason_code": r.reason_code,
         "previous_dob": r.previous_dob.isoformat() if r.previous_dob else None,
         "requested_dob": r.requested_dob.isoformat(), "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in q.order_by(DobChangeRecord.id.desc()).limit(200)
    ]


def _review(change_id: int, approve: bool, body: ReviewDecision, db: Session, admin: User):
    record = db.query(DobChangeRecord).filter(DobChangeRecord.id == change_id).with_for_update().first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    try:
        record = dob_service.review_change(db, record, approve=approve, note=body.note, admin_id=admin.id,
                                           today=utc_today())
    except dob_service.DobChangeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"id": record.id, "status": record.status}


@router.post("/dob-changes/{change_id}/approve")
def approve_dob_change(change_id: int, body: ReviewDecision, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    return _review(change_id, True, body, db, admin)


@router.post("/dob-changes/{change_id}/reject")
def reject_dob_change(change_id: int, body: ReviewDecision, db: Session = Depends(get_db),
                      admin: User = Depends(require_admin)):
    return _review(change_id, False, body, db, admin)


@router.put("/users/{user_id}/date-of-birth")
def admin_correct_date_of_birth(user_id: int, body: AdminDobCorrection, db: Session = Depends(get_db),
                                admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        profile = dob_service.admin_correct_dob(db, user, body.date_of_birth, reason=body.reason,
                                                admin_id=admin.id, today=utc_today())
    except dob_service.DobChangeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"user_id": user_id, "dob_source": profile.dob_source, "review_status": profile.review_status}


@router.get("/users/{user_id}/age-status")
def user_age_status(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user_id).first()
    context = AgeAndContestPolicyEngine(db).context_for_user(user, utc_today(), profile)
    return {
        "user_id": user_id,
        "age_tier": context.age_tier.value,
        "dob_source": profile.dob_source if profile else ("LEGACY_PROFILE" if user.date_of_birth else None),
        "assurance_level": context.assurance_level.value if context.assurance_level else None,
        "jurisdiction_status": context.jurisdiction.status.value,
        "jurisdiction": context.jurisdiction.code,
        "policy_status": context.policy.status,
        "review_status": profile.review_status if profile else "NONE",
        "registration_decision": profile.registration_decision if profile else None,
    }


# ---------------------------------------------------------------------------
# Phase 4: guardian verification review, consent withdrawal, legacy minor review
# ---------------------------------------------------------------------------

from fastapi import BackgroundTasks  # noqa: E402

from app.core.child_safety import GuardianConsentScope, GuardianVerificationMethod  # noqa: E402
from app.models.guardian import GuardianConsent, GuardianRelationship  # noqa: E402
from app.services import guardian_consent, guardian_notifications  # noqa: E402


class GuardianVerifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: GuardianVerificationMethod
    note: str = Field(min_length=5, max_length=500)


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=5, max_length=500)


@router.get("/guardian-relationships")
def list_guardian_relationships(status_filter: Optional[str] = Query("VERIFICATION_REQUIRED", alias="status", max_length=30),
                                db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Review queue. The guardian email and the minor's DOB are not returned."""
    q = db.query(GuardianRelationship)
    if status_filter:
        q = q.filter(GuardianRelationship.verification_status == status_filter.upper())
    return [{"id": r.id, "guardian_id": r.guardian_id, "minor_user_id": r.minor_user_id,
             "pending_registration_id": r.pending_registration_id, "relationship_type": r.relationship_type,
             "verification_status": r.verification_status, "verification_method": r.verification_method,
             "requested_at": r.requested_at.isoformat() if r.requested_at else None,
             "responded_at": r.responded_at.isoformat() if r.responded_at else None}
            for r in q.order_by(GuardianRelationship.id.desc()).limit(200)]


def _relationship(db: Session, relationship_id: int) -> GuardianRelationship:
    rel = db.query(GuardianRelationship).filter(GuardianRelationship.id == relationship_id).with_for_update().first()
    if rel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardian relationship not found")
    return rel


@router.post("/guardian-relationships/{relationship_id}/verify")
def verify_guardian_relationship(relationship_id: int, body: GuardianVerifyBody, background_tasks: BackgroundTasks,
                                 db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        result = guardian_consent.admin_verify_relationship(db, _relationship(db, relationship_id), method=body.method,
                                                            admin_id=admin.id, note=body.note)
    except guardian_consent.GuardianFlowError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result.completion_token and result.minor_email:
        background_tasks.add_task(guardian_notifications.send_completion_email, result.minor_email,
                                  result.completion_token)
    return {"id": relationship_id, "status": result.status}


@router.post("/guardian-relationships/{relationship_id}/reject")
def reject_guardian_relationship(relationship_id: int, body: NoteBody, db: Session = Depends(get_db),
                                 admin: User = Depends(require_admin)):
    try:
        guardian_consent.admin_reject_relationship(db, _relationship(db, relationship_id), admin_id=admin.id,
                                                   note=body.note)
    except guardian_consent.GuardianFlowError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"id": relationship_id, "status": "REJECTED"}


@router.post("/guardian-consents/{consent_id}/withdraw")
def admin_withdraw_consent(consent_id: int, body: NoteBody, db: Session = Depends(get_db),
                           admin: User = Depends(require_admin)):
    """Withdrawal on a guardian's verified request (e.g. through support)."""
    consent = db.query(GuardianConsent).filter(GuardianConsent.id == consent_id).with_for_update().first()
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found")
    try:
        consent = guardian_consent.withdraw_consent(db, consent, actor_id=admin.id, reason=body.note)
    except guardian_consent.GuardianFlowError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"consent_id": consent.id, "status": consent.withdrawal_status}


@router.get("/minor-accounts")
def list_minor_accounts(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Read-only identification of accounts whose CURRENT computed tier is a minor
    tier (ids and states only; nothing is modified)."""
    return guardian_consent.identify_minor_accounts(db, on=utc_today())


@router.post("/users/{user_id}/child-safety-review")
def flag_child_safety_review(user_id: int, body: NoteBody, db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    profile = guardian_consent.flag_for_child_safety_review(db, user, admin_id=admin.id, note=body.note,
                                                            today=utc_today())
    return {"user_id": user_id, "review_status": profile.review_status, "review_reason": profile.review_reason}


@router.get("/users/{user_id}/guardian-status")
def user_guardian_status(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    today = utc_today()
    out = {}
    for scope in GuardianConsentScope:
        requirement, check = guardian_consent.consent_requirement(db, user, scope, on=today)
        out[scope.value] = {"requirement": requirement.value, "consent_valid": check.valid, "reason": check.reason}
    return {"user_id": user_id, "scopes": out}


@router.post("/pending-registrations/expire-and-purge")
def expire_and_purge_pending(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return guardian_consent.expire_and_purge(db)
