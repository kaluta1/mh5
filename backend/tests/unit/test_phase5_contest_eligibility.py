"""Phase 5: contest age eligibility, personal submission and nomination
(MyHigh5 Child/Teen Safety s.9-14, s.17, s.19, s.32).

Every policy, rule, user, guardian and consent here is SYNTHETIC. No real email
is sent, no guardian is really verified (ADMIN_DOCUMENT_REVIEW is enabled only
inside individual tests through monkeypatch, never globally), and no payment,
KYC-provider or financial action is triggered.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from app.core.child_safety import (
    AgeTier,
    ModerationState,
    ContentRating,
    ContestEligibilityReason as R,
    ContestEntryKind,
    DecisionBasis,
    EligibilityOutcome,
    EntryExposureStatus,
    GuardianConsentScope as S,
    GuardianRelationshipType,
    GuardianVerificationMethod,
    GuardianVerificationStatus,
    MetadataSafetyStatus,
    NominationWorkflowStep,
    NomineeAgeDeclaration as D,
    PolicyOperation,
    RightsStatus,
    SafetyConcern,
    SafetyStatus,
)
from app.core.config import settings
from app.core.media_metadata import has_hidden_metadata, strip_image_metadata
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.age_safety import AgeSafetyEvent, UserAgeProfile
from app.models.business_model import ReferralPoolAssignment, RevenueRecognition
from app.models.category import Category
from app.models.contest import Contest
from app.models.contest_eligibility import CategoryAgePolicy, ContestAgeEligibility, ContestEntrySafety
from app.models.contests import Contestant
from app.models.guardian import Guardian, GuardianConsent, GuardianRelationship
from app.models.media import Media
from app.models.payment import Deposit
from app.models.user import User
from app.schemas.contest_eligibility import ContestAgeRuleDefinition
from app.services import age_gate, contest_eligibility as ce, dob_service, guardian_consent as gc
from app.services.content_safety import ContentGate
from app.services.age_policy_engine import PolicyResolution, PolicyResolutionStatus, utc_today
from app.services.content_moderation import ContentFlag, FlagType, ModerationResult, Severity
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_age_policy_engine import add_policy

TODAY = utc_today()
NOW = datetime.utcnow()
EXPOSED = {S.CONTEST_ENTRY.value, S.PUBLIC_CREATIVE_DISPLAY.value, S.NAME_DISPLAY.value, S.CITY_COUNTRY_DISPLAY.value}


# ---------------------------------------------------------------------------
# helpers (synthetic data only)
# ---------------------------------------------------------------------------

def born(years: int, days: int = 0, on: date = TODAY) -> datetime:
    try:
        d = date(on.year - years, on.month, on.day)
    except ValueError:  # 29 Feb
        d = date(on.year - years, 3, 1)
    return datetime.combine(d + timedelta(days=days), datetime.min.time())


def person(db, age=None, *, country="Tanzania", admin=False, dob=None, **extra) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(email=f"p5_{uid}@example.com", hashed_password="unused", username=f"p5_{uid}", is_active=True,
             is_admin=admin, country=country, date_of_birth=dob or (born(age) if age is not None else None), **extra)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def contest(db, mode="participation", **extra) -> Contest:
    c = Contest(name=f"C {uuid.uuid4().hex[:6]}", contest_type="beauty", level="city", contest_mode=mode,
                requires_kyc=False, **extra)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def category(db) -> Category:
    uid = uuid.uuid4().hex[:6]
    c = Category(name=f"Cat {uid}", slug=f"cat-{uid}")
    db.add(c)
    db.commit()
    return c


def rule(db, kind="contest", scope_id=None, status="ACTIVE", version=1, **fields):
    model, col = ce.RULE_MODELS[kind]
    d = ContestAgeRuleDefinition(**fields)
    row = model(status=status, rule_version=version, **{col: scope_id}, **d.model_dump(mode="json"))
    db.add(row)
    db.commit()
    return row


def enforce(db, op, jurisdiction="TZ", enabled=True):
    return age_gate.set_enforcement(db, operation=op, jurisdiction=jurisdiction, enabled=enabled,
                                    reason="synthetic phase 5 test", actor_id=None)


# Phase 6 made content safety a separate publication gate. These Phase 5 tests
# are about PARTICIPATION eligibility, so when a test gives no content inputs
# the helpers supply an explicitly approved SYNTHETIC content decision. Tests
# that pass content inputs (text, moderation results, concerns, media) run the
# real Phase 6 classifier instead.
APPROVED_CONTENT = ContentGate(ModerationState.APPROVED, rating=ContentRating.GENERAL, human_review_required=False)
_UNSET = object()


def _content(content, inputs):
    return (None if inputs else APPROVED_CONTENT) if content is _UNSET else content


def submit(db, user, c=None, content=_UNSET, **inputs):
    return ce.evaluate_personal_submission(db, user, c, ce.EntryInputs(**inputs), today=TODAY, now=datetime.utcnow(),
                                           content=_content(content, inputs))


def nominate(db, nominator, c=None, declaration=None, nominee=None, content=_UNSET, **inputs):
    return ce.evaluate_nomination(db, nominator, c, ce.EntryInputs(**inputs), nominee_age_declaration=declaration,
                                  today=TODAY, now=datetime.utcnow(), nominee_user=nominee,
                                  content=_content(content, inputs))


def entry(db, submitter, decision, kind=ContestEntryKind.PERSONAL_SUBMISSION, c=None, declaration=None, **cols):
    """Create a contestant + safety record exactly as the endpoint does."""
    row = Contestant(user_id=submitter.id, season_id=c.id if c else None, contest_id=c.id if c else None,
                     title=cols.get("title", "Entry"), description=cols.get("description", "d"),
                     image_media_ids=cols.get("image_media_ids"), video_media_ids=cols.get("video_media_ids"),
                     entry_type="nomination" if kind == ContestEntryKind.NOMINATION else "participation",
                     is_active=decision.public, is_deleted=False)
    db.add(row)
    db.flush()
    safety = ce.record_new_entry(db, row, decision, kind=kind, submitted_by=submitter,
                                 contest_id=c.id if c else None, nominee_age_declaration=declaration,
                                 now=datetime.utcnow())
    db.commit()
    return row, safety


@pytest.fixture
def accept_admin_review(monkeypatch):
    """Isolated per-test configuration: never enabled globally."""
    monkeypatch.setattr(settings, "GUARDIAN_ACCEPTED_VERIFICATION_METHODS", "ADMIN_DOCUMENT_REVIEW")


def guardian_for(db, minor: User, *, respond=True) -> GuardianRelationship:
    """A synthetic guardian who used the emailed link (contact confirmed only)."""
    g = Guardian(email=f"g_{uuid.uuid4().hex[:6]}@example.com", email_hash=uuid.uuid4().hex)
    db.add(g)
    db.flush()
    rel = GuardianRelationship(guardian_id=g.id, minor_user_id=minor.id, requested_at=NOW,
                               responded_at=NOW if respond else None,
                               relationship_type=GuardianRelationshipType.PARENT.value if respond else None,
                               verification_status=(GuardianVerificationStatus.VERIFICATION_REQUIRED.value
                                                    if respond else GuardianVerificationStatus.PENDING.value))
    db.add(rel)
    db.commit()
    return rel


def verified_guardian(db, minor, scopes=()) -> GuardianRelationship:
    """Verification through the real Phase 4 service (requires accept_admin_review)."""
    admin = person(db, 40, admin=True)
    rel = guardian_for(db, minor)
    gc.admin_verify_relationship(db, rel, method=GuardianVerificationMethod.ADMIN_DOCUMENT_REVIEW,
                                 admin_id=admin.id, note="synthetic evidence reviewed")
    db.refresh(rel)
    for scope in scopes:
        gc.grant_additional_scope(db, rel, scope, actor_id=admin.id, now=datetime.utcnow() - timedelta(seconds=5))
    return rel


def adult_flag():
    return ModerationResult(False, 0.99, [ContentFlag(FlagType.ADULT, Severity.HIGH, 0.99, "nudity")], {})


def flag(kind):
    return ModerationResult(False, 0.9, [ContentFlag(kind, Severity.HIGH, 0.9, kind.value)], {})


def jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (32, 24), (10, 200, 10))
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = "SyntheticCam"
    exif[0x8825] = {1: "N", 2: (1.0, 2.0, 3.0), 3: "E", 4: (4.0, 5.0, 6.0)}
    buf = BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes(), comment=b"hidden comment")
    return buf.getvalue()


# ===========================================================================
# CORE ELIGIBILITY
# ===========================================================================

def test_adult_is_eligible_in_transition_mode(db):
    d = submit(db, person(db, 30))
    assert d.outcome == EligibilityOutcome.ELIGIBLE_PUBLIC and d.public
    assert d.basis == DecisionBasis.TRANSITION_NOT_ENFORCED and R.POLICY_NOT_ENFORCED in d.reasons
    assert not d.enforced and d.subject_age_tier == AgeTier.ADULT_18_PLUS


def test_minor_without_policy_is_held_for_consent_not_denied(db):
    d = submit(db, person(db, 15))
    assert d.outcome == EligibilityOutcome.HELD and not d.public
    assert R.GUARDIAN_CONSENT_REQUIRED in d.reasons
    assert {s.value for s in d.missing_consent_scopes} == EXPOSED


def test_minor_eligible_only_where_enforced_policy_allows(db):
    add_policy(db)  # SYNTHETIC TZ: parental_consent_age 16, personal_submission_minimum_age 15
    teen17 = person(db, 17)
    # Transition mode never waives consent, even with an ACTIVE policy.
    assert submit(db, teen17).outcome == EligibilityOutcome.HELD
    enforce(db, PolicyOperation.PERSONAL_SUBMISSION)
    d = submit(db, teen17)
    assert d.outcome == EligibilityOutcome.ELIGIBLE_PUBLIC and d.basis == DecisionBasis.JURISDICTION_POLICY
    # 15 is allowed to submit but is below parental_consent_age: held for consent.
    d15 = submit(db, person(db, 15))
    assert d15.outcome == EligibilityOutcome.HELD and R.GUARDIAN_CONSENT_REQUIRED in d15.reasons


def test_under_policy_minimum_is_held_when_enforced(db):
    add_policy(db)
    enforce(db, PolicyOperation.PERSONAL_SUBMISSION)
    d = submit(db, person(db, 14))
    assert d.outcome == EligibilityOutcome.HELD and R.POLICY_BELOW_MINIMUM_AGE in d.reasons and not d.public


def test_under_13_is_held_in_every_mode(db):
    for enforced in (False, True):
        if enforced:
            add_policy(db)
            enforce(db, PolicyOperation.PERSONAL_SUBMISSION)
        d = submit(db, person(db, 12))
        assert d.outcome == EligibilityOutcome.HELD and R.BELOW_PLATFORM_MINIMUM in d.reasons
        assert d.basis == DecisionBasis.PLATFORM_BASELINE and not d.public


def test_missing_dob_is_held_with_update_profile_next_step(db):
    d = submit(db, person(db, None))
    assert d.outcome == EligibilityOutcome.HELD and d.reasons[0] == R.AGE_REQUIRED and not d.public
    payload = d.client_payload()
    assert payload["next_step"] == "ADD_DATE_OF_BIRTH"
    assert "on hold" in payload["message"] and "date of birth" in payload["message"]
    # UNKNOWN never gains adult treatment, even in an unrestricted contest.
    assert d.subject_age_tier == AgeTier.UNKNOWN


def test_missing_dob_hold_is_released_after_the_member_adds_a_dob(db):
    user = person(db, None)
    row, safety = entry(db, user, submit(db, user))
    assert safety.exposure_status == "HELD" and row.is_active is False
    dob_service.submit_self_service_dob(db, user, born(30).date(), today=TODAY)  # hook re-evaluates
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "PUBLIC" and row.is_active is True
    assert user.id == safety.submitted_by_user_id and db.query(User).get(user.id) is not None  # account kept


def test_missing_dob_hold_stays_when_the_new_dob_still_fails_a_rule(db):
    c = contest(db, min_age=21)
    user = person(db, None)
    row, safety = entry(db, user, submit(db, user, c), c=c)
    dob_service.submit_self_service_dob(db, user, born(19).date(), today=TODAY)
    db.refresh(safety)
    assert safety.exposure_status == "HELD" and "BELOW_CONTEST_MINIMUM_AGE" in safety.reason_codes
    assert "AGE_REQUIRED" not in safety.reason_codes


def test_missing_policy_holds_when_enforced(db):
    enforce(db, PolicyOperation.PERSONAL_SUBMISSION)
    d = submit(db, person(db, 30))
    assert d.outcome == EligibilityOutcome.HELD and R.POLICY_UNSUPPORTED_JURISDICTION in d.reasons


@pytest.mark.parametrize("status", ["DRAFT", "WITHDRAWN"])
def test_draft_or_withdrawn_policy_never_applies(db, status):
    add_policy(db, status=status)
    enforce(db, PolicyOperation.PERSONAL_SUBMISSION)
    d = submit(db, person(db, 30))
    assert d.outcome == EligibilityOutcome.HELD and R.POLICY_UNSUPPORTED_JURISDICTION in d.reasons


def test_conflicting_policy_holds(db, monkeypatch):
    enforce(db, PolicyOperation.PERSONAL_SUBMISSION)
    monkeypatch.setattr("app.services.age_policy_engine.AgeAndContestPolicyEngine.resolve_policy",
                        lambda self, j, on: PolicyResolution(PolicyResolutionStatus.CONFLICT, j, on))
    d = submit(db, person(db, 30))
    assert d.outcome == EligibilityOutcome.HELD and R.POLICY_UNAVAILABLE in d.reasons


def test_unresolved_and_mismatched_jurisdiction(db):
    add_policy(db)  # TZ only
    enforce(db, PolicyOperation.PERSONAL_SUBMISSION, jurisdiction="*")
    assert R.POLICY_JURISDICTION_UNRESOLVED in submit(db, person(db, 30, country="Atlantis")).reasons
    kenyan = submit(db, person(db, 30, country="Kenya"))
    assert kenyan.outcome == EligibilityOutcome.HELD and R.POLICY_UNSUPPORTED_JURISDICTION in kenyan.reasons
    assert submit(db, person(db, 30)).outcome == EligibilityOutcome.ELIGIBLE_PUBLIC


def test_existing_contest_min_max_age_columns_are_enforced(db):
    c = contest(db, min_age=21, max_age=25)
    assert R.BELOW_CONTEST_MINIMUM_AGE in submit(db, person(db, 20), c).reasons
    assert R.ABOVE_CONTEST_MAXIMUM_AGE in submit(db, person(db, 30), c).reasons
    assert submit(db, person(db, 22), c).outcome == EligibilityOutcome.ELIGIBLE_PUBLIC
    assert submit(db, person(db, 20), c).outcome == EligibilityOutcome.HELD


def test_age_window_is_rechecked_while_held_but_not_after_activation(db):
    c = contest(db, min_age=21, max_age=25)
    early = person(db, dob=born(21, days=1))            # 21 tomorrow
    row, safety = entry(db, early, submit(db, early, c), c=c)
    assert safety.exposure_status == "HELD"
    ce.reevaluate_entry(db, safety, actor_id=None, trigger="synthetic birthday", today=TODAY + timedelta(days=1))
    assert safety.exposure_status == "PUBLIC"          # hold released once the rule is met
    late = person(db, dob=born(26, days=1))             # 25 today, 26 tomorrow
    row2, safety2 = entry(db, late, submit(db, late, c), c=c)
    assert safety2.exposure_status == "PUBLIC"
    ce.reevaluate_entry(db, safety2, actor_id=None, trigger="synthetic birthday", today=TODAY + timedelta(days=1))
    assert safety2.exposure_status == "PUBLIC"         # a birthday never removes an active participant


def test_invalid_legacy_contest_ages_fail_closed(db):
    c = contest(db, min_age=30, max_age=20)
    assert R.CONTEST_RULES_UNAVAILABLE in submit(db, person(db, 25), c).reasons


def test_adult_only_category_holds_minors_but_draft_rule_does_not_apply(db):
    cat = category(db)
    c = contest(db, category_id=cat.id)
    rule(db, "category", cat.id, status="DRAFT", adult_only=True, minor_participation_allowed=False)
    assert R.ADULT_ONLY_CATEGORY not in submit(db, person(db, 16), c).reasons  # draft ignored
    rule(db, "category", cat.id, adult_only=True, minor_participation_allowed=False)
    d = submit(db, person(db, 16), c)
    assert d.outcome == EligibilityOutcome.HELD and R.ADULT_ONLY_CATEGORY in d.reasons
    assert submit(db, person(db, 30), c).outcome == EligibilityOutcome.ELIGIBLE_PUBLIC
    # s.17 applies to nominators too.
    assert R.ADULT_ONLY_CATEGORY in nominate(db, person(db, 16), c, D.ADULT).reasons


def test_category_jurisdiction_override(db):
    cat = category(db)
    c = contest(db, category_id=cat.id)
    rule(db, "category", cat.id, minimum_age=16)
    rule(db, "category", cat.id, jurisdiction="TZ", minimum_age=13)
    assert R.BELOW_CONTEST_MINIMUM_AGE not in submit(db, person(db, 14), c).reasons            # TZ override
    assert R.BELOW_CONTEST_MINIMUM_AGE in submit(db, person(db, 14, country="Kenya"), c).reasons


def test_eligible_tiers_and_content_rating(db):
    c = contest(db)
    rule(db, "contest", c.id, eligible_age_tiers=["TEEN_16_17"])
    assert R.AGE_TIER_NOT_ELIGIBLE in submit(db, person(db, 30), c).reasons
    c2 = contest(db)
    rule(db, "contest", c2.id, content_age_rating="TEEN_16_PLUS")
    assert R.AGE_TIER_NOT_ELIGIBLE in submit(db, person(db, 14), c2).reasons


def test_minor_participation_not_allowed(db):
    c = contest(db)
    rule(db, "contest", c.id, minor_participation_allowed=False)
    assert R.MINOR_PARTICIPATION_NOT_ALLOWED in submit(db, person(db, 17), c).reasons


def test_invalid_stored_rule_fails_closed(db):
    c = contest(db)
    row = rule(db, "contest", c.id)
    row.eligible_age_tiers = ["UNKNOWN"]  # bypassing validation: must never apply
    db.commit()
    assert R.CONTEST_RULES_UNAVAILABLE in submit(db, person(db, 30), c).reasons


def test_rule_schema_rejects_unsafe_definitions():
    for bad in ({"adult_only": True}, {"eligible_age_tiers": ["UNKNOWN"]}, {"content_age_rating": "ADULT_18_PLUS"},
                {"minimum_age": 20, "maximum_age": 10}, {"jurisdiction": "XX"}, {"content_age_rating": "PROHIBITED"}):
        with pytest.raises(ValueError):
            ContestAgeRuleDefinition(**bad)


def test_birthday_boundary_is_dynamic(db):
    user = person(db, dob=born(18, days=1))  # turns 18 tomorrow
    assert submit(db, user).outcome == EligibilityOutcome.HELD
    tomorrow = ce.evaluate_personal_submission(db, user, None, ce.EntryInputs(), today=TODAY + timedelta(days=1),
                                               now=datetime.utcnow(), content=APPROVED_CONTENT)
    assert tomorrow.outcome == EligibilityOutcome.ELIGIBLE_PUBLIC


def test_age_review_state_holds(db):
    user = person(db, 30)
    db.add(UserAgeProfile(user_id=user.id, review_status="AGE_REVIEW_REQUIRED"))
    db.commit()
    d = submit(db, user)
    assert d.outcome == EligibilityOutcome.HELD and R.AGE_REVIEW_PENDING in d.reasons
    assert d.client_payload()["next_step"] == "CONTACT_SUPPORT"


def test_corrected_dob_reevaluates_held_entry(db):
    teen = person(db, 15)
    _, safety = entry(db, teen, submit(db, teen))
    assert safety.exposure_status == "HELD"
    admin = person(db, 45, admin=True)
    dob_service.admin_correct_dob(db, teen, born(25).date(), reason="synthetic correction", admin_id=admin.id,
                                  today=TODAY)
    db.refresh(safety)
    assert safety.exposure_status == "PUBLIC" and safety.subject_age_tier == "ADULT_18_PLUS"
    assert db.query(Contestant).get(safety.contestant_id).is_active is True


def test_kyc_never_substitutes_for_age_or_consent(db):
    minor = person(db, 15, is_verified=True, identity_verified=True, address_verified=True)
    assert submit(db, minor).outcome == EligibilityOutcome.HELD
    unknown = person(db, None, is_verified=True, identity_verified=True, address_verified=True)
    assert submit(db, unknown).reasons[0] == R.AGE_REQUIRED


def test_transition_mode_account_creation_is_not_contest_approval(db):
    teen = person(db, 14)
    db.add(UserAgeProfile(user_id=teen.id, registration_decision="POLICY_NOT_ENFORCED",
                          registration_policy_outcome="UNSUPPORTED_JURISDICTION"))
    db.commit()
    assert submit(db, teen).outcome == EligibilityOutcome.HELD


def test_rule_lifecycle_versioning_and_audit(db):
    c = contest(db)
    admin = person(db, 40, admin=True)
    d1 = ce.create_rule(db, "contest", c.id, ContestAgeRuleDefinition(minimum_age=21), admin_id=admin.id,
                        reason="synthetic rule v1")
    assert d1.status == "DRAFT" and submit(db, person(db, 20), c).public
    ce.change_rule_status(db, "contest", d1, activate=True, admin_id=admin.id, reason="activate v1", today=TODAY)
    assert R.BELOW_CONTEST_MINIMUM_AGE in submit(db, person(db, 20), c).reasons
    d2 = ce.create_rule(db, "contest", c.id, ContestAgeRuleDefinition(minimum_age=19), admin_id=admin.id,
                        reason="synthetic rule v2")
    assert d2.rule_version == 2
    ce.change_rule_status(db, "contest", d2, activate=True, admin_id=admin.id, reason="activate v2", today=TODAY)
    db.refresh(d1)
    assert d1.status == "WITHDRAWN" and submit(db, person(db, 20), c).public
    ce.change_rule_status(db, "contest", d2, activate=False, admin_id=admin.id, reason="withdraw v2", today=TODAY)
    assert submit(db, person(db, 18), c).public
    actions = {a.action for a in db.query(AuditTrail).filter(AuditTrail.table_name == "contest_age_eligibility")}
    assert {"AGE_RULE_CREATED", "AGE_RULE_ACTIVATED", "AGE_RULE_SUPERSEDED", "AGE_RULE_WITHDRAWN"} <= actions


def test_rule_activation_reevaluates_open_entries(db):
    c = contest(db)
    admin = person(db, 40, admin=True)
    adult = person(db, 30)
    row, safety = entry(db, adult, submit(db, adult, c), c=c)
    assert safety.exposure_status == "PUBLIC"
    r = ce.create_rule(db, "contest", c.id, ContestAgeRuleDefinition(eligible_age_tiers=["TEEN_16_17"]),
                       admin_id=admin.id, reason="synthetic teen-only")
    ce.change_rule_status(db, "contest", r, activate=True, admin_id=admin.id, reason="activate", today=TODAY)
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "HELD" and row.is_active is False and row.is_deleted is False


# ===========================================================================
# GUARDIAN CONSENT (Phase 4 integration)
# ===========================================================================

def test_guardian_required_and_absent(db):
    d = submit(db, person(db, 14))
    assert d.outcome == EligibilityOutcome.HELD and d.guardian_relationship_id is None
    assert d.client_payload()["next_step"] == "GUARDIAN_CONSENT"


def test_contact_confirmed_guardian_is_not_authority(db):
    teen = person(db, 14)
    rel = guardian_for(db, teen)  # used the email link only
    assert gc.contact_confirmed(rel) and not gc.authority_verified(rel)
    d = submit(db, teen)
    assert d.outcome == EligibilityOutcome.HELD and d.guardian_relationship_id is None


def test_fail_closed_while_no_verification_method_is_accepted(db):
    assert gc.accepted_verification_methods() == frozenset()
    teen = person(db, 14)
    rel = guardian_for(db, teen)
    admin = person(db, 40, admin=True)
    with pytest.raises(gc.GuardianFlowError) as exc:
        gc.admin_verify_relationship(db, rel, method=GuardianVerificationMethod.ADMIN_DOCUMENT_REVIEW,
                                     admin_id=admin.id, note="synthetic attempt")
    assert exc.value.code == "METHOD_NOT_ACCEPTED"
    assert submit(db, teen).outcome == EligibilityOutcome.HELD


def test_verified_authority_but_missing_scope(db, accept_admin_review):
    teen = person(db, 14)
    verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY])
    d = submit(db, teen)
    assert d.outcome == EligibilityOutcome.HELD
    assert {s.value for s in d.missing_consent_scopes} == EXPOSED - {S.CONTEST_ENTRY.value}


def test_one_scope_never_implies_another(db, accept_admin_review):
    teen = person(db, 14)
    verified_guardian(db, teen, scopes=[S.ACCOUNT_PARTICIPATION, S.PUBLICITY, S.PRIZE_ACCEPTANCE])
    d = submit(db, teen)
    assert {s.value for s in d.missing_consent_scopes} == EXPOSED


def test_correct_scopes_make_the_entry_public_and_grant_activates_held_entry(db, accept_admin_review):
    teen = person(db, 14)
    row, safety = entry(db, teen, submit(db, teen))
    assert row.is_active is False
    rel = verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY, S.PUBLIC_CREATIVE_DISPLAY, S.NAME_DISPLAY])
    db.refresh(safety)
    assert safety.exposure_status == "HELD" and safety.missing_consent_scopes == [S.CITY_COUNTRY_DISPLAY.value]
    gc.grant_additional_scope(db, rel, S.CITY_COUNTRY_DISPLAY, actor_id=None)  # hook re-evaluates
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "PUBLIC" and row.is_active is True
    assert safety.guardian_relationship_id == rel.id


def test_media_and_publicity_scopes_when_needed(db, accept_admin_review):
    teen = person(db, 14)
    media = Media(title="m", media_type="image", path="p", url="/api/v1/media/file/1/a.jpg", user_id=teen.id,
                  metadata_sanitized_at=NOW)
    db.add(media)
    db.commit()
    c = contest(db)
    rule(db, "contest", c.id, publicity_consent_required=True)
    verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY, S.PUBLIC_CREATIVE_DISPLAY, S.NAME_DISPLAY,
                                        S.CITY_COUNTRY_DISPLAY])
    d = submit(db, teen, c, image_media_ids=json.dumps([media.id]))
    assert {s.value for s in d.missing_consent_scopes} == {S.MEDIA_USE.value, S.PUBLICITY.value}


def test_withdrawn_consent_suspends_future_eligibility_and_keeps_history(db, accept_admin_review):
    teen = person(db, 14)
    rel = verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY, S.PUBLIC_CREATIVE_DISPLAY, S.NAME_DISPLAY,
                                              S.CITY_COUNTRY_DISPLAY])
    row, safety = entry(db, teen, submit(db, teen))
    assert safety.exposure_status == "PUBLIC" and row.is_active
    consent = db.query(GuardianConsent).filter(GuardianConsent.relationship_id == rel.id,
                                               GuardianConsent.consent_scope == S.NAME_DISPLAY.value).one()
    gc.withdraw_consent(db, consent, actor_id=None, reason="synthetic withdrawal")
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "HELD" and row.is_active is False and safety.suspended_at is not None
    assert db.query(GuardianConsent).filter(GuardianConsent.id == consent.id).one().withdrawal_status == "WITHDRAWN"
    assert row.is_deleted is False  # the participation record itself is kept
    assert db.query(AuditTrail).filter(AuditTrail.table_name == "contest_entry_safety",
                                       AuditTrail.action == "ENTRY_SUSPENDED").count() == 1


def test_expired_consent_is_not_valid(db, accept_admin_review):
    teen = person(db, 14)
    rel = verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY, S.PUBLIC_CREATIVE_DISPLAY, S.NAME_DISPLAY,
                                              S.CITY_COUNTRY_DISPLAY])
    db.query(GuardianConsent).filter(GuardianConsent.relationship_id == rel.id,
                                     GuardianConsent.consent_scope == S.CONTEST_ENTRY.value) \
        .update({"expires_at": datetime.utcnow() - timedelta(minutes=1)})
    db.commit()
    assert [s.value for s in submit(db, teen).missing_consent_scopes] == [S.CONTEST_ENTRY.value]


def test_revoked_guardian_relationship_invalidates_consent(db, accept_admin_review):
    teen = person(db, 14)
    rel = verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY, S.PUBLIC_CREATIVE_DISPLAY, S.NAME_DISPLAY,
                                              S.CITY_COUNTRY_DISPLAY])
    assert submit(db, teen).public
    rel.verification_status = GuardianVerificationStatus.REVOKED.value  # synthetic revocation
    rel.revoked_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert submit(db, teen).outcome == EligibilityOutcome.HELD


def test_guardian_is_never_the_nominator_sponsor_or_account_holder(db):
    adult_sponsor = person(db, 40)
    teen = person(db, 15, sponsor_id=adult_sponsor.id)
    d = submit(db, teen)
    assert d.outcome == EligibilityOutcome.HELD and d.guardian_relationship_id is None
    # The adult nominator of a declared-minor nominee gains no guardian role.
    nd = nominate(db, adult_sponsor, None, D.MINOR)
    assert nd.outcome == EligibilityOutcome.HELD and nd.guardian_relationship_id is None
    assert db.query(GuardianRelationship).count() == 0 and db.query(GuardianConsent).count() == 0


# ===========================================================================
# NOMINATION
# ===========================================================================

def test_unclaimed_nominee_is_held_even_when_declared_adult(db):
    d = nominate(db, person(db, 30), None, D.ADULT)
    assert d.outcome == EligibilityOutcome.HELD and not d.public
    assert R.NOMINEE_UNCLAIMED in d.reasons and d.rights_status == RightsStatus.PENDING
    assert d.workflow_step == NominationWorkflowStep.NOMINEE_CONTACT
    assert d.client_payload()["next_step"] == "SHARE_CLAIM_LINK"


def test_nomination_scope_must_be_stated_by_the_policy(db):
    """nomination_minimum_age: MyHigh5 never guesses which actor it applies to."""
    add_policy(db)  # SYNTHETIC TZ policy WITHOUT nomination_age_applies_to
    enforce(db, PolicyOperation.NOMINATION)
    d = nominate(db, person(db, 30), None, D.ADULT)
    assert R.POLICY_NOMINATION_SCOPE_UNDEFINED in d.reasons and d.outcome == EligibilityOutcome.HELD


@pytest.mark.parametrize("scope, nominator_age, nominator_held, nominee_held", [
    ("NOMINATOR", 13, True, False),   # nomination_minimum_age 14 applies to the nominator only
    ("NOMINEE", 13, False, True),     # ... to the nominee only
    ("BOTH", 13, True, True),
])
def test_nomination_scope_applies_only_to_the_stated_actor(db, accept_admin_review, scope, nominator_age,
                                                           nominator_held, nominee_held):
    add_policy(db, nomination_age_applies_to=scope, parental_consent_age=13)
    enforce(db, PolicyOperation.NOMINATION)
    young = person(db, nominator_age)
    d_nominator = nominate(db, young, None, D.ADULT)
    assert (R.POLICY_BELOW_MINIMUM_AGE in d_nominator.reasons) is nominator_held
    nominee = person(db, 13)
    d_nominee = nominate(db, person(db, 30), None, None, nominee=nominee)
    assert (R.POLICY_BELOW_MINIMUM_AGE in d_nominee.reasons) is nominee_held


def test_policy_schema_accepts_explicit_nomination_scope():
    from app.schemas.age_policy import AgePolicyDefinition
    from tests.unit.test_age_policy_engine import synthetic_definition

    assert AgePolicyDefinition.model_validate(synthetic_definition()).nomination_age_applies_to is None
    ok = AgePolicyDefinition.model_validate(synthetic_definition(nomination_age_applies_to="NOMINEE"))
    assert ok.nomination_age_applies_to.value == "NOMINEE"
    with pytest.raises(ValueError):
        AgePolicyDefinition.model_validate(synthetic_definition(nomination_age_applies_to="GUESS"))


def test_minor_nominee_is_held_at_the_start_of_the_workflow(db):
    d = nominate(db, person(db, 30), None, D.MINOR)
    assert d.outcome == EligibilityOutcome.HELD
    assert {R.NOMINEE_DECLARED_MINOR, R.GUARDIAN_CONSENT_REQUIRED, R.RIGHTS_CONFIRMATION_REQUIRED} <= set(d.reasons)
    assert d.workflow_step == NominationWorkflowStep.NOMINEE_CONTACT


@pytest.mark.parametrize("declaration", [None, D.UNKNOWN])
def test_unknown_age_nominee_is_held(db, declaration):
    d = nominate(db, person(db, 30), None, declaration)
    assert d.outcome == EligibilityOutcome.HELD and R.NOMINEE_AGE_UNDETERMINED in d.reasons


def test_unknown_age_nominator_is_held_until_dob_added(db):
    d = nominate(db, person(db, None), None, D.ADULT)
    assert d.outcome == EligibilityOutcome.HELD and R.AGE_REQUIRED in d.reasons


def test_declared_minor_in_adult_only_category_is_held(db):
    cat = category(db)
    c = contest(db, category_id=cat.id)
    rule(db, "category", cat.id, adult_only=True, minor_participation_allowed=False)
    d = nominate(db, person(db, 30), c, D.MINOR)
    assert d.outcome == EligibilityOutcome.HELD and R.ADULT_ONLY_CATEGORY in d.reasons


def test_nominator_and_nominee_are_different_people(db):
    nominator = person(db, 30)
    row, safety = entry(db, nominator, nominate(db, nominator, None, D.UNKNOWN), ContestEntryKind.NOMINATION,
                        declaration=D.UNKNOWN)
    admin = person(db, 40, admin=True)
    assert safety.submitted_by_user_id == nominator.id and safety.nominee_user_id is None
    assert safety.creative_owner_type == "NOMINEE" and safety.creative_owner_user_id is None
    with pytest.raises(ce.EntryReviewError) as exc:
        ce.admin_review(db, safety, action="LINK_NOMINEE_ACCOUNT", admin_id=admin.id, note="synthetic link",
                        today=TODAY, nominee_user_id=nominator.id)
    assert exc.value.code == "NOMINATOR_IS_NOT_NOMINEE"
    db.rollback()
    nominee = person(db, 28)
    ce.admin_review(db, safety, action="LINK_NOMINEE_ACCOUNT", admin_id=admin.id, note="synthetic link",
                    today=TODAY, nominee_user_id=nominee.id)
    db.refresh(safety)
    assert safety.nominee_user_id == nominee.id and safety.creative_owner_user_id == nominee.id
    assert safety.account_holder_user_id == nominator.id
    # Linked adult nominee: still held until rights are confirmed.
    assert safety.exposure_status == "HELD" and safety.workflow_step == "RIGHTS_CONFIRMATION"
    ce.admin_review(db, safety, action="CONFIRM_RIGHTS", admin_id=admin.id, note="synthetic rights", today=TODAY)
    assert safety.exposure_status == "PUBLIC"


def test_nominator_cannot_self_assert_guardian_authority(client, db, api_world):
    nominator = person(db, 35)
    c = api_world(mode="nomination")
    resp = client.post(f"/api/v1/contestants/{c.id}", headers=auth(nominator), json={
        "title": "Song", "description": "A song", "video_media_ids": json.dumps(["https://youtu.be/x1"]),
        "nominee_age_declaration": "MINOR", "i_am_the_guardian": True, "guardian_consent": ["CONTEST_ENTRY"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["public_status"] == "PENDING_REVIEW"
    safety = db.query(ContestEntrySafety).one()
    assert safety.guardian_relationship_id is None and safety.exposure_status == "HELD"
    assert db.query(GuardianRelationship).count() == 0 and db.query(GuardianConsent).count() == 0


def test_sponsor_nominator_never_becomes_guardian_of_linked_minor(db, accept_admin_review):
    sponsor = person(db, 40)
    teen = person(db, 15, sponsor_id=sponsor.id)
    row, safety = entry(db, sponsor, nominate(db, sponsor, None, D.MINOR), ContestEntryKind.NOMINATION,
                        declaration=D.MINOR)
    admin = person(db, 45, admin=True)
    ce.admin_review(db, safety, action="LINK_NOMINEE_ACCOUNT", admin_id=admin.id, note="synthetic link",
                    today=TODAY, nominee_user_id=teen.id)
    db.refresh(safety)
    assert safety.exposure_status == "HELD" and safety.workflow_step == NominationWorkflowStep.GUARDIAN_CONSENT.value
    assert safety.guardian_relationship_id is None and db.query(GuardianRelationship).count() == 0


def test_minor_nominee_workflow_consent_then_rights_then_public(db, accept_admin_review):
    nominator = person(db, 40)
    teen = person(db, 15)
    row, safety = entry(db, nominator, nominate(db, nominator, None, D.MINOR), ContestEntryKind.NOMINATION,
                        declaration=D.MINOR)
    admin = person(db, 45, admin=True)
    ce.admin_review(db, safety, action="LINK_NOMINEE_ACCOUNT", admin_id=admin.id, note="synthetic link",
                    today=TODAY, nominee_user_id=teen.id)
    rel = verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY, S.PUBLIC_CREATIVE_DISPLAY, S.NAME_DISPLAY,
                                              S.CITY_COUNTRY_DISPLAY])
    db.refresh(safety)
    # Consent alone is not enough: rights must be confirmed first (s.12).
    assert safety.exposure_status == "HELD"
    assert safety.workflow_step == NominationWorkflowStep.RIGHTS_CONFIRMATION.value
    ce.admin_review(db, safety, action="CONFIRM_RIGHTS", admin_id=admin.id, note="synthetic rights ok", today=TODAY)
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "PUBLIC" and row.is_active and safety.guardian_relationship_id == rel.id
    # Withdrawal prevents future eligibility; the nomination itself is kept.
    consent = db.query(GuardianConsent).filter(GuardianConsent.consent_scope == S.PUBLIC_CREATIVE_DISPLAY.value).one()
    gc.withdraw_consent(db, consent, actor_id=None, reason="synthetic withdrawal")
    db.refresh(safety)
    db.refresh(row)
    assert safety.exposure_status == "HELD" and row.is_active is False and row.is_deleted is False


def test_historical_nominations_are_untouched(db):
    nominator = person(db, None)  # a legacy account without a DOB
    legacy = Contestant(user_id=nominator.id, entry_type="nomination", title="Legacy", is_active=True,
                        is_deleted=False)
    db.add(legacy)
    db.commit()
    assert ce.reevaluate_open_entries(db, trigger="synthetic", today=TODAY) == {"evaluated": 0, "changed": 0}
    db.refresh(legacy)
    assert legacy.is_active is True and ce.entry_publicly_visible(db, legacy.id)
    assert db.query(ContestEntrySafety).count() == 0


# ===========================================================================
# SUBMISSION SAFETY HOOKS
# ===========================================================================

@pytest.mark.parametrize("text, concern", [
    ("Call me on +255 712 345 678", SafetyConcern.PII_PHONE),
    ("write to kid.star@example.com", SafetyConcern.PII_EMAIL),
    ("We live at -6.79235, 39.20833", SafetyConcern.PRECISE_LOCATION),
    ("Come to 12 Uhuru Street after class", SafetyConcern.HOME_ADDRESS),
    ("I sing at Mzizima Secondary School", SafetyConcern.SCHOOL_INFORMATION),
])
def test_minor_pii_hooks_hold_for_review(db, text, concern):
    d = submit(db, person(db, 15), description=text)
    assert concern in d.safety_concerns and d.safety_status == SafetyStatus.REVIEW_REQUIRED
    assert R.SAFETY_REVIEW_REQUIRED in d.reasons and not d.public


def test_adult_pii_text_is_recorded_for_review_not_auto_approved(db):
    """Phase 6: findings are recorded for every subject; content is never
    auto-approved with a finding (the minor-only PII approval block is tested
    in the Phase 6 suite)."""
    d = submit(db, person(db, 30), description="Booking: +255 712 345 678, star@example.com")
    assert not d.public and d.participation_eligible
    assert {SafetyConcern.PII_PHONE, SafetyConcern.PII_EMAIL} <= set(d.safety_concerns)


def test_sexual_content_involving_a_minor_is_escalated_not_rated_adult(db):
    teen = person(db, 16)
    d = submit(db, teen, moderation_results=(adult_flag(),))
    assert SafetyConcern.CHILD_SEXUAL_CONTENT in d.safety_concerns
    assert d.exposure == EntryExposureStatus.CHILD_SAFETY_ESCALATED and not d.public
    assert d.safety_status == SafetyStatus.CHILD_SAFETY_ESCALATED
    assert all(getattr(c, "value", c) != ContentRating.ADULT_18_PLUS.value for c in d.safety_concerns)
    row, safety = entry(db, teen, d)
    event = db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type == "CHILD_SAFETY_ESCALATION").one()
    assert event.risk_flag is True and row.is_active is False
    # Never released by re-evaluation or an ordinary review.
    ce.reevaluate_entry(db, safety, actor_id=None, trigger="synthetic", today=TODAY)
    assert safety.exposure_status == "CHILD_SAFETY_ESCALATED"
    admin = person(db, 40, admin=True)
    for action in ("CLEAR_SAFETY_REVIEW", "CONFIRM_RIGHTS", "REEVALUATE"):
        with pytest.raises(ce.EntryReviewError):
            ce.admin_review(db, safety, action=action, admin_id=admin.id, note="synthetic try", today=TODAY)
        db.rollback()


def test_unknown_or_minor_nominee_sexual_content_is_escalated(db):
    d = nominate(db, person(db, 30), None, D.UNKNOWN, moderation_results=(adult_flag(),))
    assert d.exposure == EntryExposureStatus.CHILD_SAFETY_ESCALATED


def test_adult_sexual_content_is_not_a_child_safety_escalation(db):
    d = submit(db, person(db, 30), moderation_results=(adult_flag(),))
    assert SafetyConcern.CHILD_SEXUAL_CONTENT not in d.safety_concerns
    assert SafetyConcern.SEXUAL_CONTENT in d.safety_concerns and not d.public
    assert d.content.proposed_rating == ContentRating.ADULT_18_PLUS


@pytest.mark.parametrize("kind, concern", [(FlagType.VIOLENCE, SafetyConcern.VIOLENCE),
                                           (FlagType.WEAPONS, SafetyConcern.WEAPONS),
                                           (FlagType.DRUGS, SafetyConcern.DANGEROUS_BEHAVIOR)])
def test_violence_and_dangerous_behaviour_hold_minor_entries(db, kind, concern):
    d = submit(db, person(db, 15), moderation_results=(flag(kind),))
    assert concern in d.safety_concerns and R.SAFETY_REVIEW_REQUIRED in d.reasons


def test_third_party_rights_concern_holds_until_confirmed(db):
    adult = person(db, 30)
    d = submit(db, adult, extra_concerns=frozenset({SafetyConcern.THIRD_PARTY_RIGHTS}))
    assert d.rights_status == RightsStatus.PENDING and R.RIGHTS_CONFIRMATION_REQUIRED in d.reasons
    row, safety = entry(db, adult, d)
    admin = person(db, 40, admin=True)
    ce.admin_review(db, safety, action="CONFIRM_RIGHTS", admin_id=admin.id, note="synthetic license", today=TODAY)
    assert safety.exposure_status == "HELD"  # Phase 6: content still needs a moderation decision
    from app.services import content_safety as cs
    cs.moderate(db, cs.moderation_for(db, row.id), action="APPROVE", actor=admin, reason="SYNTHETIC_OK",
                rating=ContentRating.GENERAL, today=TODAY)
    db.refresh(safety)
    assert safety.exposure_status == "PUBLIC"


def test_admin_flag_and_clear_safety_review(db):
    adult = person(db, 30)
    row, safety = entry(db, adult, submit(db, adult))
    admin = person(db, 40, admin=True)
    ce.admin_review(db, safety, action="FLAG_CONCERN", concern=SafetyConcern.VIOLENCE, admin_id=admin.id,
                    note="synthetic flag", today=TODAY)
    assert safety.exposure_status == "HELD" and row.is_active is False
    ce.admin_review(db, safety, action="CLEAR_SAFETY_REVIEW", admin_id=admin.id, note="synthetic clear", today=TODAY)
    # Phase 6: clearing a finding revokes nothing and approves nothing; a new approval is required.
    assert safety.exposure_status == "HELD"
    from app.services import content_safety as cs
    cs.moderate(db, cs.moderation_for(db, row.id), action="APPROVE", actor=admin, reason="SYNTHETIC_OK",
                rating=ContentRating.TEEN_16_PLUS, today=TODAY)
    db.refresh(safety)
    assert safety.exposure_status == "PUBLIC"
    ce.admin_review(db, safety, action="FLAG_CONCERN", concern=SafetyConcern.CHILD_SEXUAL_CONTENT,
                    admin_id=admin.id, note="synthetic escalation", today=TODAY)
    assert safety.exposure_status == "CHILD_SAFETY_ESCALATED"
    assert cs.moderation_for(db, row.id).child_safety_escalated is True


def test_jpeg_gps_exif_comment_and_trailing_images_are_stripped_orientation_kept():
    raw = jpeg_with_gps() + b"\xff\xd8\xff\xe1appended-secondary-image-with-exif"
    assert has_hidden_metadata(raw)
    clean, ok = strip_image_metadata(raw, "image/jpeg")
    assert ok and not has_hidden_metadata(clean)
    assert b"SyntheticCam" not in clean and b"hidden comment" not in clean and b"appended" not in clean
    with Image.open(BytesIO(clean)) as im:
        im.load()
        assert im.getexif().get(0x0112) == 6 and im.size == (32, 24)


@pytest.mark.parametrize("fmt, ctype", [("PNG", "image/png"), ("WEBP", "image/webp")])
def test_png_and_webp_metadata_stripped(fmt, ctype):
    img = Image.new("RGB", (16, 16))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (1.0, 2.0, 3.0)}
    buf = BytesIO()
    img.save(buf, fmt, exif=exif.tobytes())
    assert has_hidden_metadata(buf.getvalue())
    clean, ok = strip_image_metadata(buf.getvalue(), ctype)
    assert ok and not has_hidden_metadata(clean)


def test_unsupported_or_broken_images_are_reported_not_sanitized():
    buf = BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "GIF")
    assert strip_image_metadata(buf.getvalue(), "image/gif") == (buf.getvalue(), False)
    broken = b"\xff\xd8\xff\xe1\x00"
    assert strip_image_metadata(broken, "image/jpeg") == (broken, False)


def test_upload_endpoint_strips_and_flags_images(client, db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_TYPE", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    # Keep every media root (including the repo's backend/media mirror) inside tmp_path.
    monkeypatch.setattr("app.core.storage.media_storage_roots", lambda: [str(tmp_path)])
    user = person(db, 15)
    resp = client.post("/api/v1/media/upload", headers=auth(user),
                       files={"file": ("photo.jpg", jpeg_with_gps(), "image/jpeg")})
    assert resp.status_code == 200, resp.text
    media = db.query(Media).filter(Media.user_id == user.id).one()
    assert media.metadata_sanitized_at is not None
    stored = next(tmp_path.rglob("*.jpg")).read_bytes()
    assert not has_hidden_metadata(stored) and b"SyntheticCam" not in stored


def test_minor_entry_metadata_gate(db):
    teen = person(db, 15)
    clean = Media(title="a", media_type="image", path="p", url="/api/v1/media/file/9/a.jpg", user_id=teen.id,
                  metadata_sanitized_at=NOW)
    legacy = Media(title="b", media_type="image", path="p", url="/api/v1/media/file/9/b.jpg", user_id=teen.id)
    video = Media(title="v", media_type="video", path="p", url="/api/v1/media/file/9/v.mp4", user_id=teen.id)
    db.add_all([clean, legacy, video])
    db.commit()
    assert submit(db, teen, image_media_ids=json.dumps([clean.id])).metadata_status == MetadataSafetyStatus.SANITIZED
    held = submit(db, teen, image_media_ids=json.dumps([legacy.id]))
    assert held.metadata_status == MetadataSafetyStatus.UNRESOLVED and R.METADATA_UNRESOLVED in held.reasons
    assert submit(db, teen, video_media_ids=json.dumps([video.url])).metadata_status == MetadataSafetyStatus.UNRESOLVED
    ext = submit(db, teen, video_media_ids=json.dumps(["https://www.youtube.com/watch?v=abc"]))
    assert ext.metadata_status == MetadataSafetyStatus.NOT_REQUIRED
    # Adults: the minor metadata HOLD does not apply (the finding is recorded for content review instead).
    adult = submit(db, person(db, 30), image_media_ids=json.dumps([legacy.id]))
    assert adult.metadata_status == MetadataSafetyStatus.NOT_REQUIRED
    assert SafetyConcern.METADATA_UNVERIFIED in adult.safety_concerns


# ===========================================================================
# API, PUBLIC EXPOSURE, AUDIT, FINANCIAL ISOLATION
# ===========================================================================

@pytest.fixture
def api_world(db, monkeypatch):
    """A contest with an open synthetic round; external services stubbed."""
    from app import crud
    from app.models.round import Round
    from app.services.content_moderation import content_moderation_service
    from app.services.content_relevance import content_relevance_service
    from app.services.contest_status import contest_status_service

    approved = ModerationResult(True, 1.0, [], {})
    monkeypatch.setattr(content_moderation_service, "is_configured", lambda: True)  # in-process stub only
    monkeypatch.setattr(content_moderation_service, "moderate_text", lambda text: approved)
    monkeypatch.setattr(content_moderation_service, "moderate_image", lambda url: approved)
    monkeypatch.setattr(content_moderation_service, "moderate_video", lambda url: approved)
    monkeypatch.setattr(content_relevance_service, "check_relevance",
                        lambda **kw: SimpleNamespace(is_relevant=True, score=1.0, suggestions=[]))
    monkeypatch.setattr(contest_status_service, "check_submission_allowed", lambda db_, cid: (True, None))

    def make(mode="participation", **extra):
        c = contest(db, mode, **extra)
        month = TODAY.replace(day=1)
        rnd = Round(name=f"R {uuid.uuid4().hex[:4]}", contest_id=c.id, submission_start_date=month,
                    submission_end_date=month + timedelta(days=40))
        db.add(rnd)
        db.commit()
        monkeypatch.setattr(crud.round, "get_active_round_for_contest", lambda db_, cid: rnd)
        monkeypatch.setattr(crud.round, "get_preferred_nomination_round_for_contest", lambda db_, cid: rnd)
        return c
    return make


def _post(client, user, c, **body):
    payload = {"title": "My song", "description": "My performance",
               "video_media_ids": json.dumps([f"https://youtu.be/{uuid.uuid4().hex[:8]}"])}
    payload.update(body)
    return client.post(f"/api/v1/contestants/{c.id}", headers=auth(user), json=payload)


def test_api_adult_submission_is_public(client, db, api_world):
    """Adult, fully covered, safe content is public at once. (Phase 6: an external
    video link cannot be classified, so that entry waits for human review.)"""
    c = api_world()
    resp = _post(client, person(db, 30), c, title="Morning song", description="An acoustic cover",
                 video_media_ids=None)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["public_status"] == "PUBLIC" and body["message"] == "Submission created successfully."
    contestant = db.query(Contestant).one()
    assert contestant.is_active is True
    assert db.query(ContestEntrySafety).one().exposure_status == "PUBLIC"
    yt = _post(client, person(db, 30), api_world())  # YouTube link
    assert yt.status_code == 200 and yt.json()["public_status"] == "PENDING_REVIEW"


def test_api_minor_submission_is_held_and_hidden(client, db, api_world):
    c = api_world()
    teen = person(db, 15)
    resp = _post(client, teen, c)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["public_status"] == "PENDING_REVIEW" and body["next_step"] == "GUARDIAN_CONSENT"
    text = resp.text
    assert "date_of_birth" not in text and "TEEN_" not in text and "15" not in json.dumps(body["eligibility_reasons"])
    contestant = db.query(Contestant).one()
    assert contestant.is_active is False
    stranger = person(db, 30)
    assert client.get(f"/api/v1/contestants/{contestant.id}", headers=auth(stranger)).status_code == 404
    assert client.post(f"/api/v1/contestants/{contestant.id}/vote", headers=auth(stranger)).status_code == 404
    listed = db.query(Contestant.id).filter(ce.public_entry_clause()).all()
    assert contestant.id not in {i for (i,) in listed}
    own = client.get(f"/api/v1/contest-eligibility/entries/{contestant.id}", headers=auth(teen))
    assert own.status_code == 200 and own.json()["public_status"] == "PENDING_REVIEW"
    assert client.get(f"/api/v1/contest-eligibility/entries/{contestant.id}",
                      headers=auth(stranger)).status_code == 404


def test_api_missing_dob_creates_a_held_entry_and_keeps_the_account(client, db, api_world):
    c = api_world()
    user = person(db, None)
    resp = _post(client, user, c)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["public_status"] == "PENDING_REVIEW" and body["next_step"] == "ADD_DATE_OF_BIRTH"
    assert "AGE_REQUIRED" in body["eligibility_reasons"] and "on hold" in body["message"]
    contestant = db.query(Contestant).one()
    assert contestant.is_active is False and contestant.is_deleted is False
    assert db.query(ContestEntrySafety).one().exposure_status == "HELD"
    assert db.query(User).filter(User.id == user.id, User.is_active.is_(True)).count() == 1
    # The member updates the profile DOB through the normal endpoint: automatic re-evaluation.
    upd = client.put("/api/v1/users/me", headers=auth(user), json={"date_of_birth": born(30).date().isoformat()})
    assert upd.status_code == 200, upd.text
    db.expire_all()
    safety = db.query(ContestEntrySafety).one()
    # Participation hold released; the content (possibly-minor at submission, not sent to the provider)
    # still needs a moderation decision - Phase 6 independent gate.
    assert "AGE_REQUIRED" not in safety.reason_codes and safety.exposure_status == "HELD"
    assert [c for c in safety.reason_codes if c != "POLICY_NOT_ENFORCED"] == ["CONTENT_REVIEW_REQUIRED"]
    from app.services import content_safety as cs
    cs.moderate(db, cs.moderation_for(db, contestant.id), action="APPROVE", actor=person(db, 40, admin=True),
                reason="SYNTHETIC_OK", rating=ContentRating.GENERAL, today=TODAY)
    db.expire_all()
    assert db.query(ContestEntrySafety).one().exposure_status == "PUBLIC"
    assert db.query(Contestant).one().is_active is True


def test_api_nominations_are_held_with_a_one_time_claim_token(client, db, api_world):
    c = api_world(mode="nomination")
    nominator = person(db, 30)
    resp = _post(client, nominator, c, nominee_age_declaration="ADULT")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["public_status"] == "PENDING_REVIEW" and body["next_step"] == "SHARE_CLAIM_LINK"
    token = body["nominee_claim_token"]
    assert token and len(token) >= 40
    row = db.query(ContestEntrySafety).one()
    assert row.claim_token_hash and token not in json.dumps(ce._state(row)) and row.claim_token_hash != token
    audit = json.dumps([a.new_values for a in db.query(AuditTrail)], default=str)
    assert token not in audit
    c2 = api_world(mode="nomination")
    minor = _post(client, nominator, c2, nominee_age_declaration="MINOR")
    assert minor.json()["public_status"] == "PENDING_REVIEW"
    bad = _post(client, nominator, c2, nominee_age_declaration="I_AM_THE_PARENT")
    assert bad.status_code == 422


def test_api_minor_sexual_content_goes_to_child_safety_escalation(client, db, api_world, monkeypatch):
    from app.services.content_moderation import content_moderation_service

    c = api_world()
    calls = []
    monkeypatch.setattr(content_moderation_service, "moderate_video", lambda url: calls.append(url) or adult_flag())
    # Default: a minor's media is NOT sent to the external provider at all (held for review).
    resp = _post(client, person(db, 16), c)
    assert resp.status_code == 200 and resp.json()["public_status"] == "PENDING_REVIEW" and calls == []
    # Only with explicit approval to use the provider for minors does its signal reach the pipeline.
    monkeypatch.setattr(settings, "CONTENT_MODERATION_EXTERNAL_FOR_MINORS", True)
    resp = _post(client, person(db, 16), api_world())
    assert resp.status_code == 200, resp.text
    assert resp.json()["public_status"] == "PENDING_REVIEW" and len(calls) == 1
    assert "CHILD_SAFETY" not in resp.text  # internal classification never reaches the member
    escalated = [r for r in db.query(ContestEntrySafety) if r.exposure_status == "CHILD_SAFETY_ESCALATED"]
    assert len(escalated) == 1
    # Adults keep the existing moderation rejection.
    adult = _post(client, person(db, 30), api_world())
    assert adult.status_code == 422


def test_api_update_of_escalated_entry_is_locked(client, db, api_world):
    c = api_world()
    teen = person(db, 16)
    d = submit(db, teen, c, moderation_results=(adult_flag(),))
    row, safety = entry(db, teen, d, c=c)
    resp = client.put(f"/api/v1/contestants/{row.id}", headers=auth(teen),
                      json={"title": "x", "description": "y"})
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "CONTEST_ENTRY_LOCKED"


def test_api_precheck(client, db, api_world):
    c = api_world()
    teen = person(db, 15)
    ok = client.get(f"/api/v1/contest-eligibility/contests/{c.id}", headers=auth(teen))
    assert ok.status_code == 200 and ok.json()["can_start"] is True and ok.json()["will_be_held"] is True
    assert "TEEN" not in ok.text and "date_of_birth" not in ok.text
    no = client.get(f"/api/v1/contest-eligibility/contests/{c.id}", headers=auth(person(db, None)))
    assert no.json()["can_start"] is True and no.json()["will_be_held"] is True
    assert no.json()["next_step"] == "ADD_DATE_OF_BIRTH"
    adult = client.get(f"/api/v1/contest-eligibility/contests/{c.id}", headers=auth(person(db, 30)))
    # Phase 6: content is unknown before submission, so review may still be needed.
    assert adult.json()["will_be_held"] is True and "AGE_REQUIRED" not in adult.json()["reason_codes"]


def test_admin_endpoints(client, db, api_world):
    c = api_world()
    admin = person(db, 40, admin=True)
    member = person(db, 30)
    body = {"minimum_age": 18, "reason": "synthetic adult rule"}
    assert client.post(f"/api/v1/admin/contest-eligibility/contest/{c.id}/age-rules", headers=auth(member),
                       json=body).status_code == 403
    created = client.post(f"/api/v1/admin/contest-eligibility/contest/{c.id}/age-rules", headers=auth(admin),
                          json=body)
    assert created.status_code == 201 and created.json()["status"] == "DRAFT", created.text
    rid = created.json()["id"]
    act = client.post(f"/api/v1/admin/contest-eligibility/age-rules/contest/{rid}/activate", headers=auth(admin),
                      json={"reason": "activate synthetic"})
    assert act.status_code == 200 and act.json()["status"] == "ACTIVE"
    assert client.post(f"/api/v1/admin/contest-eligibility/contest/{c.id}/age-rules", headers=auth(admin),
                       json={"adult_only": True, "reason": "unsafe"}).status_code == 422
    teen = person(db, 16)
    _post(client, teen, c)  # held by the new rule
    _post(client, teen, api_world())  # held for guardian consent
    listed = client.get("/api/v1/admin/contest-eligibility/entries", headers=auth(admin))
    assert listed.status_code == 200 and len(listed.json()) == 2
    item = listed.json()[0]
    assert "date_of_birth" not in item and "email" not in json.dumps(item)
    assert "claim_token" not in json.dumps(listed.json())
    rev = client.post(f"/api/v1/admin/contest-eligibility/entries/{item['id']}/review", headers=auth(admin),
                      json={"action": "FLAG_CONCERN", "concern": "SCHOOL_INFORMATION", "note": "synthetic flag"})
    assert rev.status_code == 200 and "SCHOOL_INFORMATION" in rev.json()["safety_concerns"]
    assert client.post("/api/v1/admin/contest-eligibility/entries/reevaluate",
                       headers=auth(admin)).json()["evaluated"] == 2


def test_audit_records_codes_only(db, accept_admin_review):
    teen = person(db, dob=datetime(2011, 4, 5))
    entry(db, teen, submit(db, teen, description="call +255 712 345 678"))
    dumped = json.dumps([[a.old_values, a.new_values] for a in db.query(AuditTrail)
                         .filter(AuditTrail.table_name == "contest_entry_safety")], default=str)
    dumped += json.dumps([e.details for e in db.query(AgeSafetyEvent)], default=str)
    for secret in ("2011", "04-05", "date_of_birth", "712 345", "+255", "call"):
        assert secret not in dumped


def test_contest_entry_decisions_never_touch_financial_records(db, accept_admin_review):
    tables = (Deposit, AffiliateCommission, ReferralPoolAssignment, RevenueRecognition, JournalEntry)
    before = [db.query(t).count() for t in tables]
    adult, teen = person(db, 30), person(db, 14)
    entry(db, adult, submit(db, adult))
    row, safety = entry(db, teen, submit(db, teen))
    rel = verified_guardian(db, teen, scopes=[S.CONTEST_ENTRY, S.PUBLIC_CREATIVE_DISPLAY, S.NAME_DISPLAY,
                                              S.CITY_COUNTRY_DISPLAY])
    ce.reevaluate_open_entries(db, trigger="synthetic", today=TODAY)
    assert [db.query(t).count() for t in tables] == before
    assert rel is not None


def test_enforcement_can_be_switched_on_only_for_approved_operations(db):
    for op in (PolicyOperation.PERSONAL_SUBMISSION, PolicyOperation.NOMINATION):
        assert enforce(db, op).enabled is True
    with pytest.raises(ValueError):
        enforce(db, PolicyOperation.VOTING)  # Phase 8
    with pytest.raises(ValueError):
        enforce(db, PolicyOperation.PRIZE_CONTRACT)  # Phase 10


def test_frontend_participate_route_carries_the_nominee_declaration(client, db, api_world):
    """/contests/{id}/participate (used by the web app) delegates to the same gate."""
    nominator = person(db, 30)
    c = api_world(mode="nomination")
    base = {"title": "Song", "description": "A song", "video_media_ids": ["https://youtu.be/p5route1"]}
    held = client.post(f"/api/v1/contests/{c.id}/participate", headers=auth(nominator),
                       json={**base, "nominee_age_declaration": "ADULT"})
    assert held.status_code == 201, held.text
    assert held.json()["public_status"] == "PENDING_REVIEW" and held.json()["nominee_claim_token"]
    assert db.query(ContestEntrySafety).one().nominee_age_declaration == "ADULT"
    c2 = api_world()
    missing_dob = client.post(f"/api/v1/contests/{c2.id}/participate", headers=auth(person(db, None)),
                              json={**base, "video_media_ids": ["https://youtu.be/p5route3"]})
    assert missing_dob.status_code == 201 and missing_dob.json()["next_step"] == "ADD_DATE_OF_BIRTH"




# ===========================================================================
# NOMINEE CLAIM (single-use, hashed, expiring; actor separation)
# ===========================================================================

def _held_nomination(db, nominator=None, declaration=D.ADULT):
    nominator = nominator or person(db, 30)
    row, safety = entry(db, nominator, nominate(db, nominator, None, declaration), ContestEntryKind.NOMINATION,
                        declaration=declaration)
    token = ce.issue_claim_token(db, safety, actor_id=nominator.id)
    return nominator, row, safety, token


def _claim(client, user, token, decision="ACCEPT"):
    return client.post("/api/v1/contest-eligibility/claims/respond", headers=auth(user),
                       json={"token": token, "decision": decision})


def test_claim_token_is_stored_hashed_and_expires(db):
    import hashlib

    _, _, safety, token = _held_nomination(db)
    assert safety.claim_token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(ce._state(safety))
    assert safety.claim_token_expires_at > datetime.utcnow() + timedelta(days=29)
    assert ce.claim_summary(db, token)["entry_title"] == "Entry"
    assert ce.claim_summary(db, token, now=datetime.utcnow() + timedelta(days=31)) is None


def test_adult_claim_links_the_nominee_confirms_rights_and_releases_the_hold(client, db):
    nominator, row, safety, token = _held_nomination(db)
    nominee = person(db, 27, email_verified=True)
    summary = client.post("/api/v1/contest-eligibility/claims/summary", headers=auth(nominee), json={"token": token})
    assert summary.status_code == 200 and "nominator" not in summary.text.lower()
    resp = _claim(client, nominee, token)
    assert resp.status_code == 200 and resp.json()["status"] == "ACCEPTED", resp.text
    db.expire_all()
    safety = db.query(ContestEntrySafety).one()
    assert safety.nominee_user_id == nominee.id and safety.creative_owner_user_id == nominee.id
    assert safety.rights_status == "CONFIRMED" and safety.exposure_status == "PUBLIC"
    assert safety.claim_token_hash is None and safety.claimed_at is not None
    assert safety.guardian_relationship_id is None and db.query(GuardianRelationship).count() == 0
    # Single use.
    assert _claim(client, person(db, 30, email_verified=True), token).status_code == 404


def test_nominator_and_account_holder_cannot_claim(client, db):
    nominator, _, safety, token = _held_nomination(db)
    nominator.email_verified = True
    db.commit()
    resp = _claim(client, nominator, token)
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "NOT_ALLOWED"
    db.refresh(safety)
    assert safety.nominee_user_id is None and safety.claim_token_hash is not None


def test_claim_requires_verified_email_and_generic_errors(client, db):
    _, _, _, token = _held_nomination(db)
    unverified = person(db, 30)
    assert _claim(client, unverified, token).json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"
    for bad in ("x" * 43, token + "tampered"):
        r = _claim(client, person(db, 30, email_verified=True), bad)
        # Same generic 404 for unknown, tampered, expired or used links (no oracle).
        assert r.status_code == 404 and token not in r.text and "nominat" not in r.text.lower()


def test_reissued_link_invalidates_the_previous_one(client, db):
    nominator, row, safety, token = _held_nomination(db)
    resp = client.post(f"/api/v1/contest-eligibility/entries/{row.id}/claim-link", headers=auth(nominator))
    assert resp.status_code == 200
    new = resp.json()["nominee_claim_token"]
    assert new != token
    assert ce.claim_summary(db, token) is None and ce.claim_summary(db, new) is not None
    other = person(db, 30)
    assert client.post(f"/api/v1/contest-eligibility/entries/{row.id}/claim-link",
                       headers=auth(other)).status_code == 404


def test_minor_claim_stays_held_for_guardian_consent_and_rights(client, db):
    _, _, safety, token = _held_nomination(db, declaration=D.MINOR)
    teen = person(db, 15, email_verified=True)
    resp = _claim(client, teen, token)
    assert resp.json()["next_step"] == "GUARDIAN_CONSENT"
    db.expire_all()
    safety = db.query(ContestEntrySafety).one()
    assert safety.nominee_user_id == teen.id and safety.exposure_status == "HELD"
    assert safety.rights_status == "PENDING" and safety.workflow_step == "GUARDIAN_CONSENT"
    assert safety.guardian_relationship_id is None and db.query(GuardianRelationship).count() == 0


def test_claimant_without_dob_stays_held_until_dob_added(client, db):
    _, _, _, token = _held_nomination(db)
    nominee = person(db, None, email_verified=True)
    assert _claim(client, nominee, token).json()["next_step"] == "ADD_DATE_OF_BIRTH"
    db.expire_all()
    safety = db.query(ContestEntrySafety).one()
    assert safety.exposure_status == "HELD" and "NOMINEE_AGE_UNDETERMINED" in safety.reason_codes
    dob_service.submit_self_service_dob(db, db.query(User).get(nominee.id), born(30).date(), today=TODAY)
    db.expire_all()
    safety = db.query(ContestEntrySafety).one()
    # The claim itself did not confirm rights (age unknown at claim time): still held for rights.
    assert "NOMINEE_AGE_UNDETERMINED" not in safety.reason_codes and safety.exposure_status == "HELD"
    assert safety.workflow_step == "RIGHTS_CONFIRMATION"


def test_declined_claim_keeps_the_record_and_holds(client, db):
    _, row, _, token = _held_nomination(db)
    resp = _claim(client, person(db, 30), token, decision="DECLINE")
    assert resp.status_code == 200 and resp.json()["status"] == "DECLINED"
    db.expire_all()
    safety = db.query(ContestEntrySafety).one()
    assert safety.exposure_status == "HELD" and "NOMINEE_DECLINED" in safety.reason_codes
    assert safety.rights_status == "DISPUTED" and safety.nominee_user_id is None
    assert db.query(Contestant).filter(Contestant.id == row.id, Contestant.is_deleted.is_(False)).count() == 1
    with pytest.raises(ce.ClaimError):
        ce.issue_claim_token(db, safety, actor_id=None)


def test_claim_route_is_rate_limited():
    from app.core.rate_limit import RATE_LIMITS

    assert "/api/v1/contest-eligibility/claims" in RATE_LIMITS


def test_unknown_is_never_adult_even_with_kyc_or_transition_registration(db):
    user = person(db, None, is_verified=True, identity_verified=True, address_verified=True)
    db.add(UserAgeProfile(user_id=user.id, registration_decision="POLICY_NOT_ENFORCED"))
    db.commit()
    for d in (submit(db, user), nominate(db, user, None, D.ADULT)):
        assert d.outcome == EligibilityOutcome.HELD and R.AGE_REQUIRED in d.reasons
        assert d.subject_age_tier != AgeTier.ADULT_18_PLUS or d.reasons[0] == R.AGE_REQUIRED
    assert user.date_of_birth is None  # never backfilled
