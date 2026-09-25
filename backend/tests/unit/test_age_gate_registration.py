"""Phase 3: registration age gate, DOB handling/provenance, DOB change protection
and age-gate circumvention controls (MyHigh5 Child/Teen Safety s.2, s.4-7, s.32).

All policies are SYNTHETIC test data (see test_age_policy_engine.synthetic_definition).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.core.child_safety import (
    AgeAssuranceLevel,
    AgeSafetyEventType,
    AgeTier,
    PolicyOperation,
    PolicyOutcome,
    RegistrationDecision,
)
from app.core.security import create_access_token
from app.crud import user as crud_user
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.age_safety import AgeSafetyEvent, ChildSafetyEnforcement, DobChangeRecord, UserAgeProfile
from app.models.business_model import ReferralPoolAssignment, RevenueRecognition
from app.models.payment import Deposit
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import age_gate, dob_service
from app.services.age_policy_engine import AgeAndContestPolicyEngine, utc_today
from tests.unit.test_age_policy_engine import add_policy
from tests.unit.test_new_business_model import _pool_member, _retired_legacy, _user, world  # noqa: F401

PASSWORD = "Str0ng*Passw0rd!"
TODAY = utc_today()
REGISTER = "/api/v1/auth/register"


def years_ago(n: int, days: int = 0) -> str:
    try:
        d = date(TODAY.year - n, TODAY.month, TODAY.day)
    except ValueError:  # 29 Feb
        d = date(TODAY.year - n, 3, 1)
    return (d + timedelta(days=days)).isoformat()


def payload(**over) -> dict:
    uid = uuid.uuid4().hex[:8]
    base = {"email": f"p3_{uid}@example.com", "username": f"p3_{uid}", "password": PASSWORD,
            "date_of_birth": "1990-01-15", "accept_terms": True, "country": "Tanzania"}
    base.update(over)
    return base


@pytest.fixture
def register(client, monkeypatch):
    """POST /auth/register from a chosen client IP (the rate limiter and the gate
    both use app.core.rate_limit._client_ip)."""
    import app.core.rate_limit as rl

    def _register(ip: str = "198.51.100.1", query: str = "", **over):
        monkeypatch.setattr(rl, "_client_ip", lambda request: ip)
        body = payload(**over)
        return client.post(REGISTER + query, json=body), body
    return _register


def enforce(db, jurisdiction="TZ", enabled=True):
    return age_gate.set_enforcement(db, operation=PolicyOperation.ACCOUNT_CREATION, jurisdiction=jurisdiction,
                                    enabled=enabled, reason="synthetic test enforcement", actor_id=None)


def blocked(resp, decision: RegistrationDecision, status_code=403):
    assert resp.status_code == status_code, resp.text
    body = resp.json()
    assert body["code"] == "REGISTRATION_NOT_COMPLETED" and body["decision"] == decision.value
    return body


def created(db, resp) -> User:
    assert resp.status_code == 201, resp.text
    return db.query(User).filter(User.id == resp.json()["id"]).one()


def profile_of(db, user) -> UserAgeProfile:
    return db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).one()


def auth(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def make_user(db, *, dob=None, country="Tanzania", admin=False, **extra) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(email=f"p3u_{uid}@example.com", hashed_password="unused", username=f"p3u_{uid}", is_active=True,
             is_admin=admin, country=country, date_of_birth=datetime.fromisoformat(dob) if dob else None, **extra)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ===========================================================================
# AGE / DOB (1-8)
# ===========================================================================

def test_01_valid_dob_registers_with_self_declared_provenance(db, register):
    resp, body = register()
    user = created(db, resp)
    assert user.date_of_birth.date() == date(1990, 1, 15)
    p = profile_of(db, user)
    assert p.dob_source == "SELF_DECLARED_REGISTRATION"
    assert p.assurance_level == AgeAssuranceLevel.SELF_DECLARED_DOB.value
    assert p.registration_decision == RegistrationDecision.POLICY_NOT_ENFORCED.value
    assert p.terms_accepted_at is not None


@pytest.mark.parametrize("bad", ["2010-02-30", "2010-13-01", "not-a-date", "15/01/1990", 19900115,
                                 "1990-01-15T10:00:00", "1850-01-01"])
def test_02_invalid_dates_rejected(db, register, bad):
    resp, _ = register(date_of_birth=bad)
    assert resp.status_code == 422
    assert db.query(User).count() == 0


def test_03_future_dob_rejected(db, register):
    resp, _ = register(date_of_birth=(TODAY + timedelta(days=1)).isoformat())
    assert resp.status_code == 422 and db.query(User).count() == 0


def test_04_leap_day_dob(db, register):
    user = created(db, register(date_of_birth="2004-02-29")[0])
    assert user.date_of_birth.date() == date(2004, 2, 29)


def test_05_exact_13th_birthday_boundary(db, register):
    created(db, register(date_of_birth=years_ago(13), ip="198.51.100.2")[0])            # exactly 13: allowed
    blocked(register(date_of_birth=years_ago(13, days=1), ip="198.51.100.3")[0],          # 12, one day short
            RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)


def test_06_missing_dob_cannot_register_as_unknown(db, client, register):
    body = payload()
    body.pop("date_of_birth")
    assert client.post(REGISTER, json=body).status_code == 422
    r, _ = register(date_of_birth=None)
    assert r.status_code == 422 and db.query(User).count() == 0


@pytest.mark.parametrize(
    "years, tier",
    [(12, AgeTier.UNDER_13), (13, AgeTier.TEEN_13_15), (15, AgeTier.TEEN_13_15), (16, AgeTier.TEEN_16_17),
     (17, AgeTier.TEEN_16_17), (18, AgeTier.ADULT_18_PLUS)],
)
def test_07_tier_boundaries_are_server_side(db, years, tier):
    r = age_gate.evaluate_registration(db, date_of_birth=date.fromisoformat(years_ago(years)), country="TZ",
                                       email=f"t{years}@example.com", ip=f"203.0.113.{years}", on=TODAY)
    assert r.context.age_tier == tier


@pytest.mark.parametrize("field, value", [("age_tier", "ADULT_18_PLUS"), ("age", 30), ("is_adult", True),
                                           ("assurance_level", "AGE_VERIFIED"), ("identity_verified", True)])
def test_08_client_cannot_supply_age_or_tier(db, register, field, value):
    resp, _ = register(**{field: value})
    assert resp.status_code == 422 and db.query(User).count() == 0


def test_08b_terms_must_be_accepted(db, register):
    assert register(accept_terms=False)[0].status_code == 422
    assert db.query(User).count() == 0


# ===========================================================================
# JURISDICTION (9-14)
# ===========================================================================

def test_09_resolved_jurisdiction_recorded(db, register):
    p = profile_of(db, created(db, register(country="Tanzania")[0]))
    assert (p.jurisdiction_code, p.jurisdiction_status) == ("TZ", "RESOLVED")


def test_10_unresolved_jurisdiction(db, register):
    p = profile_of(db, created(db, register(country="Tanznia")[0]))    # transition: allowed, recorded
    assert (p.jurisdiction_code, p.jurisdiction_status) == (None, "UNRESOLVED")
    enforce(db, "*")
    blocked(register(country="Tanznia", ip="198.51.100.9")[0], RegistrationDecision.UNRESOLVED_JURISDICTION)


def test_11_unsupported_jurisdiction(db, register):
    enforce(db, "*")
    blocked(register(country="Kenya")[0], RegistrationDecision.UNSUPPORTED_JURISDICTION)


def test_12_no_fallback_to_another_policy_or_adult(db, register):
    add_policy(db)  # TZ only
    enforce(db, "*")
    blocked(register(country="Kenya", date_of_birth="1970-01-01")[0], RegistrationDecision.UNSUPPORTED_JURISDICTION)
    assert db.query(User).count() == 0


def test_13_trusted_iso_code_input(db, register):
    p = profile_of(db, created(db, register(country="TZ")[0]))
    assert p.jurisdiction_code == "TZ"


def test_14_malformed_country_text_not_trusted_and_not_rewritten(db, register):
    user = created(db, register(country="Dar es Salaam, TZ!!")[0])
    assert user.country == "Dar es Salaam, TZ!!"                   # stored as before, not rewritten
    assert profile_of(db, user).jurisdiction_status == "UNRESOLVED"


# ===========================================================================
# POLICY TRANSITION (15-19)
# ===========================================================================

def test_15_no_policy_enforcement_off_keeps_registration_available(db, register):
    p = profile_of(db, created(db, register(country="Kenya")[0]))
    assert p.registration_decision == "POLICY_NOT_ENFORCED" and p.registration_enforced is False
    assert p.registration_policy_outcome == PolicyOutcome.UNSUPPORTED_JURISDICTION.value


def test_15b_policy_present_but_not_enforced_records_would_be_outcome(db, register):
    add_policy(db)
    p = profile_of(db, created(db, register(date_of_birth=years_ago(14))[0]))
    assert p.registration_decision == "POLICY_NOT_ENFORCED"
    assert p.registration_policy_outcome == PolicyOutcome.REQUIRES_GUARDIAN_CONSENT.value
    assert p.registration_policy_version == 1


def test_16_policy_and_enforcement_allowed(db, register):
    policy = add_policy(db)
    enforce(db, "TZ")
    p = profile_of(db, created(db, register()[0]))
    assert p.registration_decision == "ALLOWED" and p.registration_enforced is True
    assert (p.registration_policy_id, p.registration_policy_version) == (policy.id, 1)


def test_17_missing_policy_with_enforcement_fails_closed(db, register):
    enforce(db, "TZ")
    blocked(register(date_of_birth="1970-01-01")[0], RegistrationDecision.UNSUPPORTED_JURISDICTION)
    assert db.query(User).count() == 0


def test_18_future_policy_is_not_active(db, register):
    add_policy(db, effective="2099-01-01")
    enforce(db, "TZ")
    blocked(register()[0], RegistrationDecision.UNSUPPORTED_JURISDICTION)


@pytest.mark.parametrize("status", ["DRAFT", "WITHDRAWN"])
def test_19_draft_or_withdrawn_policy_not_enforced(db, register, status):
    add_policy(db, status=status)
    enforce(db, "TZ")
    blocked(register()[0], RegistrationDecision.UNSUPPORTED_JURISDICTION)


def test_19b_disabling_enforcement_restores_transition_mode(db, register):
    enforce(db, "TZ")
    blocked(register(ip="198.51.100.20")[0], RegistrationDecision.UNSUPPORTED_JURISDICTION)
    enforce(db, "TZ", enabled=False)
    created(db, register(ip="198.51.100.21")[0])


# ===========================================================================
# REGISTRATION (20-30)
# ===========================================================================

def test_20_eligible_registration_creates_active_user(db, register):
    add_policy(db)
    enforce(db, "TZ")
    user = created(db, register(date_of_birth=years_ago(20))[0])
    assert user.is_active is True


def test_21_below_minimum_account_age(db, register):
    blocked(register(date_of_birth=years_ago(12))[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    # A jurisdiction policy can raise the minimum; enforced -> 16-year-old denied.
    add_policy(db, minimum_account_age=17, minimum_independent_participation_age=17, parental_consent_age=17,
               voting_minimum_age=17, nomination_minimum_age=17, personal_submission_minimum_age=17,
               livestream_minimum_age=17, payment_minimum_age=17)
    enforce(db, "TZ")
    blocked(register(date_of_birth=years_ago(16), ip="198.51.100.30")[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    assert db.query(User).count() == 0


def test_22_parental_consent_required_creates_no_account(db, register):
    add_policy(db)  # consent below 16 for ACCOUNT_CREATION
    enforce(db, "TZ")
    body = blocked(register(date_of_birth=years_ago(14))[0], RegistrationDecision.PARENTAL_CONSENT_REQUIRED)
    assert "guardian" in body["detail"].lower()
    assert db.query(User).count() == 0 and db.query(UserAgeProfile).count() == 0


def test_23_stronger_assurance_required(db, register):
    add_policy(db, age_assurance_level={"default": "SELF_DECLARED_DOB",
                                        "operations": {"ACCOUNT_CREATION": "AGE_VERIFIED"}})
    enforce(db, "TZ")
    blocked(register()[0], RegistrationDecision.AGE_ASSURANCE_REQUIRED)
    assert db.query(User).count() == 0


def test_24_rejected_registration_leaves_no_user_or_profile(db, register):
    blocked(register(date_of_birth=years_ago(11))[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    assert db.query(User).count() == 0 and db.query(UserAgeProfile).count() == 0
    attempt = db.query(AgeSafetyEvent).one()
    assert attempt.user_id is None and attempt.decision == "BELOW_MINIMUM_ACCOUNT_AGE"


def _financial_counts(db):
    return (db.query(AffiliateCommission).count(), db.query(Deposit).count(), db.query(JournalEntry).count(),
            db.query(RevenueRecognition).count(), db.query(ReferralPoolAssignment).count())


def test_25_26_rejection_has_no_pool_or_financial_side_effect(world, register):
    db = world
    member = _pool_member(db, "pool_member@example.com")
    before = _financial_counts(db)
    blocked(register(date_of_birth=years_ago(10))[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    assert _financial_counts(db) == before
    assert db.query(User).filter(User.sponsor_id == member.id).count() == 0


def test_27_personal_sponsor_behavior_unchanged(world, register):
    db = world
    sponsor = _user(db, "sponsor@example.com")
    db.commit()
    user = created(db, register(query=f"?sponsor_code={sponsor.personal_referral_code}")[0])
    assert (user.sponsor_id, user.sponsor_source) == (sponsor.id, "PERSONAL_REFERRAL")
    assert db.query(ReferralPoolAssignment).count() == 0


def test_28_organic_referral_pool_assignment_for_allowed_case(world, register):
    db = world
    member = _pool_member(db, "pool_member2@example.com")
    user = created(db, register()[0])
    assert (user.sponsor_id, user.sponsor_source) == (member.id, "REFERRAL_POOL")
    assert db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.referred_user_id == user.id).count() == 1


def test_28b_failure_inside_registration_transaction_rolls_back_everything(world):
    db = world
    _pool_member(db, "pool_member3@example.com")
    before = _financial_counts(db)

    def boom(session, new_user):
        raise RuntimeError("simulated failure after sponsor assignment")

    obj = UserCreate(email="atomic@example.com", password=PASSWORD, username="atomic_user")
    with pytest.raises(RuntimeError):
        crud_user.create_with_sponsor(db, obj, before_commit=boom)
    db.rollback()
    assert db.query(User).filter(User.email == "atomic@example.com").count() == 0
    assert _financial_counts(db) == before
    assert db.query(UserAgeProfile).count() == 0


def test_29_duplicate_email_and_username_unchanged(db, register):
    resp, body = register()
    created(db, resp)
    dup_email, _ = register(email=body["email"], ip="198.51.100.40")
    assert dup_email.status_code == 400
    dup_user, _ = register(username=body["username"], ip="198.51.100.41")
    assert dup_user.status_code == 400
    assert db.query(User).count() == 1


def test_30_password_validation_422_and_redacted(db, register):
    resp, _ = register(password="weakpw")
    assert resp.status_code == 422 and "weakpw" not in resp.text
    assert db.query(User).count() == 0


# ===========================================================================
# AGE ASSURANCE / KYC (31-34)
# ===========================================================================

def test_31_self_declared_dob_is_not_verified(db, register):
    user = created(db, register()[0])
    ctx = AgeAndContestPolicyEngine(db).context_for_user(user, TODAY, profile_of(db, user))
    assert ctx.assurance_level == AgeAssuranceLevel.SELF_DECLARED_DOB


def test_32_kyc_does_not_satisfy_age_assurance(db):
    add_policy(db, age_assurance_level={"default": "SELF_DECLARED_DOB",
                                        "operations": {"VOTING": "AGE_VERIFIED"}})
    user = make_user(db, dob="1990-01-01", identity_verified=True, address_verified=True, is_verified=True)
    engine = AgeAndContestPolicyEngine(db)
    decision = engine.evaluate(engine.context_for_user(user, TODAY), PolicyOperation.VOTING)
    assert decision.outcome == PolicyOutcome.REQUIRES_AGE_ASSURANCE


def test_33_kyc_verified_unknown_dob_stays_unknown(db):
    user = make_user(db, dob=None, identity_verified=True, address_verified=True)
    ctx = AgeAndContestPolicyEngine(db).context_for_user(user, TODAY)
    assert ctx.age_tier == AgeTier.UNKNOWN and not ctx.adult_content_eligible


def test_34_stronger_assurance_state_represented(db):
    add_policy(db, age_assurance_level={"default": "SELF_DECLARED_DOB",
                                        "operations": {"VOTING": "AGE_VERIFIED"}})
    user = make_user(db, dob="1990-01-01")
    db.add(UserAgeProfile(user_id=user.id, dob_source="ADMIN_REVIEWED", assurance_level="AGE_VERIFIED",
                          review_status="NONE"))
    db.commit()
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).one()
    engine = AgeAndContestPolicyEngine(db)
    ctx = engine.context_for_user(user, TODAY, profile)
    assert ctx.assurance_level == AgeAssuranceLevel.AGE_VERIFIED
    assert engine.evaluate(ctx, PolicyOperation.VOTING).outcome == PolicyOutcome.ALLOWED


# ===========================================================================
# DOB CHANGE PROTECTION (35-41)
# ===========================================================================

def _put_dob(client, user, dob, **extra):
    return client.put("/api/v1/users/me", json={"date_of_birth": dob, **extra}, headers=auth(user))


def test_35_first_dob_capture_for_legacy_user(db, client):
    user = make_user(db, dob=None)
    r = _put_dob(client, user, "1995-05-05")
    assert r.status_code == 200, r.text
    db.refresh(user)
    assert user.date_of_birth.date() == date(1995, 5, 5)
    p = profile_of(db, user)
    assert p.dob_source == "SELF_DECLARED_PROFILE" and p.assurance_level == "SELF_DECLARED_DOB"
    rec = db.query(DobChangeRecord).one()
    assert (rec.status, rec.reason_code, rec.previous_dob) == ("AUTO_APPLIED", "INITIAL_CAPTURE", None)


def test_35b_first_capture_below_minimum_is_flagged_for_review(db, client):
    user = make_user(db, dob=None)
    assert _put_dob(client, user, years_ago(11)).status_code == 200
    assert profile_of(db, user).review_status == "AGE_REVIEW_REQUIRED"


def test_36_same_value_is_noop(db, client):
    user = make_user(db, dob="1990-01-15")
    r = _put_dob(client, user, "1990-01-15", bio="hello")
    assert r.status_code == 200 and r.json()["bio"] == "hello"
    assert db.query(DobChangeRecord).count() == 0 and db.query(AgeSafetyEvent).count() == 0


def test_37_same_tier_correction_applied_and_audited(db, client):
    user = make_user(db, dob="1990-01-15")
    r = _put_dob(client, user, "1990-02-15")
    assert r.status_code == 200
    db.refresh(user)
    assert user.date_of_birth.date() == date(1990, 2, 15)
    rec = db.query(DobChangeRecord).one()
    assert (rec.status, rec.reason_code, rec.previous_dob) == ("AUTO_APPLIED", "SAME_TIER_CORRECTION", date(1990, 1, 15))
    assert profile_of(db, user).dob_source == "SELF_CORRECTION"
    assert db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type == "DOB_CHANGED").count() == 1


def test_38_tier_changing_correction_requires_review_and_applies_nothing(db, client):
    user = make_user(db, dob=years_ago(15))
    r = _put_dob(client, user, "1990-01-01", bio="should not apply")
    assert r.status_code == 409 and r.json()["code"] == "DOB_CHANGE_PENDING_REVIEW"
    db.refresh(user)
    assert user.date_of_birth.date().isoformat() == years_ago(15) and user.bio is None
    rec = db.query(DobChangeRecord).one()
    assert (rec.status, rec.reason_code) == ("PENDING", "TIER_CHANGE")
    assert profile_of(db, user).review_status == "AGE_VERIFICATION_REQUIRED"   # s.5: "15 to 25"
    # a second attempt while pending is refused
    assert _put_dob(client, user, "1991-01-01").status_code == 409


def test_38b_younger_tier_claim_requires_review(db, client):
    user = make_user(db, dob="1990-01-01")
    assert _put_dob(client, user, years_ago(14)).status_code == 409
    assert profile_of(db, user).review_status == "AGE_REVIEW_REQUIRED"


def test_38c_policy_eligibility_change_within_same_tier_requires_review(db, client):
    add_policy(db)  # nomination_minimum_age 14 splits the 13-15 tier
    user = make_user(db, dob=years_ago(13))
    assert _put_dob(client, user, years_ago(14)).status_code == 409
    assert db.query(DobChangeRecord).one().reason_code == "POLICY_ELIGIBILITY_CHANGE"


def test_39_repeated_changes_trigger_review(db, client):
    user = make_user(db, dob="1990-01-15")
    assert _put_dob(client, user, "1990-02-15").status_code == 200
    r = _put_dob(client, user, "1990-03-15")
    assert r.status_code == 409
    rec = db.query(DobChangeRecord).filter(DobChangeRecord.status == "PENDING").one()
    assert rec.reason_code == "REPEATED_CHANGES"
    assert profile_of(db, user).review_status == "AGE_REVIEW_REQUIRED"
    assert db.query(AgeSafetyEvent).filter(AgeSafetyEvent.risk_flag.is_(True)).count() >= 1


def test_40_admin_correction_and_review_are_audited(db, client):
    admin = make_user(db, admin=True)
    user = make_user(db, dob=years_ago(15))
    _put_dob(client, user, "1990-01-01")          # pending review
    pending = db.query(DobChangeRecord).filter(DobChangeRecord.status == "PENDING").one()
    r = client.post(f"/api/v1/admin/age-safety/dob-changes/{pending.id}/approve", json={"note": "documents checked"},
                    headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    db.refresh(user)
    assert user.date_of_birth.date() == date(1990, 1, 1)
    p = profile_of(db, user)
    assert p.dob_source == "ADMIN_REVIEWED" and p.assurance_level == "SELF_DECLARED_DOB" and p.review_status == "NONE"

    r = client.put(f"/api/v1/admin/age-safety/users/{user.id}/date-of-birth",
                   json={"date_of_birth": "1989-12-31", "reason": "typo fixed by support"}, headers=auth(admin))
    assert r.status_code == 200
    db.refresh(user)
    assert user.date_of_birth.date() == date(1989, 12, 31)
    actions = {a.action for a in db.query(AuditTrail).filter(AuditTrail.table_name == "dob_change_records")}
    assert {"DOB_CHANGE_APPROVED", "DOB_ADMIN_CORRECTION"} <= actions
    for a in db.query(AuditTrail).filter(AuditTrail.table_name == "dob_change_records"):
        assert "1989" not in json.dumps(a.new_values) and "1990" not in json.dumps(a.new_values)


def test_40b_admin_reject_keeps_dob(db, client):
    admin = make_user(db, admin=True)
    user = make_user(db, dob=years_ago(15))
    _put_dob(client, user, "1990-01-01")
    pending = db.query(DobChangeRecord).filter(DobChangeRecord.status == "PENDING").one()
    r = client.post(f"/api/v1/admin/age-safety/dob-changes/{pending.id}/reject", json={"note": "no evidence"},
                    headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    db.refresh(user)
    assert user.date_of_birth.date().isoformat() == years_ago(15)


def test_41_unauthorized_dob_modification_rejected(db, client):
    member = make_user(db, dob="1990-01-01")
    victim = make_user(db, dob="1990-01-01")
    url = f"/api/v1/admin/age-safety/users/{victim.id}/date-of-birth"
    assert client.put(url, json={"date_of_birth": "2012-01-01", "reason": "attempt"}).status_code == 401
    assert client.put(url, json={"date_of_birth": "2012-01-01", "reason": "attempt"}, headers=auth(member)).status_code == 403
    db.refresh(victim)
    assert victim.date_of_birth.date() == date(1990, 1, 1)
    with pytest.raises(ValueError):
        crud_user.update(db, db_obj=member, obj_in={"date_of_birth": datetime(2012, 1, 1)})
    assert _put_dob(client, member, None).status_code == 422   # cannot remove DOB


def test_41b_admin_endpoints_require_admin(db, client):
    member = make_user(db)
    for method, url, body in [("get", "/api/v1/admin/age-safety/enforcement", None),
                              ("put", "/api/v1/admin/age-safety/enforcement",
                               {"operation": "ACCOUNT_CREATION", "jurisdiction": "*", "enabled": True, "reason": "x" * 6}),
                              ("get", "/api/v1/admin/age-safety/dob-changes", None),
                              ("get", f"/api/v1/admin/age-safety/users/{member.id}/age-status", None)]:
        kwargs = {"json": body} if body else {}
        assert getattr(client, method)(url, **kwargs).status_code == 401
        assert getattr(client, method)(url, headers=auth(member), **kwargs).status_code == 403
    assert db.query(ChildSafetyEnforcement).count() == 0


def test_41c_enforcement_switch_is_audited_and_validated(db, client):
    admin = make_user(db, admin=True)
    url = "/api/v1/admin/age-safety/enforcement"
    ok = client.put(url, json={"operation": "ACCOUNT_CREATION", "jurisdiction": "tz", "enabled": True,
                               "reason": "synthetic enable"}, headers=auth(admin))
    assert ok.status_code == 200 and ok.json()["jurisdiction"] == "TZ"
    assert client.put(url, json={"operation": "VOTING", "jurisdiction": "TZ", "enabled": True, "reason": "too early"},
                      headers=auth(admin)).status_code == 409                     # later phases only
    assert client.put(url, json={"operation": "ACCOUNT_CREATION", "jurisdiction": "Atlantis", "enabled": True,
                                 "reason": "bad code"}, headers=auth(admin)).status_code == 409
    assert db.query(AuditTrail).filter(AuditTrail.table_name == "child_safety_enforcement").count() == 1


# ===========================================================================
# CIRCUMVENTION (42-47)
# ===========================================================================

def test_42_same_email_underage_then_adult_is_review_blocked(db, register):
    resp, body = register(date_of_birth=years_ago(11), ip="198.51.100.50")
    blocked(resp, RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    retry, _ = register(email=body["email"], date_of_birth=years_ago(25), ip="198.51.100.51")  # new IP, same email
    blocked(retry, RegistrationDecision.REVIEW_REQUIRED)
    assert db.query(User).count() == 0


def test_43_immediate_same_ip_threshold_probing_blocked(db, register):
    blocked(register(date_of_birth=years_ago(11), ip="198.51.100.60")[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    blocked(register(date_of_birth=years_ago(25), ip="198.51.100.60")[0], RegistrationDecision.REVIEW_REQUIRED)
    assert db.query(User).count() == 0


def test_43b_older_single_ip_signal_allows_but_escalates(db):
    now = datetime.utcnow()
    ip_hash = age_gate.safety_hash("ip", "198.51.100.70")
    db.add(AgeSafetyEvent(created_at=now - timedelta(hours=3), updated_at=now, event_type="AGE_GATE_ATTEMPT",
                          ip_hash=ip_hash, age_tier="UNDER_13", decision="BELOW_MINIMUM_ACCOUNT_AGE"))
    db.commit()
    r = age_gate.evaluate_registration(db, date_of_birth=date(1990, 1, 1), country="TZ", email="family@example.com",
                                       ip="198.51.100.70", on=TODAY, now=now)
    assert r.allowed and r.flag_for_review


def test_43c_tier_hopping_on_one_email(db):
    email = "hopper@example.com"
    now = datetime.utcnow()
    for i, tier in enumerate(["TEEN_13_15", "TEEN_16_17"]):
        db.add(AgeSafetyEvent(created_at=now - timedelta(hours=i + 1), updated_at=now, event_type="AGE_GATE_ATTEMPT",
                              email_hash=age_gate.safety_hash("email", email), age_tier=tier, decision="POLICY_NOT_ENFORCED"))
    db.commit()
    r = age_gate.evaluate_registration(db, date_of_birth=date(1990, 1, 1), country="TZ", email=email,
                                       ip="203.0.113.99", on=TODAY, now=now)
    assert r.decision == RegistrationDecision.REVIEW_REQUIRED


def test_44_retry_limit(db, register):
    email = "retry@example.com"
    now = datetime.utcnow()
    for i in range(5):
        db.add(AgeSafetyEvent(created_at=now - timedelta(minutes=i + 1), updated_at=now, event_type="AGE_GATE_ATTEMPT",
                              email_hash=age_gate.safety_hash("email", email), age_tier="ADULT_18_PLUS",
                              decision="POLICY_NOT_ENFORCED"))
    db.commit()
    blocked(register(email=email)[0], RegistrationDecision.RETRY_LIMITED, status_code=429)
    ip = "203.0.113.200"
    for i in range(20):
        db.add(AgeSafetyEvent(created_at=now - timedelta(minutes=1), updated_at=now, event_type="AGE_GATE_ATTEMPT",
                              ip_hash=age_gate.safety_hash("ip", ip), age_tier="ADULT_18_PLUS", decision="POLICY_NOT_ENFORCED"))
    db.commit()
    r = age_gate.evaluate_registration(db, date_of_birth=date(1990, 1, 1), country="TZ", email="other@example.com",
                                       ip=ip, on=TODAY, now=now)
    assert r.decision == RegistrationDecision.RETRY_LIMITED


def test_45_client_response_reveals_no_risk_or_thresholds(db, register):
    blocked(register(date_of_birth=years_ago(11), ip="198.51.100.80")[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    resp, _ = register(date_of_birth=years_ago(25), ip="198.51.100.80")
    body = blocked(resp, RegistrationDecision.REVIEW_REQUIRED)
    assert set(body) == {"detail", "code", "decision", "message"}
    text = resp.text.lower()
    for leak in ("risk", "signal", "score", "threshold", "email_older", "ip_", "13", "hash"):
        assert leak not in text
    below = register(date_of_birth=years_ago(12), ip="198.51.100.81")[0]
    assert not re.search(r"\d", below.json()["detail"].replace("MyHigh5", ""))  # no ages/thresholds


def test_46_attempts_and_risk_are_recorded(db, register):
    register(date_of_birth=years_ago(11), ip="198.51.100.90")
    register(date_of_birth=years_ago(25), ip="198.51.100.90")
    events = db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type == "AGE_GATE_ATTEMPT").order_by(AgeSafetyEvent.id).all()
    assert [e.decision for e in events] == ["BELOW_MINIMUM_ACCOUNT_AGE", "REVIEW_REQUIRED"]
    assert events[1].risk_flag is True and events[1].details["signals"]


def test_47_no_plaintext_identifiers_or_dob_stored(db, register):
    resp, body = register(ip="198.51.100.91")
    created(db, resp)
    for e in db.query(AgeSafetyEvent).all():
        blob = json.dumps({k: str(v) for k, v in e.__dict__.items() if not k.startswith("_")})
        assert body["email"] not in blob and "198.51.100.91" not in blob and "1990-01-15" not in blob
        for h in (e.email_hash, e.ip_hash):
            assert h is None or re.fullmatch(r"[0-9a-f]{64}", h)


# ===========================================================================
# PRIVACY / LEGACY / REGRESSION (48-53)
# ===========================================================================

def test_48_dob_not_exposed_by_public_username_lookup(db, client):
    viewer = make_user(db)
    target = make_user(db, dob="1990-01-15")
    r = client.get(f"/api/v1/users/by-username/{target.username}", headers=auth(viewer))
    assert r.status_code == 200 and "date_of_birth" not in r.json() and "1990" not in r.text


def test_51_legacy_unknown_user_stays_unknown_and_reads_create_nothing(db, client):
    admin = make_user(db, admin=True)
    legacy = make_user(db, dob=None)
    r = client.get(f"/api/v1/admin/age-safety/users/{legacy.id}/age-status", headers=auth(admin))
    assert r.status_code == 200
    assert r.json()["age_tier"] == "UNKNOWN" and r.json()["dob_source"] is None
    assert db.query(UserAgeProfile).count() == 0
    assert "date_of_birth" not in r.json()


def test_52_legacy_dob_is_not_manufactured_into_verified(db, client):
    admin = make_user(db, admin=True)
    legacy = make_user(db, dob="1990-01-15")
    body = client.get(f"/api/v1/admin/age-safety/users/{legacy.id}/age-status", headers=auth(admin)).json()
    assert body["dob_source"] == "LEGACY_PROFILE" and body["assurance_level"] == "SELF_DECLARED_DOB"


def test_53_registration_does_not_rewrite_existing_users(db, register):
    existing = [make_user(db, dob="1980-01-01", country="Kenya"), make_user(db, dob=None, country="free text")]
    snapshot = [(u.id, u.date_of_birth, u.country, u.sponsor_id) for u in existing]
    created(db, register()[0])
    for u, snap in zip(existing, snapshot):
        db.refresh(u)
        assert (u.id, u.date_of_birth, u.country, u.sponsor_id) == snap
    assert db.query(UserAgeProfile).filter(UserAgeProfile.user_id.in_([u.id for u in existing])).count() == 0
