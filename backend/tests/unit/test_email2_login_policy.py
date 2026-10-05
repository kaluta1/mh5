"""EMAIL-2 finalization: verify-before-login for NEW accounts, with accounts
that predate the rule grandfathered.

The policy is a stored fact on the account (users.email_verification_required),
set once by public registration. Nothing is inferred from dates, deployments,
tokens or the email log.

Everything is SYNTHETIC; emails go to the in-memory FakeEmailProvider.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.security import create_access_token
from app.models.auth_security import AuthToken
from app.models.email import EmailDelivery
from app.models.login_log import LoginLog
from app.models.user import User
from app.services import auth_security
from app.services.email_events import EMAIL_EVENTS
from tests.unit.test_email2_auth_security import (  # noqa: F401  (ip is a fixture)
    A, PW, PW2, bearer, body, events, ip, link_token, login, member,
)

ME = "/api/v1/users/me"


def new_account(client, db, email_outbox, **over) -> User:
    """An account created through public registration (the EMAIL-2 lifecycle)."""
    data = body(**over)
    assert client.post(f"{A}/register", json=data).status_code == 201
    return db.query(User).filter(User.email == data["email"]).one()


# ===========================================================================
# NEW ACCOUNT: register -> verify -> login
# ===========================================================================

def test_new_account_end_to_end(client, db, email_outbox, ip):
    user = new_account(client, db, email_outbox)
    assert (user.email_verified, user.email_verification_required) == (False, True)
    assert events(db) == ["AUTH.EMAIL_VERIFICATION"]
    first_link = link_token(email_outbox[-1], "verify-email")

    # correct password, unconfirmed address: refused, no token, nothing else revealed
    early = login(client, user)
    assert early.status_code == 403
    assert early.json()["code"] == "EMAIL_NOT_VERIFIED" and early.json()["detail"] == early.json()["message"]
    assert "access_token" not in early.text and str(user.id) not in early.text and user.email not in early.text
    log = db.query(LoginLog).one()
    assert (log.user_id, log.is_successful, log.failure_reason) == (user.id, False, "Email not verified")

    # the member can ask for another email; the answer is the usual uniform one
    resend = client.post(f"{A}/resend-verification", json={"email": user.email})
    unknown = client.post(f"{A}/resend-verification", json={"email": "nobody@example.com"})
    assert resend.status_code == unknown.status_code == 200 and resend.text == unknown.text
    assert events(db) == ["AUTH.EMAIL_VERIFICATION", "AUTH.EMAIL_VERIFICATION"]
    second_link = link_token(email_outbox[-1], "verify-email")
    assert login(client, user).status_code == 403                           # asking for an email verifies nothing

    # the newest link verifies; the superseded one does not
    assert client.post(f"{A}/verify-email", json={"token": first_link}).status_code == 400
    assert login(client, user).status_code == 403
    assert client.post(f"{A}/verify-email", json={"token": second_link}).status_code == 200
    assert events(db).count("AUTH.WELCOME") == 1

    ok = login(client, user)
    assert ok.status_code == 200
    profile = client.get(ME, headers=bearer(ok.json()["access_token"])).json()
    assert (profile["email_verified"], profile["email_verification_required"]) == (True, True)

    # nothing repeats the welcome
    login(client, user)
    client.post(f"{A}/resend-verification", json={"email": user.email})
    client.post(f"{A}/verify-email", json={"token": second_link})
    assert events(db).count("AUTH.WELCOME") == 1
    assert sum(1 for m in email_outbox if m["subject"].startswith("Welcome")) == 1


def test_a_wrong_password_never_reveals_the_verification_state(client, db, email_outbox, ip):
    """Only someone who already knows the password learns that verification
    is pending. A wrong password gets the same answer for every kind of
    account, and for no account at all."""
    pending = new_account(client, db, email_outbox)
    legacy = member(db, verified=False)
    verified = member(db, verified=True)
    answers = [login(client, target, "Wr0ng*Passw0rd!")
               for target in (pending, legacy, verified, "nobody.at.all@example.com")]
    assert {a.status_code for a in answers} == {401}
    assert len({a.text for a in answers}) == 1
    assert len({tuple(sorted(k.lower() for k in a.headers)) for a in answers}) == 1
    for a in answers:
        assert "verif" not in a.text.lower() and "EMAIL_NOT_VERIFIED" not in a.text
    # by username too
    assert login(client, pending.username, "Wr0ng*Passw0rd!").text == answers[0].text
    assert login(client, pending.username, PW).status_code == 403


def test_a_deactivated_account_is_reported_as_deactivated_first(client, db, email_outbox, ip):
    user = new_account(client, db, email_outbox)
    user.is_active = False
    db.commit()
    r = login(client, user)
    assert r.status_code == 403 and "deactivated" in r.json()["detail"] and "EMAIL_NOT_VERIFIED" not in r.text
    assert login(client, user, "Wr0ng*Passw0rd!").status_code == 401        # and only with the right password


def test_an_unverified_new_account_has_no_access_even_with_a_token(client, db, email_outbox, ip):
    """Login is the only issuer of tokens and refuses these accounts. Should a
    token exist anyway, it opens nothing."""
    from app.api.deps import get_current_active_user_optional

    user = new_account(client, db, email_outbox)
    token = create_access_token(user.id, security_version=user.security_version)
    r = client.get(ME, headers=bearer(token))
    assert r.status_code == 403 and "confirm your email" in r.json()["detail"]
    assert client.post(f"{A}/change-password", headers=bearer(token),
                       json={"current_password": PW, "new_password": PW2}).status_code == 403
    assert get_current_active_user_optional(db=db, token=token) is None
    user.email_verified = True
    db.commit()
    assert client.get(ME, headers=bearer(token)).status_code == 200


def test_password_reset_does_not_bypass_verification(client, db, email_outbox, ip):
    user = new_account(client, db, email_outbox)
    client.post(f"{A}/password-reset-request", json={"email": user.email})
    reset = link_token(email_outbox[-1], "reset-password")
    assert client.post(f"{A}/password-reset-confirm", json={"token": reset, "new_password": PW2}).status_code == 200
    db.refresh(user)
    assert user.email_verified is False                                     # a reset is not a verification
    assert login(client, user, PW2).status_code == 403
    assert login(client, user, PW).status_code == 401


# ===========================================================================
# LEGACY UNVERIFIED ACCOUNT (predates the rule): grandfathered
# ===========================================================================

def test_legacy_unverified_account_keeps_signing_in(client, db, email_outbox, ip):
    user = member(db, verified=False)                                       # as the migration leaves existing rows
    assert user.email_verification_required is False

    r = login(client, user)
    assert r.status_code == 200
    session = r.json()["access_token"]
    profile = client.get(ME, headers=bearer(session)).json()
    # enough state for the account pages to offer "Verify your email"
    assert (profile["email_verified"], profile["email_verification_required"]) == (False, False)
    assert client.get(f"{A}/me", headers=bearer(session)).json()["email_verified"] is False

    db.refresh(user)
    assert user.email_verified is False                                     # not silently verified by signing in
    assert db.query(EmailDelivery).count() == 0 and db.query(AuthToken).count() == 0   # no welcome, no email at all


def test_legacy_unverified_account_can_verify_and_gets_one_welcome(client, db, email_outbox, ip):
    user = member(db, verified=False)
    session = login(client, user).json()["access_token"]

    assert client.post(f"{A}/resend-verification", json={"email": user.email}).status_code == 200
    token = link_token(email_outbox[-1], "verify-email")
    assert client.post(f"{A}/verify-email", json={"token": token}).status_code == 200
    db.refresh(user)
    assert (user.email_verified, user.email_verification_required) == (True, False)
    assert events(db) == ["AUTH.EMAIL_VERIFICATION", "AUTH.WELCOME"]

    # verifying does not end the session the member was using, and changes no session version
    assert user.security_version == 0
    assert client.get(ME, headers=bearer(session)).json()["email_verified"] is True
    assert login(client, user).status_code == 200
    assert events(db).count("AUTH.WELCOME") == 1


def test_existing_verified_account_login_is_unchanged(client, db, email_outbox, ip):
    user = member(db, verified=True)
    r = login(client, user)
    assert r.status_code == 200 and set(r.json()) == {"access_token", "token_type"}
    assert client.get(ME, headers=bearer(r.json()["access_token"])).status_code == 200
    assert db.query(EmailDelivery).count() == 0


def test_the_policy_is_a_stored_fact_not_a_runtime_guess(db):
    assert auth_security.must_verify_email(None) is False
    for required, verified, expected in ((False, False, False), (False, True, False),
                                         (True, True, False), (True, False, True)):
        user = member(db, verified=verified, email_verification_required=required)
        assert auth_security.must_verify_email(user) is expected
    # every way of creating an account other than public registration leaves the marker off
    assert User.__table__.c.email_verification_required.default.arg is False
    assert str(User.__table__.c.email_verification_required.server_default.arg) == "false"
    source = (Path(__file__).resolve().parents[2] / "app" / "services" / "auth_security.py").read_text(encoding="utf-8")
    policy = source[source.index("def must_verify_email"):]
    for forbidden in ("datetime", "created_at", "utcnow", "settings.", "os.getenv", "EmailDelivery", "AuthToken"):
        assert forbidden not in policy


def test_guardian_approved_registration_is_not_gated_by_this_task(db):
    """A guardian-approved account is finished from a single-use link sent to
    the minor's own address. That flow is unchanged here: it does not set the
    marker (create_with_sponsor's default)."""
    import inspect

    from app.crud.crud_user import CRUDUser
    from app.services import guardian_consent

    assert inspect.signature(CRUDUser.create_with_sponsor).parameters["require_email_verification"].default is False
    assert "require_email_verification" not in inspect.getsource(guardian_consent.complete_registration)


# ===========================================================================
# security_version is untouched by the policy
# ===========================================================================

def test_legacy_compatibility_does_not_bypass_security_version(client, db, email_outbox, ip):
    user = member(db, verified=False)
    old = login(client, user).json()["access_token"]
    r = client.post(f"{A}/change-password", headers=bearer(old), json={"current_password": PW, "new_password": PW2})
    assert r.status_code == 200
    assert client.get(ME, headers=bearer(old)).status_code == 401           # grandfathered, not exempt
    assert client.get(ME, headers=bearer(r.json()["access_token"])).status_code == 200

    # and a reset ends the sessions of a legacy account like any other
    current = login(client, user, PW2).json()["access_token"]
    client.post(f"{A}/password-reset-request", json={"email": user.email})
    reset = link_token(email_outbox[-1], "reset-password")
    assert client.post(f"{A}/password-reset-confirm", json={"token": reset, "new_password": PW}).status_code == 200
    assert client.get(ME, headers=bearer(current)).status_code == 401
    assert login(client, user, PW).status_code == 200


def test_verified_new_account_password_change_still_invalidates(client, db, email_outbox, ip):
    user = new_account(client, db, email_outbox)
    client.post(f"{A}/verify-email", json={"token": link_token(email_outbox[-1], "verify-email")})
    old = login(client, user).json()["access_token"]
    r = client.post(f"{A}/change-password", headers=bearer(old), json={"current_password": PW, "new_password": PW2})
    assert r.status_code == 200
    assert client.get(ME, headers=bearer(old)).status_code == 401
    assert login(client, user, PW2).status_code == 200


# ===========================================================================
# REGISTRATION against an existing address: unchanged, nothing sent
# ===========================================================================

def test_registration_for_an_existing_address_sends_nothing_and_changes_nothing(client, db, email_outbox, ip):
    verified, legacy = member(db, verified=True), member(db, verified=False)
    pending = new_account(client, db, email_outbox)
    assert len(email_outbox) == 1                                           # pending's own verification email
    snapshot = {u.id: (u.hashed_password, u.email_verified, u.email_verification_required, u.security_version)
                for u in (verified, legacy, pending)}

    answers = [client.post(f"{A}/register", json=body(email=e))
               for e in ("someone.new@example.com", verified.email, legacy.email, pending.email)]
    assert {a.status_code for a in answers} == {201}
    assert len({(a.json()["message"], a.json()["code"], tuple(sorted(a.json()))) for a in answers}) == 1

    for u in (verified, legacy, pending):
        db.refresh(u)
        assert (u.hashed_password, u.email_verified, u.email_verification_required, u.security_version) == snapshot[u.id]
    sent_to = [m["to"] for m in email_outbox]
    assert sent_to == [pending.email, "someone.new@example.com"]            # no "account exists" email, no automatic resend
    assert set(events(db)) == {"AUTH.EMAIL_VERIFICATION"}


# ===========================================================================
# OLD LINKS
# ===========================================================================

def test_links_from_before_email2_are_dead_and_harmless(client, db, email_outbox, ip):
    from datetime import datetime, timedelta

    from jose import jwt

    from app.core.config import settings

    user = member(db, verified=False)

    def legacy(kind):
        return jwt.encode({"sub": user.email, "type": kind, "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE,
                           "exp": datetime.utcnow() + timedelta(hours=1), "pwdv": "x"},
                          settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    old_verify, old_reset = legacy("email_verification"), legacy("password_reset")

    # the old GET links: a plain redirect to the page that offers a new link; the token goes nowhere
    for url in (f"{A}/verify-email?token={old_verify}", f"/api/v1/share/u/verify-email?token={old_verify}"):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].endswith("/verify-email")
        assert old_verify not in r.headers["location"] and "token" not in r.headers["location"]
    # the old tokens are not accepted anywhere, in any position
    assert client.post(f"{A}/verify-email", json={"token": old_verify}).status_code in (400, 422)
    assert client.post(f"{A}/verify-email?token={old_verify}").status_code == 422
    assert client.post(f"{A}/password-reset-confirm",
                       json={"token": old_reset, "new_password": PW2}).status_code in (400, 422)
    db.refresh(user)
    assert user.email_verified is False and user.security_version == 0
    assert login(client, user, PW).status_code == 200 and login(client, user, PW2).status_code == 401
    assert db.query(EmailDelivery).count() == 0


# ===========================================================================
# EMAIL-1 foundation is unchanged
# ===========================================================================

def test_email1_registry_is_unchanged():
    assert len(EMAIL_EVENTS) == 53
    assert EMAIL_EVENTS["AUTH.EMAIL_VERIFICATION"].trigger_implemented
    assert EMAIL_EVENTS["AUTH.WELCOME"].trigger_implemented
    for key in ("AUTH.ACCOUNT_SUSPENDED", "AUTH.ACCOUNT_RESTORED"):         # deliberately not wired in this task
        assert not EMAIL_EVENTS[key].trigger_implemented and not EMAIL_EVENTS[key].default_enabled
    assert not any("EXISTS" in key for key in EMAIL_EVENTS)                 # no "account already exists" email


def test_migration_grandfathers_existing_accounts_and_fabricates_nothing():
    source = (Path(__file__).resolve().parents[2] / "migrations" / "versions"
              / "d1e2f3a4b5c6_auth_security_email2.py").read_text(encoding="utf-8")
    upgrade = source[source.index("def upgrade"):source.index("def downgrade")]
    assert "email_verification_required BOOLEAN NOT NULL" in upgrade and "DEFAULT false" in upgrade
    statements = upgrade.upper()
    for data_change in ("UPDATE USERS", "INSERT INTO", "DELETE FROM", 'EXECUTE("UPDATE', "SET EMAIL_VERIFIED"):
        assert data_change not in statements
    assert "EMAIL_VERIFIED " not in statements and "USER_VERIFICATIONS" not in statements
    assert 'down_revision = "c0d1e2f3a4b5"' in source


@pytest.mark.parametrize("password, accepted", [
    ("Sh0rt*Pw!", False), ("Elev3n*Chars", True), ("Elev3n*Char", False), ("Tw3lve*Chars", True),
])
def test_backend_minimum_password_length_is_twelve(password, accepted):
    """The value the frontend hints must agree with (frontend/lib/password-policy.ts)."""
    from app.core.security_validators import validate_password_strength

    assert len("Tw3lve*Chars") == 12 and len("Elev3n*Char") == 11
    if accepted:
        assert validate_password_strength(password) == password
    else:
        with pytest.raises(ValueError):
            validate_password_strength(password)
