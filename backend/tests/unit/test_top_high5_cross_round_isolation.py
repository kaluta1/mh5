"""
Regression tests for cross-round candidate contamination in
SeasonMigrationService._contestants_for_contest_in_season and its caller
get_top_contestants_by_location (season_migration.py).

Bug (see KALUTASOCIETY_TOP_HIGH5_SYSTEMIC_DUPLICATE_FREEZE_AUDIT): when the
primary season-scoped active-membership query for a round's season finds
nobody -- the normal, expected outcome whenever a contest genuinely never
participated in that specific historical round -- both functions fell
through to a "vote rescue" tier meant to recover legacy rows with missing
ContestantSeason links. That tier's own first query is season-scoped and
safe; but once *that* is also empty, its second-tier query
(_contestant_ids_from_votes) drops season/round scoping entirely, returning
*every* contestant who ever voted in that contest_id, in *any* round. A
contestant genuinely belonging to Round A could therefore be silently
pulled into Round B's candidate set -- ranked, frozen into Top High5, and
even considered for promotion -- merely for sharing a contest_id, whenever
Round B genuinely has no evidence of its own for that contest (the common
case during a backfill sweep over every round, or for live promotion
whenever a from-season's real membership hasn't synced yet). Proven live
against production: 1054/1940 (54%) of all Top High5 rows were confirmed
invalid by this and the closely related premature-round defect, affecting
388 unique contestants.

Reachable from both backfill_top_high5_results.py AND, critically, the
live promote_to_next_level path (its main calls to
get_top_contestants_by_location never pass cohort_round_id) -- so this is
not merely historical residue, it can recreate the defect for any future
month.

Fix: both functions now resolve an "authoritative round" for the season
being processed (the caller's explicit cohort_round_id if given, otherwise
derived from the season's own ContestSeason.round_id -- every ContestSeason
belongs to exactly one Round) and require Contestant.round_id to match it
in the vote-rescue tier. When no authoritative round can be determined at
all, the vote-rescue tier does not run (fail closed) rather than risk an
unconstrained query.
"""
from __future__ import annotations

from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    Contestant,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService


def _user(db, suffix: str) -> User:
    user = User(email=f"th5xr-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str) -> Round:
    rnd = Round(name=f"Round {suffix}", status=RoundStatus.ACTIVE)
    db.add(rnd)
    db.flush()
    return rnd


def _season_for_round(db, rnd: Round, contest: Contest, level: SeasonLevel, suffix: str) -> ContestSeason:
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title=f"Season {suffix}", level=level)
    db.add(season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.flush()
    return season


def _contestant_no_season_link(db, *, suffix: str, rnd: Round, contest: Contest) -> Contestant:
    """A contestant with NO ContestantSeason row anywhere -- forces the
    primary season-scoped query to come up empty, so resolution must fall
    through to the vote-rescue tier under test."""
    owner = _user(db, suffix)
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Kenya",
        title=f"Contestant {suffix}",
    )
    db.add(contestant)
    db.flush()
    return contestant


def _vote(db, *, suffix: str, contestant: Contestant, contest: Contest, season: ContestSeason):
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


def _contest(db, suffix: str, level: SeasonLevel) -> Contest:
    contest = Contest(
        name=f"Contest {suffix}", contest_type="t", contest_mode="nomination", level=level.value
    )
    db.add(contest)
    db.flush()
    return contest


def test_empty_round_does_not_inherit_another_rounds_voter(db):
    """The core exploit, reproduced exactly: Round OLD has a contestant with
    real vote evidence under its own season. Round NEW is a genuinely
    different, untouched round for the SAME contest -- no votes, no active
    membership of its own. Resolving Round NEW must return empty, never
    Round OLD's contestant, no matter how the fallback tiers are ordered."""
    level = SeasonLevel.REGIONAL
    contest = _contest(db, "empty-round", level)
    round_old = _round(db, "old")
    round_new = _round(db, "new")
    season_old = _season_for_round(db, round_old, contest, level, "old")
    season_new = _season_for_round(db, round_new, contest, level, "new")

    contestant_old = _contestant_no_season_link(db, suffix="old", rnd=round_old, contest=contest)
    _vote(db, suffix="old", contestant=contestant_old, contest=contest, season=season_old)
    db.commit()

    result_new = SeasonMigrationService._contestants_for_contest_in_season(
        db, season_new.id, contest.id, active_only=True, qualified_only=False
    )
    assert result_new == [], (
        "Round NEW (no evidence of its own) incorrectly inherited Round OLD's "
        "contestant merely because they share a contest_id"
    )

    # Round OLD's own resolution must still correctly return its genuine
    # contestant -- this isn't a "remove all fallback" fix.
    result_old = SeasonMigrationService._contestants_for_contest_in_season(
        db, season_old.id, contest.id, active_only=True, qualified_only=False
    )
    assert {c.id for c in result_old} == {contestant_old.id}


def test_legitimate_same_round_vote_rescue_still_works(db):
    """A contestant with real vote evidence scoped to THIS round's own
    season, but no ContestantSeason link (the legacy-data-gap case this
    fallback exists for), must still be rescued -- the fix is round-scoped
    isolation, not fallback removal."""
    level = SeasonLevel.REGIONAL
    contest = _contest(db, "legit-rescue", level)
    rnd = _round(db, "solo")
    season = _season_for_round(db, rnd, contest, level, "solo")
    contestant = _contestant_no_season_link(db, suffix="solo", rnd=rnd, contest=contest)
    _vote(db, suffix="solo", contestant=contestant, contest=contest, season=season)
    db.commit()

    result = SeasonMigrationService._contestants_for_contest_in_season(
        db, season.id, contest.id, active_only=True, qualified_only=False
    )
    assert {c.id for c in result} == {contestant.id}


def test_two_rounds_same_contest_resolve_independently(db):
    """Round A and Round B, same contest, each with its own genuine
    contestant and vote evidence. Resolving either must return exactly its
    own contestant, never both -- baseline isolation that must hold
    regardless of insertion order or which round is processed first."""
    level = SeasonLevel.REGIONAL
    contest = _contest(db, "two-round", level)
    round_a = _round(db, "a")
    round_b = _round(db, "b")
    season_a = _season_for_round(db, round_a, contest, level, "a")
    season_b = _season_for_round(db, round_b, contest, level, "b")
    contestant_a = _contestant_no_season_link(db, suffix="a", rnd=round_a, contest=contest)
    contestant_b = _contestant_no_season_link(db, suffix="b", rnd=round_b, contest=contest)
    _vote(db, suffix="a", contestant=contestant_a, contest=contest, season=season_a)
    _vote(db, suffix="b", contestant=contestant_b, contest=contest, season=season_b)
    db.commit()

    result_a = SeasonMigrationService._contestants_for_contest_in_season(
        db, season_a.id, contest.id, active_only=True, qualified_only=False
    )
    result_b = SeasonMigrationService._contestants_for_contest_in_season(
        db, season_b.id, contest.id, active_only=True, qualified_only=False
    )
    assert {c.id for c in result_a} == {contestant_a.id}
    assert {c.id for c in result_b} == {contestant_b.id}


def test_get_top_contestants_by_location_excludes_foreign_round_voter(db):
    """The separate vote-rescue tier inside get_top_contestants_by_location
    itself (participation-mode style call, strict_season_scope=False) must
    have the same round isolation -- it has its own copy of this fallback,
    not just a delegation to _contestants_for_contest_in_season."""
    level = SeasonLevel.COUNTRY
    contest = _contest(db, "loc-empty", level)
    round_old = _round(db, "loc-old")
    round_new = _round(db, "loc-new")
    season_old = _season_for_round(db, round_old, contest, level, "loc-old")
    season_new = _season_for_round(db, round_new, contest, level, "loc-new")
    contestant_old = _contestant_no_season_link(db, suffix="loc-old", rnd=round_old, contest=contest)
    _vote(db, suffix="loc-old", contestant=contestant_old, contest=contest, season=season_old)
    db.commit()

    grouped = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season_new.id,
        "country",
        contest_id=contest.id,
        diagnostics=False,
        active_links_only=True,
        qualified_only=False,
        strict_season_scope=False,
        require_votes=False,
    )
    found_ids = {c.id for members in grouped.values() for c in members}
    assert contestant_old.id not in found_ids


def test_promote_to_next_level_does_not_pull_foreign_round_contestant(db):
    """End-to-end: promoting a genuinely empty Round NEW (same contest as
    Round OLD, which has a real contestant) must not freeze, promote, or
    otherwise surface Round OLD's contestant under Round NEW -- the live
    promotion write paths (disqualification cleanup, stale-destination
    pruning) share the same underlying resolver this fix closes."""
    level = SeasonLevel.COUNTRY
    contest = _contest(db, "promo-empty", level)
    round_old = _round(db, "promo-old")
    round_new = _round(db, "promo-new")
    season_old = _season_for_round(db, round_old, contest, level, "promo-old")
    season_new = _season_for_round(db, round_new, contest, level, "promo-new")
    contestant_old = _contestant_no_season_link(db, suffix="promo-old", rnd=round_old, contest=contest)
    _vote(db, suffix="promo-old", contestant=contestant_old, contest=contest, season=season_old)
    was_qualified_before = contestant_old.is_qualified
    db.commit()

    result = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, contest.id, from_season_id=season_new.id
    )
    db.commit()

    promoted_ids = set(result.get("promoted_contestant_ids") or [])
    assert contestant_old.id not in promoted_ids

    frozen_rows = (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == contest.id, TopHigh5Result.level == SeasonLevel.COUNTRY)
        .all()
    )
    assert contestant_old.id not in {r.contestant_id for r in frozen_rows}, (
        "Round OLD's contestant was frozen into Round NEW's Top High5"
    )

    db.refresh(contestant_old)
    assert contestant_old.is_qualified == was_qualified_before, (
        "processing Round NEW incorrectly changed Round OLD's contestant's own qualification state"
    )
