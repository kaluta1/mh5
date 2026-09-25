"""Administration of versioned AgePolicy rows (section 3: administrators update
jurisdiction policies securely without source-code changes).

The lifecycle keeps policy history immutable and resolution deterministic:

- create: a new DRAFT with the next policy_version for its jurisdiction;
- update: only DRAFT rows can change (full replacement, re-validated);
- activate: DRAFT -> ACTIVE. The effective_date must be today or later (no
  retroactive policy) and later than every existing ACTIVE version of the
  jurisdiction (append-only timeline). An ACTIVE row is never edited;
- withdraw: DRAFT, or an ACTIVE version not yet in force, -> WITHDRAWN. A version
  already in force is superseded by activating a newer one, never withdrawn, so
  past evaluations stay reproducible.

Every change writes an AuditTrail row (policy content only, no personal data).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.child_safety import AgePolicyStatus
from app.models.accounting import AuditTrail
from app.models.age_policy import AgePolicy
from app.schemas.age_policy import AgePolicyDefinition


class AgePolicyAdminError(ValueError):
    """A lifecycle rule was violated. The message is safe to show to administrators."""


def _snapshot(policy: AgePolicy) -> dict:
    return {
        "jurisdiction": policy.jurisdiction,
        "policy_version": policy.policy_version,
        "status": policy.status,
        "effective_date": policy.effective_date.isoformat() if policy.effective_date else None,
    }


def _audit(db: Session, policy: AgePolicy, action: str, actor_id: Optional[int], old: Optional[dict], new: dict) -> None:
    db.add(AuditTrail(table_name="age_policies", record_id=policy.id, action=action,
                      old_values=old, new_values=new, user_id=actor_id))


def _apply(policy: AgePolicy, definition: AgePolicyDefinition) -> None:
    for key, value in definition.model_dump(mode="json").items():
        if key == "effective_date":
            value = definition.effective_date
        setattr(policy, key, value)


def create_draft(db: Session, definition: AgePolicyDefinition, *, actor_id: Optional[int]) -> AgePolicy:
    current_max = (
        db.query(func.max(AgePolicy.policy_version))
        .filter(AgePolicy.jurisdiction == definition.jurisdiction)
        .scalar()
    )
    policy = AgePolicy(policy_version=(current_max or 0) + 1, status=AgePolicyStatus.DRAFT.value,
                       created_by_user_id=actor_id)
    _apply(policy, definition)
    db.add(policy)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AgePolicyAdminError("A concurrent change created the same policy version; retry.") from exc
    _audit(db, policy, "AGE_POLICY_CREATE", actor_id, None, {**_snapshot(policy), "definition": definition.model_dump(mode="json")})
    db.commit()
    db.refresh(policy)
    return policy


def update_draft(db: Session, policy: AgePolicy, definition: AgePolicyDefinition, *, actor_id: Optional[int]) -> AgePolicy:
    if policy.status != AgePolicyStatus.DRAFT.value:
        raise AgePolicyAdminError("Only DRAFT policies can be edited; create a new version instead.")
    if definition.jurisdiction != policy.jurisdiction:
        raise AgePolicyAdminError("The jurisdiction of an existing policy cannot change.")
    old = _snapshot(policy)
    _apply(policy, definition)
    _audit(db, policy, "AGE_POLICY_UPDATE", actor_id, old, {**_snapshot(policy), "definition": definition.model_dump(mode="json")})
    db.commit()
    db.refresh(policy)
    return policy


def activate(db: Session, policy: AgePolicy, *, actor_id: Optional[int], reason: str, today: date) -> AgePolicy:
    if policy.status != AgePolicyStatus.DRAFT.value:
        raise AgePolicyAdminError("Only DRAFT policies can be activated.")
    if policy.effective_date < today:
        raise AgePolicyAdminError("effective_date cannot be in the past (no retroactive policies).")
    latest_active = (
        db.query(func.max(AgePolicy.effective_date))
        .filter(AgePolicy.jurisdiction == policy.jurisdiction, AgePolicy.status == AgePolicyStatus.ACTIVE.value)
        .scalar()
    )
    if latest_active is not None and policy.effective_date <= latest_active:
        raise AgePolicyAdminError("effective_date must be later than every ACTIVE version of this jurisdiction.")
    old = _snapshot(policy)
    policy.status = AgePolicyStatus.ACTIVE.value
    policy.status_changed_at = datetime.utcnow()
    policy.status_changed_by_user_id = actor_id
    policy.status_reason = reason
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AgePolicyAdminError("Another ACTIVE policy already takes effect on this date.") from exc
    _audit(db, policy, "AGE_POLICY_ACTIVATE", actor_id, old, {**_snapshot(policy), "reason": reason})
    db.commit()
    db.refresh(policy)
    return policy


def withdraw(db: Session, policy: AgePolicy, *, actor_id: Optional[int], reason: str, today: date) -> AgePolicy:
    if policy.status == AgePolicyStatus.WITHDRAWN.value:
        raise AgePolicyAdminError("Policy is already withdrawn.")
    if policy.status == AgePolicyStatus.ACTIVE.value and policy.effective_date <= today:
        raise AgePolicyAdminError(
            "A policy already in force cannot be withdrawn; activate a newer version to supersede it."
        )
    old = _snapshot(policy)
    policy.status = AgePolicyStatus.WITHDRAWN.value
    policy.status_changed_at = datetime.utcnow()
    policy.status_changed_by_user_id = actor_id
    policy.status_reason = reason
    _audit(db, policy, "AGE_POLICY_WITHDRAW", actor_id, old, {**_snapshot(policy), "reason": reason})
    db.commit()
    db.refresh(policy)
    return policy
