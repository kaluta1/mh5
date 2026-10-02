"""Cumulative ranking, legacy contest ownership and the read-only dry-run on
REAL PostgreSQL (the unit suite runs on SQLite; production runs on PostgreSQL).

Opt-in: RUN_POSTGRES_TESTS=1 (and optionally POSTGRES_ADMIN_URL). Each test
creates a DISPOSABLE database, builds the model schema and drops it afterwards.
All rows are synthetic.

What only PostgreSQL can prove here:
* the correlated legacy-ownership SQL (Case E) is valid and means the same
  thing inside the promotion queries, where the enclosing query already joins
  the membership table;
* a whole nomination lifecycle with zero-vote stages, carried points and a
  legacy entry runs through the real scheduler path with its advisory locks;
* the dry-run runs inside a READ ONLY transaction, i.e. the database itself
  would have refused any write.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.contest import Contest
from app.models.contests import Contestant, ContestantSeason, ContestSeason, SeasonLevel, TopHigh5Result
from app.models.voting import ContestantVoting
from app.services import progression_ranking
from app.services.contestant_contest_resolution import (
    LEGACY_COLLISION_SEASON_WITHOUT_ROUND,
    contestant_belongs_to_contest_clause,
    explain_contest_resolution,
)
from app.services.progression_dry_run import simulate_due_progressions
from app.services.season_migration import SeasonMigrationService
from tests.integration.test_month_end_locking_postgres import (  # noqa: F401  (fixtures)
    _quiet,
    advisory_locks,
    clock,
    errors_of,
    make_contest,
    make_entries,
    make_round,
    make_user,
    pg,
    pytestmark,
    run_pass,
)

MAY = date(2026, 5, 1)


def season_of(db, rnd_id, level):
    return (db.query(ContestSeason)
            .filter(ContestSeason.round_id == rnd_id, ContestSeason.level == level,
                    ContestSeason.is_deleted == False).first())  # noqa: E712


def active_ids(db, rnd_id, level, contest_id) -> set:
    s = season_of(db, rnd_id, level)
    if s is None:
        return set()
    return {r[0] for r in db.query(ContestantSeason.contestant_id)
            .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
            .filter(ContestantSeason.season_id == s.id, ContestantSeason.is_active == True)  # noqa: E712
            .filter(contestant_belongs_to_contest_clause(contest_id)).all()}


def give_points(db, contestant_id, contest_id, season_id, points):
    ct = db.get(Contest, contest_id)
    db.add(ContestantVoting(user_id=make_user(db).id, contestant_id=contestant_id, contest_id=contest_id,
                            season_id=season_id, position=1, points=points,
                            vote_bucket_key=SeasonMigrationService._top_high5_bucket_key_for_contest(ct)))
    db.commit()


def seed(Session_):
    """A May nomination cohort of 7: six modern entries and one legacy row
    (contest_id NULL, season_id = contest id = id of a round-less season)."""
    db = Session_()
    rnd = make_round(db, MAY)
    ct = make_contest(db, "nomination", [rnd])
    entries = make_entries(db, ct, rnd, n=6)
    for day, c in enumerate(entries, start=1):
        c.registration_date = c.created_at = datetime(2026, 5, day, 12)
    owner = make_user(db)
    when = datetime(2026, 5, 20, 12)
    legacy = Contestant(user_id=owner.id, season_id=ct.id, contest_id=None, round_id=rnd.id, title="legacy",
                        entry_type="nomination", city="Arusha", country="Tanzania", region="East Africa",
                        continent="Africa", is_active=True, is_deleted=False, is_qualified=True,
                        registration_date=when, created_at=when)
    db.add(legacy)
    db.commit()
    ids = (rnd.id, ct.id, [c.id for c in entries], legacy.id)
    db.close()
    return ids


def test_legacy_clause_and_lifecycle_on_postgres(pg, clock):
    engine, observer, Session_ = pg
    rnd_id, ct_id, entry_ids, legacy_id = seed(Session_)

    db = Session_()
    legacy = db.get(Contestant, legacy_id)
    assert explain_contest_resolution(db, legacy, ct_id).code == LEGACY_COLLISION_SEASON_WITHOUT_ROUND
    resolved = {r[0] for r in db.query(Contestant.id).filter(contestant_belongs_to_contest_clause(ct_id)).all()}
    assert resolved == set(entry_ids) | {legacy_id}
    db.close()

    out = run_pass(Session_, clock, datetime(2026, 6, 1, 0, 30))
    assert errors_of(out) == []
    db = Session_()
    country = season_of(db, rnd_id, SeasonLevel.COUNTRY)
    assert active_ids(db, rnd_id, SeasonLevel.COUNTRY, ct_id) == set(entry_ids) | {legacy_id}
    give_points(db, legacy_id, ct_id, country.id, 5)          # only the legacy nominee is voted
    country_id = country.id
    db.close()

    # Country -> Regional: legacy first (5 points), then the four earliest zero-vote entries.
    out = run_pass(Session_, clock, datetime(2026, 7, 1, 0, 30))
    assert errors_of(out) == []
    db = Session_()
    expected = {legacy_id, *entry_ids[:4]}
    assert active_ids(db, rnd_id, SeasonLevel.REGIONAL, ct_id) == expected
    regional = season_of(db, rnd_id, SeasonLevel.REGIONAL)
    give_points(db, entry_ids[3], ct_id, regional.id, 3)
    scores = progression_ranking.score_candidates(
        db, contest=db.get(Contest, ct_id), round_obj=regional.round, level=SeasonLevel.REGIONAL,
        contestants=db.query(Contestant).filter(Contestant.id.in_(expected)).all())
    assert (scores[legacy_id].carried_points, scores[legacy_id].stage_points,
            scores[legacy_id].cumulative_points) == (5, 0, 5)
    assert scores[entry_ids[3]].cumulative_points == 3
    frozen = (db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct_id,
                                              TopHigh5Result.from_season_id == country_id)
              .order_by(TopHigh5Result.rank).all())
    assert [r.contestant_id for r in frozen] == [legacy_id, *entry_ids[:4]]
    assert [r.total_points for r in frozen] == [5, 0, 0, 0, 0] and all(r.migrated for r in frozen)
    db.close()

    # Regional -> Continental -> Global with no further votes: nobody is left behind.
    for month, level in ((8, SeasonLevel.CONTINENT), (9, SeasonLevel.GLOBAL)):
        out = run_pass(Session_, clock, datetime(2026, month, 1, 0, 30))
        assert errors_of(out) == []
        db = Session_()
        assert active_ids(db, rnd_id, level, ct_id) == expected, level
        db.close()

    # Retries: nothing moves, no timestamp is rewritten, no lock is left behind.
    db = Session_()
    snapshot = sorted((m.contestant_id, m.season_id, m.is_active, m.joined_at)
                      for m in db.query(ContestantSeason).all())
    votes_before = db.query(ContestantVoting).count()
    db.close()
    for hour in (1, 2, 3):
        out = run_pass(Session_, clock, datetime(2026, 9, 1, hour, 30))
        assert errors_of(out) == []
    db = Session_()
    assert sorted((m.contestant_id, m.season_id, m.is_active, m.joined_at)
                  for m in db.query(ContestantSeason).all()) == snapshot
    assert db.query(ContestantVoting).count() == votes_before == 2
    db.close()
    assert advisory_locks(observer) == []


def test_dry_run_runs_in_a_read_only_transaction_and_predicts_the_promotion(pg, clock):
    engine, observer, Session_ = pg
    rnd_id, ct_id, entry_ids, legacy_id = seed(Session_)
    assert errors_of(run_pass(Session_, clock, datetime(2026, 6, 1, 0, 30))) == []

    def fingerprint():
        with observer.connect() as c:
            return c.execute(text(
                "select (select count(*) from contestant_seasons), "
                "(select count(*) from contest_seasons), (select count(*) from top_high5_results), "
                "(select count(*) from contest_season_links), "
                "(select md5(string_agg(id::text || is_active::text || joined_at::text, ',' order by id)) "
                " from contestant_seasons), "
                "(select md5(string_agg(id::text || coalesce(is_qualified::text, 'n') || coalesce(region, ''), ',' "
                " order by id)) from contestants)")).fetchone()

    before = fingerprint()
    db = Session_()
    db.execute(text("SET TRANSACTION READ ONLY"))
    report = simulate_due_progressions(db, today=date(2026, 7, 1))
    # The transaction really is read-only: PostgreSQL refuses a write in it.
    with pytest.raises(DBAPIError):
        db.execute(text("update contestants set is_qualified = false"))
    db.rollback()
    db.close()
    assert fingerprint() == before

    (hop,) = report["transitions"]
    would_advance = {e["contestant_id"] for e in hop["entries"] if e["outcome"] == "ADVANCES"}
    assert would_advance == set(entry_ids[:5])            # zero votes: the five earliest submissions
    legacy_row = next(e for e in hop["entries"] if e["contestant_id"] == legacy_id)
    assert legacy_row["contest_resolution"] == LEGACY_COLLISION_SEASON_WITHOUT_ROUND
    assert legacy_row["outcome"] == "OUTSIDE_TOP_5" and legacy_row["rank"] == 7

    assert errors_of(run_pass(Session_, clock, datetime(2026, 7, 1, 0, 30))) == []
    db = Session_()
    assert active_ids(db, rnd_id, SeasonLevel.REGIONAL, ct_id) == would_advance
    db.close()
