"""The automatic scheduler never freezes a GLOBAL Top High5 retroactively.

The corrected finalization rule (no vote required, cumulative ranking) took
effect on 2026-10-02. A GLOBAL stage whose own voting closed before that date
was closed, and left unfrozen, under the previous rule: the automatic pass
leaves it alone. Stages that close on or after that date finalize normally.
An explicit, server-internal call can still finalize a historical stage.

The distinction is each stage's own closing date, never a round or contest id.
Production shape this protects against (read-only audit, 2026-10-02): 216 rows
for 101 contests in three old rounds would have been frozen by the first pass.
Synthetic data only (SQLite). This module deliberately uses the REAL activation
date (no override fixture).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.core.config import settings
from app.models.contests import ContestSeason, SeasonLevel, TopHigh5Result
from app.models.round import round_contests
from app.services.progression_dry_run import pending_global_finalizations, simulate_due_progressions
from app.services.season_migration import SeasonMigrationService
from tests.unit.test_cumulative_ranking_progression import (
    active_ids,
    memberships,
    nominees,
    share,
    submitted,
)
from tests.unit.test_month_end_progression_hardening import (  # noqa: F401  (fixtures)
    _quiet_scheduler_prints,
    clock,
    run_pass,
    season_for,
    state,
    wide_round,
)
from tests.unit.test_phase5_contest_eligibility import contest
from tests.unit.test_phase8_participation_safety import votes

ACTIVE_FROM = date(2026, 10, 2)


def global_rows(db, ct=None):
    q = db.query(TopHigh5Result).filter(TopHigh5Result.level == SeasonLevel.GLOBAL)
    if ct is not None:
        q = q.filter(TopHigh5Result.contest_id == ct.id)
    return q.order_by(TopHigh5Result.contest_id, TopHigh5Result.rank).all()


def cohort_at_global(db, clock, month: date, *, mode="nomination", n=6, contests=1):
    """Run one cohort through the real scheduler until it sits at GLOBAL.
    Returns (round, [contest...], {contest id: entries})."""
    rnd = wide_round(db, month)
    cts, entries = [], {}
    for _ in range(contests):
        ct = contest(db, mode=mode)
        ct.contest_type = f"type-{ct.id}"            # one contest per category and mode
        db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
        db.commit()
        cts.append(ct)
        entries[ct.id] = nominees(db, ct, rnd, n, origin=mode if mode == "nomination" else "participation")
        for i, c in enumerate(entries[ct.id]):
            c.registration_date = c.created_at = datetime(month.year, month.month, 1 + i, 12)
        db.commit()
    hops = 4 if mode == "nomination" else 5      # nomination: Country..Global; participation: City..Global
    for k in range(1, hops + 1):
        when = SeasonMigrationService._add_months(month, k)
        run_pass(db, clock, datetime(when.year, when.month, 1, 0, 30))
    for ct in cts:
        assert active_ids(db, rnd, SeasonLevel.GLOBAL, ct) == {c.id for c in entries[ct.id][:5]}
    return rnd, cts, entries


def global_close(month: date, mode="nomination") -> date:
    offset = 4 if mode == "nomination" else 5
    return SeasonMigrationService._add_months(month, offset + 1).replace(day=1)   # first day AFTER the stage


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

def test_activation_date_is_the_rule_date_and_not_tied_to_any_round_or_contest():
    assert SeasonMigrationService.GLOBAL_FINALIZATION_RULE_ACTIVE_FROM == ACTIVE_FROM
    assert SeasonMigrationService.global_finalization_active_from() == ACTIVE_FROM
    import inspect

    source = inspect.getsource(SeasonMigrationService.global_stage_is_historical) + inspect.getsource(
        SeasonMigrationService._finalize_global_top_high5
    )
    assert "round_obj.id" not in source and "contest.id in" not in source and "round_id in" not in source


@pytest.mark.parametrize("month,mode,historical", [
    (date(2026, 3, 1), "nomination", True),      # Global July 2026
    (date(2026, 5, 1), "nomination", True),      # Global September 2026, closed 30 Sep
    (date(2026, 6, 1), "nomination", False),     # Global October 2026, closes 31 Oct
    (date(2026, 9, 1), "nomination", False),
    (date(2026, 4, 1), "participation", True),   # Global September 2026
    (date(2026, 5, 1), "participation", False),  # Global October 2026
])
def test_stage_is_historical_by_its_own_closing_date(db, month, mode, historical):
    rnd = wide_round(db, month)
    assert SeasonMigrationService.global_stage_is_historical(rnd, mode) is historical


def test_a_stage_closing_exactly_on_the_activation_date_is_not_historical(db, monkeypatch):
    rnd = wide_round(db, date(2026, 5, 1))                      # nomination Global closes 2026-09-30
    monkeypatch.setattr(settings, "GLOBAL_FINALIZATION_ACTIVE_FROM", "2026-09-30", raising=False)
    assert SeasonMigrationService.global_stage_is_historical(rnd, "nomination") is False
    monkeypatch.setattr(settings, "GLOBAL_FINALIZATION_ACTIVE_FROM", "2026-10-01", raising=False)
    assert SeasonMigrationService.global_stage_is_historical(rnd, "nomination") is True


def test_malformed_override_never_widens_what_is_frozen(db, monkeypatch):
    monkeypatch.setattr(settings, "GLOBAL_FINALIZATION_ACTIVE_FROM", "soon", raising=False)
    assert SeasonMigrationService.global_finalization_active_from() == ACTIVE_FROM
    rnd = wide_round(db, date(2026, 5, 1))
    assert SeasonMigrationService.global_stage_is_historical(rnd, "nomination") is True


def test_unknown_closing_date_is_never_finalized(db):
    rnd = wide_round(db, date(2026, 5, 1))
    rnd.global_end_date = None
    assert SeasonMigrationService._global_finalization_due(rnd, "participation", date(2027, 1, 1)) is False
    assert SeasonMigrationService.global_stage_is_historical(rnd, "participation") is False


# ---------------------------------------------------------------------------
# 1 / 6. Historical closed GLOBAL stages: the normal scheduler freezes nothing
# ---------------------------------------------------------------------------

def test_normal_scheduler_never_freezes_stages_that_closed_before_the_rule(db, clock):
    """Three old cohorts, several contests each: the production '216 rows' shape."""
    worlds = [
        cohort_at_global(db, clock, date(2026, 3, 1), contests=2),
        cohort_at_global(db, clock, date(2026, 4, 1), contests=2, mode="participation"),
        cohort_at_global(db, clock, date(2026, 5, 1), contests=3),
    ]
    rnd, cts, entries = worlds[2]
    global_season = season_for(db, rnd, SeasonLevel.GLOBAL)
    votes(db, entries[cts[0].id][0], cts[0], global_season, 5)      # even a voted finalist stays unfrozen
    db.commit()
    assert global_rows(db) == []
    before, before_members = state(db), memberships(db)

    # First passes after "deployment", then hourly, then later months.
    for when in (datetime(2026, 10, 2, 17, 0), datetime(2026, 10, 2, 18, 0), datetime(2026, 11, 1, 0, 30),
                 datetime(2027, 1, 1, 0, 30)):
        out = run_pass(db, clock, when)
        assert [r for r in out["results"] if r.get("action") == "finalize_global_top_high5"] == []
    assert global_rows(db) == []
    assert state(db) == before and memberships(db) == before_members
    assert pending_global_finalizations(db, today=date(2026, 10, 2)) == []


def test_monthly_multi_pass_ops_do_not_freeze_historical_stages_either(db, clock):
    from app.services.monthly_calendar_ops import run_season_migrations

    cohort_at_global(db, clock, date(2026, 5, 1), contests=2)
    clock(datetime(2026, 11, 1, 0, 5))
    run_season_migrations(db, today=date(2026, 11, 1))
    db.commit()
    assert global_rows(db) == []


# ---------------------------------------------------------------------------
# 2 / 3 / 4 / 8 / 9. Current and future stages finalize normally
# ---------------------------------------------------------------------------

def test_current_stage_finalizes_when_due_with_the_canonical_ranking(db, clock):
    month = date(2026, 6, 1)                                         # nomination Global = October 2026
    rnd, (ct,), entries = cohort_at_global(db, clock, month)
    e = entries[ct.id][:5]
    country = season_for(db, rnd, SeasonLevel.COUNTRY)
    global_season = season_for(db, rnd, SeasonLevel.GLOBAL)
    votes(db, e[3], ct, country, 9)                                  # carried from Country
    votes(db, e[4], ct, global_season, 9)                            # earned at Global: equal cumulative
    share(db, e[4], datetime(2026, 10, 10))                          # ... separated by shares
    db.commit()

    # 3. Not due yet: voting runs through 31 October.
    for when in (datetime(2026, 10, 2, 17, 0), datetime(2026, 10, 31, 23, 59, 59)):
        run_pass(db, clock, when)
        assert global_rows(db) == []
    assert pending_global_finalizations(db, today=date(2026, 10, 31)) == []
    (preview,) = pending_global_finalizations(db, today=date(2026, 11, 1))
    assert preview["historical"] is False

    # 2 / 8. Due on 1 November: cumulative points, then shares, ..., then earlier submission.
    run_pass(db, clock, datetime(2026, 11, 1, 0, 30))
    frozen = global_rows(db, ct)
    assert [r.contestant_id for r in frozen] == [e[4].id, e[3].id, e[0].id, e[1].id, e[2].id]
    assert [(r.rank, r.total_points, r.shares) for r in frozen] == [
        (1, 9, 1), (2, 9, 0), (3, 0, 0), (4, 0, 0), (5, 0, 0)]
    assert [row["contestant_id"] for row in preview["would_freeze"]] == [r.contestant_id for r in frozen]

    # 4. Idempotent: further passes neither add nor rewrite rows.
    ids = [(r.id, r.rank, r.contestant_id, r.total_points) for r in frozen]
    for hour in (1, 2, 3):
        run_pass(db, clock, datetime(2026, 11, 1, hour, 30))
    assert [(r.id, r.rank, r.contestant_id, r.total_points) for r in global_rows(db, ct)] == ids


def test_current_zero_vote_stage_still_finalizes(db, clock):
    rnd, (ct,), entries = cohort_at_global(db, clock, date(2026, 6, 1))
    run_pass(db, clock, datetime(2026, 11, 1, 0, 30))
    assert [r.contestant_id for r in global_rows(db, ct)] == [c.id for c in entries[ct.id][:5]]


def test_current_participation_stage_finalizes_on_its_own_calendar(db, clock):
    rnd, (ct,), entries = cohort_at_global(db, clock, date(2026, 5, 1), mode="participation")   # Global = October
    run_pass(db, clock, datetime(2026, 10, 31, 12, 0))
    assert global_rows(db) == []
    run_pass(db, clock, datetime(2026, 11, 1, 0, 30))
    assert len(global_rows(db, ct)) == 5


def test_old_and_current_cohorts_side_by_side(db, clock):
    _, (old_ct,), _ = cohort_at_global(db, clock, date(2026, 5, 1))
    _, (new_ct,), _ = cohort_at_global(db, clock, date(2026, 6, 1))
    run_pass(db, clock, datetime(2026, 11, 1, 0, 30))
    assert global_rows(db, old_ct) == []
    assert len(global_rows(db, new_ct)) == 5


# ---------------------------------------------------------------------------
# 5. Explicit, authorized historical finalization still works
# ---------------------------------------------------------------------------

def test_explicit_internal_call_can_finalize_a_historical_stage(db, clock):
    rnd, (ct,), entries = cohort_at_global(db, clock, date(2026, 5, 1))
    global_season = season_for(db, rnd, SeasonLevel.GLOBAL)
    today = date(2026, 10, 2)

    assert pending_global_finalizations(db, today=today) == []
    (listed,) = pending_global_finalizations(db, today=today, include_historical=True)
    assert listed["historical"] is True and listed["stage_closed_on"] == "2026-09-30"
    assert global_rows(db) == []                                    # listing wrote nothing

    # Default (what the scheduler passes) does nothing ...
    assert SeasonMigrationService._finalize_global_top_high5(db, global_season, rnd, today) == []
    db.commit()
    assert global_rows(db) == []
    # ... the explicit internal flag finalizes, once.
    out = SeasonMigrationService._finalize_global_top_high5(db, global_season, rnd, today, include_historical=True)
    db.commit()
    assert [o["result"]["frozen_count"] for o in out] == [5]
    assert [r.contestant_id for r in global_rows(db, ct)] == [c.id for c in entries[ct.id][:5]]
    assert [row["contestant_id"] for row in listed["would_freeze"]] == [r.contestant_id for r in global_rows(db, ct)]
    assert SeasonMigrationService._finalize_global_top_high5(
        db, global_season, rnd, today, include_historical=True) == []
    assert len(global_rows(db, ct)) == 5


def test_no_api_route_exposes_the_historical_flag(app):
    for route in app.routes:
        names = {p.name for p in getattr(getattr(route, "dependant", None), "query_params", [])} | {
            p.name for p in getattr(getattr(route, "dependant", None), "body_params", [])}
        assert "include_historical" not in names, getattr(route, "path", route)


# ---------------------------------------------------------------------------
# 7 / 10. Controlled promotion of a historical cohort is not affected
# ---------------------------------------------------------------------------

def test_controlled_continental_to_global_promotion_still_works_for_an_old_cohort(db, clock):
    """The reviewed June recovery shape: entries left at Continental are promoted
    by an explicit promote_to_next_level call; the guard is not in that path."""
    month = date(2026, 5, 1)
    rnd = wide_round(db, month)
    ct = contest(db, mode="nomination")
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    e = nominees(db, ct, rnd, 3)
    for when in (datetime(2026, 6, 1, 0, 30), datetime(2026, 7, 1, 0, 30), datetime(2026, 8, 1, 0, 30)):
        run_pass(db, clock, when)                                    # ... stops at Continental
    continent = season_for(db, rnd, SeasonLevel.CONTINENT)
    assert active_ids(db, rnd, SeasonLevel.CONTINENT, ct) == {c.id for c in e}

    clock(datetime(2026, 10, 2, 17, 0))
    report = simulate_due_progressions(db, today=date(2026, 10, 2), round_ids=[rnd.id])
    assert report["totals"]["would_advance"] == 3

    out = SeasonMigrationService.promote_to_next_level(
        db, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL, ct.id, from_season_id=continent.id)
    db.commit()
    assert out["promoted_contestant_ids"] == [c.id for c in e]
    assert active_ids(db, rnd, SeasonLevel.GLOBAL, ct) == {c.id for c in e}
    # Continental Top High5 is frozen by the promotion; the Global one is not created.
    assert db.query(TopHigh5Result).filter(TopHigh5Result.level == SeasonLevel.CONTINENT,
                                           TopHigh5Result.contest_id == ct.id).count() == 3
    assert global_rows(db) == []
    for when in (datetime(2026, 10, 2, 18, 0), datetime(2026, 11, 1, 0, 30)):
        run_pass(db, clock, when)
    assert global_rows(db) == []                                     # that old Global stage closed in September
    assert db.query(ContestSeason).filter(ContestSeason.round_id == rnd.id,
                                          ContestSeason.level == SeasonLevel.GLOBAL).count() == 1


def test_guard_does_not_change_which_promotions_are_due(db, clock):
    """Country->Regional / Regional->Continental for old cohorts are untouched by the guard."""
    month = date(2026, 5, 1)
    rnd = wide_round(db, month)
    ct = contest(db, mode="nomination")
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()
    e = nominees(db, ct, rnd, 7)
    run_pass(db, clock, datetime(2026, 6, 1, 0, 30))
    report = simulate_due_progressions(db, today=date(2026, 10, 2), round_ids=[rnd.id])
    (hop,) = report["transitions"]
    assert (hop["source_stage"], hop["destination_stage"], report["totals"]["would_advance"]) == (
        "country", "regional", 5)
    assert {r["contestant_id"] for r in hop["entries"] if r["outcome"] == "ADVANCES"} == {c.id for c in e[:5]}
    assert submitted(1) < submitted(2)
