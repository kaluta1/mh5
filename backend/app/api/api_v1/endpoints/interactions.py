"""Phase 9 member interaction controls: blocks, reports, and the contact check
the UI uses to decide whether to offer "Message". Every decision is made by
app.services.interaction_safety; responses never reveal another member's age,
settings, or who blocked whom.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.core.child_safety import AgeSafetyEventType
from app.models.comment import Comment, Report
from app.models.interaction_safety import UserBlock
from app.models.private_message import PrivateConversation, PrivateMessage
from app.models.user import User
from app.services import interaction_safety as isafe

router = APIRouter()
ads_router = APIRouter()

REPORT_REASONS = ("SPAM", "HARASSMENT", "INAPPROPRIATE_CONTENT", "PERSONAL_INFORMATION", "CHILD_SAFETY", "OTHER")


def _active_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712


# ---------------------------------------------------------------------------
# Blocks (user-controlled, idempotent, visible only to the blocker)
# ---------------------------------------------------------------------------

@router.post("/blocks/{user_id}", status_code=status.HTTP_200_OK)
def block_user(user_id: int, db: Session = Depends(deps.get_db),
               current_user: User = Depends(deps.get_current_active_user)):
    if user_id == current_user.id or _active_user(db, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = db.query(UserBlock).filter(UserBlock.blocker_id == current_user.id,
                                          UserBlock.blocked_id == user_id).first()
    if existing is None:
        db.add(UserBlock(blocker_id=current_user.id, blocked_id=user_id))
        isafe.record_event(db, AgeSafetyEventType.USER_BLOCKED, actor_id=current_user.id,
                           details={"target_user_id": user_id}, decision="BLOCKED", commit=False)
        db.commit()
    return {"blocked": True, "user_id": user_id}


@router.delete("/blocks/{user_id}", status_code=status.HTTP_200_OK)
def unblock_user(user_id: int, db: Session = Depends(deps.get_db),
                 current_user: User = Depends(deps.get_current_active_user)):
    row = db.query(UserBlock).filter(UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == user_id).first()
    if row is not None:   # only the blocker can lift their own block
        db.delete(row)
        isafe.record_event(db, AgeSafetyEventType.USER_UNBLOCKED, actor_id=current_user.id,
                           details={"target_user_id": user_id}, decision="UNBLOCKED", commit=False)
        db.commit()
    return {"blocked": False, "user_id": user_id}


@router.get("/blocks")
def my_blocks(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_active_user)):
    """Only the members THIS user blocked (never who blocked them)."""
    rows = db.query(UserBlock.blocked_id).filter(UserBlock.blocker_id == current_user.id).all()
    users = {u.id: u for u in db.query(User).filter(User.id.in_([r[0] for r in rows] or [-1])).all()}
    return [{"user_id": uid, "username": getattr(users.get(uid), "username", None)} for (uid,) in rows]


@router.get("/contact/{user_id}")
def contact_status(user_id: int, db: Session = Depends(deps.get_db),
                   current_user: User = Depends(deps.get_current_active_user)):
    """Whether the UI should offer direct messaging with this member. A boolean
    only - the backend still decides on every write."""
    target = _active_user(db, user_id)
    decision = isafe.can_contact(db, current_user, target)
    blocked_by_me = db.query(UserBlock.id).filter(UserBlock.blocker_id == current_user.id,
                                                  UserBlock.blocked_id == user_id).first() is not None
    return {"user_id": user_id, "can_message": decision.allowed, "blocked_by_me": blocked_by_me}


# ---------------------------------------------------------------------------
# Reports (auditable, de-duplicated, never public, reporter never disclosed)
# ---------------------------------------------------------------------------

class InteractionReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: str = Field(pattern=r"^(comment|message|user)$")
    target_id: int = Field(gt=0)
    reason: str = Field(pattern=r"^(SPAM|HARASSMENT|INAPPROPRIATE_CONTENT|PERSONAL_INFORMATION|CHILD_SAFETY|OTHER)$")
    description: Optional[str] = Field(default=None, max_length=500)


def _not_found():
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.post("/reports", status_code=status.HTTP_201_CREATED)
def report_interaction(body: InteractionReportBody, response: Response, db: Session = Depends(deps.get_db),
                       current_user: User = Depends(deps.get_current_active_user)):
    fields = {}
    if body.target_type == "comment":
        comment = db.query(Comment).filter(Comment.id == body.target_id, Comment.is_deleted == False).first()  # noqa: E712
        if comment is None:
            raise _not_found()
        if comment.contestant_id is not None:  # only a comment the reporter may see (Phase 7 decision)
            from app.models.contests import Contestant
            from app.services.viewer_access import require_entry_access

            require_entry_access(db, current_user, db.query(Contestant).filter(
                Contestant.id == comment.contestant_id).first())
        # No contestant_id: interaction reports stay out of the legacy contestant-report list.
        fields = {"comment_id": comment.id, "user_id": comment.user_id}
    elif body.target_type == "message":
        message = db.query(PrivateMessage).filter(PrivateMessage.id == body.target_id).first()
        conversation = (db.query(PrivateConversation).filter(PrivateConversation.id == message.conversation_id).first()
                        if message is not None else None)
        if conversation is None or current_user.id not in (conversation.user1_id, conversation.user2_id):
            raise _not_found()  # only a participant can report a private message
        fields = {"private_message_id": message.id, "user_id": message.sender_id}
    else:
        if body.target_id == current_user.id or _active_user(db, body.target_id) is None:
            raise _not_found()
        fields = {"user_id": body.target_id}
    if fields.get("user_id") == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't report yourself.")

    key = {k: v for k, v in fields.items() if k in ("comment_id", "private_message_id")} or {"user_id": fields["user_id"]}
    q = db.query(Report).filter(Report.reporter_id == current_user.id, Report.status == "pending")
    for column, value in key.items():
        q = q.filter(getattr(Report, column) == value)
    if body.target_type == "user":
        q = q.filter(Report.comment_id.is_(None), Report.private_message_id.is_(None), Report.contestant_id.is_(None))
    existing = q.first()
    if existing is not None:   # idempotent: a pending report is not duplicated
        response.status_code = status.HTTP_200_OK
        return {"id": existing.id, "status": "pending", "duplicate": True}
    row = Report(reporter_id=current_user.id, reason=body.reason, description=body.description, status="pending",
                 **fields)
    db.add(row)
    db.flush()
    isafe.record_event(db, AgeSafetyEventType.INTERACTION_REPORTED, actor_id=current_user.id,
                       details={"report_id": row.id, "target_type": body.target_type, "reason": body.reason},
                       decision="REPORTED", risk=body.reason == "CHILD_SAFETY", commit=False)
    db.commit()
    # The reported member is never notified with reporter information.
    return {"id": row.id, "status": "pending", "duplicate": False}


# ---------------------------------------------------------------------------
# Advertising eligibility (per viewer; see interaction_safety for the rules)
# ---------------------------------------------------------------------------

@ads_router.get("/eligibility")
def ad_eligibility(response: Response, db: Session = Depends(deps.get_db),
                   current_user: Optional[User] = Depends(deps.get_current_active_user_optional)):
    response.headers["Cache-Control"] = "private, no-store"
    return {"sources": isafe.ad_eligibility(db, current_user)}
