"""Centralized date-of-birth change protection (Child/Teen Safety s.5, s.6).

Every change to users.date_of_birth after registration goes through this module.
crud_user.update refuses the field, so no other path can change it silently.

Self-service rules:
- first capture (no DOB yet): applied and recorded (self-declared, not verified);
  a DOB below the platform minimum age is flagged AGE_REVIEW_REQUIRED;
- same value: no-op;
- a correction that keeps the age tier AND every effective-policy outcome:
  applied immediately, audited (AUTO_APPLIED);
- a correction that changes the age tier or any policy outcome: NOT applied. A
  PENDING review record is created. An older claim needs AGE_VERIFICATION_REQUIRED
  (s.5 "claimed age changes from 15 to 25"); a younger claim needs AGE_REVIEW_REQUIRED;
- repeated changes (more than one within the window): NOT applied, AGE_REVIEW_REQUIRED
  (s.5 "repeated DOB manipulation").
Administrator corrections and review decisions are authenticated, audited, and
never mark the age as verified (a reviewed or corrected DOB is still not
age-assurance evidence).

Previous and requested DOB values live only in dob_change_records (restricted).
Events and AuditTrail carry no DOB values.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.child_safety import (
    AgeAssuranceLevel,
    AgeReviewStatus,
    AgeSafetyEventType,
    AgeTier,
    DobChangeStatus,
    DobSource,
    PolicyOperation,
)
from app.core.age_safety_config import get_age_safety_config
from app.models.accounting import AuditTrail
from app.models.age_safety import AgeSafetyEvent, DobChangeRecord, UserAgeProfile
from app.models.user import User
from app.services.age_policy_engine import AgeAndContestPolicyEngine, DobEvidence

# Repeated-change limits are operational security defaults (not legal rules):
# see app.core.age_safety_config (dob_change_window_days, dob_max_self_changes_in_window).
_TIER_ORDER = {AgeTier.UNDER_13: 0, AgeTier.TEEN_13_15: 1, AgeTier.TEEN_16_17: 2, AgeTier.ADULT_18_PLUS: 3}


class DobUpdateStatus(str, enum.Enum):
    CAPTURED = "CAPTURED"
    UNCHANGED = "UNCHANGED"
    APPLIED = "APPLIED"
    PENDING_REVIEW = "PENDING_REVIEW"


@dataclass(frozen=True)
class DobUpdateResult:
    status: DobUpdateStatus
    review_status: str


class DobChangeError(ValueError):
    """Safe to show to the caller."""


def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _as_datetime(value: date) -> datetime:
    return datetime(value.year, value.month, value.day)


def get_or_create_profile(db: Session, user: User) -> UserAgeProfile:
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).with_for_update().first()
    if profile is None:
        # Legacy user: record provenance honestly; nothing is upgraded or invented.
        profile = UserAgeProfile(
            user_id=user.id,
            dob_source=DobSource.LEGACY_PROFILE.value if user.date_of_birth is not None else None,
            assurance_level=AgeAssuranceLevel.SELF_DECLARED_DOB.value if user.date_of_birth is not None else None,
            review_status=AgeReviewStatus.NONE.value,
        )
        db.add(profile)
        db.flush()
    return profile


def _event(db: Session, user_id: int, event_type: AgeSafetyEventType, now: datetime, *, tier: Optional[AgeTier] = None,
           risk: bool = False, details: Optional[dict] = None) -> None:
    db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=event_type.value, user_id=user_id,
                          age_tier=tier.value if tier else None, risk_flag=risk, details=details))


def _set_review(profile: UserAgeProfile, status: AgeReviewStatus, reason: Optional[str], now: datetime) -> None:
    profile.review_status = status.value
    profile.review_reason = reason
    profile.review_updated_at = now


def _material_change(engine: AgeAndContestPolicyEngine, user: User, old: date, new: date, on: date) -> Optional[str]:
    old_ctx = engine.build_context(dob_evidence=DobEvidence(old, AgeAssuranceLevel.SELF_DECLARED_DOB),
                                   jurisdiction_value=user.country, on=on)
    new_ctx = engine.build_context(dob_evidence=DobEvidence(new, AgeAssuranceLevel.SELF_DECLARED_DOB),
                                   jurisdiction_value=user.country, on=on)
    if old_ctx.age_tier != new_ctx.age_tier:
        return "TIER_CHANGE"
    if old_ctx.policy.found:
        for op in PolicyOperation:
            if engine.evaluate(old_ctx, op).outcome != engine.evaluate(new_ctx, op).outcome:
                return "POLICY_ELIGIBILITY_CHANGE"
    return None


def _reevaluate_contest_entries(db: Session, user_id: int, trigger: str, actor_id: Optional[int]) -> None:
    """Phase 5: a DOB/review change can change contest eligibility (lazy import: no cycle)."""
    from app.services.contest_eligibility import safe_reevaluate_for_user

    safe_reevaluate_for_user(db, user_id, trigger=trigger, actor_id=actor_id)


def submit_self_service_dob(db: Session, user: User, new_dob: date, *, today: date,
                            now: Optional[datetime] = None) -> DobUpdateResult:
    now = now or datetime.utcnow()
    engine = AgeAndContestPolicyEngine(db)
    new_dob = _as_date(new_dob)
    current = _as_date(user.date_of_birth)
    new_tier = engine.resolve_age_tier(engine.calculate_age(new_dob, today))
    if new_tier == AgeTier.UNKNOWN:
        raise DobChangeError("Invalid date of birth")

    if current == new_dob:
        profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()
        return DobUpdateResult(DobUpdateStatus.UNCHANGED, profile.review_status if profile else AgeReviewStatus.NONE.value)

    profile = get_or_create_profile(db, user)

    if current is None:
        user.date_of_birth = _as_datetime(new_dob)
        profile.dob_source = DobSource.SELF_DECLARED_PROFILE.value
        profile.assurance_level = AgeAssuranceLevel.SELF_DECLARED_DOB.value
        db.add(DobChangeRecord(created_at=now, updated_at=now, user_id=user.id, previous_dob=None, requested_dob=new_dob,
                               status=DobChangeStatus.AUTO_APPLIED.value, reason_code="INITIAL_CAPTURE",
                               requested_by_user_id=user.id))
        risk = new_tier == AgeTier.UNDER_13
        if risk:  # s.2 / s.5: an account-holder below the platform minimum needs review
            _set_review(profile, AgeReviewStatus.AGE_REVIEW_REQUIRED, "SELF_DECLARED_BELOW_MINIMUM", now)
        _event(db, user.id, AgeSafetyEventType.DOB_CAPTURED, now, tier=new_tier, risk=risk,
               details={"source": DobSource.SELF_DECLARED_PROFILE.value})
        db.commit()
        _reevaluate_contest_entries(db, user.id, "DOB_CAPTURED", user.id)
        return DobUpdateResult(DobUpdateStatus.CAPTURED, profile.review_status)

    pending = (db.query(DobChangeRecord)
               .filter(DobChangeRecord.user_id == user.id, DobChangeRecord.status == DobChangeStatus.PENDING.value)
               .first())
    if pending is not None:
        raise DobChangeError("A date of birth change is already awaiting review.")

    cfg = get_age_safety_config()
    recent_changes = (
        db.query(DobChangeRecord)
        .filter(DobChangeRecord.user_id == user.id,
                DobChangeRecord.reason_code != "INITIAL_CAPTURE",
                DobChangeRecord.status != DobChangeStatus.ADMIN_APPLIED.value,
                DobChangeRecord.created_at >= now - timedelta(days=cfg.dob_change_window_days))
        .count()
    )
    old_tier = engine.resolve_age_tier(engine.calculate_age(current, today))

    reason = None
    review = None
    if recent_changes >= cfg.dob_max_self_changes_in_window:
        reason, review = "REPEATED_CHANGES", AgeReviewStatus.AGE_REVIEW_REQUIRED
    else:
        material = _material_change(engine, user, current, new_dob, today)
        if material:
            reason = material
            older = _TIER_ORDER.get(new_tier, -1) > _TIER_ORDER.get(old_tier, -1) or (
                new_tier == old_tier and new_dob < current)
            review = AgeReviewStatus.AGE_VERIFICATION_REQUIRED if older else AgeReviewStatus.AGE_REVIEW_REQUIRED

    if reason:
        db.add(DobChangeRecord(created_at=now, updated_at=now, user_id=user.id, previous_dob=current,
                               requested_dob=new_dob, status=DobChangeStatus.PENDING.value, reason_code=reason,
                               requested_by_user_id=user.id))
        _set_review(profile, review, reason, now)
        _event(db, user.id, AgeSafetyEventType.DOB_CHANGE_REQUESTED, now, tier=old_tier, risk=True,
               details={"reason": reason, "requested_tier": new_tier.value})
        db.commit()
        _reevaluate_contest_entries(db, user.id, "DOB_CHANGE_REQUESTED", user.id)
        return DobUpdateResult(DobUpdateStatus.PENDING_REVIEW, profile.review_status)

    db.add(DobChangeRecord(created_at=now, updated_at=now, user_id=user.id, previous_dob=current,
                           requested_dob=new_dob, status=DobChangeStatus.AUTO_APPLIED.value,
                           reason_code="SAME_TIER_CORRECTION", requested_by_user_id=user.id))
    user.date_of_birth = _as_datetime(new_dob)
    profile.dob_source = DobSource.SELF_CORRECTION.value
    profile.assurance_level = AgeAssuranceLevel.SELF_DECLARED_DOB.value
    _event(db, user.id, AgeSafetyEventType.DOB_CHANGED, now, tier=new_tier,
           details={"source": DobSource.SELF_CORRECTION.value})
    db.commit()
    _reevaluate_contest_entries(db, user.id, "DOB_CHANGED", user.id)
    return DobUpdateResult(DobUpdateStatus.APPLIED, profile.review_status)


def admin_correct_dob(db: Session, user: User, new_dob: date, *, reason: str, admin_id: int,
                      today: date, now: Optional[datetime] = None) -> UserAgeProfile:
    now = now or datetime.utcnow()
    new_dob = _as_date(new_dob)
    engine = AgeAndContestPolicyEngine(db)
    new_tier = engine.resolve_age_tier(engine.calculate_age(new_dob, today))
    if new_tier == AgeTier.UNKNOWN:
        raise DobChangeError("Invalid date of birth")
    profile = get_or_create_profile(db, user)
    previous = _as_date(user.date_of_birth)
    for pending in db.query(DobChangeRecord).filter(DobChangeRecord.user_id == user.id,
                                                    DobChangeRecord.status == DobChangeStatus.PENDING.value):
        pending.status = DobChangeStatus.REJECTED.value
        pending.reviewed_by_user_id = admin_id
        pending.reviewed_at = now
        pending.review_note = "Superseded by administrator correction"
    db.flush()
    record = DobChangeRecord(created_at=now, updated_at=now, user_id=user.id, previous_dob=previous,
                             requested_dob=new_dob, status=DobChangeStatus.ADMIN_APPLIED.value,
                             reason_code="ADMIN_CORRECTION", requested_by_user_id=admin_id,
                             reviewed_by_user_id=admin_id, reviewed_at=now, review_note=reason)
    db.add(record)
    user.date_of_birth = _as_datetime(new_dob)
    profile.dob_source = DobSource.ADMIN_CORRECTION.value
    profile.assurance_level = AgeAssuranceLevel.SELF_DECLARED_DOB.value  # a correction is not verification
    _set_review(profile, AgeReviewStatus.NONE, None, now)
    _event(db, user.id, AgeSafetyEventType.DOB_CHANGED, now, tier=new_tier,
           details={"source": DobSource.ADMIN_CORRECTION.value})
    db.flush()
    db.add(AuditTrail(table_name="dob_change_records", record_id=record.id, action="DOB_ADMIN_CORRECTION",
                      old_values=None, new_values={"user_id": user.id, "reason": reason}, user_id=admin_id))
    db.commit()
    db.refresh(profile)
    _reevaluate_contest_entries(db, user.id, "DOB_ADMIN_CORRECTION", admin_id)
    return profile


def review_change(db: Session, record: DobChangeRecord, *, approve: bool, note: str, admin_id: int,
                  today: date, now: Optional[datetime] = None) -> DobChangeRecord:
    now = now or datetime.utcnow()
    if record.status != DobChangeStatus.PENDING.value:
        raise DobChangeError("Only pending changes can be reviewed.")
    user = db.query(User).filter(User.id == record.user_id).with_for_update().first()
    profile = get_or_create_profile(db, user)
    record.reviewed_by_user_id = admin_id
    record.reviewed_at = now
    record.review_note = note
    if approve:
        record.status = DobChangeStatus.APPROVED.value
        user.date_of_birth = _as_datetime(record.requested_dob)
        profile.dob_source = DobSource.ADMIN_REVIEWED.value
        profile.assurance_level = AgeAssuranceLevel.SELF_DECLARED_DOB.value
    else:
        record.status = DobChangeStatus.REJECTED.value
    _set_review(profile, AgeReviewStatus.NONE, None, now)
    engine = AgeAndContestPolicyEngine(db)
    tier = engine.resolve_age_tier(engine.calculate_age(_as_date(user.date_of_birth), today))
    _event(db, user.id, AgeSafetyEventType.DOB_CHANGE_REVIEWED, now, tier=tier,
           details={"approved": approve, "reason": record.reason_code})
    db.add(AuditTrail(table_name="dob_change_records", record_id=record.id,
                      action="DOB_CHANGE_APPROVED" if approve else "DOB_CHANGE_REJECTED",
                      old_values={"status": DobChangeStatus.PENDING.value},
                      new_values={"status": record.status, "note": note}, user_id=admin_id))
    db.commit()
    db.refresh(record)
    _reevaluate_contest_entries(db, record.user_id, "DOB_CHANGE_REVIEWED", admin_id)
    return record
