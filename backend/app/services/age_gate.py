"""Registration age gate (Child/Teen Safety requirement s.2, s.4, s.5, s.6).

The backend alone decides the account category: the client supplies only a date
of birth and a country, and everything else is computed here with the Phase 2
AgeAndContestPolicyEngine.

Two separate layers (never conflated):

1. PLATFORM SAFETY BASELINE (s.2): "UNDER_13 - ordinary independent MyHigh5
   membership is prohibited by default. Do not create a normal account."
   This is a platform default from the requirement itself, applied in every
   mode. It is NOT a jurisdiction-specific legal conclusion and does NOT mean
   that 13 or older is legally sufficient anywhere (s.2: "Never assume that 13
   is legally sufficient everywhere"). It only ever blocks; it never allows
   something a stricter enforced policy denies.

2. JURISDICTION / LEGAL POLICY (s.3): the resolved AgePolicy. It is
   authoritative only where ACCOUNT_CREATION enforcement is switched on for the
   jurisdiction (or '*') in child_safety_enforcement. Then only an engine
   ALLOWED creates an account (decision ALLOWED, basis JURISDICTION_POLICY), and
   a missing, unsupported or conflicting policy or an unresolved jurisdiction
   blocks.

Transition mode (enforcement off, the state while no approved policies exist):
registration stays available subject to layer 1, with decision
POLICY_NOT_ENFORCED and basis TRANSITION_NOT_ENFORCED. That is a provisional
state, not legal approval. The real engine outcome (e.g.
UNSUPPORTED_JURISDICTION when no policy exists) is recorded unchanged, and no
later-phase eligibility follows from it (the engine still returns
UNSUPPORTED_JURISDICTION for every operation).

s.6 circumvention controls (basis CIRCUMVENTION_CONTROL) apply in every mode.
Their numeric thresholds are operational security defaults
(app.core.age_safety_config), not legal rules, and are never sent to clients.

Privacy: identifiers are keyed HMAC-SHA256 hashes (see safety_hash). Raw
email, IP and DOB are never stored in the event log, and there is no device
fingerprinting.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.child_safety import (
    ENFORCEABLE_OPERATIONS,
    ENFORCEMENT_ALL_JURISDICTIONS,
    AgeAssuranceLevel,
    AgeSafetyEventType,
    AgeTier,
    DecisionBasis,
    DobSource,
    JurisdictionStatus,
    PolicyOperation,
    PolicyOutcome,
    RegistrationDecision,
)
from app.core.age_safety_config import get_age_safety_config
from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.age_safety import AgeSafetyEvent, ChildSafetyEnforcement, UserAgeProfile
from app.services.age_policy_engine import AgeAndContestPolicyEngine, AgeContext, DobEvidence, PolicyDecision

# Platform safety baseline (s.2 "UNDER_13 ... prohibited by default"). Not a legal
# threshold: jurisdiction policies may only be stricter (AgePolicy validation
# requires minimum_account_age >= 13). Documentation only; the tier check below
# (AgeTier.UNDER_13) applies it.
PLATFORM_BASELINE_MINIMUM_AGE = 13

_AGE_GATED = frozenset({
    RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE.value,
    RegistrationDecision.PARENTAL_CONSENT_REQUIRED.value,
    RegistrationDecision.AGE_ASSURANCE_REQUIRED.value,
    RegistrationDecision.REVIEW_REQUIRED.value,
})
_TIER_ORDER = {AgeTier.UNDER_13: 0, AgeTier.TEEN_13_15: 1, AgeTier.TEEN_16_17: 2, AgeTier.ADULT_18_PLUS: 3}

_OUTCOME_TO_DECISION = {
    PolicyOutcome.ALLOWED: RegistrationDecision.ALLOWED,
    PolicyOutcome.DENIED: RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE,
    PolicyOutcome.REQUIRES_GUARDIAN_CONSENT: RegistrationDecision.PARENTAL_CONSENT_REQUIRED,
    PolicyOutcome.REQUIRES_AGE_ASSURANCE: RegistrationDecision.AGE_ASSURANCE_REQUIRED,
    PolicyOutcome.UNKNOWN_AGE: RegistrationDecision.AGE_ASSURANCE_REQUIRED,
    PolicyOutcome.UNKNOWN_JURISDICTION: RegistrationDecision.UNRESOLVED_JURISDICTION,
    PolicyOutcome.UNSUPPORTED_JURISDICTION: RegistrationDecision.UNSUPPORTED_JURISDICTION,
    PolicyOutcome.POLICY_CONFLICT: RegistrationDecision.POLICY_UNAVAILABLE,
}

# Safe client messages: they never mention thresholds, ages or risk signals (s.6).
CLIENT_MESSAGES = {
    RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE: "We can't create a MyHigh5 account with the information provided.",
    RegistrationDecision.PARENTAL_CONSENT_REQUIRED: "A parent or guardian's approval is required before this account can be created.",
    RegistrationDecision.AGE_ASSURANCE_REQUIRED: "Additional age verification is required before this account can be created.",
    RegistrationDecision.UNRESOLVED_JURISDICTION: "Please select your country from the list.",
    RegistrationDecision.UNSUPPORTED_JURISDICTION: "Registration is not currently available in your country.",
    RegistrationDecision.POLICY_UNAVAILABLE: "Registration is not currently available in your country.",
    RegistrationDecision.RETRY_LIMITED: "Too many registration attempts. Please try again later.",
    RegistrationDecision.REVIEW_REQUIRED: "We can't complete this registration right now. Please contact support.",
}


# ---------------------------------------------------------------------------
# Privacy-preserving identifiers
# ---------------------------------------------------------------------------

def _hash_key() -> bytes:
    """Server-side HMAC key: AGE_SAFETY_HASH_KEY if configured, otherwise derived
    from SECRET_KEY (HMAC-SHA256 with a fixed purpose label). Never logged."""
    base = (getattr(settings, "AGE_SAFETY_HASH_KEY", "") or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(base, b"mh5-age-safety-v1", hashlib.sha256).digest()


def safety_hash(kind: str, value: Optional[str]) -> Optional[str]:
    """Keyed HMAC-SHA256 of a normalized identifier (email/ip). It is not a plain
    or salted hash: it cannot be recomputed or brute-forced without the server key.

    Key rotation (AGE_SAFETY_HASH_KEY or SECRET_KEY) intentionally breaks
    correlation with older events: circumvention history starts fresh, and old
    hashes can no longer be linked to anyone."""
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    return hmac.new(_hash_key(), f"{kind}:{normalized}".encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Enforcement switch
# ---------------------------------------------------------------------------

def enforcement_enabled(db: Session, operation: PolicyOperation, jurisdiction_code: Optional[str]) -> bool:
    keys = [ENFORCEMENT_ALL_JURISDICTIONS] + ([jurisdiction_code] if jurisdiction_code else [])
    return (
        db.query(ChildSafetyEnforcement.id)
        .filter(
            ChildSafetyEnforcement.operation == operation.value,
            ChildSafetyEnforcement.jurisdiction.in_(keys),
            ChildSafetyEnforcement.enabled.is_(True),
        )
        .first()
        is not None
    )


def set_enforcement(db: Session, *, operation: PolicyOperation, jurisdiction: str, enabled: bool,
                    reason: str, actor_id: Optional[int]) -> ChildSafetyEnforcement:
    if operation not in ENFORCEABLE_OPERATIONS:
        raise ValueError(f"Enforcement for {operation.value} is not available yet")
    jurisdiction = (jurisdiction or "").strip().upper()
    if jurisdiction != ENFORCEMENT_ALL_JURISDICTIONS:
        resolved = AgeAndContestPolicyEngine.resolve_jurisdiction(jurisdiction)
        if resolved.status != JurisdictionStatus.RESOLVED or resolved.code != jurisdiction:
            raise ValueError("jurisdiction must be a supported ISO 3166-1 alpha-2 code or '*'")
    row = (
        db.query(ChildSafetyEnforcement)
        .filter(ChildSafetyEnforcement.operation == operation.value, ChildSafetyEnforcement.jurisdiction == jurisdiction)
        .with_for_update()
        .first()
    )
    old = {"enabled": row.enabled} if row else None
    if row is None:
        row = ChildSafetyEnforcement(operation=operation.value, jurisdiction=jurisdiction)
        db.add(row)
    row.enabled = bool(enabled)
    row.reason = reason
    row.changed_by_user_id = actor_id
    row.changed_at = datetime.utcnow()
    db.flush()
    db.add(AuditTrail(table_name="child_safety_enforcement", record_id=row.id, action="ENFORCEMENT_SET",
                      old_values=old, new_values={"operation": operation.value, "jurisdiction": jurisdiction,
                                                  "enabled": row.enabled, "reason": reason}, user_id=actor_id))
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Registration evaluation
# ---------------------------------------------------------------------------

@dataclass
class RegistrationGateResult:
    decision: RegistrationDecision
    enforced: bool
    context: AgeContext
    policy_decision: PolicyDecision
    email_hash: Optional[str]
    ip_hash: Optional[str]
    basis: DecisionBasis = DecisionBasis.TRANSITION_NOT_ENFORCED
    risk_signals: List[str] = field(default_factory=list)   # internal only
    flag_for_review: bool = False                            # allowed, but escalate afterwards

    @property
    def legally_resolved(self) -> bool:
        """True only when an enforced, resolved jurisdiction AgePolicy decided."""
        return self.basis == DecisionBasis.JURISDICTION_POLICY

    @property
    def allowed(self) -> bool:
        return self.decision.creates_account

    @property
    def client_message(self) -> Optional[str]:
        return CLIENT_MESSAGES.get(self.decision)


def _recent_attempts(db: Session, column, value: Optional[str], since: datetime) -> List[AgeSafetyEvent]:
    if not value:
        return []
    return (
        db.query(AgeSafetyEvent)
        .filter(column == value, AgeSafetyEvent.event_type == AgeSafetyEventType.AGE_GATE_ATTEMPT.value,
                AgeSafetyEvent.created_at >= since)
        .all()
    )


def _older(tier: AgeTier, than: Optional[str]) -> bool:
    try:
        return _TIER_ORDER.get(tier, -1) > _TIER_ORDER.get(AgeTier(than), 99)
    except ValueError:
        return False


def _risk(db: Session, tier: AgeTier, email_hash: Optional[str], ip_hash: Optional[str],
          now: datetime) -> Tuple[Optional[RegistrationDecision], List[str], bool]:
    """Return (blocking decision or None, internal signals, flag_for_review).
    Thresholds come from the operational config, never from AgePolicy."""
    cfg = get_age_safety_config()
    signals: List[str] = []
    by_email_retry = _recent_attempts(db, AgeSafetyEvent.email_hash, email_hash,
                                      now - timedelta(hours=cfg.retry_email_window_hours))
    by_ip_retry = _recent_attempts(db, AgeSafetyEvent.ip_hash, ip_hash,
                                   now - timedelta(minutes=cfg.retry_ip_window_minutes))
    if len(by_email_retry) >= cfg.retry_email_max or len(by_ip_retry) >= cfg.retry_ip_max:
        return RegistrationDecision.RETRY_LIMITED, ["retry_limit"], False

    by_email = _recent_attempts(db, AgeSafetyEvent.email_hash, email_hash,
                                now - timedelta(days=cfg.email_correlation_days))
    by_ip = _recent_attempts(db, AgeSafetyEvent.ip_hash, ip_hash, now - timedelta(hours=cfg.ip_correlation_hours))
    gated_email = [e for e in by_email if e.decision in _AGE_GATED]
    gated_ip = [e for e in by_ip if e.decision in _AGE_GATED]
    immediate = now - timedelta(minutes=cfg.ip_immediate_window_minutes)

    if any(_older(tier, e.age_tier) for e in gated_email):
        signals.append("email_older_claim_after_age_gate")
    if any(_older(tier, e.age_tier) and e.created_at >= immediate for e in gated_ip):
        signals.append("ip_immediate_older_claim_after_age_gate")
    if len(gated_ip) >= cfg.ip_repeated_probe_min and any(_older(tier, e.age_tier) for e in gated_ip):
        signals.append("ip_repeated_age_gate_probing")
    tiers = {e.age_tier for e in by_email if e.age_tier} | {tier.value}
    if len(tiers) >= cfg.tier_hopping_distinct_tiers:
        signals.append("email_tier_hopping")
    if signals:
        return RegistrationDecision.REVIEW_REQUIRED, signals, False

    # Weaker signal (shared networks exist): allow but escalate for review.
    if any(_older(tier, e.age_tier) for e in gated_ip):
        return None, ["ip_older_claim_after_age_gate"], True
    return None, [], False


def evaluate_registration(
    db: Session,
    *,
    date_of_birth: date,
    country: Optional[str],
    email: Optional[str],
    ip: Optional[str],
    on: date,
    now: Optional[datetime] = None,
) -> RegistrationGateResult:
    """Pure decision (no writes). Callers record the attempt with record_attempt()."""
    now = now or datetime.utcnow()
    engine = AgeAndContestPolicyEngine(db)
    context = engine.build_context(
        dob_evidence=DobEvidence(date_of_birth, AgeAssuranceLevel.SELF_DECLARED_DOB),
        jurisdiction_value=country,
        on=on,
    )
    policy_decision = engine.evaluate(context, PolicyOperation.ACCOUNT_CREATION)
    enforced = enforcement_enabled(db, PolicyOperation.ACCOUNT_CREATION, context.jurisdiction.code)
    email_hash = safety_hash("email", email)
    ip_hash = safety_hash("ip", ip)

    def result(decision, basis, signals=(), flag=False):
        return RegistrationGateResult(decision, enforced, context, policy_decision, email_hash, ip_hash,
                                      basis, list(signals), flag)

    blocking, signals, flag = _risk(db, context.age_tier, email_hash, ip_hash, now)
    if blocking is not None:
        return result(blocking, DecisionBasis.CIRCUMVENTION_CONTROL, signals)

    if context.age_tier in (AgeTier.UNDER_13, AgeTier.UNKNOWN):
        # Platform safety baseline (s.2); UNKNOWN cannot occur with a validated DOB.
        return result(RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE, DecisionBasis.PLATFORM_BASELINE, signals)

    if not enforced:
        # Provisional: allowed by the platform baseline only. Not legal approval.
        return result(RegistrationDecision.POLICY_NOT_ENFORCED, DecisionBasis.TRANSITION_NOT_ENFORCED, signals, flag)

    decision = _OUTCOME_TO_DECISION.get(policy_decision.outcome, RegistrationDecision.POLICY_UNAVAILABLE)
    return result(decision, DecisionBasis.JURISDICTION_POLICY, signals, flag and decision.creates_account)


def record_attempt(db: Session, result: RegistrationGateResult, now: Optional[datetime] = None) -> AgeSafetyEvent:
    """Persist the gate attempt in its own transaction (kept even when registration
    later fails, so repeated attempts are visible). Contains no raw DOB/email/IP."""
    now = now or datetime.utcnow()
    event = AgeSafetyEvent(
        created_at=now,
        updated_at=now,
        event_type=AgeSafetyEventType.AGE_GATE_ATTEMPT.value,
        email_hash=result.email_hash,
        ip_hash=result.ip_hash,
        jurisdiction_code=result.context.jurisdiction.code,
        age_tier=result.context.age_tier.value,
        decision=result.decision.value,
        enforced=result.enforced,
        policy_id=result.context.policy.policy_id,
        policy_version=result.context.policy.policy_version,
        risk_flag=bool(result.risk_signals),
        details={"basis": result.basis.value, **({"signals": result.risk_signals} if result.risk_signals else {})},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def apply_registration_state(db: Session, user, result: RegistrationGateResult, attempt: AgeSafetyEvent,
                             now: Optional[datetime] = None) -> UserAgeProfile:
    """Create the new user's age profile inside the registration transaction
    (no commit here: it commits or rolls back together with the user)."""
    now = now or datetime.utcnow()
    ctx = result.context
    profile = UserAgeProfile(
        user_id=user.id,
        dob_source=DobSource.SELF_DECLARED_REGISTRATION.value,
        assurance_level=AgeAssuranceLevel.SELF_DECLARED_DOB.value,
        jurisdiction_code=ctx.jurisdiction.code,
        jurisdiction_status=ctx.jurisdiction.status.value,
        registration_decision=result.decision.value,
        registration_policy_outcome=result.policy_decision.outcome.value,
        registration_enforced=result.enforced,
        registration_policy_id=ctx.policy.policy_id,
        registration_policy_version=ctx.policy.policy_version,
        review_status="AGE_REVIEW_REQUIRED" if result.flag_for_review else "NONE",
        review_reason="AGE_GATE_RISK" if result.flag_for_review else None,
        review_updated_at=now if result.flag_for_review else None,
        terms_accepted_at=now,
    )
    db.add(profile)
    attempt_row = db.query(AgeSafetyEvent).filter(AgeSafetyEvent.id == attempt.id).first()
    if attempt_row is not None:
        attempt_row.user_id = user.id
    for event_type in (AgeSafetyEventType.DOB_CAPTURED, AgeSafetyEventType.TERMS_ACCEPTED):
        db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=event_type.value, user_id=user.id,
                              age_tier=ctx.age_tier.value,
                              jurisdiction_code=ctx.jurisdiction.code,
                              details={"source": DobSource.SELF_DECLARED_REGISTRATION.value,
                                       "basis": result.basis.value}
                              if event_type == AgeSafetyEventType.DOB_CAPTURED else None))
    db.flush()
    return profile
