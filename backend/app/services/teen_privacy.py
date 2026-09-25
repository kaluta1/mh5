"""Teen privacy defaults and resolution (Child/Teen Safety s.7, s.8, s.14, s.24, s.25).

Server-authoritative. Later phases (profiles/content delivery, messaging,
advertising) must ask this module, never the client.

Precedence (most important first):
  1. MANDATORY SAFETY FLOOR for the user's CURRENT tier. The resolved AgePolicy's
     profile_visibility_rules if a policy is in force, otherwise built-in floors
     derived directly from the source (s.7 for 13-15; s.24/s.25 for all minors;
     UNKNOWN treated like the youngest account-holding tier; no floor for adults).
  2. GUARDIAN-CONSENT ALLOWANCES. Only the consent-scoped display permissions
     (name, city/country, public creative display; s.8, s.14). Consent can never
     lift a mandatory prohibition such as DOB, exact age, contact details or
     precise location.
  3. USER PREFERENCE. May only make things MORE private. A preference below the
     floor is rejected.

Resolution is dynamic (current age, policy and consent), so birthdays, policy
versions, consent withdrawal and guardian status changes take effect
automatically. Nothing here grants content, messaging, advertising or financial
eligibility; those phases enforce their own rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.child_safety import AgeTier, ConsentRequirement, GuardianConsentScope
from app.models.age_safety import UserAgeProfile
from app.models.guardian import UserPrivacyPreference
from app.models.user import User
from app.services.age_policy_engine import AgeAndContestPolicyEngine

# Fields where True means LESS private (visible/allowed).
EXPOSURE_FIELDS = (
    "precise_location_visible", "location_sharing", "search_engine_indexing", "public_contact_information",
    "public_date_of_birth", "exact_age_visible", "profile_discovery_by_unrelated_adults",
)
# Fields where True means MORE private (protections on).
PROTECTION_FIELDS = ("high_privacy_default", "tagging_controls_enabled", "safety_notifications_enabled",
                     "profiling_restricted")
DM_FIELD = "unknown_adult_direct_messages"
_DM_ORDER = {"ALLOWED": 0, "RESTRICTED": 1, "PROHIBITED": 2}
ALL_FIELDS = EXPOSURE_FIELDS + PROTECTION_FIELDS + (DM_FIELD,)

# ---- built-in floors (used when no AgePolicy is in force) -------------------
_STRONGEST = {**{f: False for f in EXPOSURE_FIELDS}, **{f: True for f in PROTECTION_FIELDS},
              DM_FIELD: "PROHIBITED"}                      # s.7 (13-15), fail-closed for UNDER_13/UNKNOWN
_TEEN_16_17_FLOOR = {**{f: False for f in EXPOSURE_FIELDS}, "high_privacy_default": True,
                     "tagging_controls_enabled": False, "safety_notifications_enabled": False,
                     "profiling_restricted": False, DM_FIELD: "ALLOWED"}   # s.24/s.25 minor rules
_NO_FLOOR = {**{f: True for f in EXPOSURE_FIELDS}, **{f: False for f in PROTECTION_FIELDS}, DM_FIELD: "ALLOWED"}

_BUILTIN_FLOOR = {
    AgeTier.UNDER_13: _STRONGEST, AgeTier.TEEN_13_15: _STRONGEST, AgeTier.UNKNOWN: _STRONGEST,
    AgeTier.TEEN_16_17: _TEEN_16_17_FLOOR, AgeTier.ADULT_18_PLUS: _NO_FLOOR,
}
# Defaults when the user has no preference (always at least as private as the floor).
_BUILTIN_DEFAULTS = {
    AgeTier.UNDER_13: _STRONGEST, AgeTier.TEEN_13_15: _STRONGEST, AgeTier.UNKNOWN: _STRONGEST,
    AgeTier.TEEN_16_17: {**_STRONGEST, DM_FIELD: "RESTRICTED"},   # "maintain protective defaults" (s.7)
    # Current MyHigh5 behaviour for adults: DOB, age, contact and precise location are not shown.
    AgeTier.ADULT_18_PLUS: {**_NO_FLOOR, "public_date_of_birth": False, "exact_age_visible": False,
                            "public_contact_information": False, "precise_location_visible": False,
                            "location_sharing": False},
}

DISPLAY_SCOPES = {
    "name_display": GuardianConsentScope.NAME_DISPLAY,
    "city_country_display": GuardianConsentScope.CITY_COUNTRY_DISPLAY,
    "public_creative_display": GuardianConsentScope.PUBLIC_CREATIVE_DISPLAY,
}
_ALLOWING = (ConsentRequirement.NOT_REQUIRED_ADULT, ConsentRequirement.NOT_REQUIRED_BY_POLICY,
             ConsentRequirement.SATISFIED)


class PrivacyPreferenceError(ValueError):
    def __init__(self, fields: List[str]):
        super().__init__("Privacy settings cannot be less private than the safety floor for this account.")
        self.fields = fields


def _more_private(field_name: str, a, b):
    if field_name in EXPOSURE_FIELDS:
        return bool(a) and bool(b)
    if field_name in PROTECTION_FIELDS:
        return bool(a) or bool(b)
    return a if _DM_ORDER[a] >= _DM_ORDER[b] else b


def _less_private_than(field_name: str, value, floor) -> bool:
    if field_name in EXPOSURE_FIELDS:
        return bool(value) and not bool(floor)
    if field_name in PROTECTION_FIELDS:
        return (not bool(value)) and bool(floor)
    return _DM_ORDER[value] < _DM_ORDER[floor]


@dataclass(frozen=True)
class EffectivePrivacy:
    age_tier: AgeTier
    source: str                       # "POLICY" or "BUILTIN_SOURCE_FLOOR"
    policy_version: Optional[int]
    settings: Dict[str, object]
    locked_fields: List[str]          # fields held by the mandatory floor
    display: Dict[str, bool] = field(default_factory=dict)       # consent-scoped display permissions
    display_reasons: Dict[str, str] = field(default_factory=dict)


def _floor_and_defaults(context):
    tier = context.age_tier
    if context.policy.found and context.jurisdiction.code:
        rules = context.policy.policy.profile_visibility_rules.by_tier.get(tier)
        if rules is not None:
            policy_floor = rules.model_dump()
            defaults = {f: _more_private(f, policy_floor[f], _BUILTIN_DEFAULTS[tier][f]) for f in ALL_FIELDS}
            return policy_floor, defaults, "POLICY", context.policy.policy_version
    return dict(_BUILTIN_FLOOR[tier]), dict(_BUILTIN_DEFAULTS[tier]), "BUILTIN_SOURCE_FLOOR", None


def validate_preferences(floor: Dict[str, object], prefs: Dict[str, object]) -> Dict[str, object]:
    unknown = [k for k in prefs if k not in ALL_FIELDS]
    if unknown:
        raise PrivacyPreferenceError(unknown)
    bad = []
    for k, v in prefs.items():
        if k == DM_FIELD:
            if v not in _DM_ORDER:
                bad.append(k)
                continue
        elif not isinstance(v, bool):
            bad.append(k)
            continue
        if _less_private_than(k, v, floor[k]):
            bad.append(k)
    if bad:
        raise PrivacyPreferenceError(bad)
    return prefs


def resolve_privacy(db: Session, user: User, *, on: date, at: Optional[datetime] = None) -> EffectivePrivacy:
    from app.services.guardian_consent import consent_requirement

    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()
    context = AgeAndContestPolicyEngine(db).context_for_user(user, on, profile)
    floor, defaults, source, version = _floor_and_defaults(context)
    row = db.query(UserPrivacyPreference).filter(UserPrivacyPreference.user_id == user.id).first()
    prefs = dict(row.preferences or {}) if row else {}
    effective = {}
    for f in ALL_FIELDS:
        chosen = prefs.get(f, defaults[f])
        # A stored preference that the CURRENT floor forbids (e.g. after a policy
        # change) is ignored: the floor always wins.
        effective[f] = _more_private(f, chosen, floor[f]) if not _less_private_than(f, chosen, floor[f]) else floor[f]
    locked = [f for f in ALL_FIELDS if _less_private_than(f, _NO_FLOOR[f], floor[f])]

    display, reasons = {}, {}
    for key, scope in DISPLAY_SCOPES.items():
        requirement, _ = consent_requirement(db, user, scope, on=on, at=at)
        display[key] = requirement in _ALLOWING
        reasons[key] = requirement.value
    return EffectivePrivacy(context.age_tier, source, version, effective, locked, display, reasons)


def set_preferences(db: Session, user: User, prefs: Dict[str, object], *, on: date) -> EffectivePrivacy:
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()
    context = AgeAndContestPolicyEngine(db).context_for_user(user, on, profile)
    floor, _, _, _ = _floor_and_defaults(context)
    validate_preferences(floor, prefs)
    row = db.query(UserPrivacyPreference).filter(UserPrivacyPreference.user_id == user.id).first()
    if row is None:
        row = UserPrivacyPreference(user_id=user.id, preferences=dict(prefs))
        db.add(row)
    else:
        row.preferences = {**(row.preferences or {}), **prefs}
    db.commit()
    return resolve_privacy(db, user, on=on)
