"""
Regression tests for the ContestantSeason same-level cross-round integrity
defect (see KALUTASOCIETY_CONTESTANTSEASON_MULTIROUND_INTEGRITY_AUDIT).

Bug: a contestant could end up with multiple simultaneously ACTIVE
ContestantSeason rows whose seasons share the same logical level but
belong to different rounds/cohorts. Root cause proven live: promote_to_
next_level's destination-link activation (season_migration.py) only ever
deactivated the contestant's link at `from_season.id` (this promotion's
own source season) -- it never checked whether the contestant already
held an active link at some OTHER season of the SAME level under a
DIFFERENT round before creating/reactivating the destination link. Traced
concretely against production: contestant 96 held three simultaneously
active Continental memberships (rounds 3, 4, 21); 747 (contestant, level)
groups exhibited the same pattern across all five levels.

This is entirely independent of the earlier c45d79d fix (candidate-
rescue fallback scoping) -- that fix closes a different code path and
does not touch ContestantSeason writes at all. A contestant admitted via
a corrupted ACTIVE membership is accepted by the PRIMARY query, before
any fallback tier is ever reached.

Fix: a single shared helper, _activate_contestant_season_link, is now
the only place that creates/reactivates a destination ContestantSeason
link. It deactivates any OTHER active membership the contestant holds at
a season of the SAME level (any round), before activating the target --
never touching memberships at OTHER levels. Every write path that used
to build ContestantSeason rows inline (promote_to_next_level,
migrate_to_city_season, _sync_contestants_to_season,
_ensure_source_season_links) now goes through it.

As defense in depth against the historical bad data already in
production, the PRIMARY candidate-selection queries in both
_contestants_for_contest_in_season and get_top_contestants_by_location
now also require Contestant.round_id to match the round of the season
being queried (derived from the season itself when not explicitly
supplied) -- proven safe by the full existing test suite (264/264)
passing unchanged with this added, plus Test 8 below specifically.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

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
from app.services.season_migration import SeasonMigrationService


def _user(db, suffix: str) -> User:
    user = User(email=f"cs-integrity-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str) -> Round:
    rnd = Round(name=f"Round {suffix}", status=RoundStatus.ACTIVE)
    db.add(rnd)
    db.flush()
    return rnd


def _contest(db, suffix: str, level: SeasonLevel = SeasonLevel.CONTINENT) -> Contest:
    contest = Contest(
        name=f"Contest {suffix}", contest_type="t", contest_mode="nomination", level=level.value
    )
    db.add(contest)
    db.flush()
    return contest


def _season(db, rnd: Round, contest: Contest, level: SeasonLevel, suffix: str) -> ContestSeason:
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title=f"Season {suffix}", level=level)
    db.add(season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.flush()
    return season


def _contestant(db, *, suffix: str, rnd: Round, contest: Contest) -> Contestant:
    owner = _user(db, suffix)
    c = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
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


def _membership(db, *, contestant: Contestant, season: ContestSeason, is_active: bool, joined_at=None) -> ContestantSeason:
    m = ContestantSeason(
        contestant_id=contestant.id,
        season_id=season.id,
        is_active=is_active,
        joined_at=joined_at or datetime.utcnow(),
    )
    db.add(m)
    db.flush()
    return m


def _vote(db, *, suffix: str, contestant: Contestant, contest: Contest, season: ContestSeason):
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


def _active_seasons(db, contestant_id: int, level: SeasonLevel) -> list[int]:
    """Round ids for which this contestant holds an ACTIVE membership at `level`."""
    rows = (
        db.query(ContestSeason.round_id)
        .join(ContestantSeason, ContestantSeason.season_id == ContestSeason.id)
        .filter(
            ContestantSeason.contestant_id == contestant_id,
            ContestantSeason.is_active == True,
            ContestSeason.level == level,
        )
        .all()
    )
    return sorted(r[0] for r in rows)


def test_activate_link_deactivates_foreign_round_same_level(db):
    """TEST 1: contestant has active Continental in Round A. Activating
    Continental in Round B must leave B active and A inactive -- no two
    simultaneously active same-level memberships."""
    contest = _contest(db, "t1")
    round_a = _round(db, "t1-a")
    round_b = _round(db, "t1-b")
    season_a = _season(db, round_a, contest, SeasonLevel.CONTINENT, "t1-a")
    season_b = _season(db, round_b, contest, SeasonLevel.CONTINENT, "t1-b")
    contestant = _contestant(db, suffix="t1", rnd=round_a, contest=contest)
    _membership(db, contestant=contestant, season=season_a, is_active=True)
    db.commit()

    SeasonMigrationService._activate_contestant_season_link(db, contestant.id, season_b.id)
    db.commit()

    assert _active_seasons(db, contestant.id, SeasonLevel.CONTINENT) == [round_b.id]


def test_activate_link_preserves_other_levels(db):
    """TEST 2: a contestant's active Regional membership must survive
    untouched when their Continental membership is activated -- only
    same-level conflicts are resolved, never cross-level ones."""
    contest = _contest(db, "t2")
    rnd = _round(db, "t2")
    regional_season = _season(db, rnd, contest, SeasonLevel.REGIONAL, "t2-reg")
    continent_season = _season(db, rnd, contest, SeasonLevel.CONTINENT, "t2-cont")
    contestant = _contestant(db, suffix="t2", rnd=rnd, contest=contest)
    _membership(db, contestant=contestant, season=regional_season, is_active=True)
    db.commit()

    SeasonMigrationService._activate_contestant_season_link(db, contestant.id, continent_season.id)
    db.commit()

    assert _active_seasons(db, contestant.id, SeasonLevel.REGIONAL) == [rnd.id]
    assert _active_seasons(db, contestant.id, SeasonLevel.CONTINENT) == [rnd.id]


def test_activate_link_is_idempotent(db):
    """TEST 3: activating an already-active destination link must not
    create a duplicate row or raise an integrity error."""
    contest = _contest(db, "t3")
    rnd = _round(db, "t3")
    season = _season(db, rnd, contest, SeasonLevel.CONTINENT, "t3")
    contestant = _contestant(db, suffix="t3", rnd=rnd, contest=contest)
    _membership(db, contestant=contestant, season=season, is_active=True)
    db.commit()

    SeasonMigrationService._activate_contestant_season_link(db, contestant.id, season.id)
    db.commit()

    rows = db.query(ContestantSeason).filter(
        ContestantSeason.contestant_id == contestant.id, ContestantSeason.season_id == season.id
    ).all()
    assert len(rows) == 1
    assert rows[0].is_active is True


def test_activate_link_reactivates_and_clears_foreign_conflicts(db):
    """TEST 4: destination link exists but inactive; activating it must
    reactivate it AND clear any other active same-level foreign-round
    membership."""
    contest = _contest(db, "t4")
    round_a = _round(db, "t4-a")
    round_b = _round(db, "t4-b")
    season_a = _season(db, round_a, contest, SeasonLevel.CONTINENT, "t4-a")
    season_b = _season(db, round_b, contest, SeasonLevel.CONTINENT, "t4-b")
    contestant = _contestant(db, suffix="t4", rnd=round_a, contest=contest)
    _membership(db, contestant=contestant, season=season_a, is_active=True)
    _membership(db, contestant=contestant, season=season_b, is_active=False)
    db.commit()

    SeasonMigrationService._activate_contestant_season_link(db, contestant.id, season_b.id)
    db.commit()

    assert _active_seasons(db, contestant.id, SeasonLevel.CONTINENT) == [round_b.id]


def test_activate_link_clears_multiple_bad_same_level_links(db):
    """TEST 5: contestant has THREE simultaneously active Continental
    memberships (rounds A, B, C) -- exactly the contestant-96 production
    pattern. Activating the true destination (C) must leave only C
    active."""
    contest = _contest(db, "t5")
    round_a = _round(db, "t5-a")
    round_b = _round(db, "t5-b")
    round_c = _round(db, "t5-c")
    season_a = _season(db, round_a, contest, SeasonLevel.CONTINENT, "t5-a")
    season_b = _season(db, round_b, contest, SeasonLevel.CONTINENT, "t5-b")
    season_c = _season(db, round_c, contest, SeasonLevel.CONTINENT, "t5-c")
    contestant = _contestant(db, suffix="t5", rnd=round_c, contest=contest)
    _membership(db, contestant=contestant, season=season_a, is_active=True)
    _membership(db, contestant=contestant, season=season_b, is_active=True)
    _membership(db, contestant=contestant, season=season_c, is_active=False)
    db.commit()

    SeasonMigrationService._activate_contestant_season_link(db, contestant.id, season_c.id)
    db.commit()

    assert _active_seasons(db, contestant.id, SeasonLevel.CONTINENT) == [round_c.id]


def test_activate_link_does_not_affect_other_contestants(db):
    """TEST 6: another contestant's same-level membership at a different
    round must remain completely unchanged."""
    contest = _contest(db, "t6")
    round_a = _round(db, "t6-a")
    round_b = _round(db, "t6-b")
    season_a = _season(db, round_a, contest, SeasonLevel.CONTINENT, "t6-a")
    season_b = _season(db, round_b, contest, SeasonLevel.CONTINENT, "t6-b")
    contestant_x = _contestant(db, suffix="t6-x", rnd=round_a, contest=contest)
    contestant_y = _contestant(db, suffix="t6-y", rnd=round_a, contest=contest)
    _membership(db, contestant=contestant_x, season=season_a, is_active=True)
    _membership(db, contestant=contestant_y, season=season_a, is_active=True)
    db.commit()

    SeasonMigrationService._activate_contestant_season_link(db, contestant_x.id, season_b.id)
    db.commit()

    assert _active_seasons(db, contestant_x.id, SeasonLevel.CONTINENT) == [round_b.id]
    assert _active_seasons(db, contestant_y.id, SeasonLevel.CONTINENT) == [round_a.id]


def test_primary_query_rejects_foreign_cohort_historical_bad_data(db):
    """TEST 8: reproduces the contestant-96 production scenario exactly --
    a contestant with a genuine active membership at their OWN round plus
    a (pre-existing, historical) active membership at a FOREIGN round of
    the same level. The primary candidate query in
    get_top_contestants_by_location must reject the foreign-round
    membership even though it is genuinely ACTIVE, because it does not
    match the contestant's own round_id."""
    contest = _contest(db, "t8")
    home_round = _round(db, "t8-home")
    foreign_round = _round(db, "t8-foreign")
    home_season = _season(db, home_round, contest, SeasonLevel.CONTINENT, "t8-home")
    foreign_season = _season(db, foreign_round, contest, SeasonLevel.CONTINENT, "t8-foreign")
    contestant = _contestant(db, suffix="t8", rnd=home_round, contest=contest)
    _membership(db, contestant=contestant, season=home_season, is_active=True)
    # Simulate pre-existing historical corruption: an ACTIVE membership at a
    # foreign round the contestant does not belong to.
    _membership(db, contestant=contestant, season=foreign_season, is_active=True)
    db.commit()

    # Querying the FOREIGN season directly must not admit this contestant,
    # even though their ContestantSeason link there is genuinely active.
    grouped = SeasonMigrationService.get_top_contestants_by_location(
        db,
        foreign_season.id,
        "continent",
        contest_id=contest.id,
        diagnostics=False,
        active_links_only=True,
        qualified_only=False,
        strict_season_scope=True,
        require_votes=False,
    )
    found_ids = {c.id for members in grouped.values() for c in members}
    assert contestant.id not in found_ids, (
        "primary query admitted a contestant via a foreign-round active "
        "membership -- defense-in-depth round check did not apply"
    )

    # The contestant's OWN season must still resolve them correctly.
    grouped_home = SeasonMigrationService.get_top_contestants_by_location(
        db,
        home_season.id,
        "continent",
        contest_id=contest.id,
        diagnostics=False,
        active_links_only=True,
        qualified_only=False,
        strict_season_scope=True,
        require_votes=False,
    )
    home_ids = {c.id for members in grouped_home.values() for c in members}
    assert contestant.id in home_ids


def test_promote_to_next_level_no_longer_creates_bad_same_level_membership(db):
    """PHASE 10 (live promotion, not just the helper): reproduces the
    confirmed production defect end-to-end through the real
    promote_to_next_level path. A contestant already holds an active
    Continental membership at Round A (simulating a prior promotion this
    session doesn't know about). Promoting a DIFFERENT contestant's
    regional cohort at Round B to Continental must not leave contestant
    A's Round-A Continental membership coexisting with a newly created
    Round-B one for the SAME contestant if they get selected again --
    proven directly by re-promoting the SAME contestant from Round B's
    regional stage into Round B's continental stage while they still hold
    a stale active Round-A continental link."""
    contest = _contest(db, "t10", level=SeasonLevel.CONTINENT)
    round_a = _round(db, "t10-a")
    round_b = _round(db, "t10-b")

    continent_season_a = _season(db, round_a, contest, SeasonLevel.CONTINENT, "t10-cont-a")
    regional_season_b = _season(db, round_b, contest, SeasonLevel.REGIONAL, "t10-reg-b")
    continent_season_b = _season(db, round_b, contest, SeasonLevel.CONTINENT, "t10-cont-b")

    contestant = _contestant(db, suffix="t10", rnd=round_b, contest=contest)
    # Stale active Continental membership at a foreign round (A) -- the
    # exact contestant-96 shape.
    _membership(db, contestant=contestant, season=continent_season_a, is_active=True)
    # Genuine active Regional membership at their own round (B), about to
    # be promoted.
    _membership(db, contestant=contestant, season=regional_season_b, is_active=True)
    # promote_to_next_level's actual promotion pool requires vote evidence
    # (require_votes=True, unchanged existing behavior) -- unrelated to the
    # defect under test, just a precondition for being selected at all.
    _vote(db, suffix="t10", contestant=contestant, contest=contest, season=regional_season_b)
    db.commit()

    SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, contest.id, from_season_id=regional_season_b.id
    )
    db.commit()

    active_continent_rounds = _active_seasons(db, contestant.id, SeasonLevel.CONTINENT)
    assert active_continent_rounds == [round_b.id], (
        "promote_to_next_level left a stale foreign-round Continental "
        "membership active alongside the new one: "
        f"{active_continent_rounds}"
    )
