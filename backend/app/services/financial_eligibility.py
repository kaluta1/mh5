"""Prize, KYC-initiation and financial eligibility (Child/Teen Safety Phase 10:
s.3, s.5, s.9, s.14, s.30-32).

ONE backend place decides whether a person may perform a prize or financial
operation. Every decision is OPERATION-SPECIFIC (there is no single "financially
allowed" flag) and is computed from CURRENT state on every call.

Separation (s.30-32): holding an account, entering a contest, being nominated,
receiving votes, ranking, progressing or winning NEVER implies any operation
here. KYC NEVER implies age, age assurance, guardian consent or financial
eligibility: KYC is read only where an effective, enforced AgePolicy lists it as
an ADDITIONAL requirement for the operation (Phase 2 engine), and it never
changes the age tier (dob_evidence_for_user ignores KYC). Guardian authority
comes only from Phase 4 VERIFIED relationships, per granular consent scope
(check_consent); a sponsor, nominator, payer, group member, KYC record or an
admin assertion is never a guardian.

Outcomes: ALLOWED, HOLD (the member can resolve it: add a date of birth,
stronger age verification, guardian consent, required KYC) or REVIEW_REQUIRED
(no configured rule / open review or child-safety escalation; staff or an
operator must act - nothing is guessed). A HOLD/REVIEW never rewrites results,
votes, rankings, progression, balances, commissions, journals or any history,
and never creates a substitute winner or beneficiary: it only stops a NEW
irreversible action (provider call, payout, fulfilment, contract, release).

Rules (first match wins):
1. Account not usable -> HOLD.
2. Open age review/verification (Phase 2/3) -> REVIEW_REQUIRED.
3. Open child-safety escalation on an entry the person holds/submitted/is the
   subject of (Phase 6) -> REVIEW_REQUIRED.
4. UNKNOWN age (no usable DOB) -> HOLD. UNKNOWN is never adult.
   EXCEPTION - ordinary PAYMENT (own rule, see _payment_decision): after rules
   1-3 it is restricted ONLY by an explicitly configured restriction, i.e. an
   operator-ENFORCED PAYMENT jurisdiction policy ('*' or the member's country).
   With none, the result is "no configured age restriction" (ALLOWED) - which
   is NOT an adult classification: the tier stays UNKNOWN/minor and every
   adult-only operation keeps failing closed. Products carry no age
   classification in this codebase and none is guessed. Under an enforced
   policy UNKNOWN is HOLD, and a minor gets exactly the policy's threshold,
   assurance, KYC and guardian-consent (FINANCIAL_PAYMENT) requirements.
5. Contest prize/financial restrictions stored on the contest/category rules
   (Phase 5 columns) are free-form and are not interpreted -> REVIEW_REQUIRED
   for prize operations; invalid/conflicting rules -> REVIEW_REQUIRED.
6. Confirmed adult (adult tier, and legal adult under the effective AgePolicy
   when one exists - the platform convention of Phase 7):
   - where the operation's jurisdiction policy is ENFORCED, the Phase 2 engine
     must allow it (missing/conflicting policy -> REVIEW_REQUIRED, threshold ->
     HOLD, assurance -> HOLD, policy-listed KYC -> HOLD until approved);
   - prize claim/fulfilment/payout, digital assets and contracts additionally
     need IDENTITY_AND_AGE_VERIFIED age assurance (s.5 "prize payment or legally
     binding agreement: appropriate identity and age verification").
7. Minor (known age, not a confirmed adult):
   - operations with no configured minor rule in this codebase (withdrawal of
     value off-platform, digital assets, financial contracts, KYC provider
     processing) -> REVIEW_REQUIRED. No minimum financial age is invented.
   - otherwise the jurisdiction policy must be FOUND and ENFORCED for every
     mapped operation (else REVIEW_REQUIRED) and allow it; plus the required
     assurance; plus VALID verified-guardian consent for EVERY scope the
     operation needs (one scope never implies another), unless the enforced
     policy puts the minor at/above parental_consent_age.

Public/member responses never carry reason codes; audit events carry codes only
(no DOB, age, guardian evidence, KYC data or amounts).
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.child_safety import (
    AgeAssuranceLevel,
    AgeReviewStatus,
    AgeSafetyEventType,
    AgeTier,
    GuardianConsentScope,
    JurisdictionStatus,
    PolicyOperation,
    PolicyOutcome,
    PolicyRequirement,
)
from app.models.user import User

logger = logging.getLogger(__name__)


class FinancialOperation(str, enum.Enum):
    PRIZE_ELIGIBILITY = "PRIZE_ELIGIBILITY"
    PRIZE_CLAIM = "PRIZE_CLAIM"
    PRIZE_FULFILLMENT = "PRIZE_FULFILLMENT"
    MONETARY_PRIZE_PAYOUT = "MONETARY_PRIZE_PAYOUT"
    DIGITAL_ASSET_PRIZE = "DIGITAL_ASSET_PRIZE"
    PAYMENT = "PAYMENT"
    WITHDRAWAL = "WITHDRAWAL"
    FINANCIAL_CONTRACT = "FINANCIAL_CONTRACT"
    PUBLICITY_RELEASE = "PUBLICITY_RELEASE"
    KYC_INITIATION = "KYC_INITIATION"


class Outcome(str, enum.Enum):
    ALLOWED = "ALLOWED"
    HOLD = "HOLD"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class R:
    """Internal reason codes (audit/staff only)."""
    ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
    AGE_REVIEW_PENDING = "AGE_REVIEW_PENDING"
    CHILD_SAFETY_REVIEW = "CHILD_SAFETY_REVIEW"
    AGE_REQUIRED = "AGE_REQUIRED"
    CONTEST_RESTRICTIONS_REVIEW = "CONTEST_RESTRICTIONS_REVIEW"
    CONTEST_RULES_UNAVAILABLE = "CONTEST_RULES_UNAVAILABLE"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"
    POLICY_NOT_ENFORCED = "POLICY_NOT_ENFORCED"
    BELOW_MINIMUM_AGE = "BELOW_MINIMUM_AGE"
    AGE_ASSURANCE_REQUIRED = "AGE_ASSURANCE_REQUIRED"
    KYC_REQUIRED = "KYC_REQUIRED"
    GUARDIAN_CONSENT_REQUIRED = "GUARDIAN_CONSENT_REQUIRED"
    MINOR_RULE_NOT_CONFIGURED = "MINOR_RULE_NOT_CONFIGURED"
    EVALUATION_FAILED = "EVALUATION_FAILED"
    NO_CONFIGURED_RESTRICTION = "NO_CONFIGURED_RESTRICTION"   # informational on an ALLOWED payment


class NextStep:
    """What the member themselves can do (their own state only; never shown to others)."""
    ADD_DATE_OF_BIRTH = "ADD_DATE_OF_BIRTH"
    VERIFY_AGE = "VERIFY_AGE"
    GUARDIAN_CONSENT = "GUARDIAN_CONSENT"
    COMPLETE_KYC = "COMPLETE_KYC"
    WAIT_FOR_REVIEW = "WAIT_FOR_REVIEW"


_NEXT_STEP = {
    R.AGE_REQUIRED: NextStep.ADD_DATE_OF_BIRTH,
    R.AGE_ASSURANCE_REQUIRED: NextStep.VERIFY_AGE,
    R.GUARDIAN_CONSENT_REQUIRED: NextStep.GUARDIAN_CONSENT,
    R.KYC_REQUIRED: NextStep.COMPLETE_KYC,
}


@dataclass(frozen=True)
class OperationSpec:
    policy_operations: Tuple[PolicyOperation, ...]   # Phase 2 thresholds that govern it
    consent_scopes: Tuple[GuardianConsentScope, ...]  # Phase 4 scopes a minor needs (all of them)
    minor_rule_configured: bool                      # False -> minors always REVIEW_REQUIRED
    identity_assurance: bool                         # s.5 identity + age verification


_P, _S = PolicyOperation, GuardianConsentScope
SPECS: Dict[FinancialOperation, OperationSpec] = {
    FinancialOperation.PRIZE_ELIGIBILITY: OperationSpec((_P.PRIZE_CONTRACT,), (_S.PRIZE_ACCEPTANCE,), True, False),
    FinancialOperation.PRIZE_CLAIM: OperationSpec((_P.PRIZE_CONTRACT,), (_S.PRIZE_ACCEPTANCE,), True, True),
    FinancialOperation.PRIZE_FULFILLMENT: OperationSpec((_P.PRIZE_CONTRACT,), (_S.PRIZE_ACCEPTANCE,), True, True),
    FinancialOperation.MONETARY_PRIZE_PAYOUT: OperationSpec(
        (_P.PRIZE_CONTRACT, _P.PAYMENT), (_S.PRIZE_ACCEPTANCE, _S.FINANCIAL_PAYMENT), True, True),
    # s.31: no DigitalAssetEligibilityPolicy is configured in this codebase.
    FinancialOperation.DIGITAL_ASSET_PRIZE: OperationSpec(
        (_P.PRIZE_CONTRACT, _P.PAYMENT), (_S.PRIZE_ACCEPTANCE, _S.FINANCIAL_PAYMENT), False, True),
    # PAYMENT has its own rule (_payment_decision); the spec documents the
    # policy operation and consent scope it uses when a policy is enforced.
    FinancialOperation.PAYMENT: OperationSpec((_P.PAYMENT,), (_S.FINANCIAL_PAYMENT,), True, False),
    # Value leaving the platform (commission cashout, auto payout, Leaders reward,
    # marketplace seller release). AgePolicy has no withdrawal threshold, and
    # payouts are USDT (a digital asset): no minor rule is configured.
    FinancialOperation.WITHDRAWAL: OperationSpec((), (_S.FINANCIAL_PAYMENT,), False, False),
    # No contract consent scope exists (s.14 lists none): minors always reviewed.
    FinancialOperation.FINANCIAL_CONTRACT: OperationSpec((_P.PRIZE_CONTRACT,), (), False, True),
    FinancialOperation.PUBLICITY_RELEASE: OperationSpec((), (_S.PUBLICITY,), True, False),
    # Sending a minor's identity data to an external KYC provider has no
    # configured rule; adults only.
    FinancialOperation.KYC_INITIATION: OperationSpec((), (), False, False),
}

PRIZE_OPERATIONS = frozenset({
    FinancialOperation.PRIZE_ELIGIBILITY, FinancialOperation.PRIZE_CLAIM, FinancialOperation.PRIZE_FULFILLMENT,
    FinancialOperation.MONETARY_PRIZE_PAYOUT, FinancialOperation.DIGITAL_ASSET_PRIZE,
})


@dataclass(frozen=True)
class Decision:
    operation: FinancialOperation
    outcome: Outcome
    reasons: Tuple[str, ...] = ()
    missing_scopes: Tuple[str, ...] = field(default=())

    @property
    def allowed(self) -> bool:
        return self.outcome == Outcome.ALLOWED

    @property
    def next_step(self) -> Optional[str]:
        if self.allowed:
            return None
        if self.outcome == Outcome.REVIEW_REQUIRED:
            return NextStep.WAIT_FOR_REVIEW
        for reason in self.reasons:
            if reason in _NEXT_STEP:
                return _NEXT_STEP[reason]
        return NextStep.WAIT_FOR_REVIEW

    def member_view(self) -> dict:
        """The member's OWN status: no reason codes, DOB, age or guardian data."""
        return {"operation": self.operation.value, "status": self.outcome.value, "next_step": self.next_step}

    def client_error(self) -> dict:
        return {"code": "FINANCIAL_ACTION_UNAVAILABLE" if self.outcome == Outcome.HOLD else "PENDING_SAFETY_REVIEW",
                "message": ("This action isn't available for your account yet." if self.outcome == Outcome.HOLD
                            else "This action needs a safety review before it can continue."),
                "next_step": self.next_step}


class FinancialEligibilityHold(Exception):
    """Raised by irreversible financial/prize writers. Not a ValueError on
    purpose: callers must not turn it into a message built from str(exc)."""

    def __init__(self, decision: Decision):
        super().__init__(decision.outcome.value)
        self.decision = decision


# ---------------------------------------------------------------------------
# State readers (all read-only)
# ---------------------------------------------------------------------------

def _usable(user: Optional[User]) -> bool:
    return (user is not None and isinstance(getattr(user, "id", None), int)
            and bool(getattr(user, "is_active", False)) and not getattr(user, "is_deleted", False))


def open_child_safety_escalation(db: Session, user_id: int) -> bool:
    """A CHILD_SAFETY_ESCALATED entry this person holds, submitted, owns or is the nominee of."""
    from app.models.contest_eligibility import ContestEntrySafety
    from app.models.content_moderation import ContentModeration
    from app.models.contests import Contestant

    return db.query(ContentModeration.id).join(Contestant, Contestant.id == ContentModeration.contestant_id) \
        .outerjoin(ContestEntrySafety, ContestEntrySafety.contestant_id == Contestant.id) \
        .filter(ContentModeration.state == "CHILD_SAFETY_ESCALATED",
                or_(Contestant.user_id == user_id,
                    ContestEntrySafety.submitted_by_user_id == user_id,
                    ContestEntrySafety.account_holder_user_id == user_id,
                    ContestEntrySafety.nominee_user_id == user_id,
                    ContestEntrySafety.creative_owner_user_id == user_id)).first() is not None


def _contest_restrictions(db: Session, contest, jurisdiction: Optional[str]) -> Optional[str]:
    """Stored prize/financial restrictions are not interpreted (free-form)."""
    from app.models.contest_eligibility import CategoryAgePolicy, ContestAgeEligibility
    from app.services.contest_eligibility import _active_rule

    sources = [(ContestAgeEligibility, ContestAgeEligibility.contest_id, contest.id)]
    if getattr(contest, "category_id", None):
        sources.append((CategoryAgePolicy, CategoryAgePolicy.category_id, contest.category_id))
    for model, col, scope_id in sources:
        row, conflict = _active_rule(db, model, col, scope_id, jurisdiction)
        if conflict:
            return R.CONTEST_RULES_UNAVAILABLE
        if row is not None and (row.prize_restrictions or row.financial_restrictions):
            return R.CONTEST_RESTRICTIONS_REVIEW
    return None


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

_AVAILABILITY = (PolicyOutcome.UNKNOWN_JURISDICTION, PolicyOutcome.UNSUPPORTED_JURISDICTION,
                 PolicyOutcome.POLICY_CONFLICT)


def evaluate(db: Session, user: Optional[User], operation: FinancialOperation, *, contest=None,
             on: Optional[date] = None, at: Optional[datetime] = None) -> Decision:
    """Authoritative decision from CURRENT data. Never raises (fails closed)."""
    try:
        return _evaluate(db, user, FinancialOperation(operation), contest=contest, on=on, at=at)
    except Exception as exc:  # noqa: BLE001 - never fail open
        logger.warning("Phase 10 eligibility evaluation failed: %s", type(exc).__name__)
        return Decision(FinancialOperation(operation), Outcome.REVIEW_REQUIRED, (R.EVALUATION_FAILED,))


def _evaluate(db: Session, user: Optional[User], op: FinancialOperation, *, contest, on, at) -> Decision:
    from app.models.age_safety import UserAgeProfile
    from app.services.age_gate import enforcement_enabled
    from app.services.age_policy_engine import AgeAndContestPolicyEngine, utc_today
    from app.services.guardian_consent import consent_requirement
    from app.core.child_safety import ConsentRequirement

    spec = SPECS[op]
    on, at = on or utc_today(), at or datetime.utcnow()

    def decide(outcome: Outcome, *reasons: str, missing=()) -> Decision:
        return Decision(op, outcome, tuple(reasons), tuple(missing))

    if not _usable(user):
        return decide(Outcome.HOLD, R.ACCOUNT_UNAVAILABLE)
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()
    if profile is not None and (profile.review_status or AgeReviewStatus.NONE.value) != AgeReviewStatus.NONE.value:
        return decide(Outcome.REVIEW_REQUIRED, R.AGE_REVIEW_PENDING)
    if open_child_safety_escalation(db, user.id):
        return decide(Outcome.REVIEW_REQUIRED, R.CHILD_SAFETY_REVIEW)

    engine = AgeAndContestPolicyEngine(db)
    ctx = engine.context_for_user(user, on, profile)
    if op == FinancialOperation.PAYMENT:
        return _payment_decision(db, user, ctx, engine, decide, on=on, at=at)
    if not ctx.age_known:
        return decide(Outcome.HOLD, R.AGE_REQUIRED)            # UNKNOWN is never adult

    if contest is not None and op in PRIZE_OPERATIONS:
        restriction = _contest_restrictions(db, contest, ctx.jurisdiction.code)
        if restriction:
            return decide(Outcome.REVIEW_REQUIRED, restriction)

    adult = ctx.age_tier == AgeTier.ADULT_18_PLUS and (not ctx.policy.found or ctx.legal_adult)
    if not adult and not spec.minor_rule_configured:
        return decide(Outcome.REVIEW_REQUIRED, R.MINOR_RULE_NOT_CONFIGURED)

    policy_says_consent = False
    for pop in spec.policy_operations:
        enforced = enforcement_enabled(db, pop, ctx.jurisdiction.code)
        if not enforced:
            if adult:
                continue                     # platform adult baseline where the policy is not switched on
            return decide(Outcome.REVIEW_REQUIRED, R.POLICY_NOT_ENFORCED)
        if not adult and (ctx.jurisdiction.status != JurisdictionStatus.RESOLVED or not ctx.policy.found):
            return decide(Outcome.REVIEW_REQUIRED, R.POLICY_UNAVAILABLE)
        d = engine.evaluate(ctx, pop)
        if d.outcome in _AVAILABILITY:
            return decide(Outcome.REVIEW_REQUIRED, R.POLICY_UNAVAILABLE)
        if d.outcome == PolicyOutcome.DENIED:
            return decide(Outcome.HOLD, R.BELOW_MINIMUM_AGE)
        if d.outcome in (PolicyOutcome.REQUIRES_AGE_ASSURANCE, PolicyOutcome.UNKNOWN_AGE):
            return decide(Outcome.HOLD, R.AGE_ASSURANCE_REQUIRED)
        if d.outcome == PolicyOutcome.REQUIRES_GUARDIAN_CONSENT:
            policy_says_consent = True
        if PolicyRequirement.KYC in d.requirements and not getattr(user, "identity_verified", False):
            # KYC is an ADDITIONAL requirement only; it never satisfies anything else.
            return decide(Outcome.HOLD, R.KYC_REQUIRED)

    if spec.identity_assurance and (ctx.assurance_level is None or ctx.assurance_level.rank
                                    < AgeAssuranceLevel.IDENTITY_AND_AGE_VERIFIED.rank):
        return decide(Outcome.HOLD, R.AGE_ASSURANCE_REQUIRED)

    if adult and not policy_says_consent:
        return decide(Outcome.ALLOWED)

    missing = []
    for scope in spec.consent_scopes:
        requirement, check = consent_requirement(db, user, scope, on=on, at=at)
        if check.valid:
            continue
        # Waived only by an ENFORCED policy (every mapped operation was checked
        # enforced above) that places the minor at/above parental_consent_age.
        if (requirement == ConsentRequirement.NOT_REQUIRED_BY_POLICY and spec.policy_operations
                and not policy_says_consent):
            continue
        if requirement == ConsentRequirement.NOT_REQUIRED_ADULT and adult:
            continue
        missing.append(scope.value)
    if missing:
        return decide(Outcome.HOLD, R.GUARDIAN_CONSENT_REQUIRED, missing=missing)
    return decide(Outcome.ALLOWED)


def _payment_decision(db: Session, user: User, ctx, engine, decide, *, on, at) -> Decision:
    """Ordinary payment: only an explicitly configured restriction applies.
    Never classifies anyone as adult (the tier is not consulted to ALLOW)."""
    from app.services.age_gate import enforcement_enabled
    from app.services.guardian_consent import consent_requirement

    if not enforcement_enabled(db, PolicyOperation.PAYMENT, ctx.jurisdiction.code):
        return decide(Outcome.ALLOWED, R.NO_CONFIGURED_RESTRICTION)
    d = engine.evaluate(ctx, PolicyOperation.PAYMENT)
    if d.outcome in _AVAILABILITY:
        return decide(Outcome.REVIEW_REQUIRED, R.POLICY_UNAVAILABLE)
    if d.outcome == PolicyOutcome.UNKNOWN_AGE:
        return decide(Outcome.HOLD, R.AGE_REQUIRED)             # a configured restriction: UNKNOWN fails closed
    if d.outcome == PolicyOutcome.DENIED:
        return decide(Outcome.HOLD, R.BELOW_MINIMUM_AGE)
    if d.outcome == PolicyOutcome.REQUIRES_AGE_ASSURANCE:
        return decide(Outcome.HOLD, R.AGE_ASSURANCE_REQUIRED)
    if PolicyRequirement.KYC in d.requirements and not getattr(user, "identity_verified", False):
        return decide(Outcome.HOLD, R.KYC_REQUIRED)             # additional requirement only, never age
    if d.outcome == PolicyOutcome.REQUIRES_GUARDIAN_CONSENT:
        _requirement, check = consent_requirement(db, user, GuardianConsentScope.FINANCIAL_PAYMENT, on=on, at=at)
        if not check.valid:
            return decide(Outcome.HOLD, R.GUARDIAN_CONSENT_REQUIRED,
                          missing=(GuardianConsentScope.FINANCIAL_PAYMENT.value,))
    return decide(Outcome.ALLOWED)


# ---------------------------------------------------------------------------
# Enforcement helpers
# ---------------------------------------------------------------------------

def record_decision(db: Session, decision: Decision, *, user_id: Optional[int], actor_id: Optional[int] = None,
                    subject: Optional[Dict[str, object]] = None, commit: bool = True) -> None:
    """Audit a non-ALLOWED decision: codes and ids only. Never raises."""
    if decision.allowed:
        return
    from app.models.age_safety import AgeSafetyEvent

    try:
        now = datetime.utcnow()
        event = (AgeSafetyEventType.FINANCIAL_ACTION_REVIEW_REQUIRED if decision.outcome == Outcome.REVIEW_REQUIRED
                 else AgeSafetyEventType.FINANCIAL_ACTION_HELD)
        details = {"operation": decision.operation.value, "reasons": list(decision.reasons)}
        if decision.missing_scopes:
            details["missing_scopes"] = list(decision.missing_scopes)
        if actor_id is not None and actor_id != user_id:
            details["actor_id"] = int(actor_id)
        for key, value in (subject or {}).items():
            details[key] = value
        db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=event.value, user_id=user_id,
                              decision=decision.outcome.value, risk_flag=R.CHILD_SAFETY_REVIEW in decision.reasons,
                              details=details))
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception as exc:  # noqa: BLE001
        if commit:
            db.rollback()
        logger.warning("Phase 10 audit failed: %s", type(exc).__name__)


def require(db: Session, user: Optional[User], operation: FinancialOperation, *, actor_id: Optional[int] = None,
            contest=None, subject: Optional[Dict[str, object]] = None, audit_commit: bool = True) -> Decision:
    """Evaluate; on anything but ALLOWED audit and raise FinancialEligibilityHold."""
    decision = evaluate(db, user, operation, contest=contest)
    if not decision.allowed:
        record_decision(db, decision, user_id=getattr(user, "id", None), actor_id=actor_id, subject=subject,
                        commit=audit_commit)
        raise FinancialEligibilityHold(decision)
    return decision


def http_error(exc: FinancialEligibilityHold):
    from fastapi import HTTPException, status

    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.decision.client_error())


def member_status(db: Session, user: User, operations: Iterable[FinancialOperation]) -> list:
    return [evaluate(db, user, op).member_view() for op in operations]


# ---------------------------------------------------------------------------
# Prizes (the Prize / PrizeWinner models exist but no writer uses them yet:
# these are the authoritative decisions any future claim/fulfilment writer
# must call. They never touch the result, ranking or winner row.)
# ---------------------------------------------------------------------------

def prize_operation(prize) -> FinancialOperation:
    from app.models.prize import PrizeType

    kind = PrizeType(getattr(prize.prize_type, "value", prize.prize_type))
    if kind in (PrizeType.CASH, PrizeType.GIFT_CARD, PrizeType.CREDITS):
        return FinancialOperation.MONETARY_PRIZE_PAYOUT     # money or cash-equivalent value
    if kind == PrizeType.DIGITAL_ITEM:
        return FinancialOperation.DIGITAL_ASSET_PRIZE       # conservative: may be a transferable asset
    return FinancialOperation.PRIZE_FULFILLMENT             # PHYSICAL_ITEM / EXPERIENCE


def prize_fulfillment_decision(db: Session, winner) -> Decision:
    """Claim + type-specific fulfilment, both required. The PrizeWinner row
    (the legitimate result) is never modified here."""
    user = db.query(User).filter(User.id == winner.user_id).first()
    contest = getattr(winner.prize, "contest", None)
    claim = evaluate(db, user, FinancialOperation.PRIZE_CLAIM, contest=contest)
    if not claim.allowed:
        return claim
    return evaluate(db, user, prize_operation(winner.prize), contest=contest)


def guard_prize_fulfillment(db: Session, winner, *, actor_id: Optional[int]) -> Decision:
    decision = prize_fulfillment_decision(db, winner)
    if not decision.allowed:
        record_decision(db, decision, user_id=winner.user_id, actor_id=actor_id,
                        subject={"prize_winner_id": int(winner.id)})
        raise FinancialEligibilityHold(decision)
    return decision


def fulfillment_view(db: Session, winner, viewer: Optional[User]) -> dict:
    """Physical-prize fulfilment data. Delivery details go only to the winner
    and to explicit child-safety reviewers; everyone else (including ordinary
    admins/moderators) gets no address, phone, DOB, school or guardian data."""
    from app.services.content_safety import can_resolve_child_safety

    out = {"prize_winner_id": winner.id, "prize_id": winner.prize_id, "is_claimed": winner.is_claimed,
           "is_delivered": winner.is_delivered}
    if viewer is not None and (viewer.id == winner.user_id or can_resolve_child_safety(viewer)):
        out["delivery_address"] = winner.delivery_address
        out["tracking_number"] = winner.tracking_number
    return out
