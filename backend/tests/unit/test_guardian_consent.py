"""Phase 4: verified guardian consent, pending registration handoff and teen
privacy (MyHigh5 Child/Teen Safety s.2, s.4, s.7, s.8, s.12-14, s.24, s.25, s.32).

All policies, users, guardians and emails are SYNTHETIC. No real email is sent:
the email service is replaced by a capturing stub.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.core.child_safety import (
    AgeTier,
    ConsentRequirement,
    GuardianConsentScope as S,
    GuardianRelationshipType,
    GuardianVerificationMethod,
    RegistrationDecision,
)
from app.core.config import settings
from app.core.security import create_access_token
from app.crud import user as crud_user
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.age_safety import AgeSafetyEvent, UserAgeProfile
from app.models.business_model import ReferralPoolAssignment, RevenueRecognition
from app.models.guardian import Guardian, GuardianConsent, GuardianRelationship, PendingRegistration, UserPrivacyPreference
from app.models.payment import Deposit
from app.models.user import User
from app.services import guardian_consent as gc
from app.services import guardian_notifications, teen_privacy
from app.services.age_policy_engine import utc_today
from tests.unit.test_age_gate_registration import (  # noqa: F401
    REGISTER,
    auth,
    enforce,
    make_user,
    payload,
    register,
    years_ago,
)
from tests.unit.test_age_policy_engine import add_policy
from tests.unit.test_new_business_model import _pool_member, _retired_legacy, _user, world  # noqa: F401

TODAY = utc_today()
PASSWORD = "Str0ng*Passw0rd!"
TOKEN_RE = re.compile(r"#token=([A-Za-z0-9_\-]+)")


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(to_email, subject, html_content, text_content=None):
        sent.append({"to": to_email, "subject": subject, "html": html_content})
        return True

    monkeypatch.setattr(guardian_notifications.email_service, "send_email", fake_send)
    return sent


@pytest.fixture
def accept_admin_review(monkeypatch):
    """The approved operational configuration: ADMIN_DOCUMENT_REVIEW only."""
    monkeypatch.setattr(settings, "GUARDIAN_ACCEPTED_VERIFICATION_METHODS", "ADMIN_DOCUMENT_REVIEW")


@pytest.fixture
def consent_world(db):
    """SYNTHETIC TZ policy: consent below 16 for ACCOUNT_CREATION; enforcement on."""
    add_policy(db)
    enforce(db, "TZ")
    return db


def token_from(mail) -> str:
    return TOKEN_RE.search(mail["html"]).group(1)


def start_pending(register, outbox, *, age=14, ip="198.51.100.200", guardian="parent.p4@example.com", **over):
    resp, body = register(date_of_birth=years_ago(age), ip=ip, guardian_email=guardian, **over)
    assert resp.status_code == 202, resp.text
    assert resp.json()["decision"] == "GUARDIAN_CONSENT_PENDING"
    return body, token_from(outbox[-1]) if outbox else None


def approve(client, token, scopes=(S.ACCOUNT_PARTICIPATION,), rel=GuardianRelationshipType.PARENT):
    return client.post("/api/v1/guardian/requests/respond", json={
        "token": token, "decision": "APPROVE", "relationship_type": rel.value, "scopes": [s.value for s in scopes]})


def complete(client, token, password=PASSWORD):
    return client.post("/api/v1/auth/register/complete", json={"token": token, "password": password})


def admin_verify(client, db):
    """Explicit guardian-authority verification by an authorized admin."""
    admin = db.query(User).filter(User.is_admin.is_(True)).first() or make_user(db, admin=True)
    rel = db.query(GuardianRelationship).order_by(GuardianRelationship.id.desc()).first()
    r = client.post(f"/api/v1/admin/age-safety/guardian-relationships/{rel.id}/verify",
                    json={"method": "ADMIN_DOCUMENT_REVIEW", "note": "synthetic evidence reviewed"}, headers=auth(admin))
    assert r.status_code == 200, r.text
    return r


def members(db):
    return db.query(User).filter(User.is_admin.is_(False))


def full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION,), **over):
    body, gtoken = start_pending(register, outbox, **over)
    assert approve(client, gtoken, scopes).json()["status"] == "VERIFICATION_REQUIRED"
    admin_verify(client, db)
    ctoken = token_from(outbox[-1])
    r = complete(client, ctoken)
    assert r.status_code == 201, r.text
    return db.query(User).filter(User.id == r.json()["id"]).one(), body


def financial_counts(db):
    return (db.query(AffiliateCommission).count(), db.query(Deposit).count(), db.query(JournalEntry).count(),
            db.query(RevenueRecognition).count(), db.query(ReferralPoolAssignment).count())


# ===========================================================================
# GUARDIAN MODEL (1-5)
# ===========================================================================

def test_01_to_05_guardian_is_a_distinct_explicit_actor(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, body = full_flow(client, register, outbox, db)
    guardian = db.query(Guardian).one()
    rel = db.query(GuardianRelationship).one()
    assert guardian.email == "parent.p4@example.com" and guardian.user_id is None          # not the minor
    assert rel.minor_user_id == minor.id and rel.guardian_id == guardian.id
    assert minor.sponsor_id is None or minor.sponsor_id != guardian.user_id                # not the sponsor
    assert rel.verification_status == "VERIFIED" and rel.relationship_type == "PARENT"     # explicit status
    # a nominator-like concept / arbitrary adult account is not a guardian
    adult = make_user(db, dob="1980-01-01", email_verified=True)
    assert gc.guardian_for_user(db, adult) is None


def test_04b_adult_with_unverified_email_is_not_the_guardian(db):
    g = gc.get_or_create_guardian(db, "same@example.com")
    db.commit()
    unverified = User(email="same@example.com", hashed_password="x", username="same_x", is_active=True,
                      email_verified=False)
    db.add(unverified)
    db.commit()
    assert gc.guardian_for_user(db, unverified) is None
    unverified.email_verified = True
    db.commit()
    assert gc.guardian_for_user(db, unverified).id == g.id


# ===========================================================================
# CONSENT (6-16)
# ===========================================================================

def test_06_pending_consent_after_request(consent_world, register, outbox):
    db = consent_world
    start_pending(register, outbox)
    rel = db.query(GuardianRelationship).one()
    assert rel.verification_status == "PENDING" and rel.relationship_type is None
    assert db.query(GuardianConsent).count() == 0 and db.query(User).count() == 0


def test_07_verification_requires_an_accepted_method_fail_closed(consent_world, client, register, outbox):
    db = consent_world
    _, token = start_pending(register, outbox)
    r = approve(client, token)
    assert r.json()["status"] == "VERIFICATION_REQUIRED"            # default: no method accepted
    rel = db.query(GuardianRelationship).one()
    assert rel.verification_status == "VERIFICATION_REQUIRED" and rel.verified_at is None
    pending = db.query(PendingRegistration).one()
    assert pending.status == "AWAITING_GUARDIAN" and pending.completion_token_hash is None
    assert not gc.check_consent(db, scope=S.ACCOUNT_PARTICIPATION, at=datetime.utcnow(),
                                pending_registration_id=pending.id).valid


def test_07b_admin_verification_with_accepted_method(consent_world, client, register, outbox, monkeypatch):
    db = consent_world
    _, token = start_pending(register, outbox)
    approve(client, token)
    rel = db.query(GuardianRelationship).one()
    admin = make_user(db, admin=True)
    url = f"/api/v1/admin/age-safety/guardian-relationships/{rel.id}/verify"
    body = {"method": "ADMIN_DOCUMENT_REVIEW", "note": "synthetic evidence reviewed"}
    assert client.post(url, json=body, headers=auth(admin)).status_code == 409        # method not accepted
    monkeypatch.setattr(settings, "GUARDIAN_ACCEPTED_VERIFICATION_METHODS", "ADMIN_DOCUMENT_REVIEW")
    r = client.post(url, json=body, headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    db.refresh(rel)
    assert rel.verification_status == "VERIFIED" and rel.verified_by_user_id == admin.id
    assert "finish creating" in outbox[-1]["html"].lower()
    assert db.query(AuditTrail).filter(AuditTrail.table_name == "guardian_relationships").count() == 1


def test_08_consent_grant_records_s13_fields(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.NAME_DISPLAY))
    c = db.query(GuardianConsent).filter(GuardianConsent.consent_scope == "NAME_DISPLAY").one()
    assert c.minor_user_id == minor.id and c.guardian_reference is not None
    assert c.jurisdiction == "TZ" and c.policy_version == 1
    assert c.verification_method == "ADMIN_DOCUMENT_REVIEW" and c.consent_timestamp is not None
    assert c.withdrawal_status == "GRANTED" and c.expires_at is None


def test_09_guardian_rejection(consent_world, client, register, outbox):
    db = consent_world
    _, token = start_pending(register, outbox)
    r = client.post("/api/v1/guardian/requests/respond", json={"token": token, "decision": "DECLINE"})
    assert r.json()["status"] == "DECLINED"
    assert db.query(PendingRegistration).one().status == "DECLINED"
    assert db.query(GuardianRelationship).one().verification_status == "REJECTED"
    assert db.query(GuardianConsent).count() == 0 and db.query(User).count() == 0


def test_10_11_15_16_withdrawal_preserves_history(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.PUBLICITY))
    consent = db.query(GuardianConsent).filter(GuardianConsent.consent_scope == "PUBLICITY").one()
    granted_at = consent.consent_timestamp
    before = datetime.utcnow()
    admin = make_user(db, admin=True)
    r = client.post(f"/api/v1/admin/age-safety/guardian-consents/{consent.id}/withdraw",
                    json={"note": "guardian asked support"}, headers=auth(admin))
    assert r.status_code == 200
    db.refresh(consent)
    assert consent.withdrawal_status == "WITHDRAWN" and consent.consent_timestamp == granted_at   # history kept
    assert db.query(GuardianConsent).count() == 2                                               # nothing deleted
    assert gc.check_consent(db, scope=S.PUBLICITY, at=before, minor_user_id=minor.id).valid      # valid at X
    now_check = gc.check_consent(db, scope=S.PUBLICITY, at=datetime.utcnow() + timedelta(seconds=1),
                                 minor_user_id=minor.id)
    assert not now_check.valid and now_check.reason == "WITHDRAWN"                               # not now
    assert client.post(f"/api/v1/admin/age-safety/guardian-consents/{consent.id}/withdraw",
                       json={"note": "again please"}, headers=auth(admin)).status_code == 409


def test_10b_guardian_self_service_withdrawal(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.MEDIA_USE))
    guardian_account = User(email="parent.p4@example.com", hashed_password="x", username="parent_p4",
                            is_active=True, email_verified=True)
    stranger = make_user(db, dob="1980-01-01", email_verified=True)
    db.add(guardian_account)
    db.commit()
    listing = client.get("/api/v1/guardian/me/consents", headers=auth(guardian_account)).json()
    media = next(c for c in listing if c["scope"] == "MEDIA_USE")
    assert "email" not in json.dumps(listing) and "date_of_birth" not in json.dumps(listing)
    assert client.post(f"/api/v1/guardian/me/consents/{media['consent_id']}/withdraw", json={"reason": "not mine"},
                       headers=auth(stranger)).status_code == 403
    r = client.post(f"/api/v1/guardian/me/consents/{media['consent_id']}/withdraw", json={"reason": "changed mind"},
                    headers=auth(guardian_account))
    assert r.status_code == 200 and r.json()["status"] == "WITHDRAWN"


def test_12_13_scope_specific(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.CONTEST_ENTRY))
    now = datetime.utcnow() + timedelta(seconds=1)
    assert gc.check_consent(db, scope=S.CONTEST_ENTRY, at=now, minor_user_id=minor.id).valid
    for other in (S.STAGE_ADVANCEMENT, S.PUBLICITY, S.PRIZE_ACCEPTANCE, S.FINANCIAL_PAYMENT):
        assert not gc.check_consent(db, scope=other, at=now, minor_user_id=minor.id).valid


def test_14_expired_consent_fails(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.MEDIA_USE))
    c = db.query(GuardianConsent).filter(GuardianConsent.consent_scope == "MEDIA_USE").one()
    c.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    check = gc.check_consent(db, scope=S.MEDIA_USE, at=datetime.utcnow(), minor_user_id=minor.id)
    assert not check.valid and check.reason == "EXPIRED"


@pytest.mark.parametrize("scope", list(S))
def test_17_to_27_every_scope_is_independently_grantable(consent_world, client, register, outbox, accept_admin_review,
                                                           scope):
    db = consent_world
    scopes = (S.ACCOUNT_PARTICIPATION,) if scope == S.ACCOUNT_PARTICIPATION else (S.ACCOUNT_PARTICIPATION, scope)
    minor, _ = full_flow(client, register, outbox, db, scopes=scopes)
    now = datetime.utcnow() + timedelta(seconds=1)
    assert gc.check_consent(db, scope=scope, at=now, minor_user_id=minor.id).valid
    others = [s for s in S if s not in scopes]
    assert all(not gc.check_consent(db, scope=o, at=now, minor_user_id=minor.id).valid for o in others)


def test_approval_requires_account_scope_and_relationship(consent_world, client, register, outbox):
    db = consent_world
    _, token = start_pending(register, outbox)
    r = client.post("/api/v1/guardian/requests/respond", json={"token": token, "decision": "APPROVE",
                                                                "relationship_type": "PARENT", "scopes": ["PUBLICITY"]})
    assert r.status_code == 422
    r = client.post("/api/v1/guardian/requests/respond", json={"token": token, "decision": "APPROVE",
                                                                "scopes": ["ACCOUNT_PARTICIPATION"]})
    assert r.status_code == 422
    assert db.query(PendingRegistration).one().guardian_token_used_at is None      # not consumed by bad input


# ===========================================================================
# REGISTRATION HANDOFF (28-40)
# ===========================================================================

def test_28_consent_required_without_guardian_email_creates_nothing(consent_world, register):
    db = consent_world
    resp, _ = register(date_of_birth=years_ago(14))
    assert resp.status_code == 403 and resp.json()["decision"] == "PARENTAL_CONSENT_REQUIRED"
    assert db.query(User).count() == 0 and db.query(PendingRegistration).count() == 0


def test_28b_pending_registration_is_not_a_user(consent_world, register, outbox):
    db = consent_world
    start_pending(register, outbox)
    assert db.query(User).count() == 0 and db.query(UserAgeProfile).count() == 0
    p = db.query(PendingRegistration).one()
    assert not hasattr(p, "hashed_password") and "password" not in PendingRegistration.__table__.columns.keys()


def test_29_pending_registration_cannot_login(consent_world, client, register, outbox):
    body, _ = start_pending(register, outbox)
    r = client.post("/api/v1/auth/login", data={"username": body["email"], "password": body["password"]})
    assert r.status_code == 401


def test_30_34_pending_and_tokens_expire(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    _, token = start_pending(register, outbox)
    p = db.query(PendingRegistration).one()
    p.guardian_token_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post("/api/v1/guardian/requests/lookup", json={"token": token}).status_code == 404
    assert approve(client, token).status_code == 404
    p.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert gc.expire_and_purge(db)["expired"] == 1
    db.refresh(p)
    assert p.status == "EXPIRED" and db.query(GuardianRelationship).one().verification_status == "EXPIRED"


def test_31_64_tokens_are_stored_hashed_only(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    _, gtoken = start_pending(register, outbox)
    approve(client, gtoken)
    admin_verify(client, db)
    ctoken = token_from(outbox[-1])
    p = db.query(PendingRegistration).one()
    row_blob = json.dumps({k: str(v) for k, v in p.__dict__.items() if not k.startswith("_")})
    assert gtoken not in row_blob and ctoken not in row_blob
    assert p.guardian_token_hash == gc.token_hash(gtoken) and p.completion_token_hash == gc.token_hash(ctoken)


def test_32_33_35_tokens_single_use_and_completion_once(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    _, gtoken = start_pending(register, outbox)
    approve(client, gtoken)
    assert approve(client, gtoken).status_code == 404                     # guardian token replay
    admin_verify(client, db)
    ctoken = token_from(outbox[-1])
    assert complete(client, ctoken).status_code == 201
    assert complete(client, ctoken).status_code == 404                    # completion replay
    assert members(db).count() == 1 and db.query(PendingRegistration).one().status == "COMPLETED"


def test_34b_expired_completion_token_rejected(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    _, gtoken = start_pending(register, outbox)
    approve(client, gtoken)
    admin_verify(client, db)
    p = db.query(PendingRegistration).one()
    p.completion_token_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert complete(client, token_from(outbox[-1])).status_code == 404
    assert members(db).count() == 0


def test_36_to_38_completion_uses_normal_atomic_path_with_sponsor(world, client, register, outbox, accept_admin_review):
    db = world
    add_policy(db)
    enforce(db, "TZ")
    member = _pool_member(db, "pool_member_p4@example.com")
    minor, _ = full_flow(client, register, outbox, db)
    assert (minor.sponsor_id, minor.sponsor_source) == (member.id, "REFERRAL_POOL")
    assert db.query(ReferralPoolAssignment).filter(ReferralPoolAssignment.referred_user_id == minor.id).count() == 1
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == minor.id).one()
    assert profile.registration_decision == RegistrationDecision.ALLOWED_WITH_GUARDIAN_CONSENT.value
    assert profile.assurance_level == "SELF_DECLARED_DOB"


def test_36b_personal_sponsor_code_is_carried_to_completion(world, client, register, outbox, accept_admin_review):
    db = world
    add_policy(db)
    enforce(db, "TZ")
    sponsor = _user(db, "sponsor_p4@example.com")
    db.commit()
    minor, _ = full_flow(client, register, outbox, db, query=f"?sponsor_code={sponsor.personal_referral_code}")
    assert (minor.sponsor_id, minor.sponsor_source) == (sponsor.id, "PERSONAL_REFERRAL")
    assert db.query(ReferralPoolAssignment).count() == 0


def test_39_no_financial_or_pool_side_effect_before_completion(world, client, register, outbox, accept_admin_review):
    db = world
    add_policy(db)
    enforce(db, "TZ")
    _pool_member(db, "pool_member_p4b@example.com")
    before = financial_counts(db)
    _, gtoken = start_pending(register, outbox)
    approve(client, gtoken)
    admin_verify(client, db)
    assert financial_counts(db) == before and db.query(User).filter(User.email.startswith("p3_", autoescape=True)).count() == 0


def test_40_failed_completion_leaves_no_partial_account(consent_world, client, register, outbox, accept_admin_review,
                                                         monkeypatch):
    db = consent_world
    body, gtoken = start_pending(register, outbox)
    approve(client, gtoken)
    admin_verify(client, db)
    ctoken = token_from(outbox[-1])
    import app.services.guardian_consent as module
    original = module.UserAgeProfile

    class Boom(Exception):
        pass

    def exploding(*a, **k):
        raise Boom("simulated failure inside the registration transaction")

    monkeypatch.setattr(module, "UserAgeProfile", exploding)
    with pytest.raises(Boom):
        module.complete_registration(db, ctoken, PASSWORD, today=TODAY)
    db.rollback()
    monkeypatch.setattr(module, "UserAgeProfile", original)
    assert members(db).count() == 0 and db.query(GuardianConsent).filter(GuardianConsent.minor_user_id.isnot(None)).count() == 0
    assert db.query(PendingRegistration).one().status == "APPROVED"          # retry still possible
    assert complete(client, ctoken).status_code == 201


def test_40b_weak_password_at_completion_is_422_and_not_echoed(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    _, gtoken = start_pending(register, outbox)
    approve(client, gtoken)
    admin_verify(client, db)
    r = complete(client, token_from(outbox[-1]), password="weakpw")
    assert r.status_code == 422 and "weakpw" not in r.text and members(db).count() == 0


def test_66_enumeration_safe_duplicate_pending(consent_world, register, outbox):
    db = consent_world
    body, _ = start_pending(register, outbox, ip="198.51.100.210")
    again, _ = register(email=body["email"], date_of_birth=years_ago(14), ip="198.51.100.211",
                        guardian_email="other.parent@example.com")
    assert again.status_code == 202 and again.json()["decision"] == "GUARDIAN_CONSENT_PENDING"
    assert db.query(PendingRegistration).count() == 1 and len(outbox) == 1        # nothing new sent
    assert client_json_keys(again) == {"detail", "code", "decision", "message"}


def client_json_keys(resp):
    return set(resp.json())


def test_66b_invalid_tokens_are_indistinguishable(consent_world, client):
    a = client.post("/api/v1/guardian/requests/lookup", json={"token": "x" * 43})
    b = client.post("/api/v1/guardian/requests/respond", json={"token": "y" * 43, "decision": "DECLINE"})
    c = complete(client, "z" * 43)
    assert a.status_code == b.status_code == c.status_code == 404


def test_guardian_email_must_differ_from_applicant(consent_world, register):
    resp, body = register(date_of_birth=years_ago(14), guardian_email=None)
    same, _ = register(date_of_birth=years_ago(14), ip="198.51.100.220", email="kid.p4@example.com",
                       guardian_email="kid.p4@example.com")
    assert same.status_code == 422


def test_guardian_email_ignored_when_consent_not_required(consent_world, register):
    db = consent_world
    resp, _ = register(date_of_birth="1990-01-01", guardian_email="unused.parent@example.com")
    assert resp.status_code == 201 and db.query(Guardian).count() == 0 and db.query(PendingRegistration).count() == 0


def test_lookup_reveals_minimal_information(consent_world, client, register, outbox):
    body, token = start_pending(register, outbox)
    summary = client.post("/api/v1/guardian/requests/lookup", json={"token": token}).json()
    blob = json.dumps(summary)
    assert summary["username"] == body["username"]
    for leak in (body["email"], body["date_of_birth"], "date_of_birth", "password", "age"):
        assert leak not in blob.replace("usage", "")


def test_guardian_email_contains_no_sensitive_data(consent_world, register, outbox):
    body, _ = start_pending(register, outbox)
    mail = outbox[-1]["html"]
    for leak in (body["password"], body["date_of_birth"], body["email"], years_ago(14)[:4]):
        assert leak not in mail
    assert "#token=" in mail and "?token=" not in mail                    # fragment: never sent to servers


# ===========================================================================
# PRIVACY (41-48)
# ===========================================================================

def _privacy(db, user):
    return teen_privacy.resolve_privacy(db, user, on=TODAY)


def test_41_teen_13_15_strongest_floor(db):
    teen = make_user(db, dob=years_ago(14))
    p = _privacy(db, teen)
    s = p.settings
    assert p.age_tier == AgeTier.TEEN_13_15
    for f in ("precise_location_visible", "location_sharing", "search_engine_indexing", "public_contact_information",
              "public_date_of_birth", "exact_age_visible", "profile_discovery_by_unrelated_adults"):
        assert s[f] is False and f in p.locked_fields
    for f in ("high_privacy_default", "tagging_controls_enabled", "safety_notifications_enabled", "profiling_restricted"):
        assert s[f] is True
    assert s["unknown_adult_direct_messages"] == "PROHIBITED"


def test_42_teen_16_17_protected_not_adult(db):
    p = _privacy(db, make_user(db, dob=years_ago(17)))
    assert p.age_tier == AgeTier.TEEN_16_17
    assert p.settings["search_engine_indexing"] is False and p.settings["public_date_of_birth"] is False
    assert p.settings["high_privacy_default"] is True and p.settings["unknown_adult_direct_messages"] != "ALLOWED"


def test_43_adult_has_no_teen_only_floor(db):
    p = _privacy(db, make_user(db, dob="1980-01-01"))
    assert p.locked_fields == [] and p.settings["search_engine_indexing"] is True
    assert p.settings["public_date_of_birth"] is False        # current MyHigh5 default, not a teen rule


def test_44_unknown_age_gets_strongest_protection(db):
    p = _privacy(db, make_user(db, dob=None))
    assert p.age_tier == AgeTier.UNKNOWN and p.settings["search_engine_indexing"] is False
    assert p.settings["unknown_adult_direct_messages"] == "PROHIBITED" and not any(p.display.values())


def test_45_46_minor_cannot_weaken_but_can_strengthen(db, client):
    teen = make_user(db, dob=years_ago(15))
    r = client.put("/api/v1/users/me/privacy", json={"search_engine_indexing": True}, headers=auth(teen))
    assert r.status_code == 422 and "search_engine_indexing" in r.json()["detail"]["fields"]
    adult = make_user(db, dob="1980-01-01")
    r = client.put("/api/v1/users/me/privacy", json={"search_engine_indexing": False,
                                                      "unknown_adult_direct_messages": "PROHIBITED"}, headers=auth(adult))
    assert r.status_code == 200 and r.json()["settings"]["search_engine_indexing"] is False
    assert client.put("/api/v1/users/me/privacy", json={"is_adult": True}, headers=auth(adult)).status_code == 422


def test_47_guardian_consent_cannot_lift_mandatory_prohibition(consent_world, client, register, outbox,
                                                               accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=list(S))           # every scope granted
    p = _privacy(db, minor)
    assert p.display["name_display"] is True                                    # consent-scoped allowance
    for f in ("public_date_of_birth", "exact_age_visible", "public_contact_information", "precise_location_visible"):
        assert p.settings[f] is False                                           # mandatory floor still wins


def test_48_privacy_changes_across_age_boundary(db):
    user = make_user(db, dob=years_ago(18))
    adult_today = teen_privacy.resolve_privacy(db, user, on=TODAY)
    yesterday = TODAY - timedelta(days=1)
    teen_yesterday = teen_privacy.resolve_privacy(db, user, on=yesterday)
    assert teen_yesterday.age_tier == AgeTier.TEEN_16_17 and adult_today.age_tier == AgeTier.ADULT_18_PLUS
    assert teen_yesterday.settings["search_engine_indexing"] is False and adult_today.locked_fields == []


def test_stored_preference_below_new_floor_is_ignored(db):
    user = make_user(db, dob="1980-01-01")
    db.add(UserPrivacyPreference(user_id=user.id, preferences={"search_engine_indexing": True}))
    db.commit()
    # Same stored preference, evaluated on a date when this user was 15:
    old = teen_privacy.resolve_privacy(db, user, on=date(1995, 6, 1))
    assert old.settings["search_engine_indexing"] is False


def test_display_permissions_need_consent_for_minors(consent_world, client, register, outbox, accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.CITY_COUNTRY_DISPLAY))
    p = _privacy(db, minor)
    assert p.display == {"name_display": False, "city_country_display": True, "public_creative_display": False}


# ===========================================================================
# PROFILE / PII (49-55)
# ===========================================================================

def test_49_to_55_public_minor_profile_has_no_sensitive_fields(consent_world, client, register, outbox,
                                                               accept_admin_review):
    db = consent_world
    minor, body = full_flow(client, register, outbox, db, scopes=list(S))
    viewer = make_user(db, dob="1980-01-01")
    for url in (f"/api/v1/users/by-username/{minor.username}", f"/api/v1/users/{minor.id}"):
        r = client.get(url, headers=auth(viewer))
        assert r.status_code == 200
        keys = set(r.json())
        forbidden_keys = {"date_of_birth", "age", "age_tier", "email", "phone_number", "address", "street", "school",
                          "latitude", "longitude", "location", "guardian", "guardian_email"}
        assert not keys & forbidden_keys, keys & forbidden_keys
        values = json.dumps(list(r.json().values()))
        for leak in (body["date_of_birth"], body["email"], "parent.p4@example.com"):
            assert leak not in values, leak


# ===========================================================================
# LEGACY (56-60)
# ===========================================================================

def test_56_to_60_legacy_minors_identified_and_flagged_without_manufacturing(db, client):
    admin = make_user(db, admin=True)
    under13 = make_user(db, dob=years_ago(11))
    teen = make_user(db, dob=years_ago(17))
    adult = make_user(db, dob="1980-01-01")
    unknown = make_user(db, dob=None)
    snapshot = {u.id: (u.date_of_birth, u.country, u.is_active, u.sponsor_id) for u in (under13, teen, adult, unknown)}
    listing = client.get("/api/v1/admin/age-safety/minor-accounts", headers=auth(admin)).json()
    ids = {row["user_id"]: row for row in listing}
    assert set(ids) == {under13.id, teen.id}
    assert ids[under13.id]["age_tier"] == "UNDER_13" and not ids[under13.id]["has_verified_guardian"]
    assert "date_of_birth" not in json.dumps(listing) and db.query(UserAgeProfile).count() == 0   # read-only

    r = client.post(f"/api/v1/admin/age-safety/users/{under13.id}/child-safety-review",
                    json={"note": "legacy account below platform minimum"}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["review_reason"] == "LEGACY_UNDER_MINIMUM_AGE"
    assert db.query(Guardian).count() == 0 and db.query(GuardianConsent).count() == 0            # nothing manufactured
    assert db.query(GuardianRelationship).count() == 0
    for u in (under13, teen, adult, unknown):
        db.refresh(u)
        assert (u.date_of_birth, u.country, u.is_active, u.sponsor_id) == snapshot[u.id]      # no mutation
    assert db.query(UserAgeProfile).count() == 1                                              # only the flagged one
    status = client.get(f"/api/v1/admin/age-safety/users/{teen.id}/guardian-status", headers=auth(admin)).json()
    assert all(v["consent_valid"] is False for v in status["scopes"].values())


# ===========================================================================
# KYC (61-63)
# ===========================================================================

def test_61_to_63_kyc_does_not_imply_guardian_consent_or_assurance(consent_world):
    db = consent_world
    kyc_teen = make_user(db, dob=years_ago(14), identity_verified=True, address_verified=True, is_verified=True,
                         email_verified=True)
    req, check = gc.consent_requirement(db, kyc_teen, S.ACCOUNT_PARTICIPATION, on=TODAY)
    assert req == ConsentRequirement.REQUIRED_MISSING and not check.valid
    assert gc.guardian_for_user(db, kyc_teen) is None
    assert _privacy(db, kyc_teen).age_tier == AgeTier.TEEN_13_15


def test_consent_requirement_dynamic_across_birthday_and_adulthood(consent_world, client, register, outbox,
                                                                  accept_admin_review):
    db = consent_world
    minor, _ = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.PUBLICITY))
    assert gc.consent_requirement(db, minor, S.PUBLICITY, on=TODAY)[0] == ConsentRequirement.SATISFIED
    sixteen = date(minor.date_of_birth.year + 16, minor.date_of_birth.month, minor.date_of_birth.day)
    assert gc.consent_requirement(db, minor, S.PUBLICITY, on=sixteen)[0] == ConsentRequirement.NOT_REQUIRED_BY_POLICY
    eighteen = date(minor.date_of_birth.year + 18, minor.date_of_birth.month, minor.date_of_birth.day)
    req, check = gc.consent_requirement(db, minor, S.PUBLICITY, on=eighteen)
    assert req == ConsentRequirement.NOT_REQUIRED_ADULT
    assert db.query(GuardianConsent).count() == 2                        # history kept after adulthood


def test_consent_undetermined_without_policy(db):
    teen = make_user(db, dob=years_ago(14), country="Kenya")
    assert gc.consent_requirement(db, teen, S.NAME_DISPLAY, on=TODAY)[0] == ConsentRequirement.UNDETERMINED


# ===========================================================================
# SECURITY (65-70) and retention
# ===========================================================================

def test_65_69_no_tokens_passwords_or_dob_in_events_or_audit(consent_world, client, register, outbox,
                                                              accept_admin_review, caplog):
    db = consent_world
    caplog.set_level("DEBUG")
    minor, body = full_flow(client, register, outbox, db, scopes=(S.ACCOUNT_PARTICIPATION, S.MEDIA_USE))
    tokens = TOKEN_RE.findall(" ".join(m["html"] for m in outbox))
    consent = db.query(GuardianConsent).filter(GuardianConsent.consent_scope == "MEDIA_USE").one()
    gc.withdraw_consent(db, consent, actor_id=None, reason="test")
    blobs = [json.dumps({k: str(v) for k, v in e.__dict__.items() if not k.startswith("_")}) for e in db.query(AgeSafetyEvent)]
    blobs += [json.dumps({"o": a.old_values, "n": a.new_values}) for a in db.query(AuditTrail)]
    blob = "\n".join(blobs) + caplog.text
    for secret in tokens + [PASSWORD, body["date_of_birth"], "parent.p4@example.com"]:
        assert secret not in blob


def test_67_68_unauthorized_access_rejected(consent_world, client, register, outbox):
    db = consent_world
    start_pending(register, outbox)
    member = make_user(db, dob="1980-01-01", email_verified=True)
    rel = db.query(GuardianRelationship).one()
    for method, url, body in [
        ("get", "/api/v1/admin/age-safety/guardian-relationships", None),
        ("post", f"/api/v1/admin/age-safety/guardian-relationships/{rel.id}/verify",
         {"method": "ADMIN_DOCUMENT_REVIEW", "note": "attempt by member"}),
        ("post", f"/api/v1/admin/age-safety/guardian-relationships/{rel.id}/reject", {"note": "attempt by member"}),
        ("get", "/api/v1/admin/age-safety/minor-accounts", None),
        ("post", "/api/v1/admin/age-safety/pending-registrations/expire-and-purge", None),
    ]:
        kwargs = {"json": body} if body else {}
        assert getattr(client, method)(url, **kwargs).status_code == 401
        assert getattr(client, method)(url, headers=auth(member), **kwargs).status_code == 403
    assert client.get("/api/v1/guardian/me/consents", headers=auth(member)).status_code == 403
    assert client.get("/api/v1/guardian/me/consents").status_code == 401


def test_70_no_guardian_evidence_in_public_media(db):
    columns = set()
    for model in (Guardian, GuardianRelationship, GuardianConsent, PendingRegistration):
        columns |= set(model.__table__.columns.keys())
    assert not any(k in c for c in columns for k in ("url", "file", "document", "media", "path"))


def test_retention_purges_personal_data_but_keeps_consent_history(consent_world, client, register, outbox,
                                                                  accept_admin_review):
    db = consent_world
    full_flow(client, register, outbox, db)
    p = db.query(PendingRegistration).one()
    p.updated_at = datetime.utcnow() - timedelta(days=31)
    db.commit()
    assert gc.expire_and_purge(db)["purged"] == 1
    db.refresh(p)
    assert p.email is None and p.date_of_birth is None and p.username is None and p.data_purged_at is not None
    assert db.query(GuardianConsent).count() == 1 and db.query(GuardianRelationship).count() == 1


def test_guardian_notification_only_through_outbox(consent_world, register, outbox):
    start_pending(register, outbox)
    assert len(outbox) == 1 and outbox[0]["to"] == "parent.p4@example.com"


# ===========================================================================
# REGRESSION (71-73) quick checks (the full suites cover the rest)
# ===========================================================================

def test_71_73_phase3_behaviour_unchanged(db, register):
    blocked, _ = register(date_of_birth=years_ago(12), guardian_email="parent.x@example.com")
    assert blocked.status_code == 403 and blocked.json()["decision"] == "BELOW_MINIMUM_ACCOUNT_AGE"
    assert db.query(PendingRegistration).count() == 0                     # no guardian path for under-13
    ok, _ = register(date_of_birth=years_ago(14), ip="198.51.100.230", guardian_email="parent.y@example.com")
    assert ok.status_code == 201                                          # enforcement off: transition unchanged
    profile = db.query(UserAgeProfile).one()
    assert profile.registration_decision == "POLICY_NOT_ENFORCED"
    assert db.query(Guardian).count() == 0
