"""Guardian consent endpoints (Child/Teen Safety s.12-14).

Public, token-based (the guardian needs no MyHigh5 account):
  POST /guardian/requests/lookup   minimal request summary
  POST /guardian/requests/respond  approve specific scopes, or decline
  POST /auth/register/complete     (see auth router) the minor sets a password

Authenticated guardian (a user whose VERIFIED account email is the guardian
contact email; an ordinary adult account is never a guardian):
  GET  /guardian/me/consents
  POST /guardian/me/consents/{id}/withdraw

Invalid, used and expired tokens all return the same generic 404.
Tokens are sent in request bodies, never in URLs.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.child_safety import ConsentStatus, GuardianConsentScope, GuardianRelationshipType
from app.db.session import get_db
from app.models.guardian import GuardianConsent, GuardianRelationship
from app.models.user import User
from app.services import guardian_consent

router = APIRouter()

_INVALID = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link is invalid or has expired.")


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10, max_length=200)


class GuardianDecision(TokenBody):
    decision: Literal["APPROVE", "DECLINE"]
    relationship_type: Optional[GuardianRelationshipType] = None
    scopes: List[GuardianConsentScope] = Field(default_factory=list, max_length=len(GuardianConsentScope))


class WithdrawBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


@router.post("/requests/lookup")
def lookup_request(body: TokenBody, db: Session = Depends(get_db)):
    summary = guardian_consent.guardian_request_summary(db, body.token)
    if summary is None:
        raise _INVALID
    return summary


@router.post("/requests/respond")
def respond_to_request(body: GuardianDecision, db: Session = Depends(get_db)):
    """Record the guardian's decision. Using the emailed link confirms control of
    the contact address only: guardian authority must still be verified by the
    configured MyHigh5 guardian verification process before any account exists."""
    try:
        result = guardian_consent.guardian_respond(
            db, body.token, approve=body.decision == "APPROVE", relationship_type=body.relationship_type,
            scopes=body.scopes)
    except guardian_consent.GuardianFlowError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": exc.code, "message": str(exc)}) from exc
    if result is None:
        raise _INVALID
    messages = {
        "DECLINED": "Thank you. The request has been declined and no account will be created.",
        "VERIFICATION_REQUIRED": "Thank you. Your response was recorded. Before the account can be created, "
                                 "MyHigh5 must verify your authority as parent or guardian through its "
                                 "guardian verification process.",
    }
    return {"status": result.status, "message": messages[result.status]}


def _as_guardian(db: Session, user: User):
    guardian = guardian_consent.guardian_for_user(db, user)
    if guardian is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized as a guardian.")
    return guardian


@router.get("/me/consents")
def my_consents(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    guardian = _as_guardian(db, user)
    rows = (db.query(GuardianConsent, GuardianRelationship)
            .join(GuardianRelationship, GuardianRelationship.id == GuardianConsent.relationship_id)
            .filter(GuardianConsent.guardian_reference == guardian.id,
                    GuardianRelationship.verification_status == "VERIFIED",
                    GuardianConsent.minor_user_id.isnot(None))
            .order_by(GuardianConsent.id).all())
    usernames = {u.id: u.username for u in db.query(User).filter(User.id.in_({c.minor_user_id for c, _ in rows}))} if rows else {}
    return [{"consent_id": c.id, "minor_username": usernames.get(c.minor_user_id), "scope": c.consent_scope,
             "status": c.withdrawal_status, "granted_at": c.consent_timestamp.isoformat(),
             "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None} for c, _ in rows]


@router.post("/me/consents/{consent_id}/withdraw")
def withdraw_my_consent(consent_id: int, body: WithdrawBody, db: Session = Depends(get_db),
                        user: User = Depends(get_current_active_user)):
    guardian = _as_guardian(db, user)
    consent = db.query(GuardianConsent).filter(GuardianConsent.id == consent_id,
                                               GuardianConsent.guardian_reference == guardian.id).with_for_update().first()
    if consent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found.")
    try:
        consent = guardian_consent.withdraw_consent(db, consent, actor_id=user.id, reason=body.reason)
    except guardian_consent.GuardianFlowError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"consent_id": consent.id, "status": consent.withdrawal_status,
            "withdrawn_at": consent.withdrawn_at.isoformat()}


# Registration completion lives on the auth router (see auth.py) but uses this schema.
class CompleteRegistrationBody(TokenBody):
    password: str = Field(min_length=1, max_length=200)


__all__ = ["router", "CompleteRegistrationBody", "ConsentStatus"]
