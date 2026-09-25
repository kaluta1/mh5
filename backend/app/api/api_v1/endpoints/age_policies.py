"""Admin-only AgePolicy management (Child/Teen Safety requirement, section 3).

Mounted under /admin/age-policies with the admin router dependency. There is no
public or member endpoint. The engine is not wired into any member-facing flow
in Phase 2.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.api_v1.endpoints.admin import require_admin
from app.db.session import get_db
from app.models.age_policy import AgePolicy
from app.models.user import User
from app.schemas.age_policy import AgePolicyDefinition, AgePolicyRead, AgePolicyStatusChange
from app.services import age_policy_admin
from app.services.age_policy_engine import AgeAndContestPolicyEngine, utc_today

router = APIRouter()


def _get(db: Session, policy_id: int) -> AgePolicy:
    policy = db.query(AgePolicy).filter(AgePolicy.id == policy_id).first()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Age policy not found")
    return policy


def _conflict(exc: age_policy_admin.AgePolicyAdminError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("", response_model=List[AgePolicyRead])
def list_age_policies(
    jurisdiction: Optional[str] = Query(None, max_length=10),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(AgePolicy)
    if jurisdiction:
        q = q.filter(AgePolicy.jurisdiction == jurisdiction.strip().upper())
    return q.order_by(AgePolicy.jurisdiction, AgePolicy.policy_version).all()


@router.get("/resolve")
def resolve_age_policy(
    jurisdiction: str = Query(..., max_length=100),
    on_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Preview which policy applies to a jurisdiction value on a date (no user data)."""
    engine = AgeAndContestPolicyEngine(db)
    resolved = engine.resolve_jurisdiction(jurisdiction)
    on = on_date or utc_today()
    resolution = engine.resolve_policy(resolved.code, on)
    return {
        "jurisdiction_status": resolved.status.value,
        "jurisdiction": resolved.code,
        "evaluation_date": on.isoformat(),
        "policy_status": resolution.status,
        "policy_id": resolution.policy_id,
        "policy_version": resolution.policy_version,
    }


@router.get("/{policy_id}", response_model=AgePolicyRead)
def get_age_policy(policy_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _get(db, policy_id)


@router.post("", response_model=AgePolicyRead, status_code=status.HTTP_201_CREATED)
def create_age_policy(body: AgePolicyDefinition, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        return age_policy_admin.create_draft(db, body, actor_id=admin.id)
    except age_policy_admin.AgePolicyAdminError as exc:
        raise _conflict(exc) from exc


@router.put("/{policy_id}", response_model=AgePolicyRead)
def replace_draft_age_policy(policy_id: int, body: AgePolicyDefinition, db: Session = Depends(get_db),
                             admin: User = Depends(require_admin)):
    try:
        return age_policy_admin.update_draft(db, _get(db, policy_id), body, actor_id=admin.id)
    except age_policy_admin.AgePolicyAdminError as exc:
        raise _conflict(exc) from exc


@router.post("/{policy_id}/activate", response_model=AgePolicyRead)
def activate_age_policy(policy_id: int, body: AgePolicyStatusChange, db: Session = Depends(get_db),
                        admin: User = Depends(require_admin)):
    try:
        return age_policy_admin.activate(db, _get(db, policy_id), actor_id=admin.id, reason=body.reason, today=utc_today())
    except age_policy_admin.AgePolicyAdminError as exc:
        raise _conflict(exc) from exc


@router.post("/{policy_id}/withdraw", response_model=AgePolicyRead)
def withdraw_age_policy(policy_id: int, body: AgePolicyStatusChange, db: Session = Depends(get_db),
                        admin: User = Depends(require_admin)):
    try:
        return age_policy_admin.withdraw(db, _get(db, policy_id), actor_id=admin.id, reason=body.reason, today=utc_today())
    except age_policy_admin.AgePolicyAdminError as exc:
        raise _conflict(exc) from exc
