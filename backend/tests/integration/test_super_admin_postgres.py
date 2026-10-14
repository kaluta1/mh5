"""The Super Admin role and migration c4d5e6f7a8b9 on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. SQLite ignores row locks, so
"two Super Admins revoking each other at the same moment never leave the
platform without one" can only be proven here. Everything is SYNTHETIC.
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest
from sqlalchemy import text

from app.core.security import get_password_hash
from app.models.accounting import AuditTrail
from app.models.user import Role, User
from app.services import admin_security as sec
from app.services import super_admin as sa
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

MIGRATION = "c4d5e6f7a8b9_super_admin_role.py"
PASSWORD = "Synthetic-Admin-Passw0rd!"
PASSWORD_HASH = get_password_hash(PASSWORD)


def seed(Session, name: str, *, role_name=None, admin=True, previous_role_name=None) -> int:
    with Session() as db:
        def role_id(n):
            return db.query(Role.id).filter(Role.name == n).scalar() if n else None

        user = User(email=f"{name}@example.com", username=name, hashed_password=PASSWORD_HASH, is_active=True,
                    is_deleted=False, is_admin=admin, date_of_birth=datetime(1990, 1, 1),
                    personal_referral_code=name.upper(), email_verified=True, role_id=role_id(role_name),
                    role_before_super_admin_id=role_id(previous_role_name))
        db.add(user)
        db.commit()
        return user.id


def roles(Session, *names) -> None:
    with Session() as db:
        for n in names:
            db.add(Role(name=n, description=n))
        db.commit()


def super_role_rows(engine) -> list:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "select r.name, r.is_system, (select count(*) from role_permissions rp where rp.role_id = r.id), "
            "(select count(*) from users u where u.role_id = r.id) from roles r where r.name = 'super_admin'"))]


def previous_role_column(engine) -> list:
    with engine.connect() as c:
        column = c.execute(text(
            "select data_type, is_nullable from information_schema.columns where table_name = 'users' "
            "and column_name = 'role_before_super_admin_id'")).fetchall()
        rule = c.execute(text(
            "select pg_get_constraintdef(oid) from pg_constraint where conrelid = 'users'::regclass "
            "and contype = 'f' and pg_get_constraintdef(oid) like '%role_before_super_admin_id%'")).fetchall()
    return [tuple(r) for r in column] + [r[0] for r in rule]


def access(engine) -> tuple:
    with engine.connect() as c:
        return (tuple(c.execute(text("select id, role_id, is_admin, is_active, security_version from users "
                                     "order by id")).fetchall()),
                tuple(c.execute(text("select id, name, is_system, inherit_from_id from roles where name <> "
                                     "'super_admin' order by id")).fetchall()),
                tuple(c.execute(text("select role_id, permission_id from role_permissions order by 1, 2")).fetchall()),
                tuple(c.execute(text("select id, name from permissions order by id")).fetchall()))


COLUMN = [("integer", "YES"), "FOREIGN KEY (role_before_super_admin_id) REFERENCES roles(id) ON DELETE SET NULL"]


def test_the_migration_adds_one_empty_system_role_one_empty_column_and_nothing_else(pg):
    engine, Session = pg
    roles(Session, "user")
    seed(Session, "owner", role_name="user")
    seed(Session, "member", admin=False)
    migrate(engine, MIGRATION, "downgrade")                              # the production schema before it
    assert super_role_rows(engine) == [] and previous_role_column(engine) == []
    before = access(engine)

    for _ in range(2):                                                   # a re-run is a no-op
        migrate(engine, MIGRATION, "upgrade")
        assert super_role_rows(engine) == [("super_admin", True, 0, 0)]   # no permission row, no member
        assert previous_role_column(engine) == COLUMN
        assert access(engine) == before                                  # nobody's role, no permission changed
        with engine.connect() as c:
            assert c.execute(text("select count(*) from users where role_before_super_admin_id is not null")
                             ).scalar() == 0
    migrate(engine, MIGRATION, "downgrade")
    assert super_role_rows(engine) == [] and previous_role_column(engine) == [] and access(engine) == before
    migrate(engine, MIGRATION, "upgrade")

    # A downgrade keeps the role, and the column that says what to give back, while somebody holds it.
    with Session() as db:
        db.query(User).filter(User.username == "owner").update(
            {"role_id": db.query(Role.id).filter(Role.name == "super_admin").scalar()})
        db.commit()
    migrate(engine, MIGRATION, "downgrade")
    assert super_role_rows(engine) == [("super_admin", True, 0, 1)] and previous_role_column(engine) == COLUMN


def test_the_migration_stops_on_a_role_of_that_name_it_did_not_create(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "downgrade")
    with Session() as db:
        db.add(Role(name="super_admin", description="made by hand", is_system=False))
        db.commit()
    before = access(engine)
    with pytest.raises(Exception, match="already exists"):
        migrate(engine, MIGRATION, "upgrade")
    assert super_role_rows(engine) == [("super_admin", False, 0, 0)] and access(engine) == before
    assert previous_role_column(engine) == []                            # one transaction: nothing at all


def revoke(Session, actor_id: int, target_id: int, replacement=None):
    with Session() as db:
        try:
            sec.set_super_admin(db, db.get(User, actor_id), target_id=target_id, grant=False, password=PASSWORD,
                                replacement_role_id=replacement)
            return "revoked"
        except sec.AdminSecurityError as exc:
            return exc.code


def grant(Session, actor_id: int, target_id: int):
    with Session() as db:
        try:
            sec.set_super_admin(db, db.get(User, actor_id), target_id=target_id, grant=True, password=PASSWORD)
            return "granted"
        except sec.AdminSecurityError as exc:
            return exc.code


def role_of(Session, user_id: int) -> tuple:
    with Session() as db:
        user = db.get(User, user_id)
        name = db.query(Role.name).filter(Role.id == user.role_id).scalar() if user.role_id else None
        previous = (db.query(Role.name).filter(Role.id == user.role_before_super_admin_id).scalar()
                    if user.role_before_super_admin_id else None)
        return name, previous


def test_two_super_admins_revoking_each_other_at_once_leave_one_with_its_previous_role(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "upgrade")                              # the Super Admin role
    roles(Session, "user", "finance_like", "moderator_like")
    ids = [seed(Session, "first", role_name="super_admin", previous_role_name="finance_like"),
           seed(Session, "second", role_name="super_admin", previous_role_name="moderator_like")]
    previous = {ids[0]: "finance_like", ids[1]: "moderator_like"}

    for _round in range(3):
        results = in_threads(2, lambda i: revoke(Session, ids[i], ids[1 - i]))
        assert sorted(results) == sorted(["revoked", sec.SUPER_ADMIN_REQUIRED]), results
        with Session() as db:
            remaining = sec.active_super_admin_ids(db)
        assert len(remaining) == 1
        other = [i for i in ids if i not in remaining][0]
        assert role_of(Session, other) == (previous[other], None)           # given back, nothing kept aside
        assert role_of(Session, remaining[0]) == ("super_admin", previous[remaining[0]])
        with Session() as db:
            assert db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_SUPER_ADMIN_REVOKED).count() == _round + 1
        # Put the other one back for the next round, as a Super Admin would.
        assert grant(Session, remaining[0], other) == "granted"
        assert role_of(Session, other) == ("super_admin", previous[other])
        with Session() as db:
            assert sorted(sec.active_super_admin_ids(db)) == sorted(ids)
            assert all(sa.is_super_admin(db.get(User, i)) for i in ids)


def test_two_super_admins_revoking_the_same_account_at_once_change_it_once(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "upgrade")                              # the Super Admin role
    roles(Session, "user", "finance_like", "helper")
    actors = [seed(Session, "a", role_name="super_admin"), seed(Session, "b", role_name="super_admin")]
    target = seed(Session, "target", role_name="super_admin", previous_role_name="finance_like")
    with Session() as db:
        helper = db.query(Role.id).filter(Role.name == "helper").scalar()

    # One restores the previous role, the other chooses another one: exactly one of them happens.
    results = in_threads(2, lambda i: revoke(Session, actors[i], target, None if i == 0 else helper))
    assert sorted(results) == sorted(["revoked", "NOT_SUPER_ADMIN"]), results
    name, kept = role_of(Session, target)
    assert kept is None and name == ("finance_like" if results[0] == "revoked" else "helper")
    with Session() as db:
        assert db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_SUPER_ADMIN_REVOKED).count() == 1
        assert db.get(User, target).security_version == 1                 # its sessions ended once


def test_two_super_admins_promoting_the_same_account_at_once_keep_its_real_previous_role(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "upgrade")                              # the Super Admin role
    roles(Session, "user", "moderator_like")
    actors = [seed(Session, "a", role_name="super_admin"), seed(Session, "b", role_name="super_admin")]
    target = seed(Session, "target", role_name="moderator_like")

    results = in_threads(2, lambda i: grant(Session, actors[i], target))
    assert sorted(results) == sorted(["granted", "ALREADY_SUPER_ADMIN"]), results
    # The second grant never wrote the Super Admin role down as the 'previous' one.
    assert role_of(Session, target) == ("super_admin", "moderator_like")
    assert revoke(Session, actors[0], target) == "revoked"
    assert role_of(Session, target) == ("moderator_like", None)


def test_a_replacement_role_cannot_be_deleted_while_it_is_being_given(pg):
    engine, Session = pg
    migrate(engine, MIGRATION, "upgrade")                              # the Super Admin role
    roles(Session, "user", "helper")
    boss = seed(Session, "boss", role_name="super_admin")
    target = seed(Session, "target", role_name="super_admin")
    with Session() as db:
        helper = db.query(Role.id).filter(Role.name == "helper").scalar()

    def delete_helper(_i):
        with Session() as db:
            try:
                db.query(Role).filter(Role.id == helper).delete()
                db.commit()
                return "deleted"
            except Exception:  # noqa: BLE001 - the foreign key refuses it once the role is in use
                db.rollback()
                return "kept"

    results = in_threads(2, lambda i: revoke(Session, boss, target, helper) if i == 0 else delete_helper(i))
    name, _kept = role_of(Session, target)
    # Either the revocation won (the role is in use and stays) or the deletion did (the revocation is
    # refused and the account is still a Super Admin). Never an account on a role that is gone.
    assert results in (["revoked", "kept"], ["REPLACEMENT_ROLE_NOT_FOUND", "deleted"]), results
    assert name == ("helper" if results[0] == "revoked" else "super_admin")
