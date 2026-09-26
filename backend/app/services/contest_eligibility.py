"""Contest age eligibility, personal submission and nomination (Child/Teen Safety
Phase 5: s.9-12, s.14, s.17, s.19, s.32).

This is the one place that decides whether a contest entry may be active/public.
It never decides whether a particular viewer may receive the entry's media:
that is Phase 7.

PRODUCT RULE: an unmet requirement means HOLD. The entry is created and kept,
the account is kept, the entry is not public (not listed, not votable, not in
seasons/TopHigh5), and it is re-evaluated automatically when the relevant
information changes (DOB added/corrected, review closed, guardian consent
granted/withdrawn/verified, nominee claim, rule change, admin review). When
everything is satisfied the hold is released; otherwise it stays. Nothing here
deletes or rejects an account or an entry.

Account eligibility is NOT contest eligibility (s.9). Holding an account,
having registered while jurisdiction enforcement was off, a verified KYC, or a
confirmed guardian email never makes anyone contest-eligible here.

Requirements (all must be met; each unmet one is a HOLD reason):

1. PLATFORM BASELINE (every mode, not a legal conclusion)
   - No/unusable DOB (UNKNOWN age): HOLD, AGE_REQUIRED; next step: add a date
     of birth through the existing audited DOB path. UNKNOWN is never treated as
     adult, no DOB is inferred or backfilled, and KYC data is never read.
   - UNDER_13: HOLD (s.2).
   - An open age review/verification escalation: HOLD until resolved.
2. CONTEST / CATEGORY RULES: Contest.min_age / Contest.max_age (existing
   columns, same meaning: participant age limits) plus the ACTIVE
   ContestAgeEligibility and CategoryAgePolicy rules for the jurisdiction ('*'
   unless a jurisdiction-specific rule exists). adult_only, content rating and
   minor_participation_allowed apply to every actor (s.17); min/max age and
   eligible_age_tiers apply to the person whose creative/identity is entered
   (submitter or nominee). Conflicting or invalid rules HOLD.
3. JURISDICTION POLICY (Phase 2 engine): authoritative where the operation
   (PERSONAL_SUBMISSION / NOMINATION) is switched on in child_safety_enforcement.
   Enforced: only ALLOWED (or consent-satisfied REQUIRES_GUARDIAN_CONSENT)
   passes; missing/unsupported/conflicting policy HOLDS. Where enforcement is
   off, POLICY_NOT_ENFORCED is recorded; that never releases a hold created by
   any other requirement and never waives guardian consent.
4. MINOR PROTECTIONS (every mode): a minor's entry is HELD until the Phase 4
   service reports valid, VERIFIED guardian consent for every scope the entry
   needs (s.14; one scope never implies another). Consent is only waived by a
   jurisdiction policy that is ENFORCED for the operation and says the minor is
   at/above parental_consent_age.
5. NOMINEE (s.12): the nominee is a separate person. A nomination is HELD until
   the nominee claims it with their own account (single-use claim link), and
   then until the nominee's own age, guardian consent (if a minor), rights and
   safety requirements are met. The nominator's age statement is an
   attestation only and never releases a hold. Neither the nominator, a
   sponsor nor the account holder ever becomes the nominee's guardian.
6. RIGHTS / SAFETY / METADATA HOOKS (s.10, s.11): Phase 5 hooks only, fed with
   the existing moderation results and a small deterministic PII detector.
   Sexual content with a minor or possibly-minor subject goes to the dedicated
   CHILD_SAFETY_ESCALATED path (never an ADULT_18_PLUS rating). Full
   classification is Phase 6.

nomination_minimum_age: Sections 1-32 do not say which nomination actor it
applies to. MyHigh5 does not decide that: each AgePolicy must state it
(nomination_age_applies_to = NOMINATOR / NOMINEE / BOTH). Where NOMINATION is
enforced and the effective policy does not state it, nominations are HELD
(POLICY_NOMINATION_SCOPE_UNDEFINED).

Age changes: contest min/max age is checked on every evaluation until the entry
is first activated (so a corrected or newly added DOB can release it); after
activation a birthday never removes the participant. Everything else (tier,
policy, consent, review state) is always recomputed from current data.

Nothing here touches payments, commissions, wallets, the Referral Pool, KYC
providers, votes or results.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Sequence, Set, Tuple

from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.child_safety import (
    CHILD_SAFETY_ESCALATION_CONCERNS,
    ENFORCEMENT_ALL_JURISDICTIONS,
    INFORMATIONAL_ELIGIBILITY_REASONS,
    MINOR_AGE_TIERS,
    AgeReviewStatus,
    AgeSafetyEventType,
    AgeTier,
    ConsentRequirement,
    ContentRating,
    ContestAgeRuleStatus,
    ContestEligibilityReason as R,
    ContestEntryKind,
    CreativeOwnerType,
    DecisionBasis,
    EligibilityOutcome,
    EntryExposureStatus,
    GuardianConsentScope,
    MetadataSafetyStatus,
    NominationAgeScope,
    NominationWorkflowStep,
    NomineeAgeDeclaration,
    PolicyOperation,
    PolicyOutcome,
    RightsStatus,
    SafetyConcern,
    SafetyStatus,
)
from app.models.accounting import AuditTrail
from app.models.age_safety import AgeSafetyEvent, UserAgeProfile
from app.models.contest import Contest
from app.models.contest_eligibility import CategoryAgePolicy, ContestAgeEligibility, ContestEntrySafety
from app.models.contests import Contestant
from app.models.media import Media
from app.models.user import User
from app.schemas.contest_eligibility import ContestAgeRuleDefinition
from app.services.age_gate import enforcement_enabled
from app.services.age_policy_engine import AgeAndContestPolicyEngine, AgeContext

ROLE_SUBMITTER = "SUBMITTER"
ROLE_NOMINATOR = "NOMINATOR"
ROLE_NOMINEE = "NOMINEE"

_RATING_MIN_TIER = {
    ContentRating.GENERAL: None,
    ContentRating.TEEN_13_PLUS: AgeTier.TEEN_13_15,
    ContentRating.TEEN_16_PLUS: AgeTier.TEEN_16_17,
    ContentRating.ADULT_18_PLUS: AgeTier.ADULT_18_PLUS,
}
_RATING_ORDER = [ContentRating.GENERAL, ContentRating.TEEN_13_PLUS, ContentRating.TEEN_16_PLUS,
                 ContentRating.ADULT_18_PLUS]
_TIER_ORDER = {AgeTier.UNDER_13: 0, AgeTier.TEEN_13_15: 1, AgeTier.TEEN_16_17: 2, AgeTier.ADULT_18_PLUS: 3}

_POLICY_HOLD_REASON = {
    PolicyOutcome.DENIED: R.POLICY_BELOW_MINIMUM_AGE,
    PolicyOutcome.REQUIRES_AGE_ASSURANCE: R.POLICY_AGE_ASSURANCE_REQUIRED,
    PolicyOutcome.UNKNOWN_AGE: R.AGE_REQUIRED,
    PolicyOutcome.UNKNOWN_JURISDICTION: R.POLICY_JURISDICTION_UNRESOLVED,
    PolicyOutcome.UNSUPPORTED_JURISDICTION: R.POLICY_UNSUPPORTED_JURISDICTION,
    PolicyOutcome.POLICY_CONFLICT: R.POLICY_UNAVAILABLE,
}

# Consent scopes an exposed minor needs before the entry may be public (s.14).
# STAGE_ADVANCEMENT is needed when the entry advances (geographic progression,
# Phase 8) and PRIZE_ACCEPTANCE/FINANCIAL_PAYMENT belong to Phase 10.
_EXPOSED_SCOPES = (
    GuardianConsentScope.CONTEST_ENTRY,
    GuardianConsentScope.PUBLIC_CREATIVE_DISPLAY,
    GuardianConsentScope.NAME_DISPLAY,
    GuardianConsentScope.CITY_COUNTRY_DISPLAY,
)
_NOMINATOR_SCOPES = (GuardianConsentScope.CONTEST_ENTRY,)

# Safe client messages: generic, never revealing tier, age, thresholds or review detail.
CLIENT_MESSAGES = {
    "AGE_REQUIRED": ("Your participation is on hold because your date of birth is missing from your account. "
                     "Please update your profile; we will check your entry again automatically."),
    "REVIEW": ("Your participation is on hold while your account information is reviewed. "
               "Please contact support if you have questions."),
    "NOMINEE": ("Your nomination was received and is on hold until the person you nominated confirms it. "
                "Share the claim link with them."),
    "PENDING": ("Your entry was received and is on hold. It will become visible automatically once the "
                "required checks are complete."),
}


# ---------------------------------------------------------------------------
# Contest / category rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EffectiveContestRules:
    minimum_age: Optional[int] = None
    maximum_age: Optional[int] = None
    eligible_age_tiers: Optional[frozenset] = None
    minor_participation_allowed: bool = True
    adult_only: bool = False
    parental_consent_required: bool = False
    publicity_consent_required: bool = False
    content_age_rating: Optional[ContentRating] = None
    unavailable: bool = False
    rule_ids: Tuple[str, ...] = ()

    @property
    def needs_exact_age(self) -> bool:
        return self.maximum_age is not None or (self.minimum_age is not None and self.minimum_age > 18)


def _active_rule(db: Session, model, scope_col, scope_id: int, jurisdiction: Optional[str]):
    """(row or None, unavailable). A jurisdiction-specific ACTIVE rule overrides '*'."""
    keys = [ENFORCEMENT_ALL_JURISDICTIONS] + ([jurisdiction] if jurisdiction else [])
    rows = (db.query(model).filter(scope_col == scope_id, model.status == ContestAgeRuleStatus.ACTIVE.value,
                                   model.jurisdiction.in_(keys)).all())
    specific = [r for r in rows if r.jurisdiction != ENFORCEMENT_ALL_JURISDICTIONS]
    chosen = specific or [r for r in rows if r.jurisdiction == ENFORCEMENT_ALL_JURISDICTIONS]
    if len(chosen) > 1:
        return None, True  # guarded by a partial unique index; checked again defensively
    return (chosen[0] if chosen else None), False


def rule_definition_from_row(row) -> ContestAgeRuleDefinition:
    """Re-validate a stored rule; invalid data raises (fails closed)."""
    return ContestAgeRuleDefinition.model_validate({
        name: getattr(row, name) for name in (
            "jurisdiction", "minimum_age", "maximum_age", "eligible_age_tiers", "minor_participation_allowed",
            "adult_only", "parental_consent_required", "publicity_consent_required", "content_age_rating",
            "prize_restrictions", "financial_restrictions", "notes")
    })


def resolve_contest_rules(db: Session, contest: Optional[Contest], jurisdiction: Optional[str]) -> EffectiveContestRules:
    """Combine the contest's legacy min/max age with its ACTIVE contest and
    category rules. The strictest value of each field wins."""
    if contest is None:
        return EffectiveContestRules()
    mins: List[int] = []
    maxs: List[int] = []
    tiers: Optional[Set[AgeTier]] = None
    minor_ok, adult_only, consent, publicity = True, False, False, False
    rating: Optional[ContentRating] = None
    ids: List[str] = []

    legacy_min, legacy_max = getattr(contest, "min_age", None), getattr(contest, "max_age", None)
    for value in (legacy_min, legacy_max):
        if value is not None and not (isinstance(value, int) and 0 <= value <= 120):
            return EffectiveContestRules(unavailable=True)
    if legacy_min is not None and legacy_max is not None and legacy_min > legacy_max:
        return EffectiveContestRules(unavailable=True)
    if legacy_min is not None:
        mins.append(legacy_min)
    if legacy_max is not None:
        maxs.append(legacy_max)

    sources = [(ContestAgeEligibility, ContestAgeEligibility.contest_id, contest.id, "contest")]
    if getattr(contest, "category_id", None):
        sources.append((CategoryAgePolicy, CategoryAgePolicy.category_id, contest.category_id, "category"))
    for model, col, scope_id, label in sources:
        row, conflict = _active_rule(db, model, col, scope_id, jurisdiction)
        if conflict:
            return EffectiveContestRules(unavailable=True)
        if row is None:
            continue
        try:
            d = rule_definition_from_row(row)
        except (ValidationError, ValueError, TypeError):
            return EffectiveContestRules(unavailable=True)
        ids.append(f"{label}:{row.id}:v{row.rule_version}")
        if d.minimum_age is not None:
            mins.append(d.minimum_age)
        if d.maximum_age is not None:
            maxs.append(d.maximum_age)
        if d.eligible_age_tiers:
            tiers = set(d.eligible_age_tiers) if tiers is None else tiers & set(d.eligible_age_tiers)
        minor_ok = minor_ok and d.minor_participation_allowed
        adult_only = adult_only or d.adult_only
        consent = consent or d.parental_consent_required
        publicity = publicity or d.publicity_consent_required
        if d.content_age_rating is not None and (
                rating is None or _RATING_ORDER.index(d.content_age_rating) > _RATING_ORDER.index(rating)):
            rating = d.content_age_rating

    minimum = max(mins) if mins else None
    maximum = min(maxs) if maxs else None
    if minimum is not None and maximum is not None and minimum > maximum:
        return EffectiveContestRules(unavailable=True)
    if rating == ContentRating.ADULT_18_PLUS:
        adult_only = True
    if adult_only:
        minor_ok = False
    return EffectiveContestRules(minimum, maximum, frozenset(tiers) if tiers is not None else None, minor_ok,
                                 adult_only, consent, publicity, rating, False, tuple(ids))


# ---------------------------------------------------------------------------
# Safety / PII / metadata hooks (Phase 5 only; Phase 6 replaces the detectors)
# ---------------------------------------------------------------------------

_TEXT_PATTERNS = (
    (SafetyConcern.CONTACT_INFORMATION, re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    (SafetyConcern.CONTACT_INFORMATION, re.compile(r"(?:\+?\d[\s().-]?){8,}\d")),
    (SafetyConcern.PRECISE_LOCATION, re.compile(r"-?\d{1,2}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}")),
    (SafetyConcern.HOME_ADDRESS, re.compile(
        r"\b\d{1,5}\s+(?:[A-Za-z]+\s){0,3}(?:street|st\.|avenue|ave\.?|road|rd\.?|lane|boulevard|blvd|drive|"
        r"rue|calle|avenida|strasse|straße)\b", re.IGNORECASE)),
    (SafetyConcern.SCHOOL_INFORMATION, re.compile(
        r"\b(?:school|high\s+school|primary\s+school|secondary\s+school|middle\s+school|academy|"
        r"école|ecole|lycée|lycee|collège|escuela|colegio)\b", re.IGNORECASE)),
)


def detect_text_concerns(text: Optional[str]) -> Set[SafetyConcern]:
    """Deterministic Phase 5 PII hook for a minor's (or possibly-minor) entry text."""
    found: Set[SafetyConcern] = set()
    for concern, pattern in _TEXT_PATTERNS:
        if text and pattern.search(text):
            found.add(concern)
    return found


def concerns_from_moderation(results: Iterable, *, possibly_minor_subject: bool) -> Set[SafetyConcern]:
    """Map existing ContentModerationService results to Phase 5 concerns. Sexual
    content with a possibly-minor subject is CHILD_SEXUAL_CONTENT (s.11)."""
    found: Set[SafetyConcern] = set()
    for result in results or ():
        for flag in getattr(result, "flags", None) or ():
            kind = getattr(getattr(flag, "type", None), "value", getattr(flag, "type", None))
            if kind == "adult" and possibly_minor_subject:
                found.add(SafetyConcern.CHILD_SEXUAL_CONTENT)
            elif kind in ("violence", "gore", "weapons"):
                found.add(SafetyConcern.VIOLENCE)
            elif kind == "drugs":
                found.add(SafetyConcern.DANGEROUS_BEHAVIOR)
    return found


def _refs(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = [raw]
    if not isinstance(parsed, list):
        parsed = [parsed]
    return [str(x).strip() for x in parsed if str(x).strip()]


def _hosted_media(db: Session, ref: str) -> Tuple[bool, Optional[Media]]:
    """(is_hosted_by_myhigh5, Media row if resolvable)."""
    if ref.isdigit():
        return True, db.query(Media).filter(Media.id == int(ref)).first()
    if "/api/v1/media/" in ref:  # MyHigh5-served file (relative or absolute URL)
        path = ref[ref.index("/api/v1/media/"):]
        return True, db.query(Media).filter(Media.url.in_([ref, path])).first()
    if ref.startswith(("http://", "https://")):
        media = db.query(Media).filter(Media.url == ref).first()
        return (True, media) if media is not None else (False, None)  # external link (e.g. YouTube)
    return True, None  # unknown reference form: treat as hosted and unresolved (fail safe)


def metadata_status_for(db: Session, image_media_ids: Optional[str], video_media_ids: Optional[str]) -> MetadataSafetyStatus:
    """s.10 for a minor's entry: every hosted image must have been sanitized at
    upload; hosted video cannot be stripped in Phase 5. External links (e.g.
    YouTube) are not hosted by MyHigh5."""
    hosted = False
    for ref in _refs(image_media_ids):
        is_hosted, media = _hosted_media(db, ref)
        if not is_hosted:
            continue
        hosted = True
        if media is None or media.metadata_sanitized_at is None:
            return MetadataSafetyStatus.UNRESOLVED
    for ref in _refs(video_media_ids):
        is_hosted, _ = _hosted_media(db, ref)
        if is_hosted:
            return MetadataSafetyStatus.UNRESOLVED
    return MetadataSafetyStatus.SANITIZED if hosted else MetadataSafetyStatus.NOT_REQUIRED


def _has_hosted_media(db: Session, image_media_ids: Optional[str], video_media_ids: Optional[str]) -> bool:
    return any(_hosted_media(db, ref)[0] for ref in _refs(image_media_ids) + _refs(video_media_ids))


# ---------------------------------------------------------------------------
# Decision objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EntryInputs:
    """What the entry contains (used by the hooks)."""

    title: Optional[str] = None
    description: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    moderation_results: Tuple = ()
    extra_concerns: frozenset = frozenset()   # admin-flagged or synthetic signals


@dataclass
class _Assessment:
    unmet: List[R] = field(default_factory=list)
    holds: List[R] = field(default_factory=list)
    info: List[R] = field(default_factory=list)
    missing_scopes: List[GuardianConsentScope] = field(default_factory=list)
    tier: Optional[AgeTier] = None
    determined_adult: bool = False
    possibly_minor: bool = True
    age_window_ok: bool = True
    enforced: bool = False
    baseline_hold: bool = False
    jurisdiction: Optional[str] = None
    policy_id: Optional[int] = None
    policy_version: Optional[int] = None
    guardian_relationship_id: Optional[int] = None


@dataclass(frozen=True)
class ContestEntryDecision:
    outcome: EligibilityOutcome
    reasons: Tuple[R, ...]
    exposure: EntryExposureStatus
    missing_consent_scopes: Tuple[GuardianConsentScope, ...] = ()
    basis: DecisionBasis = DecisionBasis.TRANSITION_NOT_ENFORCED
    enforced: bool = False
    subject_age_tier: Optional[AgeTier] = None
    jurisdiction: Optional[str] = None
    policy_id: Optional[int] = None
    policy_version: Optional[int] = None
    rights_status: RightsStatus = RightsStatus.NOT_REQUIRED
    safety_status: SafetyStatus = SafetyStatus.CLEAR
    safety_concerns: Tuple[SafetyConcern, ...] = ()
    metadata_status: MetadataSafetyStatus = MetadataSafetyStatus.NOT_REQUIRED
    workflow_step: Optional[NominationWorkflowStep] = None
    age_window_ok: bool = True
    guardian_relationship_id: Optional[int] = None
    creative_owner_type: CreativeOwnerType = CreativeOwnerType.SELF
    # True unless the exposed person is a determined adult or a nominee the
    # nominator declared an adult (the latter only affects which hooks run).
    subject_possibly_minor: bool = True

    @property
    def public(self) -> bool:
        return self.exposure == EntryExposureStatus.PUBLIC

    def client_payload(self) -> dict:
        """Safe for the member: codes, a generic message and the next step only.
        The internal child-safety escalation code is never shown."""
        codes = [r.value for r in self.reasons if r != R.CHILD_SAFETY_ESCALATION]
        if self.public:
            key, step = None, None
        elif R.AGE_REQUIRED in self.reasons:
            key, step = "AGE_REQUIRED", "ADD_DATE_OF_BIRTH"
        elif R.AGE_REVIEW_PENDING in self.reasons:
            key, step = "REVIEW", "CONTACT_SUPPORT"
        elif R.NOMINEE_UNCLAIMED in self.reasons:
            key, step = "NOMINEE", "SHARE_CLAIM_LINK"
        elif R.GUARDIAN_CONSENT_REQUIRED in self.reasons:
            key, step = "PENDING", "GUARDIAN_CONSENT"
        else:
            key, step = "PENDING", "AWAIT_REVIEW"
        return {"outcome": self.outcome.value, "reason_codes": codes, "message": CLIENT_MESSAGES.get(key),
                "next_step": step}


def _uniq(items: Iterable) -> Tuple:
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)


# ---------------------------------------------------------------------------
# Actor assessment
# ---------------------------------------------------------------------------

def _profile(db: Session, user: User) -> Optional[UserAgeProfile]:
    return db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()


_POLICY_AVAILABILITY_OUTCOMES = (PolicyOutcome.UNKNOWN_JURISDICTION, PolicyOutcome.UNSUPPORTED_JURISDICTION,
                                 PolicyOutcome.POLICY_CONFLICT)


def _nomination_scope_covers(ctx: AgeContext, role: str) -> Optional[bool]:
    """Does the effective policy's nomination_minimum_age apply to this actor?
    None = the policy does not say (never assumed)."""
    scope = getattr(ctx.policy.policy, "nomination_age_applies_to", None) if ctx.policy.found else None
    if scope is None:
        return None
    scope = NominationAgeScope(scope)
    return scope == NominationAgeScope.BOTH or scope.value == role


def _apply_policy(db: Session, a: _Assessment, ctx: AgeContext, operation: PolicyOperation, role: str) -> bool:
    """Layer 3. Returns True when an ENFORCED policy requires guardian consent."""
    engine = AgeAndContestPolicyEngine(db)
    decision = engine.evaluate(ctx, operation)
    enforced = enforcement_enabled(db, operation, ctx.jurisdiction.code)
    a.enforced = a.enforced or enforced
    if a.policy_id is None:
        a.policy_id, a.policy_version = decision.policy_id, decision.policy_version
    if not enforced:
        a.info.append(R.POLICY_NOT_ENFORCED)
        return False
    if operation == PolicyOperation.NOMINATION and decision.outcome not in _POLICY_AVAILABILITY_OUTCOMES:
        covered = _nomination_scope_covers(ctx, role)
        if covered is None:
            a.unmet.append(R.POLICY_NOMINATION_SCOPE_UNDEFINED)
            return False
        if not covered:
            # The policy explicitly does not apply its nomination rules to this
            # actor; the platform baseline and minor protections still apply.
            return False
    if decision.outcome == PolicyOutcome.ALLOWED:
        return False
    if decision.outcome == PolicyOutcome.REQUIRES_GUARDIAN_CONSENT:
        return True
    a.unmet.append(_POLICY_HOLD_REASON[decision.outcome])
    return False


def _consent(db: Session, a: _Assessment, user: User, ctx: AgeContext, scopes: Sequence[GuardianConsentScope], *,
             rules: EffectiveContestRules, policy_requires: bool, today: date, now: datetime) -> None:
    """Layer 4 via the Phase 4 service (check_consent through consent_requirement)."""
    from app.services.guardian_consent import consent_requirement

    for scope in scopes:
        requirement, check = consent_requirement(db, user, scope, on=today, at=now)
        if check.valid:
            a.guardian_relationship_id = a.guardian_relationship_id or check.relationship_id
            continue
        waived = (requirement == ConsentRequirement.NOT_REQUIRED_ADULT
                  or (requirement == ConsentRequirement.NOT_REQUIRED_BY_POLICY and a.enforced
                      and not policy_requires))
        if waived and not rules.parental_consent_required:
            continue
        a.missing_scopes.append(scope)
    if a.missing_scopes:
        a.holds.append(R.GUARDIAN_CONSENT_REQUIRED)


def assess_account(db: Session, user: User, *, role: str, operation: PolicyOperation, rules: EffectiveContestRules,
                   today: date, now: datetime, consent_scopes: Sequence[GuardianConsentScope] = (),
                   check_age_window: bool = True) -> _Assessment:
    a = _Assessment()
    profile = _profile(db, user)
    ctx = AgeAndContestPolicyEngine(db).context_for_user(user, today, profile)
    a.tier, a.jurisdiction = ctx.age_tier, ctx.jurisdiction.code
    exposed = role in (ROLE_SUBMITTER, ROLE_NOMINEE)

    # Layer 1: platform baseline.
    if profile is not None and (profile.review_status or AgeReviewStatus.NONE.value) != AgeReviewStatus.NONE.value:
        a.unmet.append(R.AGE_REVIEW_PENDING)
        a.baseline_hold = True
    if ctx.age_tier == AgeTier.UNKNOWN:
        # Missing DOB = HOLD. UNKNOWN is never treated as adult (or as a minor).
        a.unmet.append(R.NOMINEE_AGE_UNDETERMINED if role == ROLE_NOMINEE else R.AGE_REQUIRED)
        a.baseline_hold = True
        return a
    if ctx.age_tier == AgeTier.UNDER_13:
        a.unmet.append(R.BELOW_PLATFORM_MINIMUM)
        a.baseline_hold = True
        return a
    legal_minor = ctx.age_tier in MINOR_AGE_TIERS or (ctx.policy.found and not ctx.legal_adult)
    a.determined_adult = not legal_minor
    a.possibly_minor = legal_minor

    # Layer 2: contest / category rules.
    if rules.unavailable:
        a.unmet.append(R.CONTEST_RULES_UNAVAILABLE)
    if rules.adult_only and legal_minor:
        a.unmet.append(R.ADULT_ONLY_CATEGORY)
    elif legal_minor and not rules.minor_participation_allowed:
        a.unmet.append(R.MINOR_PARTICIPATION_NOT_ALLOWED)
    min_tier = _RATING_MIN_TIER.get(rules.content_age_rating) if rules.content_age_rating else None
    if min_tier is not None and _TIER_ORDER[ctx.age_tier] < _TIER_ORDER[min_tier]:
        a.unmet.append(R.AGE_TIER_NOT_ELIGIBLE)
    if exposed:
        if rules.eligible_age_tiers is not None and ctx.age_tier not in rules.eligible_age_tiers:
            a.unmet.append(R.AGE_TIER_NOT_ELIGIBLE)
        if check_age_window:
            if rules.minimum_age is not None and ctx._age < rules.minimum_age:
                a.unmet.append(R.BELOW_CONTEST_MINIMUM_AGE)
                a.age_window_ok = False
            if rules.maximum_age is not None and ctx._age > rules.maximum_age:
                a.unmet.append(R.ABOVE_CONTEST_MAXIMUM_AGE)
                a.age_window_ok = False

    # Layer 3: jurisdiction policy.
    policy_requires = _apply_policy(db, a, ctx, operation, role)

    # Layer 4: minor protections.
    if legal_minor or policy_requires:
        _consent(db, a, user, ctx, consent_scopes, rules=rules, policy_requires=policy_requires,
                 today=today, now=now)
    return a


def assess_unclaimed_nominee(db: Session, declaration: Optional[NomineeAgeDeclaration], *,
                             rules: EffectiveContestRules, nominator_jurisdiction: Optional[str],
                             declined: bool = False) -> _Assessment:
    """Nominee who has not claimed the nomination: always HELD. The nominator's
    statement only adds stricter reasons; it never releases the hold."""
    a = _Assessment(jurisdiction=nominator_jurisdiction)
    declaration = declaration or NomineeAgeDeclaration.UNKNOWN
    a.unmet.append(R.NOMINEE_DECLINED if declined else R.NOMINEE_UNCLAIMED)
    if rules.unavailable:
        a.unmet.append(R.CONTEST_RULES_UNAVAILABLE)
    if declaration == NomineeAgeDeclaration.MINOR:
        if rules.adult_only:
            a.unmet.append(R.ADULT_ONLY_CATEGORY)
        elif not rules.minor_participation_allowed:
            a.unmet.append(R.MINOR_PARTICIPATION_NOT_ALLOWED)
        a.unmet += [R.NOMINEE_DECLARED_MINOR, R.GUARDIAN_CONSENT_REQUIRED]
    elif declaration == NomineeAgeDeclaration.UNKNOWN:
        a.unmet.append(R.NOMINEE_AGE_UNDETERMINED)
    else:
        # Stated adult: only changes which content hooks run while unclaimed.
        a.possibly_minor = False
        if rules.eligible_age_tiers is not None and AgeTier.ADULT_18_PLUS not in rules.eligible_age_tiers:
            a.unmet.append(R.AGE_TIER_NOT_ELIGIBLE)
    return a


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def _hooks(db: Session, subject: _Assessment, inputs: EntryInputs, *, kind: ContestEntryKind,
           stored_safety: Optional[SafetyStatus] = None, stored_rights: Optional[RightsStatus] = None
           ) -> Tuple[Set[SafetyConcern], SafetyStatus, RightsStatus, MetadataSafetyStatus, List[R], bool]:
    """Layer 6. Returns (concerns, safety, rights, metadata, hold reasons, escalate)."""
    possibly_minor = subject.possibly_minor
    concerns: Set[SafetyConcern] = set(inputs.extra_concerns)
    concerns |= concerns_from_moderation(inputs.moderation_results, possibly_minor_subject=possibly_minor)
    if possibly_minor:
        concerns |= detect_text_concerns(" ".join(x for x in (inputs.title, inputs.description) if x))
    else:
        # Adults: only admin/synthetic signals and rights concerns; existing moderation is unchanged.
        concerns = {c for c in concerns if c in (SafetyConcern.THIRD_PARTY_RIGHTS,)
                    or c in inputs.extra_concerns}

    holds: List[R] = []
    escalate = bool(concerns & CHILD_SAFETY_ESCALATION_CONCERNS) or stored_safety == SafetyStatus.CHILD_SAFETY_ESCALATED
    if escalate:
        safety = SafetyStatus.CHILD_SAFETY_ESCALATED
        holds.append(R.CHILD_SAFETY_ESCALATION)
    elif stored_safety == SafetyStatus.BLOCKED:
        safety = SafetyStatus.BLOCKED
        holds.append(R.ADMIN_BLOCKED)
    elif stored_safety == SafetyStatus.REVIEWED_CLEAR:
        safety = SafetyStatus.REVIEWED_CLEAR
    elif concerns - {SafetyConcern.THIRD_PARTY_RIGHTS}:
        safety = SafetyStatus.REVIEW_REQUIRED
        holds.append(R.SAFETY_REVIEW_REQUIRED)
    else:
        safety = SafetyStatus.CLEAR

    if stored_rights in (RightsStatus.CONFIRMED, RightsStatus.DISPUTED):
        rights = stored_rights
    elif SafetyConcern.THIRD_PARTY_RIGHTS in concerns or kind == ContestEntryKind.NOMINATION:
        # A nomination uses someone else's creative: rights stay pending until the
        # nominee (an adult, by claiming) or an administrator confirms them.
        rights = RightsStatus.PENDING
    else:
        rights = RightsStatus.NOT_REQUIRED
    if rights in (RightsStatus.PENDING, RightsStatus.DISPUTED):
        holds.append(R.RIGHTS_CONFIRMATION_REQUIRED)

    metadata = MetadataSafetyStatus.NOT_REQUIRED
    if possibly_minor:
        metadata = metadata_status_for(db, inputs.image_media_ids, inputs.video_media_ids)
        if metadata == MetadataSafetyStatus.UNRESOLVED:
            holds.append(R.METADATA_UNRESOLVED)
    return concerns, safety, rights, metadata, holds, escalate


def _workflow_step(kind: ContestEntryKind, reasons: Set[R], exposure: EntryExposureStatus,
                   nominee_linked: bool) -> Optional[NominationWorkflowStep]:
    if kind != ContestEntryKind.NOMINATION:
        return None
    if exposure in (EntryExposureStatus.BLOCKED, EntryExposureStatus.CHILD_SAFETY_ESCALATED):
        return NominationWorkflowStep.BLOCKED
    if not nominee_linked:
        return NominationWorkflowStep.NOMINEE_CONTACT
    if reasons & {R.NOMINEE_AGE_UNDETERMINED, R.AGE_REVIEW_PENDING}:
        return NominationWorkflowStep.AGE_DETERMINATION
    if R.GUARDIAN_CONSENT_REQUIRED in reasons:
        return NominationWorkflowStep.GUARDIAN_CONSENT
    if R.RIGHTS_CONFIRMATION_REQUIRED in reasons:
        return NominationWorkflowStep.RIGHTS_CONFIRMATION
    if reasons & {R.SAFETY_REVIEW_REQUIRED, R.METADATA_UNRESOLVED}:
        return NominationWorkflowStep.SAFETY_REVIEW
    return NominationWorkflowStep.ACTIVE if exposure == EntryExposureStatus.PUBLIC else NominationWorkflowStep.SAFETY_REVIEW


def _compose(kind: ContestEntryKind, parts: Sequence[_Assessment], subject: _Assessment, hooks, *,
             nominee_linked: bool, owner: CreativeOwnerType) -> ContestEntryDecision:
    concerns, safety, rights, metadata, hook_holds, escalate = hooks
    unmet = _uniq(r for p in parts for r in p.unmet)
    holds = _uniq([r for p in parts for r in p.holds] + hook_holds)
    info = _uniq(r for p in parts for r in p.info)
    scopes = _uniq(s for p in parts for s in p.missing_scopes)
    if escalate:
        # s.11: the dedicated high-severity path wins over everything, so the
        # material is preserved (non-public) for specialized review.
        outcome, exposure = EligibilityOutcome.HELD, EntryExposureStatus.CHILD_SAFETY_ESCALATED
    elif safety == SafetyStatus.BLOCKED:
        outcome, exposure = EligibilityOutcome.HELD, EntryExposureStatus.BLOCKED
    elif unmet or holds:
        outcome, exposure = EligibilityOutcome.HELD, EntryExposureStatus.HELD
    else:
        outcome, exposure = EligibilityOutcome.ELIGIBLE_PUBLIC, EntryExposureStatus.PUBLIC
    enforced = any(p.enforced for p in parts)
    if any(p.baseline_hold for p in parts):
        basis = DecisionBasis.PLATFORM_BASELINE
    elif enforced:
        basis = DecisionBasis.JURISDICTION_POLICY
    else:
        basis = DecisionBasis.TRANSITION_NOT_ENFORCED
    reasons = unmet + holds + tuple(r for r in info if r in INFORMATIONAL_ELIGIBILITY_REASONS)
    return ContestEntryDecision(
        outcome=outcome, reasons=_uniq(reasons), exposure=exposure, missing_consent_scopes=scopes, basis=basis,
        enforced=enforced, subject_age_tier=subject.tier, jurisdiction=subject.jurisdiction or parts[0].jurisdiction,
        policy_id=subject.policy_id or parts[0].policy_id, policy_version=subject.policy_version or parts[0].policy_version,
        rights_status=rights, safety_status=safety, safety_concerns=tuple(sorted(concerns, key=lambda c: c.value)),
        metadata_status=metadata,
        workflow_step=_workflow_step(kind, set(unmet + holds), exposure, nominee_linked),
        age_window_ok=all(p.age_window_ok for p in parts),
        guardian_relationship_id=subject.guardian_relationship_id, creative_owner_type=owner,
        subject_possibly_minor=subject.possibly_minor)


def _exposed_scopes(db: Session, rules: EffectiveContestRules, inputs: EntryInputs) -> Tuple[GuardianConsentScope, ...]:
    scopes = list(_EXPOSED_SCOPES)
    if _has_hosted_media(db, inputs.image_media_ids, inputs.video_media_ids):
        scopes.append(GuardianConsentScope.MEDIA_USE)
    if rules.publicity_consent_required:
        scopes.append(GuardianConsentScope.PUBLICITY)
    return tuple(scopes)


def evaluate_personal_submission(db: Session, user: User, contest: Optional[Contest], inputs: EntryInputs, *,
                                 today: date, now: datetime, check_age_window: bool = True,
                                 stored: Optional[ContestEntrySafety] = None) -> ContestEntryDecision:
    subject_jur = AgeAndContestPolicyEngine.resolve_jurisdiction(getattr(user, "country", None))
    rules = resolve_contest_rules(db, contest, subject_jur.code)
    a = assess_account(db, user, role=ROLE_SUBMITTER, operation=PolicyOperation.PERSONAL_SUBMISSION, rules=rules,
                       today=today, now=now, consent_scopes=_exposed_scopes(db, rules, inputs),
                       check_age_window=check_age_window)
    hooks = _hooks(db, a, inputs, kind=ContestEntryKind.PERSONAL_SUBMISSION,
                   stored_safety=SafetyStatus(stored.safety_status) if stored else None,
                   stored_rights=RightsStatus(stored.rights_status) if stored else None)
    return _compose(ContestEntryKind.PERSONAL_SUBMISSION, [a], a, hooks, nominee_linked=False,
                    owner=CreativeOwnerType.SELF)


def evaluate_nomination(db: Session, nominator: User, contest: Optional[Contest], inputs: EntryInputs, *,
                        nominee_age_declaration: Optional[NomineeAgeDeclaration], today: date, now: datetime,
                        nominee_user: Optional[User] = None, check_age_window: bool = True,
                        stored: Optional[ContestEntrySafety] = None, declined: bool = False) -> ContestEntryDecision:
    """Two separate people: the nominator (acting) and the nominee (exposed).
    The nominator is never treated as the nominee's guardian."""
    nom_jur = AgeAndContestPolicyEngine.resolve_jurisdiction(getattr(nominator, "country", None))
    rules = resolve_contest_rules(db, contest, nom_jur.code)
    nominator_a = assess_account(db, nominator, role=ROLE_NOMINATOR, operation=PolicyOperation.NOMINATION,
                                 rules=rules, today=today, now=now, consent_scopes=_NOMINATOR_SCOPES)
    if nominee_user is not None:
        nominee_rules = resolve_contest_rules(
            db, contest, AgeAndContestPolicyEngine.resolve_jurisdiction(getattr(nominee_user, "country", None)).code)
        nominee_a = assess_account(db, nominee_user, role=ROLE_NOMINEE, operation=PolicyOperation.NOMINATION,
                                   rules=nominee_rules, today=today, now=now,
                                   consent_scopes=_exposed_scopes(db, nominee_rules, inputs),
                                   check_age_window=check_age_window)
    else:
        nominee_a = assess_unclaimed_nominee(db, nominee_age_declaration, rules=rules,
                                             nominator_jurisdiction=nom_jur.code, declined=declined)
    hooks = _hooks(db, nominee_a, inputs, kind=ContestEntryKind.NOMINATION,
                   stored_safety=SafetyStatus(stored.safety_status) if stored else None,
                   stored_rights=RightsStatus(stored.rights_status) if stored else None)
    return _compose(ContestEntryKind.NOMINATION, [nominator_a, nominee_a], nominee_a, hooks,
                    nominee_linked=nominee_user is not None, owner=CreativeOwnerType.NOMINEE)


def precheck(db: Session, user: User, contest: Optional[Contest], kind: ContestEntryKind, *, today: date,
             now: datetime) -> ContestEntryDecision:
    """Actor-level check before the member fills in the form (no media, no nominee yet)."""
    if kind == ContestEntryKind.NOMINATION:
        jur = AgeAndContestPolicyEngine.resolve_jurisdiction(getattr(user, "country", None))
        rules = resolve_contest_rules(db, contest, jur.code)
        a = assess_account(db, user, role=ROLE_NOMINATOR, operation=PolicyOperation.NOMINATION, rules=rules,
                           today=today, now=now, consent_scopes=_NOMINATOR_SCOPES)
        return _compose(kind, [a], a, (set(), SafetyStatus.CLEAR, RightsStatus.NOT_REQUIRED,
                                       MetadataSafetyStatus.NOT_REQUIRED, [], False),
                        nominee_linked=False, owner=CreativeOwnerType.NOMINEE)
    return evaluate_personal_submission(db, user, contest, EntryInputs(), today=today, now=now)


# ---------------------------------------------------------------------------
# Persistence, transitions and audit
# ---------------------------------------------------------------------------

def _state(row: ContestEntrySafety) -> dict:
    """Audit-safe snapshot: codes only (no DOB, age, guardian identity or content)."""
    return {"exposure_status": row.exposure_status, "workflow_step": row.workflow_step, "outcome": row.outcome,
            "reason_codes": row.reason_codes, "missing_consent_scopes": row.missing_consent_scopes,
            "rights_status": row.rights_status, "safety_status": row.safety_status,
            "metadata_status": row.metadata_status, "subject_age_tier": row.subject_age_tier,
            "decision_basis": row.decision_basis, "enforced": row.enforced}


def _apply(row: ContestEntrySafety, d: ContestEntryDecision, now: datetime) -> None:
    row.outcome = d.outcome.value
    row.exposure_status = d.exposure.value
    row.workflow_step = d.workflow_step.value if d.workflow_step else None
    row.reason_codes = [r.value for r in d.reasons]
    row.missing_consent_scopes = [s.value for s in d.missing_consent_scopes]
    row.decision_basis = d.basis.value
    row.enforced = d.enforced
    row.subject_age_tier = d.subject_age_tier.value if d.subject_age_tier else None
    row.jurisdiction_code = d.jurisdiction
    row.policy_id, row.policy_version = d.policy_id, d.policy_version
    row.rights_status = d.rights_status.value
    row.safety_status = d.safety_status.value
    row.safety_concerns = [c.value for c in d.safety_concerns]
    row.metadata_status = d.metadata_status.value
    row.guardian_relationship_id = d.guardian_relationship_id
    row.age_window_ok_at_entry = d.age_window_ok
    row.last_evaluated_at = now
    row.updated_at = now


def _log(db: Session, row: ContestEntrySafety, action: str, actor_id: Optional[int], new: dict,
         old: Optional[dict] = None, now: Optional[datetime] = None) -> None:
    db.add(AuditTrail(table_name="contest_entry_safety", record_id=row.id, action=action, old_values=old,
                      new_values=new, user_id=actor_id))
    now = now or datetime.utcnow()
    event = (AgeSafetyEventType.CHILD_SAFETY_ESCALATION
             if row.exposure_status == EntryExposureStatus.CHILD_SAFETY_ESCALATED.value
             else AgeSafetyEventType.CONTEST_ENTRY_TRANSITION)
    db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=event.value,
                          user_id=row.submitted_by_user_id, jurisdiction_code=row.jurisdiction_code,
                          age_tier=row.subject_age_tier, decision=row.exposure_status, enforced=row.enforced,
                          policy_id=row.policy_id, policy_version=row.policy_version,
                          risk_flag=event == AgeSafetyEventType.CHILD_SAFETY_ESCALATION,
                          details={"contestant_id": row.contestant_id, "action": action,
                                   "reason_codes": row.reason_codes}))


def record_new_entry(db: Session, contestant: Contestant, decision: ContestEntryDecision, *, kind: ContestEntryKind,
                     submitted_by: User, contest_id: Optional[int],
                     nominee_age_declaration: Optional[NomineeAgeDeclaration], now: datetime) -> ContestEntrySafety:
    """Write the entry's safety record in the caller's transaction. The caller
    created the contestant with is_active = decision.public."""
    row = ContestEntrySafety(
        created_at=now, contestant_id=contestant.id, contest_id=contest_id, entry_kind=kind.value,
        submitted_by_user_id=submitted_by.id, account_holder_user_id=contestant.user_id, nominee_user_id=None,
        creative_owner_type=decision.creative_owner_type.value,
        creative_owner_user_id=submitted_by.id if kind == ContestEntryKind.PERSONAL_SUBMISSION else None,
        nominee_age_declaration=(nominee_age_declaration or NomineeAgeDeclaration.UNKNOWN).value
        if kind == ContestEntryKind.NOMINATION else None,
        activated_at=now if decision.public else None)
    _apply(row, decision, now)
    db.add(row)
    db.flush()
    _log(db, row, "ENTRY_CREATED", submitted_by.id, _state(row), now=now)
    return row


def _contest_for(db: Session, row: ContestEntrySafety) -> Optional[Contest]:
    return db.query(Contest).filter(Contest.id == row.contest_id).first() if row.contest_id else None


def _inputs_for(contestant: Contestant, row: ContestEntrySafety) -> EntryInputs:
    stored = frozenset(SafetyConcern(c) for c in (row.safety_concerns or ()) if c in SafetyConcern.__members__)
    return EntryInputs(title=contestant.title, description=contestant.description,
                       image_media_ids=contestant.image_media_ids, video_media_ids=contestant.video_media_ids,
                       extra_concerns=stored)


def evaluate_stored_entry(db: Session, row: ContestEntrySafety, *, today: date, now: datetime,
                          inputs: Optional[EntryInputs] = None) -> ContestEntryDecision:
    contestant = db.query(Contestant).filter(Contestant.id == row.contestant_id).first()
    contest = _contest_for(db, row)
    inputs = inputs or _inputs_for(contestant, row)
    submitter = db.query(User).filter(User.id == row.submitted_by_user_id).first() if row.submitted_by_user_id else None
    # Contest min/max age: checked until the entry is first activated (a new or
    # corrected DOB can release the hold); never afterwards (a birthday does not
    # remove an active participant).
    window = row.activated_at is None
    if submitter is None:
        return ContestEntryDecision(EligibilityOutcome.HELD, (R.SAFETY_REVIEW_REQUIRED,), EntryExposureStatus.HELD)
    if row.entry_kind == ContestEntryKind.NOMINATION.value:
        nominee = db.query(User).filter(User.id == row.nominee_user_id).first() if row.nominee_user_id else None
        declaration = (NomineeAgeDeclaration(row.nominee_age_declaration)
                       if row.nominee_age_declaration else NomineeAgeDeclaration.UNKNOWN)
        return evaluate_nomination(db, submitter, contest, inputs, nominee_age_declaration=declaration,
                                   today=today, now=now, nominee_user=nominee, check_age_window=window, stored=row,
                                   declined=row.claim_declined_at is not None)
    return evaluate_personal_submission(db, submitter, contest, inputs, today=today, now=now,
                                        check_age_window=window, stored=row)


def reevaluate_entry(db: Session, row: ContestEntrySafety, *, actor_id: Optional[int], trigger: str,
                     today: date, now: Optional[datetime] = None, inputs: Optional[EntryInputs] = None,
                     commit: bool = True) -> ContestEntrySafety:
    """Recompute from CURRENT data (age, policy, consent, review state, rules).

    HELD -> PUBLIC only when everything passes. PUBLIC -> HELD when something
    required is no longer satisfied (e.g. consent withdrawn): the entry stops
    being active from now on. Votes, results and history are kept as they are.
    BLOCKED and CHILD_SAFETY_ESCALATED entries are only changed by an
    administrator, never by re-evaluation.
    """
    now = now or datetime.utcnow()
    contestant = db.query(Contestant).filter(Contestant.id == row.contestant_id).first()
    old = _state(row)
    if row.exposure_status in (EntryExposureStatus.BLOCKED.value, EntryExposureStatus.CHILD_SAFETY_ESCALATED.value):
        return row
    d = evaluate_stored_entry(db, row, today=today, now=now, inputs=inputs)
    was_public = row.exposure_status == EntryExposureStatus.PUBLIC.value
    _apply(row, d, now)
    action = "ENTRY_REEVALUATED"
    if d.public and not was_public:
        row.activated_at = now
        action = "ENTRY_ACTIVATED"
    elif was_public and not d.public:
        row.suspended_at = now
        action = "ENTRY_SUSPENDED"
    if contestant is not None and not getattr(contestant, "is_deleted", False):
        contestant.is_active = d.public
    if _state(row) != old:
        _log(db, row, action, actor_id, {**_state(row), "trigger": trigger}, old, now=now)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def reevaluate_for_user(db: Session, user_id: int, *, trigger: str, today: date, actor_id: Optional[int] = None,
                        now: Optional[datetime] = None) -> int:
    """Re-evaluate every open Phase 5 entry where this person is the submitter or
    the linked nominee (consent change, DOB change, review change)."""
    rows = (db.query(ContestEntrySafety)
            .filter(or_(ContestEntrySafety.submitted_by_user_id == user_id,
                        ContestEntrySafety.nominee_user_id == user_id),
                    ContestEntrySafety.exposure_status.in_([EntryExposureStatus.PUBLIC.value,
                                                            EntryExposureStatus.HELD.value]))
            .all())
    for row in rows:
        reevaluate_entry(db, row, actor_id=actor_id, trigger=trigger, today=today, now=now, commit=False)
    if rows:
        db.commit()
    return len(rows)


def reevaluate_open_entries(db: Session, *, trigger: str, today: date, actor_id: Optional[int] = None,
                            limit: int = 500, contest_ids: Optional[Sequence[int]] = None) -> dict:
    """Bulk re-evaluation (birthdays, policy/rule changes). Only Phase 5 entries."""
    q = db.query(ContestEntrySafety).filter(
        ContestEntrySafety.exposure_status.in_([EntryExposureStatus.PUBLIC.value, EntryExposureStatus.HELD.value]))
    if contest_ids is not None:
        q = q.filter(ContestEntrySafety.contest_id.in_(list(contest_ids) or [-1]))
    rows = q.order_by(ContestEntrySafety.id).limit(limit).all()
    before = {r.id: r.exposure_status for r in rows}
    for row in rows:
        reevaluate_entry(db, row, actor_id=actor_id, trigger=trigger, today=today, commit=False)
    db.commit()
    changed = sum(1 for r in rows if before[r.id] != r.exposure_status)
    return {"evaluated": len(rows), "changed": changed}


def safe_reevaluate_for_user(db: Session, user_id: Optional[int], *, trigger: str,
                             actor_id: Optional[int] = None) -> None:
    """Hook for other services (consent/DOB changes). Never raises into the caller."""
    if not user_id:
        return
    import logging

    from app.services.age_policy_engine import utc_today
    try:
        reevaluate_for_user(db, user_id, trigger=trigger, today=utc_today(), actor_id=actor_id)
    except Exception as exc:  # noqa: BLE001 - the caller's own change has already been committed
        db.rollback()
        logging.getLogger(__name__).warning("Phase 5 re-evaluation failed (%s): %s", trigger, type(exc).__name__)


# ---------------------------------------------------------------------------
# Contest / category rule lifecycle (administrators; audited)
# ---------------------------------------------------------------------------

RULE_MODELS = {"contest": (ContestAgeEligibility, "contest_id"), "category": (CategoryAgePolicy, "category_id")}


def create_rule(db: Session, kind: str, scope_id: int, definition: ContestAgeRuleDefinition, *, admin_id: int,
                reason: str, now: Optional[datetime] = None):
    """New rules start as DRAFT (never applied until activated)."""
    model, col = RULE_MODELS[kind]
    now = now or datetime.utcnow()
    latest = (db.query(model).filter(getattr(model, col) == scope_id, model.jurisdiction == definition.jurisdiction)
              .order_by(model.rule_version.desc()).first())
    data = definition.model_dump(mode="json")
    row = model(created_at=now, updated_at=now, rule_version=(latest.rule_version + 1) if latest else 1,
                status=ContestAgeRuleStatus.DRAFT.value, changed_by_user_id=admin_id, change_reason=reason,
                **{col: scope_id}, **data)
    db.add(row)
    db.flush()
    db.add(AuditTrail(table_name=model.__tablename__, record_id=row.id, action="AGE_RULE_CREATED", old_values=None,
                      new_values={"rule_version": row.rule_version, "jurisdiction": row.jurisdiction,
                                  "reason": reason}, user_id=admin_id))
    db.commit()
    db.refresh(row)
    return row


def _affected_contest_ids(db: Session, kind: str, row) -> List[int]:
    if kind == "contest":
        return [row.contest_id]
    return [cid for (cid,) in db.query(Contest.id).filter(Contest.category_id == row.category_id).all()]


def change_rule_status(db: Session, kind: str, row, *, activate: bool, admin_id: int, reason: str, today: date,
                       now: Optional[datetime] = None):
    """DRAFT -> ACTIVE (a previous ACTIVE rule for the same scope and jurisdiction
    is withdrawn, never edited), or ACTIVE/DRAFT -> WITHDRAWN. Open Phase 5
    entries of the affected contests are re-evaluated afterwards."""
    model, col = RULE_MODELS[kind]
    now = now or datetime.utcnow()
    old = row.status
    if activate:
        if row.status != ContestAgeRuleStatus.DRAFT.value:
            raise EntryReviewError("INVALID_STATUS", "Only a DRAFT rule can be activated.")
        rule_definition_from_row(row)  # invalid stored data never becomes ACTIVE
        for current in db.query(model).filter(getattr(model, col) == getattr(row, col),
                                              model.jurisdiction == row.jurisdiction,
                                              model.status == ContestAgeRuleStatus.ACTIVE.value):
            current.status, current.withdrawn_at = ContestAgeRuleStatus.WITHDRAWN.value, now
            db.add(AuditTrail(table_name=model.__tablename__, record_id=current.id, action="AGE_RULE_SUPERSEDED",
                              old_values={"status": "ACTIVE"}, new_values={"superseded_by": row.id},
                              user_id=admin_id))
        db.flush()
        row.status, row.activated_at = ContestAgeRuleStatus.ACTIVE.value, now
    else:
        if row.status == ContestAgeRuleStatus.WITHDRAWN.value:
            raise EntryReviewError("INVALID_STATUS", "This rule is already withdrawn.")
        row.status, row.withdrawn_at = ContestAgeRuleStatus.WITHDRAWN.value, now
    row.changed_by_user_id, row.change_reason, row.updated_at = admin_id, reason, now
    db.add(AuditTrail(table_name=model.__tablename__, record_id=row.id,
                      action="AGE_RULE_ACTIVATED" if activate else "AGE_RULE_WITHDRAWN",
                      old_values={"status": old}, new_values={"status": row.status, "reason": reason},
                      user_id=admin_id))
    db.commit()
    db.refresh(row)
    reevaluate_open_entries(db, trigger=f"AGE_RULE_{'ACTIVATED' if activate else 'WITHDRAWN'}", today=today,
                            actor_id=admin_id, contest_ids=_affected_contest_ids(db, kind, row))
    return row


def row_subject_possibly_minor(row: ContestEntrySafety) -> bool:
    """For hooks on an existing entry: only a determined adult (or a nominee the
    nominator declared an adult) is treated as not possibly minor."""
    if row.entry_kind == ContestEntryKind.NOMINATION.value and row.nominee_user_id is None:
        return row.nominee_age_declaration != NomineeAgeDeclaration.ADULT.value
    return row.subject_age_tier != AgeTier.ADULT_18_PLUS.value


def escalate_entry(db: Session, row: ContestEntrySafety, *, actor_id: Optional[int], action: str,
                   now: Optional[datetime] = None) -> ContestEntrySafety:
    """s.11 dedicated path: block publication and distribution of the entry,
    keep the record for specialized review, raise a high-severity event. Only
    codes are logged; the content itself is never copied into logs."""
    now = now or datetime.utcnow()
    old = _state(row)
    row.safety_concerns = sorted(set(row.safety_concerns or ()) | {SafetyConcern.CHILD_SEXUAL_CONTENT.value})
    row.safety_status = SafetyStatus.CHILD_SAFETY_ESCALATED.value
    row.exposure_status = EntryExposureStatus.CHILD_SAFETY_ESCALATED.value
    row.workflow_step = NominationWorkflowStep.BLOCKED.value if row.entry_kind == "NOMINATION" else None
    row.reason_codes = sorted(set(row.reason_codes or ()) | {R.CHILD_SAFETY_ESCALATION.value})
    row.suspended_at, row.updated_at = now, now
    contestant = db.query(Contestant).filter(Contestant.id == row.contestant_id).first()
    if contestant is not None:
        contestant.is_active = False
    _log(db, row, action, actor_id, _state(row), old, now=now)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Nominee claim (s.12 "Nominee notified" -> nominee confirms with their own account)
# ---------------------------------------------------------------------------
#
# Minimum safe foundation. MyHigh5 stores NO contact details for the nominee
# (who may be a minor) and sends no message itself: the nominator receives a
# single-use claim link once and passes it on. Claiming only links the
# claimant's own account as nominee/creative owner. It never creates or implies
# guardian authority, and it never makes the entry public by itself: the entry
# is re-evaluated and stays HELD until every requirement is met.

class ClaimError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _token_hash(raw: Optional[str]) -> Optional[str]:
    if not raw or len(raw) > 200:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clear_claim_token(row: ContestEntrySafety) -> None:
    row.claim_token_hash = None
    row.claim_token_expires_at = None


def issue_claim_token(db: Session, row: ContestEntrySafety, *, actor_id: Optional[int],
                      now: Optional[datetime] = None, commit: bool = True) -> str:
    """Issue (or re-issue, invalidating the previous link) the claim token for an
    unclaimed nomination. The raw token is returned once and never stored."""
    now = now or datetime.utcnow()
    if row.entry_kind != ContestEntryKind.NOMINATION.value:
        raise ClaimError("NOT_A_NOMINATION", "Only nominations can be claimed.")
    if row.claimed_at is not None or row.claim_declined_at is not None:
        raise ClaimError("CLAIM_CLOSED", "This nomination can no longer be claimed.")
    if row.exposure_status in (EntryExposureStatus.BLOCKED.value, EntryExposureStatus.CHILD_SAFETY_ESCALATED.value):
        raise ClaimError("CLAIM_CLOSED", "This nomination can no longer be claimed.")
    from app.core.age_safety_config import get_age_safety_config

    raw = secrets.token_urlsafe(32)
    row.claim_token_hash = _token_hash(raw)
    row.claim_token_issued_at = now
    row.claim_token_expires_at = now + timedelta(days=get_age_safety_config().nominee_claim_token_ttl_days)
    row.updated_at = now
    db.add(AuditTrail(table_name="contest_entry_safety", record_id=row.id, action="NOMINEE_CLAIM_LINK_ISSUED",
                      old_values=None, new_values={"expires_at": row.claim_token_expires_at.isoformat()},
                      user_id=actor_id))
    if commit:
        db.commit()
    return raw


def _open_claim(db: Session, raw: str, now: datetime, *, lock: bool = False) -> Optional[ContestEntrySafety]:
    hashed = _token_hash(raw)
    if not hashed:
        return None
    q = db.query(ContestEntrySafety).filter(ContestEntrySafety.claim_token_hash == hashed)
    if lock:
        q = q.with_for_update()
    row = q.first()
    if (row is None or row.claim_token_expires_at is None or row.claim_token_expires_at <= now
            or row.claimed_at is not None or row.claim_declined_at is not None
            or row.exposure_status in (EntryExposureStatus.BLOCKED.value,
                                       EntryExposureStatus.CHILD_SAFETY_ESCALATED.value)):
        return None
    return row


def claim_summary(db: Session, raw: str, now: Optional[datetime] = None) -> Optional[dict]:
    """What the claimant may see before deciding: the entry title and contest
    name only (never the nominator's identity or any age information)."""
    now = now or datetime.utcnow()
    row = _open_claim(db, raw, now)
    if row is None:
        return None
    contestant = db.query(Contestant).filter(Contestant.id == row.contestant_id).first()
    contest = _contest_for(db, row)
    return {"entry_title": getattr(contestant, "title", None), "contest_name": getattr(contest, "name", None),
            "expires_at": row.claim_token_expires_at.isoformat()}


def respond_to_claim(db: Session, raw: str, claimant: User, *, accept: bool, today: date,
                     now: Optional[datetime] = None) -> ContestEntrySafety:
    """The nominee accepts (links their own account) or declines the nomination.
    Single use: the token is cleared either way. Invalid, expired or used tokens
    all give the same generic error."""
    now = now or datetime.utcnow()
    row = _open_claim(db, raw, now, lock=True)
    if row is None:
        raise ClaimError("INVALID_OR_EXPIRED", "This link is invalid or has expired.")
    if claimant.id in (row.submitted_by_user_id, row.account_holder_user_id):
        # The nominator/account holder can never be the nominee (actor separation).
        raise ClaimError("NOT_ALLOWED", "This link can't be used by this account.")
    if accept and not getattr(claimant, "email_verified", False):
        raise ClaimError("EMAIL_NOT_VERIFIED", "Please verify your email address before confirming.")
    old = _state(row)
    _clear_claim_token(row)
    if accept:
        row.nominee_user_id = claimant.id
        row.creative_owner_user_id = claimant.id
        row.claimed_at = now
        ctx = AgeAndContestPolicyEngine(db).context_for_user(claimant, today, _profile(db, claimant))
        determined_adult = ctx.age_tier == AgeTier.ADULT_18_PLUS and (not ctx.policy.found or ctx.legal_adult)
        if determined_adult:
            # An adult creative owner confirms their own rights by claiming. A minor
            # cannot: rights stay pending (guardian consent + administrator).
            row.rights_status = RightsStatus.CONFIRMED.value
        action = "NOMINEE_CLAIM_ACCEPTED"
    else:
        row.claim_declined_at = now
        row.rights_status = RightsStatus.DISPUTED.value
        action = "NOMINEE_CLAIM_DECLINED"
    row.updated_at = now
    db.add(AuditTrail(table_name="contest_entry_safety", record_id=row.id, action=action, old_values=old,
                      new_values={"claimant_user_id": claimant.id, "rights_status": row.rights_status},
                      user_id=claimant.id))
    db.add(AgeSafetyEvent(created_at=now, updated_at=now, event_type=AgeSafetyEventType.NOMINEE_CLAIM.value,
                          user_id=claimant.id, details={"contestant_id": row.contestant_id, "action": action}))
    db.flush()
    return reevaluate_entry(db, row, actor_id=claimant.id, trigger=action, today=today, now=now)


# ---------------------------------------------------------------------------
# Administrator review
# ---------------------------------------------------------------------------

class EntryReviewError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def admin_review(db: Session, row: ContestEntrySafety, *, action: str, admin_id: int, note: str, today: date,
                 concern: Optional[SafetyConcern] = None, nominee_user_id: Optional[int] = None,
                 now: Optional[datetime] = None) -> ContestEntrySafety:
    """Administrator workflow actions. None of them creates guardian consent or
    guardian authority, and none of them can override a denial of eligibility:
    activation only ever happens through re-evaluation."""
    now = now or datetime.utcnow()
    old = _state(row)
    contestant = db.query(Contestant).filter(Contestant.id == row.contestant_id).first()
    row.reviewed_by_user_id, row.reviewed_at = admin_id, now
    escalated = row.exposure_status == EntryExposureStatus.CHILD_SAFETY_ESCALATED.value
    if escalated and action not in ("BLOCK",):
        raise EntryReviewError("ESCALATED", "Escalated child-safety entries are handled by specialized review only.")

    concerns = set(row.safety_concerns or ())
    if action == "CONFIRM_RIGHTS":
        row.rights_status = RightsStatus.CONFIRMED.value
        concerns.discard(SafetyConcern.THIRD_PARTY_RIGHTS.value)
    elif action == "DISPUTE_RIGHTS":
        row.rights_status = RightsStatus.DISPUTED.value
    elif action == "CLEAR_SAFETY_REVIEW":
        if concerns & {c.value for c in CHILD_SAFETY_ESCALATION_CONCERNS}:
            raise EntryReviewError("ESCALATED", "This concern cannot be cleared here.")
        row.safety_status = SafetyStatus.REVIEWED_CLEAR.value
        concerns &= {SafetyConcern.THIRD_PARTY_RIGHTS.value}
    elif action == "FLAG_CONCERN":
        concerns.add(concern.value)
        if concern in CHILD_SAFETY_ESCALATION_CONCERNS:
            action = "ESCALATE_CHILD_SAFETY"
        else:
            row.safety_status = SafetyStatus.REVIEW_REQUIRED.value
    elif action == "LINK_NOMINEE_ACCOUNT":
        if row.entry_kind != ContestEntryKind.NOMINATION.value:
            raise EntryReviewError("NOT_A_NOMINATION", "Only nominations have a nominee.")
        if nominee_user_id in (row.submitted_by_user_id,):
            raise EntryReviewError("NOMINATOR_IS_NOT_NOMINEE", "The nominator cannot be linked as the nominee.")
        if nominee_user_id == row.account_holder_user_id:
            raise EntryReviewError("NOMINATOR_IS_NOT_NOMINEE", "The account holder cannot be linked as the nominee.")
        if db.query(User.id).filter(User.id == nominee_user_id).first() is None:
            raise EntryReviewError("NOT_FOUND", "Account not found.")
        if row.nominee_user_id not in (None, nominee_user_id):
            raise EntryReviewError("ALREADY_CLAIMED", "This nomination is already linked to another account.")
        # Administrator fallback for the claim link (independent confirmation).
        row.nominee_user_id = nominee_user_id
        row.creative_owner_user_id = nominee_user_id
        row.claimed_at = row.claimed_at or now
        _clear_claim_token(row)
    elif action not in ("BLOCK", "ESCALATE_CHILD_SAFETY", "REEVALUATE"):
        raise EntryReviewError("INVALID_ACTION", "Unknown action.")
    row.safety_concerns = sorted(concerns)

    if action == "ESCALATE_CHILD_SAFETY":
        return escalate_entry(db, row, actor_id=admin_id, action="ADMIN_ESCALATE_CHILD_SAFETY", now=now)
    if action == "BLOCK":
        if not escalated:
            row.safety_status = SafetyStatus.BLOCKED.value
            row.exposure_status = EntryExposureStatus.BLOCKED.value
            row.workflow_step = NominationWorkflowStep.BLOCKED.value if row.entry_kind == "NOMINATION" else None
        row.suspended_at = now
        if contestant is not None:
            contestant.is_active = False
    _log(db, row, f"ADMIN_{action}", admin_id, {**_state(row), "note_present": bool(note)}, old, now=now)
    db.flush()
    if action not in ("BLOCK", "ESCALATE_CHILD_SAFETY"):
        return reevaluate_entry(db, row, actor_id=admin_id, trigger=f"ADMIN_{action}", today=today, now=now)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Public-exposure gate for read paths (implemented in entry_exposure, re-exported)
# ---------------------------------------------------------------------------

from app.services.entry_exposure import (  # noqa: E402,F401
    entry_publicly_visible,
    not_publicly_exposable_clause,
    public_entry_clause,
)


def owner_view(row: Optional[ContestEntrySafety]) -> Optional[dict]:
    """What the entry's own submitter may see (codes and step only)."""
    if row is None:
        return None
    return {"public_status": "PUBLIC" if row.exposure_status == EntryExposureStatus.PUBLIC.value else "PENDING_REVIEW",
            "workflow_step": row.workflow_step,
            "reason_codes": [c for c in (row.reason_codes or ())
                             if c not in (R.CHILD_SAFETY_ESCALATION.value,)]}
