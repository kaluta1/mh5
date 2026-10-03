"""External creative links: a dead link removes the entry from its contest.

No test contacts a real provider: the HTTP layer (`_http_status`) is faked.
All users, contests and entries are SYNTHETIC.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import requests

from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.contests import Contestant
from app.models.round import Round, RoundStatus
from app.models.voting import ContestantVoting
from app.services import creative_link_check as clc
from app.services.creative_link_check import LinkStatus
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import TODAY, contest, person

YT = "https://youtu.be/AAAAAAAAAAA"
YT2 = "https://www.youtube.com/watch?v=BBBBBBBBBBB"
NOW = datetime(2026, 10, 10, 9, 0, 0)


class FakeProvider:
    """Maps a video identifier found in the oEmbed URL to an HTTP status or an exception."""

    def __init__(self, default=200):
        self.default = default
        self.answers = {}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        for key, answer in self.answers.items():
            if key in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        if isinstance(self.default, Exception):
            raise self.default
        return self.default


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(clc, "_http_status", fake)
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_ENABLED", True)
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_CYCLE_HOURS", 1)       # every entry in every run
    monkeypatch.setattr(settings, "CREATIVE_LINK_CONFIRM_AFTER_HOURS", 12)
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_BATCH_SIZE", 40)
    return fake


def _round(db, c, status=RoundStatus.ACTIVE, voting_end=None):
    rnd = Round(name="R", contest_id=c.id, status=status, submission_start_date=TODAY.replace(day=1),
                submission_end_date=TODAY + timedelta(days=20), voting_end_date=voting_end)
    db.add(rnd)
    db.commit()
    return rnd


def _entry(db, c, rnd, url=YT, owner=None, **cols):
    owner = owner or person(db, 30)
    row = Contestant(user_id=owner.id, season_id=c.id, round_id=rnd.id, title="Entry", description="d",
                     entry_type="nomination", country=owner.country, nominator_country=owner.country,
                     video_media_ids=cols.pop("video_media_ids", json.dumps([url])),
                     is_active=True, is_qualified=True,
                     **{"is_deleted": False, "verification_status": "pending", **cols})
    db.add(row)
    db.commit()
    return row


def _events(db, entry_id):
    return [a.action for a in db.query(AuditTrail)
            .filter(AuditTrail.table_name == "contestants", AuditTrail.record_id == entry_id)
            .order_by(AuditTrail.id).all()]


# ---------------------------------------------------------------------------
# classification of provider answers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [404, 410])
def test_not_found_and_gone_are_definitively_dead(provider, code):
    provider.default = code
    assert clc.check_url(YT).status == LinkStatus.DEAD


@pytest.mark.parametrize("answer", [
    requests.Timeout("slow"),
    requests.ConnectionError("dns"),
    RuntimeError("unexpected"),
    401, 403, 429, 500, 502, 503, 301, 302, 400, 204,
])
def test_transient_or_ambiguous_answers_are_never_dead(provider, answer):
    provider.default = answer
    result = clc.check_url(YT)
    assert result.status == LinkStatus.UNKNOWN
    assert clc.check_entry_links(json.dumps([YT])).status == LinkStatus.UNKNOWN


def test_available_link(provider):
    assert clc.check_url(YT).status == LinkStatus.AVAILABLE


def test_only_fixed_provider_hosts_are_ever_contacted(provider):
    for url in (YT, YT2, "https://vimeo.com/123456789",
                "https://www.tiktok.com/@some.user/video/7234567890123456789"):
        assert clc.check_url(url).status == LinkStatus.AVAILABLE
    assert len(provider.calls) == 4
    for called in provider.calls:
        assert called.startswith(("https://www.youtube.com/oembed?", "https://vimeo.com/api/oembed.json?",
                                  "https://www.tiktok.com/oembed?"))


@pytest.mark.parametrize("url", [
    "https://evil.example/video.mp4",                     # direct file on an arbitrary host
    "http://169.254.169.254/latest/meta-data",            # internal address
    "http://localhost:8001/health",
    "https://www.facebook.com/watch?v=123456",            # no safe public check
    "https://www.tiktok.com/t/ZTshort",                   # short link: no validated id
    "https://youtu.be/short",                             # malformed id
    "https://user:pw@www.youtube.com/watch?v=AAAAAAAAAAA",
    "ftp://youtube.com/watch?v=AAAAAAAAAAA",
    "not a url",
])
def test_unsupported_or_unsafe_urls_are_not_fetched(provider, url):
    assert clc.check_url(url).status == LinkStatus.UNSUPPORTED
    assert provider.calls == []


def test_entry_is_dead_only_when_every_creative_is_dead(provider):
    provider.answers = {"AAAAAAAAAAA": 404, "BBBBBBBBBBB": 200}
    assert clc.check_entry_links(json.dumps([YT])).status == LinkStatus.DEAD
    assert clc.check_entry_links(json.dumps([YT, YT2])).status == LinkStatus.AVAILABLE
    # a hosted video or an uncheckable link next to a dead one keeps the entry
    assert clc.check_entry_links(json.dumps([YT, "/api/v1/media/file/1/v.mp4"])).status == LinkStatus.UNKNOWN
    assert clc.check_entry_links(json.dumps([YT, "https://evil.example/v.mp4"])).status == LinkStatus.UNKNOWN
    # stored values are sometimes JSON-encoded twice
    assert clc.check_entry_links(json.dumps([json.dumps([YT])])).status == LinkStatus.DEAD
    assert clc.check_entry_links(None).status == LinkStatus.UNSUPPORTED


def test_submission_check_is_off_when_disabled(provider, monkeypatch):
    provider.default = 404
    assert clc.submission_link_is_dead(json.dumps([YT])) is True
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_ENABLED", False)
    assert clc.submission_link_is_dead(json.dumps([YT])) is False


# ---------------------------------------------------------------------------
# periodic recheck: confirmation, idempotency, safety valves
# ---------------------------------------------------------------------------

def test_two_dead_results_apart_remove_the_entry_and_keep_its_history(db, provider):
    c = contest(db, "nomination")
    rnd = _round(db, c)
    row = _entry(db, c, rnd)
    voter = person(db, 30)
    db.add(ContestantVoting(user_id=voter.id, contestant_id=row.id, contest_id=c.id, season_id=c.id, position=1,
                            points=5, vote_bucket_key=f"contest:{c.id}"))
    db.commit()
    provider.default = 404

    first = clc.run_link_recheck(db, now=NOW)
    assert (first["suspected"], first["removed"]) == (1, 0)
    db.refresh(row)
    assert row.verification_status == "pending"          # one result never removes anything

    # Re-running within the confirmation delay changes nothing (idempotent).
    again = clc.run_link_recheck(db, now=NOW + timedelta(hours=1))
    assert (again["suspected"], again["removed"]) == (0, 0)
    assert _events(db, row.id) == ["CREATIVE_LINK_SUSPECT"]

    second = clc.run_link_recheck(db, now=NOW + timedelta(hours=13))
    assert second["removed"] == 1
    db.refresh(row)
    assert row.verification_status == "creative_unavailable"
    assert _events(db, row.id) == ["CREATIVE_LINK_SUSPECT", "CREATIVE_LINK_REMOVED"]
    removal = db.query(AuditTrail).filter(AuditTrail.action == "CREATIVE_LINK_REMOVED").one()
    assert removal.old_values == {"verification_status": "pending"}          # what an admin needs to restore it

    # Logical removal: the row, its votes and its fields are intact.
    assert row.is_deleted is False and row.is_active is True and row.video_media_ids == json.dumps([YT])
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == row.id).count() == 1

    # A removed entry is no longer a candidate: later runs are no-ops.
    later = clc.run_link_recheck(db, now=NOW + timedelta(hours=40))
    assert later["candidates"] == 0 and _events(db, row.id)[-1] == "CREATIVE_LINK_REMOVED"


@pytest.mark.parametrize("answer", [requests.Timeout("slow"), 429, 500, 503, 403, requests.ConnectionError("net")])
def test_transient_failures_never_suspect_or_remove(db, provider, answer):
    c = contest(db, "nomination")
    row = _entry(db, c, _round(db, c))
    provider.default = answer
    for hours in (0, 13, 26, 39):
        summary = clc.run_link_recheck(db, now=NOW + timedelta(hours=hours))
        assert (summary["suspected"], summary["removed"], summary["unknown"]) == (0, 0, 1)
    db.refresh(row)
    assert row.verification_status == "pending" and _events(db, row.id) == []


def test_a_transient_failure_between_two_dead_results_does_not_confirm(db, provider):
    c = contest(db, "nomination")
    row = _entry(db, c, _round(db, c))
    provider.default = 404
    clc.run_link_recheck(db, now=NOW)
    provider.default = requests.Timeout("slow")
    clc.run_link_recheck(db, now=NOW + timedelta(hours=13))
    db.refresh(row)
    assert row.verification_status == "pending" and _events(db, row.id) == ["CREATIVE_LINK_SUSPECT"]


def test_a_successful_check_clears_the_suspicion(db, provider):
    c = contest(db, "nomination")
    row = _entry(db, c, _round(db, c))
    provider.default = 404
    clc.run_link_recheck(db, now=NOW)
    provider.default = 200
    cleared = clc.run_link_recheck(db, now=NOW + timedelta(hours=13))
    assert cleared["cleared"] == 1
    provider.default = 404
    clc.run_link_recheck(db, now=NOW + timedelta(hours=26))     # a NEW first strike, not a confirmation
    db.refresh(row)
    assert row.verification_status == "pending"
    assert _events(db, row.id) == ["CREATIVE_LINK_SUSPECT", "CREATIVE_LINK_OK", "CREATIVE_LINK_SUSPECT"]


def test_a_batch_that_looks_mostly_dead_is_ignored_as_an_anomaly(db, provider):
    c = contest(db, "nomination")
    rnd = _round(db, c)
    rows = [_entry(db, c, rnd, url=f"https://youtu.be/{chr(65 + i) * 11}") for i in range(6)]
    provider.default = 404
    for hours in (0, 13):
        summary = clc.run_link_recheck(db, now=NOW + timedelta(hours=hours))
        assert summary["aborted"] is True and summary["suspected"] == 0 and summary["removed"] == 0
    for row in rows:
        db.refresh(row)
        assert row.verification_status == "pending" and _events(db, row.id) == []


def test_only_public_entries_of_running_rounds_are_rechecked(db, provider):
    c = contest(db, "nomination")
    running = _round(db, c)
    finished = _round(db, c, status=RoundStatus.COMPLETED)
    ended = _round(db, c, voting_end=TODAY - timedelta(days=400))
    live = _entry(db, c, running)
    _entry(db, c, finished, url=YT2)                                   # completed round
    _entry(db, c, ended, url="https://youtu.be/CCCCCCCCCCC")           # voting ended long ago
    _entry(db, c, running, url="https://youtu.be/DDDDDDDDDDD", verification_status="rejected")
    _entry(db, c, running, url="https://youtu.be/EEEEEEEEEEE", is_deleted=True)
    _entry(db, c, running, video_media_ids=json.dumps(["/api/v1/media/file/1/v.mp4"]))   # hosted only
    summary = clc.run_link_recheck(db, now=datetime.combine(TODAY, datetime.min.time()))
    assert summary["candidates"] == 1
    assert [u for u in provider.calls if "AAAAAAAAAAA" in u] and len(provider.calls) == 1
    assert live.verification_status == "pending"


def test_the_run_is_bounded_and_rotates(db, provider, monkeypatch):
    c = contest(db, "nomination")
    rnd = _round(db, c)
    for i in range(12):
        _entry(db, c, rnd, url=f"https://youtu.be/{chr(97 + i) * 11}")
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_BATCH_SIZE", 5)
    assert clc.run_link_recheck(db, now=NOW)["candidates"] == 5
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_BATCH_SIZE", 40)
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_CYCLE_HOURS", 4)
    seen = sum(clc.run_link_recheck(db, now=NOW + timedelta(hours=h))["candidates"] for h in range(4))
    assert seen == 12                                              # each entry exactly once per cycle


def test_disabled_recheck_does_nothing(db, provider, monkeypatch):
    c = contest(db, "nomination")
    _entry(db, c, _round(db, c))
    monkeypatch.setattr(settings, "CREATIVE_LINK_CHECK_ENABLED", False)
    provider.default = 404
    summary = clc.run_link_recheck(db, now=NOW)
    assert summary["enabled"] is False and summary["candidates"] == 0 and provider.calls == []


def test_scheduler_is_registered_with_the_existing_manager():
    from app.services.scheduler_manager import scheduler_manager

    assert "creative-links" in scheduler_manager.list_tasks()


# ---------------------------------------------------------------------------
# a removed entry is out of the roster, count, detail, voting and ranking
# ---------------------------------------------------------------------------

def test_removed_entry_disappears_everywhere_and_an_admin_can_restore_it(client, db, provider):
    from app.services import participation_safety as ps
    from app.services.entry_exposure import owner_entry_status

    c = contest(db, "nomination")
    rnd = _round(db, c)
    owner = person(db, 30)
    row = _entry(db, c, rnd, owner=owner)
    listing = client.get(f"/api/v1/contestants/contest/{c.id}", params={"roundId": rnd.id})
    assert [r["id"] for r in listing.json()] == [row.id]
    assert ps.participation_decision(db, row).eligible is True

    provider.default = 404
    clc.run_link_recheck(db, now=NOW)
    clc.run_link_recheck(db, now=NOW + timedelta(hours=13))
    db.expire_all()
    row = db.query(Contestant).get(row.id)

    assert client.get(f"/api/v1/contestants/contest/{c.id}", params={"roundId": rnd.id}).json() == []
    detail = client.get(f"/api/v1/contests/{c.id}", params={"roundId": rnd.id, "entryType": "nomination",
                                                           "rosterOnly": "true"}).json()
    assert detail["contestants"] == [] and detail["entries_count"] == 0
    stranger = person(db, 30)
    assert client.get(f"/api/v1/contestants/{row.id}", headers=auth(stranger)).status_code == 404
    assert client.post(f"/api/v1/contestants/{row.id}/vote", headers=auth(stranger)).status_code != 200
    decision = ps.participation_decision(db, row)
    assert decision.eligible is False and ps.Reason.REMOVED in decision.reasons      # ranking / progression
    assert owner_entry_status(db, row) == "CREATIVE_UNAVAILABLE"
    assert client.get(f"/api/v1/contestants/{row.id}", headers=auth(owner)).status_code == 200   # owner still sees it

    # Restoration is an explicit administrator action; a later good check alone restores nothing.
    provider.default = 200
    clc.run_link_recheck(db, now=NOW + timedelta(hours=40))
    db.expire_all()
    assert db.query(Contestant).get(row.id).verification_status == "creative_unavailable"
    admin = person(db, 40, admin=True)
    assert client.post(f"/api/v1/admin/contestants/{row.id}/approve", headers=auth(admin)).status_code == 200
    assert [r["id"] for r in client.get(f"/api/v1/contestants/contest/{c.id}",
                                        params={"roundId": rnd.id}).json()] == [row.id]
