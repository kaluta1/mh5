"""AgeAndContestPolicyEngine: the authoritative backend source of age/jurisdiction
policy (MyHigh5 Child/Teen Safety requirement, sections 2, 3, 5 and 32).

Resolution chain:

    user/viewer -> jurisdiction -> effective AgePolicy -> DOB evidence -> age
    -> age tier -> operation evaluation

Everything fails closed. UNKNOWN age, unknown or unresolved jurisdiction, a
missing policy, conflicting policies and invalid stored policy data never
produce ALLOWED and never grant adult treatment.

Phase 2 scope: this engine is available but is NOT wired into registration,
contests, voting, TopHigh5, content delivery, messaging, advertising or
financial flows. Later phases consume it.

Separation of concerns (section 32): KYC, age assurance, guardian consent,
contest eligibility and financial eligibility are separate. The engine reports
KYC and guardian consent as *requirements*. It never reads KYC state, and a
verified KYC never implies an age, tier or permission.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import FrozenSet, List, Optional, Union

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.child_safety import (
    AGE_THRESHOLD_FIELD_BY_OPERATION,
    AgeAssuranceLevel,
    AgePolicyStatus,
    AgeTier,
    ContentRating,
    JurisdictionStatus,
    PolicyOperation,
    PolicyOutcome,
    PolicyRequirement,
)
from app.core.jurisdictions import ISO_COUNTRY_NAMES
from app.models.age_policy import AgePolicy
from app.schemas.age_policy import AgePolicyDefinition

# Default age structure boundaries (section 2). These define the named tiers;
# jurisdiction-specific thresholds live in AgePolicy rows.
TEEN_START_AGE = 13
OLDER_TEEN_START_AGE = 16
ADULT_TIER_START_AGE = 18
# Ages above this are treated as unreliable DOB data, not as very old adults.
MAX_PLAUSIBLE_AGE = 120

_NAME_TO_CODE = {name.casefold(): code for code, name in ISO_COUNTRY_NAMES.items()}


def utc_today() -> date:
    """Evaluation date for callers at the request boundary. Core logic takes explicit dates."""
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DobEvidence:
    """A date of birth plus how strongly it is assured. Never returned to consumers."""

    date_of_birth: date
    assurance_level: AgeAssuranceLevel


@dataclass(frozen=True)
class JurisdictionResolution:
    status: JurisdictionStatus
    code: Optional[str] = None
    source: Optional[str] = None  # "ISO_CODE" | "COUNTRY_NAME"


class PolicyResolutionStatus:
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    INVALID_DATA = "INVALID_DATA"


@dataclass(frozen=True)
class PolicyResolution:
    status: str
    jurisdiction: Optional[str]
    evaluation_date: date
    policy_id: Optional[int] = None
    policy_version: Optional[int] = None
    policy: Optional[AgePolicyDefinition] = field(default=None, repr=False)

    @property
    def found(self) -> bool:
        return self.status == PolicyResolutionStatus.FOUND


@dataclass(frozen=True)
class AgeContext:
    """Everything a later phase needs to evaluate operations for one person.

    The date of birth is not kept. The numeric age is private (repr/compare
    disabled) and not exposed through PolicyDecision.
    """

    evaluation_date: date
    age_tier: AgeTier
    assurance_level: Optional[AgeAssuranceLevel]
    jurisdiction: JurisdictionResolution
    policy: PolicyResolution
    _age: Optional[int] = field(default=None, repr=False, compare=False)

    @property
    def age_known(self) -> bool:
        return self._age is not None

    @property
    def legal_adult(self) -> bool:
        """True only for a known age at or above the jurisdiction's adult_age."""
        return bool(self.policy.found and self._age is not None and self._age >= self.policy.policy.adult_age)

    @property
    def adult_content_eligible(self) -> bool:
        """Adult tier AND legal adult under the effective policy. Never true for UNKNOWN."""
        return self.age_tier == AgeTier.ADULT_18_PLUS and self.legal_adult


@dataclass(frozen=True)
class PolicyDecision:
    """Structured result of evaluating one operation. Contains no DOB or numeric age."""

    operation: PolicyOperation
    outcome: PolicyOutcome
    reason: str
    age_tier: AgeTier
    jurisdiction: Optional[str]
    policy_id: Optional[int] = None
    policy_version: Optional[int] = None
    requirements: FrozenSet[PolicyRequirement] = frozenset()

    @property
    def allowed(self) -> bool:
        return self.outcome == PolicyOutcome.ALLOWED


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AgeAndContestPolicyEngine:
    def __init__(self, db: Session):
        self.db = db

    # ---- age ---------------------------------------------------------------

    @staticmethod
    def calculate_age(date_of_birth: Union[date, datetime, None], on: date) -> Optional[int]:
        """Completed years at `on`, or None when the DOB is missing, in the future
        or implausible.

        A 29 February birthday is reached on 1 March in non-leap years (the later,
        more protective date).
        """
        if date_of_birth is None:
            return None
        dob = date_of_birth.date() if isinstance(date_of_birth, datetime) else date_of_birth
        if dob > on:
            return None
        age = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
        if age > MAX_PLAUSIBLE_AGE:
            return None
        return age

    @staticmethod
    def resolve_age_tier(age: Optional[int]) -> AgeTier:
        if age is None or age < 0:
            return AgeTier.UNKNOWN
        if age < TEEN_START_AGE:
            return AgeTier.UNDER_13
        if age < OLDER_TEEN_START_AGE:
            return AgeTier.TEEN_13_15
        if age < ADULT_TIER_START_AGE:
            return AgeTier.TEEN_16_17
        return AgeTier.ADULT_18_PLUS

    @staticmethod
    def dob_evidence_for_user(user) -> Optional[DobEvidence]:
        """Best DOB evidence currently available for a user.

        Only the profile date of birth exists today, and it is self-declared.
        KYC data is deliberately not used: KYC does not imply age assurance, and
        the source-selection rules belong to the Phase 3 age-assurance workflow.
        """
        dob = getattr(user, "date_of_birth", None)
        if dob is None:
            return None
        dob = dob.date() if isinstance(dob, datetime) else dob
        return DobEvidence(date_of_birth=dob, assurance_level=AgeAssuranceLevel.SELF_DECLARED_DOB)

    # ---- jurisdiction ------------------------------------------------------

    @staticmethod
    def resolve_jurisdiction(raw: Optional[str]) -> JurisdictionResolution:
        """Deterministic, read-only normalization of a stored country value.

        Accepts an exact ISO 3166-1 alpha-2 code, or an exact case-insensitive
        country name from the member-facing country list. Anything else (typos,
        abbreviations, cities, ambiguous text) stays UNRESOLVED. Stored data is
        never rewritten.
        """
        if raw is None:
            return JurisdictionResolution(JurisdictionStatus.UNKNOWN)
        text = re.sub(r"\s+", " ", str(raw)).strip()
        if not text:
            return JurisdictionResolution(JurisdictionStatus.UNKNOWN)
        if len(text) == 2 and text.isalpha() and text.upper() in ISO_COUNTRY_NAMES:
            return JurisdictionResolution(JurisdictionStatus.RESOLVED, text.upper(), "ISO_CODE")
        code = _NAME_TO_CODE.get(text.casefold())
        if code:
            return JurisdictionResolution(JurisdictionStatus.RESOLVED, code, "COUNTRY_NAME")
        return JurisdictionResolution(JurisdictionStatus.UNRESOLVED)

    # ---- policy ------------------------------------------------------------

    def resolve_policy(self, jurisdiction: Optional[str], on: date) -> PolicyResolution:
        """The ACTIVE policy in force for `jurisdiction` on date `on`: the ACTIVE
        version with the latest effective_date <= on. DRAFT and WITHDRAWN rows
        never apply, and future-dated versions do not apply early."""
        if not jurisdiction:
            return PolicyResolution(PolicyResolutionStatus.NOT_FOUND, None, on)
        rows: List[AgePolicy] = (
            self.db.query(AgePolicy)
            .filter(
                AgePolicy.jurisdiction == jurisdiction,
                AgePolicy.status == AgePolicyStatus.ACTIVE.value,
                AgePolicy.effective_date <= on,
            )
            .order_by(AgePolicy.effective_date.desc(), AgePolicy.id.asc())
            .limit(2)
            .all()
        )
        if not rows:
            return PolicyResolution(PolicyResolutionStatus.NOT_FOUND, jurisdiction, on)
        if len(rows) == 2 and rows[0].effective_date == rows[1].effective_date:
            # Guarded by a partial unique index; checked again here defensively.
            return PolicyResolution(PolicyResolutionStatus.CONFLICT, jurisdiction, on)
        row = rows[0]
        try:
            definition = policy_definition_from_row(row)
        except (ValidationError, ValueError, TypeError):
            return PolicyResolution(PolicyResolutionStatus.INVALID_DATA, jurisdiction, on, row.id, row.policy_version)
        return PolicyResolution(PolicyResolutionStatus.FOUND, jurisdiction, on, row.id, row.policy_version, definition)

    # ---- context & evaluation ---------------------------------------------

    def build_context(
        self,
        *,
        dob_evidence: Optional[DobEvidence],
        jurisdiction_value: Optional[str],
        on: date,
    ) -> AgeContext:
        jurisdiction = self.resolve_jurisdiction(jurisdiction_value)
        policy = self.resolve_policy(jurisdiction.code, on)
        age = self.calculate_age(dob_evidence.date_of_birth, on) if dob_evidence else None
        return AgeContext(
            evaluation_date=on,
            age_tier=self.resolve_age_tier(age),
            assurance_level=dob_evidence.assurance_level if (dob_evidence and age is not None) else None,
            jurisdiction=jurisdiction,
            policy=policy,
            _age=age,
        )

    def context_for_user(self, user, on: date) -> AgeContext:
        """Context from existing profile data (read-only; nothing is written)."""
        return self.build_context(
            dob_evidence=self.dob_evidence_for_user(user),
            jurisdiction_value=getattr(user, "country", None),
            on=on,
        )

    def evaluate(self, context: AgeContext, operation: PolicyOperation) -> PolicyDecision:
        """Evaluate one operation. Checks run in this order (first match wins):
        jurisdiction -> policy -> known age -> age threshold -> age assurance
        -> guardian consent -> ALLOWED.

        KYC is added as an independent requirement and never changes the age
        outcome. ALLOWED means the age/jurisdiction policy permits the
        operation; consumers must still satisfy every listed requirement.
        """
        tier = context.age_tier
        jcode = context.jurisdiction.code

        def decide(outcome: PolicyOutcome, reason: str, requirements=frozenset()) -> PolicyDecision:
            return PolicyDecision(
                operation=operation,
                outcome=outcome,
                reason=reason,
                age_tier=tier,
                jurisdiction=jcode,
                policy_id=context.policy.policy_id,
                policy_version=context.policy.policy_version,
                requirements=frozenset(requirements),
            )

        if context.jurisdiction.status == JurisdictionStatus.UNKNOWN:
            return decide(PolicyOutcome.UNKNOWN_JURISDICTION, "jurisdiction_missing")
        if context.jurisdiction.status == JurisdictionStatus.UNRESOLVED:
            return decide(PolicyOutcome.UNKNOWN_JURISDICTION, "jurisdiction_unresolved")

        resolution = context.policy
        if resolution.status == PolicyResolutionStatus.CONFLICT:
            return decide(PolicyOutcome.POLICY_CONFLICT, "multiple_effective_policies")
        if resolution.status == PolicyResolutionStatus.INVALID_DATA:
            return decide(PolicyOutcome.POLICY_CONFLICT, "invalid_policy_data")
        if not resolution.found:
            return decide(PolicyOutcome.UNSUPPORTED_JURISDICTION, "no_effective_policy")
        policy = resolution.policy

        requirements = set()
        if operation in policy.kyc_requirement.operations:
            requirements.add(PolicyRequirement.KYC)

        if not context.age_known:
            requirements.add(PolicyRequirement.AGE_ASSURANCE)
            return decide(PolicyOutcome.UNKNOWN_AGE, "age_unknown", requirements)

        threshold = getattr(policy, AGE_THRESHOLD_FIELD_BY_OPERATION[operation])
        if context._age < threshold:
            return decide(PolicyOutcome.DENIED, "below_minimum_age", requirements)

        required_level = policy.age_assurance_level.required_for(operation)
        if context.assurance_level is None or context.assurance_level.rank < required_level.rank:
            requirements.add(PolicyRequirement.AGE_ASSURANCE)
            return decide(PolicyOutcome.REQUIRES_AGE_ASSURANCE, "insufficient_age_assurance", requirements)

        if operation in policy.parental_consent_requirement.operations and context._age < policy.parental_consent_age:
            requirements.add(PolicyRequirement.GUARDIAN_CONSENT)
            return decide(PolicyOutcome.REQUIRES_GUARDIAN_CONSENT, "guardian_consent_required", requirements)

        return decide(PolicyOutcome.ALLOWED, "policy_permits", requirements)

    def permitted_content_ratings(self, context: AgeContext) -> FrozenSet[ContentRating]:
        """Ratings the effective policy permits for this context. With no usable
        policy nothing is guaranteed permitted (empty set). ADULT_18_PLUS
        additionally requires legal adulthood under the policy. PROHIBITED is
        never returned."""
        if not context.policy.found or context.jurisdiction.status != JurisdictionStatus.RESOLVED:
            return frozenset()
        ratings = set(context.policy.policy.permitted_content_ratings.by_tier.get(context.age_tier, []))
        ratings.discard(ContentRating.PROHIBITED)
        if not context.adult_content_eligible:
            ratings.discard(ContentRating.ADULT_18_PLUS)
        return frozenset(ratings)


def policy_definition_from_row(row: AgePolicy) -> AgePolicyDefinition:
    """Re-validate a stored row. Invalid stored data raises and fails closed."""
    return AgePolicyDefinition.model_validate(
        {
            "jurisdiction": row.jurisdiction,
            "effective_date": row.effective_date,
            **{name: getattr(row, name) for name in AGE_THRESHOLD_FIELD_BY_OPERATION.values()},
            "parental_consent_age": row.parental_consent_age,
            "adult_age": row.adult_age,
            "kyc_requirement": row.kyc_requirement,
            "age_assurance_level": row.age_assurance_level,
            "parental_consent_requirement": row.parental_consent_requirement,
            "permitted_content_ratings": row.permitted_content_ratings,
            "advertising_restrictions": row.advertising_restrictions,
            "profile_visibility_rules": row.profile_visibility_rules,
            "notes": row.notes,
        }
    )
