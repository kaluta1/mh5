"""
Regression tests for zero-vote inclusion in frozen Top High5 results.

Background: a read-only production audit (2026-09-11, see
kalutasociety-tophigh5-zero-votes-season262 memory) proved that
`GET /api/v1/seasons/top-high5` returned an empty leaderboard for entire
rounds because ranking dropped every candidate with zero `contestant_voting`
rows. That was fixed by ranking with `require_votes=False`.

A later, larger change (the Top High5 functional-spec rework) moved the
endpoint from live-computing rankings on every request to reading frozen
results written once, when a level's voting closes
(SeasonMigrationService._freeze_top_high5_results, invoked from
promote_to_next_level). The zero-vote-inclusion property now lives in that
freeze step instead of the endpoint, so these tests seed a COUNTRY-level
roster, run the real promotion (which freezes COUNTRY as a side effect),
then assert on what the endpoint serves from the frozen table -- proving
zero-vote inclusion survives the freeze, that voted contestants still
outrank zero-vote ones, and that round/country/contest-resolution boundaries
are unchanged.
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
from app.services.season_migration import SeasonMigrationService


def _user(db, suffix: str) -> User:
    user = User(email=f"th5zv-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str) -> Round:
    """
    A cohort round whose submission month is safely in the past relative to
    whenever this test actually runs, so the REGIONAL vote-open gate
    (cohort month + 2) inside promote_to_next_level is always satisfied --
    without that, the freeze this file tests would be silently skipped as
    "too early".
    """
    cohort_start = SeasonMigrationService._add_months(date.today().replace(day=1), -4)
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
    """One active nomination contest, linked into `rnd`, with an active
    country-level season/link -- the minimal wiring promote_to_next_level
    needs to rank and freeze a COUNTRY-level roster."""
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


def _promote_country_to_regional(db, contest: Contest, season: ContestSeason) -> dict:
    """Closes COUNTRY voting for this contest -- the real trigger that
    freezes COUNTRY-level Top High5 results (see
    SeasonMigrationService._freeze_top_high5_results)."""
    result = SeasonMigrationService.promote_to_next_level(
        db,
        SeasonLevel.COUNTRY,
        SeasonLevel.REGIONAL,
        contest.id,
        from_season_id=season.id,
    )
    db.commit()
    return result


def _all_contestant_ids(payload) -> set[int]:
    return {row["contestant_id"] for c in payload["contests"] for row in c["rows"]}


def _fetch(client, *, round_id: int, country: str, level: str = "country"):
    resp = client.get(
        f"/api/v1/seasons/top-high5?round_id={round_id}&country={country}&level={level}"
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_zero_vote_frozen_contestant_is_included(client, db):
    """TEST 1: a genuine contestant with zero votes must still be frozen and
    served -- the exact production symptom (Tanzania / round 28 / season
    262), now at the freeze layer instead of live computation."""
    rnd = _round(db, "t1")
    contest, season = _country_scope(db, rnd, suffix="t1")
    contestant = _contestant(
        db, suffix="t1", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    db.commit()
    _promote_country_to_regional(db, contest, season)

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert contestant.id in ids

    row = next(
        r for c in payload["contests"] for r in c["rows"] if r["contestant_id"] == contestant.id
    )
    assert row["votes_count"] == 0
    assert row["stars_points"] == 0


def test_voted_frozen_contestant_is_included_and_scored(client, db):
    """TEST 2: a voted contestant is frozen with its real points/vote count."""
    rnd = _round(db, "t2")
    contest, season = _country_scope(db, rnd, suffix="t2")
    contestant = _contestant(
        db, suffix="t2", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    _vote(db, suffix="t2", contestant=contestant, contest=contest, season=season)
    db.commit()
    _promote_country_to_regional(db, contest, season)

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    row = next(
        r for c in payload["contests"] for r in c["rows"] if r["contestant_id"] == contestant.id
    )
    assert row["votes_count"] == 1
    assert row["stars_points"] == 5


def test_mixed_voted_and_zero_vote_contestants_both_frozen_and_ranked(client, db):
    """TEST 3: voted and zero-vote contestants are both frozen, and the voted
    one ranks strictly above the zero-vote one."""
    rnd = _round(db, "t3")
    contest, season = _country_scope(db, rnd, suffix="t3")
    voted = _contestant(
        db, suffix="t3-voted", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    zero = _contestant(
        db, suffix="t3-zero", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    _vote(db, suffix="t3", contestant=voted, contest=contest, season=season)
    db.commit()
    _promote_country_to_regional(db, contest, season)

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert {voted.id, zero.id} <= ids

    rows = [r for c in payload["contests"] for r in c["rows"]]
    ranks = {r["contestant_id"]: r["rank"] for r in rows}
    assert ranks[voted.id] < ranks[zero.id]


def test_different_round_voted_contestant_is_excluded(client, db):
    """TEST 4: a contestant frozen under a DIFFERENT round, even with real
    votes, must never appear in another round's results."""
    target_round = _round(db, "t4-target")
    target_contest, target_season = _country_scope(db, target_round, suffix="t4-target")
    target_contestant = _contestant(
        db,
        suffix="t4-target",
        rnd=target_round,
        contest=target_contest,
        season=target_season,
        country="Tanzania",
    )
    db.commit()
    _promote_country_to_regional(db, target_contest, target_season)

    other_round = _round(db, "t4-other")
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
    _promote_country_to_regional(db, other_contest, other_season)

    payload = _fetch(client, round_id=target_round.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert target_contestant.id in ids
    assert other_contestant.id not in ids


def test_correct_round_wrong_country_is_excluded(client, db):
    """TEST 5: a same-round, zero-vote contestant whose country does not
    match the requested one stays excluded."""
    rnd = _round(db, "t5")
    contest, season = _country_scope(db, rnd, suffix="t5")
    wrong_country = _contestant(
        db, suffix="t5", rnd=rnd, contest=contest, season=season, country="Kenya"
    )
    db.commit()
    _promote_country_to_regional(db, contest, season)

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert wrong_country.id not in ids


def test_case_a_resolved_contestant_with_ambiguous_season_still_frozen(client, db):
    """TEST 6: Case A (contestant.contest_id set directly) remains
    authoritative even when the contestant's season also links to a second,
    unrelated contest, and the frozen zero-vote contestant stays correctly
    scoped to the contest its contest_id names, not the sibling one."""
    rnd = _round(db, "t6")
    contest, season = _country_scope(db, rnd, suffix="t6")
    sibling_contest = Contest(
        name="Sibling Contest t6", contest_type="t", contest_mode="nomination", level="country"
    )
    db.add(sibling_contest)
    db.flush()
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=sibling_contest.id))
    db.add(ContestSeasonLink(contest_id=sibling_contest.id, season_id=season.id, is_active=True))
    db.flush()

    contestant = _contestant(
        db, suffix="t6", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    db.commit()
    _promote_country_to_regional(db, contest, season)
    # Sibling contest never gets promoted -- it has no roster of its own, so
    # promote_to_next_level would just report "no contestants to promote".
    SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, sibling_contest.id, from_season_id=season.id
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
    """TEST 7: a genuine season-linked contestant whose season links to
    MULTIPLE active contests, with no contest_id and no vote evidence, has no
    authoritative signal (contestant_contest_resolution.py, Cases A-D all
    fail) and must stay excluded from freezing entirely."""
    rnd = _round(db, "t7")
    contest_a, season = _country_scope(db, rnd, suffix="t7-a")
    contest_b = Contest(
        name="Contest t7-b", contest_type="t", contest_mode="nomination", level="country"
    )
    db.add(contest_b)
    db.flush()
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest_b.id))
    db.add(ContestSeasonLink(contest_id=contest_b.id, season_id=season.id, is_active=True))
    db.flush()

    ambiguous = _contestant(
        db,
        suffix="t7",
        rnd=rnd,
        contest=contest_a,
        season=season,
        country="Tanzania",
        resolved=False,
    )
    db.commit()
    _promote_country_to_regional(db, contest_a, season)

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert ambiguous.id not in ids


def test_tanzania_round28_equivalent_zero_vote_dataset_returns_genuine_results(client, db):
    """TEST 8: the actual production scenario at realistic scale -- several
    genuine contestants, all zero votes, no fallback data of any kind. Before
    the underlying fix, this returned an empty leaderboard for the whole
    round; the frozen result now shows every genuine contestant."""
    rnd = _round(db, "t8")
    contest, season = _country_scope(db, rnd, suffix="t8")
    contestants = [
        _contestant(
            db, suffix=f"t8-{i}", rnd=rnd, contest=contest, season=season, country="Tanzania"
        )
        for i in range(4)
    ]
    db.commit()
    _promote_country_to_regional(db, contest, season)

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    ids = _all_contestant_ids(payload)
    assert {c.id for c in contestants} <= ids
    assert payload["contests"], "expected at least one non-empty contest group"


def test_no_frozen_result_before_promotion_runs(client, db):
    """TEST 9: before COUNTRY voting has actually closed (no promotion run
    yet), the endpoint must return no results for that round/level -- it must
    never fall back to live vote counts. This is the core behavior this
    rework exists for."""
    rnd = _round(db, "t9")
    contest, season = _country_scope(db, rnd, suffix="t9")
    contestant = _contestant(
        db, suffix="t9", rnd=rnd, contest=contest, season=season, country="Tanzania"
    )
    _vote(db, suffix="t9", contestant=contestant, contest=contest, season=season)
    db.commit()
    # Deliberately do NOT call promote_to_next_level.

    payload = _fetch(client, round_id=rnd.id, country="Tanzania")
    assert payload["contests"] == []
