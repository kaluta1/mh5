"""
Regression tests for the Top High5 zero-vote inclusion fix
(app/api/api_v1/endpoints/season_migration.py::get_top_high5_by_country).

Background: a read-only production audit (2026-09-11, see
kalutasociety-tophigh5-zero-votes-season262 memory) proved that
`GET /api/v1/seasons/top-high5` returned an empty leaderboard for entire
rounds -- not because contestants or contest/season/link structure were
missing (they were confirmed present and correctly resolved), but because
`aggregate_rankings(..., require_votes=True)` dropped every candidate with
zero `contestant_voting` rows, and the affected season had none at all. The
fix changes that one call site (inside `_build_rows_for_group`) to
`require_votes=False`: the candidate set is already fully constrained by
round/level/contest/roster resolution *before* ranking runs, so a zero-vote
member of that set is a genuine contestant, not a data error, and now stays
visible with a zero score instead of being silently dropped.

This file proves, end-to-end through the real HTTP route (not just the
ranking helper in isolation): zero-vote inclusion, that voted contestants
still rank above zero-vote ones, that the existing contest_id resolver
protections (contestant_contest_resolution.py) are untouched, and -- most
importantly -- that none of this weakens the requested `round_id` boundary:
a contestant from a different round can never appear, regardless of how many
votes or how much engagement it has.
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
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.models.voting import ContestantVoting


def _user(db, suffix: str) -> User:
    user = User(email=f"th5zv-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str, month: int) -> Round:
    start = date(2026, month, 1)
    end = start + timedelta(days=27)
    rnd = Round(
        name=f"Round {suffix}",
        status=RoundStatus.ACTIVE,
        submission_start_date=start,
        submission_end_date=end,
    )
    db.add(rnd)
    db.flush()
    return rnd


def _country_scope(db, rnd: Round, *, suffix: str):
    """One active nomination contest, linked into `rnd`, with an active
    country-level season/link -- the minimal wiring the endpoint needs to
    consider a contest at all."""
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


def _contestant(
    db,
    *,
    suffix: str,
    rnd: Round,
    contest: Contest,
    season: ContestSeason,
    country: str,
    resolved: bool = True,
) -> Contestant:
    """A candidate whose contest mapping is resolved via Case A (contest_id
    set directly) unless `resolved=False`, in which case it is left as an
    ambiguous genuine-season reference (no contest_id, no unique link) so it
    must stay excluded regardless of the zero-vote-inclusion fix."""
    owner = _user(db, suffix)
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id if resolved else None,
        season_id=None if resolved else season.id,
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


def _vote(db, *, suffix: str, contestant: Contestant, contest: Contest, season: ContestSeason):
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
            points=5,
        )
    )
    db.flush()


def _all_contestant_ids(payload) -> set[int]:
    return {row["contestant_id"] for c in payload["contests"] for row in c["rows"]}


def _fetch(client, *, round_id: int, country: str, level: str = "country"):
    resp = client.get(
        f"/api/v1/seasons/top-high5?round_id={round_id}&country={country}&level={level}"
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_zero_vote_current_round_contestant_is_included(client, db):
    """TEST 1: a genuine current-round contestant with zero votes must appear
    -- this is the exact production bug (Tanzania / round 28 / season 262)."""
    rnd = _round(db, "t1", month=9)
    contest, season = _country_scope(db, rnd, suffix="t1")
    contestant = _contestant(
        db, suffix="t1", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    db.commit()

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert contestant.id in ids

    row = next(
        r for c in payload["contests"] for r in c["rows"] if r["contestant_id"] == contestant.id
    )
    assert row["votes_count"] == 0
    assert row["stars_points"] == 0
    assert row["migrates_next_stage"] is False


def test_voted_current_round_contestant_is_included_and_scored(client, db):
    """TEST 2: a voted current-round contestant is included and keeps using
    the existing points/vote-count calculation, unchanged by this fix."""
    rnd = _round(db, "t2", month=9)
    contest, season = _country_scope(db, rnd, suffix="t2")
    contestant = _contestant(
        db, suffix="t2", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    _vote(db, suffix="t2", contestant=contestant, contest=contest, season=season)
    db.commit()

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    row = next(
        r for c in payload["contests"] for r in c["rows"] if r["contestant_id"] == contestant.id
    )
    assert row["votes_count"] == 1
    assert row["stars_points"] == 5
    assert row["migrates_next_stage"] is True


def test_mixed_voted_and_zero_vote_contestants_both_eligible_and_ranked(client, db):
    """TEST 3: voted and zero-vote current-round contestants are both
    eligible, and the voted one ranks strictly above the zero-vote one under
    the existing scoring rule -- the fix adds eligibility, it does not change
    how eligible candidates are ordered."""
    rnd = _round(db, "t3", month=9)
    contest, season = _country_scope(db, rnd, suffix="t3")
    voted = _contestant(
        db, suffix="t3-voted", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    zero = _contestant(
        db, suffix="t3-zero", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    _vote(db, suffix="t3", contestant=voted, contest=contest, season=season)
    db.commit()

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert {voted.id, zero.id} <= ids

    rows = [r for c in payload["contests"] for r in c["rows"]]
    ranks = {r["contestant_id"]: r["rank"] for r in rows}
    assert ranks[voted.id] < ranks[zero.id]


def test_different_round_voted_contestant_is_excluded(client, db):
    """TEST 4: a contestant belonging to a DIFFERENT round, even with real
    votes, must never appear in the requested round's results -- the
    candidate set is built strictly from the requested round's own roster
    before ranking ever runs."""
    target_round = _round(db, "t4-target", month=9)
    target_contest, target_season = _country_scope(db, target_round, suffix="t4-target")
    target_contestant = _contestant(
        db,
        suffix="t4-target",
        rnd=target_round,
        contest=target_contest,
        season=target_season,
        country="Tanzania",
    )

    other_round = _round(db, "t4-other", month=8)
    other_contest, other_season = _country_scope(db, other_round, suffix="t4-other")
    other_contestant = _contestant(
        db,
        suffix="t4-other",
        rnd=other_round,
        contest=other_contest,
        season=other_season,
        country="Tanzania",
    )
    _vote(db, suffix="t4-other", contestant=other_contestant, contest=other_contest, season=other_season)
    db.commit()

    payload = _fetch(client, round_id=target_round.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert target_contestant.id in ids
    assert other_contestant.id not in ids


def test_different_round_high_engagement_contestant_is_still_excluded(client, db):
    """TEST 5: a different-round contestant with the strongest possible
    ranking signal (multiple votes) is still excluded -- proving the round
    boundary is structural (candidate-set membership), not a side effect of
    the ranking/scoring comparison."""
    target_round = _round(db, "t5-target", month=9)
    target_contest, target_season = _country_scope(db, target_round, suffix="t5-target")
    target_contestant = _contestant(
        db,
        suffix="t5-target",
        rnd=target_round,
        contest=target_contest,
        season=target_season,
        country="Tanzania",
    )

    other_round = _round(db, "t5-other", month=7)
    other_contest, other_season = _country_scope(db, other_round, suffix="t5-other")
    other_contestant = _contestant(
        db,
        suffix="t5-other",
        rnd=other_round,
        contest=other_contest,
        season=other_season,
        country="Tanzania",
    )
    for i in range(5):
        _vote(db, suffix=f"t5-other-{i}", contestant=other_contestant, contest=other_contest, season=other_season)
    db.commit()

    payload = _fetch(client, round_id=target_round.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert target_contestant.id in ids
    assert other_contestant.id not in ids


def test_correct_round_wrong_country_is_excluded(client, db):
    """TEST 6: a same-round, zero-vote contestant whose country does not
    match the requested one stays excluded -- country filtering is unrelated
    to and unweakened by the zero-vote-inclusion fix."""
    rnd = _round(db, "t6", month=9)
    contest, season = _country_scope(db, rnd, suffix="t6")
    wrong_country = _contestant(
        db, suffix="t6", rnd=rnd, contest=contest, season=season, country="Kenya"
    )
    db.commit()

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert wrong_country.id not in ids


def test_case_a_resolved_contestant_with_ambiguous_season_still_included_zero_votes(client, db):
    """TEST 7: Case A (contestant.contest_id set directly) remains
    authoritative and wins even when the contestant's season also links to a
    second, unrelated contest (which would otherwise make the season
    reference ambiguous) -- and the now-included zero-vote contestant is
    still correctly scoped to the contest its contest_id names, not the
    sibling one."""
    rnd = _round(db, "t7", month=9)
    contest, season = _country_scope(db, rnd, suffix="t7")
    sibling_contest = Contest(
        name="Sibling Contest t7", contest_type="t", contest_mode="nomination", level="country"
    )
    db.add(sibling_contest)
    db.flush()
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=sibling_contest.id))
    db.add(ContestSeasonLink(contest_id=sibling_contest.id, season_id=season.id, is_active=True))
    db.flush()

    contestant = _contestant(
        db, suffix="t7", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    db.commit()

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")

    contest_group = next(c for c in payload["contests"] if c["contest_id"] == contest.id)
    sibling_group = next(
        (c for c in payload["contests"] if c["contest_id"] == sibling_contest.id), None
    )
    assert contestant.id in {r["contestant_id"] for r in contest_group["rows"]}
    if sibling_group is not None:
        assert contestant.id not in {r["contestant_id"] for r in sibling_group["rows"]}


def test_ambiguous_unresolved_contestant_mapping_is_excluded(client, db):
    """TEST 8: a genuine season-linked contestant whose season links to
    MULTIPLE active contests, with no contest_id and no vote evidence, has no
    authoritative signal (contestant_contest_resolution.py, Cases A-D all
    fail) and must stay excluded -- the zero-vote-inclusion fix only widens
    who ranks once inside a resolved roster, it does not resolve ambiguous
    mappings."""
    rnd = _round(db, "t8", month=9)
    contest_a, season = _country_scope(db, rnd, suffix="t8-a")
    contest_b = Contest(
        name="Contest t8-b", contest_type="t", contest_mode="nomination", level="country"
    )
    db.add(contest_b)
    db.flush()
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest_b.id))
    db.add(ContestSeasonLink(contest_id=contest_b.id, season_id=season.id, is_active=True))
    db.flush()

    ambiguous = _contestant(
        db,
        suffix="t8",
        rnd=rnd,
        contest=contest_a,
        season=season,
        country="Tanzania",
        resolved=False,
    )
    db.commit()

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert ambiguous.id not in ids


def test_tanzania_round28_equivalent_zero_vote_dataset_returns_genuine_results(client, db):
    """TEST 9: the actual production scenario at realistic scale -- several
    genuine current-round contestants, all zero votes, no fallback data of
    any kind. Before this fix, this returned an empty leaderboard for the
    whole round; after it, every genuine contestant is visible."""
    rnd = _round(db, "t9", month=9)
    contest, season = _country_scope(db, rnd, suffix="t9")
    contestants = [
        _contestant(
            db, suffix=f"t9-{i}", rnd=rnd, contest=contest, season=season, country="Tanzania"
        )
        for i in range(4)
    ]
    db.commit()

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert {c.id for c in contestants} <= ids
    assert payload["contests"], "expected at least one non-empty contest group"


def test_no_cross_round_fallback_when_requested_round_has_no_voted_contestants(client, db):
    """TEST 10: when the requested round has candidates but none of them have
    votes, the response must be built purely from that round's own (now
    zero-score-eligible) roster -- never padded out, replaced, or
    supplemented with a different round's voted contestants. No 'any round' /
    historical / previous-round fallback exists in this code path (confirmed
    by inspection: get_top_contestants_by_location's only such fallback is
    gated by strict_season_scope=True, which every Top High5 call site
    passes, disabling it)."""
    target_round = _round(db, "t10-target", month=9)
    target_contest, target_season = _country_scope(db, target_round, suffix="t10-target")
    target_zero_vote = _contestant(
        db,
        suffix="t10-target",
        rnd=target_round,
        contest=target_contest,
        season=target_season,
        country="Tanzania",
    )

    other_round = _round(db, "t10-other", month=6)
    other_contest, other_season = _country_scope(db, other_round, suffix="t10-other")
    other_voted = _contestant(
        db,
        suffix="t10-other",
        rnd=other_round,
        contest=other_contest,
        season=other_season,
        country="Tanzania",
    )
    _vote(db, suffix="t10-other", contestant=other_voted, contest=other_contest, season=other_season)
    db.commit()

    payload = _fetch(client, round_id=target_round.id, country="Tanzania")
    assert payload["round_id"] == target_round.id
    ids = _all_contestant_ids(payload)
    assert ids == {target_zero_vote.id}
