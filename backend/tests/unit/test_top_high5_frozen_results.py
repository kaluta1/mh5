"""
Tests for the frozen Top High5 results feature: the freeze hook
(SeasonMigrationService._freeze_top_high5_results, wired into
promote_to_next_level and the new GLOBAL finalization step) that replaced
live vote computation on the /top-high5 endpoint. See the functional spec
this implements: Top High5 must show only finalized results from a closed
voting month, never the current live leaderboard, and the same set that is
migrated must be the set that is frozen.

Covers three properties specific to this rework that the existing
zero-vote-inclusion and contest-resolution test files don't touch:

1. Idempotency: re-running a promotion never duplicates or rewrites a
   frozen result (spec section 20 -- a finalized result must never change).
2. The CONTINENT level's own per-continent Top High5 is a genuinely
   different ranking from the worldwide Continental->Global promotion pool
   -- a continent's own rank 4-5 (or an entire other continent) can be
   frozen with migrated=False while still being a real, displayed result.
3. GLOBAL has no further promotion, so its own Top High5 needs a dedicated
   finalization step, gated on the same due-date logic as every other level
   (not on whenever an admin happens to trigger a promotion).
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    Contestant,
    ContestantSeason,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.services.season_migration import SeasonMigrationService


def _user(db, suffix: str) -> User:
    user = User(email=f"th5fr-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str, *, months_ago: int) -> Round:
    cohort_start = SeasonMigrationService._add_months(date.today().replace(day=1), -months_ago)
    end = cohort_start + timedelta(days=27)
    rnd = Round(
        name=f"Round {cohort_start.strftime('%B %Y')} {suffix}",
        status=RoundStatus.ACTIVE,
        submission_start_date=cohort_start,
        submission_end_date=end,
    )
    db.add(rnd)
    db.flush()
    return rnd


def _country_scope(db, rnd: Round, *, suffix: str):
    contest = Contest(
        name=f"Contest {suffix}", contest_type="t", contest_mode="nomination", level="country"
    )
    db.add(contest)
    db.flush()
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title=f"Season {suffix}", level=SeasonLevel.COUNTRY)
    db.add(season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.flush()
    return contest, season


def _contestant(db, *, suffix: str, rnd: Round, contest: Contest, season: ContestSeason, country: str) -> Contestant:
    owner = _user(db, suffix)
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country=country,
        title=f"Contestant {suffix}",
    )
    db.add(contestant)
    db.flush()
    db.add(ContestantSeason(contestant_id=contestant.id, season_id=season.id, is_active=True))
    db.flush()
    return contestant


def _vote(db, *, suffix: str, contestant: Contestant, contest: Contest, season: ContestSeason, points: int = 5):
    from app.models.voting import ContestantVoting

    voter = _user(db, f"voter-{suffix}")
    bucket_key = f"ty:{contest.contest_type or ''}:{contest.contest_mode or ''}"
    db.add(
        ContestantVoting(
            user_id=voter.id,
            contestant_id=contestant.id,
            contest_id=contest.id,
            season_id=season.id,
            vote_bucket_key=bucket_key,
            position=1,
            points=points,
        )
    )
    db.flush()


def test_freeze_is_idempotent_on_rerun(db):
    """Re-running the same promotion twice must not duplicate or alter the
    frozen result (spec section 20/21)."""
    rnd = _round(db, "idem", months_ago=4)
    contest, season = _country_scope(db, rnd, suffix="idem")
    a = _contestant(db, suffix="idem-a", rnd=rnd, contest=contest, season=season, country="Tanzania")
    b = _contestant(db, suffix="idem-b", rnd=rnd, contest=contest, season=season, country="Tanzania")
    _vote(db, suffix="idem-a", contestant=a, contest=contest, season=season, points=10)
    db.commit()

    first = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, contest.id, from_season_id=season.id
    )
    db.commit()
    # Promotion itself only advances the voted contestant `a`; the freeze is
    # zero-vote-inclusive (matches the shipped display precedent), so `b`
    # is still frozen too, just with migrated=False.
    assert first.get("promoted_count") == 1

    rows_after_first = (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == contest.id, TopHigh5Result.level == SeasonLevel.COUNTRY)
        .order_by(TopHigh5Result.rank)
        .all()
    )
    assert len(rows_after_first) == 2
    assert rows_after_first[0].contestant_id == a.id
    assert rows_after_first[0].rank == 1
    assert rows_after_first[0].migrated is True
    assert rows_after_first[1].contestant_id == b.id
    assert rows_after_first[1].rank == 2
    assert rows_after_first[1].migrated is False
    first_ids = {r.id for r in rows_after_first}

    # Re-running (e.g. an admin re-triggering, or a scheduler retry) must not
    # duplicate or overwrite the already-frozen rows.
    SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, contest.id, from_season_id=season.id
    )
    db.commit()

    rows_after_second = (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == contest.id, TopHigh5Result.level == SeasonLevel.COUNTRY)
        .all()
    )
    assert {r.id for r in rows_after_second} == first_ids


def test_continent_freeze_differs_from_worldwide_global_pool(db):
    """A continent's own Top High5 (per continent) is frozen even for
    members that don't make the worldwide Continental->Global cut -- proving
    the freeze hook uses a genuinely separate ranking from the promotion
    pool, and that `migrated` reflects real destination membership, not
    rank <= 5."""
    rnd = _round(db, "cont", months_ago=4)
    contest = Contest(
        name="Contest cont", contest_type="t", contest_mode="nomination", level="continent"
    )
    db.add(contest)
    db.flush()
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    continent_season = ContestSeason(
        round_id=rnd.id, title="Continental cont", level=SeasonLevel.CONTINENT
    )
    db.add(continent_season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=continent_season.id, is_active=True))
    db.flush()

    def _continent_contestant(suffix: str, continent: str, points: int) -> Contestant:
        owner = _user(db, suffix)
        c = Contestant(
            user_id=owner.id,
            round_id=rnd.id,
            contest_id=contest.id,
            # The worldwide GLOBAL-selection filter inside promote_to_next_level
            # uses the legacy Contestant.season_id == contest_id comparison
            # (a pre-existing, out-of-scope-here quirk) -- match it so the
            # real code path is exercised faithfully.
            season_id=contest.id,
            is_active=True,
            is_deleted=False,
            is_qualified=True,
            continent=continent,
            title=f"Contestant {suffix}",
            registration_date=rnd.submission_start_date,
        )
        db.add(c)
        db.flush()
        db.add(ContestantSeason(contestant_id=c.id, season_id=continent_season.id, is_active=True))
        db.flush()
        if points:
            _vote(db, suffix=suffix, contestant=c, contest=contest, season=continent_season, points=points)
        return c

    # Africa dominates the worldwide vote count; Europe's own top members
    # have real (but much lower) votes, so Europe's continent-level Top
    # High5 is real and non-empty, yet none of it should migrate globally
    # under a worldwide limit of 3.
    africa = [_continent_contestant(f"africa-{i}", "Africa", points) for i, points in enumerate([100, 90, 80, 70, 60])]
    europe = [_continent_contestant(f"europe-{i}", "Europe", points) for i, points in enumerate([5, 4, 3, 2, 1])]
    db.commit()

    result = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL, contest.id, from_season_id=continent_season.id, limit=3
    )
    db.commit()
    assert result.get("promoted_count") == 3
    globally_promoted_ids = set(result["promoted_contestant_ids"])
    # Worldwide top 3 by points are Africa's top 3.
    assert globally_promoted_ids == {africa[0].id, africa[1].id, africa[2].id}

    frozen = (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == contest.id, TopHigh5Result.level == SeasonLevel.CONTINENT)
        .all()
    )
    by_jurisdiction: dict[str, list[TopHigh5Result]] = {}
    for r in frozen:
        by_jurisdiction.setdefault(r.jurisdiction, []).append(r)

    assert set(by_jurisdiction.keys()) == {"Africa", "Europe"}
    assert len(by_jurisdiction["Africa"]) == 5
    assert len(by_jurisdiction["Europe"]) == 5

    africa_migrated = {r.contestant_id for r in by_jurisdiction["Africa"] if r.migrated}
    assert africa_migrated == {africa[0].id, africa[1].id, africa[2].id}
    europe_migrated = {r.contestant_id for r in by_jurisdiction["Europe"] if r.migrated}
    assert europe_migrated == set()  # real, displayed Top High5 -- none advanced globally


def test_global_finalization_respects_due_date(db):
    """GLOBAL's own Top High5 must only be frozen once its voting has
    actually closed -- not merely because an admin/scheduler run happens to
    execute."""

    def _global_scope(suffix: str, *, months_ago: int):
        rnd = _round(db, suffix, months_ago=months_ago)
        contest = Contest(
            name=f"Contest {suffix}", contest_type="t", contest_mode="nomination", level="global"
        )
        db.add(contest)
        db.flush()
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
        global_season = ContestSeason(round_id=rnd.id, title=f"Global {suffix}", level=SeasonLevel.GLOBAL)
        db.add(global_season)
        db.flush()
        db.add(ContestSeasonLink(contest_id=contest.id, season_id=global_season.id, is_active=True))
        db.flush()

        owner = _user(db, suffix)
        c = Contestant(
            user_id=owner.id,
            round_id=rnd.id,
            contest_id=contest.id,
            season_id=contest.id,
            is_active=True,
            is_deleted=False,
            is_qualified=True,
            continent="Africa",
            title=f"Contestant {suffix}",
            registration_date=rnd.submission_start_date,
        )
        db.add(c)
        db.flush()
        db.add(ContestantSeason(contestant_id=c.id, season_id=global_season.id, is_active=True))
        db.flush()
        _vote(db, suffix=suffix, contestant=c, contest=contest, season=global_season, points=10)
        db.commit()
        return rnd, contest, global_season

    # GLOBAL vote-open for a cohort is month+4; not-yet-closed case: a cohort
    # that started this month has its GLOBAL vote-open four months in the
    # future, so it is nowhere near closed.
    not_due_round, not_due_contest, not_due_season = _global_scope("notdue", months_ago=0)
    SeasonMigrationService._finalize_global_top_high5(db, not_due_season, not_due_round, date.today())
    db.commit()
    assert (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == not_due_contest.id, TopHigh5Result.level == SeasonLevel.GLOBAL)
        .count()
        == 0
    )

    # Due case: a cohort that started 6 months ago has GLOBAL voting open
    # since month+4 (2 months ago) and closed since the end of that month.
    due_round, due_contest, due_season = _global_scope("due", months_ago=6)
    SeasonMigrationService._finalize_global_top_high5(db, due_season, due_round, date.today())
    db.commit()
    frozen = (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == due_contest.id, TopHigh5Result.level == SeasonLevel.GLOBAL)
        .all()
    )
    assert len(frozen) == 1
    assert frozen[0].jurisdiction == "Global"
    assert frozen[0].to_season_id is None
    assert frozen[0].migrated is False


def test_reconciliation_matches_frozen_migrated_set_to_actual_membership(db):
    """The set of contestant_ids frozen with migrated=True for a group must
    exactly equal that contest's actual active ContestantSeason membership
    in the destination season (spec section 23), by construction."""
    from app.services.contestant_contest_resolution import contestant_belongs_to_contest_clause

    rnd = _round(db, "recon", months_ago=4)
    contest, season = _country_scope(db, rnd, suffix="recon")
    a = _contestant(db, suffix="recon-a", rnd=rnd, contest=contest, season=season, country="Tanzania")
    b = _contestant(db, suffix="recon-b", rnd=rnd, contest=contest, season=season, country="Tanzania")
    _vote(db, suffix="recon-a", contestant=a, contest=contest, season=season, points=10)
    _vote(db, suffix="recon-b", contestant=b, contest=contest, season=season, points=5)
    db.commit()

    result = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, contest.id, from_season_id=season.id
    )
    db.commit()
    to_season_id = result["to_season_id"]

    frozen_migrated_ids = {
        row[0]
        for row in db.query(TopHigh5Result.contestant_id)
        .filter(
            TopHigh5Result.contest_id == contest.id,
            TopHigh5Result.to_season_id == to_season_id,
            TopHigh5Result.migrated == True,  # noqa: E712
        )
        .all()
    }
    actual_ids = {
        row[0]
        for row in db.query(ContestantSeason.contestant_id)
        .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
        .filter(
            ContestantSeason.season_id == to_season_id,
            ContestantSeason.is_active == True,
            contestant_belongs_to_contest_clause(contest.id),
        )
        .all()
    }
    assert frozen_migrated_ids == actual_ids == {a.id, b.id}
