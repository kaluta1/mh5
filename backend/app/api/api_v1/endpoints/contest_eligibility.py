"""Phase 5 contest age eligibility endpoints (Child/Teen Safety s.9-12, s.17, s.19).

member_router (mounted at /contest-eligibility):
- a pre-check for the current member before they fill in an entry form
  (an unmet requirement never blocks the form: the entry is created ON HOLD);
- the workflow status of the member's own entry;
- the nominee claim: the nominator can re-issue the single-use claim link, and
  the nominee (signed in with their own account) can view, accept or decline.
  Tokens travel in request bodies (never in URLs/logs) and only their hashes
  are stored.
Responses carry codes and generic messages only: no DOB, age, threshold,
guardian identity or internal review detail.

admin_router (mounted at /admin/contest-eligibility, admin only):
- contest (ContestAgeEligibility) and category (CategoryAgePolicy) age rules:
  create as DRAFT, activate, withdraw (versioned, audited, never edited in place);
- the held/blocked entry queue and review actions;
- bulk re-evaluation (birthdays, policy changes).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.api.api_v1.endpoints.admin import require_admin
from app.core.child_safety import ContestEntryKind, EntryExposureStatus
from app.db.session import get_db
from app.models.category import Category
from app.models.contest import Contest
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant
from app.models.user import User
from app.schemas.contest_eligibility import (
    ContestAgeRuleCreate,
    ContestAgeRuleDefinition,
    ContestAgeRuleRead,
    ContestAgeRuleStatusChange,
    EntryReviewAction,
)
from app.services import contest_eligibility as service
from app.services.age_policy_engine import utc_today

member_router = APIRouter()
admin_router = APIRouter()


# ---------------------------------------------------------------------------
# Member
# ---------------------------------------------------------------------------

@member_router.get("/contests/{contest_id}")
def participation_precheck(
    contest_id: int,
    kind: ContestEntryKind = Query(ContestEntryKind.PERSONAL_SUBMISSION),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Would an entry by the current member be public or on hold right now? The
    member can always submit; an unmet requirement puts the entry ON HOLD and it
    is re-evaluated automatically. The backend re-checks on submit."""
    contest = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()  # noqa: E712
    if contest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    decision = service.precheck(db, current_user, contest, kind, today=utc_today(), now=datetime.utcnow())
    payload = decision.client_payload()
    payload["can_start"] = True
    payload["will_be_held"] = not decision.public or kind == ContestEntryKind.NOMINATION
    return payload


@member_router.get("/entries/{contestant_id}")
def my_entry_status(
    contestant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Workflow status of the member's own entry (codes and step only)."""
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if contestant is None or contestant.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    row = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant_id).first()
    return service.owner_view(row, db) or {"public_status": "PUBLIC", "workflow_step": None, "reason_codes": []}


# ---------------------------------------------------------------------------
# Admin: age rules
# ---------------------------------------------------------------------------

def _scope_exists(db: Session, kind: str, scope_id: int) -> bool:
    model = Contest if kind == "contest" else Category
    return db.query(model.id).filter(model.id == scope_id).first() is not None


def _rule_or_404(db: Session, kind: str, rule_id: int):
    model, _ = service.RULE_MODELS[kind]
    row = db.query(model).filter(model.id == rule_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return row


def _kind(kind: str) -> str:
    if kind not in service.RULE_MODELS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown rule kind")
    return kind


@admin_router.get("/{kind}/{scope_id}/age-rules", response_model=List[ContestAgeRuleRead])
def list_rules(kind: str, scope_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    model, col = service.RULE_MODELS[_kind(kind)]
    return (db.query(model).filter(getattr(model, col) == scope_id)
            .order_by(model.jurisdiction, model.rule_version.desc()).all())


@admin_router.post("/{kind}/{scope_id}/age-rules", response_model=ContestAgeRuleRead,
                   status_code=status.HTTP_201_CREATED)
def create_rule(kind: str, scope_id: int, body: ContestAgeRuleCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    if not _scope_exists(db, _kind(kind), scope_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    definition = ContestAgeRuleDefinition.model_validate(body.model_dump(exclude={"reason"}))
    return service.create_rule(db, kind, scope_id, definition, admin_id=admin.id, reason=body.reason)


@admin_router.post("/age-rules/{kind}/{rule_id}/activate", response_model=ContestAgeRuleRead)
def activate_rule(kind: str, rule_id: int, body: ContestAgeRuleStatusChange, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    row = _rule_or_404(db, _kind(kind), rule_id)
    try:
        return service.change_rule_status(db, kind, row, activate=True, admin_id=admin.id, reason=body.reason,
                                          today=utc_today())
    except service.EntryReviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "INVALID_RULE", "message": "The stored rule is invalid."})


@admin_router.post("/age-rules/{kind}/{rule_id}/withdraw", response_model=ContestAgeRuleRead)
def withdraw_rule(kind: str, rule_id: int, body: ContestAgeRuleStatusChange, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    row = _rule_or_404(db, _kind(kind), rule_id)
    try:
        return service.change_rule_status(db, kind, row, activate=False, admin_id=admin.id, reason=body.reason,
                                          today=utc_today())
    except service.EntryReviewError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})


# ---------------------------------------------------------------------------
# Admin: entries
# ---------------------------------------------------------------------------

def _entry_dict(row: ContestEntrySafety) -> dict:
    """Admin view: actors as ids, workflow codes. No DOB, age or guardian contact data."""
    return {
        "id": row.id, "contestant_id": row.contestant_id, "contest_id": row.contest_id, "entry_kind": row.entry_kind,
        "submitted_by_user_id": row.submitted_by_user_id, "account_holder_user_id": row.account_holder_user_id,
        "nominee_user_id": row.nominee_user_id, "creative_owner_type": row.creative_owner_type,
        "nominee_age_declaration": row.nominee_age_declaration,
        "has_verified_guardian_consent_link": row.guardian_relationship_id is not None,
        "exposure_status": row.exposure_status, "workflow_step": row.workflow_step, "outcome": row.outcome,
        "reason_codes": row.reason_codes, "missing_consent_scopes": row.missing_consent_scopes,
        "rights_status": row.rights_status, "safety_status": row.safety_status,
        "safety_concerns": row.safety_concerns, "metadata_status": row.metadata_status,
        "subject_age_tier": row.subject_age_tier, "decision_basis": row.decision_basis, "enforced": row.enforced,
        "last_evaluated_at": row.last_evaluated_at.isoformat() if row.last_evaluated_at else None,
    }


@admin_router.get("/entries")
def list_entries(
    exposure_status: Optional[EntryExposureStatus] = Query(EntryExposureStatus.HELD),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(ContestEntrySafety)
    if exposure_status is not None:
        q = q.filter(ContestEntrySafety.exposure_status == exposure_status.value)
    return [_entry_dict(r) for r in q.order_by(ContestEntrySafety.id.desc()).limit(limit).all()]


@admin_router.post("/entries/{entry_id}/review")
def review_entry(entry_id: int, body: EntryReviewAction, db: Session = Depends(get_db),
                 admin: User = Depends(require_admin)):
    row = db.query(ContestEntrySafety).filter(ContestEntrySafety.id == entry_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    try:
        row = service.admin_review(db, row, action=body.action, admin_id=admin.id, note=body.note,
                                   today=utc_today(), concern=body.concern, nominee_user_id=body.nominee_user_id)
    except service.EntryReviewError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})
    return _entry_dict(row)


@admin_router.post("/entries/reevaluate")
def reevaluate_entries(limit: int = Query(500, ge=1, le=5000), db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    return service.reevaluate_open_entries(db, trigger="ADMIN_BULK_REEVALUATE", today=utc_today(),
                                           actor_id=admin.id, limit=limit)


# ---------------------------------------------------------------------------
# Member: nominee claim
# ---------------------------------------------------------------------------

class ClaimToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=200)


class ClaimResponse(ClaimToken):
    decision: str = Field(pattern=r"^(ACCEPT|DECLINE)$")


def _claim_error(exc: service.ClaimError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if exc.code == "INVALID_OR_EXPIRED" else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})


@member_router.post("/entries/{contestant_id}/claim-link")
def reissue_claim_link(
    contestant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """The nominator gets a fresh single-use claim link (the previous one stops working)."""
    row = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant_id).first()
    if row is None or row.submitted_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    try:
        token = service.issue_claim_token(db, row, actor_id=current_user.id)
    except service.ClaimError as exc:
        raise _claim_error(exc)
    return {"nominee_claim_token": token, "expires_at": row.claim_token_expires_at.isoformat()}


@member_router.post("/claims/summary")
def claim_summary(body: ClaimToken, db: Session = Depends(get_db),
                  current_user: User = Depends(deps.get_current_active_user)):
    summary = service.claim_summary(db, body.token)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"code": "INVALID_OR_EXPIRED", "message": "This link is invalid or has expired."})
    return summary


@member_router.post("/claims/respond")
def respond_to_claim(body: ClaimResponse, db: Session = Depends(get_db),
                     current_user: User = Depends(deps.get_current_active_user)):
    """The nominee accepts (their own account becomes the nominee) or declines.
    Accepting never makes the entry public by itself and never creates any
    guardian relationship."""
    try:
        row = service.respond_to_claim(db, body.token, current_user, accept=body.decision == "ACCEPT",
                                       today=utc_today())
    except service.ClaimError as exc:
        db.rollback()
        raise _claim_error(exc)
    view = service.owner_view(row, db) or {}
    next_step = None
    if body.decision == "ACCEPT" and row.exposure_status != EntryExposureStatus.PUBLIC.value:
        codes = set(row.reason_codes or ())
        if "NOMINEE_AGE_UNDETERMINED" in codes:
            next_step = "ADD_DATE_OF_BIRTH"
        elif "GUARDIAN_CONSENT_REQUIRED" in codes:
            next_step = "GUARDIAN_CONSENT"
        else:
            next_step = "AWAIT_REVIEW"
    return {"status": "ACCEPTED" if body.decision == "ACCEPT" else "DECLINED",
            "public_status": view.get("public_status"), "next_step": next_step}
