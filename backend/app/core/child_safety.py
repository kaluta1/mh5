"""Shared child/teen-safety vocabulary (MyHigh5 Child/Teen Safety requirement).

Values are plain strings so they can be stored in VARCHAR/JSON columns without
PostgreSQL enum types (same convention as app.models.business_model).
"""
from __future__ import annotations

import enum


class AgeTier(str, enum.Enum):
    """Default age structure (requirement section 2), plus UNKNOWN.

    UNKNOWN covers users without a reliable date of birth. It never receives adult
    treatment.
    """

    UNDER_13 = "UNDER_13"
    TEEN_13_15 = "TEEN_13_15"
    TEEN_16_17 = "TEEN_16_17"
    ADULT_18_PLUS = "ADULT_18_PLUS"
    UNKNOWN = "UNKNOWN"


MINOR_AGE_TIERS = frozenset({AgeTier.UNDER_13, AgeTier.TEEN_13_15, AgeTier.TEEN_16_17})


class ContentRating(str, enum.Enum):
    """Content age ratings (section 15). PROHIBITED is never permitted for anyone."""

    GENERAL = "GENERAL"
    TEEN_13_PLUS = "TEEN_13_PLUS"
    TEEN_16_PLUS = "TEEN_16_PLUS"
    ADULT_18_PLUS = "ADULT_18_PLUS"
    PROHIBITED = "PROHIBITED"


class AgeAssuranceLevel(str, enum.Enum):
    """Strength of the evidence behind a user's age (section 5), weakest first.

    SELF_DECLARED_DOB: date of birth entered by the user ("DOB + risk controls").
    AGE_VERIFIED: an age check confirming the age or an age-over-threshold result.
    IDENTITY_AND_AGE_VERIFIED: identity and age verification (e.g. prize payment,
    legally binding agreements).
    """

    SELF_DECLARED_DOB = "SELF_DECLARED_DOB"
    AGE_VERIFIED = "AGE_VERIFIED"
    IDENTITY_AND_AGE_VERIFIED = "IDENTITY_AND_AGE_VERIFIED"

    @property
    def rank(self) -> int:
        return _ASSURANCE_RANK[self]


_ASSURANCE_RANK = {
    AgeAssuranceLevel.SELF_DECLARED_DOB: 1,
    AgeAssuranceLevel.AGE_VERIFIED: 2,
    AgeAssuranceLevel.IDENTITY_AND_AGE_VERIFIED: 3,
}


class PolicyOperation(str, enum.Enum):
    """Operations with a dedicated age threshold in AgePolicy (section 3).

    Each value maps to exactly one AgePolicy threshold field (see
    AGE_THRESHOLD_FIELD_BY_OPERATION). Operations without a dedicated threshold
    field in the requirement (public publication, withdrawals, monetization,
    publicity) are left to the later phases that design them.
    """

    ACCOUNT_CREATION = "ACCOUNT_CREATION"
    INDEPENDENT_PARTICIPATION = "INDEPENDENT_PARTICIPATION"
    VOTING = "VOTING"
    NOMINATION = "NOMINATION"
    PERSONAL_SUBMISSION = "PERSONAL_SUBMISSION"
    LIVESTREAM = "LIVESTREAM"
    PRIZE_CONTRACT = "PRIZE_CONTRACT"
    PAYMENT = "PAYMENT"


AGE_THRESHOLD_FIELD_BY_OPERATION = {
    PolicyOperation.ACCOUNT_CREATION: "minimum_account_age",
    PolicyOperation.INDEPENDENT_PARTICIPATION: "minimum_independent_participation_age",
    PolicyOperation.VOTING: "voting_minimum_age",
    PolicyOperation.NOMINATION: "nomination_minimum_age",
    PolicyOperation.PERSONAL_SUBMISSION: "personal_submission_minimum_age",
    PolicyOperation.LIVESTREAM: "livestream_minimum_age",
    PolicyOperation.PRIZE_CONTRACT: "prize_contract_age",
    PolicyOperation.PAYMENT: "payment_minimum_age",
}


class AgePolicyStatus(str, enum.Enum):
    """AgePolicy lifecycle.

    DRAFT: editable, never used for evaluation.
    ACTIVE: in force from effective_date until a later ACTIVE version of the same
        jurisdiction takes effect. It stays resolvable for its historical period
        and is never edited in place; changes need a new version.
    WITHDRAWN: never used for evaluation. The row is kept for history.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"


class JurisdictionStatus(str, enum.Enum):
    RESOLVED = "RESOLVED"          # deterministic, trusted country code
    UNKNOWN = "UNKNOWN"            # no jurisdiction information at all
    UNRESOLVED = "UNRESOLVED"      # a value exists but cannot be normalized safely


class PolicyOutcome(str, enum.Enum):
    """Result of evaluating one operation. Only ALLOWED permits the operation."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    REQUIRES_AGE_ASSURANCE = "REQUIRES_AGE_ASSURANCE"
    REQUIRES_GUARDIAN_CONSENT = "REQUIRES_GUARDIAN_CONSENT"
    UNKNOWN_AGE = "UNKNOWN_AGE"
    UNKNOWN_JURISDICTION = "UNKNOWN_JURISDICTION"
    UNSUPPORTED_JURISDICTION = "UNSUPPORTED_JURISDICTION"
    POLICY_CONFLICT = "POLICY_CONFLICT"


class PolicyRequirement(str, enum.Enum):
    """Independent requirements a consumer must check separately (never implied)."""

    KYC = "KYC"
    GUARDIAN_CONSENT = "GUARDIAN_CONSENT"
    AGE_ASSURANCE = "AGE_ASSURANCE"


# ---------------------------------------------------------------------------
# Phase 3: registration, DOB provenance, review and circumvention vocabulary
# ---------------------------------------------------------------------------

class RegistrationDecision(str, enum.Enum):
    """Machine-readable outcome of the registration age gate (s.4, s.6)."""

    ALLOWED = "ALLOWED"
    POLICY_NOT_ENFORCED = "POLICY_NOT_ENFORCED"          # transition: enforcement off, account allowed
    BELOW_MINIMUM_ACCOUNT_AGE = "BELOW_MINIMUM_ACCOUNT_AGE"
    PARENTAL_CONSENT_REQUIRED = "PARENTAL_CONSENT_REQUIRED"  # continued by the Phase 4 guardian workflow
    AGE_ASSURANCE_REQUIRED = "AGE_ASSURANCE_REQUIRED"
    UNRESOLVED_JURISDICTION = "UNRESOLVED_JURISDICTION"
    UNSUPPORTED_JURISDICTION = "UNSUPPORTED_JURISDICTION"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"            # conflicting/invalid policy data
    RETRY_LIMITED = "RETRY_LIMITED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

    @property
    def creates_account(self) -> bool:
        return self in (RegistrationDecision.ALLOWED, RegistrationDecision.POLICY_NOT_ENFORCED)


class DobSource(str, enum.Enum):
    """How the stored date of birth was obtained. None of these implies verification."""

    LEGACY_PROFILE = "LEGACY_PROFILE"                    # existed before Phase 3 (implicit when no profile row)
    SELF_DECLARED_REGISTRATION = "SELF_DECLARED_REGISTRATION"
    SELF_DECLARED_PROFILE = "SELF_DECLARED_PROFILE"      # first capture after registration
    SELF_CORRECTION = "SELF_CORRECTION"                  # minor correction applied without review
    ADMIN_REVIEWED = "ADMIN_REVIEWED"                    # correction approved by an administrator
    ADMIN_CORRECTION = "ADMIN_CORRECTION"                # administrator-entered correction


class AgeReviewStatus(str, enum.Enum):
    """Escalation state (s.5): stronger verification or human review is needed."""

    NONE = "NONE"
    AGE_VERIFICATION_REQUIRED = "AGE_VERIFICATION_REQUIRED"
    AGE_REVIEW_REQUIRED = "AGE_REVIEW_REQUIRED"


class DobChangeStatus(str, enum.Enum):
    AUTO_APPLIED = "AUTO_APPLIED"      # same-tier self correction, applied and audited
    PENDING = "PENDING"                # material change waiting for review; not applied
    APPROVED = "APPROVED"              # applied after review
    REJECTED = "REJECTED"              # not applied
    ADMIN_APPLIED = "ADMIN_APPLIED"    # administrator correction


class AgeSafetyEventType(str, enum.Enum):
    AGE_GATE_ATTEMPT = "AGE_GATE_ATTEMPT"
    DOB_CAPTURED = "DOB_CAPTURED"
    DOB_CHANGED = "DOB_CHANGED"
    DOB_CHANGE_REQUESTED = "DOB_CHANGE_REQUESTED"
    DOB_CHANGE_REVIEWED = "DOB_CHANGE_REVIEWED"
    REVIEW_STATUS_CHANGED = "REVIEW_STATUS_CHANGED"
    TERMS_ACCEPTED = "TERMS_ACCEPTED"


ENFORCEMENT_ALL_JURISDICTIONS = "*"
# Operations whose enforcement can be switched on in Phase 3. Later phases add theirs.
ENFORCEABLE_OPERATIONS = frozenset({PolicyOperation.ACCOUNT_CREATION})


class DecisionBasis(str, enum.Enum):
    """Why a registration decision was reached. Keeps the platform safety baseline
    separate from jurisdiction/legal policy, so transition mode is never recorded
    as legal approval."""

    PLATFORM_BASELINE = "PLATFORM_BASELINE"            # s.2 default (under-13), not a legal conclusion
    JURISDICTION_POLICY = "JURISDICTION_POLICY"        # enforced, resolved AgePolicy decided
    TRANSITION_NOT_ENFORCED = "TRANSITION_NOT_ENFORCED"  # no enforced policy: allowed only provisionally
    CIRCUMVENTION_CONTROL = "CIRCUMVENTION_CONTROL"    # s.6 retry/risk controls
