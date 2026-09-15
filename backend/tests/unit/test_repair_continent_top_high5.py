"""
Tests for scripts/repair_continent_top_high5.py -- the explicitly-approved,
additive-only repair for CONTINENT-level top_high5_results groups whose
`migrated=True` set is missing real GLOBAL destination-season members (see
the 2026-09-15 production reconciliation audit and its repair preflight, in
KALUTASOCIETY memory).

Imports the script directly (it lives in backend/scripts/, not backend/app/)
so every assertion runs against the exact same functions the CLI uses --
no subprocess, no duplicated logic.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
THIS_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_TEST_DIR not in sys.path:
    sys.path.insert(0, THIS_TEST_DIR)

from repair_continent_top_high5 import (  # noqa: E402
    RepairAbort,
    discover_group_plan,
    run_repair,
)

from app.models.contest import Contest  # noqa: E402
from app.models.contests import (  # noqa: E402
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, RoundStatus  # noqa: E402
from app.models.user import User  # noqa: E402


def _user(db, suffix: str) -> User:
    user = User(email=f"repair-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str) -> Round:
    rnd = Round(
        name=f"Round {suffix}",
        status=RoundStatus.ACTIVE,
        submission_start_date=date.today(),
        submission_end_date=date.today(),
    )
    db.add(rnd)
    db.flush()
    return rnd


def _continent_scope(db, rnd: Round, *, suffix: str, contest_level: str = "continent"):
    contest = Contest(
        name=f"Contest {suffix}", contest_type="t", contest_mode="nomination", level=contest_level
    )
    db.add(contest)
    db.flush()
    source_season = ContestSeason(round_id=rnd.id, title=f"Continent {suffix}", level=SeasonLevel.CONTINENT)
    db.add(source_season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=source_season.id, is_active=True))
    dest_season = ContestSeason(round_id=rnd.id, title=f"Global {suffix}", level=SeasonLevel.GLOBAL)
    db.add(dest_season)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=dest_season.id, is_active=True))
    db.flush()
    return contest, source_season, dest_season


def _contestant(
    db,
    *,
    suffix: str,
    rnd: Round,
    contest: Contest,
    continent: str,
    active_in_dest: "ContestSeason | None" = None,
    active_in_source: "ContestSeason | None" = None,
) -> Contestant:
    owner = _user(db, suffix)
    c = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        continent=continent,
        title=f"Contestant {suffix}",
    )
    db.add(c)
    db.flush()
    if active_in_source is not None:
        db.add(ContestantSeason(contestant_id=c.id, season_id=active_in_source.id, is_active=True))
    if active_in_dest is not None:
        db.add(ContestantSeason(contestant_id=c.id, season_id=active_in_dest.id, is_active=True))
    db.flush()
    return c


def _existing_row(db, *, contest, source_season, dest_season, contestant, jurisdiction, rank, migrated):
    row = TopHigh5Result(
        contestant_id=contestant.id,
        contest_id=contest.id,
        category_id=contest.category_id,
        level=SeasonLevel.CONTINENT,
        jurisdiction=jurisdiction,
        round_id=source_season.round_id,
        from_season_id=source_season.id,
        to_season_id=dest_season.id,
        rank=rank,
        migrated=migrated,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# 1. Uses actual migration membership, not current vote ranking
# ---------------------------------------------------------------------------


def test_uses_destination_membership_not_vote_ranking(db):
    """The reconstructed target set must come from real active
    ContestantSeason membership in the destination, never from a
    votes-based ranking (that method is REJECTED per the audit)."""
    rnd = _round(db, "membership")
    contest, source, dest = _continent_scope(db, rnd, suffix="membership")
    a = _contestant(db, suffix="a", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    # b has huge current votes but never actually migrated -- must NOT appear
    b = _contestant(db, suffix="b", rnd=rnd, contest=contest, continent="Africa", active_in_source=source)
    db.commit()

    plan = discover_group_plan(db, contest.id, rnd.id)
    bucket = plan.buckets[0]
    assert bucket.jurisdiction == "Africa"
    assert bucket.target_contestant_ids == [a.id]
    assert b.id not in bucket.target_contestant_ids


def test_current_vote_recomputation_not_used(db):
    """Explicitly proves no vote/points data influences bucket membership --
    only ContestantSeason.is_active in the destination season does."""
    from app.models.voting import ContestantVoting

    rnd = _round(db, "novotes")
    contest, source, dest = _continent_scope(db, rnd, suffix="novotes")
    winner = _contestant(db, suffix="winner", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    heavy_voter_target = _contestant(
        db, suffix="heavy", rnd=rnd, contest=contest, continent="Africa", active_in_source=source
    )
    voter = _user(db, "voter")
    db.add(
        ContestantVoting(
            user_id=voter.id,
            contestant_id=heavy_voter_target.id,
            contest_id=contest.id,
            season_id=source.id,
            vote_bucket_key="ty::",
            position=1,
            points=99999,
        )
    )
    db.commit()

    plan = discover_group_plan(db, contest.id, rnd.id)
    bucket = plan.buckets[0]
    assert bucket.target_contestant_ids == [winner.id]


# ---------------------------------------------------------------------------
# 2/3. Inactive source-season membership does not remove a legitimate promotee
# ---------------------------------------------------------------------------


def test_inactive_source_membership_does_not_block_repair(db):
    """The exact production defect: a real promotee has is_active=False at
    the CONTINENT source (normal after promotion) but is_active=True at the
    GLOBAL destination -- the repair must still find and add them."""
    rnd = _round(db, "inactive")
    contest, source, dest = _continent_scope(db, rnd, suffix="inactive")
    promotee = _contestant(db, suffix="promotee", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    # simulate: was active at source at promotion time, now deactivated
    db.add(ContestantSeason(contestant_id=promotee.id, season_id=source.id, is_active=False))
    db.commit()

    plan = discover_group_plan(db, contest.id, rnd.id)
    bucket = plan.buckets[0]
    assert bucket.status == "READY"
    assert promotee.id in bucket.to_insert_contestant_ids


# ---------------------------------------------------------------------------
# 4/5/6. Bucket size boundaries
# ---------------------------------------------------------------------------


def test_one_member_bucket(db):
    rnd = _round(db, "one")
    contest, source, dest = _continent_scope(db, rnd, suffix="one")
    a = _contestant(db, suffix="a", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    db.commit()

    plan = discover_group_plan(db, contest.id, rnd.id)
    bucket = plan.buckets[0]
    assert bucket.status == "READY"
    assert bucket.target_contestant_ids == [a.id]


def test_exactly_five_member_bucket(db):
    rnd = _round(db, "five")
    contest, source, dest = _continent_scope(db, rnd, suffix="five")
    members = [
        _contestant(db, suffix=f"m{i}", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
        for i in range(5)
    ]
    db.commit()

    plan = discover_group_plan(db, contest.id, rnd.id)
    bucket = plan.buckets[0]
    assert bucket.status == "READY"
    assert set(bucket.target_contestant_ids) == {m.id for m in members}
    assert len(bucket.target_contestant_ids) == 5


def test_over_five_members_refuses_repair(db):
    """Must never arbitrarily pick five -- refuse and skip instead."""
    rnd = _round(db, "sixplus")
    contest, source, dest = _continent_scope(db, rnd, suffix="sixplus")
    for i in range(6):
        _contestant(db, suffix=f"m{i}", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    db.commit()

    plan = discover_group_plan(db, contest.id, rnd.id)
    bucket = plan.buckets[0]
    assert bucket.status == "SKIPPED_OVER_CAP"
    assert bucket.target_contestant_ids == []
    assert bucket.to_insert_contestant_ids == []


# ---------------------------------------------------------------------------
# 7/8/9/10. Refusal / rejection scopes
# ---------------------------------------------------------------------------


def test_missing_destination_evidence_refuses_repair(db):
    """No GLOBAL season linked at all for this contest+round -> report and
    skip the whole group, never fall back to vote recomputation."""
    rnd = _round(db, "noglobal")
    contest = Contest(name="Contest noglobal", contest_type="t", contest_mode="nomination", level="continent")
    db.add(contest)
    db.flush()
    source = ContestSeason(round_id=rnd.id, title="Continent noglobal", level=SeasonLevel.CONTINENT)
    db.add(source)
    db.flush()
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=source.id, is_active=True))
    db.commit()
    # deliberately no GLOBAL season / link created

    plan = discover_group_plan(db, contest.id, rnd.id)
    assert plan.status == "SKIPPED_NO_SEASON_EVIDENCE"
    assert plan.buckets == []


def test_wrong_round_rejected(db):
    """A contest's CONTINENT season for round A must never be used to
    satisfy a repair target naming round B."""
    rnd_a = _round(db, "ra")
    rnd_b = _round(db, "rb")
    contest, source, dest = _continent_scope(db, rnd_a, suffix="wronground")
    _contestant(db, suffix="a", rnd=rnd_a, contest=contest, continent="Africa", active_in_dest=dest)
    db.commit()

    plan_wrong_round = discover_group_plan(db, contest.id, rnd_b.id)
    assert plan_wrong_round.status == "SKIPPED_NO_SEASON_EVIDENCE"

    plan_right_round = discover_group_plan(db, contest.id, rnd_a.id)
    assert plan_right_round.status == "READY"


def test_wrong_jurisdiction_rejected(db):
    """A repair for jurisdiction 'Africa' must never pull in a real 'Europe'
    member -- each jurisdiction bucket is scoped strictly by the
    contestant's own continent field."""
    rnd = _round(db, "geo")
    contest, source, dest = _continent_scope(db, rnd, suffix="geo")
    africa = _contestant(db, suffix="africa", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    europe = _contestant(db, suffix="europe", rnd=rnd, contest=contest, continent="Europe", active_in_dest=dest)
    db.commit()

    plan = discover_group_plan(db, contest.id, rnd.id)
    by_jurisdiction = {b.jurisdiction: b for b in plan.buckets}
    assert by_jurisdiction["Africa"].target_contestant_ids == [africa.id]
    assert by_jurisdiction["Europe"].target_contestant_ids == [europe.id]


def test_cross_category_contestant_rejected(db):
    """A contestant belonging to a different contest (different category)
    must never be pulled into this contest's repair, even if active in the
    same physical destination season row (e.g. two contests sharing a
    pooled regional/global season)."""
    rnd = _round(db, "crosscat")
    contest_a, source_a, dest_a = _continent_scope(db, rnd, suffix="crosscat-a")
    contest_b, source_b, dest_b = _continent_scope(db, rnd, suffix="crosscat-b")
    real_member = _contestant(db, suffix="real", rnd=rnd, contest=contest_a, continent="Africa", active_in_dest=dest_a)
    # belongs to contest_b, but happens to be active in the SAME dest_a season id space is avoided
    # by construction (separate season objects) -- assert it never leaks into contest_a's plan.
    other_contest_member = _contestant(
        db, suffix="other", rnd=rnd, contest=contest_b, continent="Africa", active_in_dest=dest_b
    )
    db.commit()

    plan_a = discover_group_plan(db, contest_a.id, rnd.id)
    assert plan_a.buckets[0].target_contestant_ids == [real_member.id]
    assert other_contest_member.id not in plan_a.buckets[0].target_contestant_ids


# ---------------------------------------------------------------------------
# 11. Existing normal write-once freeze behavior remains unchanged
# ---------------------------------------------------------------------------


def test_normal_freeze_write_once_guard_unchanged(db):
    """SeasonMigrationService._freeze_top_high5_results' write-once guard is
    untouched by this repair tool -- a second promotion call still no-ops."""
    from app.services.season_migration import SeasonMigrationService

    rnd = _round(db, "writeonce")
    contest, source, dest = _continent_scope(db, rnd, suffix="writeonce")
    a = _contestant(db, suffix="a", rnd=rnd, contest=contest, continent="Africa")
    db.add(ContestantSeason(contestant_id=a.id, season_id=source.id, is_active=True))
    db.commit()

    written_first = SeasonMigrationService._freeze_top_high5_results(
        db,
        level=SeasonLevel.CONTINENT,
        jurisdiction="Africa",
        contest=contest,
        from_season=source,
        to_season=dest,
        ranked_contestants=[a],
    )
    db.commit()
    assert written_first == 1

    written_second = SeasonMigrationService._freeze_top_high5_results(
        db,
        level=SeasonLevel.CONTINENT,
        jurisdiction="Africa",
        contest=contest,
        from_season=source,
        to_season=dest,
        ranked_contestants=[a],
    )
    db.commit()
    assert written_second == 0
    assert (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == contest.id, TopHigh5Result.level == SeasonLevel.CONTINENT)
        .count()
        == 1
    )


# ---------------------------------------------------------------------------
# 12/13/14/15/16. run_repair: dry-run, transactional apply, aborts, allowlist
# ---------------------------------------------------------------------------


def test_dry_run_performs_zero_writes(db):
    rnd = _round(db, "dryrun")
    contest, source, dest = _continent_scope(db, rnd, suffix="dryrun")
    a = _contestant(db, suffix="a", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    db.commit()
    before = db.query(TopHigh5Result).count()

    result = run_repair(db, [{"contest_id": contest.id, "round_id": rnd.id}], apply=False)

    assert result["applied"] is False
    assert result["aborted"] is False
    after = db.query(TopHigh5Result).count()
    assert after == before == 0
    assert result["report"]["ROWS_TO_INSERT"] == 1
    assert result["report"]["EXPECTED_TOTAL_ROWS_AFTER_REPAIR"] == before + 1


def test_apply_path_is_transactional_and_never_deletes(db):
    rnd = _round(db, "apply")
    contest, source, dest = _continent_scope(db, rnd, suffix="apply")
    keep = _contestant(db, suffix="keep", rnd=rnd, contest=contest, continent="Africa")
    missing = _contestant(db, suffix="missing", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    # a legitimate non-migrated row that must survive the repair untouched
    _existing_row(
        db, contest=contest, source_season=source, dest_season=dest, contestant=keep, jurisdiction="Africa",
        rank=1, migrated=False,
    )
    db.commit()
    current_total = db.query(TopHigh5Result).count()
    assert current_total == 1

    result = run_repair(
        db,
        [{"contest_id": contest.id, "round_id": rnd.id}],
        apply=True,
        expected_current_total=current_total,
    )

    assert result["aborted"] is False
    assert result["applied"] is True
    assert result["rows_inserted"] == 1
    rows = (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == contest.id, TopHigh5Result.level == SeasonLevel.CONTINENT)
        .order_by(TopHigh5Result.rank)
        .all()
    )
    assert len(rows) == 2
    kept_row = next(r for r in rows if r.contestant_id == keep.id)
    assert kept_row.migrated is False  # untouched, never deleted or flipped
    new_row = next(r for r in rows if r.contestant_id == missing.id)
    assert new_row.migrated is True
    assert new_row.rank != kept_row.rank  # no unique-constraint collision


def test_unexpected_target_count_causes_rollback(db):
    rnd = _round(db, "badtotal")
    contest, source, dest = _continent_scope(db, rnd, suffix="badtotal")
    _contestant(db, suffix="a", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    db.commit()
    real_total = db.query(TopHigh5Result).count()

    result = run_repair(
        db,
        [{"contest_id": contest.id, "round_id": rnd.id}],
        apply=True,
        expected_current_total=real_total + 5,  # deliberately wrong
    )

    assert result["aborted"] is True
    assert "current total mismatch" in result["abort_reason"]
    assert db.query(TopHigh5Result).count() == real_total  # nothing written


def test_unexpected_snapshot_membership_causes_rollback(db):
    """If the set of rows that would be updated has changed since a prior
    snapshot was captured, abort rather than proceed on stale evidence."""
    rnd = _round(db, "stale")
    contest, source, dest = _continent_scope(db, rnd, suffix="stale")
    member = _contestant(db, suffix="m", rnd=rnd, contest=contest, continent="Africa", active_in_dest=dest)
    existing = _existing_row(
        db, contest=contest, source_season=source, dest_season=dest, contestant=member, jurisdiction="Africa",
        rank=1, migrated=False,  # misflagged -- should be promoted to True
    )
    db.commit()
    current_total = db.query(TopHigh5Result).count()

    stale_snapshot = {"rows_to_be_updated": [{"id": existing.id + 999}]}  # doesn't match reality

    result = run_repair(
        db,
        [{"contest_id": contest.id, "round_id": rnd.id}],
        apply=True,
        expected_current_total=current_total,
        expected_snapshot=stale_snapshot,
    )

    assert result["aborted"] is True
    assert "changed since the supplied snapshot" in result["abort_reason"]
    row = db.query(TopHigh5Result).filter(TopHigh5Result.id == existing.id).one()
    assert row.migrated is False  # untouched


def test_repair_cannot_touch_a_group_outside_the_allowlist(db):
    """Only explicitly-listed (contest_id, round_id) pairs are ever
    examined or written -- a second, real, equally-broken group not in the
    allowlist must be left completely alone."""
    rnd = _round(db, "scope")
    approved_contest, approved_source, approved_dest = _continent_scope(db, rnd, suffix="approved")
    other_contest, other_source, other_dest = _continent_scope(db, rnd, suffix="other")
    _contestant(db, suffix="a", rnd=rnd, contest=approved_contest, continent="Africa", active_in_dest=approved_dest)
    _contestant(db, suffix="b", rnd=rnd, contest=other_contest, continent="Africa", active_in_dest=other_dest)
    db.commit()
    current_total = db.query(TopHigh5Result).count()

    result = run_repair(
        db,
        [{"contest_id": approved_contest.id, "round_id": rnd.id}],  # other_contest NOT included
        apply=True,
        expected_current_total=current_total,
    )

    assert result["applied"] is True
    assert (
        db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == approved_contest.id).count() == 1
    )
    assert db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == other_contest.id).count() == 0


# ---------------------------------------------------------------------------
# 17/18/19. Unrelated behavior unchanged
# ---------------------------------------------------------------------------


def test_country_backfill_behavior_unchanged(db):
    """COUNTRY reconstruction still goes through the original, unmodified
    _groups_from_actual_migration default (cap=5) -- the repair tool's
    cap=None extension must not change any existing caller's behavior."""
    from backfill_top_high5_results import _groups_from_actual_migration

    rnd = _round(db, "country-unchanged")
    contest = Contest(name="Contest country", contest_type="t", contest_mode="nomination", level="country")
    db.add(contest)
    db.flush()
    dest_season = ContestSeason(round_id=rnd.id, title="Regional country-unchanged", level=SeasonLevel.REGIONAL)
    db.add(dest_season)
    db.flush()
    members = []
    for i in range(7):  # more than 5 -- must still silently cap by default
        owner = _user(db, f"country-{i}")
        c = Contestant(
            user_id=owner.id, round_id=rnd.id, contest_id=contest.id, is_active=True, is_deleted=False,
            is_qualified=True, country="Tanzania", title=f"C{i}",
        )
        db.add(c)
        db.flush()
        db.add(ContestantSeason(contestant_id=c.id, season_id=dest_season.id, is_active=True))
        members.append(c)
    db.commit()

    capped = _groups_from_actual_migration(db, contest, dest_season, "country")
    assert len(capped["Tanzania"]) == 5  # unchanged default behavior

    uncapped = _groups_from_actual_migration(db, contest, dest_season, "country", cap=None)
    assert len(uncapped["Tanzania"]) == 7  # new, opt-in only


def test_regional_backfill_behavior_unchanged(db):
    """REGIONAL still uses the exact-reconstruction path untouched by any
    of this session's changes (only CONTINENT's dispatch changed)."""
    from backfill_top_high5_results import _groups_from_actual_migration

    rnd = _round(db, "regional-unchanged")
    contest = Contest(name="Contest regional", contest_type="t", contest_mode="nomination", level="regional")
    db.add(contest)
    db.flush()
    dest_season = ContestSeason(round_id=rnd.id, title="Continent regional-unchanged", level=SeasonLevel.CONTINENT)
    db.add(dest_season)
    db.flush()
    owner = _user(db, "regional-1")
    c = Contestant(
        user_id=owner.id, round_id=rnd.id, contest_id=contest.id, is_active=True, is_deleted=False,
        is_qualified=True, region="East Africa", title="R1",
    )
    db.add(c)
    db.flush()
    db.add(ContestantSeason(contestant_id=c.id, season_id=dest_season.id, is_active=True))
    db.commit()

    grouped = _groups_from_actual_migration(db, contest, dest_season, "region")
    assert grouped == {"East Africa": [c]}


def test_live_go_forward_freeze_path_unchanged(db):
    """promote_to_next_level's own freeze call is untouched by this
    session's changes. Reuses test_top_high5_frozen_results.py's own
    fixture helpers (proven, exact working setup for this exact call)
    rather than a re-derived one, so this test is a faithful re-run of that
    existing, still-passing property -- not a new, independently-fallible
    reconstruction of it."""
    from app.services.season_migration import SeasonMigrationService
    from test_top_high5_frozen_results import _contestant as _frozen_contestant
    from test_top_high5_frozen_results import _country_scope, _round as _frozen_round, _vote

    rnd = _frozen_round(db, "livepath", months_ago=4)
    contest, season = _country_scope(db, rnd, suffix="livepath")
    a = _frozen_contestant(db, suffix="livepath-a", rnd=rnd, contest=contest, season=season, country="Tanzania")
    _vote(db, suffix="livepath-a", contestant=a, contest=contest, season=season, points=10)
    db.commit()

    result = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, contest.id, from_season_id=season.id
    )
    db.commit()
    assert result.get("promoted_count") == 1
    frozen = (
        db.query(TopHigh5Result)
        .filter(TopHigh5Result.contest_id == contest.id, TopHigh5Result.level == SeasonLevel.COUNTRY)
        .all()
    )
    assert len(frozen) == 1
    assert frozen[0].contestant_id == a.id
    assert frozen[0].migrated is True
