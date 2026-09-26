"""Phase 2: Age & Jurisdiction Policy Engine (MyHigh5 Child/Teen Safety s.2, 3, 5, 7,
15, 24, 25, 32).

All policies here are SYNTHETIC test data. They are not legal policy for any
country, and no production policy is created anywhere.
"""
from __future__ import annotations

import copy
import re
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.child_safety import (
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
from app.core.security import create_access_token
from app.models.accounting import AuditTrail
from app.models.age_policy import AgePolicy
from app.models.user import User
from app.schemas.age_policy import AgePolicyDefinition
from app.services import age_policy_admin
from app.services.age_policy_engine import (
    AgeAndContestPolicyEngine,
    DobEvidence,
    PolicyResolutionStatus,
)

E = AgeAndContestPolicyEngine
ON = date(2026, 9, 25)

_STRICT_PROFILE = {
    "high_privacy_default": True, "precise_location_visible": False, "location_sharing": False,
    "search_engine_indexing": False, "public_contact_information": False, "public_date_of_birth": False,
    "exact_age_visible": False, "profile_discovery_by_unrelated_adults": False,
    "unknown_adult_direct_messages": "PROHIBITED", "tagging_controls_enabled": True,
    "safety_notifications_enabled": True, "profiling_restricted": True,
}
_ADULT_PROFILE = {
    "high_privacy_default": False, "precise_location_visible": False, "location_sharing": False,
    "search_engine_indexing": True, "public_contact_information": False, "public_date_of_birth": False,
    "exact_age_visible": False, "profile_discovery_by_unrelated_adults": True,
    "unknown_adult_direct_messages": "ALLOWED", "tagging_controls_enabled": False,
    "safety_notifications_enabled": False, "profiling_restricted": False,
}


def synthetic_definition(**overrides) -> dict:
    """A valid SYNTHETIC policy (not legal advice or real policy)."""
    base = {
        "jurisdiction": "TZ",
        "effective_date": "2026-01-01",
        "minimum_account_age": 13,
        "minimum_independent_participation_age": 16,
        "parental_consent_age": 16,
        "adult_age": 18,
        "voting_minimum_age": 13,
        "nomination_minimum_age": 14,
        "personal_submission_minimum_age": 15,
        "livestream_minimum_age": 16,
        "prize_contract_age": 18,
        "payment_minimum_age": 17,
        "kyc_requirement": {"operations": ["PRIZE_CONTRACT", "PAYMENT"]},
        "age_assurance_level": {
            "default": "SELF_DECLARED_DOB",
            "operations": {"PRIZE_CONTRACT": "IDENTITY_AND_AGE_VERIFIED", "PAYMENT": "IDENTITY_AND_AGE_VERIFIED"},
        },
        "parental_consent_requirement": {"operations": ["ACCOUNT_CREATION", "PERSONAL_SUBMISSION", "NOMINATION"]},
        "permitted_content_ratings": {"by_tier": {
            "UNDER_13": ["GENERAL"],
            "TEEN_13_15": ["GENERAL", "TEEN_13_PLUS"],
            "TEEN_16_17": ["GENERAL", "TEEN_13_PLUS", "TEEN_16_PLUS"],
            "ADULT_18_PLUS": ["GENERAL", "TEEN_13_PLUS", "TEEN_16_PLUS", "ADULT_18_PLUS"],
            "UNKNOWN": ["GENERAL"],
        }},
        "advertising_restrictions": {"by_tier": {
            t: {"targeted_advertising_allowed": t == "ADULT_18_PLUS", "restricted_categories": []}
            for t in ("UNDER_13", "TEEN_13_15", "TEEN_16_17", "ADULT_18_PLUS", "UNKNOWN")
        }},
        "profile_visibility_rules": {"by_tier": {
            "UNDER_13": dict(_STRICT_PROFILE),
            "TEEN_13_15": dict(_STRICT_PROFILE),
            "TEEN_16_17": {**_STRICT_PROFILE, "unknown_adult_direct_messages": "RESTRICTED"},
            "ADULT_18_PLUS": dict(_ADULT_PROFILE),
            "UNKNOWN": dict(_STRICT_PROFILE),
        }},
        "notes": "SYNTHETIC TEST POLICY - not a legal policy",
    }
    for key, value in overrides.items():
        base[key] = value
    return base


def add_policy(db, *, status="ACTIVE", version=1, effective="2026-01-01", **overrides) -> AgePolicy:
    """Insert a row directly (bypassing admin lifecycle) for resolution tests."""
    d = AgePolicyDefinition.model_validate(synthetic_definition(effective_date=effective, **overrides))
    row = AgePolicy(policy_version=version, status=status)
    for key, value in d.model_dump(mode="json").items():
        setattr(row, key, d.effective_date if key == "effective_date" else value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def born(years_before: int, on: date = ON, days_delta: int = 0) -> date:
    from datetime import timedelta
    return date(on.year - years_before, on.month, on.day) + timedelta(days=days_delta)


def ctx(db, *, dob=None, country="TZ", level=AgeAssuranceLevel.SELF_DECLARED_DOB, on=ON):
    evidence = DobEvidence(dob, level) if dob else None
    return E(db).build_context(dob_evidence=evidence, jurisdiction_value=country, on=on)


# ===========================================================================
# AGE CALCULATION (1-9)
# ===========================================================================

def test_01_no_dob_is_unknown():
    assert E.calculate_age(None, ON) is None
    assert E.resolve_age_tier(None) == AgeTier.UNKNOWN


@pytest.mark.parametrize(
    "dob, expected_age, expected_tier",
    [
        (born(12), 12, AgeTier.UNDER_13),                         # 2: twelve
        (born(13, days_delta=1), 12, AgeTier.UNDER_13),           # day before 13th birthday
        (born(13), 13, AgeTier.TEEN_13_15),                       # 3: exact 13th birthday
        (born(15), 15, AgeTier.TEEN_13_15),                       # 4: fifteen
        (born(16, days_delta=1), 15, AgeTier.TEEN_13_15),         # day before 16th
        (born(16), 16, AgeTier.TEEN_16_17),                       # 5: exact 16th birthday
        (born(17), 17, AgeTier.TEEN_16_17),                       # 6: seventeen
        (born(18, days_delta=1), 17, AgeTier.TEEN_16_17),         # day before 18th
        (born(18), 18, AgeTier.ADULT_18_PLUS),                    # 7: exact 18th birthday
    ],
)
def test_02_to_07_age_boundaries(dob, expected_age, expected_tier):
    assert E.calculate_age(dob, ON) == expected_age
    assert E.resolve_age_tier(E.calculate_age(dob, ON)) == expected_tier


def test_08_leap_year_dob():
    dob = date(2008, 2, 29)
    assert E.calculate_age(dob, date(2026, 2, 28)) == 17        # non-leap year: birthday not reached yet
    assert E.calculate_age(dob, date(2026, 3, 1)) == 18
    assert E.calculate_age(dob, date(2024, 2, 29)) == 16        # leap year: exact birthday
    assert E.calculate_age(dob, date(2024, 2, 28)) == 15


def test_09_future_or_implausible_dob_is_unresolved():
    assert E.calculate_age(date(2030, 1, 1), ON) is None
    assert E.calculate_age(date(1850, 1, 1), ON) is None
    assert E.resolve_age_tier(E.calculate_age(date(2030, 1, 1), ON)) == AgeTier.UNKNOWN


def test_age_calculation_accepts_datetime_and_is_deterministic():
    assert E.calculate_age(datetime(2010, 9, 25, 23, 59), ON) == 16
    assert E.calculate_age(date(2010, 9, 25), date(2027, 9, 24)) == 16


# ===========================================================================
# JURISDICTION (10-14)
# ===========================================================================

def test_10_known_iso_code_resolves():
    r = E.resolve_jurisdiction("tz")
    assert (r.status, r.code, r.source) == (JurisdictionStatus.RESOLVED, "TZ", "ISO_CODE")


def test_11_legacy_country_name_resolves_without_rewriting_user_data():
    user = SimpleNamespace(country="  tanzania ", date_of_birth=None)
    r = E.resolve_jurisdiction(user.country)
    assert (r.status, r.code, r.source) == (JurisdictionStatus.RESOLVED, "TZ", "COUNTRY_NAME")
    assert user.country == "  tanzania "  # untouched


@pytest.mark.parametrize("value", ["Tanznia", "Dar es Salaam", "TZA", "Congo?", "UK", "Tanzania, Kenya", "123"])
def test_12_ambiguous_or_unknown_text_stays_unresolved(value):
    assert E.resolve_jurisdiction(value).status == JurisdictionStatus.UNRESOLVED
    assert E.resolve_jurisdiction(value).code is None


@pytest.mark.parametrize("value", [None, "", "   "])
def test_13_missing_jurisdiction_is_unknown(value):
    assert E.resolve_jurisdiction(value).status == JurisdictionStatus.UNKNOWN


def test_14_unsupported_jurisdiction_gets_no_fallback(db):
    add_policy(db)  # TZ only
    for country in ("Kenya", "Atlantis", None):
        c = ctx(db, dob=born(30), country=country)
        d = E(db).evaluate(c, PolicyOperation.VOTING)
        assert not d.allowed
        assert d.outcome in (PolicyOutcome.UNSUPPORTED_JURISDICTION, PolicyOutcome.UNKNOWN_JURISDICTION)
        assert not c.legal_adult and not c.adult_content_eligible
        assert E(db).permitted_content_ratings(c) == frozenset()


def test_jurisdiction_table_matches_member_country_list():
    """The trusted mapping must stay identical to frontend/lib/countries.ts."""
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "lib" / "countries.ts"
    if not path.exists():
        pytest.skip("frontend source not present")
    pairs = re.findall(r"\{\s*code:\s*'([A-Z]{2})',\s*name:\s*(['\"])(.*?)\2\s*\}", path.read_text(encoding="utf-8"))
    assert {code: name for code, _, name in pairs} == ISO_COUNTRY_NAMES
    assert len({n.casefold() for n in ISO_COUNTRY_NAMES.values()}) == len(ISO_COUNTRY_NAMES)


# ===========================================================================
# POLICY RESOLUTION (15-20)
# ===========================================================================

def test_15_effective_policy_resolves(db):
    p = add_policy(db)
    r = E(db).resolve_policy("TZ", ON)
    assert r.status == PolicyResolutionStatus.FOUND and r.policy_id == p.id and r.policy_version == 1


def test_16_future_policy_does_not_apply_early(db):
    v1 = add_policy(db, version=1, effective="2026-01-01")
    add_policy(db, version=2, effective="2026-12-01", voting_minimum_age=16)
    assert E(db).resolve_policy("TZ", date(2026, 11, 30)).policy_id == v1.id
    later = E(db).resolve_policy("TZ", date(2026, 12, 1))
    assert later.policy_version == 2 and later.policy.voting_minimum_age == 16


def test_16b_policy_not_yet_effective_at_all(db):
    add_policy(db, effective="2027-01-01")
    assert E(db).resolve_policy("TZ", ON).status == PolicyResolutionStatus.NOT_FOUND


@pytest.mark.parametrize("status", ["DRAFT", "WITHDRAWN"])
def test_17_inactive_policy_never_applies(db, status):
    add_policy(db, status=status)
    assert E(db).resolve_policy("TZ", ON).status == PolicyResolutionStatus.NOT_FOUND


def test_18_historical_policy_resolves_for_its_period(db):
    v1 = add_policy(db, version=1, effective="2025-01-01", voting_minimum_age=15)
    v2 = add_policy(db, version=2, effective="2026-01-01", voting_minimum_age=13)
    assert E(db).resolve_policy("TZ", date(2025, 6, 1)).policy_id == v1.id
    assert E(db).resolve_policy("TZ", date(2026, 6, 1)).policy_id == v2.id
    assert E(db).resolve_policy("TZ", date(2024, 12, 31)).status == PolicyResolutionStatus.NOT_FOUND
    fourteen_in_2025 = ctx(db, dob=date(2011, 1, 1), on=date(2025, 6, 1))
    assert E(db).evaluate(fourteen_in_2025, PolicyOperation.VOTING).outcome == PolicyOutcome.DENIED


def test_19_overlapping_active_policies_are_rejected_by_database(db):
    add_policy(db, version=1, effective="2026-01-01")
    with pytest.raises(IntegrityError):
        add_policy(db, version=2, effective="2026-01-01")
    db.rollback()


def test_19b_invalid_stored_policy_data_fails_closed(db):
    row = add_policy(db)
    row.permitted_content_ratings = {"by_tier": {"ADULT_18_PLUS": ["PROHIBITED"]}}  # corrupt directly
    db.commit()
    c = ctx(db, dob=born(30))
    assert c.policy.status == PolicyResolutionStatus.INVALID_DATA
    d = E(db).evaluate(c, PolicyOperation.VOTING)
    assert d.outcome == PolicyOutcome.POLICY_CONFLICT and not d.allowed


def test_19c_engine_detects_conflict_even_without_index():
    """Defense in depth: two ACTIVE rows with the same effective date (e.g. data
    that bypassed the unique index) resolve to CONFLICT, never to either row."""
    same_day = [SimpleNamespace(id=1, effective_date=date(2026, 1, 1), policy_version=1),
                SimpleNamespace(id=2, effective_date=date(2026, 1, 1), policy_version=2)]

    class _Query:
        def filter(self, *a, **k):
            return self

        order_by = limit = filter

        def all(self):
            return same_day

    engine = E(SimpleNamespace(query=lambda *a, **k: _Query()))
    assert engine.resolve_policy("TZ", ON).status == PolicyResolutionStatus.CONFLICT


def test_20_missing_policy_fails_safely(db):
    c = ctx(db, dob=born(40))
    d = E(db).evaluate(c, PolicyOperation.ACCOUNT_CREATION)
    assert d.outcome == PolicyOutcome.UNSUPPORTED_JURISDICTION and not d.allowed
    assert not c.legal_adult and not c.adult_content_eligible


# ===========================================================================
# POLICY SEMANTICS (21-30)
# ===========================================================================

@pytest.mark.parametrize(
    "operation, field",
    [
        (PolicyOperation.ACCOUNT_CREATION, "minimum_account_age"),                      # 21
        (PolicyOperation.INDEPENDENT_PARTICIPATION, "minimum_independent_participation_age"),  # 22
        (PolicyOperation.VOTING, "voting_minimum_age"),                                 # 24
        (PolicyOperation.NOMINATION, "nomination_minimum_age"),                         # 25
        (PolicyOperation.PERSONAL_SUBMISSION, "personal_submission_minimum_age"),       # 26
        (PolicyOperation.LIVESTREAM, "livestream_minimum_age"),                         # 27
        (PolicyOperation.PRIZE_CONTRACT, "prize_contract_age"),                         # 28
        (PolicyOperation.PAYMENT, "payment_minimum_age"),                               # 29
    ],
)
def test_21_to_29_operation_threshold_is_policy_driven(db, operation, field):
    threshold = 17
    overrides = {field: threshold}
    if field == "minimum_account_age":  # every other threshold must be >= the account age
        overrides.update({f: max(v, threshold) for f, v in synthetic_definition().items()
                          if f.endswith("_age") and isinstance(v, int)})
    add_policy(db, **overrides)
    strong = AgeAssuranceLevel.IDENTITY_AND_AGE_VERIFIED
    below = E(db).evaluate(ctx(db, dob=born(threshold, days_delta=1), level=strong), operation)
    at = E(db).evaluate(ctx(db, dob=born(threshold), level=strong), operation)
    assert below.outcome == PolicyOutcome.DENIED and below.reason == "below_minimum_age"
    assert at.outcome != PolicyOutcome.DENIED


def test_21b_under_13_can_never_create_account(db):
    add_policy(db)
    d = E(db).evaluate(ctx(db, dob=born(12)), PolicyOperation.ACCOUNT_CREATION)
    assert d.outcome == PolicyOutcome.DENIED and d.age_tier == AgeTier.UNDER_13
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(minimum_account_age=12, voting_minimum_age=12,
                                                                nomination_minimum_age=12, personal_submission_minimum_age=12))


def test_23_parental_consent_threshold(db):
    add_policy(db, parental_consent_age=16)
    engine = E(db)
    fifteen = engine.evaluate(ctx(db, dob=born(15)), PolicyOperation.PERSONAL_SUBMISSION)
    sixteen = engine.evaluate(ctx(db, dob=born(16)), PolicyOperation.PERSONAL_SUBMISSION)
    assert fifteen.outcome == PolicyOutcome.REQUIRES_GUARDIAN_CONSENT
    assert PolicyRequirement.GUARDIAN_CONSENT in fifteen.requirements
    assert sixteen.outcome == PolicyOutcome.ALLOWED
    # Operations not listed in parental_consent_requirement do not ask for consent.
    assert engine.evaluate(ctx(db, dob=born(15)), PolicyOperation.VOTING).outcome == PolicyOutcome.ALLOWED


def test_30_adult_threshold_is_policy_driven(db):
    add_policy(db, adult_age=21, minimum_independent_participation_age=16, prize_contract_age=21)
    nineteen = ctx(db, dob=born(19))
    assert nineteen.age_tier == AgeTier.ADULT_18_PLUS
    assert not nineteen.legal_adult and not nineteen.adult_content_eligible
    assert ContentRating.ADULT_18_PLUS not in E(db).permitted_content_ratings(nineteen)
    assert E(db).evaluate(nineteen, PolicyOperation.PRIZE_CONTRACT).outcome == PolicyOutcome.DENIED
    twentyone = ctx(db, dob=born(21))
    assert twentyone.legal_adult and twentyone.adult_content_eligible
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(adult_age=17))


def test_threshold_consistency_validation():
    with pytest.raises(ValidationError):  # operation below account age
        AgePolicyDefinition.model_validate(synthetic_definition(minimum_account_age=16))
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(parental_consent_age=19))
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(minimum_independent_participation_age=12))
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(jurisdiction="XX"))


# ===========================================================================
# SEPARATION OF CONCERNS (31-35)
# ===========================================================================

def test_31_kyc_verified_does_not_imply_adult(db):
    add_policy(db)
    engine = E(db)
    kyc_verified_no_dob = SimpleNamespace(date_of_birth=None, country="Tanzania",
                                          identity_verified=True, address_verified=True, is_verified=True)
    c = engine.context_for_user(kyc_verified_no_dob, ON)
    assert c.age_tier == AgeTier.UNKNOWN and not c.legal_adult
    kyc_verified_teen = SimpleNamespace(date_of_birth=datetime(2010, 1, 1), country="TZ",
                                        identity_verified=True, address_verified=True)
    c2 = engine.context_for_user(kyc_verified_teen, ON)
    assert c2.age_tier == AgeTier.TEEN_16_17 and not c2.adult_content_eligible
    # KYC state is never an input; a KYC requirement is only reported.
    d = engine.evaluate(c2, PolicyOperation.PAYMENT)
    assert PolicyRequirement.KYC in d.requirements


def test_31b_profile_dob_is_self_declared_and_kyc_dob_is_not_used():
    user = SimpleNamespace(date_of_birth=datetime(2000, 5, 5), kyc_verifications=[
        SimpleNamespace(verified_date_of_birth=datetime(1990, 1, 1))])
    ev = E.dob_evidence_for_user(user)
    assert ev.assurance_level == AgeAssuranceLevel.SELF_DECLARED_DOB and ev.date_of_birth == date(2000, 5, 5)


def test_32_unknown_age_never_gets_adult_privileges(db):
    add_policy(db)
    engine = E(db)
    c = ctx(db, dob=None)
    assert c.age_tier == AgeTier.UNKNOWN and not c.legal_adult and not c.adult_content_eligible
    for op in PolicyOperation:
        d = engine.evaluate(c, op)
        assert d.outcome == PolicyOutcome.UNKNOWN_AGE and not d.allowed
    assert ContentRating.ADULT_18_PLUS not in engine.permitted_content_ratings(c)


def test_33_missing_jurisdiction_never_gets_unrestricted_fallback(db):
    add_policy(db)
    for country in (None, "", "somewhere"):
        c = ctx(db, dob=born(40), country=country)
        for op in PolicyOperation:
            assert not E(db).evaluate(c, op).allowed
        assert not c.adult_content_eligible


def test_34_age_assurance_is_independent_of_kyc(db):
    add_policy(db)
    engine = E(db)
    self_declared_adult = ctx(db, dob=born(30), level=AgeAssuranceLevel.SELF_DECLARED_DOB)
    d = engine.evaluate(self_declared_adult, PolicyOperation.PRIZE_CONTRACT)
    assert d.outcome == PolicyOutcome.REQUIRES_AGE_ASSURANCE
    assert {PolicyRequirement.AGE_ASSURANCE, PolicyRequirement.KYC} <= d.requirements
    verified = ctx(db, dob=born(30), level=AgeAssuranceLevel.IDENTITY_AND_AGE_VERIFIED)
    ok = engine.evaluate(verified, PolicyOperation.PRIZE_CONTRACT)
    assert ok.outcome == PolicyOutcome.ALLOWED and PolicyRequirement.KYC in ok.requirements
    # A per-operation level can only strengthen the default, never weaken it.
    d2 = AgePolicyDefinition.model_validate(synthetic_definition(age_assurance_level={
        "default": "AGE_VERIFIED", "operations": {"VOTING": "SELF_DECLARED_DOB"}}))
    assert d2.age_assurance_level.required_for(PolicyOperation.VOTING) == AgeAssuranceLevel.AGE_VERIFIED


def test_35_guardian_consent_requirement_without_consent_implementation(db):
    add_policy(db)
    d = E(db).evaluate(ctx(db, dob=born(14)), PolicyOperation.NOMINATION)
    assert d.outcome == PolicyOutcome.REQUIRES_GUARDIAN_CONSENT and not d.allowed


def test_decision_exposes_no_dob_or_numeric_age(db):
    add_policy(db)
    d = E(db).evaluate(ctx(db, dob=date(2010, 3, 4)), PolicyOperation.VOTING)
    text = repr(d) + repr(d.__dict__)
    assert "2010" not in text and "age=" not in text.replace("age_tier", "")
    assert not hasattr(d, "date_of_birth")


# ===========================================================================
# CONTENT / POLICY CONFIG (36-39)
# ===========================================================================

def test_36_permitted_content_ratings_validate_and_resolve(db):
    add_policy(db)
    engine = E(db)
    assert engine.permitted_content_ratings(ctx(db, dob=born(14))) == {ContentRating.GENERAL, ContentRating.TEEN_13_PLUS}
    assert ContentRating.ADULT_18_PLUS not in engine.permitted_content_ratings(ctx(db, dob=born(17)))
    assert ContentRating.ADULT_18_PLUS in engine.permitted_content_ratings(ctx(db, dob=born(18)))
    ratings = copy.deepcopy(synthetic_definition()["permitted_content_ratings"])
    ratings["by_tier"].pop("UNKNOWN")
    with pytest.raises(ValidationError):  # every tier must be explicit
        AgePolicyDefinition.model_validate(synthetic_definition(permitted_content_ratings=ratings))


@pytest.mark.parametrize(
    "tier, rating",
    [
        ("ADULT_18_PLUS", "PROHIBITED"),     # 37: never permitted
        ("TEEN_16_17", "ADULT_18_PLUS"),     # minors never get 18+
        ("TEEN_13_15", "TEEN_16_PLUS"),
        ("UNKNOWN", "ADULT_18_PLUS"),        # unknown age never adult
        ("UNKNOWN", "TEEN_16_PLUS"),
        ("UNDER_13", "TEEN_13_PLUS"),
    ],
)
def test_37_prohibited_and_age_inappropriate_ratings_rejected(tier, rating):
    ratings = copy.deepcopy(synthetic_definition()["permitted_content_ratings"])
    ratings["by_tier"][tier] = ratings["by_tier"][tier] + [rating]
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(permitted_content_ratings=ratings))


def test_38_advertising_restrictions_validate():
    ads = copy.deepcopy(synthetic_definition()["advertising_restrictions"])
    ads["by_tier"]["TEEN_13_15"]["restricted_categories"] = ["GAMBLING", "ALCOHOL"]
    AgePolicyDefinition.model_validate(synthetic_definition(advertising_restrictions=ads))
    for tier in ("UNKNOWN", "UNDER_13"):
        bad = copy.deepcopy(ads)
        bad["by_tier"][tier]["targeted_advertising_allowed"] = True
        with pytest.raises(ValidationError):
            AgePolicyDefinition.model_validate(synthetic_definition(advertising_restrictions=bad))
    bad = copy.deepcopy(ads)
    bad["by_tier"]["ADULT_18_PLUS"]["restricted_categories"] = ["not a code"]
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(advertising_restrictions=bad))
    bad = copy.deepcopy(ads)
    bad["by_tier"]["ADULT_18_PLUS"]["unexpected"] = 1
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(advertising_restrictions=bad))


@pytest.mark.parametrize(
    "tier, key, value",
    [
        ("TEEN_13_15", "search_engine_indexing", True),
        ("TEEN_13_15", "public_date_of_birth", True),
        ("TEEN_13_15", "exact_age_visible", True),
        ("TEEN_13_15", "precise_location_visible", True),
        ("TEEN_13_15", "location_sharing", True),
        ("TEEN_13_15", "public_contact_information", True),
        ("TEEN_13_15", "unknown_adult_direct_messages", "ALLOWED"),
        ("TEEN_13_15", "profile_discovery_by_unrelated_adults", True),
        ("TEEN_13_15", "tagging_controls_enabled", False),
        ("TEEN_13_15", "safety_notifications_enabled", False),
        ("TEEN_13_15", "profiling_restricted", False),
        ("TEEN_16_17", "public_date_of_birth", True),
        ("TEEN_16_17", "search_engine_indexing", True),
        ("TEEN_16_17", "high_privacy_default", False),
        ("UNKNOWN", "exact_age_visible", True),
        ("UNKNOWN", "unknown_adult_direct_messages", "ALLOWED"),
    ],
)
def test_39_profile_visibility_rules_enforce_teen_protections(tier, key, value):
    rules = copy.deepcopy(synthetic_definition()["profile_visibility_rules"])
    rules["by_tier"][tier][key] = value
    with pytest.raises(ValidationError):
        AgePolicyDefinition.model_validate(synthetic_definition(profile_visibility_rules=rules))


def test_39b_valid_profile_rules_accepted():
    d = AgePolicyDefinition.model_validate(synthetic_definition())
    assert d.profile_visibility_rules.by_tier[AgeTier.TEEN_13_15].search_engine_indexing is False


# ===========================================================================
# ADMIN LIFECYCLE (versioning, history, audit)
# ===========================================================================

def _admin(db, admin=True):
    import uuid
    u = User(email=f"p2-{uuid.uuid4().hex[:8]}@example.com", hashed_password="unused", is_active=True, is_admin=admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_admin_lifecycle_versioning_and_audit(db):
    admin = _admin(db)
    today = date(2026, 9, 25)
    d1 = AgePolicyDefinition.model_validate(synthetic_definition(effective_date="2026-10-01"))
    p1 = age_policy_admin.create_draft(db, d1, actor_id=admin.id)
    assert (p1.policy_version, p1.status) == (1, "DRAFT")
    p1 = age_policy_admin.activate(db, p1, actor_id=admin.id, reason="synthetic activation", today=today)
    assert p1.status == "ACTIVE"
    with pytest.raises(age_policy_admin.AgePolicyAdminError):  # ACTIVE is immutable
        age_policy_admin.update_draft(db, p1, d1, actor_id=admin.id)

    p2 = age_policy_admin.create_draft(db, AgePolicyDefinition.model_validate(
        synthetic_definition(effective_date="2026-10-01")), actor_id=admin.id)
    assert p2.policy_version == 2
    with pytest.raises(age_policy_admin.AgePolicyAdminError):  # not later than existing ACTIVE
        age_policy_admin.activate(db, p2, actor_id=admin.id, reason="overlap attempt", today=today)
    p2 = age_policy_admin.update_draft(db, p2, AgePolicyDefinition.model_validate(
        synthetic_definition(effective_date="2026-11-01", voting_minimum_age=14)), actor_id=admin.id)
    p2 = age_policy_admin.activate(db, p2, actor_id=admin.id, reason="new version", today=today)

    engine = E(db)
    assert engine.resolve_policy("TZ", date(2026, 10, 15)).policy_version == 1
    assert engine.resolve_policy("TZ", date(2026, 11, 2)).policy_version == 2

    # Withdrawing a not-yet-in-force version restores the previous one for that period.
    age_policy_admin.withdraw(db, p2, actor_id=admin.id, reason="scheduled change cancelled", today=today)
    assert engine.resolve_policy("TZ", date(2026, 11, 2)).policy_version == 1
    # A version already in force cannot be withdrawn (history stays reproducible).
    with pytest.raises(age_policy_admin.AgePolicyAdminError):
        age_policy_admin.withdraw(db, p1, actor_id=admin.id, reason="try rewrite", today=date(2026, 10, 5))

    actions = [a.action for a in db.query(AuditTrail).filter(AuditTrail.table_name == "age_policies").order_by(AuditTrail.id)]
    assert actions == ["AGE_POLICY_CREATE", "AGE_POLICY_ACTIVATE", "AGE_POLICY_CREATE", "AGE_POLICY_UPDATE",
                       "AGE_POLICY_ACTIVATE", "AGE_POLICY_WITHDRAW"]


def test_admin_cannot_activate_retroactively(db):
    admin = _admin(db)
    p = age_policy_admin.create_draft(db, AgePolicyDefinition.model_validate(
        synthetic_definition(effective_date="2026-01-01")), actor_id=admin.id)
    with pytest.raises(age_policy_admin.AgePolicyAdminError):
        age_policy_admin.activate(db, p, actor_id=admin.id, reason="retroactive", today=ON)


def _payload(**overrides):
    return synthetic_definition(effective_date="2099-01-01", **overrides)


def test_admin_api_requires_admin(client, db):
    member = _admin(db, admin=False)
    headers = {"Authorization": f"Bearer {create_access_token(subject=member.id)}"}
    assert client.get("/api/v1/admin/age-policies").status_code == 401
    assert client.post("/api/v1/admin/age-policies", json=_payload()).status_code == 401
    assert client.get("/api/v1/admin/age-policies", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/age-policies", json=_payload(), headers=headers).status_code == 403
    assert db.query(AgePolicy).count() == 0


def test_admin_api_create_activate_resolve(client, db):
    admin = _admin(db)
    headers = {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}
    created = client.post("/api/v1/admin/age-policies", json=_payload(), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "DRAFT" and body["policy_version"] == 1 and body["jurisdiction"] == "TZ"
    bad = client.post("/api/v1/admin/age-policies", json=_payload(adult_age=16), headers=headers)
    assert bad.status_code == 422
    act = client.post(f"/api/v1/admin/age-policies/{body['id']}/activate", json={"reason": "synthetic test"}, headers=headers)
    assert act.status_code == 200 and act.json()["status"] == "ACTIVE"
    edit = client.put(f"/api/v1/admin/age-policies/{body['id']}", json=_payload(), headers=headers)
    assert edit.status_code == 409
    res = client.get("/api/v1/admin/age-policies/resolve", params={"jurisdiction": "Tanzania", "on_date": "2099-06-01"},
                     headers=headers)
    assert res.status_code == 200
    assert res.json()["policy_status"] == "FOUND" and res.json()["policy_version"] == 1


def test_engine_is_only_wired_into_approved_flows():
    """Phase 2 built the engine; Phase 3 wires it into registration and DOB updates;
    Phase 5 into contest entry (personal submission / nomination) eligibility.
    No other endpoint (voting, TopHigh5, media delivery, payments...) may consume
    it until its own phase."""
    import pathlib

    endpoints = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "api_v1" / "endpoints"
    users = sorted(p.name for p in endpoints.glob("*.py")
                   if "age_policy_engine" in p.read_text(encoding="utf-8"))
    assert users == ["age_policies.py", "age_safety.py", "auth.py", "contest_eligibility.py", "contestant.py",
                     "users.py"]
