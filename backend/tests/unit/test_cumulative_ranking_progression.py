"""Management-confirmed ranking and progression rules (2026-10-02).

* positions 1..5 earn 5..1 voting points; ranking is by total POINTS;
* points are CUMULATIVE across the phases of a cohort (never copied votes);
* ties: shares, likes, comments, views, earlier submission, then entry id;
* the top five of each group advance; no vote is needed, fewer than five all
  advance, a sole entry advances;
* legacy entries whose season_id collides with a ContestSeason id are resolved
  from evidence, never guessed;
* an entry that cannot be placed is left untouched and reported;
* a scheduler retry changes nothing.

Every user, entry, vote and round here is SYNTHETIC (SQLite).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.comment import Comment
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import round_contests
from app.models.voting import ContestantShare, ContestantVoting, ContestLike, PageView
from app.services import progression_ranking
from app.services.contestant_contest_resolution import (
    EXPLICIT_CONTEST_ID,
    LEGACY_COLLISION_ROUND_VERIFIED,
    LEGACY_COLLISION_SEASON_WITHOUT_ROUND,
    LEGACY_SEASON_ID_AS_CONTEST,
    contestant_belongs_to_contest_clause,
    explain_contest_resolution,
)
from app.services.progression_dry_run import (
    audit_legacy_collisions,
    pending_global_finalizations,
    simulate_due_progressions,
    simulate_hop,
)
from app.services.progression_ranking import ProgressionScore, progression_sort_key, rank_group
from app.services.season_migration import SeasonMigrationService
from app.services.voting_ranking import (
    VotingConflict,
    points_for_position,
    reorder_myhigh5_votes,
)
from tests.unit.test_month_end_progression_hardening import (  # noqa: F401  (fixtures)
    _quiet_scheduler_prints,
    active_at,
    clock,
    entry,
    run_pass,
    season_for,
    state,
    wide_round,
)
from tests.unit.test_phase5_contest_eligibility import contest, person
from tests.unit.test_phase8_participation_safety import member, season, top_high5, votes
from tests.unit.test_voting_ranking import _cast, _scope

MAY = date(2026, 5, 1)


@pytest.fixture(autouse=True)
def _corrected_finalization_rule_already_active(monkeypatch):
    """These scenarios use synthetic cohorts dated before 2026-10-02. They model
    stages that close while the corrected GLOBAL finalization rule is in force,
    so the rule's activation date is moved before them. The guard for stages
    that closed under the previous rule is covered by
    test_global_finalization_historical_guard.py."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "GLOBAL_FINALIZATION_ACTIVE_FROM", "2000-01-01", raising=False)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def cohort(db, mode="nomination", month=MAY):
    rnd = wide_round(db, month)
    ct = contest(db, mode=mode)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    return rnd, ct


def submitted(day: int, month: date = MAY) -> datetime:
    return datetime(month.year, month.month, day, 12, 0, 0)


def nominees(db, ct, rnd, n, *, country="Tanzania", start_day=1, origin="nomination"):
    """n entries, entry i submitted on day start_day+i (earlier index = earlier)."""
    return [
        entry(db, ct, rnd, k=start_day + i, origin=origin, country=country, when=submitted(start_day + i))
        for i in range(n)
    ]


def active_ids(db, rnd, level, ct) -> set:
    s = season_for(db, rnd, level)
    if s is None:
        return set()
    return {
        r[0]
        for r in db.query(ContestantSeason.contestant_id)
        .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
        .filter(ContestantSeason.season_id == s.id, ContestantSeason.is_active == True)  # noqa: E712
        .filter(contestant_belongs_to_contest_clause(ct.id))
        .all()
    }


def memberships(db):
    return sorted(
        (m.contestant_id, m.season_id, m.is_active, m.joined_at) for m in db.query(ContestantSeason).all()
    )


def score_of(db, ct, rnd, level, entries):
    return progression_ranking.score_candidates(db, contest=ct, round_obj=rnd, level=level, contestants=entries)


def share(db, c, when):
    db.add(ContestantShare(contestant_id=c.id, share_link="https://example.test/s", created_at=when))


def like(db, c, when):
    db.add(ContestLike(user_id=person(db, 30).id, contestant_id=c.id, created_at=when))


def comment(db, c, when):
    db.add(Comment(user_id=person(db, 30).id, contestant_id=c.id, content="c", created_at=when))


def view(db, c, when):
    db.add(PageView(contestant_id=c.id, viewed_at=when))


# ---------------------------------------------------------------------------
# VOTING: 5/4/3/2/1, reorder, uniqueness, stage isolation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("position,points", [(1, 5), (2, 4), (3, 3), (4, 2), (5, 1)])
def test_position_points(position, points):
    assert points_for_position(position) == points


def test_five_ranked_votes_earn_5_4_3_2_1(db):
    scope = _scope(db)
    cast = [_cast(db, scope, index) for index in range(5)]
    assert [(v.position, v.points) for v in cast] == [(1, 5), (2, 4), (3, 3), (4, 2), (5, 1)]


def test_reordering_recalculates_points(db):
    scope = _scope(db)
    voter, _, ct, s, *_rest, contestants = scope
    for index in range(5):
        _cast(db, scope, index)
    from app.services.voting_ranking import bucket_key_for_contest

    reorder_myhigh5_votes(
        db, voter_id=voter.id, season_id=s.id, contest_id=ct.id, bucket_key=bucket_key_for_contest(ct),
        ordered_contestant_ids=[c.id for c in reversed(contestants[:5])],
    )
    by_entry = {v.contestant_id: v.points for v in db.query(ContestantVoting).all()}
    assert [by_entry[c.id] for c in contestants[:5]] == [1, 2, 3, 4, 5]


def test_one_vote_per_voter_entry_and_season(db):
    scope = _scope(db)
    _cast(db, scope, 0)
    with pytest.raises(VotingConflict):
        _cast(db, scope, 0)


def test_stage_isolation_and_foreign_round_votes_are_not_counted(db):
    rnd, ct = cohort(db)
    other_rnd = wide_round(db, date(2026, 4, 1))
    country, regional = season(db, rnd, ct, SeasonLevel.COUNTRY), season(db, rnd, ct, SeasonLevel.REGIONAL)
    foreign = season(db, other_rnd, ct, SeasonLevel.COUNTRY)
    (a,) = nominees(db, ct, rnd, 1)
    votes(db, a, ct, country, 5)
    votes(db, a, ct, regional, 3)
    votes(db, a, ct, foreign, 4)   # another cohort's season: never part of this cohort
    db.commit()

    at_country = score_of(db, ct, rnd, SeasonLevel.COUNTRY, [a])[a.id]
    assert (at_country.carried_points, at_country.stage_points, at_country.cumulative_points) == (0, 5, 5)
    at_regional = score_of(db, ct, rnd, SeasonLevel.REGIONAL, [a])[a.id]
    assert (at_regional.carried_points, at_regional.stage_points, at_regional.cumulative_points) == (5, 3, 8)
    assert at_regional.points_by_level == {"city": 0, "country": 5, "regional": 3}


# ---------------------------------------------------------------------------
# RANKING: points, then shares, likes, comments, views, earlier submission, id
# ---------------------------------------------------------------------------

def _score(cid, **kw):
    kw.setdefault("submitted_at", datetime(2026, 5, 10))
    return ProgressionScore(contestant_id=cid, stage_level="country", **kw)


@pytest.mark.parametrize("winner,loser", [
    (dict(cumulative_points=6), dict(cumulative_points=5, shares=99, likes=99, comments=99, views=99)),
    (dict(cumulative_points=5, shares=2), dict(cumulative_points=5, shares=1, likes=99, comments=99, views=99)),
    (dict(cumulative_points=5, shares=1, likes=2), dict(cumulative_points=5, shares=1, likes=1, comments=99, views=99)),
    (dict(cumulative_points=5, likes=1, comments=2), dict(cumulative_points=5, likes=1, comments=1, views=99)),
    (dict(cumulative_points=5, comments=1, views=2), dict(cumulative_points=5, comments=1, views=1)),
    (dict(cumulative_points=5, views=1, submitted_at=datetime(2026, 5, 2)),
     dict(cumulative_points=5, views=1, submitted_at=datetime(2026, 5, 3))),
])
def test_tie_break_ladder(winner, loser):
    # The winner carries the HIGHER id, so the id fallback can never explain the result.
    scores = {2: _score(2, **winner), 1: _score(1, **loser)}
    members = [SimpleNamespace(id=1, user_id=11), SimpleNamespace(id=2, user_id=22)]
    assert [c.id for c in rank_group(members, scores)] == [2, 1]


def test_deterministic_final_fallback_is_the_entry_id():
    same = dict(cumulative_points=5, shares=1, likes=1, comments=1, views=1, submitted_at=datetime(2026, 5, 2))
    scores = {7: _score(7, **same), 3: _score(3, **same)}
    members = [SimpleNamespace(id=7, user_id=1), SimpleNamespace(id=3, user_id=2)]
    assert [c.id for c in rank_group(members, scores)] == [3, 7]
    assert [c.id for c in rank_group(list(reversed(members)), scores)] == [3, 7]
    assert progression_sort_key(scores[3]) < progression_sort_key(scores[7])


def test_missing_submission_time_sorts_after_a_known_one():
    scores = {1: _score(1, cumulative_points=5, submitted_at=None), 2: _score(2, cumulative_points=5)}
    members = [SimpleNamespace(id=1, user_id=1), SimpleNamespace(id=2, user_id=2)]
    assert [c.id for c in rank_group(members, scores)] == [2, 1]


def test_promotion_ranks_with_real_engagement_values(db, clock):
    """The audit's tie-break bug: promotion ranked with engagement = 0 for
    everyone. Seven zero-vote nominees; the LAST five submitted hold the real
    engagement, so only reading it can put them ahead of the two earliest."""
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 7)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    mid_june = datetime(2026, 6, 15)
    share(db, e[6], mid_june)
    like(db, e[5], mid_june)
    comment(db, e[4], mid_june)
    view(db, e[3], mid_june)
    view(db, e[2], mid_june)
    # After the Country stage closed (June 30): must not count for that stage.
    for _ in range(3):
        share(db, e[0], datetime(2026, 7, 1, 0, 0, 1))
    db.commit()

    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    scores = score_of(db, ct, rnd, SeasonLevel.COUNTRY, e)
    assert [scores[c.id].shares for c in e] == [0, 0, 0, 0, 0, 0, 1]
    assert (scores[e[5].id].likes, scores[e[4].id].comments, scores[e[3].id].views) == (1, 1, 1)
    order = [c.id for c in rank_group(e, scores)]
    assert order == [e[6].id, e[5].id, e[4].id, e[2].id, e[3].id, e[0].id, e[1].id]

    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == {c.id for c in e[2:]}
    frozen = (db.query(TopHigh5Result)
              .filter(TopHigh5Result.contest_id == ct.id, TopHigh5Result.from_season_id == country.id)
              .order_by(TopHigh5Result.rank).all())
    assert [r.contestant_id for r in frozen] == order[:5]
    assert [(r.shares, r.likes, r.comments, r.views) for r in frozen] == [
        (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1), (0, 0, 0, 1)]
    assert all(r.migrated for r in frozen)


# ---------------------------------------------------------------------------
# CARRY-FORWARD: Country -> Regional -> Continental -> Global
# ---------------------------------------------------------------------------

def test_voting_points_accumulate_across_every_phase_without_copying_votes(db, clock):
    rnd, ct = cohort(db)
    tz = nominees(db, ct, rnd, 4, country="Tanzania", start_day=1)
    ke = nominees(db, ct, rnd, 4, country="Kenya", start_day=10)
    t1, t2, t3, t4 = tz
    k1, k2, k3, k4 = ke
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    for c, pts in zip(tz + ke, (20, 15, 10, 5, 18, 12, 8, 4)):
        votes(db, c, ct, country, pts)
    db.commit()

    # Country -> Regional: every country has four entries, so all eight advance.
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == {c.id for c in tz + ke}
    regional = season_for(db, rnd, SeasonLevel.REGIONAL)
    assert db.query(ContestantVoting).filter(ContestantVoting.season_id == regional.id).count() == 0

    # Regional: only t4 (+3) and k4 (+30) receive new votes.
    votes(db, t4, ct, regional, 3)
    votes(db, k4, ct, regional, 30)
    db.commit()
    at_regional = score_of(db, ct, rnd, SeasonLevel.REGIONAL, tz + ke)
    assert (at_regional[k4.id].carried_points, at_regional[k4.id].stage_points,
            at_regional[k4.id].cumulative_points) == (4, 30, 34)
    assert (at_regional[t4.id].carried_points, at_regional[t4.id].stage_points,
            at_regional[t4.id].cumulative_points) == (5, 3, 8)
    assert at_regional[t1.id].cumulative_points == 20   # no new vote: the Country score still stands

    # Regional -> Continental: one East Africa group of eight, top five by
    # CUMULATIVE points. On Regional points alone t4 would be second.
    run_pass(db, clock, datetime(2026, 8, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.CONTINENT, ct) == {k4.id, t1.id, k1.id, t2.id, k2.id}
    frozen = (db.query(TopHigh5Result)
              .filter(TopHigh5Result.contest_id == ct.id, TopHigh5Result.level == SeasonLevel.REGIONAL)
              .order_by(TopHigh5Result.rank).all())
    assert [(r.contestant_id, r.total_points) for r in frozen] == [
        (k4.id, 34), (t1.id, 20), (k1.id, 18), (t2.id, 15), (k2.id, 12)]
    assert all(r.migrated for r in frozen)

    # Continental adds new points on top of the carried score.
    continent = season_for(db, rnd, SeasonLevel.CONTINENT)
    votes(db, k2, ct, continent, 10)
    db.commit()
    at_continent = score_of(db, ct, rnd, SeasonLevel.CONTINENT, [k4, t1, k1, t2, k2])
    assert (at_continent[k2.id].carried_points, at_continent[k2.id].stage_points,
            at_continent[k2.id].cumulative_points) == (12, 10, 22)
    assert at_continent[k2.id].points_by_level == {"city": 0, "country": 12, "regional": 0, "continent": 10}

    # Continental -> Global: the cumulative score is the starting score at Global.
    run_pass(db, clock, datetime(2026, 9, 1, 0, 30))
    finalists = [k4, t1, k1, t2, k2]
    assert active_ids(db, rnd, SeasonLevel.GLOBAL, ct) == {c.id for c in finalists}
    at_global = score_of(db, ct, rnd, SeasonLevel.GLOBAL, finalists)
    assert {c.id: at_global[c.id].cumulative_points for c in finalists} == {
        k4.id: 34, k2.id: 22, t1.id: 20, k1.id: 18, t2.id: 15}
    assert all(at_global[c.id].stage_points == 0 for c in finalists)

    global_season = season_for(db, rnd, SeasonLevel.GLOBAL)
    votes(db, t2, ct, global_season, 25)
    db.commit()
    run_pass(db, clock, datetime(2026, 10, 1, 0, 30))
    final = (db.query(TopHigh5Result)
             .filter(TopHigh5Result.contest_id == ct.id, TopHigh5Result.level == SeasonLevel.GLOBAL)
             .order_by(TopHigh5Result.rank).all())
    assert [(r.contestant_id, r.total_points) for r in final] == [
        (t2.id, 40), (k4.id, 34), (k2.id, 22), (t1.id, 20), (k1.id, 18)]

    # Votes themselves were never copied or moved: one row per vote cast.
    by_season = {}
    for v in db.query(ContestantVoting).all():
        by_season[v.season_id] = by_season.get(v.season_id, 0) + 1
    assert by_season == {country.id: 8, regional.id: 2, continent.id: 1, global_season.id: 1}


# ---------------------------------------------------------------------------
# ZERO VOTES / SOLE CONTESTANT
# ---------------------------------------------------------------------------

def test_zero_votes_more_than_five_top_five_by_tie_breakers(db, clock):
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 7)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    # No vote, no engagement: the five earliest submissions advance.
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == {c.id for c in e[:5]}
    assert active_ids(db, rnd, SeasonLevel.COUNTRY, ct) == {e[5].id, e[6].id}
    assert db.query(ContestantVoting).count() == 0


def test_zero_votes_fewer_than_five_all_advance(db, clock):
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 3)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == {c.id for c in e}


def test_sole_contestant_advances_automatically_through_every_stage(db, clock):
    rnd, ct = cohort(db)
    (only,) = nominees(db, ct, rnd, 1)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    for month, level in ((7, SeasonLevel.REGIONAL), (8, SeasonLevel.CONTINENT), (9, SeasonLevel.GLOBAL)):
        run_pass(db, clock, datetime(2026, month, 1, 0, 30))
        assert active_ids(db, rnd, level, ct) == {only.id}, level
    assert db.query(ContestantVoting).count() == 0


def test_zero_votes_never_leave_the_next_stage_empty_personal_lifecycle(db, clock):
    """City -> Country -> Regional -> Continental -> Global with no vote at all."""
    rnd, ct = cohort(db, mode="participation")
    e = nominees(db, ct, rnd, 7, origin="participation")
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.CITY, ct) == {c.id for c in e}
    for month, level in ((7, SeasonLevel.COUNTRY), (8, SeasonLevel.REGIONAL),
                         (9, SeasonLevel.CONTINENT), (10, SeasonLevel.GLOBAL)):
        run_pass(db, clock, datetime(2026, month, 1, 0, 30))
        assert active_ids(db, rnd, level, ct) == {c.id for c in e[:5]}, level
    run_pass(db, clock, datetime(2026, 11, 1, 0, 30))
    final = (db.query(TopHigh5Result)
             .filter(TopHigh5Result.contest_id == ct.id, TopHigh5Result.level == SeasonLevel.GLOBAL)
             .order_by(TopHigh5Result.rank).all())
    assert [r.contestant_id for r in final] == [c.id for c in e[:5]]


# ---------------------------------------------------------------------------
# PROGRESSION: groups, nominators, safety, regional pools, retries
# ---------------------------------------------------------------------------

def test_maximum_five_per_group_each_group_ranked_on_its_own(db, clock):
    rnd, ct = cohort(db)
    tz = nominees(db, ct, rnd, 7, country="Tanzania", start_day=1)
    ke = nominees(db, ct, rnd, 6, country="Kenya", start_day=10)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    votes(db, tz[6], ct, country, 5)    # the last Tanzanian submission is voted in
    db.commit()
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == (
        {tz[6].id} | {c.id for c in tz[:4]} | {c.id for c in ke[:5]})


def test_one_winner_per_nominator(db, clock):
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 6)
    twin = Contestant(user_id=e[0].user_id, season_id=ct.id, contest_id=ct.id, round_id=rnd.id,
                      title="twin", description="d", entry_type="nomination", city="Arusha",
                      country="Tanzania", region="East Africa", continent="Africa", is_active=True,
                      is_deleted=False, is_qualified=True, registration_date=submitted(2),
                      created_at=submitted(2))
    db.add(twin)
    db.commit()
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    promoted = active_ids(db, rnd, SeasonLevel.REGIONAL, ct)
    # The nominator's better (earlier) entry advances; the twin does not take a
    # second slot, which goes to the next nominator instead.
    assert twin.id not in promoted
    assert promoted == {c.id for c in e[:5]}


def test_safety_held_winner_is_not_promoted_and_not_replaced(db, clock):
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 6)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    leader = e[0]
    db.add(ContestEntrySafety(created_at=datetime(2026, 6, 20), updated_at=datetime(2026, 6, 20),
                              contestant_id=leader.id, contest_id=ct.id, entry_kind="NOMINATION",
                              exposure_status="HELD", outcome="HOLD", reason_codes=["SYNTHETIC_HOLD"],
                              last_evaluated_at=datetime(2026, 6, 20), activated_at=datetime(2026, 6, 2),
                              enforced=True))
    leader.is_active = False
    db.commit()
    out = run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    promoted = active_ids(db, rnd, SeasonLevel.REGIONAL, ct)
    assert promoted == {c.id for c in e[1:5]}          # four, not five: no substitute
    assert e[5].id not in promoted
    held = [r["result"].get("held_contestant_ids") for r in out["results"]
            if r.get("action") == "promote_country_to_regional"]
    assert held == [[leader.id]]
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    link = db.query(ContestantSeason).filter(ContestantSeason.contestant_id == leader.id,
                                             ContestantSeason.season_id == country.id).one()
    assert link.is_active is True


def test_missing_regional_pool_leaves_winners_untouched_and_recoverable(db, clock):
    rnd, ct = cohort(db)
    tz = nominees(db, ct, rnd, 2, country="Tanzania", start_day=1)
    fr = nominees(db, ct, rnd, 6, country="France", start_day=10)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    out = run_pass(db, clock, datetime(2026, 7, 1, 0, 30))

    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == {c.id for c in tz}
    result = next(r["result"] for r in out["results"] if r.get("action") == "promote_country_to_regional")
    assert {(u["contestant_id"], u["group"], u["reason"]) for u in result["unplaced"]} == {
        (c.id, "France", "NO_REGIONAL_POOL_CONFIGURED") for c in fr[:5]}
    for c in fr:   # winners AND the rest of the group: nothing about them changed
        db.refresh(c)
        assert c.is_qualified is True and c.is_active is True and c.region == "East Africa"
        link = db.query(ContestantSeason).filter(ContestantSeason.contestant_id == c.id,
                                                 ContestantSeason.season_id == country.id).one()
        assert link.is_active is True
    # France's own country Top High5 is still recorded.
    frozen = db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id,
                                             TopHigh5Result.jurisdiction == "France").all()
    assert len(frozen) == 5 and not any(r.migrated for r in frozen)


def test_every_group_unplaced_is_a_stable_no_op_on_every_retry(db, clock):
    rnd, ct = cohort(db)
    nominees(db, ct, rnd, 3, country="France")
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == set()
    before, before_members = state(db), memberships(db)
    seasons_before = db.query(ContestSeason).count()
    for hour in range(1, 6):
        run_pass(db, clock, datetime(2026, 7, 1, hour, 30))
    assert state(db) == before
    assert memberships(db) == before_members          # joined_at included
    assert db.query(ContestSeason).count() == seasons_before
    assert {c.is_qualified for c in db.query(Contestant).all()} == {True}


def test_repeated_passes_change_nothing_after_a_promotion(db, clock):
    rnd, ct = cohort(db)
    nominees(db, ct, rnd, 7)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    before, before_members = state(db), memberships(db)
    seasons, frozen = db.query(ContestSeason).count(), db.query(TopHigh5Result).count()
    for hour in range(1, 6):
        run_pass(db, clock, datetime(2026, 7, 1, hour, 30))
    assert state(db) == before
    assert memberships(db) == before_members
    assert (db.query(ContestSeason).count(), db.query(TopHigh5Result).count()) == (seasons, frozen)


def test_promoting_again_converges_without_duplicates(db, clock):
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 7)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    clock(datetime(2026, 7, 1, 0, 30))
    first = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, ct.id, from_season_id=country.id)
    db.commit()
    before_members = memberships(db)
    frozen = db.query(TopHigh5Result).count()
    # An already promoted cohort: the source link is inactive, so the call is refused cleanly.
    again = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, ct.id, from_season_id=country.id)
    db.commit()
    assert first["promoted_contestant_ids"] == [c.id for c in e[:5]]
    assert "error" in again
    assert memberships(db) == before_members
    assert db.query(TopHigh5Result).count() == frozen


def test_partially_completed_progression_is_finished_consistently(db, clock):
    """Destination membership exists for one winner while its source membership
    is still active (an interrupted earlier run): the next run converges."""
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 7)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    regional = ContestSeason(round_id=rnd.id, title="pre-existing regional", level=SeasonLevel.REGIONAL)
    db.add(regional)
    db.flush()
    joined = datetime(2026, 6, 30, 23, 0, 0)
    member_row = ContestantSeason(contestant_id=e[0].id, season_id=regional.id, is_active=True, joined_at=joined)
    stale_row = ContestantSeason(contestant_id=e[6].id, season_id=regional.id, is_active=True, joined_at=joined)
    db.add_all([member_row, stale_row])
    db.commit()

    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert db.query(ContestSeason).filter(ContestSeason.round_id == rnd.id,
                                          ContestSeason.level == SeasonLevel.REGIONAL).count() == 1
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == {c.id for c in e[:5]}
    assert active_ids(db, rnd, SeasonLevel.COUNTRY, ct) == {e[5].id, e[6].id}
    rows = db.query(ContestantSeason).filter(ContestantSeason.contestant_id == e[0].id).all()
    assert sorted((r.season_id, r.is_active) for r in rows) == [(country.id, False), (regional.id, True)]
    db.refresh(member_row)
    assert member_row.joined_at == joined            # already in place: timestamp kept
    frozen = db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id).all()
    assert {r.contestant_id for r in frozen if r.migrated} == {c.id for c in e[:5]}


# ---------------------------------------------------------------------------
# CONTINENTAL -> GLOBAL: one worldwide pool per contest (shipped scope kept)
# ---------------------------------------------------------------------------

def _continental_cohort(db, clock):
    """Six African and four European entries of one contest at Continental."""
    rnd, ct = cohort(db)
    continent_season = season(db, rnd, ct, SeasonLevel.CONTINENT)
    africa = nominees(db, ct, rnd, 6, country="Tanzania", start_day=1)
    europe = nominees(db, ct, rnd, 4, country="France", start_day=10)
    for c in europe:
        c.continent, c.region = "Europe", "Western Europe"
    for c in africa + europe:
        member(db, c, continent_season)
    db.commit()
    clock(datetime(2026, 9, 1, 0, 30))
    return rnd, ct, continent_season, africa, europe


def _to_global(db, ct, continent_season):
    out = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL, ct.id, from_season_id=continent_season.id)
    db.commit()
    return out


def test_global_takes_the_worldwide_top_five_not_five_per_continent(db, clock):
    rnd, ct, continent_season, africa, europe = _continental_cohort(db, clock)
    country = season(db, rnd, ct, SeasonLevel.COUNTRY, link=False)
    # Cumulative: points earned at Country still count at Continental.
    votes(db, europe[3], ct, country, 40)
    votes(db, africa[5], ct, country, 30)
    votes(db, europe[0], ct, continent_season, 20)
    votes(db, africa[0], ct, continent_season, 10)
    db.commit()

    out = _to_global(db, ct, continent_season)
    # Ten entries on two continents -> five advance in total, ranked together.
    assert out["promoted_contestant_ids"] == [europe[3].id, africa[5].id, europe[0].id, africa[0].id, africa[1].id]
    assert out["unplaced"] == []
    assert active_ids(db, rnd, SeasonLevel.GLOBAL, ct) == set(out["promoted_contestant_ids"])

    # Each continent's own Top High5 is still frozen separately.
    frozen = db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id,
                                             TopHigh5Result.level == SeasonLevel.CONTINENT).all()
    by_continent = {}
    for row in sorted(frozen, key=lambda r: r.rank):
        by_continent.setdefault(row.jurisdiction, []).append((row.contestant_id, row.total_points, row.migrated))
    assert by_continent["Africa"] == [(africa[5].id, 30, True), (africa[0].id, 10, True), (africa[1].id, 0, True),
                                      (africa[2].id, 0, False), (africa[3].id, 0, False)]
    assert by_continent["Europe"] == [(europe[3].id, 40, True), (europe[0].id, 20, True),
                                      (europe[1].id, 0, False), (europe[2].id, 0, False)]


def test_global_with_zero_votes_takes_the_five_earliest_worldwide(db, clock):
    rnd, ct, continent_season, africa, europe = _continental_cohort(db, clock)
    out = _to_global(db, ct, continent_season)
    assert out["promoted_contestant_ids"] == [c.id for c in africa[:5]]
    assert not any(c.id in out["promoted_contestant_ids"] for c in europe)


def test_entry_without_a_continent_still_competes_for_global(db, clock):
    rnd, ct, continent_season, africa, europe = _continental_cohort(db, clock)
    stray = europe[0]
    stray.continent, stray.country, stray.nominator_country = None, "Atlantis", None
    votes(db, stray, ct, continent_season, 9)
    db.commit()
    out = _to_global(db, ct, continent_season)
    assert out["promoted_contestant_ids"][0] == stray.id and out["unplaced"] == []


# ---------------------------------------------------------------------------
# RETRY: joined_at
# ---------------------------------------------------------------------------

def test_activation_never_rewrites_joined_at_of_an_active_membership(db):
    rnd, ct = cohort(db)
    s = season(db, rnd, ct, SeasonLevel.COUNTRY)
    (a,) = nominees(db, ct, rnd, 1)
    joined = datetime(2026, 6, 1, 0, 5)
    db.add(ContestantSeason(contestant_id=a.id, season_id=s.id, is_active=True, joined_at=joined))
    db.commit()
    link = SeasonMigrationService._activate_contestant_season_link(db, a.id, s.id)
    db.commit()
    assert link.joined_at == joined and link.is_active is True
    assert db.query(ContestantSeason).filter(ContestantSeason.contestant_id == a.id).count() == 1

    link.is_active = False
    db.commit()
    later = datetime(2026, 6, 20)
    link = SeasonMigrationService._activate_contestant_season_link(db, a.id, s.id, joined_at=later)
    db.commit()
    assert link.is_active is True and link.joined_at == later    # a real reactivation is recorded


def test_hourly_retry_of_a_waiting_stage_keeps_joined_at(db, clock):
    rnd, ct = cohort(db)
    nominees(db, ct, rnd, 4)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    before = memberships(db)
    for hour in range(1, 5):
        run_pass(db, clock, datetime(2026, 6, 10, hour, 30))
    assert memberships(db) == before


# ---------------------------------------------------------------------------
# LEGACY contest ownership: DJ / Comedy / Handsome, id collisions, ambiguity
# ---------------------------------------------------------------------------

def _legacy_world(db):
    """An old round whose season ids 1..3 numerically equal contest ids 1..3."""
    old_rnd = wide_round(db, date(2025, 3, 1))
    old_seasons = []
    for level in (SeasonLevel.CITY, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL):
        s = ContestSeason(round_id=old_rnd.id, title=f"old {level.value}", level=level)
        db.add(s)
        db.flush()
        old_seasons.append(s)
    contests = {}
    for name in ("DJ", "Comedy", "Handsome"):
        contests[name] = contest(db, mode="nomination")
        contests[name].name = name
        # Distinct categories: the scheduler promotes one contest per category and mode.
        contests[name].contest_type = name.lower()
    db.commit()
    rnd = wide_round(db, MAY)
    for ct in contests.values():
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    for ct in contests.values():
        collided = db.get(ContestSeason, ct.id)
        assert collided is not None and collided.round_id == old_rnd.id   # the collision under test
    return old_rnd, old_seasons, rnd, contests


def legacy_entry(db, ct, rnd, *, day=5, country="Tanzania", season_id=None):
    user = person(db, 30, country=country)
    c = Contestant(user_id=user.id, season_id=ct.id if season_id is None else season_id, contest_id=None,
                   round_id=rnd.id, title=f"legacy {ct.name} {day}", description="d", entry_type="nomination",
                   city="Arusha", country=country, region="East Africa", continent="Africa", is_active=True,
                   is_deleted=False, is_qualified=True, registration_date=submitted(day),
                   created_at=submitted(day))
    db.add(c)
    db.commit()
    return c


def resolved_ids(db, ct) -> set:
    return {r[0] for r in db.query(Contestant.id).filter(contestant_belongs_to_contest_clause(ct.id)).all()}


@pytest.mark.parametrize("name", ["DJ", "Comedy", "Handsome"])
def test_legacy_entry_with_colliding_season_id_is_resolved_and_promoted(db, clock, name):
    _, _, rnd, contests = _legacy_world(db)
    ct = contests[name]
    legacy = legacy_entry(db, ct, rnd)
    modern = entry(db, ct, rnd, k=9, origin="nomination", when=submitted(9))
    assert explain_contest_resolution(db, legacy, ct.id).code == LEGACY_COLLISION_ROUND_VERIFIED
    assert explain_contest_resolution(db, modern, ct.id).code == EXPLICIT_CONTEST_ID
    assert resolved_ids(db, ct) == {legacy.id, modern.id}
    for other in contests.values():        # never assigned to an unrelated contest
        if other.id != ct.id:
            assert legacy.id not in resolved_ids(db, other)
            assert explain_contest_resolution(db, legacy, other.id).belongs is False

    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    votes(db, legacy, ct, country, 5)      # the voted legacy nominee of the audit
    db.commit()
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == {legacy.id, modern.id}
    top = (db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id)
           .order_by(TopHigh5Result.rank).first())
    assert (top.contestant_id, top.total_points, top.migrated) == (legacy.id, 5, True)
    db.refresh(legacy)
    assert legacy.contest_id is None       # compatibility in code only: the row is not backfilled


def test_explicit_contest_id_always_wins_over_a_colliding_season_id(db):
    _, _, rnd, contests = _legacy_world(db)
    dj, comedy = contests["DJ"], contests["Comedy"]
    c = legacy_entry(db, dj, rnd)
    c.contest_id = comedy.id               # season_id still equals the DJ contest id
    db.commit()
    assert resolved_ids(db, comedy) == {c.id} and resolved_ids(db, dj) == set()
    assert explain_contest_resolution(db, c, comedy.id).code == EXPLICIT_CONTEST_ID
    assert explain_contest_resolution(db, c, dj.id).belongs is False


def test_plain_legacy_row_without_collision_still_resolves(db):
    rnd, ct = cohort(db)
    for _ in range(3):                      # push the contest id past every season id
        ct = contest(db, mode="nomination")
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    assert db.get(ContestSeason, ct.id) is None
    c = legacy_entry(db, ct, rnd)
    assert explain_contest_resolution(db, c, ct.id).code == LEGACY_SEASON_ID_AS_CONTEST
    assert resolved_ids(db, ct) == {c.id}


def test_collision_with_a_season_that_has_no_round_is_resolved_and_labelled(db):
    """A season without a round can never be an entry's own season (membership
    of an unknown-round season is refused), so the legacy reading stands."""
    _, old_seasons, rnd, contests = _legacy_world(db)
    ct = contests["Comedy"]
    db.get(ContestSeason, ct.id).round_id = None
    c = legacy_entry(db, ct, rnd)
    assert resolved_ids(db, ct) == {c.id}
    assert explain_contest_resolution(db, c, ct.id).code == LEGACY_COLLISION_SEASON_WITHOUT_ROUND
    assert all(c.id not in resolved_ids(db, other) for other in contests.values() if other.id != ct.id)


def test_ambiguous_collision_same_round_stays_rejected(db):
    """season_id may genuinely be the entry's own season: not provably legacy."""
    old_rnd, _, _, contests = _legacy_world(db)
    ct = contests["Comedy"]
    db.execute(round_contests.insert().values(round_id=old_rnd.id, contest_id=ct.id))
    c = legacy_entry(db, ct, old_rnd)
    assert resolved_ids(db, ct) == set()
    assert explain_contest_resolution(db, c, ct.id).code == "AMBIGUOUS_COLLISION_SAME_ROUND"


def test_ambiguous_collision_votes_for_another_contest_stays_rejected(db):
    _, _, rnd, contests = _legacy_world(db)
    ct, other = contests["Comedy"], contests["DJ"]
    c = legacy_entry(db, ct, rnd)
    s = season(db, rnd, other, SeasonLevel.COUNTRY)
    votes(db, c, other, s, 5)
    db.commit()
    assert resolved_ids(db, ct) == set()
    assert explain_contest_resolution(db, c, ct.id).code == "AMBIGUOUS_COLLISION_VOTES_NAME_ANOTHER_CONTEST"


def test_ambiguous_collision_contest_not_in_the_entry_round_stays_rejected(db):
    _, _, rnd, contests = _legacy_world(db)
    ct = contests["Handsome"]
    db.execute(round_contests.delete().where(round_contests.c.contest_id == ct.id))
    c = legacy_entry(db, ct, rnd)
    assert resolved_ids(db, ct) == set()
    assert explain_contest_resolution(db, c, ct.id).code == "AMBIGUOUS_COLLISION_CONTEST_NOT_IN_ENTRY_ROUND"


def test_unique_link_of_a_foreign_round_season_never_claims_a_legacy_entry(db):
    """Production shape (read-only check, 2026-10-02): old City season 5 has one
    active link, to an unrelated contest. Its link says nothing about a July
    Comedy nominee whose season_id is 5 only because the Comedy contest is 5."""
    _, _, rnd, contests = _legacy_world(db)
    ct, other = contests["Comedy"], contests["DJ"]
    c = legacy_entry(db, ct, rnd)
    db.add(ContestSeasonLink(contest_id=other.id, season_id=ct.id, is_active=True))
    db.commit()
    assert resolved_ids(db, ct) == {c.id}
    assert resolved_ids(db, other) == set()
    assert explain_contest_resolution(db, c, ct.id).code == LEGACY_COLLISION_ROUND_VERIFIED
    assert explain_contest_resolution(db, c, other.id).belongs is False


def test_unique_link_still_resolves_a_genuine_same_round_season_reference(db):
    old_rnd, old_seasons, _, contests = _legacy_world(db)
    ct, other = contests["Comedy"], contests["DJ"]
    db.execute(round_contests.insert().values(round_id=old_rnd.id, contest_id=other.id))
    c = legacy_entry(db, ct, old_rnd)          # season_id is a season of the entry's OWN round
    db.add(ContestSeasonLink(contest_id=other.id, season_id=ct.id, is_active=True))
    db.commit()
    assert resolved_ids(db, other) == {c.id} and resolved_ids(db, ct) == set()
    assert explain_contest_resolution(db, c, other.id).code == "UNIQUE_SEASON_LINK"


def test_explanation_always_agrees_with_the_sql_clause(db):
    old_rnd, _, rnd, contests = _legacy_world(db)
    rows = [legacy_entry(db, contests["DJ"], rnd), legacy_entry(db, contests["Comedy"], old_rnd, day=6),
            entry(db, contests["Handsome"], rnd, k=3, origin="nomination", when=submitted(3))]
    orphan = legacy_entry(db, contests["DJ"], rnd, day=7, season_id=999)
    rows.append(orphan)
    for ct in contests.values():
        resolved = resolved_ids(db, ct)
        for c in rows:
            assert explain_contest_resolution(db, c, ct.id).belongs == (c.id in resolved), (ct.name, c.title)


# ---------------------------------------------------------------------------
# TOP HIGH5: frozen and live results follow the corrected ranking
# ---------------------------------------------------------------------------

def test_frozen_and_live_top_high5_follow_the_promotion_order(db, clock):
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 6)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    votes(db, e[5], ct, country, 9)
    votes(db, e[3], ct, country, 9)
    share(db, e[5], datetime(2026, 6, 15))
    db.commit()
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    expected = [e[5].id, e[3].id, e[0].id, e[1].id, e[2].id]
    frozen = (db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id)
              .order_by(TopHigh5Result.rank).all())
    assert [r.contestant_id for r in frozen] == expected
    assert [r.rank for r in frozen] == [1, 2, 3, 4, 5]
    assert [r.total_points for r in frozen] == [9, 9, 0, 0, 0]
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == set(expected)

    # Live display for the Country level of this cohort (July, per the Top High5 calendar offset).
    raw, _ = top_high5(db, SeasonLevel.COUNTRY, today=date(2026, 7, 15))
    rows = [r for card in raw["contests"] for r in card["rows"]]
    assert [r["contestant_id"] for r in rows] == expected
    assert [(r["stars_points"], r["stage_points"], r["carried_points"]) for r in rows[:2]] == [(9, 9, 0), (9, 9, 0)]
    assert all(r["migrates_next_stage"] for r in rows)


# ---------------------------------------------------------------------------
# VOTE PAGE: the displayed score and order are the ranking engine's
# ---------------------------------------------------------------------------

def test_vote_page_shows_the_cumulative_score_with_its_breakdown(db, clock):
    from app.crud.crud_contest import contest as contest_crud
    from app.schemas.contest import ContestantEnriched

    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 4)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    for c, pts in zip(e, (20, 15, 10, 5)):
        votes(db, c, ct, country, pts)
    db.commit()

    # Country stage: nothing carried yet, the score is the stage score.
    rows = contest_crud.get_contest_with_enriched_contestants(db, ct.id, round_id=rnd.id)["contestants"]
    assert [(r["id"], r["rank"], r["total_points"], r["stage_points"], r["carried_points"]) for r in rows] == [
        (e[0].id, 1, 20, 20, 0), (e[1].id, 2, 15, 15, 0), (e[2].id, 3, 10, 10, 0), (e[3].id, 4, 5, 5, 0)]

    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    regional = season_for(db, rnd, SeasonLevel.REGIONAL)
    votes(db, e[3], ct, regional, 12)
    db.commit()
    votes_before = sorted((v.id, v.season_id, v.contestant_id, v.points) for v in db.query(ContestantVoting).all())

    rows = contest_crud.get_contest_with_enriched_contestants(db, ct.id, round_id=rnd.id)["contestants"]
    got = [(r["id"], r["rank"], r["total_points"], r["stage_points"], r["carried_points"], r["cumulative_points"],
            r["votes_count"]) for r in rows]
    # Regional does not restart from zero: e[3] is 5 carried + 12 new = 17, behind e[0]'s carried 20.
    assert got == [(e[0].id, 1, 20, 0, 20, 20, 0), (e[3].id, 2, 17, 12, 5, 17, 1),
                   (e[1].id, 3, 15, 0, 15, 15, 0), (e[2].id, 4, 10, 0, 10, 10, 0)]
    assert all(r["season"]["level"] == "regional" for r in rows)
    # Vote details stay this stage's own rows; nothing was copied or created.
    assert [len(r["votes"]) for r in rows] == [0, 1, 0, 0]
    assert sorted((v.id, v.season_id, v.contestant_id, v.points) for v in db.query(ContestantVoting).all()) == votes_before
    # The API schema carries the explicit fields.
    parsed = ContestantEnriched(**rows[1])
    assert (parsed.total_points, parsed.stage_points, parsed.carried_points, parsed.cumulative_points) == (17, 12, 5, 17)
    # The roster order is exactly the order promotion would use.
    scores = score_of(db, ct, rnd, SeasonLevel.REGIONAL, e)
    assert [r["id"] for r in rows] == [c.id for c in rank_group(e, scores)]


def test_vote_page_counts_votes_whose_bucket_key_keeps_the_contest_type_case(db, clock):
    """Production shape: the DJ contest's type is 'Music' and its votes are
    stored under 'ty:Music:nomination'. The page must count them."""
    from app.crud.crud_contest import contest as contest_crud

    rnd, ct = cohort(db)
    ct.contest_type = "Music"
    db.commit()
    (a,) = nominees(db, ct, rnd, 1)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    votes(db, a, ct, country, 5)
    db.commit()
    assert db.query(ContestantVoting).one().vote_bucket_key == "ty:Music:nomination"
    (row,) = contest_crud.get_contest_with_enriched_contestants(db, ct.id, round_id=rnd.id)["contestants"]
    assert (row["total_points"], row["stage_points"]) == (5, 5)


# ---------------------------------------------------------------------------
# DRY-RUN: read-only, and it predicts exactly what promotion then does
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing_and_matches_the_real_promotion(db, clock):
    _, _, rnd, contests = _legacy_world(db)
    ct = contests["Comedy"]
    tz = nominees(db, ct, rnd, 6, country="Tanzania", start_day=1)
    fr = nominees(db, ct, rnd, 2, country="France", start_day=10)
    legacy = legacy_entry(db, ct, rnd, day=20)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    votes(db, legacy, ct, country, 5)
    db.commit()

    before, before_members = state(db), memberships(db)
    flags = sorted((c.id, c.is_qualified, c.is_active, c.region) for c in db.query(Contestant).all())
    seasons = db.query(ContestSeason).count()
    report = simulate_due_progressions(db, today=date(2026, 7, 1), contest_ids=[ct.id])
    assert not db.new and not db.dirty and not db.deleted
    db.rollback()
    db.expire_all()
    assert state(db) == before and memberships(db) == before_members
    assert sorted((c.id, c.is_qualified, c.is_active, c.region) for c in db.query(Contestant).all()) == flags
    assert db.query(ContestSeason).count() == seasons

    (hop,) = report["transitions"]
    assert (hop["source_stage"], hop["destination_stage"], hop["source_season_id"]) == (
        "country", "regional", country.id)
    assert hop["destination_season_would_be_created"] is True
    by_id = {row["contestant_id"]: row for row in hop["entries"]}
    assert by_id[legacy.id]["contest_resolution"] == LEGACY_COLLISION_ROUND_VERIFIED
    assert (by_id[legacy.id]["rank"], by_id[legacy.id]["cumulative_points"], by_id[legacy.id]["outcome"]) == (
        1, 5, "ADVANCES")
    assert by_id[tz[4].id]["outcome"] == "OUTSIDE_TOP_5"
    assert {row["outcome"] for row in hop["entries"] if row["group"] == "France"} == {
        "UNPLACED:NO_REGIONAL_POOL_CONFIGURED"}
    would_advance = {cid for cid, row in by_id.items() if row["outcome"] == "ADVANCES"}
    assert would_advance == {legacy.id} | {c.id for c in tz[:4]}
    assert report["totals"]["would_advance"] == 5
    assert report["totals"]["unplaced"] == 2
    assert report["totals"]["legacy_entries_resolved_by_round_evidence"] == 1
    for column in ("entry_title", "nominator_user_id", "previous_stage_points", "current_stage_points",
                   "cumulative_points", "shares", "likes", "comments", "views", "submitted_at", "rank",
                   "qualifies", "destination_stage", "group"):
        assert column in by_id[legacy.id]

    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert active_ids(db, rnd, SeasonLevel.REGIONAL, ct) == would_advance
    assert {c.id for c in fr} <= active_ids(db, rnd, SeasonLevel.COUNTRY, ct)


def test_dry_run_reports_safety_hold_and_unresolved_legacy_entry(db, clock):
    old_rnd, _, rnd, contests = _legacy_world(db)
    ct = contests["DJ"]
    e = nominees(db, ct, rnd, 3)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    db.add(ContestEntrySafety(created_at=datetime(2026, 6, 20), updated_at=datetime(2026, 6, 20),
                              contestant_id=e[0].id, contest_id=ct.id, entry_kind="NOMINATION",
                              exposure_status="HELD", outcome="HOLD", reason_codes=["SYNTHETIC_HOLD"],
                              last_evaluated_at=datetime(2026, 6, 20), activated_at=datetime(2026, 6, 2),
                              enforced=True))
    e[0].is_active = False
    # A legacy row whose own votes name another contest: stays unresolved, and is listed.
    stray = legacy_entry(db, ct, rnd, day=25)
    other_season = season(db, rnd, contests["Comedy"], SeasonLevel.REGIONAL)
    votes(db, stray, contests["Comedy"], other_season, 1)
    db.commit()

    hop = simulate_hop(db, contest=ct, from_season=country)
    by_id = {row["contestant_id"]: row for row in hop["entries"]}
    assert by_id[e[0].id]["outcome"] == "QUALIFIES_BUT_SAFETY_HELD"
    assert by_id[e[0].id]["safety_eligible"] is False
    assert hop["summary"]["would_advance"] == 2 and hop["summary"]["qualify_but_safety_held"] == 1
    (excluded,) = hop["excluded_legacy_entries"]
    assert excluded["contestant_id"] == stray.id
    assert excluded["contest_resolution"] == "AMBIGUOUS_COLLISION_VOTES_NAME_ANOTHER_CONTEST"
    assert not db.new and not db.dirty and not db.deleted


def test_dry_run_reconciliation_lists_frozen_rows_that_no_longer_match(db, clock):
    """Production shape: the old code froze a stuck stage with stage-only
    points, id order and migrated=False. The dry-run lists every such row."""
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 3)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    votes(db, e[2], ct, country, 7)
    for rank, (c, pts) in enumerate(((e[0], 0), (e[2], 0), (e[1], 0)), start=1):
        db.add(TopHigh5Result(contestant_id=c.id, contest_id=ct.id, level=SeasonLevel.COUNTRY,
                              jurisdiction="Tanzania", round_id=rnd.id, from_season_id=country.id,
                              rank=rank, total_points=pts, total_votes=0, migrated=False))
    db.commit()
    before = [(r.id, r.rank, r.contestant_id, r.total_points, r.migrated) for r in db.query(TopHigh5Result).all()]

    hop = simulate_hop(db, contest=ct, from_season=country)
    rows = {r["rank"]: r for r in hop["top_high5_reconciliation"]}
    assert (rows[1]["existing_contestant_id"], rows[1]["corrected_contestant_id"],
            rows[1]["corrected_cumulative_points"]) == (e[0].id, e[2].id, 7)
    assert "DIFFERENT_ENTRY_AT_RANK" in rows[1]["reason"]
    assert "MIGRATED_FLAG_WOULD_BE_STALE_AFTER_PROMOTION" in rows[3]["reason"]
    assert all(r["needs_reconciliation"] for r in rows.values())
    assert hop["summary"]["frozen_rows_needing_reconciliation"] == 3
    assert (hop["summary"]["source_contestants"], hop["summary"]["eligible"], hop["summary"]["would_advance"]) == (3, 3, 3)
    assert {row["regional_pool"] for row in hop["entries"]} == {"East Africa"}
    db.rollback()
    assert [(r.id, r.rank, r.contestant_id, r.total_points, r.migrated) for r in db.query(TopHigh5Result).all()] == before

    # Write-once is kept by the real promotion too: the rows are left for an approved reconciliation.
    run_pass(db, clock, datetime(2026, 7, 1, 0, 30))
    assert [(r.id, r.rank, r.contestant_id, r.total_points, r.migrated) for r in db.query(TopHigh5Result).all()] == before


def test_legacy_audit_classifies_every_colliding_row(db):
    old_rnd, _, rnd, contests = _legacy_world(db)
    dj, comedy, handsome = contests["DJ"], contests["Comedy"], contests["Handsome"]
    safe = legacy_entry(db, dj, rnd, day=1)
    same_round = legacy_entry(db, comedy, old_rnd, day=2)
    conflict = legacy_entry(db, comedy, rnd, day=3)
    votes(db, conflict, dj, season(db, rnd, dj, SeasonLevel.COUNTRY), 5)
    db.execute(round_contests.delete().where(round_contests.c.contest_id == handsome.id))
    unresolved = legacy_entry(db, handsome, rnd, day=4)
    entry(db, dj, rnd, k=9, origin="nomination", when=submitted(9))      # explicit contest_id: not audited
    db.commit()

    audit = audit_legacy_collisions(db)
    status = {row["contestant_id"]: (row["status"], row["code"]) for row in audit["entries"]}
    assert status == {
        safe.id: ("RESOLVED_SAFELY", LEGACY_COLLISION_ROUND_VERIFIED),
        same_round.id: ("AMBIGUOUS", "AMBIGUOUS_COLLISION_SAME_ROUND"),
        conflict.id: ("CONFLICT", "AMBIGUOUS_COLLISION_VOTES_NAME_ANOTHER_CONTEST"),
        unresolved.id: ("UNRESOLVED", "AMBIGUOUS_COLLISION_CONTEST_NOT_IN_ENTRY_ROUND"),
    }
    assert audit["total"] == 4
    assert audit["counts"] == {"RESOLVED_SAFELY": 1, "AMBIGUOUS": 1, "CONFLICT": 1, "UNRESOLVED": 1}
    assert not db.new and not db.dirty and not db.deleted
    assert all(c.contest_id is None for c in (safe, same_round, conflict, unresolved))   # nothing backfilled


def test_pending_global_finalization_preview_matches_the_real_freeze(db, clock):
    rnd, ct = cohort(db)
    e = nominees(db, ct, rnd, 6)
    for month in (6, 7, 8, 9):
        run_pass(db, clock, datetime(2026, month, 1, 0, 30))
    global_season = season_for(db, rnd, SeasonLevel.GLOBAL)
    votes(db, e[4], ct, global_season, 5)
    db.commit()
    assert pending_global_finalizations(db, today=date(2026, 9, 30)) == []      # voting still open
    (preview,) = pending_global_finalizations(db, today=date(2026, 10, 1))
    assert not db.new and not db.dirty and not db.deleted
    assert db.query(TopHigh5Result).filter(TopHigh5Result.level == SeasonLevel.GLOBAL).count() == 0
    expected = [e[4].id, e[0].id, e[1].id, e[2].id, e[3].id]
    assert [row["contestant_id"] for row in preview["would_freeze"]] == expected

    run_pass(db, clock, datetime(2026, 10, 1, 0, 30))
    frozen = (db.query(TopHigh5Result).filter(TopHigh5Result.level == SeasonLevel.GLOBAL)
              .order_by(TopHigh5Result.rank).all())
    assert [r.contestant_id for r in frozen] == expected
    assert pending_global_finalizations(db, today=date(2026, 10, 1)) == []

