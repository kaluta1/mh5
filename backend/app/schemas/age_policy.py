"""Typed, validated AgePolicy configuration (Child/Teen Safety requirement, section 3).

The structured AgePolicy fields are small typed schemas rather than free-form
JSON. The hard rules enforced here come directly from the requirement, and a
policy that breaks one of them cannot be saved:

- s.2: UNDER_13 ordinary membership is prohibited (no child-account framework), so
  minimum_account_age >= 13. Minors remain minors, so adult_age >= 18.
- s.7, s.16, s.15: ADULT_18_PLUS content is never permitted to anyone under 18, and
  PROHIBITED is never permitted to anyone.
- s.7, s.24, s.25: teen privacy defaults and minor-profile display rules.
- UNKNOWN age is fail-closed: it gets the most protective treatment and never
  adult permissions.

advertising_restrictions is intentionally minimal: the source document is
truncated at the start of section 33 ("Restrict categori..."), so detailed
advertising rules are DEFERRED and not invented here.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.child_safety import (
    AGE_THRESHOLD_FIELD_BY_OPERATION,
    AgeAssuranceLevel,
    AgePolicyStatus,
    AgeTier,
    ContentRating,
    PolicyOperation,
)
from app.core.jurisdictions import ISO_COUNTRY_NAMES

ALL_TIERS = frozenset(AgeTier)

# Highest content ratings each tier may ever be configured to receive. The
# rating names themselves define this (a TEEN_16_PLUS rating is not for 13-15),
# and UNKNOWN is capped like the youngest account-holding tier.
_MAX_RATINGS_BY_TIER: Dict[AgeTier, frozenset] = {
    AgeTier.UNDER_13: frozenset({ContentRating.GENERAL}),
    AgeTier.TEEN_13_15: frozenset({ContentRating.GENERAL, ContentRating.TEEN_13_PLUS}),
    AgeTier.TEEN_16_17: frozenset({ContentRating.GENERAL, ContentRating.TEEN_13_PLUS, ContentRating.TEEN_16_PLUS}),
    AgeTier.ADULT_18_PLUS: frozenset(
        {ContentRating.GENERAL, ContentRating.TEEN_13_PLUS, ContentRating.TEEN_16_PLUS, ContentRating.ADULT_18_PLUS}
    ),
    AgeTier.UNKNOWN: frozenset({ContentRating.GENERAL, ContentRating.TEEN_13_PLUS}),
}

_STRONGEST_PROTECTION_TIERS = frozenset({AgeTier.UNDER_13, AgeTier.TEEN_13_15, AgeTier.UNKNOWN})
_PROTECTED_TIERS = _STRONGEST_PROTECTION_TIERS | {AgeTier.TEEN_16_17}


def _require_all_tiers(value: dict, field: str) -> dict:
    missing = ALL_TIERS - set(value)
    if missing:
        raise ValueError(f"{field} must define every age tier; missing: {sorted(t.value for t in missing)}")
    return value


def _unique(ops: List[PolicyOperation], field: str) -> List[PolicyOperation]:
    if len(set(ops)) != len(ops):
        raise ValueError(f"{field} contains duplicate operations")
    return ops


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KycRequirement(_Strict):
    """Operations for which the policy requires KYC. KYC stays a separate
    dimension: it is reported as a requirement and never implies age or eligibility."""

    operations: List[PolicyOperation] = Field(default_factory=list)

    @field_validator("operations")
    @classmethod
    def _no_duplicates(cls, v):
        return _unique(v, "kyc_requirement.operations")


class AgeAssuranceRequirement(_Strict):
    """Minimum age-assurance level: a default plus stronger per-operation levels (s.5)."""

    default: AgeAssuranceLevel = AgeAssuranceLevel.SELF_DECLARED_DOB
    operations: Dict[PolicyOperation, AgeAssuranceLevel] = Field(default_factory=dict)

    def required_for(self, operation: PolicyOperation) -> AgeAssuranceLevel:
        level = self.operations.get(operation, self.default)
        # A per-operation level can only strengthen the default.
        return level if level.rank >= self.default.rank else self.default


class ParentalConsentRequirement(_Strict):
    """Operations needing guardian consent while the user is younger than
    parental_consent_age (s.3, s.9, s.14). Consent itself is not implemented here."""

    operations: List[PolicyOperation] = Field(default_factory=list)

    @field_validator("operations")
    @classmethod
    def _no_duplicates(cls, v):
        return _unique(v, "parental_consent_requirement.operations")


class PermittedContentRatings(_Strict):
    """Content ratings each age tier may receive (s.15/s.16)."""

    by_tier: Dict[AgeTier, List[ContentRating]]

    @field_validator("by_tier")
    @classmethod
    def _validate(cls, v: Dict[AgeTier, List[ContentRating]]):
        _require_all_tiers(v, "permitted_content_ratings.by_tier")
        for tier, ratings in v.items():
            if ContentRating.PROHIBITED in ratings:
                raise ValueError("PROHIBITED content can never be permitted")
            excess = set(ratings) - _MAX_RATINGS_BY_TIER[tier]
            if excess:
                raise ValueError(
                    f"{tier.value} cannot be permitted {sorted(r.value for r in excess)}"
                )
            if len(set(ratings)) != len(ratings):
                raise ValueError(f"duplicate ratings for {tier.value}")
        return v


class TierAdvertisingRestrictions(_Strict):
    targeted_advertising_allowed: bool = False
    # Opaque category codes. The requirement's detailed advertising rules are
    # truncated (s.33) and DEFERRED; this list only reserves the structure.
    restricted_categories: List[str] = Field(default_factory=list)

    @field_validator("restricted_categories")
    @classmethod
    def _codes(cls, v: List[str]):
        for code in v:
            if not code or len(code) > 50 or not code.replace("_", "").isalnum() or code.upper() != code:
                raise ValueError("advertising category codes must be UPPER_SNAKE_CASE (max 50 chars)")
        if len(set(v)) != len(v):
            raise ValueError("duplicate advertising category codes")
        return v


class AdvertisingRestrictions(_Strict):
    """Minimal advertising foundation. Detailed rules DEFERRED (source truncated at s.33)."""

    by_tier: Dict[AgeTier, TierAdvertisingRestrictions]

    @field_validator("by_tier")
    @classmethod
    def _validate(cls, v):
        _require_all_tiers(v, "advertising_restrictions.by_tier")
        for tier in (AgeTier.UNDER_13, AgeTier.UNKNOWN):
            if v[tier].targeted_advertising_allowed:
                raise ValueError(f"targeted advertising cannot be allowed for {tier.value}")
        return v


class TierProfileVisibility(_Strict):
    high_privacy_default: bool
    precise_location_visible: bool
    location_sharing: bool
    search_engine_indexing: bool
    public_contact_information: bool
    public_date_of_birth: bool
    exact_age_visible: bool
    profile_discovery_by_unrelated_adults: bool
    unknown_adult_direct_messages: Literal["ALLOWED", "RESTRICTED", "PROHIBITED"]
    tagging_controls_enabled: bool
    safety_notifications_enabled: bool
    profiling_restricted: bool


# s.24/s.25: never shown for any minor (or unknown age) by default.
_MINOR_MUST_BE_OFF = (
    "precise_location_visible",
    "location_sharing",
    "search_engine_indexing",
    "public_contact_information",
    "public_date_of_birth",
    "exact_age_visible",
)
# s.7 (13-15, strongest protections), also applied to UNDER_13 and UNKNOWN.
_STRONGEST_MUST_BE_ON = ("high_privacy_default", "tagging_controls_enabled", "safety_notifications_enabled", "profiling_restricted")
_STRONGEST_MUST_BE_OFF = ("profile_discovery_by_unrelated_adults",)


class ProfileVisibilityRules(_Strict):
    """Default profile privacy per tier (s.7, s.24, s.25)."""

    by_tier: Dict[AgeTier, TierProfileVisibility]

    @field_validator("by_tier")
    @classmethod
    def _validate(cls, v: Dict[AgeTier, TierProfileVisibility]):
        _require_all_tiers(v, "profile_visibility_rules.by_tier")
        for tier in _PROTECTED_TIERS:
            rules = v[tier]
            for name in _MINOR_MUST_BE_OFF:
                if getattr(rules, name):
                    raise ValueError(f"{name} must be off for {tier.value}")
            if not rules.high_privacy_default:
                raise ValueError(f"high_privacy_default must be on for {tier.value}")
        for tier in _STRONGEST_PROTECTION_TIERS:
            rules = v[tier]
            for name in _STRONGEST_MUST_BE_ON:
                if not getattr(rules, name):
                    raise ValueError(f"{name} must be on for {tier.value}")
            for name in _STRONGEST_MUST_BE_OFF:
                if getattr(rules, name):
                    raise ValueError(f"{name} must be off for {tier.value}")
            if rules.unknown_adult_direct_messages == "ALLOWED":
                raise ValueError(f"direct messages from unknown adults cannot be ALLOWED for {tier.value}")
        return v


class AgePolicyDefinition(_Strict):
    """Complete content of one AgePolicy version (everything except version/status)."""

    jurisdiction: str = Field(min_length=2, max_length=10)
    effective_date: date

    minimum_account_age: int = Field(ge=0, le=120)
    minimum_independent_participation_age: int = Field(ge=0, le=120)
    parental_consent_age: int = Field(ge=0, le=120)
    adult_age: int = Field(ge=0, le=120)
    voting_minimum_age: int = Field(ge=0, le=120)
    nomination_minimum_age: int = Field(ge=0, le=120)
    personal_submission_minimum_age: int = Field(ge=0, le=120)
    livestream_minimum_age: int = Field(ge=0, le=120)
    prize_contract_age: int = Field(ge=0, le=120)
    payment_minimum_age: int = Field(ge=0, le=120)

    kyc_requirement: KycRequirement
    age_assurance_level: AgeAssuranceRequirement
    parental_consent_requirement: ParentalConsentRequirement
    permitted_content_ratings: PermittedContentRatings
    advertising_restrictions: AdvertisingRestrictions
    profile_visibility_rules: ProfileVisibilityRules

    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("jurisdiction")
    @classmethod
    def _jurisdiction(cls, v: str) -> str:
        code = (v or "").strip().upper()
        if code not in ISO_COUNTRY_NAMES:
            raise ValueError("jurisdiction must be a supported ISO 3166-1 alpha-2 country code")
        return code

    @model_validator(mode="after")
    def _thresholds(self):
        if self.minimum_account_age < 13:
            raise ValueError("minimum_account_age must be at least 13 (under-13 membership is prohibited)")
        if self.adult_age < 18:
            raise ValueError("adult_age must be at least 18")
        if not (self.minimum_account_age <= self.minimum_independent_participation_age <= self.adult_age):
            raise ValueError("minimum_independent_participation_age must be between minimum_account_age and adult_age")
        if not (13 <= self.parental_consent_age <= self.adult_age):
            raise ValueError("parental_consent_age must be between 13 and adult_age")
        for field in AGE_THRESHOLD_FIELD_BY_OPERATION.values():
            if getattr(self, field) < self.minimum_account_age:
                raise ValueError(f"{field} cannot be lower than minimum_account_age")
        return self


class AgePolicyStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=500)


class AgePolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jurisdiction: str
    policy_version: int
    status: AgePolicyStatus
    effective_date: date
    minimum_account_age: int
    minimum_independent_participation_age: int
    parental_consent_age: int
    adult_age: int
    voting_minimum_age: int
    nomination_minimum_age: int
    personal_submission_minimum_age: int
    livestream_minimum_age: int
    prize_contract_age: int
    payment_minimum_age: int
    kyc_requirement: dict
    age_assurance_level: dict
    parental_consent_requirement: dict
    permitted_content_ratings: dict
    advertising_restrictions: dict
    profile_visibility_rules: dict
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status_changed_at: Optional[datetime] = None
    status_reason: Optional[str] = None
