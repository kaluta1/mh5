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


# ---------------------------------------------------------------------------
# Phase 8: progression safety holds (staff review; codes only)
# ---------------------------------------------------------------------------

@router.get("/progression-holds")
def progression_holds(status_filter: Optional[str] = Query(None, alias="status", pattern=r"^(HELD|RELEASED|REVIEW_REQUIRED)$"),
                      limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                      _: User = Depends(require_content_moderator)):
    """VISIBLE_TO_STAFF only: listing a hold never makes the entry eligible for
    public voting, ranking or progression."""
    from app.models.progression_safety import ProgressionSafetyHold
    from app.services import participation_safety as ps

    q = db.query(ProgressionSafetyHold)
    q = q.filter(ProgressionSafetyHold.status == status_filter) if status_filter else \
        q.filter(ProgressionSafetyHold.status.in_(["HELD", "REVIEW_REQUIRED"]))
    return [ps.staff_hold_view(h) for h in q.order_by(ProgressionSafetyHold.id.asc()).limit(limit).all()]


@router.post("/progression-holds/{hold_id}/recheck")
def recheck_progression_hold(hold_id: int, db: Session = Depends(get_db),
                             user: User = Depends(require_content_moderator)):
    """Re-run the centralized gate for one hold. This is NOT an override: the
    hold is released only if the entry is eligible now (resolved through the
    normal Phase 5/6 paths) and the destination stage is still running."""
    from app.models.progression_safety import ProgressionSafetyHold
    from app.services import participation_safety as ps

    hold = db.query(ProgressionSafetyHold).filter(ProgressionSafetyHold.id == hold_id).first()
    if hold is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    ps.release_holds(db, contestant_ids=[hold.contestant_id], actor_id=user.id)
    db.commit()
    db.refresh(hold)
    return ps.staff_hold_view(hold)


# ---------------------------------------------------------------------------
# Phase 9: interaction reports (comments, private messages, accounts)
#
# Staff access only through this report workflow: an ordinary moderator sees
# ordinary reports; a CHILD_SAFETY report is visible ONLY to an explicit
# child_safety_resolve holder (never implied by admin/moderator). A private
# message is readable only as the evidence of a report about THAT message
# (no inbox access), and every evidence read is audited.
# ---------------------------------------------------------------------------

def _interaction_report_query(db: Session, user: User):
    from sqlalchemy import or_

    from app.models.comment import Report

    q = db.query(Report).filter(Report.contestant_id.is_(None), or_(
        Report.comment_id.isnot(None), Report.private_message_id.isnot(None), Report.user_id.isnot(None)))
    if not cs.can_resolve_child_safety(user):
        q = q.filter(Report.reason != "CHILD_SAFETY")
    if not cs.can_moderate(user):
        q = q.filter(Report.reason == "CHILD_SAFETY")
    return q


def _report_item(r) -> dict:
    target = "message" if r.private_message_id else "comment" if r.comment_id else "user"
    return {"id": r.id, "target_type": target, "comment_id": r.comment_id,
            "private_message_id": r.private_message_id, "reported_user_id": r.user_id, "reason": r.reason,
            "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None}


@router.get("/interaction-reports")
def interaction_reports(status_filter: Optional[str] = Query(None, alias="status", pattern=r"^(pending|reviewed|resolved)$"),
                        limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                        user: User = Depends(require_content_moderator)):
    from app.models.comment import Report

    q = _interaction_report_query(db, user)
    if status_filter:
        q = q.filter(Report.status == status_filter)
    return [_report_item(r) for r in q.order_by(Report.id.asc()).limit(limit).all()]


def _message_text(db: Session, message, reporter_id: int) -> Optional[str]:
    """Decrypt ONE reported message with the reporting participant's key."""
    from app.models.user_encryption_keys import UserEncryptionKeys
    from app.services.feed_encryption import get_encryption_service

    def keys(uid):
        return db.query(UserEncryptionKeys).filter(UserEncryptionKeys.user_id == uid,
                                                   UserEncryptionKeys.is_active == True).first()  # noqa: E712
    try:
        sender, reader = keys(message.sender_id), keys(reporter_id)
        payload = (message.sender_encrypted_content if message.sender_id == reporter_id
                   and getattr(message, "sender_encrypted_content", None) else message.content)
        if sender is None or reader is None:
            return None
        return get_encryption_service().decrypt_message(encrypted_message=payload, sender_public_key=sender.public_key,
                                                        recipient_private_key=reader.encrypted_private_key,
                                                        is_private_key_encrypted=True)
    except Exception:  # noqa: BLE001 - legacy/undecryptable content is not shown
        return None


@router.get("/interaction-reports/{report_id}")
def interaction_report_evidence(report_id: int, db: Session = Depends(get_db),
                                user: User = Depends(require_content_moderator)):
    from app.models.comment import Comment, Report
    from app.models.private_message import PrivateMessage

    row = _interaction_report_query(db, user).filter(Report.id == report_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    evidence = None
    if row.comment_id:
        comment = db.query(Comment).filter(Comment.id == row.comment_id).first()
        evidence = comment.content if comment else None
    elif row.private_message_id:
        message = db.query(PrivateMessage).filter(PrivateMessage.id == row.private_message_id).first()
        evidence = _message_text(db, message, row.reporter_id) if message else None
    db.add(AuditTrail(table_name="report", record_id=row.id, action="EVIDENCE_ACCESSED", old_values=None,
                      new_values={"target": _report_item(row)["target_type"], "reason": row.reason}, user_id=user.id))
    db.commit()
    return {**_report_item(row), "evidence": evidence, "description": row.description}


class InteractionReportReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(reviewed|resolved)$")
    note_code: str = Field(min_length=3, max_length=80, pattern=r"^[A-Z0-9_]+$")


@router.post("/interaction-reports/{report_id}/review")
def review_interaction_report(report_id: int, body: InteractionReportReviewBody, db: Session = Depends(get_db),
                              user: User = Depends(require_content_moderator)):
    from app.models.comment import Report

    row = _interaction_report_query(db, user).filter(Report.id == report_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    old = row.status
    row.status, row.reviewed_by, row.reviewed_at = body.status, user.id, datetime.utcnow()
    row.moderator_notes = body.note_code
    db.add(AuditTrail(table_name="report", record_id=row.id, action=f"REPORT_{body.status.upper()}",
                      old_values={"status": old}, new_values={"status": body.status, "note_code": body.note_code},
                      user_id=user.id))
    db.commit()
    return _report_item(row)
