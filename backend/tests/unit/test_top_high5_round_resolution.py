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
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.models.contest import Contest
from app.models.contests import ContestSeason, Contestant, SeasonLevel, TopHigh5Result
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User


def _round(
    db,
    suffix: str,
    *,
    country_season_end_date=None,
    regional_end_date=None,
    continental_end_date=None,
    global_end_date=None,
    status: RoundStatus = RoundStatus.ACTIVE,
) -> Round:
    rnd = Round(
        name=f"Round {suffix}",
        status=status,
        submission_start_date=date(2026, 1, 1),
        submission_end_date=date(2026, 1, 31),
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


def _setup_two_rounds_one_level(
    db,
    *,
    level: SeasonLevel,
    date_field: str,
    old_end_date,
    new_end_date,
    old_created_at=None,
    new_created_at=None,
):
    """Two rounds, one frozen row each at `level`, in the same jurisdiction
    ("Africa"/continent style contest) so they compete for auto-selection."""
    contest = Contest(
        name=f"Contest {level.value}-resolution",
        contest_type="t",
        contest_mode="nomination",
        level=level.value,
    )
    db.add(contest)
    db.flush()

    old_round = _round(db, "old", **{date_field: old_end_date})
    new_round = _round(db, "new", **{date_field: new_end_date})
    for rnd in (old_round, new_round):
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))

    old_season = ContestSeason(round_id=old_round.id, title="old season", level=level)
    new_season = ContestSeason(round_id=new_round.id, title="new season", level=level)
    db.add_all([old_season, new_season])
    db.flush()

    jurisdiction = "Africa" if level in (SeasonLevel.CONTINENT, SeasonLevel.GLOBAL) else "Kenya"
    if level == SeasonLevel.GLOBAL:
        jurisdiction = "Global"

    old_contestant = _contestant(db, suffix="old", rnd=old_round, contest=contest, continent="Africa", country="Kenya")
    new_contestant = _contestant(db, suffix="new", rnd=new_round, contest=contest, continent="Africa", country="Kenya")

    _frozen_row(
        db, contest=contest, level=level, jurisdiction=jurisdiction, rnd=new_round,
        season=new_season, contestant=new_contestant,
        created_at=new_created_at or (datetime.utcnow() - timedelta(days=30)),
    )
    _frozen_row(
        db, contest=contest, level=level, jurisdiction=jurisdiction, rnd=old_round,
        season=old_season, contestant=old_contestant,
        created_at=old_created_at or datetime.utcnow(),
    )
    db.commit()
    return old_round, new_round, old_contestant, new_contestant


def test_continent_resolution_uses_close_date_not_stale_created_at(db, client):
    """A later `created_at` on an OLDER (but still-closed) round's row --
    simulating a repair/backfill run -- must not override a genuinely newer,
    also-closed round's frozen result."""
    today = date.today()
    old_round, new_round, _old_c, new_c = _setup_two_rounds_one_level(
        db,
        level=SeasonLevel.CONTINENT,
        date_field="continental_end_date",
        old_end_date=today - timedelta(days=200),
        new_end_date=today - timedelta(days=20),
        old_created_at=datetime.utcnow(),  # written LAST, like a repair tool
        new_created_at=datetime.utcnow() - timedelta(days=30),
    )

    resp = client.get("/api/v1/seasons/top-high5", params={"level": "continent", "country": "Kenya"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] == new_round.id, (
        "picked the stale, later-written OLD round instead of the "
        "chronologically newer, also-closed round"
    )
    contestant_ids = {row["contestant_id"] for c in body["contests"] for row in c["rows"]}
    assert contestant_ids == {new_c.id}


def test_continent_resolution_excludes_not_yet_closed_round(db, client):
    """A round whose CONTINENTAL window has not actually closed yet must
    never be auto-selected, even if it already has a frozen row (as
    maintenance tooling has, in production, written prematurely) and even
    though it has the highest round_id / most recent created_at."""
    today = date.today()
    closed_round, _open_round, _closed_c, open_c = _setup_two_rounds_one_level(
        db,
        level=SeasonLevel.CONTINENT,
        date_field="continental_end_date",
        old_end_date=today - timedelta(days=20),   # genuinely closed
        new_end_date=today + timedelta(days=9),    # NOT closed yet
        old_created_at=datetime.utcnow() - timedelta(days=30),
        new_created_at=datetime.utcnow(),  # highest round_id AND newest created_at
    )

    resp = client.get("/api/v1/seasons/top-high5", params={"level": "continent", "country": "Kenya"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] == closed_round.id, (
        "auto-selected a round whose continental voting has not closed yet -- "
        "this is the exact production bug (round with the highest round_id/"
        "created_at picked over the genuinely latest CLOSED round)"
    )
    contestant_ids = {row["contestant_id"] for c in body["contests"] for row in c["rows"]}
    assert open_c.id not in contestant_ids


def test_country_resolution_excludes_not_yet_closed_round(db, client):
    today = date.today()
    closed_round, _open_round, _closed_c, _open_c = _setup_two_rounds_one_level(
        db,
        level=SeasonLevel.COUNTRY,
        date_field="country_season_end_date",
        old_end_date=today - timedelta(days=10),
        new_end_date=today + timedelta(days=5),
    )
    resp = client.get("/api/v1/seasons/top-high5", params={"level": "country", "country": "Kenya"})
    assert resp.status_code == 200
    assert resp.json()["round_id"] == closed_round.id


def test_regional_resolution_excludes_not_yet_closed_round(db, client):
    today = date.today()
    closed_round, _open_round, _closed_c, _open_c = _setup_two_rounds_one_level(
        db,
        level=SeasonLevel.REGIONAL,
        date_field="regional_end_date",
        old_end_date=today - timedelta(days=10),
        new_end_date=today + timedelta(days=5),
    )
    resp = client.get("/api/v1/seasons/top-high5", params={"level": "regional", "country": "Kenya"})
    assert resp.status_code == 200
    assert resp.json()["round_id"] == closed_round.id


def test_global_resolution_excludes_not_yet_closed_round(db, client):
    today = date.today()
    closed_round, _open_round, _closed_c, _open_c = _setup_two_rounds_one_level(
        db,
        level=SeasonLevel.GLOBAL,
        date_field="global_end_date",
        old_end_date=today - timedelta(days=10),
        new_end_date=today + timedelta(days=5),
    )
    resp = client.get("/api/v1/seasons/top-high5", params={"level": "global"})
    assert resp.status_code == 200
    assert resp.json()["round_id"] == closed_round.id


def test_global_resolution_null_date_completed_round(db, client):
    """A legacy round with its level end-date column NULL but
    Round.status == COMPLETED (matches production round 3 -- a population
    gap, not an open cohort) must still resolve, not silently return an
    empty result."""
    contest = Contest(name="Contest global-null-date", contest_type="t", contest_mode="nomination", level="global")
    db.add(contest)
    db.flush()

    rnd = _round(db, "legacy-completed", status=RoundStatus.COMPLETED, global_end_date=None)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title="legacy global season", level=SeasonLevel.GLOBAL)
    db.add(season)
    db.flush()
    contestant = _contestant(db, suffix="legacy-g", rnd=rnd, contest=contest)
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
    """A level with only a not-yet-closed round's frozen row (no closed
    round exists at all yet) must return an empty result, not fall back to
    the not-yet-closed round and not error."""
    contest = Contest(name="Contest none-eligible", contest_type="t", contest_mode="nomination", level="continent")
    db.add(contest)
    db.flush()

    rnd = _round(db, "still-open", continental_end_date=date.today() + timedelta(days=5))
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=contest.id))
    season = ContestSeason(round_id=rnd.id, title="open season", level=SeasonLevel.CONTINENT)
    db.add(season)
    db.flush()
    contestant = _contestant(db, suffix="open-only", rnd=rnd, contest=contest, continent="Africa")
    _frozen_row(
        db, contest=contest, level=SeasonLevel.CONTINENT, jurisdiction="Africa", rnd=rnd,
        season=season, contestant=contestant, created_at=datetime.utcnow(),
    )
    db.commit()

    resp = client.get("/api/v1/seasons/top-high5", params={"level": "continent", "country": "Kenya"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_id"] is None
    assert body["contests"] == []


def test_explicit_round_id_bypasses_close_date_gate(db, client):
    """Explicit ?round_id=... must still return that exact round's frozen
    data even if its level has not closed yet -- the close-date gate only
    applies to automatic ("latest") resolution, per the existing contract
    that explicit/manual selection is always honored exactly."""
    contest = Contest(name="Contest explicit-open", contest_type="t", contest_mode="nomination", level="continent")
    db.add(contest)
    db.flush()

    rnd = _round(db, "explicit-open", continental_end_date=date.today() + timedelta(days=5))
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
