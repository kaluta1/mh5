"""Administrator security hardening.

The `is_admin` flag alone used to be enough to make further accounts
administrators and to record payments by hand. What is tested here is that
each of those steps is closed:

  1. an account that has been switched off opens nothing, whatever token it
     holds, on ANY authenticated route (the administrator routes among them);
  2. making somebody an administrator needs an explicit permission, the
     acting administrator's password, and is never done on one's own account;
  3. recording a payment by hand needs the same, and a reason;
  4. the general role management API cannot hand out any of that;
  5. guessing passwords is bounded and every refused sign-in is kept.

Every account, password and amount is SYNTHETIC.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.routing import APIRoute
from jose import jwt

from app.api import deps
from app.api.api_v1.endpoints import admin as admin_endpoints
from app.api.api_v1.endpoints import auth as auth_endpoints
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission
from app.models.login_log import LoginLog
from app.models.payment import Deposit
from app.models.user import Permission, Role, User
from app.scripts import grant_payment_permissions as grants
from app.services import admin_security as sec
from app.services import auth_throttle
from app.services import payment_config as pc
from tests.unit.test_new_business_model import _assert_all_journals_balance, world  # noqa: F401

pytestmark = pytest.mark.unit

PASSWORD = "Synthetic-Admin-Passw0rd!"
PASSWORD_HASH = get_password_hash(PASSWORD)
REASON = "Bank transfer ref 2026-10-13/0042, callback never arrived"


def role_with(db, *names, name=None) -> Role:
    rows = [db.query(Permission).filter(Permission.name == n).first() or Permission(name=n, category="admin")
            for n in names]
    role = Role(name=name or ("r_" + "_".join(n[:6] for n in names))[:64], permissions=rows)
    db.add(role)
    db.flush()
    return role


def person(db, name, *, admin=False, active=True, permissions=(), version=0, role=None, **extra) -> User:
    if permissions:
        role = role_with(db, *permissions, name=f"role_{name}")
    row = User(email=f"{name}@example.com", username=name, hashed_password=PASSWORD_HASH, is_active=active,
               is_deleted=False, is_admin=admin, date_of_birth=datetime(1990, 1, 1), security_version=version,
               personal_referral_code=name.upper(), role_id=role.id if role else None,
               **{"email_verified": True, **extra})
    db.add(row)
    db.commit()
    return row


def bearer(user, *, version=None, minutes=5) -> dict:
    token = create_access_token(user.id, expires_delta=timedelta(minutes=minutes),
                                security_version=user.security_version if version is None else version)
    return {"Authorization": f"Bearer {token}"}


def code_of(response) -> str:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else str(detail)


def denials(db) -> list:
    db.expire_all()
    return [(r.user_id, r.record_id, r.new_values["attempted"], r.new_values["reason"])
            for r in db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_DENIED).order_by(AuditTrail.id).all()]


# ===========================================================================
# 1. An account that is switched off opens nothing
# ===========================================================================

ADMIN_READS = ("/api/v1/admin/users", "/api/v1/admin/statistics", "/api/v1/admin/finance/overview",
               "/api/v1/admin/finance/settings", "/api/v1/admin/cashouts", "/api/v1/admin/transactions")


def test_the_token_and_the_account_are_both_checked_on_the_administrator_routes(client, db):
    active = person(db, "boss", admin=True)
    disabled = person(db, "ghost", admin=True, active=False, version=1)      # switched off, version moved on
    member = person(db, "member")

    for path in ADMIN_READS:
        assert client.get(path, headers=bearer(active)).status_code == 200, path          # an active administrator
        assert client.get(path, headers=bearer(member)).status_code == 403, path          # an ordinary member
        assert client.get(path).status_code == 401, path                                 # nobody
        # The weakness: a disabled administrator with a token of the CURRENT version.
        assert client.get(path, headers=bearer(disabled)).status_code == 401, path
        # ... and with a token issued before the account's version moved on.
        assert client.get(path, headers=bearer(disabled, version=0)).status_code == 401, path
        assert client.get(path, headers=bearer(active, version=7)).status_code == 401, path   # a version never issued
        assert client.get(path, headers=bearer(active, minutes=-1)).status_code == 401, path  # expired
        assert client.get(path, headers={"Authorization": "Bearer not-a-token"}).status_code == 401, path
    # Signed with another key, otherwise identical.
    forged = jwt.encode({"exp": datetime.utcnow() + timedelta(minutes=5), "iat": datetime.utcnow(),
                         "sub": str(active.id), "type": "access", "iss": settings.JWT_ISSUER,
                         "aud": settings.JWT_AUDIENCE, "jti": "x", "sv": 0},
                        "another-key-entirely-0000000000000000", algorithm=settings.ALGORITHM)
    assert client.get(ADMIN_READS[0], headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    # A token for an account that does not exist.
    nobody = create_access_token(999999, expires_delta=timedelta(minutes=5))
    assert client.get(ADMIN_READS[0], headers={"Authorization": f"Bearer {nobody}"}).status_code == 401


def _dependency_names(dependant, seen=None) -> set:
    seen = set() if seen is None else seen
    for d in dependant.dependencies:
        seen.add(getattr(d.call, "__name__", type(d.call).__name__))
        _dependency_names(d, seen)
    return seen


def _api_routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route, _dependency_names(route.dependant)


def _path(route) -> str:
    out = route.path
    for name in route.param_convertors:
        out = out.replace("{" + name + "}", "1").replace("{" + name + ":path}", "1")
    return out


def test_no_authenticated_route_accepts_a_disabled_account_or_a_stale_token(client, db, app):
    """EVERY route that asks who is calling, not a list of them: a route added
    tomorrow is covered the day it is added."""
    from app.core.rate_limit import _buckets

    ghost = person(db, "ghost", admin=True, active=False, version=1, permissions=("all",))
    stale = person(db, "stale", admin=True, version=2)
    deleted = person(db, "deleted", admin=True, permissions=("all",))
    deleted.is_deleted = True                                      # deleted, and still marked active
    db.commit()
    current, old, removed = bearer(ghost), bearer(stale, version=1), bearer(deleted)
    checked = 0
    for route, names in _api_routes(app):
        if "get_current_user" not in names:
            continue                                               # public, or optional sign-in
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            _buckets.clear()                                       # the request limiter is not what is tested
            for label, headers in (("disabled account", current), ("stale token", old), ("deleted account", removed)):
                answer = client.request(method, _path(route), headers=headers)
                assert answer.status_code == 401, f"{label}: {method} {route.path} -> {answer.status_code}"
            checked += 1
    assert checked > 400                                           # the whole API, not a handful of routes


def test_every_administrator_route_refuses_an_ordinary_member_before_anything_else(client, db, app):
    from app.core.rate_limit import _buckets

    member = person(db, "member")
    headers = bearer(member)
    gate = {"require_admin", "get_current_admin_user", "PermissionChecker", "require_processor",
            "require_email_manager", "require_content_moderator"}
    # Authorized by a short-lived signed link instead of a bearer token (an <img> cannot send one).
    signed_link = {"/api/v1/kyc/admin/documents/{document_id}/{side}"}
    checked = 0
    for route, names in _api_routes(app):
        if "/admin" not in route.path and "/rbac/" not in route.path:
            continue
        if route.path in signed_link or route.path == "/api/v1/rbac/me/permissions":
            continue
        assert names & gate, f"{route.path} has no administrator check in its dependencies"
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            _buckets.clear()
            answer = client.request(method, _path(route), headers=headers)
            assert answer.status_code == 403, f"{method} {route.path} -> {answer.status_code}"
            checked += 1
    assert checked > 100


def test_an_inactive_administrator_is_not_an_administrator_even_past_the_token_check(db):
    """Defence in depth: the route file's own check does not rely on the token check."""
    ghost = person(db, "ghost", admin=True, active=False)
    with pytest.raises(Exception) as refused:
        admin_endpoints.check_admin(ghost)
    assert getattr(refused.value, "status_code", None) == 403
    assert admin_endpoints.check_admin(person(db, "boss", admin=True)).username == "boss"
    assert sec.is_administrator(ghost) is True and deps.get_current_user is not None


# ===========================================================================
# 2. Making somebody an administrator
# ===========================================================================

def role_url(user) -> str:
    return f"/api/v1/admin/users/{user.id}/role"


def test_being_an_administrator_is_not_enough_to_make_another_one(client, db):
    plain = person(db, "plain", admin=True)                                  # is_admin only, no permission
    wildcard = person(db, "wild", admin=True, permissions=("all",))          # 'all' implies nothing here either
    owner = person(db, "owner", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    member, target = person(db, "member"), person(db, "target")
    body = {"is_admin": True, "current_password": PASSWORD}

    assert client.put(role_url(target), json=body).status_code == 401
    assert client.put(role_url(target), headers=bearer(member), json=body).status_code == 403
    for actor in (plain, wildcard):
        refused = client.put(role_url(target), headers=bearer(actor), json=body)
        assert (refused.status_code, code_of(refused)) == (403, "PERMISSION_REQUIRED")
    # The request an older client sends: no password at all.
    old_client = client.put(role_url(target), headers=bearer(plain), json={"is_admin": True})
    assert (old_client.status_code, code_of(old_client)) == (403, "PERMISSION_REQUIRED")
    # With the permission: still the password, and never one's own account.
    for password in ("", "not-the-password"):
        refused = client.put(role_url(target), headers=bearer(owner), json={"is_admin": True, "current_password": password})
        assert (refused.status_code, code_of(refused)) == (403, "REAUTH_REQUIRED")
    own = client.put(role_url(owner), headers=bearer(owner), json={"is_admin": False, "current_password": PASSWORD})
    assert (own.status_code, code_of(own)) == (403, "SELF_ACTION_FORBIDDEN")
    promote_self = client.put(role_url(plain), headers=bearer(plain), json=body)
    assert promote_self.status_code == 403

    db.expire_all()
    assert db.get(User, target.id).is_admin is False and db.get(User, owner.id).is_admin is True
    assert db.query(AuditTrail).filter(AuditTrail.action == "ADMIN_ROLE_UPDATE").count() == 0
    # Every refusal is on record: who, on which account, what, why.
    assert denials(db) == [
        (plain.id, target.id, "grant administrator", "PERMISSION_REQUIRED"),
        (wildcard.id, target.id, "grant administrator", "PERMISSION_REQUIRED"),
        (plain.id, target.id, "grant administrator", "PERMISSION_REQUIRED"),
        (owner.id, target.id, "grant administrator", "REAUTH_REQUIRED"),
        (owner.id, target.id, "grant administrator", "REAUTH_REQUIRED"),
        (owner.id, owner.id, "remove administrator", "SELF_ACTION_FORBIDDEN"),
        (plain.id, plain.id, "grant administrator", "PERMISSION_REQUIRED"),
    ]

    granted = client.put(role_url(target), headers=bearer(owner), json=body)
    assert granted.status_code == 200 and granted.json()["is_admin"] is True
    db.expire_all()
    entry = db.query(AuditTrail).filter(AuditTrail.action == "ADMIN_ROLE_UPDATE").one()
    assert (entry.user_id, entry.record_id, entry.old_values, entry.new_values) == (
        owner.id, target.id, {"is_admin": False}, {"is_admin": True})
    assert PASSWORD not in str(entry.new_values) and entry.ip_address
    # The same request again changes nothing and writes nothing.
    assert client.put(role_url(target), headers=bearer(owner), json=body).status_code == 200
    assert db.query(AuditTrail).filter(AuditTrail.action == "ADMIN_ROLE_UPDATE").count() == 1


def test_only_an_account_that_can_sign_in_becomes_an_administrator_and_losing_the_role_ends_its_sessions(client, db):
    owner = person(db, "owner", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    body = {"is_admin": True, "current_password": PASSWORD}
    disabled = person(db, "disabled", active=False)
    unverified = person(db, "unverified", email_verified=False, email_verification_required=True)
    for target in (disabled, unverified):                                    # an unverified address
        refused = client.put(role_url(target), headers=bearer(owner), json=body)
        assert (refused.status_code, code_of(refused)) == (409, "TARGET_NOT_ELIGIBLE")
    assert client.put("/api/v1/admin/users/999999/role", headers=bearer(owner), json=body).status_code == 404

    other = person(db, "other", admin=True)
    session = bearer(other)
    assert client.get("/api/v1/admin/users", headers=session).status_code == 200
    removed = client.put(role_url(other), headers=bearer(owner), json={"is_admin": False, "current_password": PASSWORD})
    assert removed.status_code == 200 and removed.json()["is_admin"] is False
    db.expire_all()
    assert db.get(User, other.id).security_version == 1
    assert client.get("/api/v1/admin/users", headers=session).status_code == 401      # the old session is over
    assert client.get("/api/v1/admin/users", headers=bearer(db.get(User, other.id))).status_code == 403


def test_switching_an_administrator_account_on_or_off_is_a_privileged_action(client, db):
    plain = person(db, "plain", admin=True)
    owner = person(db, "owner", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    contained = person(db, "contained", admin=True, active=False, version=1)   # an administrator account that was switched off
    member = person(db, "member")

    def status(target, actor, active, password=None):
        body = {"is_active": active} if password is None else {"is_active": active, "current_password": password}
        return client.put(f"/api/v1/admin/users/{target.id}/status", headers=bearer(actor), json=body)

    # Anybody with is_admin could switch the contained account back on. No longer.
    refused = status(contained, plain, True)
    assert (refused.status_code, code_of(refused)) == (403, "PERMISSION_REQUIRED")
    assert (status(contained, owner, True).status_code, code_of(status(contained, owner, True))) == (403, "REAUTH_REQUIRED")
    assert code_of(status(owner, plain, False, PASSWORD)) == "PERMISSION_REQUIRED"     # nor switch an administrator off
    assert code_of(status(plain, plain, False)) == "SELF_ACTION_FORBIDDEN"             # nor oneself, either way
    db.expire_all()
    assert db.get(User, contained.id).is_active is False and db.get(User, owner.id).is_active is True

    assert status(contained, owner, True, PASSWORD).status_code == 200
    # An ordinary member is still moderated by any administrator, and switching off ends the sessions.
    session = bearer(member)
    assert client.get("/api/v1/users/me", headers=session).status_code == 200
    assert status(member, plain, False).status_code == 200
    db.expire_all()
    assert db.get(User, member.id).is_active is False and db.get(User, member.id).security_version == 1
    assert client.get("/api/v1/users/me", headers=session).status_code == 401
    assert status(member, plain, True).status_code == 200
    assert client.get("/api/v1/users/me", headers=session).status_code == 401          # back on is not signed back in

    # Deleting: never an administrator's account, never one's own.
    gone = client.delete(f"/api/v1/admin/users/{owner.id}", headers=bearer(plain))
    assert (gone.status_code, code_of(gone)) == (409, "ADMIN_ACCOUNT_PROTECTED")
    assert code_of(client.delete(f"/api/v1/admin/users/{plain.id}", headers=bearer(plain))) == "SELF_ACTION_FORBIDDEN"
    assert client.delete(f"/api/v1/admin/users/{member.id}", headers=bearer(plain)).status_code == 200


def test_nobody_verifies_an_identity_by_hand(client, db):
    # KYC is decided by the provider only: no administrator marks an identity verified
    # or unverified, their own or a member's.
    admin, member = person(db, "boss", admin=True), person(db, "member")
    member.identity_verified = True
    db.commit()
    for target in (admin, member):
        for action in ("verify", "unverify"):
            answer = client.put(f"/api/v1/admin/users/{target.id}/kyc/{action}", headers=bearer(admin))
            assert (answer.status_code, code_of(answer)) == (410, "KYC_DECIDED_BY_PROVIDER")
    assert client.put(f"/api/v1/admin/users/{member.id}/kyc/verify", headers=bearer(member)).status_code == 403
    db.expire_all()
    assert not db.get(User, admin.id).identity_verified and db.get(User, member.id).identity_verified is True


# ===========================================================================
# 3. Recording a payment by hand
# ===========================================================================

def grant(client, actor, target, **body):
    payload = {"product_code": "annual_membership", "notes": REASON, "current_password": PASSWORD, **body}
    return client.post(f"/api/v1/admin/users/{target.id}/grant-payment", headers=bearer(actor),
                       json={k: v for k, v in payload.items() if v is not None})


EVIDENCE = "TX-0xsynthetic-receipt-0001"


def confirm(client, actor, request_id, **body):
    payload = {"current_password": PASSWORD, "evidence_reference": EVIDENCE, **body}
    return client.post(f"/api/v1/admin/manual-payments/{request_id}/confirm", headers=bearer(actor),
                       json={k: v for k, v in payload.items() if v is not None})


def test_a_manual_payment_needs_its_own_permission_the_password_and_another_account(client, world):
    db = world
    plain = person(db, "plain", admin=True)
    wildcard = person(db, "wild", admin=True, permissions=("all",))
    finance = person(db, "finance", admin=True, permissions=(pc.PERMISSION_MANAGE, pc.PERMISSION_PROCESS,
                                                              pc.PERMISSION_ACTIVATE))
    cashier = person(db, "cashier", admin=True, permissions=(sec.PERMISSION_GRANT_PAYMENTS,))
    sponsor = person(db, "sponsor")
    member = person(db, "member", sponsor_id=sponsor.id)
    inactive = person(db, "inactive", active=False)

    def nothing_recorded():
        db.expire_all()
        return (db.query(Deposit).count(), db.query(JournalEntry).count(), db.query(AffiliateCommission).count()) == (0, 0, 0)

    assert client.post(f"/api/v1/admin/users/{member.id}/grant-payment", json={}).status_code == 401
    assert grant(client, member, member).status_code == 403                                  # a member
    for actor in (plain, wildcard, finance):                           # not is_admin, not 'all', not the payment settings
        refused = grant(client, actor, member)
        assert (refused.status_code, code_of(refused)) == (403, "PERMISSION_REQUIRED"), actor.username
    # An administrator paying themselves, and a request without a password.
    assert code_of(grant(client, plain, plain)) == "PERMISSION_REQUIRED"
    assert code_of(grant(client, cashier, cashier)) == "SELF_ACTION_FORBIDDEN"
    assert code_of(grant(client, cashier, member, verify_identity=True)) == "KYC_DECIDED_BY_PROVIDER"   # never by hand
    for password in (None, "", "not-the-password"):
        assert code_of(grant(client, cashier, member, current_password=password)) == "REAUTH_REQUIRED"
    # A payment has to say which payment it is.
    for notes in (None, "", "paid", "   x      y   "):
        missing = grant(client, cashier, member, notes=notes)
        assert (missing.status_code, code_of(missing)) == (400, "REASON_REQUIRED"), notes
    assert code_of(grant(client, cashier, inactive)) == "TARGET_NOT_ELIGIBLE"
    assert grant(client, cashier, member, amount="1.00").status_code == 400                 # not the product's price
    assert nothing_recorded()
    assert [d[3] for d in denials(db)].count("PERMISSION_REQUIRED") == 4
    assert {(d[0], d[3]) for d in denials(db)} >= {(cashier.id, "SELF_ACTION_FORBIDDEN"), (cashier.id, "REAUTH_REQUIRED")}

    # Step 1: recorded. Nothing is credited, posted or commissioned yet.
    done = grant(client, cashier, member)
    assert done.status_code == 200 and done.json()["status"] == "pending_confirmation", done.text
    request_id = done.json()["request_id"]
    db.expire_all()
    deposit = db.query(Deposit).one()
    assert (deposit.user_id, deposit.validated_by, str(deposit.status.value)) == (member.id, None, "pending")
    assert (db.query(JournalEntry).count(), db.query(AffiliateCommission).count()) == (0, 0)
    assert db.query(AuditTrail).filter(AuditTrail.action == "MANUAL_PAYMENT_REQUESTED").one().user_id == cashier.id
    # Step 2: never the same administrator; a second one confirms, citing the evidence.
    same = confirm(client, cashier, request_id)
    assert (same.status_code, code_of(same)) == (403, "SAME_ADMINISTRATOR")
    checker = person(db, "checker", admin=True, permissions=(sec.PERMISSION_GRANT_PAYMENTS,))
    assert code_of(confirm(client, checker, request_id, evidence_reference="x")) == "EVIDENCE_REQUIRED"
    assert code_of(confirm(client, finance, request_id)) == "PERMISSION_REQUIRED"
    ok = confirm(client, checker, request_id)
    assert ok.status_code == 200 and ok.json()["status"] == "granted", ok.text
    assert code_of(confirm(client, checker, request_id)) == "ALREADY_DECIDED"
    db.expire_all()
    deposit = db.query(Deposit).one()
    assert (deposit.user_id, deposit.validated_by, str(deposit.status.value)) == (member.id, checker.id, "validated")
    assert REASON in deposit.admin_notes and f"admin #{cashier.id}" in deposit.admin_notes and EVIDENCE in deposit.admin_notes
    entry = db.query(AuditTrail).filter(AuditTrail.action == "ADMIN_PAYMENT_GRANT").one()
    assert (entry.user_id, entry.record_id) == (checker.id, member.id)
    assert entry.new_values["reason"] == REASON and entry.new_values["deposit_id"] == deposit.id
    assert (entry.new_values["requested_by"], entry.new_values["confirmed_by"]) == (cashier.id, checker.id)
    assert PASSWORD not in str(entry.new_values) + str(deposit.admin_notes)
    # The ledger is the ordinary validation pipeline's, untouched by this change, and balances.
    _assert_all_journals_balance(db)
    assert db.query(JournalEntry).count() >= 1
    # Asked again: the existing credit is reported, nothing is recorded twice.
    again = grant(client, cashier, member)
    assert again.status_code == 200 and again.json()["status"] == "already_paid"
    assert db.query(Deposit).count() == 1


# ===========================================================================
# 4. The role management API cannot hand any of this out
# ===========================================================================

def test_the_role_management_api_cannot_grant_a_protected_permission_or_make_an_administrator(client, db):
    protected = {n: Permission(name=n, category="admin") for n in sorted(sec.PROTECTED_PERMISSIONS)}
    ordinary = Permission(name="moderate_comments", category="moderator")
    wildcard = Permission(name="all", category="admin")
    manage = [Permission(name=n, category="admin") for n in ("manage_roles", "manage_permissions", "manage_users")]
    admin_role = Role(name="admin", permissions=[wildcard])
    manager_role = Role(name="role_manager", permissions=manage)
    finance_role = Role(name="finance_manager_m", permissions=[protected[pc.PERMISSION_MANAGE]])
    db.add_all([*protected.values(), ordinary, wildcard, admin_role, manager_role, finance_role])
    db.flush()
    # Somebody who may manage roles in general, with every general right there is.
    root = person(db, "root", admin=True, role=admin_role)
    manager = person(db, "manager", role=manager_role)
    finance = person(db, "finance", admin=True, role=finance_role)
    member = person(db, "member")
    base = "/api/v1/rbac"

    for actor in (root, manager):
        h = bearer(actor)
        refusals = []
        for name, perm in protected.items():
            refusals += [
                client.post(f"{base}/roles/{actor.role_id}/permissions/{perm.id}", headers=h),          # to my own role
                client.put(f"{base}/roles/{actor.role_id}/permissions", headers=h, json={"permission_ids": [perm.id]}),
                client.post(f"{base}/roles", headers=h, json={"name": f"x_{name}"[:40], "permission_ids": [perm.id]}),
                client.put(f"{base}/permissions/{perm.id}", headers=h, json={"name": "renamed"}),
                client.delete(f"{base}/permissions/{perm.id}", headers=h),
            ]
        refusals += [
            client.put(f"{base}/permissions/{ordinary.id}", headers=h, json={"name": sec.PERMISSION_MANAGE_ADMINS}),
            # A role that carries a protected permission: not changed, not inherited from, not given, not taken.
            client.put(f"{base}/roles/{finance_role.id}", headers=h, json={"description": "mine now"}),
            client.delete(f"{base}/roles/{finance_role.id}", headers=h),
            client.post(f"{base}/roles", headers=h, json={"name": "heir", "inherit_from_id": finance_role.id}),
            client.post(f"{base}/roles/{finance_role.id}/permissions/{ordinary.id}", headers=h),
            client.delete(f"{base}/roles/{finance_role.id}/permissions/{protected[pc.PERMISSION_MANAGE].id}", headers=h),
            client.post(f"{base}/users/assign-role", headers=h, json={"user_id": actor.id, "role_id": finance_role.id}),
            client.post(f"{base}/users/assign-role", headers=h, json={"user_id": finance.id, "role_id": manager_role.id}),
            # No new administrator through here.
            client.post(f"{base}/users/assign-role", headers=h, json={"user_id": member.id, "role_id": admin_role.id}),
        ]
        assert [(r.status_code, code_of(r)) for r in refusals] == [(403, "PROTECTED_PERMISSION")] * len(refusals), \
            actor.username
    created = client.post(f"{base}/permissions", headers=bearer(root), json={"name": pc.PERMISSION_ACTIVATE})
    assert created.status_code in (400, 403)                      # exists, or protected: never created through here

    db.expire_all()
    for user in (root, manager, member):
        assert not any(sec.has_permission(db.get(User, user.id), n) for n in sec.PROTECTED_PERMISSIONS)
    assert sec.is_administrator(db.get(User, member.id)) is False
    assert pc.has_permission(db.get(User, finance.id), pc.PERMISSION_MANAGE)                # and nothing was taken away
    assert sorted(p.name for p in db.get(Role, finance_role.id).permissions) == [pc.PERMISSION_MANAGE]

    # Ordinary role management still works.
    h = bearer(root)
    made = client.post(f"{base}/roles", headers=h, json={"name": "comment_moderator", "permission_ids": [ordinary.id]})
    assert made.status_code == 201, made.text
    assert client.post(f"{base}/users/assign-role", headers=h,
                       json={"user_id": member.id, "role_id": made.json()["id"]}).status_code == 200
    assert client.post(f"{base}/permissions", headers=h, json={"name": "pin_posts"}).status_code == 201


def test_the_grant_tool_names_the_two_new_permissions_like_the_others(db):
    base = Role(name="user", is_system=True)
    db.add(base)
    db.add_all([Permission(name=name, category="admin") for name in grants.PERMISSIONS])
    db.flush()
    owner = person(db, "owner", admin=True, role=base)
    developer = person(db, "developer", admin=True, role=base)
    assert set(grants.PERMISSIONS) == sec.PROTECTED_PERMISSIONS
    with pytest.raises(grants.GrantError):
        grants.grant(db, owner.email, [], apply=True)              # still nothing by default
    assert grants.grant(db, owner.email, [sec.PERMISSION_MANAGE_ADMINS], apply=True) == (
        "granted", "finance_manager_r_user", True)
    assert grants.grant(db, owner.email, [sec.PERMISSION_GRANT_PAYMENTS, pc.PERMISSION_MANAGE], apply=True)[1] == \
        "finance_manager_mrg_user"
    db.expire_all()
    held = {n for n in grants.PERMISSIONS if sec.has_permission(db.get(User, owner.id), n)}
    assert held == {sec.PERMISSION_MANAGE_ADMINS, sec.PERMISSION_GRANT_PAYMENTS, pc.PERMISSION_MANAGE}
    assert not any(sec.has_permission(db.get(User, developer.id), n) for n in grants.PERMISSIONS)


# ===========================================================================
# 5. Signing in
# ===========================================================================

LOGIN = "/api/v1/auth/login"
ADDRESS = "203.0.113.9"


@pytest.fixture
def address(monkeypatch):
    """The client address the sign-in endpoint sees; a test can change it."""
    current = {"ip": ADDRESS}
    monkeypatch.setattr(auth_endpoints, "client_ip", lambda request: current["ip"])
    return current


@pytest.fixture
def fixed_address(address):
    return address


def sign_in(client, identifier, password=PASSWORD):
    from app.core.rate_limit import _buckets

    _buckets.clear()                                               # the in-memory first line is tested elsewhere
    return client.post(LOGIN, data={"username": identifier, "password": password})


def test_every_refused_sign_in_is_kept_and_none_says_whether_the_account_exists(client, db, fixed_address):
    user = person(db, "member")
    wrong = sign_in(client, user.email, "not-the-password")
    unknown = sign_in(client, "nobody@example.com", "not-the-password")
    by_name = sign_in(client, "member", "not-the-password")
    # The same answer, word for word, whether or not the account exists.
    assert wrong.status_code == unknown.status_code == by_name.status_code == 401
    assert wrong.json() == unknown.json() == by_name.json()
    assert "token" not in wrong.text

    db.expire_all()
    rows = db.query(LoginLog).order_by(LoginLog.id).all()
    assert [(r.user_id, r.is_successful, r.failure_reason) for r in rows] == [
        (user.id, False, "Incorrect password"), (user.id, False, "Incorrect password")]
    # An identifier that names nobody has no account to attach to: the audit trail, without the identifier.
    trail = db.query(AuditTrail).filter(AuditTrail.action == auth_endpoints.AUDIT_LOGIN_FAILED).all()
    assert [(t.table_name, t.user_id, t.new_values) for t in trail] == [("auth", None, {"reason": "Unknown identifier"})]
    assert "nobody@example.com" not in str([t.new_values for t in trail]) and "not-the-password" not in str(
        [(r.failure_reason, r.user_agent) for r in rows])

    ok = sign_in(client, user.email)
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"}).status_code == 200
    # A deactivated account with the RIGHT password is refused, and that is kept too.
    off = person(db, "off", active=False)
    assert sign_in(client, off.email).status_code == 403
    db.expire_all()
    assert db.query(LoginLog).filter(LoginLog.user_id == off.id).one().failure_reason == "Account deactivated"


def test_guessing_holds_back_the_address_that_guessed_not_the_account(client, db, address):
    """Knowing an administrator's email address is not enough to lock that administrator out."""
    victim, other = person(db, "victim"), person(db, "other")
    limit = auth_throttle.LOGIN_FAIL_ACCOUNT_ADDRESS[0].limit
    for _ in range(limit):
        assert sign_in(client, victim.email, "not-the-password").status_code == 401

    # The address that guessed: held back from THAT account, with the answer a wrong password gets.
    held = sign_in(client, victim.email)                           # the RIGHT password
    unknown = sign_in(client, "nobody@example.com", "x")
    assert held.status_code == 401 and held.json() == unknown.json()
    db.expire_all()
    reasons = [r.failure_reason for r in db.query(LoginLog).filter(LoginLog.user_id == victim.id).order_by(LoginLog.id)]
    assert reasons == ["Incorrect password"] * limit + ["Account temporarily locked"]
    # Other people behind the same address are not affected ...
    assert sign_in(client, other.email).status_code == 200
    # ... and neither is the account's owner, on any other connection.
    address["ip"] = "198.51.100.20"
    assert sign_in(client, victim.email).status_code == 200
    assert sign_in(client, victim.email, "typo").status_code == 401            # their own mistakes are their own
    assert sign_in(client, victim.email).status_code == 200
    # It ends by itself: the next window starts clean, nobody has to unlock anything.
    pair = f"{victim.id}:{ADDRESS}"
    assert auth_throttle.blocked(db, auth_throttle.LOGIN_FAIL_ACCOUNT_ADDRESS, pair) is True
    later = datetime.utcnow() + timedelta(seconds=auth_throttle.LOGIN_FAIL_ACCOUNT_ADDRESS[0].window + 1)
    assert auth_throttle.blocked(db, auth_throttle.LOGIN_FAIL_ACCOUNT_ADDRESS, pair, now=later) is False


def test_no_sign_in_limit_lasts_longer_than_minutes_and_the_account_breaker_needs_a_distributed_attack(client, db, address):
    rules = (auth_throttle.LOGIN_FAIL_ACCOUNT_ADDRESS + auth_throttle.LOGIN_FAIL_ACCOUNT + auth_throttle.LOGIN_FAIL_IP
             + auth_throttle.REAUTH_FAIL)
    assert all(rule.window <= 900 for rule in rules)               # no daily cap: nothing outlasts 15 minutes
    assert not any(rule.scope.endswith(":day") for rule in rules)
    breaker = auth_throttle.LOGIN_FAIL_ACCOUNT[0]
    # One address is held back after a handful of failures, so it can never trip the breaker alone.
    assert breaker.limit >= 10 * auth_throttle.LOGIN_FAIL_ACCOUNT_ADDRESS[0].limit

    victim = person(db, "victim")
    for i in range(breaker.limit - 1):                             # failures spread over many addresses
        assert auth_throttle.hit(db, auth_throttle.LOGIN_FAIL_ACCOUNT, victim.id) is True
    assert sign_in(client, victim.email).status_code == 200        # one short of it: the owner signs in
    assert auth_throttle.hit(db, auth_throttle.LOGIN_FAIL_ACCOUNT, victim.id) is True
    tripped = sign_in(client, victim.email)                        # a real distributed run: paused, and says nothing
    assert tripped.status_code == 401 and tripped.json()["detail"] == auth_endpoints.LOGIN_FAILED_MESSAGE
    later = datetime.utcnow() + timedelta(seconds=breaker.window + 1)
    assert auth_throttle.blocked(db, auth_throttle.LOGIN_FAIL_ACCOUNT, victim.id, now=later) is False


def test_members_sharing_one_address_are_not_stopped_by_each_others_mistakes(client, db, address):
    """A mobile carrier or an office: many members, one address."""
    members = [person(db, f"member{i}") for i in range(4)]
    per_account = auth_throttle.LOGIN_FAIL_ACCOUNT_ADDRESS[0].limit - 1
    for member in members:                                         # everybody mistypes, several times
        for _ in range(per_account):
            assert sign_in(client, member.email, "typo").status_code == 401
    assert per_account * len(members) < auth_throttle.LOGIN_FAIL_IP[0].limit
    for member in members:                                         # and everybody still gets in
        assert sign_in(client, member.email).status_code == 200
    assert auth_throttle.blocked(db, auth_throttle.LOGIN_FAIL_IP, ADDRESS) is False


def test_guessing_from_one_address_stops_that_address_and_a_correct_password_costs_nothing(client, db, address):
    user = person(db, "member")
    limit = auth_throttle.LOGIN_FAIL_IP[0].limit
    for _ in range(3):                                             # signing in correctly is never counted
        assert sign_in(client, user.email).status_code == 200
    assert auth_throttle.blocked(db, auth_throttle.LOGIN_FAIL_IP, ADDRESS) is False
    for i in range(limit):                                         # one password tried on many identifiers
        assert sign_in(client, f"nobody{i}@example.com", "guess").status_code == 401
    kept = db.query(AuditTrail).filter(AuditTrail.action == auth_endpoints.AUDIT_LOGIN_FAILED).count()
    assert kept == limit

    blocked = sign_in(client, user.email)                          # even the right password, from this address
    assert blocked.status_code == 429 and "access_token" not in blocked.text
    assert sign_in(client, "nobody@example.com", "guess").status_code == 429
    # Once blocked nothing more is written: an attacker cannot fill the tables.
    db.expire_all()
    assert db.query(AuditTrail).filter(AuditTrail.action == auth_endpoints.AUDIT_LOGIN_FAILED).count() == kept
    assert db.query(LoginLog).filter(LoginLog.is_successful.is_(False)).count() == 0
    # The member is not locked: from any other address they sign in at once ...
    address["ip"] = "198.51.100.20"
    assert sign_in(client, user.email).status_code == 200
    # ... and the blocked address recovers by itself when its window ends.
    later = datetime.utcnow() + timedelta(seconds=auth_throttle.LOGIN_FAIL_IP[0].window + 1)
    assert auth_throttle.blocked(db, auth_throttle.LOGIN_FAIL_IP, ADDRESS, now=later) is False


def test_a_forwarding_header_typed_by_the_client_does_not_choose_the_address(monkeypatch):
    """The limits are per address, so the address must be the one that connected."""
    from starlette.requests import Request as StarletteRequest

    from app.core.client_ip import client_ip as resolve

    def request(peer, forwarded=None, real_ip=None):
        headers = []
        if forwarded is not None:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        if real_ip is not None:
            headers.append((b"x-real-ip", real_ip.encode()))
        return StarletteRequest({"type": "http", "client": (peer, 1234), "headers": headers, "method": "GET",
                                 "path": "/", "query_string": b""})

    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    # Behind our proxy: the entry OUR proxy appended, never what the client wrote to its left.
    assert resolve(request("127.0.0.1", "203.0.113.9")) == "203.0.113.9"
    assert resolve(request("127.0.0.1", "10.9.9.9, 1.2.3.4, 203.0.113.9")) == "203.0.113.9"
    # A direct connection: the header is not read at all.
    assert resolve(request("198.51.100.7", "203.0.113.9")) == "198.51.100.7"
    assert resolve(request("198.51.100.7", real_ip="203.0.113.9")) == "198.51.100.7"
    # Garbage, or nothing, next to our proxy: nothing further left is believed.
    assert resolve(request("127.0.0.1", "203.0.113.9, not-an-address")) == "127.0.0.1"
    assert resolve(request("127.0.0.1")) == "127.0.0.1"
    assert resolve(request("127.0.0.1", real_ip="203.0.113.9")) == "127.0.0.1"
    # Only the proxies we name are ours.
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    assert resolve(request("127.0.0.1", "203.0.113.9")) == "127.0.0.1"
    assert resolve(request("10.1.2.3", "203.0.113.9, 10.4.5.6")) == "203.0.113.9"


def test_if_the_limit_store_cannot_be_read_sign_in_is_refused_not_unlimited(db, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(db, "query", broken)
    assert auth_throttle.blocked(db, auth_throttle.LOGIN_FAIL_IP, ADDRESS) is True


def test_the_existing_sign_in_and_password_change_still_work(client, db, fixed_address):
    user = person(db, "member")
    first = sign_in(client, "member").json()["access_token"]                # by username
    second = sign_in(client, user.email).json()["access_token"]             # by email
    h1, h2 = ({"Authorization": f"Bearer {t}"} for t in (first, second))
    assert client.get("/api/v1/users/me", headers=h1).status_code == client.get("/api/v1/users/me", headers=h2).status_code == 200
    changed = client.post("/api/v1/auth/change-password", headers=h1,
                          json={"current_password": PASSWORD, "new_password": "Another-Passw0rd!42"})
    assert changed.status_code == 200, changed.text
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/v1/users/me", headers=fresh).status_code == 200
    assert client.get("/api/v1/users/me", headers=h2).status_code == 401    # every earlier session is over
    assert sign_in(client, user.email).status_code == 401 and sign_in(client, user.email, "Another-Passw0rd!42").status_code == 200


# ===========================================================================
# 6. A deactivated account is nobody on EVERY path that reads a token
# ===========================================================================

def raw_token(user, *, version=None) -> str:
    return bearer(user, version=version)["Authorization"].split(" ", 1)[1]


def token_paths(client, db) -> dict:
    """Every place a bearer token is turned into an identity: name -> does it accept this token?"""
    import asyncio
    from types import SimpleNamespace

    from app.services import auth_security, viewer_access
    from app.services.social_socket import social_socket_service

    def media_request(token):
        return SimpleNamespace(headers={"authorization": f"Bearer {token}"}, cookies={})

    return {
        # 1. REST: the dependency every authenticated route resolves.
        "rest": lambda t: client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {t}"}).status_code == 200,
        # 2. /auth/validate-token.
        "validate-token": lambda t: client.post("/api/v1/auth/validate-token",
                                                headers={"Authorization": f"Bearer {t}"}).status_code == 200,
        # 3. The helper behind the Socket.IO handshake and the media middleware.
        "helper": lambda t: auth_security.access_token_user_id(t, db) is not None,
        # 4. Socket.IO handshake (opens its own session, as it does in production).
        "socket.io": lambda t: asyncio.run(social_socket_service._authenticate_user({"token": t})) is not None,
        # 5. Media requests carrying a bearer token.
        "media": lambda t: viewer_access.requester_user_id(media_request(t)) is not None,
        # 6. GraphQL context (optional sign-in) and its administrator gate.
        "graphql": lambda t: deps.get_current_active_user_optional(db=db, token=t) is not None,
    }


def test_every_token_entry_point_refuses_a_deactivated_account(client, db):
    from types import SimpleNamespace

    from app.graphql import schema as graphql_schema

    active = person(db, "boss", admin=True)
    ghost = person(db, "ghost", admin=True, active=False, version=1)
    good, off, stale = raw_token(active), raw_token(ghost), raw_token(ghost, version=0)
    paths = token_paths(client, db)
    for name, accepted in paths.items():
        assert accepted(good) is True, f"{name}: an active account must still work"
        assert accepted(off) is False, f"{name}: a deactivated account with a current-version token"
        assert accepted(stale) is False, f"{name}: a deactivated account with an old-version token"
        assert accepted("not-a-token") is False, name
    expired = create_access_token(active.id, expires_delta=timedelta(minutes=-1))
    assert not any(accepted(expired) for accepted in paths.values())           # expiry is still checked everywhere
    assert not any(accepted(raw_token(active, version=9)) for accepted in paths.values())   # and the version
    with pytest.raises(PermissionError):
        graphql_schema._require_graphql_admin(SimpleNamespace(context={"user": None}))
    with pytest.raises(PermissionError):
        graphql_schema._require_graphql_admin(SimpleNamespace(context={"user": ghost}))
    assert graphql_schema._require_graphql_admin(SimpleNamespace(context={"user": active})).id == active.id


def test_a_deleted_account_is_nobody_although_it_is_still_marked_active(client, db, fixed_address):
    """Deleting an account sets `is_deleted` and leaves `is_active` alone, so
    every check that read only `is_active` let a deleted account carry on."""
    from app.models.email import EmailDelivery

    admin = person(db, "boss", admin=True)
    kept = person(db, "kept")
    gone = person(db, "gone")
    gone_admin = person(db, "goneadmin", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    session = raw_token(gone)                                      # signed in before the deletion
    paths = token_paths(client, db)
    assert all(accepted(session) for accepted in paths.values())

    assert client.delete(f"/api/v1/admin/users/{gone.id}", headers=bearer(admin)).status_code == 200
    db.expire_all()
    row = db.get(User, gone.id)
    assert (row.is_deleted, row.is_active, row.security_version) == (True, True, 1)
    # The session it had, and one issued under the version it has now: neither is an identity anywhere.
    for name, accepted in paths.items():
        assert accepted(session) is False, f"{name}: the session from before the deletion"
        assert accepted(raw_token(row)) is False, f"{name}: a current-version token of a deleted account"
        assert accepted(raw_token(kept)) is True, f"{name}: another member is not affected"
    assert client.get("/api/v1/users/me", headers=bearer(row)).status_code == 401
    # It cannot sign in again with the right password, and that is kept ...
    assert sign_in(client, gone.email).status_code == 403
    assert sign_in(client, "gone").status_code == 403
    assert db.query(LoginLog).filter(LoginLog.user_id == gone.id, LoginLog.is_successful.is_(False)).count() == 2
    # ... nor get a link by email that would give it a new password.
    before = db.query(EmailDelivery).count()
    for path in ("/api/v1/auth/password-reset-request", "/api/v1/auth/resend-verification"):
        assert client.post(path, json={"email": gone.email}).status_code == 200      # the same answer as for anybody
    assert db.query(EmailDelivery).count() == before

    # A deleted administrator (marked in the database: the API refuses to delete one) is not an administrator.
    gone_admin.is_deleted = True
    db.commit()
    assert client.get("/api/v1/admin/users", headers=bearer(gone_admin)).status_code == 401
    refused = client.put(role_url(kept), headers=bearer(gone_admin), json={"is_admin": True, "current_password": PASSWORD})
    assert refused.status_code == 401
    with pytest.raises(Exception) as not_admin:
        admin_endpoints.check_admin(gone_admin)
    assert getattr(not_admin.value, "status_code", None) == 403
    with pytest.raises(sec.AdminSecurityError):
        sec.authorize(db, gone_admin, permission=sec.PERMISSION_MANAGE_ADMINS, password=PASSWORD, target_id=kept.id,
                      attempted="grant administrator")
    db.expire_all()
    assert db.get(User, kept.id).is_admin is False

    # Everybody else carries on exactly as before.
    assert sign_in(client, kept.email).status_code == 200
    assert client.get("/api/v1/users/me", headers=bearer(kept)).status_code == 200
    assert client.get("/api/v1/admin/users", headers=bearer(admin)).status_code == 200


# ===========================================================================
# 7. Nobody records a payment they would earn a commission from
# ===========================================================================

def test_the_upline_is_found_through_both_referral_records_and_survives_bad_data(db):
    from app.models.affiliate import AffiliateTree

    top = person(db, "top")
    mid = person(db, "mid", sponsor_id=top.id)
    leaf = person(db, "leaf", sponsor_id=mid.id)
    assert sec.upline_ids(db, leaf.id) == {mid.id, top.id}
    assert sec.upline_ids(db, top.id) == set()
    assert sec.earns_from_payment_by(db, top.id, leaf.id) is True              # indirectly
    assert sec.earns_from_payment_by(db, leaf.id, top.id) is False             # commissions go up, not down
    assert sec.earns_from_payment_by(db, leaf.id, leaf.id) is False            # (their own account is another rule)

    # The affiliate tree names a sponsor the users table does not.
    orphan, tree_sponsor = person(db, "orphan"), person(db, "treesponsor")
    db.add(AffiliateTree(user_id=orphan.id, sponsor_id=tree_sponsor.id, level=1))
    db.commit()
    assert sec.upline_ids(db, orphan.id) == {tree_sponsor.id}

    # A self-sponsor can no longer be stored (ck_users_sponsor_not_self).
    from sqlalchemy.exc import IntegrityError

    selfish = person(db, "selfish")
    selfish.sponsor_id = selfish.id
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # A historical cycle and a sponsor that does not exist: each ends, none raises.
    a, b = person(db, "cyca"), person(db, "cycb")
    a.sponsor_id, b.sponsor_id = b.id, a.id
    dangling = person(db, "dangling", sponsor_id=987654)
    db.commit()
    assert sec.upline_ids(db, a.id) == {a.id, b.id} and sec.earns_from_payment_by(db, b.id, a.id) is True
    assert sec.upline_ids(db, dangling.id) == {987654}
    assert sec.earns_from_payment_by(db, top.id, a.id) is False

    # A very long line is walked to a bound, not forever.
    previous = top
    for i in range(sec.UPLINE_MAX_DEPTH + 10):
        previous = person(db, f"deep{i}", sponsor_id=previous.id)
    assert len(sec.upline_ids(db, previous.id)) == sec.UPLINE_MAX_DEPTH


def test_an_administrator_cannot_record_a_payment_for_their_own_referral_line(client, world, monkeypatch):
    from app.models.affiliate import AffiliateTree

    db = world
    cashier = person(db, "cashier", admin=True, permissions=(sec.PERMISSION_GRANT_PAYMENTS,),
                     usdt_wallet_address="0x" + "2" * 40)
    direct = person(db, "direct", sponsor_id=cashier.id)                       # the administrator's own referral
    indirect = person(db, "indirect", sponsor_id=direct.id)
    by_tree = person(db, "bytree")
    db.add(AffiliateTree(user_id=by_tree.id, sponsor_id=cashier.id, level=1))
    other_sponsor = person(db, "othersponsor", usdt_wallet_address="0x" + "3" * 40)
    unrelated = person(db, "unrelated", sponsor_id=other_sponsor.id)
    db.commit()

    def recorded():
        db.expire_all()
        return db.query(Deposit).count(), db.query(JournalEntry).count(), db.query(AffiliateCommission).count()

    for member in (direct, indirect, by_tree):
        refused = grant(client, cashier, member)
        assert (refused.status_code, code_of(refused)) == (403, "COMMISSION_CONFLICT"), member.username
    assert recorded() == (0, 0, 0)
    assert [(d[0], d[1], d[3]) for d in denials(db)] == [
        (cashier.id, m.id, "COMMISSION_CONFLICT") for m in (direct, indirect, by_tree)]

    # The legitimate workflow: a member outside the administrator's line, recorded by one
    # administrator and confirmed by another; the member's own sponsor earns what a received payment earns.
    checker = person(db, "checker", admin=True, permissions=(sec.PERMISSION_GRANT_PAYMENTS,))
    done = grant(client, cashier, unrelated)
    assert done.status_code == 200 and done.json()["status"] == "pending_confirmation", done.text
    ok = confirm(client, checker, done.json()["request_id"])
    assert ok.status_code == 200 and ok.json()["status"] == "granted", ok.text
    db.expire_all()
    commission = db.query(AffiliateCommission).one()
    assert (commission.user_id, commission.source_user_id) == (other_sponsor.id, unrelated.id)
    _assert_all_journals_balance(db)
    after_legitimate = recorded()

    # Belt and braces: even if the referral records were wrong, the RESULT is checked. A payment whose
    # commission turns out to be the administrator's own is undone completely.
    monkeypatch.setattr(sec, "earns_from_payment_by", lambda *_a, **_k: False)
    pending = grant(client, cashier, direct)
    assert pending.status_code == 200 and pending.json()["status"] == "pending_confirmation"
    undone = confirm(client, checker, pending.json()["request_id"])
    assert (undone.status_code, code_of(undone)) == (403, "COMMISSION_CONFLICT")
    deposits, journals, commissions = recorded()
    assert (deposits, journals, commissions) == (after_legitimate[0] + 1, after_legitimate[1], after_legitimate[2])
    from app.models.financial_controls import ManualPaymentConfirmation
    assert db.get(ManualPaymentConfirmation, pending.json()["request_id"]).status == "REQUESTED"   # nothing decided
    assert db.query(AffiliateCommission).filter(AffiliateCommission.user_id == cashier.id).count() == 0
    _assert_all_journals_balance(db)


# ===========================================================================
# 8. The password check behind every privileged action
# ===========================================================================

def test_wrong_passwords_are_counted_per_account_and_nothing_secret_is_kept(db):
    from app.services import reauth

    actor, other = person(db, "boss", admin=True), person(db, "other", admin=True)
    limit = auth_throttle.REAUTH_FAIL[0].limit

    def outcome(who, password, **kwargs) -> str:
        try:
            reauth.verify(db, who, password, ip="203.0.113.9", **kwargs)
            return "ok"
        except reauth.ReauthError as exc:
            return exc.code

    assert outcome(actor, PASSWORD) == "ok"
    for missing in (None, ""):                                     # nothing was guessed: refused, not counted
        assert outcome(actor, missing) == reauth.REQUIRED
    assert db.query(AuditTrail).count() == 0
    for i in range(limit):
        assert outcome(actor, f"guess-number-{i}") == reauth.REQUIRED
    rows = db.query(AuditTrail).filter(AuditTrail.action == reauth.AUDIT_REAUTH_FAILED).all()
    assert [(r.user_id, r.record_id, r.new_values, r.ip_address) for r in rows] == [
        (actor.id, actor.id, {"reason": "incorrect password"}, "203.0.113.9")] * limit
    assert "guess-number" not in str([(r.old_values, r.new_values, r.user_agent) for r in rows])

    assert outcome(actor, PASSWORD) == reauth.LOCKED               # paused, with the right password too
    assert outcome(actor, "another-guess") == reauth.LOCKED
    assert db.query(AuditTrail).count() == limit                   # and nothing more is written while paused
    assert outcome(other, PASSWORD) == "ok"                        # nobody else is affected
    later = datetime.utcnow() + timedelta(seconds=auth_throttle.REAUTH_FAIL[0].window + 1)
    assert auth_throttle.blocked(db, auth_throttle.REAUTH_FAIL, actor.id, now=later) is False   # it ends by itself


def test_a_wrong_password_undoes_what_the_request_had_started(db):
    from app.services import reauth

    actor = person(db, "boss", admin=True)
    actor.full_name = "changed before the password was checked"
    with pytest.raises(reauth.ReauthError):
        reauth.verify(db, actor, "not-the-password")
    db.expire_all()
    assert db.get(User, actor.id).full_name is None


def test_the_password_cannot_be_guessed_through_one_endpoint_after_another(client, world, fixed_address):
    db = world
    owner = person(db, "owner", admin=True, permissions=(
        sec.PERMISSION_MANAGE_ADMINS, sec.PERMISSION_GRANT_PAYMENTS, pc.PERMISSION_MANAGE, pc.PERMISSION_ACTIVATE))
    target, member = person(db, "target"), person(db, "member")
    h = bearer(owner)
    wrong = "not-the-password"

    attempts = [
        lambda pw: client.put(role_url(target), headers=h, json={"is_admin": True, "current_password": pw}),
        lambda pw: client.post(f"/api/v1/admin/users/{member.id}/grant-payment", headers=h,
                               json={"product_code": "annual_membership", "notes": REASON, "current_password": pw}),
        lambda pw: client.put("/api/v1/admin/finance/settings", headers=h,
                              json={"changes": {"usd_min_usd": "150"}, "current_password": pw}),
        lambda pw: client.post("/api/v1/admin/finance/payouts/reactivate", headers=h,
                               json={"current_password": pw, "confirmation": pc.CONFIRM_REACTIVATION,
                                     "note": "Compared the payout with the provider statement."}),
        lambda pw: client.post("/api/v1/auth/change-password", headers=h,
                               json={"current_password": pw, "new_password": "Another-Passw0rd!42"}),
    ]
    limit = auth_throttle.REAUTH_FAIL[0].limit
    assert limit == len(attempts)
    for attempt in attempts:                                       # one guess at each door
        refused = attempt(wrong)
        assert refused.status_code in (400, 403), refused.text
    # The count is shared: every door is now closed, to the right password as well.
    for attempt in attempts:
        closed = attempt(PASSWORD)
        assert closed.status_code == 429, closed.text
    assert code_of(attempts[0](PASSWORD)) == "REAUTH_LOCKED" and code_of(attempts[2](PASSWORD)) == "REAUTH_LOCKED"

    db.expire_all()
    assert db.get(User, target.id).is_admin is False and db.query(Deposit).count() == 0
    assert pc.load(db).usd_min_usd != 150 and db.get(User, owner.id).security_version == 0
    # Signing in is a different thing and is not affected; neither is anybody else.
    assert sign_in(client, owner.email).status_code == 200
    assert client.get("/api/v1/admin/users", headers=h).status_code == 200     # still signed in, still an administrator
    second = person(db, "second", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    assert client.put(role_url(target), headers=bearer(second),
                      json={"is_admin": True, "current_password": PASSWORD}).status_code == 200
