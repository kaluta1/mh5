"""Super Admin keeps ordinary member access (permanent RBAC rule).

The Super Admin role adds administrative privileges; it never removes what an ordinary member may
do. Every authenticated member read (GET, no path parameter, outside the admin and staff prefixes)
answers a Super Admin exactly as it answers an ordinary member, each with their own data, while
the administrative routes stay closed to the member and to anonymous callers.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.unit.test_admin_security_hardening import bearer, person
from tests.unit.test_super_admin import superadmin

pytestmark = pytest.mark.unit

ADMIN_PREFIXES = ("/api/v1/admin", "/api/v1/rbac", "/api/v1/roles", "/api/v1/kyc/admin", "/api/v1/finance")


def member_reads(app) -> list[str]:
    paths = set()
    for route in app.routes:
        if (isinstance(route, APIRoute) and "GET" in route.methods and route.path.startswith("/api/v1/")
                and "{" not in route.path and "/admin" not in route.path
                and not route.path.startswith(ADMIN_PREFIXES)):
            paths.add(route.path)
    return sorted(paths)


def test_a_super_admin_gets_every_member_read_an_ordinary_member_gets(app, client, db):
    member, boss = person(db, "plainmember"), superadmin(db, "ownerboss")
    tolerant = TestClient(app, raise_server_exceptions=False)    # same app and test database as `client`
    refused = []
    for path in member_reads(app):
        as_member = tolerant.get(path, headers=bearer(member)).status_code
        as_boss = tolerant.get(path, headers=bearer(boss)).status_code
        if as_member < 400 and as_boss >= 400:
            refused.append((path, as_member, as_boss))
    assert refused == []


def test_a_super_admin_sees_their_own_member_account(client, db):
    member, boss = person(db, "plainmember"), superadmin(db, "ownerboss")
    for user in (member, boss):
        me = client.get("/api/v1/users/me", headers=bearer(user))
        assert me.status_code == 200 and me.json()["id"] == user.id


def test_the_member_referral_pool_reads_answer_a_super_admin_with_their_own_data(client, db):
    boss = superadmin(db, "ownerboss")
    for path in ("/api/v1/referral-pool/me", "/api/v1/referral-pool/units/eligibility",
                 "/api/v1/referral-pool/units/purchases", "/api/v1/referral-pool/units/assignments"):
        assert client.get(path, headers=bearer(boss)).status_code == 200, path


def test_administrative_routes_stay_closed_to_members_and_anonymous_callers(client, db):
    member = person(db, "plainmember")
    for path in ("/api/v1/admin/super-admins", "/api/v1/admin/users", "/api/v1/admin/referral-pool/overview"):
        assert client.get(path, headers=bearer(member)).status_code == 403, path
        assert client.get(path).status_code == 401, path
    assert client.get("/api/v1/referral-pool/units/dashboard").status_code == 401
