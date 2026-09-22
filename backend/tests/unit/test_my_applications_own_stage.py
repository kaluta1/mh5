"""
REQUIRED TESTS 9-12 (My Applications display fix). Verifies
crud_contestant.get_multi_by_user_with_stats no longer sources
`contest_level` from Contest.level (a single scalar shared by an entire
contest across every round/contestant -- confirmed this session to be
showing the same wrong stage to ~every nominee of ~every nomination
contest), and instead resolves each contestant's OWN current stage from
their OWN active ContestantSeason, scoped to their OWN round_id.
"""
from __future__ import annotations

from datetime import datetime

from app.crud.crud_contestant import crud_contestant
from app.models.contest import Contest
from app.models.contests import ContestantSeason, ContestSeason, Contestant, SeasonLevel
from app.models.round import Round, RoundStatus
from app.models.user import User


def _round(db, suffix: str) -> Round:
    rnd = Round(name=f"Round {suffix}", status=RoundStatus.ACTIVE)
    db.add(rnd)
    db.flush()
    return rnd


def _contest(db, suffix: str, *, level: str) -> Contest:
    contest = Contest(name=f"Contest {suffix}", contest_type="t", level=level, contest_mode="nomination")
    db.add(contest)
    db.flush()
    return contest


def _owner_and_contestant(db, *, suffix: str, rnd: Round, contest: Contest) -> Contestant:
    owner = User(email=f"myapp-{suffix}@example.test", hashed_password="unused")
    db.add(owner)
    db.flush()
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id,
        season_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        entry_type="nomination",
        title=f"Contestant {suffix}",
    )
    db.add(contestant)
    db.flush()
    return contestant, owner


def _active_season(db, *, rnd: Round, level: SeasonLevel, suffix: str) -> ContestSeason:
    season = ContestSeason(round_id=rnd.id, title=f"Season {suffix}", level=level)
    db.add(season)
    db.flush()
    return season


def _activate(db, *, contestant: Contestant, season: ContestSeason) -> None:
    db.add(
        ContestantSeason(
            contestant_id=contestant.id,
            season_id=season.id,
            joined_at=datetime.utcnow(),
            is_active=True,
        )
    )
    db.flush()


def test_my_applications_returns_each_contestants_own_stage(db):
    """
    REQUIRED TEST 9. Two contestants, same contest, different rounds and
    different actual own-round stages -- each must get their OWN correct
    contest_level, not a shared value.
    """
    contest = _contest(db, "own-stage", level="regional")  # Contest.level deliberately says "regional"

    round_a = _round(db, "a")
    contestant_a, owner_a = _owner_and_contestant(db, suffix="a", rnd=round_a, contest=contest)
    season_a = _active_season(db, rnd=round_a, level=SeasonLevel.CITY, suffix="a")
    _activate(db, contestant=contestant_a, season=season_a)

    round_b = _round(db, "b")
    contestant_b, owner_b = _owner_and_contestant(db, suffix="b", rnd=round_b, contest=contest)
    season_b = _active_season(db, rnd=round_b, level=SeasonLevel.CONTINENT, suffix="b")
    _activate(db, contestant=contestant_b, season=season_b)
    db.commit()

    results_a = crud_contestant.get_multi_by_user_with_stats(db, user_id=owner_a.id)
    results_b = crud_contestant.get_multi_by_user_with_stats(db, user_id=owner_b.id)

    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0]["contest_level"] == "city"
    assert results_b[0]["contest_level"] == "continent"


def test_contest_level_scalar_cannot_override_own_stage(db):
    """
    REQUIRED TEST 10. Contest.level is deliberately set to a value
    different from the contestant's actual own-round stage -- My
    Applications must return the contestant's own stage, never Contest.level.
    """
    contest = _contest(db, "override", level="global")  # deliberately wrong/stale
    rnd = _round(db, "override")
    contestant, owner = _owner_and_contestant(db, suffix="override", rnd=rnd, contest=contest)
    season = _active_season(db, rnd=rnd, level=SeasonLevel.COUNTRY, suffix="override")
    _activate(db, contestant=contestant, season=season)
    db.commit()

    results = crud_contestant.get_multi_by_user_with_stats(db, user_id=owner.id)
    assert results[0]["contest_level"] == "country"
    assert results[0]["contest_level"] != "global"


def test_foreign_round_active_membership_does_not_leak(db):
    """
    REQUIRED TEST 11 (part 1). A contestant with one valid own-round active
    ContestantSeason AND one active foreign-round ContestantSeason (the
    still-partially-unrepaired cross-round contamination defect) must show
    only the own-round stage.
    """
    contest = _contest(db, "mixed", level="regional")
    own_round = _round(db, "mixed-own")
    foreign_round = _round(db, "mixed-foreign")
    contestant, owner = _owner_and_contestant(db, suffix="mixed", rnd=own_round, contest=contest)

    own_season = _active_season(db, rnd=own_round, level=SeasonLevel.CITY, suffix="mixed-own")
    _activate(db, contestant=contestant, season=own_season)

    foreign_season = _active_season(db, rnd=foreign_round, level=SeasonLevel.CONTINENT, suffix="mixed-foreign")
    _activate(db, contestant=contestant, season=foreign_season)
    db.commit()

    results = crud_contestant.get_multi_by_user_with_stats(db, user_id=owner.id)
    assert results[0]["contest_level"] == "city"
    assert results[0]["contest_level"] != "continent"


def test_only_foreign_round_membership_returns_none(db):
    """
    REQUIRED TEST 11 (part 2). A contestant with ONLY a foreign-round active
    membership and no own-round valid membership must return
    contest_level = None, never the foreign level.
    """
    contest = _contest(db, "onlyforeign", level="regional")
    own_round = _round(db, "onlyforeign-own")
    foreign_round = _round(db, "onlyforeign-foreign")
    contestant, owner = _owner_and_contestant(db, suffix="onlyforeign", rnd=own_round, contest=contest)

    foreign_season = _active_season(db, rnd=foreign_round, level=SeasonLevel.CONTINENT, suffix="onlyforeign")
    _activate(db, contestant=contestant, season=foreign_season)
    db.commit()

    results = crud_contestant.get_multi_by_user_with_stats(db, user_id=owner.id)
    assert results[0]["contest_level"] is None


def test_submission_or_start_voting_contestant_returns_none(db):
    """
    REQUIRED TEST 12. A contestant with no own-round active geographic
    ContestantSeason at all (still in Submission or Start Voting) must
    return contest_level = None -- never a fake/invented City label.
    """
    contest = _contest(db, "notyet", level="city")
    rnd = _round(db, "notyet")
    contestant, owner = _owner_and_contestant(db, suffix="notyet", rnd=rnd, contest=contest)
    db.commit()  # no ContestantSeason created at all

    results = crud_contestant.get_multi_by_user_with_stats(db, user_id=owner.id)
    assert len(results) == 1
    assert results[0]["contest_level"] is None
