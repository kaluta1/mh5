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
    ALLOWED_WITH_GUARDIAN_CONSENT = "ALLOWED_WITH_GUARDIAN_CONSENT"  # Phase 4: completed after verified consent
    POLICY_NOT_ENFORCED = "POLICY_NOT_ENFORCED"          # transition: enforcement off, account allowed
    BELOW_MINIMUM_ACCOUNT_AGE = "BELOW_MINIMUM_ACCOUNT_AGE"
    PARENTAL_CONSENT_REQUIRED = "PARENTAL_CONSENT_REQUIRED"  # continued by the Phase 4 guardian workflow
    GUARDIAN_CONSENT_PENDING = "GUARDIAN_CONSENT_PENDING"    # Phase 4: pending registration awaiting guardian
    AGE_ASSURANCE_REQUIRED = "AGE_ASSURANCE_REQUIRED"
    UNRESOLVED_JURISDICTION = "UNRESOLVED_JURISDICTION"
    UNSUPPORTED_JURISDICTION = "UNSUPPORTED_JURISDICTION"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"            # conflicting/invalid policy data
    RETRY_LIMITED = "RETRY_LIMITED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

    @property
    def creates_account(self) -> bool:
        return self in (RegistrationDecision.ALLOWED, RegistrationDecision.ALLOWED_WITH_GUARDIAN_CONSENT,
                        RegistrationDecision.POLICY_NOT_ENFORCED)


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
    GUARDIAN_CONSENT_REQUESTED = "GUARDIAN_CONSENT_REQUESTED"
    GUARDIAN_RESPONDED = "GUARDIAN_RESPONDED"
    GUARDIAN_VERIFIED = "GUARDIAN_VERIFIED"
    GUARDIAN_REJECTED = "GUARDIAN_REJECTED"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    PENDING_REGISTRATION_COMPLETED = "PENDING_REGISTRATION_COMPLETED"
    PENDING_REGISTRATION_EXPIRED = "PENDING_REGISTRATION_EXPIRED"
    LEGACY_REVIEW_FLAGGED = "LEGACY_REVIEW_FLAGGED"
    CONTEST_ENTRY_TRANSITION = "CONTEST_ENTRY_TRANSITION"
    NOMINEE_CLAIM = "NOMINEE_CLAIM"
    CHILD_SAFETY_ESCALATION = "CHILD_SAFETY_ESCALATION"


ENFORCEMENT_ALL_JURISDICTIONS = "*"
# Operations whose jurisdiction-policy enforcement can be switched on. Phase 3 added
# ACCOUNT_CREATION; Phase 5 adds the contest-entry operations. Later phases add theirs.
ENFORCEABLE_OPERATIONS = frozenset({
    PolicyOperation.ACCOUNT_CREATION,
    PolicyOperation.PERSONAL_SUBMISSION,
    PolicyOperation.NOMINATION,
})


class DecisionBasis(str, enum.Enum):
    """Why a registration decision was reached. Keeps the platform safety baseline
    separate from jurisdiction/legal policy, so transition mode is never recorded
    as legal approval."""

    PLATFORM_BASELINE = "PLATFORM_BASELINE"            # s.2 default (under-13), not a legal conclusion
    JURISDICTION_POLICY = "JURISDICTION_POLICY"        # enforced, resolved AgePolicy decided
    TRANSITION_NOT_ENFORCED = "TRANSITION_NOT_ENFORCED"  # no enforced policy: allowed only provisionally
    CIRCUMVENTION_CONTROL = "CIRCUMVENTION_CONTROL"    # s.6 retry/risk controls


# ---------------------------------------------------------------------------
# Phase 4: guardian consent and teen privacy vocabulary
# (status names are implementation choices; the source defines the concepts,
#  s.13 GuardianConsent fields and s.14 consent areas, but not status names)
# ---------------------------------------------------------------------------

class GuardianConsentScope(str, enum.Enum):
    """Granular consent areas, one per item listed in s.14. Consent to one scope
    never implies another."""

    ACCOUNT_PARTICIPATION = "ACCOUNT_PARTICIPATION"
    PUBLIC_CREATIVE_DISPLAY = "PUBLIC_CREATIVE_DISPLAY"
    NAME_DISPLAY = "NAME_DISPLAY"
    CITY_COUNTRY_DISPLAY = "CITY_COUNTRY_DISPLAY"
    CONTEST_ENTRY = "CONTEST_ENTRY"
    STAGE_ADVANCEMENT = "STAGE_ADVANCEMENT"
    MEDIA_USE = "MEDIA_USE"
    PUBLICITY = "PUBLICITY"
    PRIZE_ACCEPTANCE = "PRIZE_ACCEPTANCE"
    FINANCIAL_PAYMENT = "FINANCIAL_PAYMENT"
    PROMOTIONAL_CAMPAIGNS = "PROMOTIONAL_CAMPAIGNS"


class GuardianRelationshipType(str, enum.Enum):
    PARENT = "PARENT"
    LEGAL_GUARDIAN = "LEGAL_GUARDIAN"


class GuardianVerificationStatus(str, enum.Enum):
    """Verification of one guardian's authority over one minor."""

    PENDING = "PENDING"                          # requested; the guardian has not responded
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"  # responded, but no accepted verification yet
    VERIFIED = "VERIFIED"                        # verified through an ACCEPTED method
    REJECTED = "REJECTED"                        # declined by the guardian or rejected by review
    REVOKED = "REVOKED"                          # authority withdrawn after verification
    EXPIRED = "EXPIRED"                          # request or verification lapsed


class GuardianContactConfirmation(str, enum.Enum):
    """A. CONTACT / INBOX CONTROL. It proves that someone controls the guardian contact
    address; it proves NOTHING about who that person is. It authenticates the
    guardian workflow (delivery, response) but can never establish guardian
    authority and never makes consent valid. Stored as GuardianRelationship.responded_at."""

    EMAIL_LINK = "EMAIL_LINK"   # the single-use emailed link was used


class GuardianVerificationMethod(str, enum.Enum):
    """B. GUARDIAN AUTHORITY VERIFICATION: a configured MyHigh5 guardian verification
    process that establishes VERIFIED. Only these methods can be configured in
    GUARDIAN_ACCEPTED_VERIFICATION_METHODS (empty = none, fail closed). No method is
    claimed to be legally sufficient in any or every jurisdiction; jurisdiction
    policy or legal review may later permit, strengthen, replace or disallow each
    one (s.13: "according to applicable law and risk").

    ADMIN_DOCUMENT_REVIEW: an authorized administrator attests that appropriate
    evidence was reviewed OUTSIDE the application. The application stores no
    document; the attestation, reviewer, time and note are recorded.
    """

    ADMIN_DOCUMENT_REVIEW = "ADMIN_DOCUMENT_REVIEW"


class ConsentStatus(str, enum.Enum):
    """withdrawal_status (s.13) plus grant state of one consent record."""

    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"


class PendingRegistrationStatus(str, enum.Enum):
    AWAITING_GUARDIAN = "AWAITING_GUARDIAN"
    APPROVED = "APPROVED"          # guardian verified + ACCOUNT_PARTICIPATION granted; waiting for the minor
    COMPLETED = "COMPLETED"        # the account was created (exactly once)
    DECLINED = "DECLINED"          # the guardian declined
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ConsentRequirement(str, enum.Enum):
    """Answer to 'is guardian consent needed/present for this scope now?'."""

    NOT_REQUIRED_ADULT = "NOT_REQUIRED_ADULT"            # legal adult under the policy (history kept)
    NOT_REQUIRED_BY_POLICY = "NOT_REQUIRED_BY_POLICY"    # minor at/above parental_consent_age
    SATISFIED = "SATISFIED"                              # valid verified consent for this scope
    REQUIRED_MISSING = "REQUIRED_MISSING"
    UNDETERMINED = "UNDETERMINED"                        # unknown age/jurisdiction/policy: treat as required


# ---------------------------------------------------------------------------
# Phase 5: contest age eligibility, personal submission and nomination
# (s.9-12, s.14, s.17, s.19). Names are implementation choices; the source
# defines the concepts (ContestAgeEligibility, the ContestCategory age policy,
# the nomination actors and the nomination workflow) but not status names.
# ---------------------------------------------------------------------------

class ContestAgeRuleStatus(str, enum.Enum):
    """Lifecycle of a contest/category age rule. Only ACTIVE rules apply. An
    ACTIVE rule is never edited in place: withdraw it and create a new version."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"


class ContestEntryKind(str, enum.Enum):
    PERSONAL_SUBMISSION = "PERSONAL_SUBMISSION"
    NOMINATION = "NOMINATION"


class EligibilityOutcome(str, enum.Enum):
    """ELIGIBLE_PUBLIC: every applicable requirement is met; the entry is active/public.
    HELD: at least one requirement is not met (missing DOB, age/contest/category
        rule, jurisdiction policy, guardian consent, rights, safety). The entry
        and the account are kept, the entry is not public, and it is
        re-evaluated automatically when the relevant information changes.

    Product rule: a requirement that is not met always means HOLD, never
    deletion or rejection of the account or the entry."""

    ELIGIBLE_PUBLIC = "ELIGIBLE_PUBLIC"
    HELD = "HELD"


class EntryExposureStatus(str, enum.Enum):
    """Workflow-level public exposure of one contest entry (Phase 5): may the
    entry be active/public at all. Whether a particular viewer may receive its
    media is a separate, later question (Phase 7)."""

    PUBLIC = "PUBLIC"                                  # eligible and active
    HELD = "HELD"                                      # created, not public, requirements pending
    BLOCKED = "BLOCKED"                                # not public; only an administrator can change it
    CHILD_SAFETY_ESCALATED = "CHILD_SAFETY_ESCALATED"  # s.11 high-severity path; never auto-released


class NominationWorkflowStep(str, enum.Enum):
    """s.12: Nomination -> Nominee notified -> Age status determined ->
    Parental/guardian approval -> Rights confirmed -> Content reviewed -> Activated.
    The step shown is the first one that is still open."""

    NOMINEE_CONTACT = "NOMINEE_CONTACT"      # waiting for the nominee to claim the nomination
    AGE_DETERMINATION = "AGE_DETERMINATION"
    GUARDIAN_CONSENT = "GUARDIAN_CONSENT"
    RIGHTS_CONFIRMATION = "RIGHTS_CONFIRMATION"
    SAFETY_REVIEW = "SAFETY_REVIEW"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class NomineeAgeDeclaration(str, enum.Enum):
    """What the NOMINATOR states about the nominee. This is a third-party
    attestation, never verification, and it is stored as such. It never
    releases a hold: a nomination stays held until the nominee claims it and
    every requirement is met. It only selects stricter handling (MINOR/UNKNOWN
    content checks) while the nominee is unclaimed."""

    ADULT = "ADULT"
    MINOR = "MINOR"
    UNKNOWN = "UNKNOWN"


class CreativeOwnerType(str, enum.Enum):
    SELF = "SELF"              # personal submission: the submitter owns the creative
    NOMINEE = "NOMINEE"        # nomination: the nominated person
    THIRD_PARTY = "THIRD_PARTY"
    UNKNOWN = "UNKNOWN"


class RightsStatus(str, enum.Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"


class SafetyStatus(str, enum.Enum):
    CLEAR = "CLEAR"                                    # no Phase 5 concern raised
    REVIEW_REQUIRED = "REVIEW_REQUIRED"                # a concern needs human review before activation
    REVIEWED_CLEAR = "REVIEWED_CLEAR"                  # an administrator cleared the concerns
    BLOCKED = "BLOCKED"
    CHILD_SAFETY_ESCALATED = "CHILD_SAFETY_ESCALATED"


class MetadataSafetyStatus(str, enum.Enum):
    """s.10: EXIF/GPS on hosted photographs and videos in a minor's entry."""

    NOT_REQUIRED = "NOT_REQUIRED"      # adult subject, or no hosted media
    SANITIZED = "SANITIZED"            # every hosted image was sanitized at upload
    UNRESOLVED = "UNRESOLVED"          # hosted video or unsanitized/unknown media: not publicly activatable


class SafetyConcern(str, enum.Enum):
    """Content-safety findings (s.10, s.11, s.15, s.18). One vocabulary for the
    Phase 5 hooks and the Phase 6 content-safety pipeline. Findings are codes
    only: the matched text itself is never stored or logged.

    CHILD_SEXUAL_CONTENT is a dedicated high-severity concern. It is never
    reduced to an ADULT_18_PLUS rating (s.11)."""

    # personal information / location (s.10, s.24)
    PII_EMAIL = "PII_EMAIL"
    PII_PHONE = "PII_PHONE"
    PRECISE_LOCATION = "PRECISE_LOCATION"
    HOME_ADDRESS = "HOME_ADDRESS"
    SCHOOL_INFORMATION = "SCHOOL_INFORMATION"
    CONTACT_INFORMATION = "CONTACT_INFORMATION"      # Phase 5 generic code (kept for stored records)
    PERSONAL_INFORMATION = "PERSONAL_INFORMATION"
    # child safety (s.11) - dedicated path
    CHILD_SEXUAL_CONTENT = "CHILD_SEXUAL_CONTENT"
    # content (s.10, s.15, s.18)
    SEXUAL_CONTENT = "SEXUAL_CONTENT"                # adult subject only; never used for a possible minor
    VIOLENCE = "VIOLENCE"
    GRAPHIC_VIOLENCE = "GRAPHIC_VIOLENCE"
    WEAPONS = "WEAPONS"
    DANGEROUS_BEHAVIOR = "DANGEROUS_BEHAVIOR"
    HATE = "HATE"
    OFFENSIVE_LANGUAGE = "OFFENSIVE_LANGUAGE"
    SPAM = "SPAM"
    THIRD_PARTY_RIGHTS = "THIRD_PARTY_RIGHTS"
    # pipeline state
    UNCLASSIFIED_MEDIA = "UNCLASSIFIED_MEDIA"        # automated classification could not cover the media
    METADATA_UNVERIFIED = "METADATA_UNVERIFIED"      # hosted image without verified EXIF/GPS sanitization


CHILD_SAFETY_ESCALATION_CONCERNS = frozenset({SafetyConcern.CHILD_SEXUAL_CONTENT})


# ---------------------------------------------------------------------------
# Phase 6: content classification and moderation (s.10, s.11, s.15-18)
# ---------------------------------------------------------------------------

class ModerationState(str, enum.Enum):
    """Content-moderation lifecycle of one governed entry. Separate from the
    Phase 5 participation HOLD: public exposure requires BOTH participation
    eligibility and APPROVED content (and no child-safety escalation)."""

    PENDING = "PENDING"                                # not yet evaluated/reviewed
    APPROVED = "APPROVED"                              # rated and approved for publication
    REVIEW_REQUIRED = "REVIEW_REQUIRED"                # held for human review
    PROHIBITED = "PROHIBITED"                          # must never be public
    CHILD_SAFETY_ESCALATED = "CHILD_SAFETY_ESCALATED"  # dedicated s.11 path; only an authorized resolver acts


class ClassifierStatus(str, enum.Enum):
    """Outcome of automated classification. Only COMPLETED can ever support an
    automated approval; anything else is fail-closed (human review)."""

    COMPLETED = "COMPLETED"        # every required dimension completed
    PARTIAL = "PARTIAL"            # some required dimension not run / not supported
    UNAVAILABLE = "UNAVAILABLE"    # provider needed but not configured/not permitted
    FAILED = "FAILED"              # a required check errored
    NOT_RUN = "NOT_RUN"


class CoverageDimension(str, enum.Enum):
    """Safety dimensions Phase 6 is responsible for. Each one is tracked
    separately so "nothing was detected" is never confused with "this was not
    evaluated"."""

    TEXT_PERSONAL_INFORMATION = "TEXT_PERSONAL_INFORMATION"  # PII, location, address, school
    TEXT_HARM = "TEXT_HARM"                                  # sexual, violence, dangerous behaviour
    TEXT_LANGUAGE = "TEXT_LANGUAGE"                          # profanity / spam (local rules)
    MEDIA_CONTENT = "MEDIA_CONTENT"                          # image/video content classification
    MEDIA_METADATA = "MEDIA_METADATA"                        # EXIF/GPS sanitization of hosted media


class CoverageStatus(str, enum.Enum):
    """Outcome of one safety dimension. Only COMPLETED_NO_FINDING and
    NOT_APPLICABLE can ever support an automated approval."""

    COMPLETED_NO_FINDING = "COMPLETED_NO_FINDING"
    COMPLETED_FINDING = "COMPLETED_FINDING"
    NOT_APPLICABLE = "NOT_APPLICABLE"      # nothing of this kind in the submission
    NOT_SUPPORTED = "NOT_SUPPORTED"        # present, but the local pipeline cannot evaluate it
    NOT_RUN = "NOT_RUN"                    # required check did not run (e.g. provider unavailable)
    FAILED = "FAILED"                      # the check errored


AUTO_APPROVABLE_COVERAGE = frozenset({CoverageStatus.COMPLETED_NO_FINDING, CoverageStatus.NOT_APPLICABLE})


class ChildSafetyResolution(str, enum.Enum):
    """Decision of an explicitly authorized child-safety reviewer. Neither value
    publishes anything: CONFIRMED is terminal (PROHIBITED); NO_CHILD_SAFETY_CONCERN
    only returns the content to ordinary review, where a moderator must still
    approve it separately."""

    CONFIRMED = "CONFIRMED"
    NO_CHILD_SAFETY_CONCERN = "NO_CHILD_SAFETY_CONCERN"


class MemberContentStatus(str, enum.Enum):
    """What the entry's owner may see about content review (no detection internals)."""

    APPROVED = "APPROVED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONTENT_HELD = "CONTENT_HELD"
    UPDATE_REQUIRED = "UPDATE_REQUIRED"
    PROHIBITED = "PROHIBITED"


# Permissions (role-based, app.models.user.Permission names).
PERMISSION_MODERATE_CONTENT = "moderate_content"
# Deliberately NOT implied by the 'all' wildcard or by is_admin: must be granted explicitly.
PERMISSION_CHILD_SAFETY_RESOLVE = "child_safety_resolve"


class NominationAgeScope(str, enum.Enum):
    """AgePolicy.nomination_age_applies_to: which nomination actor the policy's
    nomination_minimum_age applies to. Sections 1-32 do not say, so the policy
    author must state it explicitly; MyHigh5 never assumes it. A policy without
    it cannot be enforced for NOMINATION (entries are held)."""

    NOMINATOR = "NOMINATOR"
    NOMINEE = "NOMINEE"
    BOTH = "BOTH"


class ContestEligibilityReason(str, enum.Enum):
    """Machine-readable reasons why an entry is HELD. Safe for clients: they
    never carry a DOB, an exact age, a threshold or guardian details."""

    # age of an account holder
    AGE_REQUIRED = "AGE_REQUIRED"                          # no/unusable DOB: add a date of birth
    AGE_REVIEW_PENDING = "AGE_REVIEW_PENDING"
    BELOW_PLATFORM_MINIMUM = "BELOW_PLATFORM_MINIMUM"      # UNDER_13 (s.2 baseline)
    # contest / category rules
    BELOW_CONTEST_MINIMUM_AGE = "BELOW_CONTEST_MINIMUM_AGE"
    ABOVE_CONTEST_MAXIMUM_AGE = "ABOVE_CONTEST_MAXIMUM_AGE"
    AGE_TIER_NOT_ELIGIBLE = "AGE_TIER_NOT_ELIGIBLE"
    ADULT_ONLY_CATEGORY = "ADULT_ONLY_CATEGORY"
    MINOR_PARTICIPATION_NOT_ALLOWED = "MINOR_PARTICIPATION_NOT_ALLOWED"
    CONTEST_RULES_UNAVAILABLE = "CONTEST_RULES_UNAVAILABLE"
    # jurisdiction policy (blocking only where the operation is enforced)
    POLICY_BELOW_MINIMUM_AGE = "POLICY_BELOW_MINIMUM_AGE"
    POLICY_JURISDICTION_UNRESOLVED = "POLICY_JURISDICTION_UNRESOLVED"
    POLICY_UNSUPPORTED_JURISDICTION = "POLICY_UNSUPPORTED_JURISDICTION"
    POLICY_UNAVAILABLE = "POLICY_UNAVAILABLE"
    POLICY_AGE_ASSURANCE_REQUIRED = "POLICY_AGE_ASSURANCE_REQUIRED"
    POLICY_NOMINATION_SCOPE_UNDEFINED = "POLICY_NOMINATION_SCOPE_UNDEFINED"
    POLICY_NOT_ENFORCED = "POLICY_NOT_ENFORCED"            # informational: transition mode
    # guardian consent (Phase 4)
    GUARDIAN_CONSENT_REQUIRED = "GUARDIAN_CONSENT_REQUIRED"
    # nominee
    NOMINEE_UNCLAIMED = "NOMINEE_UNCLAIMED"                # the nominee has not claimed the nomination
    NOMINEE_DECLINED = "NOMINEE_DECLINED"
    NOMINEE_AGE_UNDETERMINED = "NOMINEE_AGE_UNDETERMINED"
    NOMINEE_DECLARED_MINOR = "NOMINEE_DECLARED_MINOR"
    # rights / safety / metadata hooks
    RIGHTS_CONFIRMATION_REQUIRED = "RIGHTS_CONFIRMATION_REQUIRED"
    SAFETY_REVIEW_REQUIRED = "SAFETY_REVIEW_REQUIRED"
    CHILD_SAFETY_ESCALATION = "CHILD_SAFETY_ESCALATION"
    METADATA_UNRESOLVED = "METADATA_UNRESOLVED"
    ADMIN_BLOCKED = "ADMIN_BLOCKED"
    # Phase 6 content gate
    CONTENT_REVIEW_REQUIRED = "CONTENT_REVIEW_REQUIRED"
    CONTENT_UPDATE_REQUIRED = "CONTENT_UPDATE_REQUIRED"
    CONTENT_PROHIBITED = "CONTENT_PROHIBITED"
    CONTENT_RATING_NOT_PERMITTED = "CONTENT_RATING_NOT_PERMITTED"


# Reasons that only inform (jurisdiction-policy enforcement is off for the
# operation); they never cause a hold and never release one.
INFORMATIONAL_ELIGIBILITY_REASONS = frozenset({
    ContestEligibilityReason.POLICY_NOT_ENFORCED,
})
