"""The Super Admin role.

  1. a Super Admin holds every administrative permission, the protected ones
     included, and only while the account is an active administrator on the
     system role;
  2. only a Super Admin grants or revokes the role, with the current
     password, never on their own account, never removing the last one, and
     every step (refusals too) is audited;
  3. no other path (administrator flag, account switch, deletion, role
     management API, grant tools) can make or unmake a Super Admin;
  4. the safeguards that do not depend on a permission still hold for a
     Super Admin (password, own account, own referral line);
  5. the first Super Admins are named once, by the bootstrap tool.

Every account and password is SYNTHETIC.
"""
from __future__ import annotations

import pytest

from app.api import deps
from app.models.accounting import AuditTrail
from app.models.user import Permission, Role, User
from app.scripts import bootstrap_super_admins as bootstrap
from app.scripts import grant_email_settings_permission as email_grants
from app.scripts import grant_payment_permissions as grants
from app.services import admin_security as sec
from app.services import content_safety, email_settings_service, kyc_settings
from app.services import payment_config as pc
from app.services import super_admin as sa
from tests.unit.test_admin_security_hardening import (PASSWORD, bearer, code_of, denials, grant, person,  # noqa: F401
                                                      role_with)
from tests.unit.test_new_business_model import world  # noqa: F401

pytestmark = pytest.mark.unit

EVERY_PROTECTED = sorted(sec.PROTECTED_PERMISSIONS) + [email_settings_service.PERMISSION_MANAGE_EMAIL_SETTINGS,
                                                       "child_safety_resolve", "moderate_content", "manage_roles"]


def super_role(db) -> Role:
    role = db.query(Role).filter(Role.name == sa.SUPER_ADMIN_ROLE_NAME).first()
    if role is None:
        role = Role(name=sa.SUPER_ADMIN_ROLE_NAME, description="Super Admin", is_system=True)
        db.add(role)
        db.commit()
    return role


def base_role(db) -> Role:
    role = db.query(Role).filter(Role.name == "user").first()
    if role is None:
        role = Role(name="user", description="Utilisateur standard", is_system=False)
        db.add(role)
        db.commit()
    return role


def superadmin(db, name, **kw) -> User:
    return person(db, name, admin=True, role=super_role(db), **kw)


def sa_url(user) -> str:
    return f"/api/v1/admin/users/{user.id}/super-admin"


def set_super(client, actor, target, value, password=PASSWORD, replacement=None):
    body = {"is_super_admin": value}
    if password is not None:
        body["current_password"] = password
    if replacement is not None:
        body["replacement_role_id"] = replacement
    return client.put(sa_url(target), headers=bearer(actor), json=body)


def audits(db, action) -> list:
    db.expire_all()
    return [(r.user_id, r.record_id, r.old_values, r.new_values)
            for r in db.query(AuditTrail).filter(AuditTrail.action == action).order_by(AuditTrail.id).all()]


# ===========================================================================
# 1. What a Super Admin is, and holds
# ===========================================================================

def test_a_super_admin_holds_every_administrative_permission(client, db):
    for name in EVERY_PROTECTED:
        db.add(Permission(name=name, category="admin"))
    db.commit()
    boss = superadmin(db, "boss")
    plain = person(db, "plain", admin=True)

    assert sa.is_super_admin(boss) and not sa.is_super_admin(plain)
    for name in EVERY_PROTECTED + ["a_permission_added_next_year"]:
        assert pc.has_permission(boss, name), name
        assert sec.has_permission(boss, name), name
        assert deps.check_user_permission(boss, name), name
        assert not pc.has_permission(plain, name), name
    assert deps.check_user_permissions(boss, ["x", "y"], require_all=True)
    assert pc.can_activate(boss) and kyc_settings.has_permission(boss)
    assert email_settings_service.can_manage_email_settings(boss)
    assert content_safety.can_resolve_child_safety(boss) and content_safety.can_moderate(boss)

    mine = client.get("/api/v1/rbac/me/permissions", headers=bearer(boss))
    assert mine.status_code == 200 and set(mine.json()) == set(EVERY_PROTECTED)
    assert client.get("/api/v1/rbac/me/permissions", headers=bearer(plain)).json() == []
    # The pages ask the server what may be changed: everything, for a Super Admin.
    view = client.get("/api/v1/kyc/admin/settings", headers=bearer(boss))
    assert view.status_code == 200 and view.json()["can_change"] is True
    assert client.get("/api/v1/kyc/admin/settings", headers=bearer(plain)).json()["can_change"] is False
    listing = client.get("/api/v1/admin/super-admins", headers=bearer(boss)).json()
    assert listing["can_manage"] is True and [r["id"] for r in listing["super_admins"]] == [boss.id]
    assert client.get("/api/v1/admin/super-admins", headers=bearer(plain)).json()["can_manage"] is False
    assert client.get("/api/v1/admin/super-admins", headers=bearer(person(db, "member"))).status_code == 403
    users = {u["id"]: u for u in client.get("/api/v1/admin/users", headers=bearer(boss)).json()}
    assert users[boss.id]["is_super_admin"] is True and users[plain.id]["is_super_admin"] is False


def test_only_an_active_administrator_on_the_system_role_is_a_super_admin(db):
    role = super_role(db)
    switched_off = person(db, "off", admin=True, active=False, role=role)
    deleted = person(db, "deleted", admin=True, role=role)
    deleted.is_deleted = True
    db.commit()
    not_admin = person(db, "notadmin", role=role)                        # the role without the administrator flag
    for user in (switched_off, deleted, not_admin, None):
        assert not sa.is_super_admin(user)
        assert user is None or not pc.has_permission(user, sec.PERMISSION_MANAGE_ADMINS)
    # A look-alike: the same name without the system flag, or another name, does not count.
    assert not sa.is_super_admin_role(Role(name=sa.SUPER_ADMIN_ROLE_NAME, is_system=False))
    assert not sa.is_super_admin_role(Role(name="super_admin_", is_system=True))
    assert sa.is_super_admin(person(db, "real", admin=True, role=role))


# ===========================================================================
# 2. Granting and revoking
# ===========================================================================

def test_only_a_super_admin_grants_the_role_with_the_password_and_never_to_themselves(client, db):
    boss = superadmin(db, "boss")
    owner = person(db, "owner", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS, "all"))
    plain = person(db, "plain", admin=True)
    member = person(db, "member")
    target = person(db, "target", admin=True)

    assert client.put(sa_url(target), json={"is_super_admin": True, "current_password": PASSWORD}).status_code == 401
    assert set_super(client, member, target, True).status_code == 403
    for actor in (plain, owner):                     # neither is_admin nor manage_administrators nor 'all' is enough
        refused = set_super(client, actor, target, True)
        assert (refused.status_code, code_of(refused)) == (403, sec.SUPER_ADMIN_REQUIRED), actor.username
    assert code_of(set_super(client, owner, owner, True)) == sec.SUPER_ADMIN_REQUIRED     # nor promote oneself
    for password in (None, "", "not-the-password"):
        refused = set_super(client, boss, target, True, password=password)
        assert (refused.status_code, code_of(refused)) == (403, "REAUTH_REQUIRED")
    own = set_super(client, boss, boss, False)
    assert (own.status_code, code_of(own)) == (403, "SELF_ACTION_FORBIDDEN")             # no self-demotion
    db.expire_all()
    assert not sa.is_super_admin(db.get(User, target.id)) and sa.is_super_admin(db.get(User, boss.id))
    assert audits(db, sec.AUDIT_SUPER_ADMIN_GRANTED) == []
    assert [(d[0], d[1], d[2], d[3]) for d in denials(db)] == [
        (plain.id, target.id, "grant super admin", sec.SUPER_ADMIN_REQUIRED),
        (owner.id, target.id, "grant super admin", sec.SUPER_ADMIN_REQUIRED),
        (owner.id, owner.id, "grant super admin", sec.SUPER_ADMIN_REQUIRED),
        (boss.id, target.id, "grant super admin", "REAUTH_REQUIRED"),
        (boss.id, target.id, "grant super admin", "REAUTH_REQUIRED"),
        (boss.id, target.id, "grant super admin", "REAUTH_REQUIRED"),
        (boss.id, boss.id, "revoke super admin", "SELF_ACTION_FORBIDDEN"),
    ]

    old_role = target.role_id
    done = set_super(client, boss, target, True)
    assert done.status_code == 200 and done.json() == {"id": target.id, "is_super_admin": True,
                                                       "role_id": super_role(db).id, "role": "super_admin"}
    db.expire_all()
    assert sa.is_super_admin(db.get(User, target.id))
    [(actor_id, record_id, old, new)] = audits(db, sec.AUDIT_SUPER_ADMIN_GRANTED)
    assert (actor_id, record_id, old["role_id"], new["role"]) == (boss.id, target.id, old_role, "super_admin")
    entry = db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_SUPER_ADMIN_GRANTED).one()
    assert entry.ip_address and PASSWORD not in str(entry.new_values) + str(entry.old_values)
    again = set_super(client, boss, target, True)
    assert (again.status_code, code_of(again)) == (409, "ALREADY_SUPER_ADMIN")


def test_only_an_active_administrator_with_a_verified_address_can_become_a_super_admin(client, db):
    boss = superadmin(db, "boss")
    candidates = (person(db, "member"),                                                  # not an administrator
                  person(db, "off", admin=True, active=False),
                  person(db, "gone", admin=True),
                  person(db, "unverified", admin=True, email_verified=False, is_verified=False))
    candidates[2].is_deleted = True
    db.commit()
    for target in candidates:
        refused = set_super(client, boss, target, True)
        assert (refused.status_code, code_of(refused)) == (409, "TARGET_NOT_ELIGIBLE"), target.username
    assert set_super(client, boss, type("U", (), {"id": 999999})(), True).status_code == 404
    db.expire_all()
    assert not any(sa.is_super_admin(db.get(User, t.id)) for t in candidates)


def test_revoking_ends_the_powers_and_the_sessions_and_needs_another_super_admin(client, db):
    base = base_role(db)
    first, second = superadmin(db, "first"), superadmin(db, "second")
    session = bearer(second)
    assert client.get("/api/v1/admin/super-admins", headers=session).json()["can_manage"] is True

    not_one = set_super(client, first, person(db, "plain", admin=True), False, replacement=base.id)
    assert (not_one.status_code, code_of(not_one)) == (409, "NOT_SUPER_ADMIN")
    done = set_super(client, first, second, False, replacement=base.id)
    assert done.status_code == 200 and done.json()["is_super_admin"] is False
    db.expire_all()
    revoked = db.get(User, second.id)
    assert revoked.role.name == "user" and revoked.is_admin is True and revoked.security_version == 1
    assert not pc.has_permission(revoked, sec.PERMISSION_MANAGE_KYC)
    assert client.get("/api/v1/admin/super-admins", headers=session).status_code == 401   # the old session is over
    [(actor_id, record_id, old, new)] = audits(db, sec.AUDIT_SUPER_ADMIN_REVOKED)
    assert (actor_id, record_id, old["role"], new["role"]) == (first.id, second.id, "super_admin", "user")
    assert new["restored_previous_role"] is False
    # The last one cannot demote themselves, and nobody else is left to do it.
    own = set_super(client, first, first, False)
    assert code_of(own) == "SELF_ACTION_FORBIDDEN"
    assert sec.active_super_admin_ids(db) == [first.id]


def test_promotion_keeps_the_previous_role_and_demotion_gives_it_back(client, db):
    base_role(db)
    boss, colleague = superadmin(db, "boss"), superadmin(db, "colleague")
    # An administrator whose role carries a permission of its own (here: the email settings).
    target = person(db, "target", admin=True, permissions=(email_settings_service.PERMISSION_MANAGE_EMAIL_SETTINGS,))
    previous = target.role_id

    assert set_super(client, boss, target, True).status_code == 200
    db.expire_all()
    promoted = db.get(User, target.id)
    assert sa.is_super_admin(promoted) and promoted.role_before_super_admin_id == previous
    [(_a, _r, old, new)] = audits(db, sec.AUDIT_SUPER_ADMIN_GRANTED)
    assert (old["role_id"], old["role"], new["role"]) == (previous, "role_target", "super_admin")

    # Revoked by somebody else than the one who granted it: the previous access comes back, nothing more.
    done = set_super(client, colleague, target, False)
    assert done.status_code == 200, done.text
    assert done.json() == {"id": target.id, "is_super_admin": False, "role_id": previous, "role": "role_target"}
    db.expire_all()
    demoted = db.get(User, target.id)
    assert (demoted.role_id, demoted.role_before_super_admin_id, demoted.is_admin) == (previous, None, True)
    assert demoted.security_version == 1
    assert email_settings_service.can_manage_email_settings(demoted)                 # its own permission is back
    assert not pc.has_permission(demoted, sec.PERMISSION_MANAGE_KYC)                 # the Super Admin ones are gone
    [(actor_id, _r, old, new)] = audits(db, sec.AUDIT_SUPER_ADMIN_REVOKED)
    assert (actor_id, old["role"], new) == (
        colleague.id, "super_admin", {"role_id": previous, "role": "role_target", "restored_previous_role": True})

    # Promoted again and demoted with an explicit choice instead: the choice wins.
    helper = Role(name="helper", description="an ordinary role")
    db.add(helper)
    db.commit()
    assert set_super(client, boss, target, True).status_code == 200
    done = set_super(client, boss, target, False, replacement=helper.id)
    assert done.status_code == 200 and done.json()["role"] == "helper"
    db.expire_all()
    assert (db.get(User, target.id).role_id, db.get(User, target.id).role_before_super_admin_id) == (helper.id, None)
    assert audits(db, sec.AUDIT_SUPER_ADMIN_REVOKED)[-1][3]["restored_previous_role"] is False


def test_without_a_usable_previous_role_the_acting_super_admin_must_choose(client, db):
    boss = superadmin(db, "boss")
    no_role = person(db, "norole", admin=True)                                       # had no role at all
    assert set_super(client, boss, no_role, True).status_code == 200
    refused = set_super(client, boss, no_role, False)
    assert (refused.status_code, code_of(refused)) == (409, "REPLACEMENT_ROLE_REQUIRED")
    db.expire_all()
    assert sa.is_super_admin(db.get(User, no_role.id))                               # nothing changed
    assert db.get(User, no_role.id).security_version == 0
    assert audits(db, sec.AUDIT_SUPER_ADMIN_REVOKED) == []
    assert denials(db)[-1][2:] == ("revoke super admin", "REPLACEMENT_ROLE_REQUIRED")

    # A previous role that has since been changed by hand to lead back to Super Admin is not restored.
    sneaky = Role(name="sneaky", inherit_from_id=super_role(db).id)
    db.add(sneaky)
    db.commit()
    db.query(User).filter(User.id == no_role.id).update({"role_before_super_admin_id": sneaky.id})
    db.commit()
    refused = set_super(client, boss, no_role, False)
    assert (refused.status_code, code_of(refused)) == (409, "REPLACEMENT_ROLE_REQUIRED")
    db.expire_all()
    assert sa.is_super_admin(db.get(User, no_role.id))

    base = base_role(db)
    assert set_super(client, boss, no_role, False, replacement=base.id).status_code == 200
    db.expire_all()
    assert db.get(User, no_role.id).role_id == base.id and not sa.is_super_admin(db.get(User, no_role.id))


def test_a_replacement_role_never_leads_back_to_super_admin(client, db):
    role = super_role(db)
    boss, other = superadmin(db, "boss"), superadmin(db, "other")
    child = Role(name="child_of_super", inherit_from_id=role.id)
    db.add(child)
    db.commit()
    grandchild = Role(name="grandchild_of_super", inherit_from_id=child.id)
    looping_a = Role(name="loop_a")
    db.add_all([grandchild, looping_a])
    db.commit()
    looping_b = Role(name="loop_b", inherit_from_id=looping_a.id)
    db.add(looping_b)
    db.commit()
    looping_a.inherit_from_id = looping_b.id                                        # a cycle, made by hand
    db.commit()

    for replacement, code in ((role.id, "REPLACEMENT_ROLE_GRANTS_SUPER_ADMIN"),
                              (child.id, "REPLACEMENT_ROLE_GRANTS_SUPER_ADMIN"),
                              (grandchild.id, "REPLACEMENT_ROLE_GRANTS_SUPER_ADMIN"),
                              (looping_a.id, "REPLACEMENT_ROLE_GRANTS_SUPER_ADMIN"),
                              (999999, "REPLACEMENT_ROLE_NOT_FOUND")):
        refused = set_super(client, boss, other, False, replacement=replacement)
        assert (refused.status_code, code_of(refused)) == (422, code), replacement
    for bad in (0, -1, "3", 1.5, True):                                              # not a role id at all
        body = {"is_super_admin": False, "current_password": PASSWORD, "replacement_role_id": bad}
        assert client.put(sa_url(other), headers=bearer(boss), json=body).status_code == 422, bad
    # A replacement belongs to a revocation only.
    target = person(db, "target", admin=True)
    misused = set_super(client, boss, target, True, replacement=base_role(db).id)
    assert (misused.status_code, code_of(misused)) == (422, "INVALID_REQUEST")
    db.expire_all()
    assert sa.is_super_admin(db.get(User, other.id)) and not sa.is_super_admin(db.get(User, target.id))
    assert audits(db, sec.AUDIT_SUPER_ADMIN_REVOKED) == audits(db, sec.AUDIT_SUPER_ADMIN_GRANTED) == []
    # The choice is still checked AFTER the password, so it cannot be used to probe without one.
    assert code_of(set_super(client, boss, other, False, password="wrong", replacement=role.id)) == "REAUTH_REQUIRED"


def test_the_demotion_choices_are_shown_to_a_super_admin_only(client, db):
    role = super_role(db)
    boss = superadmin(db, "boss")
    target = person(db, "target", admin=True, permissions=("moderate_content",))
    previous = target.role_id
    db.add_all([Role(name="child_of_super", inherit_from_id=role.id), Role(name="helper")])
    db.commit()
    assert set_super(client, boss, target, True).status_code == 200
    url = f"/api/v1/admin/users/{target.id}/super-admin/demotion-options"

    answer = client.get(url, headers=bearer(boss)).json()
    assert answer["previous_role"] == {"id": previous, "name": "role_target"} and answer["previous_role_valid"]
    names = {r["name"] for r in answer["roles"]}
    assert {"helper", "role_target"} <= names
    assert not names & {"super_admin", "child_of_super"}
    plain = person(db, "plain", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    assert code_of(client.get(url, headers=bearer(plain))) == sec.SUPER_ADMIN_REQUIRED
    assert client.get(url, headers=bearer(person(db, "member"))).status_code == 403
    assert client.get("/api/v1/admin/users/999999/super-admin/demotion-options", headers=bearer(boss)).status_code == 404


def test_a_demotion_and_a_promotion_racing_on_one_account_keep_the_previous_role(client, db, monkeypatch):
    """A second grant that arrives while the first is being written must not
    record the Super Admin role as the 'previous' one (it would then be given
    back on revocation). The rows are re-read under the lock, so it is refused."""
    boss, colleague = superadmin(db, "boss"), superadmin(db, "colleague")
    target = person(db, "target", admin=True, permissions=("moderate_content",))
    previous = target.role_id
    real_lock = sec._lock_super_admins
    calls = {"n": 0}

    def granted_meanwhile(session, role_id, *also):
        calls["n"] += 1
        if calls["n"] == 1:          # the other grant committed between this one's checks and its lock
            session.query(User).filter(User.id == target.id).update(
                {"role_id": role_id, "role_before_super_admin_id": previous})
        return real_lock(session, role_id, *also)

    monkeypatch.setattr(sec, "_lock_super_admins", granted_meanwhile)
    late = set_super(client, colleague, target, True)
    assert (late.status_code, code_of(late)) == (409, "ALREADY_SUPER_ADMIN")
    monkeypatch.setattr(sec, "_lock_super_admins", real_lock)
    assert set_super(client, boss, target, True).status_code == 200                  # the real grant
    db.expire_all()
    assert db.get(User, target.id).role_before_super_admin_id == previous            # never the Super Admin role
    assert set_super(client, colleague, target, False).status_code == 200
    db.expire_all()
    assert db.get(User, target.id).role_id == previous


def test_the_last_super_admin_is_never_removed_even_when_the_records_disagree(client, db, monkeypatch):
    first, second = superadmin(db, "first"), superadmin(db, "second")
    # Defence in depth: whatever the count says when the rows are locked decides.
    monkeypatch.setattr(sec, "active_super_admin_ids", lambda *_a, **_k: [second.id])
    refused = set_super(client, first, second, False)
    assert (refused.status_code, code_of(refused)) == (409, "LAST_SUPER_ADMIN")
    off = client.put(f"/api/v1/admin/users/{second.id}/status", headers=bearer(first),
                     json={"is_active": False, "current_password": PASSWORD})
    assert (off.status_code, code_of(off)) == (409, "LAST_SUPER_ADMIN")
    db.expire_all()
    assert sa.is_super_admin(db.get(User, second.id))
    assert [d[3] for d in denials(db)] == ["LAST_SUPER_ADMIN", "LAST_SUPER_ADMIN"]


def test_a_super_admin_revoked_meanwhile_cannot_finish_what_they_started(client, db, monkeypatch):
    """Two Super Admins revoking each other at the same moment: the rows are
    locked and re-read, and the one who lost the role is refused."""
    base_role(db)
    first, second = superadmin(db, "first"), superadmin(db, "second")
    real_lock = sec._lock_super_admins
    base_id = base_role(db).id

    def revoked_just_before_the_lock(session, role_id, *also):
        session.query(User).filter(User.id == first.id).update({"role_id": base_id})
        return real_lock(session, role_id, *also)

    monkeypatch.setattr(sec, "_lock_super_admins", revoked_just_before_the_lock)
    refused = set_super(client, first, second, False)
    assert (refused.status_code, code_of(refused)) == (403, sec.SUPER_ADMIN_REQUIRED)
    db.expire_all()
    assert sa.is_super_admin(db.get(User, second.id))
    assert audits(db, sec.AUDIT_SUPER_ADMIN_REVOKED) == []


# ===========================================================================
# 3. No other way in or out
# ===========================================================================

def test_no_other_administrator_path_makes_or_unmakes_a_super_admin(client, db):
    boss, other = superadmin(db, "boss"), superadmin(db, "other")
    owner = person(db, "owner", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    body = {"current_password": PASSWORD}

    # Removing the administrator flag: refused for everybody, a Super Admin too.
    for actor in (owner, boss):
        flag = client.put(f"/api/v1/admin/users/{other.id}/role", headers=bearer(actor), json={"is_admin": False, **body})
        assert (flag.status_code, code_of(flag)) == (409, "SUPER_ADMIN_PROTECTED"), actor.username
    # Nor does the flag turn an account that sits on the role (only possible by hand) into a Super Admin.
    dormant = person(db, "dormant", role=super_role(db))
    made = client.put(f"/api/v1/admin/users/{dormant.id}/role", headers=bearer(owner), json={"is_admin": True, **body})
    assert (made.status_code, code_of(made)) == (409, "SUPER_ADMIN_PROTECTED")
    db.expire_all()
    assert not sa.is_super_admin(db.get(User, dormant.id))
    # Switching a Super Admin account off or on: another Super Admin only.
    off = client.put(f"/api/v1/admin/users/{other.id}/status", headers=bearer(owner), json={"is_active": False, **body})
    assert (off.status_code, code_of(off)) == (403, sec.SUPER_ADMIN_REQUIRED)
    no_password = client.put(f"/api/v1/admin/users/{other.id}/status", headers=bearer(boss), json={"is_active": False})
    assert code_of(no_password) == "REAUTH_REQUIRED"
    # Deleting: never an administrator's account.
    gone = client.delete(f"/api/v1/admin/users/{other.id}", headers=bearer(boss))
    assert (gone.status_code, code_of(gone)) == (409, "ADMIN_ACCOUNT_PROTECTED")
    db.expire_all()
    assert sa.is_super_admin(db.get(User, other.id))

    session = bearer(other)
    done = client.put(f"/api/v1/admin/users/{other.id}/status", headers=bearer(boss), json={"is_active": False, **body})
    assert done.status_code == 200
    db.expire_all()
    assert not sa.is_super_admin(db.get(User, other.id))
    assert client.get("/api/v1/admin/users", headers=session).status_code == 401
    back = client.put(f"/api/v1/admin/users/{other.id}/status", headers=bearer(owner), json={"is_active": True, **body})
    assert code_of(back) == sec.SUPER_ADMIN_REQUIRED                       # switching back on is the same rule
    assert client.put(f"/api/v1/admin/users/{other.id}/status", headers=bearer(boss),
                      json={"is_active": True, **body}).status_code == 200


def test_the_role_management_api_cannot_touch_the_super_admin_role(client, db):
    role = super_role(db)
    manage = role_with(db, "manage_roles", "manage_users", "manage_permissions", "all", name="rolemanager")
    manager = person(db, "manager", admin=True, role=manage)
    boss = superadmin(db, "boss")
    target = person(db, "target", admin=True)
    ordinary = Role(name="helper")
    db.add(ordinary)
    db.commit()
    h = bearer(manager)

    attempts = [
        client.post("/api/v1/rbac/users/assign-role", headers=h, json={"user_id": target.id, "role_id": role.id}),
        client.post("/api/v1/rbac/users/assign-role", headers=h, json={"user_id": boss.id, "role_id": ordinary.id}),
        client.post("/api/v1/rbac/roles", headers=h, json={"name": "super_admin"}),
        client.post("/api/v1/rbac/roles", headers=h, json={"name": "Super_Admin "}),
        client.post("/api/v1/rbac/roles", headers=h, json={"name": "child", "inherit_from_id": role.id}),
        client.put(f"/api/v1/rbac/roles/{ordinary.id}", headers=h, json={"name": "super_admin"}),
        client.put(f"/api/v1/rbac/roles/{role.id}", headers=h, json={"name": "renamed"}),
        client.put(f"/api/v1/rbac/roles/{role.id}/permissions", headers=h, json={"permission_ids": []}),
        client.delete(f"/api/v1/rbac/roles/{role.id}", headers=h),
    ]
    for response in attempts:
        assert (response.status_code, code_of(response)) == (403, "PROTECTED_PERMISSION"), response.text
    db.expire_all()
    assert db.get(User, target.id).role_id != role.id and sa.is_super_admin(db.get(User, boss.id))
    assert db.query(Role).filter(Role.name == "super_admin").one().is_system is True


def test_the_grant_tools_leave_a_super_admin_alone(db):
    for name in grants.PERMISSIONS + (email_settings_service.PERMISSION_MANAGE_EMAIL_SETTINGS,):
        db.add(Permission(name=name, category="admin"))
    db.commit()
    boss = superadmin(db, "boss")
    with pytest.raises(grants.GrantError, match="Super Admin"):
        grants.grant(db, boss.email, [sec.PERMISSION_MANAGE_KYC], apply=True)
    with pytest.raises(grants.GrantError, match="Super Admin"):
        grants.revoke(db, boss.email, apply=True)
    with pytest.raises(email_grants.GrantError, match="Super Admin"):
        email_grants.grant(db, boss.email, apply=True)
    db.expire_all()
    assert db.get(User, boss.id).role.name == "super_admin"


# ===========================================================================
# 4. The safeguards that are not permissions still hold
# ===========================================================================

def test_a_super_admin_is_still_bound_by_the_password_and_the_financial_safeguards(client, world):
    db = world
    boss = superadmin(db, "boss", usdt_wallet_address="0x" + "4" * 40)
    referral = person(db, "referral", sponsor_id=boss.id)

    # No payment recorded for oneself, nor for one's own referral line.
    assert code_of(grant(client, boss, boss)) == "SELF_ACTION_FORBIDDEN"
    assert code_of(grant(client, boss, referral)) == "COMMISSION_CONFLICT"
    assert code_of(grant(client, boss, referral, current_password="wrong")) == "REAUTH_REQUIRED"
    # Nor one's own identity verified.
    own = client.put(f"/api/v1/admin/users/{boss.id}/kyc/verify", headers=bearer(boss))
    assert code_of(own) == "SELF_ACTION_FORBIDDEN"
    # The KYC settings: the permission is there, the password is still asked for.
    for password in ("", "wrong"):
        refused = client.put("/api/v1/kyc/admin/settings", headers=bearer(boss),
                             json={"enabled": True, "current_password": password})
        assert refused.status_code == 403 and code_of(refused) == "REAUTH_REQUIRED", refused.text
    db.expire_all()
    from app.models.payment import Deposit

    assert db.query(Deposit).count() == 0 and not db.get(User, boss.id).identity_verified


# ===========================================================================
# 5. The first Super Admins
# ===========================================================================

def test_the_first_super_admins_are_named_once_by_id_and_address(db):
    role = super_role(db)
    owner = person(db, "owner", admin=True)
    operator = person(db, "operator", admin=True, permissions=("manage_email_settings",))
    plain_member = person(db, "member")
    pair = [(owner.id, owner.email), (operator.id, operator.email.upper())]

    refusals = [
        [(owner.id, owner.email)],                                              # only one
        [(owner.id, owner.email), (owner.id, owner.email)],                     # the same twice
        [(owner.id, operator.email), (operator.id, operator.email)],            # id and address of different accounts
        [(owner.id, owner.email), (plain_member.id, plain_member.email)],       # not an administrator
    ]
    for accounts in refusals:
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap.bootstrap(db, accounts, apply=True)
    # A dry run writes nothing.
    assert [u.id for u in bootstrap.bootstrap(db, pair)] == [owner.id, operator.id]
    db.expire_all()
    assert db.query(User).filter(User.role_id == role.id).count() == 0

    old_operator_role = operator.role_id
    bootstrap.bootstrap(db, pair, apply=True)
    db.expire_all()
    assert sa.is_super_admin(db.get(User, owner.id)) and sa.is_super_admin(db.get(User, operator.id))
    rows = audits(db, sec.AUDIT_SUPER_ADMIN_BOOTSTRAP)
    assert [(r[0], r[1]) for r in rows] == [(None, owner.id), (None, operator.id)]
    assert rows[1][2]["role_id"] == old_operator_role
    assert db.get(User, operator.id).role_before_super_admin_id == old_operator_role
    assert db.get(User, owner.id).role_before_super_admin_id is None
    # Once there is a Super Admin, the tool does nothing: the application decides.
    third = person(db, "third", admin=True)
    with pytest.raises(bootstrap.BootstrapError, match="already hold"):
        bootstrap.bootstrap(db, [(third.id, third.email), (owner.id, owner.email)], apply=True)


def test_the_bootstrap_tool_refuses_without_the_role_and_parses_its_arguments(db):
    a, b = person(db, "a", admin=True), person(db, "b", admin=True)
    with pytest.raises(bootstrap.BootstrapError, match="migrations"):
        bootstrap.bootstrap(db, [(a.id, a.email), (b.id, b.email)])
    assert bootstrap.parse_account(" 12:owner@example.com ".strip()) == (12, "owner@example.com")
    for bad in ("owner@example.com", "x:owner@example.com", "12:", "12-owner@example.com"):
        with pytest.raises(Exception):
            bootstrap.parse_account(bad)
