"""Phase 4.1: database/session error logging never writes sensitive submitted
values (passwords, tokens, keys, emails, DOB, SQL bound parameters) to logs.

Every secret below is synthetic and distinctive; each test asserts it occurs
nowhere in the captured log output (messages AND formatted tracebacks).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, StatementError

import app.db.session as session_module
from app.core.redaction import describe_exception, safe_traceback
from app.db.session import get_db
from tests.conftest import TestingSessionLocal

PW = "Pw-SECRET-7f3a9c!Zq"
LONG_PW = "L" * 240 + "LONGPW-SECRET-TAIL-91"
ACCESS = "eyJ-ACCESS-TOKEN-SECRET-4411"
REFRESH = "REFRESH-TOKEN-SECRET-5522"
GTOKEN = "GUARDIAN-TOKEN-SECRET-abcdefghijklmnop0123456789"
CTOKEN = "COMPLETION-TOKEN-SECRET-qrstuvwxyz9876543210ABCD"
API_KEY = "sk_live_APIKEY_SECRET_77"
CLIENT_SECRET = "CLIENT-SECRET-VALUE-88"
OTP = "OTP-SECRET-123987"
SEED = "SEED-MNEMONIC-SECRET-abandon-zoo"
EMAIL = "leaky.person.91@example.com"
DOB = "2011-04-17"
ALL_SECRETS = (PW, "LONGPW-SECRET-TAIL-91", ACCESS, REFRESH, GTOKEN, CTOKEN, API_KEY, CLIENT_SECRET, OTP, SEED,
               EMAIL, DOB)


def assert_clean(text_: str):
    leaked = [s for s in ALL_SECRETS if s in text_]
    assert not leaked, f"sensitive values in logs: {leaked}"


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture
def test_sessions(monkeypatch):
    """get_db() must never open the configured (real) database in these tests."""
    monkeypatch.setattr(session_module, "SessionLocal", TestingSessionLocal)


def drive_get_db(exc: BaseException):
    """Throw `exc` into the real get_db() dependency, as FastAPI does when the
    endpoint (or request validation) fails while the session is open."""
    gen = get_db()
    next(gen)
    with pytest.raises(BaseException) as raised:
        gen.throw(exc)
    return raised.value


def real_integrity_error(db) -> IntegrityError:
    try:
        db.execute(text("INSERT INTO users (email, hashed_password, date_of_birth) VALUES (:e, :p, :d)"),
                   {"e": EMAIL, "p": PW, "d": DOB})
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        return exc
    raise AssertionError("expected an IntegrityError")


class FakePgError(Exception):
    """Shape of a psycopg2 error: message with row values, plus pgcode/diag."""

    pgcode = "23505"
    diag = SimpleNamespace(schema_name="public", table_name="users", column_name=None,
                           constraint_name="users_email_key")


# ---- through HTTP, with the REAL get_db dependency ----------------------------

@pytest.fixture
def real_get_db(client, app):
    app.dependency_overrides.pop(get_db, None)     # the client fixture restores everything afterwards
    return client


@pytest.mark.parametrize("path,body", [
    ("/api/v1/auth/register/complete", {"token": "x", "password": PW}),                  # 1 password
    ("/api/v1/auth/register/complete", {"token": CTOKEN, "password": LONG_PW}),          # 2 long password
    ("/api/v1/auth/register/complete", {"token": CTOKEN}),                               # 5 completion token
    ("/api/v1/guardian/requests/respond", {"token": GTOKEN, "scopes": []}),              # 4 guardian token
    ("/api/v1/auth/register", {"email": EMAIL, "username": "leaky91", "password": PW,    # 7/8 email, DOB
                               "date_of_birth": DOB, "country": "Tanzania"}),
])
def test_rejected_input_never_reaches_logs_or_response(real_get_db, logs, path, body):
    r = real_get_db.post(path, json=body)
    assert r.status_code == 422
    assert_clean(logs.text)
    for secret in (PW, "LONGPW-SECRET-TAIL-91", GTOKEN, CTOKEN):             # 12 no echo in the API response
        assert secret not in r.text
    assert "Unexpected error in database session" not in logs.text        # client errors are not DB errors


# ---- get_db() branches ---------------------------------------------------------

def test_validation_error_with_nested_secrets_is_summarized(test_sessions, logs):
    exc = RequestValidationError([{
        "type": "missing", "loc": ("body", "profile"), "msg": "Field required",
        "input": {"access_token": ACCESS, "refresh_token": REFRESH, "api_key": API_KEY,
                  "client_secret": CLIENT_SECRET, "nested": [{"otp": OTP, "seed": SEED}], "email": EMAIL}}])
    assert drive_get_db(exc) is exc
    assert_clean(logs.text)                                                  # 3, 6, 10
    assert "RequestValidationError errors=1 [body.profile:missing]" in logs.text


def test_sqlalchemy_bound_parameters_not_logged(test_sessions, db, logs, monkeypatch):
    exc = real_integrity_error(db)
    assert EMAIL in str(exc) and PW in str(exc)                              # precondition: the raw message leaks
    monkeypatch.setenv("DEBUG", "true")                                      # debug responses include a summary
    raised = drive_get_db(exc)
    assert isinstance(raised, HTTPException) and raised.status_code == 503
    assert_clean(logs.text)                                                  # 9 bound parameters
    assert_clean(str(raised.detail))
    assert "IntegrityError" in logs.text and "sql=INSERT users" in logs.text   # 11 useful metadata
    assert "Traceback (values omitted)" in logs.text and "real_integrity_error" in logs.text


def test_driver_message_row_values_not_logged(test_sessions, logs):
    orig = FakePgError(f'duplicate key value violates unique constraint "users_email_key"\n'
                       f"DETAIL:  Key (email)=({EMAIL}) already exists.")
    exc = IntegrityError("INSERT INTO users (email, hashed_password) VALUES (%(email)s, %(pw)s)",
                         {"email": EMAIL, "pw": PW}, orig)
    assert EMAIL in str(exc)
    drive_get_db(exc)
    assert_clean(logs.text)
    for safe in ("sqlstate=23505", "constraint_name=users_email_key", "table_name=users", "driver=FakePgError"):
        assert safe in logs.text


def test_interpolated_sql_literal_not_logged(test_sessions, logs):
    exc = StatementError("boom", f"UPDATE users SET api_key='{API_KEY}', email='{EMAIL}' WHERE id=1",
                         None, ValueError(f"bad value {API_KEY}"))
    drive_get_db(exc)
    assert_clean(logs.text)
    assert "sql=UPDATE users" in logs.text
    literal = StatementError("boom", f"SELECT 'note from {SEED}' FROM users", None, ValueError("x"))
    assert SEED not in describe_exception(literal) and "sql=SELECT users" in describe_exception(literal)


def test_connection_error_keeps_reason_without_values(test_sessions, logs):
    orig = Exception('connection to server at "db.internal.example" (10.0.0.9), port 5432 failed: timeout expired')
    exc = OperationalError("SELECT * FROM users WHERE email = %(e)s", {"e": EMAIL}, orig)
    raised = drive_get_db(exc)
    assert isinstance(raised, HTTPException) and raised.status_code == 503
    assert_clean(logs.text)
    assert "timeout expired" in logs.text and "db.internal.example" not in logs.text


@pytest.mark.parametrize("message", [
    f"could not connect: postgresql://dbuser91:{PW}@db.internal.example:5432/app?sslmode=require",
    f"invalid connection option: user=dbuser91 password={PW} host=db.internal.example",
    f'FATAL:  password authentication failed for user "dbuser91"\nDETAIL: {PW}',
])
def test_connection_error_never_exposes_credentials(test_sessions, logs, message):
    drive_get_db(OperationalError("SELECT 1", {"e": EMAIL}, Exception(message)))
    assert_clean(logs.text)
    for value in ("dbuser91", "db.internal.example"):
        assert value not in logs.text
    assert "OperationalError" in logs.text


def test_unexpected_error_logs_type_and_frames_only(test_sessions, logs):
    def failing_operation():
        raise ValueError(f"cannot process {EMAIL} with password {PW}")
    try:
        failing_operation()
    except ValueError as exc:
        err = exc
    assert drive_get_db(err) is err                                          # re-raised unchanged
    assert_clean(logs.text)
    assert "Unexpected error in database session: ValueError" in logs.text
    assert "failing_operation" in logs.text                                  # traceback frames kept


def test_authenticate_database_error_not_logged_with_identifier(db, logs, monkeypatch):
    from app.crud.crud_user import user as crud_user

    def boom(*a, **k):
        raise IntegrityError("SELECT * FROM users WHERE email = %(e)s", {"e": EMAIL}, FakePgError(f"x {EMAIL}"))
    monkeypatch.setattr(type(crud_user), "get_by_email", boom)
    with pytest.raises(IntegrityError):
        crud_user.authenticate(db, email_or_username=EMAIL, password=PW)
    assert_clean(logs.text)
    assert "Database error during authentication: IntegrityError" in logs.text


# ---- database errors that escape get_db() --------------------------------------

def test_escaping_database_error_is_logged_safely_with_same_response(client, app, logs):
    async def uses_own_session():
        raise IntegrityError("INSERT INTO pending_registrations (email, guardian_token_hash) VALUES (?, ?)",
                             (EMAIL, GTOKEN), FakePgError(f"DETAIL: Key (email)=({EMAIL})"))
    app.add_api_route("/__test__/db-escape", uses_own_session, methods=["GET"])
    try:
        r = client.get("/__test__/db-escape")
    finally:
        app.router.routes[:] = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/__test__/db-escape"]
    assert r.status_code == 500 and r.text == "Internal Server Error"
    assert_clean(logs.text)
    assert "GET /__test__/db-escape database error: IntegrityError" in logs.text


# ---- helpers ------------------------------------------------------------------------

def test_describe_exception_keeps_chain_types_not_messages():
    try:
        try:
            raise KeyError(API_KEY)
        except KeyError as inner:
            raise RuntimeError(f"wrapped {PW}") from inner
    except RuntimeError as exc:
        summary, tb = describe_exception(exc), safe_traceback(exc)
    assert summary == "RuntimeError <- KeyError"
    assert_clean(summary + tb)
    assert "-- caused --" in tb
