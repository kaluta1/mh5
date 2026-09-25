"""Phase 3 final hardening: sensitive-field redaction, platform baseline vs
jurisdiction policy, transition mode is not legal approval, operational config,
keyed hashing, DOB audit privacy, and the terms-acceptance limitation.

Policies here are SYNTHETIC test data.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.core import age_safety_config as cfgmod
from app.core.age_safety_config import AgeSafetyOperationalConfig, override_age_safety_config
from app.core.child_safety import (
    ContentRating,
    DecisionBasis,
    PolicyOperation,
    PolicyOutcome,
    RegistrationDecision,
)
from app.core.config import settings
from app.core.redaction import REDACTED, is_sensitive_field, redact_sensitive
from app.models.accounting import AuditTrail
from app.models.age_policy import AgePolicy
from app.models.age_safety import AgeSafetyEvent, UserAgeProfile
from app.models.user import User
from app.services import age_gate
from app.services.age_policy_engine import AgeAndContestPolicyEngine, utc_today
from tests.unit.test_age_gate_registration import (  # noqa: F401
    REGISTER,
    auth,
    blocked,
    created,
    enforce,
    make_user,
    payload,
    profile_of,
    register,
    years_ago,
)
from tests.unit.test_age_policy_engine import add_policy

TODAY = utc_today()

SENSITIVE_NAMES = [
    "password", "current_password", "new_password", "password_confirmation", "passwordConfirmation",
    "currentPassword", "secret", "client_secret", "clientSecret", "api_key", "apiKey", "API-KEY", "token",
    "access_token", "accessToken", "refresh_token", "refreshToken", "otp", "pin", "cardPin", "cvv", "seed",
    "seed_phrase", "mnemonic", "private_key", "privateKey",
]
ORDINARY_NAMES = ["email", "username", "country", "shipping", "opinion", "pinned", "spinner", "tokenizer",
                  "description", "date_of_birth", "passport_number", "seeding_round", "keyword"]


# ===========================================================================
# 1. Recursive sensitive-field redaction
# ===========================================================================

@pytest.mark.parametrize("name", SENSITIVE_NAMES)
def test_sensitive_name_variants_detected(name):
    assert is_sensitive_field(name)


@pytest.mark.parametrize("name", ORDINARY_NAMES)
def test_ordinary_names_not_redacted(name):
    assert not is_sensitive_field(name)


def test_nested_and_list_redaction():
    body = {"email": "a@example.com", "auth": {"currentPassword": "p1", "tokens": [{"refresh_token": "r1"}]},
            "card": {"cvv": "123", "holder": "Ann"}, "items": [{"api-key": "k"}, {"note": "keep"}]}
    out = redact_sensitive(body)
    assert out["email"] == "a@example.com" and out["card"]["holder"] == "Ann" and out["items"][1]["note"] == "keep"
    blob = json.dumps(out)
    for secret in ("p1", "r1", "123", '"k"'):
        assert secret not in blob
    assert out["auth"]["currentPassword"] == REDACTED and out["card"]["cvv"] == REDACTED


def test_validation_response_never_echoes_sensitive_values(client):
    secrets = {"password": "TopSecret*Passw0rd1", "new_password": "NewSecret*2", "client_secret": "cs-777",
               "refreshToken": "rt-888", "mnemonic": "alpha beta gamma", "private_key": "pk-999"}
    # Missing date_of_birth/accept_terms -> 'missing' errors carry the whole body; extra keys are forbidden.
    r = client.post(REGISTER, json={"email": "redact@example.com", **secrets,
                                     "nested": {"pin": "4321", "profile": {"otp": "654321"}}})
    assert r.status_code == 422
    for value in list(secrets.values()) + ["4321", "654321"]:
        assert value not in r.text
    assert "redact@example.com" in r.text  # ordinary input still echoed


# ===========================================================================
# 2-3. Platform baseline vs jurisdiction policy; transition is not legal approval
# ===========================================================================

def _basis_of_last_attempt(db) -> str:
    return db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type == "AGE_GATE_ATTEMPT") \
        .order_by(AgeSafetyEvent.id.desc()).first().details["basis"]


def test_under_13_blocked_by_platform_baseline_in_transition(db, register):
    blocked(register(date_of_birth=years_ago(12))[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    assert _basis_of_last_attempt(db) == DecisionBasis.PLATFORM_BASELINE.value


def test_stricter_enforced_policy_is_authoritative_over_baseline(db, register):
    add_policy(db, minimum_account_age=17, minimum_independent_participation_age=17, parental_consent_age=17,
               voting_minimum_age=17, nomination_minimum_age=17, personal_submission_minimum_age=17,
               livestream_minimum_age=17, payment_minimum_age=17)
    enforce(db, "TZ")
    blocked(register(date_of_birth=years_ago(15))[0], RegistrationDecision.BELOW_MINIMUM_ACCOUNT_AGE)
    assert _basis_of_last_attempt(db) == DecisionBasis.JURISDICTION_POLICY.value


def test_baseline_never_allows_what_a_stricter_policy_denies(db):
    add_policy(db, minimum_account_age=16, minimum_independent_participation_age=16, parental_consent_age=16,
               voting_minimum_age=16, nomination_minimum_age=16, personal_submission_minimum_age=16,
               livestream_minimum_age=16)
    enforce(db, "TZ")
    r = age_gate.evaluate_registration(db, date_of_birth=date.fromisoformat(years_ago(14)), country="TZ",
                                       email="strict@example.com", ip="203.0.113.5", on=TODAY)
    assert not r.allowed and r.basis == DecisionBasis.JURISDICTION_POLICY


def test_transition_registration_is_not_legal_approval(db, register):
    resp, _ = register(date_of_birth=years_ago(13))
    user = created(db, resp)
    p = profile_of(db, user)
    assert p.registration_decision == RegistrationDecision.POLICY_NOT_ENFORCED.value
    assert p.registration_decision != RegistrationDecision.ALLOWED.value
    assert p.registration_enforced is False and p.registration_policy_id is None
    assert p.registration_policy_outcome == PolicyOutcome.UNSUPPORTED_JURISDICTION.value  # no policy: recorded as-is
    assert _basis_of_last_attempt(db) == DecisionBasis.TRANSITION_NOT_ENFORCED.value
    for word in ("eligible", "legal", "approved"):
        assert word not in resp.text.lower()


def test_transition_gate_result_is_not_legally_resolved(db):
    r = age_gate.evaluate_registration(db, date_of_birth=date(1990, 1, 1), country="Tanzania",
                                       email="t@example.com", ip="203.0.113.6", on=TODAY)
    assert r.decision == RegistrationDecision.POLICY_NOT_ENFORCED and not r.legally_resolved
    assert r.policy_decision.outcome == PolicyOutcome.UNSUPPORTED_JURISDICTION


def test_policy_allowed_only_with_enforced_resolved_policy(db, register):
    add_policy(db)
    enforce(db, "TZ")
    p = profile_of(db, created(db, register()[0]))
    assert p.registration_decision == "ALLOWED" and p.registration_enforced and p.registration_policy_id is not None
    assert _basis_of_last_attempt(db) == DecisionBasis.JURISDICTION_POLICY.value


def test_transition_adult_gets_no_later_phase_eligibility(db, register):
    user = created(db, register(date_of_birth="1970-01-01")[0])
    engine = AgeAndContestPolicyEngine(db)
    ctx = engine.context_for_user(user, TODAY, profile_of(db, user))
    assert not ctx.adult_content_eligible and not ctx.legal_adult
    assert engine.permitted_content_ratings(ctx) == frozenset()
    for op in PolicyOperation:  # contest, prize, payment... none allowed without a policy
        assert engine.evaluate(ctx, op).outcome == PolicyOutcome.UNSUPPORTED_JURISDICTION


def test_unresolved_jurisdiction_stays_visible_internally(db, client, register):
    admin = make_user(db, admin=True)
    user = created(db, register(country="Tanznia")[0])
    assert profile_of(db, user).registration_policy_outcome == PolicyOutcome.UNKNOWN_JURISDICTION.value
    status = client.get(f"/api/v1/admin/age-safety/users/{user.id}/age-status", headers=auth(admin)).json()
    assert status["jurisdiction_status"] == "UNRESOLVED" and status["policy_status"] == "NOT_FOUND"
    assert status["registration_decision"] == "POLICY_NOT_ENFORCED"


def test_blocked_messages_make_no_legal_or_threshold_claims():
    for decision, message in age_gate.CLIENT_MESSAGES.items():
        low = message.lower()
        assert "13" not in low and "eligible" not in low and "legal" not in low, decision


# ===========================================================================
# 4. Operational configuration
# ===========================================================================

def test_config_defaults_are_the_documented_operational_values():
    c = AgeSafetyOperationalConfig()
    assert (c.retry_email_max, c.retry_email_window_hours, c.retry_ip_max, c.retry_ip_window_minutes) == (5, 24, 20, 60)
    assert (c.email_correlation_days, c.tier_hopping_distinct_tiers, c.dob_change_window_days) == (30, 3, 365)


@pytest.mark.parametrize("bad", [{"retry_email_max": 0}, {"retry_ip_max": -1}, {"tier_hopping_distinct_tiers": 5},
                                 {"tier_hopping_distinct_tiers": 1}, {"dob_change_window_days": 0},
                                 {"ip_immediate_window_minutes": 600, "ip_correlation_hours": 1}, {"unknown": 1}])
def test_config_rejects_nonsensical_values(bad):
    with pytest.raises(ValidationError):
        AgeSafetyOperationalConfig(**bad)


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("AGE_SAFETY_RETRY_EMAIL_MAX", "9")
    assert cfgmod._from_env().retry_email_max == 9
    monkeypatch.setenv("AGE_SAFETY_RETRY_EMAIL_MAX", "0")
    with pytest.raises(ValidationError):
        cfgmod._from_env()


def test_config_override_changes_behavior_deterministically(db):
    def attempt(ip):
        return age_gate.evaluate_registration(db, date_of_birth=date(1990, 1, 1), country="TZ",
                                              email="cfg@example.com", ip=ip, on=TODAY)

    age_gate.record_attempt(db, attempt("203.0.113.7"))            # one attempt for this email
    with override_age_safety_config(retry_email_max=1):
        assert attempt("203.0.113.8").decision == RegistrationDecision.RETRY_LIMITED
    assert attempt("203.0.113.9").allowed                           # default (5) restored afterwards


def test_dob_change_limit_is_configurable(db, client):
    user = make_user(db, dob="1990-01-15")
    with override_age_safety_config(dob_max_self_changes_in_window=2):
        assert client.put("/api/v1/users/me", json={"date_of_birth": "1990-02-15"}, headers=auth(user)).status_code == 200
        assert client.put("/api/v1/users/me", json={"date_of_birth": "1990-03-15"}, headers=auth(user)).status_code == 200
        assert client.put("/api/v1/users/me", json={"date_of_birth": "1990-04-15"}, headers=auth(user)).status_code == 409


def test_operational_thresholds_are_not_agepolicy_fields():
    policy_columns = set(AgePolicy.__table__.columns.keys())
    assert not (set(AgeSafetyOperationalConfig.model_fields) & policy_columns)


# ===========================================================================
# 5. Keyed hashing / identifier privacy
# ===========================================================================

def test_safety_hash_is_keyed_hmac_not_plain_hash(monkeypatch):
    monkeypatch.setattr(settings, "AGE_SAFETY_HASH_KEY", "")
    h = age_gate.safety_hash("email", "  Person@Example.com ")
    key = hmac.new(settings.SECRET_KEY.encode(), b"mh5-age-safety-v1", hashlib.sha256).digest()
    assert h == hmac.new(key, b"email:person@example.com", hashlib.sha256).hexdigest()
    assert h != hashlib.sha256(b"person@example.com").hexdigest()
    assert h != hashlib.sha256(b"email:person@example.com").hexdigest()


def test_dedicated_key_and_rotation_break_correlation(monkeypatch):
    monkeypatch.setattr(settings, "AGE_SAFETY_HASH_KEY", "")
    derived = age_gate.safety_hash("ip", "192.0.2.1")
    monkeypatch.setattr(settings, "AGE_SAFETY_HASH_KEY", "dedicated-test-key-A")
    a = age_gate.safety_hash("ip", "192.0.2.1")
    monkeypatch.setattr(settings, "AGE_SAFETY_HASH_KEY", "dedicated-test-key-B")
    b = age_gate.safety_hash("ip", "192.0.2.1")
    assert len({derived, a, b}) == 3


def test_no_raw_identifiers_or_dob_in_events_or_audit(db, client, register):
    admin = make_user(db, admin=True)
    resp, body = register(ip="198.51.100.120", date_of_birth="1991-07-04")
    user = created(db, resp)
    client.put("/api/v1/users/me", json={"date_of_birth": "1991-08-04"}, headers=auth(user))
    client.put(f"/api/v1/admin/age-safety/users/{user.id}/date-of-birth",
               json={"date_of_birth": "1991-09-04", "reason": "support fix"}, headers=auth(admin))
    enforce(db, "TZ", enabled=False)
    stored = []
    for e in db.query(AgeSafetyEvent).all():
        stored.append(json.dumps({k: str(v) for k, v in e.__dict__.items() if not k.startswith("_")}))
    for a in db.query(AuditTrail).all():
        stored.append(json.dumps({"old": a.old_values, "new": a.new_values}))
    blob = "\n".join(stored)
    for raw in (body["email"], "198.51.100.120", "1991-07-04", "1991-08-04", "1991-09-04", "1991"):
        assert raw not in blob
    # ordinary account storage is unaffected
    assert db.query(User).filter(User.email == body["email"]).count() == 1


# ===========================================================================
# 7. Terms acceptance
# ===========================================================================

def test_terms_acceptance_recorded_without_invented_version(db, register):
    p = profile_of(db, created(db, register()[0]))
    assert isinstance(p.terms_accepted_at, datetime)
    assert not any("version" in c and "terms" in c for c in UserAgeProfile.__table__.columns.keys())
    assert register(accept_terms=False, ip="198.51.100.130")[0].status_code == 422
