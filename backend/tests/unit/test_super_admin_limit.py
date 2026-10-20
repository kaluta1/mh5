"""At most five Super Admins (super_admin.MAX_SUPER_ADMINS).

  1. a Super Admin can promote administrators until five accounts hold the
     role; a sixth grant is refused, audited, and changes nothing;
  2. every account on the role takes a seat, switched off or not, so
     switching one back on never makes a sixth;
  3. a Super Admin demoted to a plain administrator keeps the account, the
     password, the profile and everything else; only the role changes;
  4. nobody but a Super Admin can make a Super Admin, by any path, not even
     themselves;
  5. the last Super Admin cannot be removed;
  6. the bootstrap tool never names more than five.

Every account and password is SYNTHETIC.
"""
from __future__ import annotations

import pytest

from app.core.security import verify_password
from app.models.accounting import AuditTrail
from app.models.user import Role, User
from app.scripts import bootstrap_super_admins as bootstrap
from app.services import admin_security as sec
from app.services import password_exposure
from app.services import super_admin as sa
from tests.unit.test_admin_security_hardening import PASSWORD, bearer, code_of, denials, person  # noqa: F401
from tests.unit.test_super_admin import audits, base_role, set_super, super_role, superadmin

pytestmark = pytest.mark.unit

# What a demotion may change on the account; every other column must stay as it was.
ROLE_COLUMNS = {"role_id", "role_before_super_admin_id", "security_version", "updated_at"}


def snapshot(db, user_id) -> dict:
    db.expire_all()
    row = db.get(User, user_id)
    return {c.name: getattr(row, c.name) for c in User.__table__.columns if c.name not in ROLE_COLUMNS}


def seats(client, actor) -> dict:
    data = client.get("/api/v1/admin/super-admins", headers=bearer(actor)).json()
    return {k: data[k] for k in ("can_manage", "can_grant", "max_super_admins", "seats_used")}


def test_the_limit_is_five():
    assert sa.MAX_SUPER_ADMINS == 5


def test_a_super_admin_promotes_up_to_five_and_a_sixth_is_refused(client, db):
    base = base_role(db)
    boss = superadmin(db, "boss")
    candidates = [person(db, f"admin{i}", admin=True) for i in range(5)]
    assert seats(client, boss) == {"can_manage": True, "can_grant": True, "max_super_admins": 5, "seats_used": 1}

    for i, target in enumerate(candidates[:4]):
        done = set_super(client, boss, target, True)
        assert done.status_code == 200 and done.json()["is_super_admin"] is True, done.text
        assert seats(client, boss)["seats_used"] == i + 2
    assert sec.active_super_admin_ids(db) == sorted([boss.id] + [c.id for c in candidates[:4]])
    assert seats(client, boss) == {"can_manage": True, "can_grant": False, "max_super_admins": 5, "seats_used": 5}

    sixth = candidates[4]
    before = snapshot(db, sixth.id), db.get(User, sixth.id).role_id
    refused = set_super(client, boss, sixth, True)
    assert (refused.status_code, code_of(refused)) == (409, sec.SUPER_ADMIN_LIMIT_REACHED)
    assert "at most 5" in refused.json()["detail"]["message"]
    assert (snapshot(db, sixth.id), db.get(User, sixth.id).role_id) == before
    assert not sa.is_super_admin(db.get(User, sixth.id))
    assert len(audits(db, sec.AUDIT_SUPER_ADMIN_GRANTED)) == 4
    assert denials(db)[-1] == (boss.id, sixth.id, "grant super admin", sec.SUPER_ADMIN_LIMIT_REACHED)
    # Any of the five meets the same limit.
    assert code_of(set_super(client, candidates[0], sixth, True)) == sec.SUPER_ADMIN_LIMIT_REACHED

    # A seat freed by a revocation can be given again.
    assert set_super(client, boss, candidates[3], False, replacement=base.id).status_code == 200
    assert seats(client, boss)["can_grant"] is True
    assert set_super(client, boss, sixth, True).status_code == 200
    assert len(sec.active_super_admin_ids(db)) == 5


def test_the_limit_is_checked_after_the_password_and_the_actor(client, db):
    base_role(db)
    boss = superadmin(db, "boss")
    for i in range(4):
        superadmin(db, f"full{i}")
    plain = person(db, "plain", admin=True)
    target = person(db, "target", admin=True)
    # The limit is no way to probe: without being a Super Admin, or without the password, that is the answer.
    assert code_of(set_super(client, plain, target, True)) == sec.SUPER_ADMIN_REQUIRED
    assert code_of(set_super(client, boss, target, True, password="wrong")) == "REAUTH_REQUIRED"
    assert code_of(set_super(client, boss, target, True)) == sec.SUPER_ADMIN_LIMIT_REACHED
    # Already one: that is said first, whatever the count.
    assert code_of(set_super(client, boss, db.query(User).filter(User.username == "full0").one(), True)) \
        == "ALREADY_SUPER_ADMIN"


def test_an_account_switched_off_keeps_its_seat_so_switching_it_on_never_makes_a_sixth(client, db):
    base_role(db)
    boss = superadmin(db, "boss")
    colleague = superadmin(db, "colleague")
    resting = superadmin(db, "resting", active=False)                  # on the role, switched off
    for i in range(2):
        superadmin(db, f"other{i}")
    target = person(db, "target", admin=True)
    assert len(sec.active_super_admin_ids(db)) == 4
    assert seats(client, boss)["seats_used"] == 5

    refused = set_super(client, boss, target, True)
    assert code_of(refused) == sec.SUPER_ADMIN_LIMIT_REACHED
    # Switching it back on is allowed (a Super Admin does it) and still makes five, not six.
    switched = client.put(f"/api/v1/admin/users/{resting.id}/status", headers=bearer(colleague),
                          json={"is_active": True, "current_password": PASSWORD})
    assert switched.status_code == 200, switched.text
    assert len(sec.active_super_admin_ids(db)) == 5
    # Revoking the account that is switched off frees its seat.
    db.query(User).filter(User.id == resting.id).update({"is_active": False})
    db.commit()
    assert set_super(client, boss, resting, False, replacement=base_role(db).id).status_code == 200
    assert set_super(client, boss, target, True).status_code == 200
    assert seats(client, boss)["seats_used"] == 5


def test_a_super_admin_demoted_to_administrator_keeps_everything_but_the_role(client, db):
    base_role(db)
    admin_role = Role(name="admin", description="Administrator", is_system=True)
    db.add(admin_role)
    db.commit()
    boss = superadmin(db, "boss")
    target = person(db, "target", admin=True, role=admin_role, first_name="Ada", last_name="Lovelace",
                    city="London", country="GB", phone_number="+440000000000",
                    usdt_wallet_address="0x" + "1" * 40)
    unrelated = person(db, "unrelated", admin=True, role=admin_role)
    keep_target, keep_boss, keep_unrelated = (snapshot(db, target.id), snapshot(db, boss.id),
                                              snapshot(db, unrelated.id))
    roles_before = [(r.id, r.name, r.is_system, r.inherit_from_id) for r in db.query(Role).order_by(Role.id)]

    assert set_super(client, boss, target, True).status_code == 200
    done = set_super(client, boss, target, False)                        # back to its previous role: admin
    assert done.status_code == 200 and done.json() == {"id": target.id, "is_super_admin": False,
                                                       "role_id": admin_role.id, "role": "admin"}
    db.expire_all()
    demoted = db.get(User, target.id)
    assert (demoted.role_id, demoted.role_before_super_admin_id, demoted.is_admin) == (admin_role.id, None, True)
    assert sec.is_administrator(demoted) and not sa.is_super_admin(demoted)
    assert not sec.has_permission(demoted, sec.PERMISSION_MANAGE_ADMINS)
    assert demoted.security_version == 1                                 # its Super Admin sessions ended
    # The password, the profile, the wallet and every other column are untouched; so are other accounts.
    assert snapshot(db, target.id) == keep_target
    assert snapshot(db, boss.id) == keep_boss and snapshot(db, unrelated.id) == keep_unrelated
    assert db.get(User, unrelated.id).role_id == admin_role.id
    assert [(r.id, r.name, r.is_system, r.inherit_from_id) for r in db.query(Role).order_by(Role.id)] == roles_before
    # Its own password still works.
    assert verify_password(PASSWORD, demoted.hashed_password)


def test_no_one_but_a_super_admin_makes_a_super_admin_by_any_path(client, db):
    role = super_role(db)
    boss = superadmin(db, "boss")
    # The strongest ordinary administrator there is: every grantable permission, 'all' included.
    strong = person(db, "strong", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS, "manage_users",
                                                            "manage_roles", "all"))
    plain = person(db, "plain", admin=True)
    member = person(db, "member")
    seats_before = sec.super_admin_holder_ids(db)

    for actor in (strong, plain):
        for target in (actor, plain if actor is strong else strong, member):
            refused = set_super(client, actor, target, True)
            assert (refused.status_code, code_of(refused)) == (403, sec.SUPER_ADMIN_REQUIRED)
    assert set_super(client, member, member, True).status_code == 403
    # The role management API: the Super Admin role cannot be handed out, inherited or renamed into.
    for actor in (strong, plain):
        for target in (actor, member):
            assigned = client.post("/api/v1/rbac/users/assign-role", headers=bearer(actor),
                                   json={"user_id": target.id, "role_id": role.id})
            assert assigned.status_code in (403, 409), assigned.text
    child = client.post("/api/v1/rbac/roles", headers=bearer(strong),
                        json={"name": "almost_super", "inherit_from_id": role.id})
    assert child.status_code in (403, 409), child.text
    renamed = client.post("/api/v1/rbac/roles", headers=bearer(strong), json={"name": "super_admin"})
    assert renamed.status_code in (400, 403, 409), renamed.text
    # Their own profile cannot carry a role or the administrator flag.
    for field in ({"role_id": role.id}, {"is_admin": True}):
        changed = client.put("/api/v1/users/me", headers=bearer(member), json=field)
        assert changed.status_code == 422, (field, changed.text)

    db.expire_all()
    assert sec.super_admin_holder_ids(db) == seats_before == [boss.id]
    assert db.get(User, member.id).is_admin is False
    assert audits(db, sec.AUDIT_SUPER_ADMIN_GRANTED) == []


def test_the_last_super_admin_cannot_be_removed(client, db):
    base_role(db)
    owner = superadmin(db, "owner")
    strong = person(db, "strong", admin=True, permissions=(sec.PERMISSION_MANAGE_ADMINS, "all"))
    keep = snapshot(db, owner.id)

    own = set_super(client, owner, owner, False, replacement=base_role(db).id)
    assert (own.status_code, code_of(own)) == (403, "SELF_ACTION_FORBIDDEN")
    assert code_of(set_super(client, strong, owner, False)) == sec.SUPER_ADMIN_REQUIRED
    flag = client.put(f"/api/v1/admin/users/{owner.id}/role", headers=bearer(strong),
                      json={"is_admin": False, "current_password": PASSWORD})
    assert (flag.status_code, code_of(flag)) == (409, "SUPER_ADMIN_PROTECTED")
    off = client.put(f"/api/v1/admin/users/{owner.id}/status", headers=bearer(strong),
                     json={"is_active": False, "current_password": PASSWORD})
    assert (off.status_code, code_of(off)) == (403, sec.SUPER_ADMIN_REQUIRED)
    self_off = client.put(f"/api/v1/admin/users/{owner.id}/status", headers=bearer(owner),
                          json={"is_active": False, "current_password": PASSWORD})
    assert self_off.status_code == 403
    # Even a direct call with a second Super Admin on the books but switched off: the owner stays.
    resting = superadmin(db, "resting", active=False)
    with pytest.raises(sec.AdminSecurityError) as refused:
        sec.refuse_removing_last_super_admin(db, resting, target=db.get(User, owner.id), attempted="test")
    assert refused.value.code == "LAST_SUPER_ADMIN"

    db.expire_all()
    assert sec.active_super_admin_ids(db) == [owner.id]
    assert sa.is_super_admin(db.get(User, owner.id)) and snapshot(db, owner.id) == keep
    assert audits(db, sec.AUDIT_SUPER_ADMIN_REVOKED) == []


def test_the_bootstrap_tool_names_at_most_five(db, monkeypatch):
    super_role(db)
    accounts = [(person(db, f"boot{i}", admin=True).id, f"boot{i}@example.com") for i in range(6)]
    monkeypatch.setattr(password_exposure, "loaded_count", lambda _db: 1)
    with pytest.raises(bootstrap.BootstrapError, match="at most 5"):
        bootstrap.bootstrap(db, accounts, apply=True)
    assert sec.super_admin_holder_ids(db) == []
    assert db.query(AuditTrail).filter(AuditTrail.action == sec.AUDIT_SUPER_ADMIN_BOOTSTRAP).count() == 0
    named = bootstrap.bootstrap(db, accounts[:5], apply=True)
    assert len(named) == 5 and len(sec.super_admin_holder_ids(db)) == 5
