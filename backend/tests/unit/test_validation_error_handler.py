"""Shared request-validation error handler (main.validation_exception_handler).

Root cause fixed: ValueError-based validators put the exception object in the
Pydantic error ctx, and the handler returned exc.errors() unencoded, so the
JSON response failed and the request became HTTP 500. It now always returns a
JSON-safe 422 with the same envelope, and sensitive submitted values are
redacted.
"""
from __future__ import annotations

import copy
import json
import uuid

import pytest
from fastapi.exceptions import RequestValidationError

from app.core.security import create_access_token
from app.models.age_policy import AgePolicy
from app.models.user import User
from tests.unit.test_age_policy_engine import synthetic_definition

URL = "/api/v1/admin/age-policies"


@pytest.fixture
def admin_headers(db):
    admin = User(email=f"val-{uuid.uuid4().hex[:8]}@example.com", hashed_password="unused",
                 is_active=True, is_admin=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}


def _payload(**overrides):
    return synthetic_definition(effective_date="2099-01-01", **overrides)


def _assert_safe_422(response, expect_msg: str = ""):
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Request validation failed"
    assert isinstance(body["detail"], list) and body["detail"]
    for err in body["detail"]:
        assert {"type", "loc", "msg"} <= set(err)
    text = response.text
    assert "Traceback" not in text and 'File "' not in text and "site-packages" not in text
    if expect_msg:
        assert expect_msg in " ".join(e["msg"] for e in body["detail"])
    return body


# ---- AgePolicy endpoints (previously HTTP 500) -----------------------------

@pytest.mark.parametrize(
    "overrides, expect",
    [
        ({"adult_age": 17}, "adult_age must be at least 18"),
        ({"minimum_account_age": 12, "voting_minimum_age": 12, "nomination_minimum_age": 12,
          "personal_submission_minimum_age": 12}, "minimum_account_age must be at least 13"),
        ({"parental_consent_age": 25}, "parental_consent_age"),
        ({"voting_minimum_age": 200}, ""),
        ({"jurisdiction": "XX"}, "supported ISO"),
    ],
)
def test_invalid_age_thresholds_return_422(client, db, admin_headers, overrides, expect):
    _assert_safe_422(client.post(URL, json=_payload(**overrides), headers=admin_headers), expect)
    assert db.query(AgePolicy).count() == 0


def test_invalid_status_or_unknown_fields_return_422(client, admin_headers):
    # status is lifecycle-managed and not part of the definition (extra="forbid").
    _assert_safe_422(client.post(URL, json={**_payload(), "status": "ACTIVE"}, headers=admin_headers))
    _assert_safe_422(client.post(URL, json={**_payload(), "policy_version": 7}, headers=admin_headers))


def test_invalid_configuration_returns_422(client, admin_headers):
    ratings = copy.deepcopy(_payload()["permitted_content_ratings"])
    ratings["by_tier"]["ADULT_18_PLUS"].append("PROHIBITED")
    _assert_safe_422(client.post(URL, json=_payload(permitted_content_ratings=ratings), headers=admin_headers),
                     "PROHIBITED")


@pytest.mark.parametrize(
    "field, value",
    [
        ("profile_visibility_rules", {"by_tier": {"TEEN_13_15": {"search_engine_indexing": "yes please"}}}),
        ("profile_visibility_rules", {"by_tier": "not-an-object"}),
        ("advertising_restrictions", {"by_tier": {"UNKNOWN": {"targeted_advertising_allowed": True}}}),
        ("age_assurance_level", {"default": "TRUST_ME"}),
        ("kyc_requirement", {"operations": ["ACCOUNT_CREATION", "ACCOUNT_CREATION"]}),
        ("parental_consent_requirement", ["not", "an", "object"]),
    ],
)
def test_invalid_nested_structures_return_422(client, admin_headers, field, value):
    _assert_safe_422(client.post(URL, json=_payload(**{field: value}), headers=admin_headers))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"content": b"{not json", "headers_extra": {"Content-Type": "application/json"}},
        {"content": b"[1, 2, 3]", "headers_extra": {"Content-Type": "application/json"}},
        {"content": b"", "headers_extra": {"Content-Type": "application/json"}},
    ],
)
def test_malformed_payloads_return_422(client, admin_headers, kwargs):
    headers = {**admin_headers, **kwargs["headers_extra"]}
    _assert_safe_422(client.post(URL, content=kwargs["content"], headers=headers))


def test_undecodable_body_is_a_safe_client_error(client, admin_headers):
    # Non-UTF-8 bytes are rejected by FastAPI's body parser (400) before validation.
    r = client.post(URL, content=b"\xff\xfe\x00binary", headers={**admin_headers, "Content-Type": "application/json"})
    assert r.status_code == 400
    assert "Traceback" not in r.text and "site-packages" not in r.text


def test_invalid_query_parameter_returns_422(client, admin_headers):
    _assert_safe_422(client.get(f"{URL}/resolve", params={"jurisdiction": "TZ", "on_date": "not-a-date"},
                                headers=admin_headers))


def test_validation_still_requires_admin_first(client):
    # Unauthenticated callers are rejected before the body is validated.
    assert client.post(URL, json=_payload(adult_age=17)).status_code == 401


# ---- serialization of previously failing values ----------------------------

def test_handler_serializes_exception_objects_and_arbitrary_values():
    from main import _safe_validation_errors

    class Opaque:
        def __repr__(self):
            return "<Opaque>"

    errors = [
        {"type": "value_error", "loc": ("body", "x"), "msg": "Value error, bad", "input": b"\xff\x00",
         "ctx": {"error": ValueError("bad"), "obj": Opaque(), "limit": {1, 2}}},
        {"type": "value_error", "loc": ("body", "nested", 0), "msg": "m", "input": {"k": ValueError("inner")}},
    ]
    safe = _safe_validation_errors(RequestValidationError(errors).errors())
    json.dumps(safe)  # must not raise
    assert safe[0]["ctx"]["error"] == "bad"
    assert safe[0]["loc"] == ["body", "x"]
    assert safe[1]["input"] == {"k": "inner"}


# ---- existing non-AgePolicy endpoints --------------------------------------

def test_registration_weak_password_is_422_not_500_and_not_echoed(client):
    secret = "weakpw"
    r = client.post("/api/v1/auth/register", json={"email": "val@example.com", "password": secret, "username": "valuser1"})
    body = _assert_safe_422(r, "Password must be at least 12 characters")
    assert secret not in r.text
    pw_errors = [e for e in body["detail"] if "password" in e["loc"]]
    assert pw_errors and all(e["input"] == "[REDACTED]" for e in pw_errors)


def test_registration_bad_email_keeps_existing_422_shape(client):
    r = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "Str0ng*Passw0rd!"})
    body = _assert_safe_422(r)
    email_err = next(e for e in body["detail"] if "email" in e["loc"])
    assert email_err["input"] == "not-an-email"  # non-sensitive inputs are unchanged
    assert email_err["loc"] == ["body", "email"]


def test_registration_extra_field_rejected_as_before(client):
    r = client.post("/api/v1/auth/register", json={"email": "x@example.com", "password": "Str0ng*Passw0rd!", "is_admin": True})
    body = _assert_safe_422(r)
    assert any(e["type"] == "extra_forbidden" for e in body["detail"])


def test_login_missing_form_fields_is_422(client):
    body = _assert_safe_422(client.post("/api/v1/auth/login", data={}))
    assert all(e["input"] in (None, "[REDACTED]") or "password" not in e["loc"] for e in body["detail"])
