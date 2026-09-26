"""Phase 6 content moderation API (mounted at /admin/content-moderation).

Access: administrators or a role holding `moderate_content`. The dedicated
child-safety resolution additionally requires the explicit
`child_safety_resolve` permission (never implied by admin or the 'all'
wildcard). Responses carry codes and identifiers only: no content text, no
matched PII, no evidence, no tokens.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.core.child_safety import ChildSafetyResolution, ContentRating, ModerationState, SafetyConcern
from app.db.session import get_db
from app.models.accounting import AuditTrail
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.user import User
from app.services import content_safety as cs

router = APIRouter()


def require_content_moderator(current_user: User = Depends(deps.get_current_active_user)) -> User:
    """Queue access: ordinary moderators, or designated child-safety resolvers.
    Each action is authorized again in the service (moderate vs resolve)."""
    if not (cs.can_moderate(current_user) or cs.can_resolve_child_safety(current_user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed.")
    return current_user


class ModerationActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(APPROVE|HOLD|REQUEST_UPDATE|CLASSIFY|PROHIBIT|ESCALATE_CHILD_SAFETY|RESOLVE_ISSUE)$")
    reason: str = Field(min_length=3, max_length=80, pattern=r"^[A-Z0-9_]+$")  # structured reason code, not free text
    rating: Optional[ContentRating] = None
    finding_codes: List[SafetyConcern] = Field(default_factory=list, max_length=20)


class ChildSafetyResolutionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: ChildSafetyResolution
    reason: str = Field(min_length=3, max_length=80, pattern=r"^[A-Z0-9_]+$")


def _item(db: Session, row: ContentModeration) -> dict:
    entry = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == row.contestant_id).first()
    return {
        "id": row.id, "contestant_id": row.contestant_id,
        "contest_id": entry.contest_id if entry else None,
        "entry_kind": entry.entry_kind if entry else None,
        "submitted_by_user_id": entry.submitted_by_user_id if entry else None,
        "nominee_user_id": entry.nominee_user_id if entry else None,
        "exposure_status": entry.exposure_status if entry else None,
        "state": row.state, "rating": row.rating, "proposed_rating": row.proposed_rating,
        "findings": row.findings or [], "resolved_findings": row.resolved_findings or [],
        "classifier_status": row.classifier_status, "classifier_version": row.classifier_version,
        "coverage": row.coverage or {},
        "human_review_required": row.human_review_required, "update_required": row.update_required,
        "subject_possibly_minor": row.subject_possibly_minor,
        "child_safety_escalated": row.child_safety_escalated,
        "child_safety_resolution": row.child_safety_resolution,
        "automated_decision": row.automated_decision,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def _row_or_404(db: Session, item_id: int) -> ContentModeration:
    row = db.query(ContentModeration).filter(ContentModeration.id == item_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return row


@router.get("/queue")
def queue(state: Optional[ModerationState] = Query(None), child_safety: Optional[bool] = Query(None),
          limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
          _: User = Depends(require_content_moderator)):
    q = db.query(ContentModeration)
    if state is not None:
        q = q.filter(ContentModeration.state == state.value)
    else:
        q = q.filter(ContentModeration.state.in_([ModerationState.PENDING.value, ModerationState.REVIEW_REQUIRED.value,
                                                  ModerationState.CHILD_SAFETY_ESCALATED.value]))
    if child_safety is not None:
        q = q.filter(ContentModeration.child_safety_escalated.is_(child_safety))
    rows = q.order_by(ContentModeration.child_safety_escalated.desc(), ContentModeration.id.asc()).limit(limit).all()
    return [_item(db, r) for r in rows]


@router.get("/items/{item_id}")
def item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_content_moderator)):
    row = _row_or_404(db, item_id)
    history = (db.query(AuditTrail).filter(AuditTrail.table_name == "content_moderation",
                                           AuditTrail.record_id == row.id).order_by(AuditTrail.id.asc()).all())
    return {**_item(db, row),
            "can_moderate": cs.can_moderate(user),
            "can_resolve_child_safety": cs.can_resolve_child_safety(user),
            "history": [{"action": h.action, "actor_user_id": h.user_id,
                         "at": h.created_at.isoformat() if h.created_at else None,
                         "state": (h.new_values or {}).get("state"), "rating": (h.new_values or {}).get("rating"),
                         "reason_code": (h.new_values or {}).get("reason_code")} for h in history]}


@router.post("/items/{item_id}/actions")
def act(item_id: int, body: ModerationActionBody, db: Session = Depends(get_db),
        user: User = Depends(require_content_moderator)):
    row = _row_or_404(db, item_id)
    try:
        row = cs.moderate(db, row, action=body.action, actor=user, reason=body.reason, rating=body.rating,
                          finding_codes=body.finding_codes, now=datetime.utcnow())
    except cs.ModerationError as exc:
        db.rollback()
        code = status.HTTP_403_FORBIDDEN if exc.code == "FORBIDDEN" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})
    return _item(db, row)


@router.post("/items/{item_id}/child-safety-resolution")
def resolve(item_id: int, body: ChildSafetyResolutionBody, db: Session = Depends(get_db),
            user: User = Depends(require_content_moderator)):
    row = _row_or_404(db, item_id)
    try:
        row = cs.resolve_child_safety(db, row, resolution=body.resolution, actor=user, reason=body.reason,
                                      now=datetime.utcnow())
    except cs.ModerationError as exc:
        db.rollback()
        code = status.HTTP_403_FORBIDDEN if exc.code == "FORBIDDEN" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})
    return _item(db, row)
