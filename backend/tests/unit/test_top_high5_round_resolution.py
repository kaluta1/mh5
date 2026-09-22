"""
Regression tests for the "which round is the current Top High5 for this
level" resolution query in GET /api/v1/seasons/top-high5 (no explicit
round_id).

History: an earlier local fix in this file/endpoint swapped the ordering
from `created_at DESC` to `round_id DESC` (`created_at` is stamped at INSERT
time, and backfill/repair tooling such as backfill_top_high5_results.py and
repair_continent_top_high5.py rewrites historical rounds' rows long after
the fact, so it doesn't reflect real calendar chronology). That swap was
insufficient: verified directly against production data, BOTH orderings
picked the same wrong round for CONTINENT (round 21, a round whose
continental voting window was still nine days from closing) over round 4
(already closed, correctly showing real winners as migrated to GLOBAL) --
because neither `created_at` nor `round_id` ever gated on whether the
round's *own* level had actually finished; they only ever compared rows
that were already, wrongly, being treated as candidates. The same
"picks a not-yet-closed round" defect was independently confirmed at
COUNTRY and REGIONAL too.

Fix: resolution must (a) only consider rounds whose `requested_level`'s own
end date (`Round.country_season_end_date` / `regional_end_date` /
`continental_end_date` / `global_end_date`) has actually passed -- falling
back to `Round.status == COMPLETED` for the handful of legacy rounds where
that date column is NULL -- and (b) among those eligible rounds, order by
that same end date, not by round_id or created_at (both of which can be
produced out of calendar order by admin backfill tooling:
POST /rounds/generate-monthly accepts an arbitrary past year/month).

2026 mode-aware resolver update: these Round.<level>_end_date columns are
participation's calendar specifically (see the later, separate
nomination/participation calendar-mismatch audit and
test_top_high5_mode_aware_resolver.py). This file's fixtures directly
manipulate those columns to simulate "closed" vs "not yet closed" -- that
is now precisely participation's own gate, so every fixture here uses
contest_mode="participation" (previously "nomination", before contest
mode had any bearing on which calendar gates a result). The protection
these tests verify -- never auto-select a round before its own level has
genuinely closed -- is unchanged and still fully enforced; only the mode
label was corrected to match what is actually being exercised. Nomination's
own, independent, earlier calendar is covered separately in
test_top_high5_mode_aware_resolver.py.

2026 derived-architecture update: the default (no explicit round_id) path
no longer reads top_high5_results at all (see
app.services.top_high5_live.resolve_live_top_high5 and
KALUTASOCIETY_DERIVED_TOPHIGH5_FINAL_IMPLEMENTATION). Fixtures for the
default-resolution tests below now also create real ContestantSeason
membership + a vote for each round's contestant -- what the derived
resolver actually reads -- alongside the pre-existing frozen rows (kept in
place specifically to prove frozen data no longer has any influence). Only
`?round_id=` (explicit) still reads top_high5_results, exercised by
test_explicit_round_id_bypasses_close_date_gate.

2026-09-23 calendar-month-filter update: the close-date-based "has this
round's own level genuinely finished" gating described above has been
replaced by an exact calendar-month target (target_month = current month
minus a fixed per-level offset -- see app.services.top_high5_live's module
docstring). There is no longer a "closed vs not yet closed" pair to choose
between; there is exactly one target month per level, and a round either
is or is not that month's round. Fixtures below now give each round a real
`submission_start_date` (its cohort month) instead of manipulating the
`_end_date` columns, which the calendar rule no longer reads for
selection (they remain informational stage_open/close_date metadata only).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models.contest import Contest
from app.models.contests import ContestantSeason, ContestSeason, Contestant, SeasonLevel, TopHigh5Result
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.models.voting import ContestantVoting
from app.services.top_high5_live import target_cohort_month


def _round(
    db,
    suffix: str,
    *,
    submission_month_start: date,
    country_season_end_date=None,
    regional_end_date=None,
    continental_end_date=None,
    global_end_date=None,
    status: RoundStatus = RoundStatus.ACTIVE,
) -> Round:
    rnd = Round(
        name=f"Round {submission_month_start.strftime('%B %Y')} {suffix}",
        status=status,
        submission_start_date=submission_month_start,
        submission_end_date=submission_month_start,
        country_season_end_date=country_season_end_date,
        regional_end_date=regional_end_date,
        continental_end_date=continental_end_date,
        global_end_date=global_end_date,
    )
    db.add(rnd)
    db.flush()
    return rnd


def _contestant(db, *, suffix: str, rnd: Round, contest: Contest, **extra) -> Contestant:
    owner = User(email=f"th5rr-{suffix}@example.test", hashed_password="unused")
    db.add(owner)
    db.flush()
    c = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        contest_id=contest.id,
        season_id=contest.id,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        title=f"Contestant {suffix}",
        **extra,
    )
    db.add(c)
    db.flush()
    return c


def _frozen_row(
    db,
    *,
    contest: Contest,
    level: SeasonLevel,
    jurisdiction: str,
    rnd: Round,
    season: ContestSeason,
    contestant: Contestant,
    created_at: datetime,
    rank: int = 1,
) -> TopHigh5Result:
    row = TopHigh5Result(
        contestant_id=contestant.id,
        contest_id=contest.id,
        category_id=contest.category_id,
        level=level,
        jurisdiction=jurisdiction,
        round_id=rnd.id,
        from_season_id=season.id,
        to_season_id=None,
        rank=rank,
        total_points=10,
        total_votes=1,
        migrated=False,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _member(db, *, contestant: Contestant, season: ContestSeason) -> ContestantSeason:
    row = ContestantSeason(contestant_id=contestant.id, season_id=season.id, is_active=True)
    db.add(row)
    db.flush()
    return row


def _vote(db, *, contestant: Contestant, contest: Contest, season: ContestSeason, suffix: str) -> ContestantVoting:
    voter = User(email=f"th5rr-voter-{suffix}@example.test", hashed_password="unused")
    db.add(voter)
    db.flush()
    row = ContestantVoting(
        user_id=voter.id,
        contestant_id=contestant.id,
        contest_id=contest.id,
        season_id=season.id,
        vote_bucket_key=f"ty:{contest.contest_type or ''}:{contest.contest_mode or ''}",
        position=1,
        points=10,
    )
    db.add(row)
    db.flush()
    return row


def _setup_target_and_other_month(
    db,
    *,
    level: SeasonLevel,
    today: date,
    other_month_start: date,
):
    """One contest with real cohort data in the level's EXACT calendar
    target month for `today` (see target_cohort_month), and a second round
    for a DIFFERENT month, in the same jurisdiction, so they compete for
    auto-selection. Only the target month's round must ever be picked."""
    target_month_start = target_cohort_month(level, today)
    assert target_month_start != other_month_start, "test fixture must use two genuinely different months"

    contest = Contest(
        name=f"Contest {level.value}-resolution",
        contest_type="t",
        contest_mode="participation",
        level=level.value,
    )
    db.add(contest)
    db.flush()

    target_round = _round(db, "target", submission_month_start=target_month_start)
    other_round = _round(db, "other", submission_month_start=other_month_start)
    for rnd in (target_round, other_round):
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))

    target_season = ContestSeason(round_id=target_round.id, title="target season", level=level)
    other_season = ContestSeason(round_id=other_round.id, title="other season", level=level)
    db.add_all([target_season, other_season])
    db.flush()

    # REGIONAL jurisdiction must be a region-pool label ("East Africa"), not
    # a country name -- matches how real production rows are frozen (see
    # test_top_high5_mode_aware_resolver.py) and how the endpoint's own
    # REGIONAL filter (regional_pool_id_for_region_label) actually matches.
    # COUNTRY jurisdiction is genuinely the country name itself.
    if level == SeasonLevel.GLOBAL:
        jurisdiction = "Global"
    elif level == SeasonLevel.CONTINENT:
        jurisdiction = "Africa"
    elif level == SeasonLevel.REGIONAL:
        jurisdiction = "East Africa"
    else:
        jurisdiction = "Kenya"

    target_contestant = _contestant(db, suffix="target", rnd=target_round, contest=contest, continent="Africa", country="Kenya")
    other_contestant = _contestant(db, suffix="other", rnd=other_round, contest=contest, continent="Africa", country="Kenya")

    # Real cohort membership + a vote each -- what the derived resolver
    # actually reads (see module docstring). The frozen rows below remain,
    # specifically to prove they no longer influence the default result
    # (neither which round is picked, nor being required at all).
    _member(db, contestant=target_contestant, season=target_season)
    _member(db, contestant=other_contestant, season=other_season)
    _vote(db, contestant=target_contestant, contest=contest, season=target_season, suffix="target")
    _vote(db, contestant=other_contestant, contest=contest, season=other_season, suffix="other")

    _frozen_row(
        db, contest=contest, level=level, jurisdiction=jurisdiction, rnd=other_round,
        season=other_season, contestant=other_contestant,
        created_at=datetime.utcnow(),  # written LAST -- must not matter at all
    )
    _frozen_row(
        db, contest=contest, level=level, jurisdiction=jurisdiction, rnd=target_round,
        season=target_season, contestant=target_contestant,
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db.commit()
    return target_round, other_round, target_contestant, other_contestant


def test_continent_resolution_ignores_created_at_and_uses_calendar_target(db, client):
    """A later `created_at` on the OTHER-month round's frozen row --
    simulating a repair/backfill run -- must have zero effect. Only the
    exact calendar target month's round is ever selected."""
    today = date.today()
    continent_target = target_cohort_month(SeasonLevel.CONTINENT, today)
    other_month = date(continent_target.year - 1, continent_target.month, 1)  # a year off, unambiguous
    target_round, _other_round, target_c, _other_c = _setup_target_and_other_month(
        db, level=SeasonLevel.CONTINENT, today=today, other_month_start=other_month,
    )

    resp = client.get("/api/v1/seasons/top-high5", params={"level": "continent", "country": "Kenya"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] == target_round.id, (
        "picked the stale, later-written OTHER-month round instead of the "
        "exact calendar target month"
    )
    contestant_ids = {row["contestant_id"] for c in body["contests"] for row in c["rows"]}
    assert contestant_ids == {target_c.id}


def test_continent_resolution_excludes_non_target_month_round(db, client):
    """A round for a month other than the exact calendar target must never
    be auto-selected, even though it already has a frozen row (as
    maintenance tooling has, in production, written prematurely) and even
    though it has the highest round_id / most recent created_at."""
    today = date.today()
    other_month = target_cohort_month(SeasonLevel.GLOBAL, today)  # a different, safely-distinct month
    target_round, _other_round, _target_c, other_c = _setup_target_and_other_month(
        db, level=SeasonLevel.CONTINENT, today=today, other_month_start=other_month,
    )

    resp = client.get("/api/v1/seasons/top-high5", params={"level": "continent", "country": "Kenya"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] == target_round.id, (
        "auto-selected a round for the wrong calendar month -- the exact "
        "production-shaped defect this file guards against"
    )
    contestant_ids = {row["contestant_id"] for c in body["contests"] for row in c["rows"]}
    assert other_c.id not in contestant_ids


def test_country_resolution_excludes_non_target_month_round(db, client):
    today = date.today()
    other_month = target_cohort_month(SeasonLevel.GLOBAL, today)
    target_round, _other_round, _target_c, _other_c = _setup_target_and_other_month(
        db, level=SeasonLevel.COUNTRY, today=today, other_month_start=other_month,
    )
    resp = client.get("/api/v1/seasons/top-high5", params={"level": "country", "country": "Kenya"})
    assert resp.status_code == 200
    assert resp.json()["round_id"] == target_round.id


def test_regional_resolution_excludes_non_target_month_round(db, client):
    today = date.today()
    other_month = target_cohort_month(SeasonLevel.GLOBAL, today)
    target_round, _other_round, _target_c, _other_c = _setup_target_and_other_month(
        db, level=SeasonLevel.REGIONAL, today=today, other_month_start=other_month,
    )
    resp = client.get("/api/v1/seasons/top-high5", params={"level": "regional", "country": "Kenya"})
    assert resp.status_code == 200
    assert resp.json()["round_id"] == target_round.id


def test_global_resolution_excludes_non_target_month_round(db, client):
    today = date.today()
    other_month = target_cohort_month(SeasonLevel.CITY, today)
    target_round, _other_round, _target_c, _other_c = _setup_target_and_other_month(
        db, level=SeasonLevel.GLOBAL, today=today, other_month_start=other_month,
    )
    resp = client.get("/api/v1/seasons/top-high5", params={"level": "global"})
    assert resp.status_code == 200
    assert resp.json()["round_id"] == target_round.id


def test_global_resolution_works_with_null_participation_end_date_columns(db, client):
    """The calendar rule never reads Round.<level>_end_date for selection
    (only for informational stage_open/close_date metadata) -- a round
    with those columns NULL must still resolve normally, purely from its
    submission_start_date (cohort month) matching the calendar target."""
    today = date.today()
    target_month = target_cohort_month(SeasonLevel.GLOBAL, today)
    contest = Contest(name="Contest global-null-date", contest_type="t", contest_mode="participation", level="global")
    db.add(contest)
    db.flush()

    rnd = _round(db, "legacy-completed", submission_month_start=target_month, status=RoundStatus.COMPLETED, global_end_date=None)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title="legacy global season", level=SeasonLevel.GLOBAL)
    db.add(season)
    db.flush()
    contestant = _contestant(db, suffix="legacy-g", rnd=rnd, contest=contest)
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="legacy-g")
    _frozen_row(
        db, contest=contest, level=SeasonLevel.GLOBAL, jurisdiction="Global", rnd=rnd,
        season=season, contestant=contestant, created_at=datetime.utcnow(),
    )
    db.commit()

    resp = client.get("/api/v1/seasons/top-high5", params={"level": "global"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] == rnd.id
    contestant_ids = {row["contestant_id"] for c in body["contests"] for row in c["rows"]}
    assert contestant_ids == {contestant.id}


def test_no_eligible_round_returns_empty_not_an_error(db, client):
    """A level with only a NON-target-month round's frozen row (no round
    for the exact calendar target month exists at all) must return an
    empty result, not fall back to the wrong-month round, and not error."""
    contest = Contest(name="Contest none-eligible", contest_type="t", contest_mode="participation", level="continent")
    db.add(contest)
    db.flush()

    today = date.today()
    # Deliberately a month that is NOT this level's calendar target.
    wrong_month = target_cohort_month(SeasonLevel.CITY, today)
    rnd = _round(db, "still-open", submission_month_start=wrong_month)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title="open season", level=SeasonLevel.CONTINENT)
    db.add(season)
    db.flush()
    contestant = _contestant(db, suffix="open-only", rnd=rnd, contest=contest, continent="Africa")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="open-only")
    _frozen_row(
        db, contest=contest, level=SeasonLevel.CONTINENT, jurisdiction="Africa", rnd=rnd,
        season=season, contestant=contestant, created_at=datetime.utcnow(),
    )
    db.commit()

    # Real cohort membership exists, but for the wrong calendar month --
    # must still return empty, never substitute it.
    resp = client.get("/api/v1/seasons/top-high5", params={"level": "continent", "country": "Kenya"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] is None
    assert body["contests"] == []


def test_explicit_round_id_bypasses_close_date_gate(db, client):
    """Explicit ?round_id=... must still return that exact round's frozen
    data even when it is NOT the calendar target month -- the target-month
    gate only applies to automatic resolution, per the existing contract
    that explicit/manual selection is always honored exactly."""
    contest = Contest(name="Contest explicit-open", contest_type="t", contest_mode="participation", level="continent")
    db.add(contest)
    db.flush()

    wrong_month = target_cohort_month(SeasonLevel.CITY, date.today())
    rnd = _round(db, "explicit-open", submission_month_start=wrong_month)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title="open season", level=SeasonLevel.CONTINENT)
    db.add(season)
    db.flush()
    contestant = _contestant(db, suffix="explicit-open", rnd=rnd, contest=contest, continent="Africa")
    _frozen_row(
        db, contest=contest, level=SeasonLevel.CONTINENT, jurisdiction="Africa", rnd=rnd,
        season=season, contestant=contestant, created_at=datetime.utcnow(),
    )
    db.commit()

    resp = client.get(
        "/api/v1/seasons/top-high5",
        params={"level": "continent", "country": "Kenya", "round_id": rnd.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] == rnd.id
    contestant_ids = {row["contestant_id"] for c in body["contests"] for row in c["rows"]}
    assert contestant_ids == {contestant.id}
