"""Month-end progression hardening: stage voting boundaries, personal-origin
progression beyond Country, origin preservation, idempotency and STEP 1
recovery. Every user, entry, vote and round here is SYNTHETIC (SQLite).

PostgreSQL advisory-lock behaviour cannot be proven on SQLite; it is covered by
tests/integration/test_month_end_locking_postgres.py (opt-in).

Boundary semantics (UTC, the application's authoritative clock): a stage whose
end date is 2026-09-30 is votable through 2026-09-30 23:59:59 and closed from
2026-10-01 00:00:00, whether or not the promotion pass has run yet.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

import app.services.season_migration as sm
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.voting import ContestantVoting
from app.services.contest_status import contest_status_service
from app.services.season_migration import SeasonMigrationService
from tests.unit.test_phase5_contest_eligibility import contest, person
from tests.unit.test_phase8_participation_safety import make_round, post_vote, season

LEVELS = [SeasonLevel.CITY, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _corrected_finalization_rule_already_active(monkeypatch):
    """These scenarios use synthetic cohorts dated before 2026-10-02. They model
    stages that close while the corrected GLOBAL finalization rule is in force,
    so the rule's activation date is moved before them. The guard for stages
    that closed under the previous rule is covered by
    test_global_finalization_historical_guard.py."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "GLOBAL_FINALIZATION_ACTIVE_FROM", "2000-01-01", raising=False)


@pytest.fixture(autouse=True)
def _quiet_scheduler_prints(monkeypatch):
    """The migration service prints progress lines containing non-ASCII marks;
    a Windows cp1252 console/capture cannot encode them. Output is irrelevant here."""
    import builtins

    monkeypatch.setattr(builtins, "print", lambda *a, **k: None)


@pytest.fixture
def clock(monkeypatch):
    """Freeze the scheduler's date and the vote-window clock (UTC)."""
    state = {"now": datetime(2026, 1, 1)}

    class FrozenDate(date):
        @classmethod
        def today(cls):
            n = state["now"]
            return date(n.year, n.month, n.day)

    monkeypatch.setattr(sm, "date", FrozenDate)
    monkeypatch.setattr(contest_status_service, "_utc_now", lambda: state["now"])

    def set_now(dt: datetime) -> None:
        state["now"] = dt

    return set_now


def wide_round(db, submission_month: date) -> Round:
    """Participation stage columns + a multi-month round voting window, i.e. the
    exact situation in which the old code reopened a closed stage."""
    rnd = make_round(db, submission_month)
    rnd.name = f"Round {submission_month:%B %Y}"
    rnd.voting_start_date = SeasonMigrationService._add_months(submission_month, 1)
    rnd.voting_end_date = SeasonMigrationService._add_months(submission_month, 6) - timedelta(days=1)
    db.commit()
    return rnd


def entry(db, ct, rnd, *, k: int, origin: str, city="Arusha", country="Tanzania", when=None):
    user = person(db, 30, country=country)
    when = when or datetime.combine(rnd.submission_start_date, datetime.min.time()) + timedelta(days=9)
    c = Contestant(user_id=user.id, season_id=ct.id, contest_id=ct.id, round_id=rnd.id,
                   title=f"{origin[:1].upper()}{ct.id}-k{k}", description="d", entry_type=origin,
                   city=city, country=country, region="East Africa", continent="Africa",
                   is_active=True, is_deleted=False, is_qualified=True,
                   registration_date=when, created_at=when)
    db.add(c)
    db.commit()
    return c


def add_votes(db, c, s, ct, n: int, when: datetime):
    for _ in range(n):
        voter = person(db, 30)
        db.add(ContestantVoting(user_id=voter.id, contestant_id=c.id, contest_id=ct.id, season_id=s.id,
                                vote_bucket_key=SeasonMigrationService._top_high5_bucket_key_for_contest(ct),
                                vote_date=when, position=1, points=1))
    db.commit()


def run_pass(db, clock, when: datetime):
    clock(when)
    out = SeasonMigrationService.check_and_process_migrations(db, allow_multi_hop=True)
    db.commit()
    db.expire_all()
    return out


def season_for(db, rnd, level):
    return (db.query(ContestSeason)
            .filter(ContestSeason.round_id == rnd.id, ContestSeason.level == level,
                    ContestSeason.is_deleted == False)  # noqa: E712
            .order_by(ContestSeason.id).first())


def active_at(db, rnd, level, ct) -> set:
    s = season_for(db, rnd, level)
    if s is None:
        return set()
    rows = (db.query(Contestant.title)
            .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
            .filter(ContestantSeason.season_id == s.id, ContestantSeason.is_active == True,  # noqa: E712
                    Contestant.contest_id == ct.id)
            .all())
    return {r[0] for r in rows}


def state(db):
    return (
        sorted((m.contestant_id, m.season_id, m.is_active) for m in db.query(ContestantSeason).all()),
        sorted((l.contest_id, l.season_id, l.is_active) for l in db.query(ContestSeasonLink).all()),
        sorted((t.contest_id, str(t.level), t.jurisdiction, t.round_id, t.rank, t.contestant_id)
               for t in db.query(TopHigh5Result).all()),
        sorted((c.id, c.entry_type) for c in db.query(Contestant).all()),
        db.query(ContestantVoting).count(),
    )


# ---------------------------------------------------------------------------
# 1. Strict stage voting window (participation)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("when,expected", [
    (datetime(2026, 9, 30, 0, 0, 0), True),
    (datetime(2026, 9, 30, 12, 0, 0), True),
    (datetime(2026, 9, 30, 23, 59, 59), True),
    (datetime(2026, 10, 1, 0, 0, 0), False),
    (datetime(2026, 10, 1, 0, 0, 30), False),
    (datetime(2026, 10, 1, 0, 50, 0), False),   # progression delayed to 00:50: still closed
])
def test_participation_stage_closes_at_end_of_last_day(db, when, expected):
    rnd = wide_round(db, date(2026, 8, 1))           # City = September 2026
    assert rnd.city_season_end_date == date(2026, 9, 30)
    assert contest_status_service.round_voting_open_at(rnd, when) is True   # round window still open
    is_open, _ = contest_status_service.season_stage_voting_status(rnd, "city", when)
    assert is_open is expected


def test_not_yet_started_stage_keeps_round_window_fallback(db):
    """Narrow fix: only an ENDED stage is closed; the pre-start fallback is unchanged."""
    rnd = wide_round(db, date(2026, 8, 1))           # Country stage starts 2026-10-01
    is_open, _ = contest_status_service.season_stage_voting_status(rnd, "country", datetime(2026, 9, 15))
    assert is_open is True


# ---------------------------------------------------------------------------
# 2. Strict stage voting window (nomination calendar)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("when,expected", [
    (datetime(2026, 9, 1, 0, 0, 0), True),
    (datetime(2026, 9, 30, 23, 59, 59), True),
    (datetime(2026, 10, 1, 0, 0, 0), False),
    (datetime(2026, 10, 1, 0, 0, 30), False),
    (datetime(2026, 10, 1, 0, 50, 0), False),
])
def test_nomination_country_vote_follows_nomination_calendar(db, when, expected):
    from app.api.api_v1.endpoints.contestant import _nomination_stage_voting_allowed

    rnd = wide_round(db, date(2026, 8, 1))           # August nominations: Country vote = September
    # The participation columns say Country is OPEN in October (M+2); nominations must not follow them.
    assert contest_status_service.season_stage_voting_status(rnd, "country", datetime(2026, 10, 1, 0, 0, 30))[0] is True
    assert _nomination_stage_voting_allowed(rnd, "country", when) is expected


def test_nomination_closed_message_names_the_end_date(db):
    from app.api.api_v1.endpoints.contestant import _nomination_stage_voting_message

    rnd = wide_round(db, date(2026, 8, 1))
    msg = _nomination_stage_voting_message(rnd, "country", datetime(2026, 10, 1, 0, 0, 30))
    assert "ended on 2026-09-30" in msg


# ---------------------------------------------------------------------------
# 3. Real vote endpoint + reorder: post-close votes rejected, progression delayed
# ---------------------------------------------------------------------------

def _global_scope(db):
    """Participation entry at GLOBAL (no location restriction) whose stage ends 2026-09-30."""
    rnd = wide_round(db, date(2026, 4, 1))           # Global = September 2026
    rnd.voting_end_date = date(2027, 1, 31)           # round window still open in October
    db.commit()
    assert rnd.global_end_date == date(2026, 9, 30)
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    s = season(db, rnd, ct, SeasonLevel.GLOBAL)
    c = entry(db, ct, rnd, k=1, origin="participation")
    db.add(ContestantSeason(contestant_id=c.id, season_id=s.id, is_active=True, joined_at=datetime(2026, 9, 1)))
    db.commit()
    return rnd, ct, s, c


@pytest.mark.parametrize("when,status_code", [
    (datetime(2026, 9, 30, 23, 59, 59), 201),
    (datetime(2026, 10, 1, 0, 0, 0), 400),
    (datetime(2026, 10, 1, 0, 0, 30), 400),
    (datetime(2026, 10, 1, 0, 50, 0), 400),
])
def test_vote_endpoint_rejects_votes_after_stage_close(client, db, clock, when, status_code):
    _, ct, s, c = _global_scope(db)
    clock(when)
    r = post_vote(client, person(db, 30), c, ct)
    assert r.status_code == status_code, r.text
    stored = db.query(ContestantVoting).filter(ContestantVoting.season_id == s.id).count()
    assert stored == (1 if status_code == 201 else 0)
    if status_code == 400:
        assert "ended on 2026-09-30" in r.json().get("detail", r.json().get("message", ""))


def test_reorder_refused_after_stage_close(db, clock):
    from app.api.api_v1.endpoints.contestant import _closed_stage_reason_for_season

    _, ct, s, _ = _global_scope(db)
    assert _closed_stage_reason_for_season(db, s.id, ct, datetime(2026, 9, 30, 23, 59, 59)) is None
    assert "ended on 2026-09-30" in _closed_stage_reason_for_season(db, s.id, ct, datetime(2026, 10, 1, 0, 0, 30))


def test_reorder_endpoint_refused_after_stage_close(client, db, clock):
    from tests.unit.test_age_gate_registration import auth

    _, ct, s, c = _global_scope(db)
    voter = person(db, 30)
    clock(datetime(2026, 9, 30, 20, 0))
    assert post_vote(client, voter, c, ct).status_code == 201
    before = [(v.position, v.points) for v in db.query(ContestantVoting).all()]
    clock(datetime(2026, 10, 1, 0, 0, 30))
    r = client.put("/api/v1/contestants/user/my-votes/reorder", headers=auth(voter),
                   json={"season_id": s.id, "contest_id": ct.id, "votes": [{"contestant_id": c.id, "position": 1}]})
    assert r.status_code == 400, r.text
    db.expire_all()
    assert [(v.position, v.points) for v in db.query(ContestantVoting).all()] == before


# ---------------------------------------------------------------------------
# 4. Top High5 boundary: Sep-30 final-day vote counts, Oct-1 vote cannot
# ---------------------------------------------------------------------------

def test_final_day_vote_lifts_rank6_into_top5_and_post_close_vote_cannot(client, db, clock):
    rnd = wide_round(db, date(2026, 8, 1))            # City = September 2026
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    entries = [entry(db, ct, rnd, k=k, origin="participation") for k in (1, 2, 3, 4, 5, 6)]
    run_pass(db, clock, datetime(2026, 9, 1, 0, 30))  # City init
    city = season_for(db, rnd, SeasonLevel.CITY)
    for c, pts in zip(entries, (60, 50, 40, 30, 20, 10)):
        add_votes(db, c, city, ct, pts, datetime(2026, 9, 15, 12))
    sixth, fifth = entries[5], entries[4]

    # Valid final-second vote: #6 (10) overtakes #5 (20).
    clock(datetime(2026, 9, 30, 23, 59, 59))
    assert contest_status_service.season_stage_voting_status(rnd, "city", datetime(2026, 9, 30, 23, 59, 59))[0] is True
    add_votes(db, sixth, city, ct, 15, datetime(2026, 9, 30, 23, 59, 59))
    run_pass(db, clock, datetime(2026, 9, 30, 23, 59, 59))
    assert active_at(db, rnd, SeasonLevel.COUNTRY, ct) == set()          # still a voting day

    # Oct 1 00:00:30, BEFORE the (delayed) promotion pass: a vote for the old #5 is refused.
    clock(datetime(2026, 10, 1, 0, 0, 30))
    assert contest_status_service.season_stage_voting_status(rnd, "city", datetime(2026, 10, 1, 0, 0, 30))[0] is False

    run_pass(db, clock, datetime(2026, 10, 1, 0, 50))
    promoted = active_at(db, rnd, SeasonLevel.COUNTRY, ct)
    assert sixth.title in promoted and fifth.title not in promoted
    assert promoted == {e.title for e in entries if e is not fifth}
    frozen = (db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id,
                                              TopHigh5Result.level == SeasonLevel.CITY)
              .order_by(TopHigh5Result.rank).all())
    assert [t.contestant_id for t in frozen] == [entries[i].id for i in (0, 1, 2, 3, 5)]
    assert frozen[4].total_points == 25


# ---------------------------------------------------------------------------
# 5. Full lifecycles: personal to Global, nomination on its own calendar, no mixing
# ---------------------------------------------------------------------------

# Month-by-month voting level for a May-2026 cohort.
PERSONAL_VOTE_LEVEL = {6: SeasonLevel.CITY, 7: SeasonLevel.COUNTRY, 8: SeasonLevel.REGIONAL,
                       9: SeasonLevel.CONTINENT, 10: SeasonLevel.GLOBAL}
NOMINATION_VOTE_LEVEL = {6: SeasonLevel.COUNTRY, 7: SeasonLevel.REGIONAL, 8: SeasonLevel.CONTINENT,
                         9: SeasonLevel.GLOBAL}


def _vote_month(db, rnd, ct, level, month):
    s = season_for(db, rnd, level)
    members = (db.query(Contestant)
               .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
               .filter(ContestantSeason.season_id == s.id, ContestantSeason.is_active == True,  # noqa: E712
                       Contestant.contest_id == ct.id).all())
    for c in members:
        add_votes(db, c, s, ct, int(c.title.rsplit("-k", 1)[1]), datetime(2026, month, 15, 12))


def test_personal_and_nomination_full_lifecycles_share_rounds_without_mixing(db, clock):
    rnd = wide_round(db, date(2026, 5, 1))
    personal = contest(db)                        # participation mode
    nomination = contest(db, mode="nomination")
    for ct in (personal, nomination):
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    p_entries = [entry(db, personal, rnd, k=k, origin="participation") for k in range(1, 8)]
    n_entries = [entry(db, nomination, rnd, k=k, origin="nomination") for k in range(1, 8)]
    top5 = lambda es: {e.title for e in es if int(e.title.rsplit("-k", 1)[1]) >= 3}  # noqa: E731

    # Submission / nomination month (May): nothing is active yet.
    run_pass(db, clock, datetime(2026, 5, 31, 23, 59, 59))
    assert all(not active_at(db, rnd, lvl, ct) for lvl in LEVELS for ct in (personal, nomination))

    expected_personal = {6: SeasonLevel.CITY, 7: SeasonLevel.COUNTRY, 8: SeasonLevel.REGIONAL,
                         9: SeasonLevel.CONTINENT, 10: SeasonLevel.GLOBAL}
    for month in range(6, 11):
        run_pass(db, clock, datetime(2026, month, 1, 0, 0))
        # Personal: exactly the calendar level for this month (M+1 City ... M+5 Global).
        lvl = expected_personal[month]
        want = {e.title for e in p_entries} if lvl == SeasonLevel.CITY else top5(p_entries)
        assert active_at(db, rnd, lvl, personal) == want, (month, lvl)
        if month in NOMINATION_VOTE_LEVEL:
            n_lvl = NOMINATION_VOTE_LEVEL[month]
            n_want = {e.title for e in n_entries} if n_lvl == SeasonLevel.COUNTRY else top5(n_entries)
            assert active_at(db, rnd, n_lvl, nomination) == n_want, (month, n_lvl)

        _vote_month(db, rnd, personal, PERSONAL_VOTE_LEVEL[month], month)
        if month in NOMINATION_VOTE_LEVEL:
            _vote_month(db, rnd, nomination, NOMINATION_VOTE_LEVEL[month], month)

        # Last voting day: nobody moves to the next level yet.
        last = SeasonMigrationService._add_months(date(2026, month, 1), 1) - timedelta(days=1)
        before = state(db)
        run_pass(db, clock, datetime(last.year, last.month, last.day, 23, 59, 59))
        assert state(db) == before, f"progressed on the last voting day {last}"

    # Global results: nomination finalises Oct 1 (after Sep), personal Nov 1 (after Oct).
    def frozen_global(ct):
        return db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id,
                                               TopHigh5Result.level == SeasonLevel.GLOBAL).count()
    assert frozen_global(nomination) == 5 and frozen_global(personal) == 0
    run_pass(db, clock, datetime(2026, 11, 1, 0, 0))
    assert frozen_global(personal) == 5

    # No mixing, provenance intact, one frozen group per contest.
    for ct, origin, es in ((personal, "participation", p_entries), (nomination, "nomination", n_entries)):
        ids = {e.id for e in es}
        for lvl in LEVELS:
            assert {t for t in active_at(db, rnd, lvl, ct)} <= {e.title for e in es}
        rows = db.query(TopHigh5Result).filter(TopHigh5Result.contest_id == ct.id).all()
        assert rows and all(r.contestant_id in ids for r in rows)
        assert {c.entry_type for c in db.query(Contestant).filter(Contestant.contest_id == ct.id)} == {origin}

    # Idempotency: 1 / 2 / 5 further runs change nothing.
    final = state(db)
    for n in (1, 2, 5):
        for _ in range(n):
            run_pass(db, clock, datetime(2026, 11, 1, 0, 5))
        assert state(db) == final


def test_nomination_entry_in_personal_contest_never_rides_personal_calendar(db, clock):
    rnd = wide_round(db, date(2026, 8, 1))
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    ok = entry(db, ct, rnd, k=1, origin="participation")
    stray = entry(db, ct, rnd, k=2, origin="nomination")
    run_pass(db, clock, datetime(2026, 9, 1, 0, 30))
    assert active_at(db, rnd, SeasonLevel.CITY, ct) == {ok.title}
    assert stray.entry_type == "nomination"


# ---------------------------------------------------------------------------
# 6. Safety hold, votes not copied, unique (entry, stage)
# ---------------------------------------------------------------------------

def test_hold_keeps_slot_and_votes_are_not_copied(db, clock):
    rnd = wide_round(db, date(2026, 8, 1))
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    entries = [entry(db, ct, rnd, k=k, origin="participation") for k in (1, 2, 3, 4, 5, 6)]
    run_pass(db, clock, datetime(2026, 9, 1, 0, 30))
    city = season_for(db, rnd, SeasonLevel.CITY)
    for c, pts in zip(entries, (60, 50, 40, 30, 20, 10)):
        add_votes(db, c, city, ct, pts, datetime(2026, 9, 15))
    leader = entries[0]
    db.add(ContestEntrySafety(created_at=datetime(2026, 9, 20), updated_at=datetime(2026, 9, 20),
                              contestant_id=leader.id, contest_id=ct.id, entry_kind="PERSONAL_SUBMISSION",
                              exposure_status="HELD", outcome="HOLD", reason_codes=["SYNTHETIC_HOLD"],
                              last_evaluated_at=datetime(2026, 9, 20), activated_at=datetime(2026, 9, 2),
                              enforced=True))
    leader.is_active = False
    db.commit()
    votes_before = db.query(ContestantVoting).count()

    run_pass(db, clock, datetime(2026, 10, 1, 0, 50))
    promoted = active_at(db, rnd, SeasonLevel.COUNTRY, ct)
    assert leader.title not in promoted and entries[5].title not in promoted and len(promoted) == 4
    assert db.query(ContestantVoting).count() == votes_before
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    assert db.query(ContestantVoting).filter(ContestantVoting.season_id == country.id).count() == 0

    member = db.query(ContestantSeason).filter(ContestantSeason.season_id == country.id).first()
    db.add(ContestantSeason(contestant_id=member.contestant_id, season_id=country.id, is_active=True,
                            joined_at=datetime(2026, 10, 1)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# 7. STEP 1 failure recovery: one failing contest does not abort the pass
# ---------------------------------------------------------------------------

def test_step1_failure_rolls_back_and_the_pass_continues(db, clock, monkeypatch):
    rnd = wide_round(db, date(2026, 8, 1))
    first, second = contest(db), contest(db)
    for ct in (first, second):
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    a = entry(db, first, rnd, k=1, origin="participation")
    b = entry(db, second, rnd, k=1, origin="participation")

    original = SeasonMigrationService.migrate_to_city_season
    rollbacks = []
    real_rollback = db.rollback

    def failing(session, contest_id, round_id):
        if contest_id == first.id:
            raise RuntimeError("synthetic DB failure")
        return original(session, contest_id, round_id)

    def counting_rollback():
        rollbacks.append(1)
        return real_rollback()

    monkeypatch.setattr(SeasonMigrationService, "migrate_to_city_season", staticmethod(failing))
    monkeypatch.setattr(db, "rollback", counting_rollback)
    out = run_pass(db, clock, datetime(2026, 9, 1, 0, 30))
    errors = [r for r in out["results"] if (r.get("result") or {}).get("error")]
    assert [r["contest_id"] for r in errors] == [first.id]
    assert rollbacks, "a failed STEP 1 contest must roll the session back"
    assert active_at(db, rnd, SeasonLevel.CITY, second) == {b.title}
    assert active_at(db, rnd, SeasonLevel.CITY, first) == set()

    monkeypatch.setattr(SeasonMigrationService, "migrate_to_city_season", staticmethod(original))
    run_pass(db, clock, datetime(2026, 9, 1, 1, 30))   # retry on the next pass
    assert active_at(db, rnd, SeasonLevel.CITY, first) == {a.title}
