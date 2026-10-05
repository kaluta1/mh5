"""EMAIL-2: authentication email + account security.

Registration (no account enumeration), email verification (purpose-bound,
short-lived, one-time credentials held as digests), resend, welcome lifecycle,
password reset, durable rate limits, client address behind the trusted proxy,
session invalidation on password change / reset, and what happens to the
account when the email system fails.

Everything is SYNTHETIC. No test contacts Resend: emails go to the in-memory
FakeEmailProvider (conftest.email_outbox). Addresses are documentation ranges.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from starlette.requests import Request

import app.core.rate_limit as rl
from app.core import client_ip as client_ip_module
from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.security import (
    create_access_token, create_kyc_document_view_token, get_password_hash, verify_kyc_document_view_token,
    verify_password,
)
from app.models.accounting import AuditTrail
from app.models.auth_security import (
    PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET, AuthRateLimit, AuthToken,
)
from app.models.email import EmailDelivery, EmailEventSetting
from app.models.login_log import LoginLog
from app.models.user import User
from app.services import auth_security, auth_throttle, auth_tokens
from app.services import email_settings_service as svc
from app.services import email_templates as tpl
from app.services.email import email_service
from app.services.email_events import EmailEvent, get_event
from app.services.email_providers import FAIL_NETWORK, ProviderResult
from app.services.email_render import RenderError, render

A = "/api/v1/auth"
PW = "Str0ng*Passw0rd!"
PW2 = "N3w*Passw0rd!xy"
PW3 = "Third*Passw0rd!9"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def ip(monkeypatch):
    """Choose the client address the application sees (the limiter middleware
    and the auth endpoints read the same function)."""
    state = {"ip": "198.51.100.1"}
    monkeypatch.setattr(rl, "_client_ip", lambda request: state["ip"])

    def use(address: str) -> None:
        state["ip"] = address
    return use


def body(**over) -> dict:
    uid = uuid.uuid4().hex[:8]
    base = {"email": f"e2_{uid}@example.com", "username": f"e2_{uid}", "password": PW,
            "date_of_birth": "1990-01-15", "accept_terms": True, "country": "Tanzania"}
    base.update(over)
    return base


def member(db, *, password=PW, verified=False, active=True, **extra) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(email=extra.pop("email", f"m_{uid}@example.com"), username=f"m_{uid}",
                hashed_password=get_password_hash(password), is_active=active, email_verified=verified, **extra)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, user_or_email, password=PW):
    email = user_or_email if isinstance(user_or_email, str) else user_or_email.email
    return client.post(f"{A}/login", data={"username": email, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def link_token(mail: dict, page: str) -> str:
    """The one-time credential inside an email's link."""
    return re.search(rf"/{page}#token=([\w\-]+)", mail["html"]).group(1)


def events(db):
    return [r.event_key for r in db.query(EmailDelivery).order_by(EmailDelivery.id).all()]


def issue(db, user, purpose) -> str:
    raw = auth_tokens.issue(db, user, purpose)
    db.commit()
    return raw


def restart():
    """A process restart: the in-memory limiter forgets everything."""
    rl._buckets.clear()


def audits(db, action):
    return db.query(AuditTrail).filter(AuditTrail.action == action).all()


def everything_stored(db) -> str:
    """Every value in the tables a credential could leak into."""
    parts = []
    for model in (EmailDelivery, AuditTrail, AuthToken, AuthRateLimit, LoginLog):
        for row in db.query(model).all():
            parts += [str(getattr(row, c.name)) for c in model.__table__.columns]
    return " ".join(parts)


# ===========================================================================
# REGISTRATION
# ===========================================================================

def test_new_registration_creates_an_unverified_account_and_queues_only_the_verification(client, db, email_outbox, ip):
    data = body()
    r = client.post(f"{A}/register", json=data)
    assert r.status_code == 201
    assert r.json() == {"message": r.json()["message"], "detail": r.json()["message"],
                        "code": "REGISTRATION_ACCEPTED", "email": data["email"]}
    user = db.query(User).filter(User.email == data["email"]).one()
    assert (user.email_verified, user.security_version, user.is_active) == (False, 0, True)
    assert events(db) == ["AUTH.EMAIL_VERIFICATION"]                        # no welcome yet
    assert login(client, data["email"]).status_code == 200                  # sign-in itself is unchanged


def test_registration_answer_is_the_same_for_new_verified_and_unverified_addresses(client, db, email_outbox, ip,
                                                                                    monkeypatch):
    verified = member(db, verified=True)
    unverified = member(db, verified=False)
    before = {u.id: (u.hashed_password, u.username, u.email_verified, u.security_version)
              for u in (verified, unverified)}
    hashes = []
    real_hash = get_password_hash
    import app.api.api_v1.endpoints.auth as auth_endpoints
    import app.crud.crud_user as crud_module

    def counting(password):
        hashes.append(1)
        return real_hash(password)
    monkeypatch.setattr(auth_endpoints, "get_password_hash", counting)
    monkeypatch.setattr(crud_module, "get_password_hash", counting)

    answers = {}
    for label, email in (("new", "brand.new@example.com"), ("verified", verified.email),
                         ("unverified", unverified.email), ("case", verified.email.upper())):
        hashes.clear()
        r = client.post(f"{A}/register", json=body(email=email))
        answers[label] = r
        assert len(hashes) == 1, label                                      # same dominant cost on every path
    statuses = {a.status_code for a in answers.values()}
    assert statuses == {201}
    shapes = {tuple(sorted(a.json())) for a in answers.values()}
    assert len(shapes) == 1
    assert len({(a.json()["message"], a.json()["code"]) for a in answers.values()}) == 1
    assert len({tuple(sorted(k.lower() for k in a.headers)) for a in answers.values()}) == 1
    for a in answers.values():
        assert "exist" not in a.text.lower() and "already" not in a.text.lower() and "déjà" not in a.text.lower()
        assert "id" not in a.json() and "username" not in a.json()

    # nothing was created for, changed on, or sent to the existing accounts
    assert db.query(User).count() == 3
    for user in (verified, unverified):
        db.refresh(user)
        assert (user.hashed_password, user.username, user.email_verified, user.security_version) == before[user.id]
    deliveries = db.query(EmailDelivery).all()
    assert [d.event_key for d in deliveries] == ["AUTH.EMAIL_VERIFICATION"]
    assert deliveries[0].user_id == db.query(User).filter(User.email == "brand.new@example.com").one().id
    assert db.query(AuthToken).count() == 0 or all(t.user_id == deliveries[0].user_id for t in db.query(AuthToken))


def test_a_taken_username_cannot_be_used_to_probe_an_email(client, db, ip):
    existing = member(db, verified=True)
    for email in ("someone.new@example.com", existing.email):
        r = client.post(f"{A}/register", json=body(email=email, username=existing.username))
        assert r.status_code == 400 and "utilisateur" in r.json()["detail"]   # same answer for both addresses
    assert db.query(User).count() == 1


def test_a_registration_cannot_take_over_an_unverified_account(client, db, email_outbox, ip):
    """An existing account, even an unverified one, is never overwritten: the
    password stays the one its creator chose."""
    data = body()
    assert client.post(f"{A}/register", json=data).status_code == 201
    again = client.post(f"{A}/register", json=body(email=data["email"], password=PW2))
    assert again.status_code == 201
    assert login(client, data["email"], PW).status_code == 200
    assert login(client, data["email"], PW2).status_code == 401
    assert db.query(User).filter(User.email == data["email"]).count() == 1
    assert events(db) == ["AUTH.EMAIL_VERIFICATION"]                        # one email, from the first registration


def test_registration_race_on_the_unique_email_answers_the_same(client, db, ip, monkeypatch):
    """Two requests pass the existence check together; the database constraint
    decides. The loser gets the ordinary answer, not an 'exists' error."""
    from sqlalchemy.exc import IntegrityError

    import app.api.api_v1.endpoints.auth as auth_endpoints

    def lose_the_race(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception('duplicate key value violates unique constraint "ix_users_email"'))
    monkeypatch.setattr(auth_endpoints.crud_user, "create_with_sponsor", lose_the_race)
    data = body()
    r = client.post(f"{A}/register", json=data)
    assert r.status_code == 201 and r.json()["code"] == "REGISTRATION_ACCEPTED"


# ===========================================================================
# EMAIL VERIFICATION
# ===========================================================================

def _registered(client, db, email_outbox, **over):
    data = body(**over)
    assert client.post(f"{A}/register", json=data).status_code == 201
    user = db.query(User).filter(User.email == data["email"]).one()
    return user, link_token(email_outbox[-1], "verify-email")


def test_verification_succeeds_once_and_sends_one_welcome(client, db, email_outbox, ip):
    user, token = _registered(client, db, email_outbox)
    r = client.post(f"{A}/verify-email", json={"token": token})
    assert r.status_code == 200 and r.json()["code"] == "EMAIL_VERIFIED"
    assert user.email not in r.text                                         # nothing about the account comes back
    db.refresh(user)
    assert user.email_verified is True
    row = db.query(AuthToken).one()
    assert row.consumed_at is not None and row.revoked_at is None
    audit = audits(db, auth_security.AUDIT_EMAIL_VERIFIED)
    assert len(audit) == 1 and audit[0].user_id == user.id and audit[0].ip_address == "198.51.100.1"
    assert events(db) == ["AUTH.EMAIL_VERIFICATION", "AUTH.WELCOME"]
    welcome = email_outbox[-1]
    assert welcome["to"] == user.email and "#token=" not in welcome["html"] and "/dashboard" in welcome["html"]

    # replay: refused, and nothing happens a second time
    again = client.post(f"{A}/verify-email", json={"token": token})
    assert again.status_code == 400
    db.refresh(user)
    assert user.email_verified is True
    assert events(db).count("AUTH.WELCOME") == 1 and len(audits(db, auth_security.AUDIT_EMAIL_VERIFIED)) == 1


def test_welcome_is_never_repeated(client, db, email_outbox, ip):
    user, token = _registered(client, db, email_outbox)
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200
    assert login(client, user).status_code == 200                                    # login
    assert client.post(f"{A}/resend-verification", json={"email": user.email}).status_code == 200  # resend
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400              # replay
    # even a (hypothetical) second verification of the same account cannot produce a second welcome
    user.email_verified = False
    db.commit()
    second = issue(db, user, PURPOSE_EMAIL_VERIFICATION)
    assert client.post(f"{A}/verify-email", json={"token": second}).status_code == 200
    assert events(db).count("AUTH.WELCOME") == 1
    assert sum(1 for m in email_outbox if m["subject"].startswith("Welcome")) == 1


def test_expired_verification_link_is_refused(client, db, email_outbox, ip):
    user, token = _registered(client, db, email_outbox)
    row = db.query(AuthToken).one()
    lifetime = row.expires_at - row.created_at
    assert timedelta(minutes=59) < lifetime <= timedelta(minutes=60)        # short-lived (was 24 hours)
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400
    db.refresh(user)
    assert user.email_verified is False and events(db) == ["AUTH.EMAIL_VERIFICATION"]


@pytest.mark.parametrize("bad", ["x", "a" * 31, "a" * 43, "a" * 129, "a" * 512, "../../etc/passwd", "' OR 1=1 --",
                                 "<script>alert(1)</script>", "\x00" * 40, "é" * 40])
def test_malformed_verification_credentials_are_refused_the_same_way(client, db, email_outbox, ip, bad):
    user, _ = _registered(client, db, email_outbox)
    r = client.post(f"{A}/verify-email", json={"token": bad})
    assert r.status_code == 400 and r.json()["detail"] == "This link is invalid, has expired or has already been used."
    db.refresh(user)
    assert user.email_verified is False


@pytest.mark.parametrize("payload", [{}, {"token": ""}, {"token": None}, {"token": 12345}, {"token": ["a"]},
                                     {"token": "a" * 513}])
def test_verification_body_is_validated(client, db, ip, payload):
    assert client.post(f"{A}/verify-email", json=payload).status_code == 422


def test_all_refusals_look_identical(client, db, email_outbox, ip):
    """Unknown, expired, used, superseded, inactive account: one answer."""
    user, used = _registered(client, db, email_outbox)
    client.post(f"{A}/verify-email", json={"token": used})

    expired_user = member(db)
    expired = issue(db, expired_user, PURPOSE_EMAIL_VERIFICATION)
    db.query(AuthToken).filter(AuthToken.user_id == expired_user.id).update(
        {AuthToken.expires_at: datetime.utcnow() - timedelta(hours=1)})
    superseded_user = member(db)
    superseded = issue(db, superseded_user, PURPOSE_EMAIL_VERIFICATION)
    issue(db, superseded_user, PURPOSE_EMAIL_VERIFICATION)
    inactive_user = member(db)
    inactive = issue(db, inactive_user, PURPOSE_EMAIL_VERIFICATION)
    inactive_user.is_active = False
    db.commit()

    answers = [client.post(f"{A}/verify-email", json={"token": t})
               for t in (used, expired, superseded, inactive, "u" * 43)]
    assert {a.status_code for a in answers} == {400}
    assert len({a.text for a in answers}) == 1
    for u in (expired_user, superseded_user, inactive_user):
        db.refresh(u)
        assert u.email_verified is False


def test_a_credential_only_works_for_its_own_purpose(client, db, email_outbox, ip):
    user = member(db)
    reset = issue(db, user, PURPOSE_PASSWORD_RESET)
    verify = issue(db, user, PURPOSE_EMAIL_VERIFICATION)

    # a reset credential is not a verification credential ...
    assert client.post(f"{A}/verify-email", json={"token": reset}).status_code == 400
    # ... a verification credential is not a reset credential ...
    assert client.post(f"{A}/password-reset-confirm", json={"token": verify, "new_password": PW2}).status_code == 400
    db.refresh(user)
    assert user.email_verified is False and verify_password(PW, user.hashed_password)
    # ... neither is a session ...
    for token in (reset, verify):
        assert client.get("/api/v1/users/me", headers=bearer(token)).status_code == 401
    # ... and a session (or any other signed JWT) is not a credential for either
    access = login(client, user).json()["access_token"]
    kyc = create_kyc_document_view_token(user.id, 1, "front")
    forged = jwt.encode({"sub": user.email, "type": "email_verification", "iss": settings.JWT_ISSUER,
                         "aud": settings.JWT_AUDIENCE, "exp": datetime.utcnow() + timedelta(hours=1)},
                        settings.SECRET_KEY, algorithm=settings.ALGORITHM)   # the pre-EMAIL-2 link format
    for token in (access, kyc, forged):
        assert client.post(f"{A}/verify-email", json={"token": token}).status_code in (400, 422)
        assert client.post(f"{A}/password-reset-confirm",
                           json={"token": token, "new_password": PW2}).status_code in (400, 422)
    db.refresh(user)
    assert user.email_verified is False and verify_password(PW, user.hashed_password)

    # the wrong-purpose attempts did not burn the credentials: each still works where it belongs
    assert client.post(f"{A}/verify-email", json={"token": verify}).status_code == 200
    assert client.post(f"{A}/password-reset-confirm", json={"token": reset, "new_password": PW2}).status_code == 200


def test_a_credential_only_works_for_its_own_account(client, db, email_outbox, ip):
    alice, bob = member(db), member(db)
    token = issue(db, alice, PURPOSE_EMAIL_VERIFICATION)
    assert db.query(AuthToken).one().user_id == alice.id
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200
    db.refresh(alice)
    db.refresh(bob)
    assert alice.email_verified is True and bob.email_verified is False     # no account id for a caller to swap

    # Re-pointing a stored row at another account does not help: the row is also
    # bound to the address the credential was sent to.
    carol, dave = member(db), member(db)
    token = issue(db, carol, PURPOSE_EMAIL_VERIFICATION)
    db.query(AuthToken).filter(AuthToken.user_id == carol.id).update({AuthToken.user_id: dave.id})
    db.commit()
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400
    db.refresh(dave)
    assert dave.email_verified is False


def test_verification_link_dies_with_account_security_changes(client, db, email_outbox, ip):
    # the address changed since the link was sent
    user = member(db)
    token = issue(db, user, PURPOSE_EMAIL_VERIFICATION)
    user.email = f"moved_{uuid.uuid4().hex[:6]}@example.com"
    db.commit()
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400
    # the account was deactivated
    user = member(db)
    token = issue(db, user, PURPOSE_EMAIL_VERIFICATION)
    user.is_active = False
    db.commit()
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400
    # the address is already verified (by an earlier link)
    user = member(db, verified=True)
    token = issue(db, user, PURPOSE_EMAIL_VERIFICATION)
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 400
    assert events(db) == []                                                 # and no welcome for any of them


def test_consume_is_atomic(db):
    user = member(db)
    token = issue(db, user, PURPOSE_EMAIL_VERIFICATION)
    assert auth_tokens.consume(db, token, PURPOSE_EMAIL_VERIFICATION).id == user.id
    with pytest.raises(auth_tokens.AuthTokenError) as second:               # same transaction, before any commit
        auth_tokens.consume(db, token, PURPOSE_EMAIL_VERIFICATION)
    assert second.value.reason == "used"
    db.rollback()                                                           # the business change failed ...
    assert auth_tokens.consume(db, token, PURPOSE_EMAIL_VERIFICATION).id == user.id   # ... so the link is not lost


def test_the_credential_travels_in_the_fragment_and_is_stored_only_as_a_digest(client, db, email_outbox, ip):
    user, token = _registered(client, db, email_outbox)
    mail = email_outbox[0]
    assert f"/verify-email#token={token}" in mail["html"] and f"/verify-email#token={token}" in mail["text"]
    assert "?token=" not in mail["html"] and "?token=" not in mail["text"]  # never a query string
    assert token not in mail["subject"]
    assert len(token) >= 43                                                 # 256 random bits
    stored = everything_stored(db)
    assert token not in stored
    assert auth_tokens.hash_token(token) in stored                          # the digest, and only the digest
    assert user.email not in " ".join(str(getattr(db.query(AuthToken).one(), c.name))
                                      for c in AuthToken.__table__.columns)  # no address in the token row


def test_verification_is_never_performed_by_a_get_or_a_query_string(client, db, email_outbox, ip):
    user, token = _registered(client, db, email_outbox)
    for url in (f"{A}/verify-email?token={token}", f"/api/v1/share/u/verify-email?token={token}",
                f"{A}/verify-email"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].endswith("/verify-email")
        assert token not in r.headers["location"]
    assert client.post(f"{A}/verify-email?token={token}").status_code == 422   # the body is the only way in
    db.refresh(user)
    assert user.email_verified is False
    assert db.query(AuthToken).one().consumed_at is None                    # a scanner fetching links burns nothing
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200


def test_the_raw_credential_is_never_logged(client, db, email_outbox, ip, caplog):
    user, token = _registered(client, db, email_outbox)
    reset_user = member(db)
    client.post(f"{A}/password-reset-request", json={"email": reset_user.email})
    reset = link_token(email_outbox[-1], "reset-password")
    with caplog.at_level("DEBUG"):
        client.post(f"{A}/verify-email", json={"token": token})
        client.post(f"{A}/verify-email", json={"token": token})             # refusal path
        client.post(f"{A}/password-reset-confirm", json={"token": reset, "new_password": PW2})
        client.post(f"{A}/password-reset-confirm", json={"token": reset, "new_password": PW3})
        client.post(f"{A}/password-reset-confirm", json={"token": "z" * 43, "new_password": PW3})
    assert "refused" in caplog.text                                          # the refusals were logged ...
    for secret in (token, reset, "z" * 43, PW2, PW3):
        assert secret not in caplog.text                                     # ... without any secret


# ===========================================================================
# RESEND VERIFICATION
# ===========================================================================

def test_resend_sends_a_new_link_that_replaces_the_old_one(client, db, email_outbox, ip):
    user, first = _registered(client, db, email_outbox)
    r = client.post(f"{A}/resend-verification", json={"email": user.email})
    assert r.status_code == 200
    assert events(db) == ["AUTH.EMAIL_VERIFICATION", "AUTH.EMAIL_VERIFICATION"]
    second = link_token(email_outbox[-1], "verify-email")
    assert second != first
    assert client.post(f"{A}/verify-email", json={"token": first}).status_code == 400   # the earlier link is dead
    db.refresh(user)
    assert user.email_verified is False
    assert client.post(f"{A}/verify-email", json={"token": second}).status_code == 200
    db.refresh(user)
    assert user.email_verified is True
    # the resent email does not say "your account has been created"
    assert "has been created" in email_outbox[0]["html"] and "has been created" not in email_outbox[1]["html"]


def test_resend_answer_is_uniform_and_only_unverified_accounts_get_mail(client, db, email_outbox, ip):
    unverified, verified, inactive = member(db), member(db, verified=True), member(db, active=False)
    answers = [client.post(f"{A}/resend-verification", json={"email": e})
               for e in (unverified.email, verified.email, inactive.email, "nobody@example.com")]
    assert {a.status_code for a in answers} == {200} and len({a.text for a in answers}) == 1
    assert len({tuple(sorted(k.lower() for k in a.headers)) for a in answers}) == 1
    deliveries = db.query(EmailDelivery).all()
    assert [(d.event_key, d.user_id) for d in deliveries] == [("AUTH.EMAIL_VERIFICATION", unverified.id)]
    assert len(email_outbox) == 1 and email_outbox[0]["to"] == unverified.email


def test_resend_double_submit_sends_one_email(client, db, email_outbox, ip):
    user = member(db)
    for _ in range(2):
        assert client.post(f"{A}/resend-verification", json={"email": user.email}).status_code == 200
    assert events(db) == ["AUTH.EMAIL_VERIFICATION"]


def test_resend_cannot_bomb_a_mailbox(client, db, email_outbox, ip, monkeypatch):
    """Per-account limit: the same mailbox, whatever the number of client
    addresses and restarts. The answer stays the same when the limit is hit."""
    user = member(db)
    monkeypatch.setattr("app.api.api_v1.endpoints.auth._minute_bucket", lambda now=None: uuid.uuid4().int % 10**9)
    answers = []
    for i in range(12):
        ip(f"203.0.113.{i + 1}")                                            # a different address every time
        restart()
        answers.append(client.post(f"{A}/resend-verification", json={"email": user.email}))
    assert {a.status_code for a in answers} == {200} and len({a.text for a in answers}) == 1
    hourly = auth_throttle.VERIFY_ACCOUNT[0].limit
    assert db.query(EmailDelivery).count() == hourly == 3
    assert len(email_outbox) == 3


def test_resend_per_address_limit_is_durable_and_says_nothing_about_accounts(client, db, email_outbox, ip):
    known = member(db)
    codes = []
    for i in range(8):
        restart()                                                           # the in-memory limiter is gone each time
        email = known.email if i % 2 else f"guess{i}@example.com"
        codes.append(client.post(f"{A}/resend-verification", json={"email": email}).status_code)
    assert codes == [200] * 5 + [429] * 3                                   # the database remembered
    # only one row per address and window; unknown emails created none
    assert {r.scope for r in db.query(AuthRateLimit)} <= {"verify:ip", "verify:ip:day", "verify:account",
                                                          "verify:account:day", "verify:global"}
    assert db.query(AuthRateLimit).filter(AuthRateLimit.scope == "verify:account").count() == 1


# ===========================================================================
# PASSWORD RESET
# ===========================================================================

def test_reset_request_answer_is_uniform(client, db, email_outbox, ip):
    known, inactive = member(db), member(db, active=False)
    answers = [client.post(f"{A}/password-reset-request", json={"email": e})
               for e in (known.email, inactive.email, "nobody@example.com", known.email.upper())]
    assert {a.status_code for a in answers} == {200} and len({a.text for a in answers}) == 1
    assert len({tuple(sorted(k.lower() for k in a.headers)) for a in answers}) == 1
    assert [(d.event_key, d.user_id) for d in db.query(EmailDelivery)] == [("AUTH.PASSWORD_RESET", known.id)]


def test_unknown_addresses_cause_no_account_or_email_writes(client, db, email_outbox, ip):
    """Write amplification: a caller typing random emails creates one row per
    client address and window, nothing per email."""
    for i in range(4):
        client.post(f"{A}/password-reset-request", json={"email": f"random{i}@example.com"})
    assert db.query(EmailDelivery).count() == 0 and db.query(AuthToken).count() == 0
    rows = db.query(AuthRateLimit).all()
    assert sorted(r.scope for r in rows) == ["reset:ip", "reset:ip:day"] and {r.count for r in rows} == {4}
    assert "random" not in everything_stored(db) and "198.51.100.1" not in everything_stored(db)


def test_password_reset_end_to_end(client, db, email_outbox, ip):
    user = member(db, verified=True)
    old_session = login(client, user).json()["access_token"]
    assert client.get("/api/v1/users/me", headers=bearer(old_session)).status_code == 200

    assert client.post(f"{A}/password-reset-request", json={"email": user.email}).status_code == 200
    mail = email_outbox[-1]
    token = link_token(mail, "reset-password")
    assert "?token=" not in mail["html"] and token not in mail["subject"] and user.email not in token
    row = db.query(AuthToken).one()
    assert row.purpose == PURPOSE_PASSWORD_RESET
    assert timedelta(minutes=29) < row.expires_at - row.created_at <= timedelta(minutes=30)
    assert "30 minutes" in mail["html"]                                     # the email states the real lifetime

    ip("203.0.113.9")
    r = client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2})
    assert r.status_code == 200, r.text
    db.refresh(user)
    assert verify_password(PW2, user.hashed_password) and user.security_version == 1

    # every earlier session is over; the new password signs in
    assert client.get("/api/v1/users/me", headers=bearer(old_session)).status_code == 401
    assert login(client, user, PW).status_code == 401
    fresh = login(client, user, PW2)
    assert fresh.status_code == 200
    assert client.get("/api/v1/users/me", headers=bearer(fresh.json()["access_token"])).status_code == 200

    # replay
    assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW3}).status_code == 400
    db.refresh(user)
    assert verify_password(PW2, user.hashed_password) and user.security_version == 1

    # notice + audit, with no secret in either
    assert events(db) == ["AUTH.PASSWORD_RESET", "AUTH.PASSWORD_CHANGED"]
    notice = email_outbox[-1]
    assert notice["to"] == user.email and "203.0.113.9" in notice["html"]
    for secret in (PW, PW2, token, old_session, fresh.json()["access_token"]):
        assert secret not in notice["html"] and secret not in notice["text"] and secret not in notice["subject"]
    assert [a.ip_address for a in audits(db, auth_security.AUDIT_PASSWORD_RESET)] == ["203.0.113.9"]
    invalidated = audits(db, auth_security.AUDIT_SESSIONS_INVALIDATED)
    assert len(invalidated) == 1 and invalidated[0].new_values == {"reason": "AUTH_PASSWORD_RESET",
                                                                   "security_version": 1}
    stored = everything_stored(db)
    for secret in (PW, PW2, token, old_session, user.hashed_password):
        assert secret not in stored


def test_expired_reset_link_is_refused(client, db, email_outbox, ip):
    user = member(db)
    token = issue(db, user, PURPOSE_PASSWORD_RESET)
    db.query(AuthToken).update({AuthToken.expires_at: datetime.utcnow() - timedelta(seconds=1)})
    db.commit()
    assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2}).status_code == 400
    db.refresh(user)
    assert verify_password(PW, user.hashed_password) and user.security_version == 0


def test_a_weak_new_password_does_not_burn_the_link(client, db, ip):
    user = member(db)
    token = issue(db, user, PURPOSE_PASSWORD_RESET)
    r = client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": "weak"})
    assert r.status_code == 422 and "weak" not in r.text and token not in r.text
    assert db.query(AuthToken).one().consumed_at is None
    assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2}).status_code == 200


def test_a_newer_reset_link_replaces_the_older_one(client, db, email_outbox, ip, monkeypatch):
    monkeypatch.setattr("app.api.api_v1.endpoints.auth._minute_bucket", lambda now=None: uuid.uuid4().int % 10**9)
    user = member(db)
    client.post(f"{A}/password-reset-request", json={"email": user.email})
    first = link_token(email_outbox[-1], "reset-password")
    client.post(f"{A}/password-reset-request", json={"email": user.email})
    second = link_token(email_outbox[-1], "reset-password")
    assert first != second
    assert client.post(f"{A}/password-reset-confirm", json={"token": first, "new_password": PW2}).status_code == 400
    assert client.post(f"{A}/password-reset-confirm", json={"token": second, "new_password": PW2}).status_code == 200


def test_reset_link_dies_when_the_password_changes_another_way(client, db, email_outbox, ip):
    user = member(db)
    token = issue(db, user, PURPOSE_PASSWORD_RESET)
    session = login(client, user).json()["access_token"]
    assert client.post(f"{A}/change-password", headers=bearer(session),
                       json={"current_password": PW, "new_password": PW2}).status_code == 200
    row = db.query(AuthToken).one()
    assert row.revoked_at is not None                                       # revoked explicitly ...
    row.revoked_at = None
    db.commit()
    r = client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW3})
    assert r.status_code == 400                                             # ... and stale by security_version too
    db.refresh(user)
    assert verify_password(PW2, user.hashed_password)


def test_reset_for_an_account_that_became_inactive_is_refused_uniformly(client, db, ip):
    user = member(db)
    token = issue(db, user, PURPOSE_PASSWORD_RESET)
    user.is_active = False
    db.commit()
    inactive = client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2})
    unknown = client.post(f"{A}/password-reset-confirm", json={"token": "q" * 43, "new_password": PW2})
    assert inactive.status_code == unknown.status_code == 400 and inactive.text == unknown.text


# ---- rate limits ------------------------------------------------------------

def test_reset_limit_repeated_same_address(client, db, email_outbox, ip):
    user = member(db)
    codes = []
    for _ in range(8):
        restart()
        codes.append(client.post(f"{A}/password-reset-request", json={"email": user.email}).status_code)
    assert codes == [200] * 5 + [429] * 3                                   # durable: survives every restart
    blocked = client.post(f"{A}/password-reset-request", json={"email": "nobody@example.com"})
    assert blocked.status_code == 429                                       # and says nothing about the address typed


def test_reset_limit_repeated_same_account_from_many_addresses(client, db, email_outbox, ip, monkeypatch):
    monkeypatch.setattr("app.api.api_v1.endpoints.auth._minute_bucket", lambda now=None: uuid.uuid4().int % 10**9)
    user = member(db)
    answers = []
    for i in range(10):
        ip(f"203.0.113.{i + 1}")
        restart()
        answers.append(client.post(f"{A}/password-reset-request", json={"email": user.email}))
    assert {a.status_code for a in answers} == {200} and len({a.text for a in answers}) == 1   # still uniform
    assert db.query(EmailDelivery).count() == auth_throttle.RESET_ACCOUNT[0].limit == 3
    assert len(email_outbox) == 3


def test_reset_limit_many_accounts_from_one_address(client, db, email_outbox, ip):
    members = [member(db) for _ in range(8)]
    codes = []
    for m in members:
        restart()
        codes.append(client.post(f"{A}/password-reset-request", json={"email": m.email}).status_code)
    assert codes == [200] * 5 + [429] * 3
    assert db.query(EmailDelivery).count() == 5                             # one address reaches five mailboxes, no more


def test_reset_limit_window_expires(client, db, email_outbox, ip, monkeypatch):
    monkeypatch.setattr("app.api.api_v1.endpoints.auth._minute_bucket", lambda now=None: uuid.uuid4().int % 10**9)
    user = member(db)
    for _ in range(5):
        restart()
        client.post(f"{A}/password-reset-request", json={"email": user.email})
    restart()
    assert client.post(f"{A}/password-reset-request", json={"email": user.email}).status_code == 429
    assert db.query(EmailDelivery).count() == 3                             # account limit reached before the address limit

    # an hour later: the hourly windows are over, the daily ones are not
    for row in db.query(AuthRateLimit).all():
        row.window_start = row.window_start - timedelta(hours=1)
    for delivery in db.query(EmailDelivery).all():
        delivery.created_at = delivery.created_at - timedelta(hours=2)
    db.commit()
    restart()
    again = client.post(f"{A}/password-reset-request", json={"email": user.email})
    assert again.status_code == 200
    assert db.query(EmailDelivery).count() == 4                             # legitimate recovery works again


def test_reset_platform_wide_ceiling(client, db, email_outbox, ip, monkeypatch):
    monkeypatch.setattr(auth_throttle, "RESET_GLOBAL", (auth_throttle.Limit("reset:global", 2, 3600),))
    answers = []
    for i in range(4):
        ip(f"203.0.113.{i + 1}")
        answers.append(client.post(f"{A}/password-reset-request", json={"email": member(db).email}))
    assert {a.status_code for a in answers} == {200} and len({a.text for a in answers}) == 1
    assert db.query(EmailDelivery).count() == 2


def test_throttle_unit_behaviour(db):
    rule = (auth_throttle.Limit("unit:scope", 3, 3600),)
    t0 = datetime(2026, 10, 5, 12, 10)
    assert [auth_throttle.hit(db, rule, "k", now=t0) for _ in range(5)] == [True, True, True, False, False]
    row = db.query(AuthRateLimit).one()
    assert row.count == 3                                                   # at the limit nothing more is written
    assert row.window_start == datetime(2026, 10, 5, 12, 0)
    assert "k" not in row.key_hash and len(row.key_hash) == 64              # keyed hash, not the key
    assert auth_throttle.hit(db, rule, "other", now=t0) is True             # keys are independent
    assert auth_throttle.hit(db, rule, "k", now=t0 + timedelta(minutes=49)) is False   # same window
    assert auth_throttle.hit(db, rule, "k", now=t0 + timedelta(minutes=50)) is True    # next window
    # several rules: all must allow
    both = (auth_throttle.Limit("unit:a", 5, 3600), auth_throttle.Limit("unit:b", 1, 86400))
    assert [auth_throttle.hit(db, both, "z", now=t0) for _ in range(2)] == [True, False]


def test_throttle_fails_closed_when_the_store_is_unavailable(client, db, email_outbox, ip, monkeypatch):
    user = member(db)

    def broken(*args, **kwargs):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(auth_throttle, "_hit_one", broken)
    assert auth_throttle.hit(db, auth_throttle.RESET_IP, "x") is False
    assert client.post(f"{A}/password-reset-request", json={"email": user.email}).status_code == 429
    assert db.query(EmailDelivery).count() == 0


def test_expired_counter_rows_are_cleaned_up(db):
    old = datetime.utcnow() - timedelta(days=5)
    db.add(AuthRateLimit(scope="reset:ip", key_hash="h" * 64, window_start=old, count=1))
    db.commit()
    assert auth_throttle.hit(db, auth_throttle.RESET_GLOBAL, auth_throttle.GLOBAL_KEY) is True
    assert db.query(AuthRateLimit).filter(AuthRateLimit.window_start == old).count() == 0


# ===========================================================================
# PASSWORD CHANGE + SESSION INVALIDATION
# ===========================================================================

def test_password_change_ends_every_earlier_session_and_returns_a_new_one(client, db, email_outbox, ip):
    user = member(db, verified=True)
    phone = login(client, user).json()["access_token"]
    laptop = login(client, user).json()["access_token"]

    r = client.post(f"{A}/change-password", headers=bearer(laptop),
                    json={"current_password": PW, "new_password": PW2})
    assert r.status_code == 200, r.text
    new_session = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer" and new_session not in (phone, laptop)

    for stale in (phone, laptop):                                           # every earlier token, this device's too
        assert client.get("/api/v1/users/me", headers=bearer(stale)).status_code == 401
        assert client.post(f"{A}/validate-token", headers=bearer(stale)).status_code == 401
    assert client.get("/api/v1/users/me", headers=bearer(new_session)).status_code == 200
    assert client.post(f"{A}/validate-token", headers=bearer(new_session)).json()["user_id"] == user.id

    assert login(client, user, PW).status_code == 401
    assert login(client, user, PW2).status_code == 200

    db.refresh(user)
    assert user.security_version == 1
    assert events(db) == ["AUTH.PASSWORD_CHANGED"]
    notice = email_outbox[-1]
    for secret in (PW, PW2, phone, laptop, new_session):
        assert secret not in notice["html"] and secret not in notice["text"]
    assert len(audits(db, auth_security.AUDIT_PASSWORD_CHANGED)) == 1
    assert len(audits(db, auth_security.AUDIT_SESSIONS_INVALIDATED)) == 1
    for secret in (PW, PW2, phone, new_session):
        assert secret not in everything_stored(db)


def test_wrong_current_password_changes_nothing(client, db, email_outbox, ip):
    user = member(db)
    session = login(client, user).json()["access_token"]
    r = client.post(f"{A}/change-password", headers=bearer(session),
                    json={"current_password": "Wr0ng*Passw0rd!", "new_password": PW2})
    assert r.status_code == 400 and "access_token" not in r.text
    same = client.post(f"{A}/change-password", headers=bearer(session),
                       json={"current_password": PW, "new_password": PW})
    assert same.status_code == 400
    weak = client.post(f"{A}/change-password", headers=bearer(session),
                       json={"current_password": PW, "new_password": "abc123"})
    assert weak.status_code == 422                                          # the 12-character policy applies here too
    db.refresh(user)
    assert verify_password(PW, user.hashed_password) and user.security_version == 0
    assert client.get("/api/v1/users/me", headers=bearer(session)).status_code == 200   # the session is untouched
    assert events(db) == [] and audits(db, auth_security.AUDIT_PASSWORD_CHANGED) == []


def test_change_password_requires_a_current_session(client, db, ip):
    assert client.post(f"{A}/change-password",
                       json={"current_password": PW, "new_password": PW2}).status_code == 401


def test_tokens_issued_before_the_release_keep_working_until_the_password_changes(client, db, ip):
    """A token without the `sv` claim counts as version 0: the deployment
    signs nobody out. The first password change ends it like any other."""
    user = member(db)
    legacy = jwt.encode({"sub": str(user.id), "type": "access", "iss": settings.JWT_ISSUER,
                         "aud": settings.JWT_AUDIENCE, "exp": datetime.utcnow() + timedelta(days=1)},
                        settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert client.get("/api/v1/users/me", headers=bearer(legacy)).status_code == 200
    assert client.post(f"{A}/change-password", headers=bearer(legacy),
                       json={"current_password": PW, "new_password": PW2}).status_code == 200
    assert client.get("/api/v1/users/me", headers=bearer(legacy)).status_code == 401


def test_a_token_from_the_future_or_with_a_tampered_version_is_refused(client, db, ip):
    user = member(db)
    assert client.get("/api/v1/users/me",
                      headers=bearer(create_access_token(user.id, security_version=5))).status_code == 401
    garbage = jwt.encode({"sub": str(user.id), "type": "access", "sv": "x", "iss": settings.JWT_ISSUER,
                          "aud": settings.JWT_AUDIENCE, "exp": datetime.utcnow() + timedelta(days=1)},
                         settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert client.get("/api/v1/users/me", headers=bearer(garbage)).status_code == 401


def test_stale_token_is_anonymous_everywhere(client, db, ip):
    """The optional-auth dependency, the media requester identity and the
    Socket.IO handshake all apply the same rule."""
    from app.api.deps import get_current_active_user_optional
    from app.services import viewer_access

    user = member(db)
    stale = create_access_token(user.id, security_version=0)
    assert get_current_active_user_optional(db=db, token=stale).id == user.id
    assert auth_security.access_token_user_id(stale, db) == user.id
    auth_security.set_password(db, user, PW2, action=auth_security.AUDIT_PASSWORD_CHANGED)
    db.commit()
    current = create_access_token(user.id, security_version=user.security_version)

    assert get_current_active_user_optional(db=db, token=stale) is None
    assert get_current_active_user_optional(db=db, token=current).id == user.id
    assert auth_security.access_token_user_id(stale, db) is None
    assert auth_security.access_token_user_id(current, db) == user.id
    assert auth_security.access_token_user_id("not-a-token", db) is None
    assert auth_security.access_token_user_id(create_access_token(999999), db) is None   # no such account

    def media_request(token):
        return Request({"type": "http", "method": "GET", "path": "/", "query_string": b"",
                        "headers": [(b"authorization", f"Bearer {token}".encode())]})
    assert viewer_access.requester_user_id(media_request(stale)) is None
    assert viewer_access.requester_user_id(media_request(current)) == user.id


def test_session_invalidation_is_specific_to_access_tokens(client, db, email_outbox, ip):
    """A password change must not break credentials of another kind."""
    user = member(db)
    verification = issue(db, user, PURPOSE_EMAIL_VERIFICATION)
    kyc_view = create_kyc_document_view_token(user.id, 77, "front")
    session = login(client, user).json()["access_token"]
    assert client.post(f"{A}/change-password", headers=bearer(session),
                       json={"current_password": PW, "new_password": PW2}).status_code == 200

    assert verify_kyc_document_view_token(kyc_view, 77, "front") == user.id            # unrelated signed token
    assert db.query(AuthToken).filter(AuthToken.purpose == PURPOSE_EMAIL_VERIFICATION).one().revoked_at is None
    assert client.post(f"{A}/verify-email", json={"token": verification}).status_code == 200   # still verifies
    db.refresh(user)
    assert user.email_verified is True


def test_guardian_and_claim_tokens_are_separate_credentials():
    """They live in their own tables with their own hashing; nothing in
    EMAIL-2 reads or writes them."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "services"
    for name in ("auth_tokens.py", "auth_security.py", "auth_throttle.py"):
        source = (root / name).read_text(encoding="utf-8").lower()
        assert "pendingregistration" not in source and "guardian_token" not in source
        assert "claim_token" not in source and "user_verifications" not in source.replace("`user_verifications`", "")


def test_crud_reset_password_also_invalidates_sessions(db):
    from app.crud import user as crud_user

    user = member(db)
    crud_user.reset_password(db, user=user, new_password=PW2)
    db.refresh(user)
    assert user.security_version == 1 and verify_password(PW2, user.hashed_password)


# ===========================================================================
# CLIENT ADDRESS / PROXY
# ===========================================================================

def _req(peer, xff=None, extra=()):
    headers = list(extra)
    if xff is not None:
        headers.append(("x-forwarded-for", xff))
    return Request({"type": "http", "method": "POST", "path": "/", "query_string": b"",
                    "headers": [(k.encode(), v.encode()) for k, v in headers],
                    "client": (peer, 1234) if peer else None})


@pytest.mark.parametrize("peer, xff, expected", [
    # a direct connection is its socket address, whatever it claims
    ("198.51.100.20", "1.1.1.1", "198.51.100.20"),
    ("198.51.100.20", "127.0.0.1", "198.51.100.20"),
    # behind nginx: the right-most entry is the one nginx appended
    ("127.0.0.1", "203.0.113.50", "203.0.113.50"),
    ("127.0.0.1", "1.1.1.1, 203.0.113.50", "203.0.113.50"),               # forged left-most value ignored
    ("127.0.0.1", "1.1.1.1, 2.2.2.2, 3.3.3.3, 203.0.113.50", "203.0.113.50"),
    ("127.0.0.1", "127.0.0.1, 203.0.113.50", "203.0.113.50"),
    ("::1", "203.0.113.50", "203.0.113.50"),
    # only our proxies in the chain / nothing usable: the peer itself
    ("127.0.0.1", None, "127.0.0.1"),
    ("127.0.0.1", "", "127.0.0.1"),
    ("127.0.0.1", "127.0.0.1", "127.0.0.1"),
    ("127.0.0.1", "203.0.113.50, garbage", "127.0.0.1"),                   # garbage next to the proxy: stop
    ("127.0.0.1", "<script>, 203.0.113.50", "203.0.113.50"),
    # formats
    ("127.0.0.1", "203.0.113.50:51234", "203.0.113.50"),
    ("127.0.0.1", "2001:db8::7", "2001:db8::7"),
    ("127.0.0.1", "[2001:db8::7]:443", "2001:db8::7"),
    ("127.0.0.1", "::ffff:203.0.113.50", "203.0.113.50"),
])
def test_client_address_matrix(peer, xff, expected):
    assert client_ip(_req(peer, xff)) == expected
    assert rl._client_ip(_req(peer, xff)) == expected                       # the limiter uses the same function


def test_other_forwarding_headers_are_not_trusted():
    spoof = [("x-real-ip", "1.1.1.1"), ("forwarded", "for=1.1.1.1"), ("x-client-ip", "1.1.1.1"),
             ("cf-connecting-ip", "1.1.1.1"), ("true-client-ip", "1.1.1.1")]
    assert client_ip(_req("198.51.100.20", None, spoof)) == "198.51.100.20"
    assert client_ip(_req("127.0.0.1", "203.0.113.50", spoof)) == "203.0.113.50"
    assert client_ip(_req(None)) == "unknown"


def test_trusted_proxy_list_is_configurable(monkeypatch):
    # client -> CDN/LB (10.0.0.0/8) -> nginx (127.0.0.1) -> app
    chain = "1.1.1.1, 203.0.113.50, 10.1.2.3"
    assert client_ip(_req("127.0.0.1", chain)) == "10.1.2.3"                # default: only loopback is ours
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1, ::1, 10.0.0.0/8, not-an-address")
    assert client_ip(_req("127.0.0.1", chain)) == "203.0.113.50"
    assert client_ip(_req("10.9.9.9", chain)) == "203.0.113.50"
    assert client_ip(_req("198.51.100.20", chain)) == "198.51.100.20"
    assert client_ip_module.is_trusted_proxy("not-an-address") is False
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "")                             # trust nothing
    assert client_ip(_req("127.0.0.1", chain)) == "127.0.0.1"


def test_forged_forwarded_for_cannot_bypass_the_durable_limiter(app, db, email_outbox):
    """Production shape: the request reaches the app from nginx on loopback,
    with the real client appended to whatever the client sent."""
    import app.db.session as session_module
    from app.db.session import get_db
    from tests.conftest import TestingSessionLocal, engine

    user = member(db)
    app.dependency_overrides[get_db] = lambda: (yield db)
    original = (session_module.engine, session_module.SessionLocal)
    session_module.engine, session_module.SessionLocal = engine, TestingSessionLocal
    try:
        with TestClient(app, client=("127.0.0.1", 40000)) as nginx:
            codes = []
            for i in range(8):
                restart()
                codes.append(nginx.post(f"{A}/password-reset-request", json={"email": user.email},
                                        headers={"X-Forwarded-For": f"10.{i}.{i}.{i}, 203.0.113.77",
                                                 "X-Real-IP": f"10.{i}.{i}.{i}"}).status_code)
            assert codes == [200] * 5 + [429] * 3                           # one client, however it dresses up
            restart()
            other = nginx.post(f"{A}/password-reset-request", json={"email": "nobody@example.com"},
                               headers={"X-Forwarded-For": "203.0.113.77, 198.51.100.200"})
            assert other.status_code == 200                                 # a different real client has its own budget
    finally:
        app.dependency_overrides.pop(get_db, None)
        session_module.engine, session_module.SessionLocal = original
    assert db.query(AuthRateLimit).filter(AuthRateLimit.scope == "reset:ip").count() == 2


def test_login_log_and_security_notice_record_the_real_address(app, db, email_outbox):
    import app.db.session as session_module
    from app.db.session import get_db
    from tests.conftest import TestingSessionLocal, engine

    user = member(db)
    app.dependency_overrides[get_db] = lambda: (yield db)
    original = (session_module.engine, session_module.SessionLocal)
    session_module.engine, session_module.SessionLocal = engine, TestingSessionLocal
    try:
        with TestClient(app, client=("127.0.0.1", 40000)) as nginx:
            forged = {"X-Forwarded-For": "6.6.6.6, 203.0.113.88", "X-Real-IP": "6.6.6.6"}
            token = nginx.post(f"{A}/login", data={"username": user.email, "password": PW},
                               headers=forged).json()["access_token"]
            assert nginx.post(f"{A}/change-password", headers={**forged, **bearer(token)},
                              json={"current_password": PW, "new_password": PW2}).status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
        session_module.engine, session_module.SessionLocal = original
    assert [l.ip_address for l in db.query(LoginLog).all()] == ["203.0.113.88"]
    assert audits(db, auth_security.AUDIT_PASSWORD_CHANGED)[0].ip_address == "203.0.113.88"
    notice = email_outbox[-1]
    assert "203.0.113.88" in notice["html"] and "6.6.6.6" not in notice["html"]


# ===========================================================================
# EMAIL FAILURE: the account state stays correct
# ===========================================================================

def test_password_reset_survives_an_unavailable_provider(client, db, email_outbox, ip):
    user = member(db)
    token = issue(db, user, PURPOSE_PASSWORD_RESET)
    email_outbox.provider.script = [ProviderResult(False, retryable=True, error_category=FAIL_NETWORK)]
    assert client.post(f"{A}/password-reset-confirm", json={"token": token, "new_password": PW2}).status_code == 200
    assert len(email_outbox) == 0                                           # the notice could not be sent ...
    notice = db.query(EmailDelivery).one()
    assert (notice.event_key, notice.status) == ("AUTH.PASSWORD_CHANGED", "QUEUED")   # ... it will be retried
    db.refresh(user)
    assert verify_password(PW2, user.hashed_password) and user.security_version == 1   # the reset stands
    assert login(client, user, PW2).status_code == 200


def test_verification_survives_a_welcome_email_failure(client, db, email_outbox, ip):
    user, token = _registered(client, db, email_outbox)
    svc.get_settings_for_update(db).emergency_stop = True
    db.commit()
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200
    db.refresh(user)
    assert user.email_verified is True                                      # verified regardless
    welcome = db.query(EmailDelivery).filter(EmailDelivery.event_key == "AUTH.WELCOME").one()
    assert (welcome.status, welcome.failure_category) == ("SUPPRESSED", "emergency_stop")
    assert len(email_outbox) == 1                                           # only the verification email ever went out


def test_registration_survives_missing_encryption_and_resend_recovers(client, db, email_outbox, ip, monkeypatch):
    monkeypatch.delenv("EMAIL_SETTINGS_ENCRYPTION_KEY")
    monkeypatch.setattr(settings, "EMAIL_SETTINGS_ENCRYPTION_KEY", "")
    data = body()
    assert client.post(f"{A}/register", json=data).status_code == 201       # same answer
    user = db.query(User).filter(User.email == data["email"]).one()
    assert user.email_verified is False and user.is_active                  # a legitimate unverified account
    failed = db.query(EmailDelivery).one()
    assert (failed.status, failed.failure_category) == ("FAILED", "encryption_unconfigured")
    assert len(email_outbox) == 0 and db.query(AuthToken).count() == 0

    monkeypatch.setenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "synthetic-test-email-settings-encryption-key")
    assert client.post(f"{A}/resend-verification", json={"email": user.email}).status_code == 200
    token = link_token(email_outbox[-1], "verify-email")
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200


def test_registration_survives_an_email_service_crash(client, db, ip, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("email subsystem down")
    monkeypatch.setattr(email_service, "_enqueue", boom)
    data = body()
    assert client.post(f"{A}/register", json=data).status_code == 201
    user = db.query(User).filter(User.email == data["email"]).one()
    session = login(client, user).json()["access_token"]
    r = client.post(f"{A}/change-password", headers=bearer(session),
                    json={"current_password": PW, "new_password": PW2})
    assert r.status_code == 200                                             # the change is committed before the email
    db.refresh(user)
    assert verify_password(PW2, user.hashed_password) and user.security_version == 1
    assert db.query(EmailDelivery).count() == 0


def test_emergency_stop_and_event_switch_are_respected(client, db, email_outbox, ip):
    user = member(db)
    # the Admin switched the password reset email off
    svc.set_event_enabled(db, get_event(EmailEvent.AUTH_PASSWORD_RESET), False, actor_id=None)
    db.commit()
    off = client.post(f"{A}/password-reset-request", json={"email": user.email})
    row = db.query(EmailDelivery).one()
    assert (row.status, row.failure_category) == ("SUPPRESSED", "event_disabled")
    assert db.query(AuthToken).count() == 0                                 # no email, so no credential either

    db.query(EmailEventSetting).delete()
    svc.get_settings_for_update(db).emergency_stop = True
    db.commit()
    stopped = client.post(f"{A}/resend-verification", json={"email": user.email})
    assert db.query(EmailDelivery).order_by(EmailDelivery.id.desc()).first().failure_category == "emergency_stop"
    assert len(email_outbox) == 0 and db.query(AuthToken).count() == 0
    # the public answers do not change
    assert off.status_code == stopped.status_code == 200


def test_a_switch_turned_off_after_queueing_issues_no_credential(client, db, email_outbox, ip):
    user = member(db)
    client.post(f"{A}/password-reset-request", json={"email": user.email})
    svc.get_settings_for_update(db).emergency_stop = True                   # before the worker runs
    db.commit()
    assert len(email_outbox) == 0
    assert db.query(EmailDelivery).one().status == "SUPPRESSED" and db.query(AuthToken).count() == 0


def test_no_auth_code_talks_to_the_provider_directly():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app"
    for rel in ("api/api_v1/endpoints/auth.py", "services/auth_tokens.py", "services/auth_security.py",
                "services/auth_throttle.py", "services/email_verification.py"):
        source = (root / rel).read_text(encoding="utf-8")
        assert "import resend" not in source and "resend.Emails" not in source and "email_providers" not in source


# ===========================================================================
# RENDERING / TEMPLATES
# ===========================================================================

def test_verification_email_is_not_rendered_for_a_verified_or_changed_account(db):
    verified = member(db, verified=True)
    with pytest.raises(RenderError):
        render(db, event_key="AUTH.EMAIL_VERIFICATION", to=verified.email, user_id=verified.id, context={}, lang="en")
    other = member(db)
    for event in ("AUTH.EMAIL_VERIFICATION", "AUTH.PASSWORD_RESET", "AUTH.WELCOME"):
        with pytest.raises(RenderError):                                    # queued for an address that is no longer the account's
            render(db, event_key=event, to="old.address@example.com", user_id=other.id, context={}, lang="en")
    assert db.query(AuthToken).count() == 0


@pytest.mark.parametrize("lang", ["fr", "en", "es", "de"])
def test_auth_templates_in_every_language(db, lang):
    user = member(db)
    year = str(datetime.utcnow().year)
    subjects = {}
    for event, page in (("AUTH.EMAIL_VERIFICATION", "verify-email"), ("AUTH.PASSWORD_RESET", "reset-password"),
                        ("AUTH.WELCOME", None)):
        subject, html, text = render(db, event_key=event, to=user.email, user_id=user.id,
                                     context={"new_account": True}, lang=lang)
        subjects[event] = subject
        assert subject and "\n" not in subject and "token" not in subject.lower()
        assert text and text.strip() and "<" not in text.replace("<br>", "")   # a real plaintext alternative
        assert year in html and year in text                                # dynamic year
        assert "{minutes}" not in html and "{minutes}" not in text
        if page:
            token = re.search(rf"/{page}#token=([\w\-]+)", html).group(1)
            assert token in text and token not in subject
            assert re.search(rf'href="https?://[^"]+/{page}#token={token}"', html)   # safe absolute link
            assert ("60" if page == "verify-email" else "30") in html
        else:
            assert "#token=" not in html
        assert user.email not in html and user.email not in text            # no PII the email does not need
    assert len(set(subjects.values())) == 3
    english = render(db, event_key="AUTH.WELCOME", to=user.email, user_id=user.id, context={}, lang="en")[0]
    assert (subjects["AUTH.WELCOME"] == english) == (lang == "en")


def test_auth_templates_fall_back_to_english(db):
    user = member(db)
    english = render(db, event_key="AUTH.WELCOME", to=user.email, user_id=user.id, context={}, lang="en")
    for lang in ("sw", "zh", "", None, "pt_BR"):
        assert render(db, event_key="AUTH.WELCOME", to=user.email, user_id=user.id, context={}, lang=lang) == english


def test_auth_templates_escape_dynamic_values():
    hostile = 'https://myhigh5.com/verify-email#token=abc"><script>alert(1)</script>'
    for subject, html, text in (tpl.get_verify_email("en", hostile, 60), tpl.get_password_reset_email("en", hostile, 30),
                                tpl.get_welcome_email("en", hostile)):
        assert "<script>" not in html and 'abc">' not in html               # an unsafe URL is refused, not rendered
    _, html, _ = tpl.get_password_change_security_email("en", "https://myhigh5.com/contact",
                                                        '<img src=x onerror=alert(1)>', None)
    assert "<img src=x" not in html and "&lt;img" in html


def test_registry_keys_are_unchanged_and_welcome_is_live():
    from app.services.email_events import EMAIL_EVENTS

    auth_keys = sorted(k for k in EMAIL_EVENTS if k.startswith("AUTH."))
    assert auth_keys == ["AUTH.ACCOUNT_RESTORED", "AUTH.ACCOUNT_SUSPENDED", "AUTH.EMAIL_VERIFICATION",
                         "AUTH.PASSWORD_CHANGED", "AUTH.PASSWORD_RESET", "AUTH.WELCOME"]
    assert len(EMAIL_EVENTS) == 53
    live = {k for k in auth_keys if EMAIL_EVENTS[k].trigger_implemented}
    assert live == {"AUTH.EMAIL_VERIFICATION", "AUTH.WELCOME", "AUTH.PASSWORD_RESET", "AUTH.PASSWORD_CHANGED"}
    for key in ("AUTH.EMAIL_VERIFICATION", "AUTH.PASSWORD_RESET", "AUTH.PASSWORD_CHANGED"):
        assert EMAIL_EVENTS[key].critical                                   # still individually switchable, with a warning


# ===========================================================================
# LOGIN: no enumeration by timing, nothing identifying in logs
# ===========================================================================

def test_login_does_the_same_work_for_an_unknown_identifier(client, db, ip, monkeypatch, caplog):
    import app.crud.crud_user as crud_module

    user = member(db)
    checks = []
    real = crud_module.verify_password

    def counting(plain, hashed):
        checks.append(hashed)
        return real(plain, hashed)
    monkeypatch.setattr(crud_module, "verify_password", counting)

    with caplog.at_level("DEBUG"):
        unknown = login(client, "nobody.here@example.com", "Wr0ng*Passw0rd!")
        wrong = login(client, user, "Wr0ng*Passw0rd!")
    assert unknown.status_code == wrong.status_code == 401 and unknown.text == wrong.text
    assert len(checks) == 2                                                 # one bcrypt check on each path
    assert checks[0].startswith("$2") and checks[0] != user.hashed_password  # a real hash nobody knows
    assert "nobody.here@example.com" not in caplog.text and user.email not in caplog.text
    assert "Wr0ng*Passw0rd!" not in caplog.text
