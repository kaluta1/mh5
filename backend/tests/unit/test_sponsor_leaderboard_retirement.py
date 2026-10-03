"""The old sponsor leaderboard is retired (management decision, 2026-10-03).

It ranked sponsors by direct KYC / Founding Membership referrals and is not
part of the current business model. Its two routes were public and returned
sponsors' names, e-mail addresses and locations; they now answer 410 Gone.

Nothing else called "leaderboard" or "leaders" is affected: contest
leaderboards, Top High5 and MyHigh5 Leaders are different features.

All users are SYNTHETIC.
"""
from __future__ import annotations

import pytest

from app.crud import user as crud_user
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import person

RETIRED = ["/api/v1/affiliates/leaderboard", "/api/v1/affiliates/leaderboard/mfm"]


def _paths(app):
    return {getattr(r, "path", "") for r in app.routes}


@pytest.mark.parametrize("path", RETIRED)
def test_sponsor_leaderboard_routes_are_gone_for_everyone(client, db, path):
    sponsor = person(db, 30, email_verified=True)
    person(db, 30, sponsor_id=sponsor.id)
    for headers in ({}, auth(sponsor), auth(person(db, 40, admin=True))):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 410, resp.text
        body = resp.text
        assert "retired" in body.lower()
        # No sponsor data of any kind leaves the server.
        assert sponsor.email not in body and sponsor.username not in body
        assert "referrals_count" not in body and "avatar_url" not in body
        assert not isinstance(resp.json(), list)


def test_sponsor_ranking_queries_are_removed():
    assert not hasattr(crud_user, "get_top_sponsors")
    assert not hasattr(crud_user, "get_top_mfm_sponsors")


def test_other_ranking_features_are_still_routed(app):
    paths = _paths(app)
    # Top High5 and contest rankings
    assert "/api/v1/seasons/top-high5" in paths
    assert "/api/v1/contestants/leaderboard/contest/{contest_id}" in paths
    # MyHigh5 Leaders (a separate programme)
    assert "/api/v1/leaders/me" in paths and "/api/v1/leaders/periods" in paths
    # Direct affiliate features
    for p in ("/api/v1/affiliates/stats", "/api/v1/affiliates/commissions", "/api/v1/affiliates/commissions/stats"):
        assert p in paths, p


def test_top_high5_contest_leaderboard_leaders_and_affiliate_endpoints_still_answer(client, db):
    member = person(db, 30, email_verified=True)
    # Top High5 is alive: it asks for a country instead of saying "gone".
    top = client.get("/api/v1/seasons/top-high5")
    assert top.status_code not in (404, 410), top.text
    # Contest leaderboard is alive: an unknown contest is "not found", not "gone".
    assert client.get("/api/v1/contestants/leaderboard/contest/999999").status_code != 410
    # MyHigh5 Leaders
    assert client.get("/api/v1/leaders/periods", headers=auth(member)).status_code == 200
    assert client.get("/api/v1/leaders/me", headers=auth(member)).status_code == 200
    # Direct affiliate
    stats = client.get("/api/v1/affiliates/stats", headers=auth(member))
    assert stats.status_code == 200 and stats.json()["direct_referrals"] == 0
    assert client.get("/api/v1/affiliates/commissions", headers=auth(member)).status_code == 200
