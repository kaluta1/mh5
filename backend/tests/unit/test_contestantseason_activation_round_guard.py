"""
Regression tests for the writer paths that could UNDO the production
ContestantSeason repair (see KALUTASOCIETY_CONTESTANTSEASON_REPAIR_APPLICATION_
IMPACT_REPORT).

The repair deactivates foreign-round, same-level ContestantSeason rows. Before
this fix three writers could recreate them:

1. SeasonMigrationService._ensure_source_season_links -- called on every
   promotion attempt (the in-process scheduler retries hundreds of stuck
   source seasons hourly) -- picked candidates from voters OR from the legacy
   Contestant.season_id == contest_id fallback, which spans every round of the
   contest, and then reactivated/created their membership through the shared
   helper. That helper deactivates the contestant's OTHER active same-level
   memberships, i.e. it would displace the valid home-round membership.
2. Admin "update contestant" (PUT /admin/contestants/{id}) reactivated any
   existing ContestantSeason of a newly chosen season with no round check.
3. migrate_to_city_season linked every active contestant of the contest, in
   any round, into the round's CITY season.

Invariant now enforced by ONE rule
(SeasonMigrationService.contestant_season_round_conflict): a contestant may only
be activated in a season of its own round; an unknown round on either side fails
closed.
"""
from __future__ import annotations

import asyncio
import pathlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    Contestant,
    ContestantSeason,
    SeasonLevel,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.services.season_migration import (
    ForeignRoundActivationError,
    SeasonMigrationService,
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def _user(db, suffix: str) -> User:
    user = User(email=f"round-guard-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str) -> Round:
    rnd = Round(name=f"Round {suffix}", status=RoundStatus.ACTIVE)
    db.add(rnd)
    db.flush()
    return rnd


def _contest(db, suffix: str) -> Contest:
    contest = Contest(
        name=f"Contest {suffix}", contest_type="t", contest_mode="nomination", level="continent"
    )
    db.add(contest)
    db.flush()
    return contest


def _season(db, rnd, contest, level: SeasonLevel, suffix: str) -> ContestSeason:
    """rnd=None builds a legacy season with no round."""
    if rnd is not None:
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(
        round_id=rnd.id if rnd is not None else None, title=f"Season {suffix}", level=level
    )
    db.add(season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.flush()
    return season


def _contestant(db, *, suffix: str, rnd, contest) -> Contestant:
    """season_id=contest.id reproduces the legacy Contestant.season_id ==
    Contest.id overload that _ensure_source_season_links' fallback relies on."""
    owner = _user(db, suffix)
    c = Contestant(
        user_id=owner.id,
        season_id=contest.id,
        round_id=rnd.id if rnd is not None else None,
        contest_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Kenya",
        region="East Africa",
        continent="Africa",
        title=f"Contestant {suffix}",
    )
    db.add(c)
    db.flush()
    return c


def _membership(db, *, contestant, season, is_active, joined_at=None) -> ContestantSeason:
    m = ContestantSeason(
        contestant_id=contestant.id,
        season_id=season.id,
        is_active=is_active,
        joined_at=joined_at or datetime.utcnow(),
    )
    db.add(m)
    db.flush()
    return m


def _vote(db, *, suffix: str, contestant, contest, season):
    from app.models.voting import ContestantVoting

    voter = _user(db, f"voter-{suffix}")
    db.add(
        ContestantVoting(
            user_id=voter.id,
            contestant_id=contestant.id,
            contest_id=contest.id,
            season_id=season.id,
            vote_bucket_key=f"ty:{contest.contest_type or ''}:{contest.contest_mode or ''}",
            position=1,
            points=5,
        )
    )
    db.flush()


def _state(db, contestant, season) -> bool | None:
    row = (
        db.query(ContestantSeason)
        .filter(ContestantSeason.contestant_id == contestant.id, ContestantSeason.season_id == season.id)
        .first()
    )
    return None if row is None else bool(row.is_active)


def _active_season_ids(db, contestant, level: SeasonLevel) -> list[int]:
    rows = (
        db.query(ContestantSeason.season_id)
        .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
        .filter(
            ContestantSeason.contestant_id == contestant.id,
            ContestantSeason.is_active == True,
            ContestSeason.level == level,
        )
        .all()
    )
    return sorted(r[0] for r in rows)


def _post_repair_fixture(db, suffix: str):
    """The exact production risk: contestant with a valid home-round KEEP
    membership (round A) and a foreign-round membership at round B that the
    repair has already set inactive."""
    contest = _contest(db, suffix)
    home_round, foreign_round = _round(db, f"{suffix}-home"), _round(db, f"{suffix}-foreign")
    home_season = _season(db, home_round, contest, SeasonLevel.CONTINENT, f"{suffix}-home")
    foreign_season = _season(db, foreign_round, contest, SeasonLevel.CONTINENT, f"{suffix}-foreign")
    contestant = _contestant(db, suffix=suffix, rnd=home_round, contest=contest)
    _membership(db, contestant=contestant, season=home_season, is_active=True)  # KEEP
    _membership(db, contestant=contestant, season=foreign_season, is_active=False)  # repaired
    db.commit()
    return contest, home_round, foreign_round, home_season, foreign_season, contestant


# --------------------------------------------------------------------------
# the single rule
# --------------------------------------------------------------------------
def test_round_conflict_rule_table():
    rule = SeasonMigrationService.contestant_season_round_conflict
    assert rule(3, 3) is None
    assert rule(3, 4) == "ROUND_MISMATCH"
    assert rule(None, 3) == "CONTESTANT_ROUND_UNKNOWN"
    assert rule(3, None) == "SEASON_ROUND_UNKNOWN"
    assert rule(None, None) == "CONTESTANT_ROUND_UNKNOWN"


# --------------------------------------------------------------------------
# TEST 1-3, 6: _ensure_source_season_links vs the repaired foreign membership
# --------------------------------------------------------------------------
def test_1_ensure_source_links_refuses_foreign_round_contestant(db):
    contest, _, _, _, foreign_season, contestant = _post_repair_fixture(db, "t1")

    repaired = SeasonMigrationService._ensure_source_season_links(db, contest.id, foreign_season.id)
    db.commit()

    assert repaired == 0


def test_2_foreign_existing_membership_is_not_reactivated(db):
    contest, _, _, _, foreign_season, contestant = _post_repair_fixture(db, "t2")

    SeasonMigrationService._ensure_source_season_links(db, contest.id, foreign_season.id)
    db.commit()

    assert _state(db, contestant, foreign_season) is False


def test_3_rejecting_foreign_membership_does_not_deactivate_home_keep(db):
    contest, _, _, home_season, foreign_season, contestant = _post_repair_fixture(db, "t3")

    SeasonMigrationService._ensure_source_season_links(db, contest.id, foreign_season.id)
    db.commit()

    assert _state(db, contestant, home_season) is True
    assert _active_season_ids(db, contestant, SeasonLevel.CONTINENT) == [home_season.id]


def test_4_valid_same_round_source_membership_still_works(db):
    contest = _contest(db, "t4")
    rnd = _round(db, "t4")
    season = _season(db, rnd, contest, SeasonLevel.CONTINENT, "t4")
    deactivated = _contestant(db, suffix="t4-a", rnd=rnd, contest=contest)
    _membership(db, contestant=deactivated, season=season, is_active=False)
    missing = _contestant(db, suffix="t4-b", rnd=rnd, contest=contest)
    db.commit()

    repaired = SeasonMigrationService._ensure_source_season_links(db, contest.id, season.id)
    db.commit()

    assert repaired == 2
    assert _state(db, deactivated, season) is True
    assert _state(db, missing, season) is True


def test_5_voter_derived_candidate_from_foreign_round_is_rejected(db):
    contest, _, _, _, foreign_season, foreign_contestant = _post_repair_fixture(db, "t5")
    # a home-round contestant of the FOREIGN season's round, also a voter
    round_b = db.query(Round).filter(Round.id == foreign_season.round_id).one()
    legit = _contestant(db, suffix="t5-legit", rnd=round_b, contest=contest)
    _vote(db, suffix="t5a", contestant=foreign_contestant, contest=contest, season=foreign_season)
    _vote(db, suffix="t5b", contestant=legit, contest=contest, season=foreign_season)
    db.commit()

    repaired = SeasonMigrationService._ensure_source_season_links(db, contest.id, foreign_season.id)
    db.commit()

    assert repaired == 1  # only the contestant that actually belongs to that round
    assert _state(db, foreign_contestant, foreign_season) is False
    assert _state(db, legit, foreign_season) is True


def test_6_legacy_fallback_candidate_from_foreign_round_is_rejected(db):
    contest, _, _, _, foreign_season, foreign_contestant = _post_repair_fixture(db, "t6")
    round_b = db.query(Round).filter(Round.id == foreign_season.round_id).one()
    legit = _contestant(db, suffix="t6-legit", rnd=round_b, contest=contest)  # no votes anywhere
    db.commit()

    repaired = SeasonMigrationService._ensure_source_season_links(db, contest.id, foreign_season.id)
    db.commit()

    assert repaired == 1
    assert _state(db, foreign_contestant, foreign_season) is False
    assert _state(db, legit, foreign_season) is True


# --------------------------------------------------------------------------
# TEST 7: NULL / unknown authoritative round -> fail closed
# --------------------------------------------------------------------------
def test_7a_null_contestant_round_is_not_activated_by_source_repair(db):
    contest = _contest(db, "t7a")
    rnd = _round(db, "t7a")
    season = _season(db, rnd, contest, SeasonLevel.CONTINENT, "t7a")
    orphan = _contestant(db, suffix="t7a", rnd=None, contest=contest)
    db.commit()

    repaired = SeasonMigrationService._ensure_source_season_links(db, contest.id, season.id)
    db.commit()

    assert repaired == 0
    assert _state(db, orphan, season) is None


def test_7b_null_season_round_repairs_nothing(db):
    contest = _contest(db, "t7b")
    rnd = _round(db, "t7b")
    legacy_season = _season(db, None, contest, SeasonLevel.CONTINENT, "t7b-legacy")
    contestant = _contestant(db, suffix="t7b", rnd=rnd, contest=contest)
    db.commit()

    repaired = SeasonMigrationService._ensure_source_season_links(db, contest.id, legacy_season.id)
    db.commit()

    assert repaired == 0
    assert _state(db, contestant, legacy_season) is None


@pytest.mark.parametrize("case", ["contestant_round_null", "season_round_null", "mismatch"])
def test_7c_shared_helper_refuses_and_mutates_nothing(db, case):
    contest = _contest(db, f"t7c-{case}")
    home = _round(db, f"t7c-{case}-home")
    other = _round(db, f"t7c-{case}-other")
    home_season = _season(db, home, contest, SeasonLevel.CONTINENT, f"t7c-{case}-home")
    if case == "contestant_round_null":
        contestant, target = _contestant(db, suffix="t7c1", rnd=None, contest=contest), home_season
    elif case == "season_round_null":
        contestant = _contestant(db, suffix="t7c2", rnd=home, contest=contest)
        target = _season(db, None, contest, SeasonLevel.CONTINENT, "t7c2-legacy")
    else:
        contestant = _contestant(db, suffix="t7c3", rnd=home, contest=contest)
        target = _season(db, other, contest, SeasonLevel.CONTINENT, "t7c3-other")
    keep = _membership(db, contestant=contestant, season=home_season, is_active=True)
    db.commit()

    with pytest.raises(ForeignRoundActivationError):
        SeasonMigrationService._activate_contestant_season_link(db, contestant.id, target.id)
    db.rollback()

    db.refresh(keep)
    assert keep.is_active is True
    assert _state(db, contestant, target) is (True if target.id == home_season.id else None)


# --------------------------------------------------------------------------
# TEST 8-9: admin season edit
# --------------------------------------------------------------------------
def _admin_edit(db, contestant_id: int, season_id: int):
    from app.api.api_v1.endpoints.admin import ContestantUpdateRequest, update_contestant

    return asyncio.run(
        update_contestant(
            contestant_id=contestant_id,
            contestant_data=ContestantUpdateRequest(season_id=season_id),
            db=db,
            current_user=SimpleNamespace(is_admin=True),
        )
    )


def test_8_admin_season_edit_cannot_reactivate_foreign_round_membership(db):
    contest, _, _, home_season, foreign_season, contestant = _post_repair_fixture(db, "t8")
    contestant.season_id = 900_001  # legacy value that differs from every season id
    db.commit()

    with pytest.raises(HTTPException) as exc:
        _admin_edit(db, contestant.id, foreign_season.id)

    assert exc.value.status_code == 409
    assert _state(db, contestant, foreign_season) is False  # not reactivated
    assert _state(db, contestant, home_season) is True  # KEEP untouched
    db.refresh(contestant)
    assert contestant.season_id == 900_001  # nothing else was applied either


def test_9a_admin_legitimate_same_round_activation_still_works(db):
    contest = _contest(db, "t9a")
    rnd = _round(db, "t9a")
    city = _season(db, rnd, contest, SeasonLevel.CITY, "t9a-city")
    country = _season(db, rnd, contest, SeasonLevel.COUNTRY, "t9a-country")
    contestant = _contestant(db, suffix="t9a", rnd=rnd, contest=contest)
    _membership(db, contestant=contestant, season=city, is_active=True)
    contestant.season_id = city.id
    db.commit()

    result = _admin_edit(db, contestant.id, country.id)

    assert result["season_id"] == country.id
    assert _state(db, contestant, country) is True
    assert _state(db, contestant, city) is False  # old link still deactivated


def test_9b_admin_same_round_reactivation_preserves_joined_at(db):
    contest = _contest(db, "t9b")
    rnd = _round(db, "t9b")
    city = _season(db, rnd, contest, SeasonLevel.CITY, "t9b-city")
    country = _season(db, rnd, contest, SeasonLevel.COUNTRY, "t9b-country")
    contestant = _contestant(db, suffix="t9b", rnd=rnd, contest=contest)
    original_joined = datetime(2026, 3, 1, 12, 0, 0)
    _membership(db, contestant=contestant, season=city, is_active=True)
    _membership(db, contestant=contestant, season=country, is_active=False, joined_at=original_joined)
    contestant.season_id = city.id
    db.commit()

    _admin_edit(db, contestant.id, country.id)

    row = (
        db.query(ContestantSeason)
        .filter(ContestantSeason.contestant_id == contestant.id, ContestantSeason.season_id == country.id)
        .one()
    )
    assert row.is_active is True
    assert row.joined_at == original_joined


# --------------------------------------------------------------------------
# TEST 10: same-level protection still works (home-round activation)
# --------------------------------------------------------------------------
def test_10_home_round_activation_still_clears_foreign_same_level_only(db):
    contest = _contest(db, "t10")
    home, foreign = _round(db, "t10-home"), _round(db, "t10-foreign")
    home_continent = _season(db, home, contest, SeasonLevel.CONTINENT, "t10-hc")
    foreign_continent = _season(db, foreign, contest, SeasonLevel.CONTINENT, "t10-fc")
    home_regional = _season(db, home, contest, SeasonLevel.REGIONAL, "t10-hr")
    contestant = _contestant(db, suffix="t10", rnd=home, contest=contest)
    _membership(db, contestant=contestant, season=foreign_continent, is_active=True)  # historical corruption
    _membership(db, contestant=contestant, season=home_regional, is_active=True)  # other level
    db.commit()

    SeasonMigrationService._activate_contestant_season_link(db, contestant.id, home_continent.id)
    db.commit()

    assert _active_season_ids(db, contestant, SeasonLevel.CONTINENT) == [home_continent.id]
    assert _active_season_ids(db, contestant, SeasonLevel.REGIONAL) == [home_regional.id]


# --------------------------------------------------------------------------
# TEST 11-12: c45d79d isolation / contestant-96 shape stay blocked post-repair
# --------------------------------------------------------------------------
def test_11_12_foreign_membership_stays_blocked_from_candidate_selection(db):
    contest, _, _, home_season, foreign_season, contestant = _post_repair_fixture(db, "t11")
    # contestant-96 shape: an ACTIVE foreign membership (pre-repair state) too
    db.query(ContestantSeason).filter(
        ContestantSeason.contestant_id == contestant.id, ContestantSeason.season_id == foreign_season.id
    ).update({"is_active": True})
    db.commit()

    foreign_pool = SeasonMigrationService._contestants_for_contest_in_season(
        db, foreign_season.id, contest.id, active_only=True
    )
    home_pool = SeasonMigrationService._contestants_for_contest_in_season(
        db, home_season.id, contest.id, active_only=True
    )

    assert contestant.id not in {c.id for c in foreign_pool}
    assert contestant.id in {c.id for c in home_pool}


# --------------------------------------------------------------------------
# migrate_to_city_season: no longer links other rounds' contestants
# --------------------------------------------------------------------------
def test_migrate_to_city_season_is_round_scoped(db):
    contest = _contest(db, "city")
    home, other = _round(db, "city-home"), _round(db, "city-other")
    db.execute(round_contests.insert().values(round_id=home.id, contest_id=contest.id))
    mine = _contestant(db, suffix="city-mine", rnd=home, contest=contest)
    theirs = _contestant(db, suffix="city-theirs", rnd=other, contest=contest)
    db.commit()

    result = SeasonMigrationService.migrate_to_city_season(db, contest.id, home.id)
    db.commit()

    assert result.get("error") is None
    city_season_id = result["season_id"]
    assert (
        db.query(ContestantSeason)
        .filter(ContestantSeason.contestant_id == mine.id, ContestantSeason.season_id == city_season_id, ContestantSeason.is_active == True)
        .count()
        == 1
    )
    assert (
        db.query(ContestantSeason)
        .filter(ContestantSeason.contestant_id == theirs.id)
        .count()
        == 0
    )


# --------------------------------------------------------------------------
# PHASE 9: the repair-undo scenario, old behaviour vs new behaviour
# --------------------------------------------------------------------------
def test_phase9_old_behaviour_would_undo_the_repair(db, monkeypatch):
    """With the round rule neutralised (== the pre-fix logic, which had no
    round check anywhere) the source-link repair reactivates the foreign
    membership and the shared helper then deactivates the valid KEEP."""
    contest, _, _, home_season, foreign_season, contestant = _post_repair_fixture(db, "p9old")
    monkeypatch.setattr(
        SeasonMigrationService, "contestant_season_round_conflict", staticmethod(lambda a, b: None)
    )

    repaired = SeasonMigrationService._ensure_source_season_links(db, contest.id, foreign_season.id)
    db.commit()

    assert repaired == 1
    assert _state(db, contestant, foreign_season) is True  # FOREIGN_REACTIVATED = YES (the defect)
    assert _state(db, contestant, home_season) is False  # KEEP displaced (the defect)


def test_phase9_new_behaviour_keeps_repair_intact(db):
    contest, _, _, home_season, foreign_season, contestant = _post_repair_fixture(db, "p9new")

    SeasonMigrationService._ensure_source_season_links(db, contest.id, foreign_season.id)
    db.commit()

    foreign_reactivated = _state(db, contestant, foreign_season) is True
    keep_still_active = _state(db, contestant, home_season) is True
    assert foreign_reactivated is False  # FOREIGN_REACTIVATED = NO
    assert keep_still_active is True  # KEEP_STILL_ACTIVE = YES


# --------------------------------------------------------------------------
# PHASE 10: hourly scheduler simulation after the hypothetical repair
# --------------------------------------------------------------------------
def _scheduler_world(db):
    """Three contestants of round A, each with a KEEP at A's continent season
    and repaired (inactive) rows at B's and C's continent seasons; the stuck
    (contest, source season) pairs the production scheduler retries hourly."""
    contest = _contest(db, "sched")
    rounds = {k: _round(db, f"sched-{k}") for k in ("a", "b", "c")}
    seasons = {k: _season(db, rounds[k], contest, SeasonLevel.CONTINENT, f"sched-{k}") for k in rounds}
    people = [_contestant(db, suffix=f"sched-{i}", rnd=rounds["a"], contest=contest) for i in range(3)]
    for p in people:
        _membership(db, contestant=p, season=seasons["a"], is_active=True)
        _membership(db, contestant=p, season=seasons["b"], is_active=False)
        _membership(db, contestant=p, season=seasons["c"], is_active=False)
    db.commit()
    return contest, rounds, seasons, people


def _assert_repair_intact(db, seasons, people):
    """The repaired foreign rows never come back. The home KEEP row may only
    leave by a LEGITIMATE promotion (round A's own continental season is a
    real source season and promotes its contestants to A's GLOBAL season) --
    never because a foreign row displaced it."""
    for p in people:
        assert _state(db, p, seasons["b"]) is False
        assert _state(db, p, seasons["c"]) is False
        assert set(_active_season_ids(db, p, SeasonLevel.CONTINENT)) <= {seasons["a"].id}
        if _state(db, p, seasons["a"]) is False:
            promoted_to = (
                db.query(ContestSeason.round_id)
                .join(ContestantSeason, ContestantSeason.season_id == ContestSeason.id)
                .filter(
                    ContestantSeason.contestant_id == p.id,
                    ContestantSeason.is_active == True,
                    ContestSeason.level == SeasonLevel.GLOBAL,
                )
                .all()
            )
            assert [r[0] for r in promoted_to] == [p.round_id], "KEEP left without a legitimate home-round promotion"


def test_phase10_hourly_promotion_attempts_cannot_recreate_foreign_memberships(db, monkeypatch):
    contest, _, seasons, people = _scheduler_world(db)
    seen = []
    real = SeasonMigrationService._ensure_source_season_links

    def spy(db=None, contest_id=None, season_id=None):
        result = real(db=db, contest_id=contest_id, season_id=season_id)
        seen.append((season_id, result))
        return result

    monkeypatch.setattr(SeasonMigrationService, "_ensure_source_season_links", staticmethod(spy))

    for _ in range(3):  # three hourly passes, each committing (worst case)
        for key in ("b", "c", "a"):
            SeasonMigrationService.promote_to_next_level(
                db, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL, contest.id, from_season_id=seasons[key].id
            )
            db.commit()

    assert {sid for sid, _ in seen} >= {seasons["b"].id, seasons["c"].id}, "source-link repair was never exercised"
    assert all(n == 0 for sid, n in seen if sid in (seasons["b"].id, seasons["c"].id))
    _assert_repair_intact(db, seasons, people)


def test_phase10_scheduler_entrypoint_check_and_process_migrations(db, monkeypatch):
    """Drives the real scheduler entry point (the call the hourly loop makes),
    only stubbing the calendar-due check so the fixture needs no dates."""
    contest, _, seasons, people = _scheduler_world(db)
    monkeypatch.setattr(
        SeasonMigrationService, "_promotion_due_for_contest", staticmethod(lambda *a, **k: True)
    )
    calls = []
    real = SeasonMigrationService._ensure_source_season_links

    def spy(db=None, contest_id=None, season_id=None):
        calls.append(season_id)
        return real(db=db, contest_id=contest_id, season_id=season_id)

    monkeypatch.setattr(SeasonMigrationService, "_ensure_source_season_links", staticmethod(spy))

    from app.services.monthly_calendar_ops import run_season_migrations

    for _ in range(2):
        run_season_migrations(db)
        db.commit()

    assert calls, "the scheduler entry point never reached the source-link repair"
    _assert_repair_intact(db, seasons, people)


# --------------------------------------------------------------------------
# PHASE 11: the monthly job runs the hardened application code (static)
# --------------------------------------------------------------------------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_phase11_monthly_job_resolves_code_relative_to_its_own_tree():
    entry = (REPO_ROOT / "backend" / "scripts" / "ensure_month_round_and_migrations.py").read_text(encoding="utf-8")
    wrapper = (REPO_ROOT / "backend" / "scripts" / "run_ensure_month_round_and_migrations.sh").read_text(encoding="utf-8")
    cron = (REPO_ROOT / "scripts" / "run_monthly_migration_cron.sh").read_text(encoding="utf-8")

    # it imports the app from the backend directory it lives in ...
    assert "os.path.abspath(__file__)" in entry and "sys.path.insert(0, BACKEND_ROOT)" in entry
    assert "from app.services.monthly_calendar_ops import run_monthly_calendar_ops" in entry
    # ... and that pipeline reaches the hardened promotion code
    ops = (REPO_ROOT / "backend" / "app" / "services" / "monthly_calendar_ops.py").read_text(encoding="utf-8")
    assert "season_migration_service.check_and_process_migrations" in ops
    # no hard-coded checkout: the tree that runs is decided ONLY by where the
    # systemd unit's ExecStart points (production configuration)
    for text_ in (entry, wrapper, cron):
        assert "/root/kalutasociety" not in text_ and "/root/mh5" not in text_
    assert 'ROOT="$(cd "$(dirname "$0")/.." && pwd)"' in cron
