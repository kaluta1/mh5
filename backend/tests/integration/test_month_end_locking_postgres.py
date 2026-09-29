"""Month-end progression locking on REAL PostgreSQL (SQLite cannot prove it).

Opt-in: RUN_POSTGRES_TESTS=1 (and optionally POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each test creates a DISPOSABLE
database (never an existing one), builds the model schema, and drops it
afterwards. All rows are synthetic.

The engine mirrors the production pool (QueuePool, pool_size 10) and every test
first warms the pool to TWO idle connections, because the defect only exists
when the ORM session can be handed a different pooled connection after a commit.
statement_timeout is 5 s here, so a stranded advisory lock turns into a fast,
visible failure instead of a hang.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import Enum as SAEnum, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401  (register every model)
import app.services.season_migration as sm
from app.db.base_class import Base
from app.models.contest import Contest
from app.models.contests import Contestant, ContestantSeason, ContestSeason, SeasonLevel
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.models.voting import ContestantVoting
from app.services.contest_status import contest_status_service
from app.services.season_migration import SEASON_MIGRATION_LOCK_KEY, SeasonMigrationService

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres@127.0.0.1:5432/postgres")


# ---------------------------------------------------------------------------
# disposable database
# ---------------------------------------------------------------------------

def _build_schema(engine) -> None:
    """Model schema. Some enums are declared create_type=False (created by old
    migrations) or wrapped in TypeDecorators, so create every enum first."""
    import sys

    seen, candidates = set(), []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            candidates += [col.type, getattr(col.type, "impl", None)]
    for name, mod in list(sys.modules.items()):
        if name.startswith("app.models") and mod is not None:
            candidates += [v for v in vars(mod).values() if isinstance(v, SAEnum)]
    with engine.begin() as conn:
        for ty in candidates:
            if isinstance(ty, SAEnum) and getattr(ty, "name", None) and ty.name not in seen:
                seen.add(ty.name)
                ty.create(conn, checkfirst=True)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def pg():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    name = f"month_end_lock_{uuid.uuid4().hex[:10]}"
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name)
    engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20, pool_timeout=10,
                           connect_args={"options": "-c statement_timeout=5000"})
    observer = create_engine(url, poolclass=NullPool)
    try:
        _build_schema(engine)
        yield engine, observer, sessionmaker(bind=engine, autocommit=False, autoflush=False)
    finally:
        engine.dispose()
        observer.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def warm_pool(engine, n: int = 2) -> None:
    conns = [engine.connect() for _ in range(n)]
    for c in conns:
        c.execute(text("select 1"))
    for c in conns:
        c.close()


def advisory_locks(observer) -> list:
    with observer.connect() as c:
        return c.execute(text(
            "select l.pid, l.classid, l.objid, l.objsubid from pg_locks l "
            "join pg_database d on d.oid = l.database "
            "where l.locktype = 'advisory' and d.datname = current_database()")).fetchall()


def can_take(observer, sql: str, params: dict) -> bool:
    with observer.connect() as c:
        got = bool(c.execute(text(sql.format(fn="pg_try_advisory_lock")), params).scalar())
        if got:
            c.execute(text(sql.format(fn="pg_advisory_unlock")), params)
        return got


MAIN_LOCK_SQL = "select {fn}(:k)"
SEASON_LOCK_SQL = "select {fn}(:k, hashtext(:c))"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    import builtins

    monkeypatch.setattr(builtins, "print", lambda *a, **k: None)


@pytest.fixture
def clock(monkeypatch):
    state = {"now": datetime(2026, 1, 1)}

    class FrozenDate(date):
        @classmethod
        def today(cls):
            n = state["now"]
            return date(n.year, n.month, n.day)

    monkeypatch.setattr(sm, "date", FrozenDate)
    monkeypatch.setattr(contest_status_service, "_utc_now", lambda: state["now"])
    return lambda dt: state.__setitem__("now", dt)


# ---------------------------------------------------------------------------
# synthetic lifecycle data
# ---------------------------------------------------------------------------

def _month_end(d: date) -> date:
    return SeasonMigrationService._add_months(d, 1) - timedelta(days=1)


def make_round(db, month: date) -> Round:
    m = [SeasonMigrationService._add_months(month, i) for i in range(6)]
    rnd = Round(name=f"Round {month:%B %Y}", status=RoundStatus.ACTIVE,
                submission_start_date=m[0], submission_end_date=_month_end(m[0]),
                voting_start_date=m[1], voting_end_date=_month_end(m[5]),
                city_season_start_date=m[1], city_season_end_date=_month_end(m[1]),
                country_season_start_date=m[2], country_season_end_date=_month_end(m[2]),
                regional_start_date=m[3], regional_end_date=_month_end(m[3]),
                continental_start_date=m[4], continental_end_date=_month_end(m[4]),
                global_start_date=m[5], global_end_date=_month_end(m[5]))
    db.add(rnd)
    db.commit()
    return rnd


def make_user(db) -> User:
    u = User(email=f"u{uuid.uuid4().hex[:10]}@example.test", hashed_password="x", is_active=True)
    db.add(u)
    db.flush()
    return u


def make_contest(db, mode: str, rounds) -> Contest:
    uid = uuid.uuid4().hex[:6]
    # Legacy overload: contestants.season_id stores Contest.id (FK to contest_seasons).
    legacy = ContestSeason(title=f"legacy-{uid}", level=SeasonLevel.COUNTRY)
    db.add(legacy)
    db.flush()
    ct = Contest(id=legacy.id, name=f"C {uid}", contest_type=f"t{uid}", contest_mode=mode,
                 level="city" if mode == "participation" else "country", is_active=True, is_deleted=False,
                 requires_kyc=False)
    db.add(ct)
    db.flush()
    for rnd in rounds:
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    return ct


def make_entries(db, ct, rnd, n=6) -> list:
    when = datetime.combine(rnd.submission_start_date, datetime.min.time()) + timedelta(days=9)
    out = []
    for k in range(1, n + 1):
        u = make_user(db)
        c = Contestant(user_id=u.id, season_id=ct.id, contest_id=ct.id, round_id=rnd.id, title=f"{ct.id}-k{k}",
                       entry_type=ct.contest_mode, city="Arusha", country="Tanzania", region="East Africa",
                       continent="Africa", is_active=True, is_deleted=False, is_qualified=True,
                       registration_date=when, created_at=when)
        db.add(c)
        out.append(c)
    db.commit()
    return out


def vote_active_members(db, rnd, level, when):
    s = (db.query(ContestSeason).filter(ContestSeason.round_id == rnd.id, ContestSeason.level == level,
                                        ContestSeason.is_deleted == False).first())  # noqa: E712
    members = (db.query(Contestant).join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
               .filter(ContestantSeason.season_id == s.id, ContestantSeason.is_active == True).all())  # noqa: E712
    for c in members:
        ct = db.get(Contest, c.contest_id)
        for _ in range(int(c.title.rsplit("-k", 1)[1])):
            v = make_user(db)
            db.add(ContestantVoting(user_id=v.id, contestant_id=c.id, contest_id=ct.id, season_id=s.id,
                                    vote_bucket_key=SeasonMigrationService._top_high5_bucket_key_for_contest(ct),
                                    vote_date=when, position=1, points=1))
    db.commit()


def active_count(db, rnd, level, ct) -> int:
    return (db.query(ContestantSeason).join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
            .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
            .filter(ContestSeason.round_id == rnd.id, ContestSeason.level == level,
                    ContestantSeason.is_active == True, Contestant.contest_id == ct.id).count())  # noqa: E712


def run_pass(Session_, clock, when):
    clock(when)
    s = Session_()
    try:
        out = SeasonMigrationService.check_and_process_migrations(s, allow_multi_hop=True)
        s.commit()
        return out
    finally:
        s.close()


def errors_of(out) -> list:
    return [(r.get("contest_id"), r.get("action"), str((r.get("result") or {}).get("error"))[:160])
            for r in out.get("results", []) if (r.get("result") or {}).get("error")]


def seed_city_due(Session_, n_contests=3):
    """n personal contests whose City stage opens 2026-09-01 (August cohort)."""
    db = Session_()
    rnd = make_round(db, date(2026, 8, 1))
    cts = [make_contest(db, "participation", [rnd]) for _ in range(n_contests)]
    for ct in cts:
        make_entries(db, ct, rnd)
    ids = (rnd.id, [c.id for c in cts])
    db.close()
    return ids


# ---------------------------------------------------------------------------
# TEST 1 / 3: main lock released after success; another connection can take it
# ---------------------------------------------------------------------------

def test_main_lock_released_after_successful_run(pg, clock):
    engine, observer, Session_ = pg
    seed_city_due(Session_)
    warm_pool(engine)
    out = run_pass(Session_, clock, datetime(2026, 9, 1, 0, 30))   # commits many times while locked
    assert not errors_of(out), errors_of(out)
    assert advisory_locks(observer) == []
    assert can_take(observer, MAIN_LOCK_SQL, {"k": SEASON_MIGRATION_LOCK_KEY})


# ---------------------------------------------------------------------------
# TEST 2: main lock released after an exception inside the protected run
# ---------------------------------------------------------------------------

def test_main_lock_released_after_exception(pg, clock, monkeypatch):
    engine, observer, Session_ = pg
    warm_pool(engine)

    def boom(db, *a, **k):
        db.execute(text("select 1"))
        db.commit()                      # connection goes back to the pool mid-run
        db.execute(text("select 1"))
        raise RuntimeError("synthetic failure inside the locked section")

    monkeypatch.setattr(SeasonMigrationService, "_check_and_process_migrations_locked", staticmethod(boom))
    clock(datetime(2026, 9, 1))
    s = Session_()
    with pytest.raises(RuntimeError):
        SeasonMigrationService.check_and_process_migrations(s)
    s.close()
    assert advisory_locks(observer) == []
    assert can_take(observer, MAIN_LOCK_SQL, {"k": SEASON_MIGRATION_LOCK_KEY})


def test_second_run_is_skipped_only_while_the_first_holds_the_lock(pg, clock):
    engine, observer, Session_ = pg
    holder = observer.connect()
    holder.execute(text("select pg_advisory_lock(:k)"), {"k": SEASON_MIGRATION_LOCK_KEY})
    try:
        out = run_pass(Session_, clock, datetime(2026, 9, 1))
        assert out.get("skipped") == "locked"
    finally:
        holder.execute(text("select pg_advisory_unlock(:k)"), {"k": SEASON_MIGRATION_LOCK_KEY})
        holder.close()
    out = run_pass(Session_, clock, datetime(2026, 9, 1))
    assert out.get("skipped") is None
    assert advisory_locks(observer) == []


# ---------------------------------------------------------------------------
# TEST 4: season-creation lock is not retained by any pooled connection
# ---------------------------------------------------------------------------

def test_season_lock_not_retained_after_commit(pg):
    engine, observer, Session_ = pg
    db = Session_()
    rnd = make_round(db, date(2026, 8, 1))
    rid = rnd.id
    db.close()
    warm_pool(engine)
    db = Session_()
    db.execute(text("select 1"))
    season = SeasonMigrationService.get_or_create_season(db, SeasonLevel.GLOBAL, round_id=rid)  # creates + commits
    db.close()
    assert season.id is not None
    assert advisory_locks(observer) == []
    assert can_take(observer, SEASON_LOCK_SQL, {"k": SEASON_MIGRATION_LOCK_KEY, "c": f"{rid}:global"})


# ---------------------------------------------------------------------------
# TEST 5: concurrent season requests cannot create duplicates
# ---------------------------------------------------------------------------

def test_concurrent_season_requests_create_one_season(pg):
    engine, observer, Session_ = pg
    db = Session_()
    rid = make_round(db, date(2026, 8, 1)).id
    db.close()

    def slow_insert(session, flush_context, instances):
        if any(isinstance(o, ContestSeason) for o in session.new):
            time.sleep(0.4)              # widen the select->insert race window

    event.listen(Session, "before_flush", slow_insert)
    ids, errors = [], []
    barrier = threading.Barrier(4)

    def worker():
        s = Session_()
        try:
            barrier.wait()
            ids.append(SeasonMigrationService.get_or_create_season(s, SeasonLevel.REGIONAL, round_id=rid).id)
            s.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))
        finally:
            s.close()

    try:
        threads = [threading.Thread(target=worker) for _ in range(4)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
    finally:
        event.remove(Session, "before_flush", slow_insert)
    assert not errors, errors
    assert len(set(ids)) == 1
    with observer.connect() as c:
        n = c.execute(text("select count(*) from contest_seasons where round_id=:r and level='regional'"),
                      {"r": rid}).scalar()
    assert n == 1
    assert advisory_locks(observer) == []


# ---------------------------------------------------------------------------
# TEST 6: multi-contest Oct-1 run completes in one pass, no stale-lock timeouts
# ---------------------------------------------------------------------------

def test_multi_contest_october_first_completes_in_one_pass(pg, clock):
    engine, observer, Session_ = pg
    db = Session_()
    aug, sep = make_round(db, date(2026, 8, 1)), make_round(db, date(2026, 9, 1))
    personal = [make_contest(db, "participation", [aug, sep]) for _ in range(3)]
    nomination = [make_contest(db, "nomination", [aug, sep]) for _ in range(3)]
    for ct in personal + nomination:
        make_entries(db, ct, aug)
        make_entries(db, ct, sep)
    aug_id, sep_id = aug.id, sep.id
    personal_ids, nomination_ids = [c.id for c in personal], [c.id for c in nomination]
    db.close()

    # September 1: August personal cohort enters City, August nominations enter Country
    # (several contests create the same new (round, level) seasons in one pass).
    warm_pool(engine)
    out_sep = run_pass(Session_, clock, datetime(2026, 9, 1, 0, 30))
    assert not errors_of(out_sep), errors_of(out_sep)
    db = Session_()
    vote_active_members(db, db.get(Round, aug_id), SeasonLevel.CITY, datetime(2026, 9, 15, 12))
    vote_active_members(db, db.get(Round, aug_id), SeasonLevel.COUNTRY, datetime(2026, 9, 15, 12))
    db.close()
    assert advisory_locks(observer) == []

    # October 1 on a warm two-connection pool (production shape).
    warm_pool(engine)
    t0 = time.monotonic()
    out = run_pass(Session_, clock, datetime(2026, 10, 1, 0, 5))
    elapsed = time.monotonic() - t0
    assert not errors_of(out), errors_of(out)
    assert elapsed < 30, f"pass took {elapsed:.1f}s (stale-lock waits?)"

    db = Session_()
    aug, sep = db.get(Round, aug_id), db.get(Round, sep_id)
    for ct in (db.get(Contest, i) for i in personal_ids):
        assert active_count(db, aug, SeasonLevel.COUNTRY, ct) == 5     # City -> Country, top 5
        assert active_count(db, sep, SeasonLevel.CITY, ct) == 6        # Submission -> City
    for ct in (db.get(Contest, i) for i in nomination_ids):
        assert active_count(db, aug, SeasonLevel.REGIONAL, ct) == 5    # Country -> Regional, top 5
        assert active_count(db, sep, SeasonLevel.COUNTRY, ct) == 6     # Nomination -> Country
    dup = db.execute(text("select count(*) from (select round_id, level from contest_seasons where not is_deleted "
                          "and round_id is not null group by 1,2 having count(*) > 1) x")).scalar()
    db.close()
    assert dup == 0
    assert advisory_locks(observer) == []

    before = advisory_locks(observer)
    again = run_pass(Session_, clock, datetime(2026, 10, 1, 0, 50))   # idempotent rerun
    assert not errors_of(again) and before == advisory_locks(observer) == []


# ---------------------------------------------------------------------------
# TEST 7: a DB error in one contest leaves a usable transaction for the rest
# ---------------------------------------------------------------------------

def test_db_error_in_one_contest_rolls_back_and_pass_continues(pg, clock, monkeypatch):
    engine, observer, Session_ = pg
    rid, (first, second, third) = seed_city_due(Session_)
    original = SeasonMigrationService.migrate_to_city_season

    def failing(db, contest_id, round_id):
        if contest_id == first:
            db.execute(text("select 1/0"))      # real PostgreSQL error: transaction aborted
        return original(db, contest_id, round_id)

    monkeypatch.setattr(SeasonMigrationService, "migrate_to_city_season", staticmethod(failing))
    warm_pool(engine)
    out = run_pass(Session_, clock, datetime(2026, 9, 1, 0, 30))
    assert [e[0] for e in errors_of(out)] == [first]
    db = Session_()
    rnd = db.get(Round, rid)
    cts = {c.id: c for c in db.query(Contest).filter(Contest.id.in_([first, second, third]))}
    assert active_count(db, rnd, SeasonLevel.CITY, cts[second]) == 6
    assert active_count(db, rnd, SeasonLevel.CITY, cts[third]) == 6
    assert active_count(db, rnd, SeasonLevel.CITY, cts[first]) == 0
    db.close()

    monkeypatch.setattr(SeasonMigrationService, "migrate_to_city_season", staticmethod(original))
    run_pass(Session_, clock, datetime(2026, 9, 1, 1, 30))           # retry on the next pass
    db = Session_()
    assert active_count(db, db.get(Round, rid), SeasonLevel.CITY, db.get(Contest, first)) == 6
    db.close()
    assert advisory_locks(observer) == []
