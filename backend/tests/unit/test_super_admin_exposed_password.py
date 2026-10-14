"""An exposed password blocks the Super Admin role, and a single first Super Admin.

  1. an account whose CURRENT password hash is among the exposed ones cannot be
     made a Super Admin, by the bootstrap or in the Admin Panel; once its owner
     sets a new password, it can (through the normal interface, by a Super Admin);
  2. the bootstrap refuses to run before the exposed list is loaded, and starts
     with ONE Super Admin only when told so (--single);
  3. a single Super Admin keeps every last-Super-Admin protection;
  4. the loader stores fingerprints only, is repeatable, and counts the
     accounts still affected;
  5. a password reset cannot set the same password again.

Every account, password and hash is SYNTHETIC.
"""
from __future__ import annotations

import pytest

from app.core.security import get_password_hash, verify_password
from app.models.accounting import AuditTrail
from app.models.auth_security import PURPOSE_PASSWORD_RESET, ExposedPasswordFingerprint
from app.models.user import Role, User
from app.scripts import bootstrap_super_admins as boot
from app.scripts import load_exposed_password_fingerprints as loader
from app.services import admin_security as sec
from app.services import auth_tokens, password_exposure
from app.services import super_admin as sa
from tests.unit.test_admin_security_hardening import (PASSWORD, address, bearer, code_of, denials,  # noqa: F401
                                                      fixed_address, person)
from tests.unit.test_super_admin import base_role, set_super, super_role

pytestmark = pytest.mark.unit

NEW_PASSWORD = "A-Brand-New-Passw0rd!77"


def expose(db, *users) -> None:
    """The users' CURRENT hashes appear in an exposed copy of the user table."""
    password_exposure.add(db, [u.hashed_password for u in users], source="synthetic exposure")
    db.commit()


def own_hash(db, user):
    """The synthetic accounts share one precomputed hash; give this one its own (same password, new salt),
    so that exposing it exposes nobody else."""
    user.hashed_password = get_password_hash(PASSWORD)
    db.commit()
    return user


def admins(db):
    base_role(db)
    super_role(db)
    operator = person(db, "operator", admin=True, permissions=("manage_email_settings",))
    owner = own_hash(db, person(db, "owner", admin=True))
    expose(db, owner)
    return operator, owner


# ===========================================================================
# 1. The exposed password blocks the role until it is changed
# ===========================================================================

def test_the_exposed_check_is_about_the_current_hash_only(db):
    operator, owner = admins(db)
    assert password_exposure.is_exposed(db, owner) and not password_exposure.is_exposed(db, operator)
    stored = db.query(ExposedPasswordFingerprint).one()
    assert stored.fingerprint != owner.hashed_password and len(stored.fingerprint) == 64     # a fingerprint, not the hash
    assert owner.hashed_password not in str([(r.fingerprint, r.source) for r in db.query(ExposedPasswordFingerprint)])
    owner.hashed_password = "$2b$12$" + "x" * 53                                             # any new hash
    assert not password_exposure.is_exposed(db, owner)


def test_a_super_admin_cannot_promote_an_account_whose_password_was_exposed_until_it_is_changed(client, db, fixed_address):
    operator, owner = admins(db)
    boot.bootstrap(db, [(operator.id, operator.email)], apply=True, single=True)
    db.expire_all()
    owner_role = db.get(User, owner.id).role_id

    refused = set_super(client, operator, owner, True)
    assert (refused.status_code, code_of(refused)) == (409, password_exposure.PASSWORD_CHANGE_REQUIRED)
    db.expire_all()
    unchanged = db.get(User, owner.id)
    assert (unchanged.role_id, unchanged.role_before_super_admin_id, sa.is_super_admin(unchanged)) == (owner_role, None, False)
    assert denials(db)[-1][1:] == (owner.id, "grant super admin", password_exposure.PASSWORD_CHANGE_REQUIRED)
    assert db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_SUPER_ADMIN_GRANTED).count() == 0

    # The owner changes the password through the ordinary page; then the ordinary promotion works.
    changed = client.post("/api/v1/auth/change-password", headers=bearer(unchanged),
                          json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert changed.status_code == 200, changed.text
    db.expire_all()
    assert not password_exposure.is_exposed(db, db.get(User, owner.id))
    done = set_super(client, operator, db.get(User, owner.id), True)
    assert done.status_code == 200, done.text
    db.expire_all()
    promoted = db.get(User, owner.id)
    assert sa.is_super_admin(promoted) and promoted.role_before_super_admin_id == owner_role
    assert sec.active_super_admin_ids(db) == sorted([operator.id, owner.id])


# ===========================================================================
# 2. The bootstrap: the exposed list, the exposed account, --single
# ===========================================================================

def test_the_bootstrap_needs_the_exposed_list_and_refuses_an_exposed_account(db):
    base_role(db)
    super_role(db)
    operator = person(db, "operator", admin=True)
    owner = own_hash(db, person(db, "owner", admin=True))
    with pytest.raises(boot.BootstrapError, match="exposed password fingerprints is empty"):
        boot.bootstrap(db, [(operator.id, operator.email)], single=True)
    expose(db, owner)
    with pytest.raises(boot.BootstrapError, match=password_exposure.PASSWORD_CHANGE_REQUIRED):
        boot.bootstrap(db, [(operator.id, operator.email), (owner.id, owner.email)], apply=True)
    with pytest.raises(boot.BootstrapError, match=password_exposure.PASSWORD_CHANGE_REQUIRED):
        boot.bootstrap(db, [(owner.id, owner.email)], apply=True, single=True)
    db.expire_all()
    assert sec.active_super_admin_ids(db) == []                                    # all or nothing: nobody promoted
    assert db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_SUPER_ADMIN_BOOTSTRAP).count() == 0


def test_one_first_super_admin_only_when_asked_for_and_only_exactly_one(db):
    operator, owner = admins(db)
    other = person(db, "other", admin=True)
    with pytest.raises(boot.BootstrapError, match="at least 2"):
        boot.bootstrap(db, [(operator.id, operator.email)], apply=True)              # no --single
    with pytest.raises(boot.BootstrapError, match="exactly one"):
        boot.bootstrap(db, [(operator.id, operator.email), (other.id, other.email)], apply=True, single=True)
    assert [u.id for u in boot.bootstrap(db, [(operator.id, operator.email)], single=True)] == [operator.id]   # dry run
    db.expire_all()
    assert sec.active_super_admin_ids(db) == []

    previous = operator.role_id
    boot.bootstrap(db, [(operator.id, operator.email)], apply=True, single=True)
    db.expire_all()
    assert sec.active_super_admin_ids(db) == [operator.id]
    assert db.get(User, operator.id).role_before_super_admin_id == previous
    [row] = db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_SUPER_ADMIN_BOOTSTRAP).all()
    assert (row.user_id, row.record_id, row.new_values["single_initial_super_admin"]) == (None, operator.id, True)
    # Nobody else changed, the exposed owner least of all.
    assert (db.get(User, owner.id).role_id, db.get(User, owner.id).role_before_super_admin_id) == (owner.role_id, None)
    with pytest.raises(boot.BootstrapError, match="already hold"):
        boot.bootstrap(db, [(other.id, other.email)], apply=True, single=True)


def test_the_command_line_prints_ids_only(db, capsys, monkeypatch):
    operator, _owner = admins(db)
    import app.db.session as session_module

    monkeypatch.setattr(session_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    assert boot.main(["--single", "--account", f"{operator.id}:{operator.email}"]) == 0
    out = capsys.readouterr().out
    assert f"#{operator.id}" in out and "DRY RUN" in out and operator.email not in out


# ===========================================================================
# 3. A single Super Admin keeps every last-Super-Admin protection
# ===========================================================================

def test_a_single_super_admin_is_protected_as_the_last_one(client, db, fixed_address):
    operator, owner = admins(db)
    manager = person(db, "manager", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS,))
    boot.bootstrap(db, [(operator.id, operator.email)], apply=True, single=True)
    db.expire_all()
    me = db.get(User, operator.id)
    body = {"current_password": PASSWORD}
    assert code_of(set_super(client, me, me, False, replacement=base_role(db).id)) == "SELF_ACTION_FORBIDDEN"
    assert code_of(client.put(f"/api/v1/admin/users/{me.id}/status", headers=bearer(manager),
                              json={"is_active": False, **body})) == sec.SUPER_ADMIN_REQUIRED
    assert code_of(client.put(f"/api/v1/admin/users/{me.id}/role", headers=bearer(manager),
                              json={"is_admin": False, **body})) == "SUPER_ADMIN_PROTECTED"
    assert code_of(set_super(client, manager, me, False)) == sec.SUPER_ADMIN_REQUIRED
    assert client.delete(f"/api/v1/admin/users/{me.id}", headers=bearer(manager)).status_code == 409
    db.expire_all()
    assert sec.active_super_admin_ids(db) == [operator.id]


# ===========================================================================
# 4. The loader
# ===========================================================================

def copy_block(rows):
    lines = ["COPY public.users (id, email, hashed_password, is_admin) FROM stdin;"]
    lines += [f"{i}\tu{i}@example.com\t{h}\tf" for i, h in rows]
    return lines + ["\\.", ""]


def test_the_loader_stores_fingerprints_only_and_is_repeatable(db, tmp_path):
    _operator, owner = admins(db)
    db.query(ExposedPasswordFingerprint).delete()
    db.commit()
    dump = tmp_path / "exposed.sql"
    dump.write_text("\n".join(["-- synthetic", "SET x = 1;"] + copy_block([(1, owner.hashed_password),
                                                                           (2, "$2b$12$" + "y" * 53), (3, "\\N")])))
    dry = loader.load(db, [str(dump)], source="synthetic", apply=False)
    assert dry == {"hashes read": 2, "distinct fingerprints": 2, "already recorded": 0, "new": 2,
                   "accounts whose current password is one of them": 1}
    assert db.query(ExposedPasswordFingerprint).count() == 0                        # a dry run writes nothing
    done = loader.load(db, [str(dump)], source="synthetic", apply=True)
    assert done["new"] == 2 and db.query(ExposedPasswordFingerprint).count() == 2
    stored = " ".join(r.fingerprint + str(r.source) for r in db.query(ExposedPasswordFingerprint))
    assert owner.hashed_password not in stored and "u1@example.com" not in stored
    again = loader.load(db, [str(dump)], source="synthetic", apply=True)
    assert (again["new"], again["already recorded"]) == (0, 2)
    assert password_exposure.is_exposed(db, owner)
    for bad in ("no users here\n", "COPY public.users (id, email) FROM stdin;\n1\tx\n\\.\n"):
        other = tmp_path / "bad.sql"
        other.write_text(bad)
        with pytest.raises(loader.LoadError):
            loader.load(db, [str(other)], source="synthetic", apply=True)


# ===========================================================================
# 5. A password reset sets a NEW password
# ===========================================================================

def test_a_password_reset_cannot_set_the_same_password_again(client, db, email_outbox, fixed_address):
    _operator, owner = admins(db)
    raw = auth_tokens.issue(db, owner, PURPOSE_PASSWORD_RESET)
    db.commit()
    same = client.post("/api/v1/auth/password-reset-confirm", json={"token": raw, "new_password": PASSWORD})
    assert same.status_code == 400
    db.expire_all()
    assert verify_password(PASSWORD, db.get(User, owner.id).hashed_password)
    assert password_exposure.is_exposed(db, db.get(User, owner.id))                # still blocked
    # The link was not used up by the refusal: it sets a new password.
    done = client.post("/api/v1/auth/password-reset-confirm", json={"token": raw, "new_password": NEW_PASSWORD})
    assert done.status_code == 200, done.text
    db.expire_all()
    assert not password_exposure.is_exposed(db, db.get(User, owner.id))
