from __future__ import annotations

from datetime import date, datetime, timedelta

from app.api.api_v1.endpoints.contestant import (
    _contestant_belongs_to_contest,
    _resolve_contest_for_contestant_vote,
)
from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    Contestant,
    SeasonLevel,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User


def _user(db, suffix: str) -> User:
    user = User(email=f"cid-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _contest(db, suffix: str) -> Contest:
    contest = Contest(
        name=f"Contest {suffix}",
        contest_type=f"type-{suffix}",
        contest_mode="nomination",
        level="country",
    )
    db.add(contest)
    db.flush()
    return contest


def _round_and_season(db, suffix: str, month: int = 9):
    start = date(2026, month, 1)
    rnd = Round(
        name=f"Round {suffix}",
        status=RoundStatus.ACTIVE,
        submission_start_date=start,
        submission_end_date=add_months_stub(start),
    )
    db.add(rnd)
    db.flush()
    season = ContestSeason(
        round_id=rnd.id,
        title=f"Season {suffix}",
        level=SeasonLevel.COUNTRY,
    )
    db.add(season)
    db.flush()
    return rnd, season


def add_months_stub(d: date) -> date:
    # Local helper: end of a 1-month submission window, avoids importing the
    # production add_months() just for a test fixture date.
    if d.month == 12:
        return date(d.year + 1, 1, 1) - timedelta(days=1)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _link(db, contest: Contest, season: ContestSeason):
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.flush()


def test_new_contest_id_path_is_preferred_and_authoritative(db):
    """A contestant with contest_id populated resolves via that field alone --
    it must not need season_id to agree, proving contest_id is checked first
    and trusted on its own."""
    owner = _user(db, "new-path")
    rnd, season = _round_and_season(db, "new-path")
    real_contest = _contest(db, "real")
    decoy_contest = _contest(db, "decoy")
    _link(db, real_contest, season)
    _link(db, decoy_contest, season)

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,      # a genuine ContestSeason reference
        contest_id=real_contest.id,  # the new, authoritative field
        title="New-style contestant",
    )
    db.add(contestant)
    db.flush()

    assert _contestant_belongs_to_contest(db, contestant, real_contest.id, season) is True
    # decoy_contest is linked to the same season but is NOT this contestant's contest_id
    assert _contestant_belongs_to_contest(db, contestant, decoy_contest.id, season) is False

    resolved = _resolve_contest_for_contestant_vote(db, contestant, season)
    assert resolved is not None
    assert resolved.id == real_contest.id


def test_legacy_season_id_fallback_still_works_when_contest_id_is_null(db):
    """Old-style rows (contest_id NULL, season_id overloaded as a legacy
    Contest.id) must resolve exactly as they did before this change."""
    owner = _user(db, "legacy-path")
    rnd, season = _round_and_season(db, "legacy-path")
    legacy_contest = _contest(db, "legacy")
    _link(db, legacy_contest, season)

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=legacy_contest.id,  # legacy convention: season_id holds a Contest.id
        contest_id=None,              # never backfilled for this row
        title="Legacy-style contestant",
    )
    db.add(contestant)
    db.flush()

    assert _contestant_belongs_to_contest(db, contestant, legacy_contest.id, season) is True

    resolved = _resolve_contest_for_contestant_vote(db, contestant, season)
    assert resolved is not None
    assert resolved.id == legacy_contest.id


def test_genuine_season_reference_is_never_reinterpreted_as_contest_id(db):
    """A contestant with a real ContestSeason link (contest_id NULL, season_id
    a genuine ContestSeason.id that does NOT coincide with any relevant
    Contest.id here) must resolve via the normal season/round_contests path,
    completely unaffected by the new contest_id field or the legacy
    season_id-as-contest_id fallback."""
    owner = _user(db, "genuine-season")
    rnd, season = _round_and_season(db, "genuine-season")
    _contest(db, "decoy-to-shift-id-sequence")  # ensures only_contest.id != season.id below
    only_contest = _contest(db, "only")
    _link(db, only_contest, season)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=only_contest.id))

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,  # genuine season reference; not equal to only_contest.id
        contest_id=None,
        title="Genuine season contestant",
    )
    db.add(contestant)
    db.flush()
    assert contestant.season_id != only_contest.id  # sanity: no accidental numeric coincidence

    # _contestant_belongs_to_contest must fall through both the preferred and legacy
    # contest_id-style checks (neither matches) and land on the real ContestSeasonLink path.
    assert _contestant_belongs_to_contest(db, contestant, only_contest.id, season) is True

    resolved = _resolve_contest_for_contestant_vote(db, contestant, season)
    assert resolved is not None
    assert resolved.id == only_contest.id


def test_null_contest_id_and_null_season_id_resolves_to_nothing_without_crashing(db):
    """A contestant with neither field set (e.g. mid-creation, or genuinely
    unlinked) must resolve to None/False rather than raising, and must not
    match an unrelated contest by accident."""
    owner = _user(db, "null-both")
    rnd, season = _round_and_season(db, "null-both")
    unrelated_contest = _contest(db, "unrelated")

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=None,
        contest_id=None,
        title="Unlinked contestant",
    )
    db.add(contestant)
    db.flush()

    assert _contestant_belongs_to_contest(db, contestant, unrelated_contest.id, season) is False
    assert _resolve_contest_for_contestant_vote(db, contestant, season) is None
