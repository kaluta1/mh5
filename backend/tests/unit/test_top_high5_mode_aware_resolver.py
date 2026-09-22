"""
Tests for the 2026 mode-aware Top High5 round resolver fix.

Confirmed production bug (read-only audit, 2026-09-22): get_top_high5_by_country
selected the single "latest round" for COUNTRY/REGIONAL/CONTINENTAL using
participation's shared Round.<level>_end_date columns. Nomination contests
close each level one month earlier under their own, independent calendar
(SeasonMigrationService._nomination_vote_close_date_for_level) -- so real,
already-frozen nomination results were hidden for up to a month, and the
endpoint fell back to a stale, older cohort instead.

This file exercises app.api.api_v1.endpoints.season_migration's new
_get_top_high5_mode_aware path (and its two helpers, _level_close_date_for_mode
/ _level_result_eligible) directly, with hand-built TopHigh5Result rows --
bypassing the scheduler/freeze machinery entirely (already covered by
test_top_high5_frozen_results.py), since only the round-SELECTION logic
changed here, not what gets frozen or when.
"""
from __future__ import annotations

from datetime import date

from app.api.api_v1.endpoints.season_migration import (
    _get_top_high5_mode_aware,
    _get_top_high5_single_round,
    _level_close_date_for_mode,
    _level_result_eligible,
)
from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    Contestant,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.user import User
from app.services.season_migration import SeasonMigrationService


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_end(d: date) -> date:
    import calendar as _calendar

    last_day = _calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def _round_for_month(db, suffix: str, *, submission_month_start: date) -> Round:
    """
    A Round with the FULL canonical PARTICIPATION calendar column set
    (City=M+1, Country=M+2, Regional=M+3, Continental=M+4, Global=M+5),
    matching exactly what generate_monthly_rounds.py writes for a real
    round. Nomination's own (independent, earlier) close dates are never
    stored on the Round -- they're computed on demand from
    submission_start_date by SeasonMigrationService, exactly like
    production.
    """
    add = SeasonMigrationService._add_months
    city = add(submission_month_start, 1)
    country = add(submission_month_start, 2)
    regional = add(submission_month_start, 3)
    continental = add(submission_month_start, 4)
    globl = add(submission_month_start, 5)
    rnd = Round(
        name=f"Round {submission_month_start.strftime('%B %Y')} {suffix}",
        status=RoundStatus.ACTIVE,
        submission_start_date=submission_month_start,
        submission_end_date=_month_end(submission_month_start),
        city_season_start_date=city,
        city_season_end_date=_month_end(city),
        country_season_start_date=country,
        country_season_end_date=_month_end(country),
        regional_start_date=regional,
        regional_end_date=_month_end(regional),
        continental_start_date=continental,
        continental_end_date=_month_end(continental),
        global_start_date=globl,
        global_end_date=_month_end(globl),
    )
    db.add(rnd)
    db.flush()
    return rnd


def _contest(db, suffix: str, *, mode: str) -> Contest:
    contest = Contest(name=f"Contest {suffix}", contest_type="t", contest_mode=mode, level="country")
    db.add(contest)
    db.flush()
    return contest


def _season(db, rnd: Round, *, level: SeasonLevel, suffix: str) -> ContestSeason:
    season = ContestSeason(round_id=rnd.id, title=f"Season {suffix}", level=level)
    db.add(season)
    db.flush()
    return season


def _contestant(db, *, suffix: str, rnd: Round, contest: Contest, country: str, region: str = "") -> Contestant:
    owner = User(email=f"th5resolver-{suffix}@example.test", hashed_password="unused")
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
        entry_type=("nomination" if contest.contest_mode == "nomination" else "participation"),
        title=f"Contestant {suffix}",
        country=country,
        region=region,
        continent="Africa",
    )
    db.add(c)
    db.flush()
    return c


def _freeze_row(
    db, *, contestant: Contestant, contest: Contest, rnd: Round, season: ContestSeason,
    level: SeasonLevel, jurisdiction: str, rank: int, votes: int = 5, points: int = 10,
) -> TopHigh5Result:
    row = TopHigh5Result(
        contestant_id=contestant.id,
        contest_id=contest.id,
        level=level,
        jurisdiction=jurisdiction,
        round_id=rnd.id,
        from_season_id=season.id,
        rank=rank,
        total_points=points,
        total_votes=votes,
        migrated=(rank <= 5),
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Phase 6: participation must not regress -- July participation Regional
# belongs to October (M+3), not September.
# ---------------------------------------------------------------------------

def test_participation_regional_not_eligible_before_its_own_close_date(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "partreg", submission_month_start=july)
    contest = _contest(db, "partreg", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="partreg")
    contestant = _contestant(db, suffix="partreg", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _freeze_row(db, contestant=contestant, contest=contest, rnd=rnd, season=season,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    db.commit()

    # September 22: July's PARTICIPATION regional_end_date is 2026-10-31 -- not yet passed.
    today = date(2026, 9, 22)
    assert _level_result_eligible(rnd, SeasonLevel.REGIONAL, "participation", today) is False

    result = _get_top_high5_mode_aware(
        db,
        requested_level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=today,
    )
    assert result["contests"] == []


def test_participation_regional_eligible_once_its_own_close_date_passes(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "partreg2", submission_month_start=july)
    contest = _contest(db, "partreg2", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="partreg2")
    contestant = _contestant(db, suffix="partreg2", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _freeze_row(db, contestant=contestant, contest=contest, rnd=rnd, season=season,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    db.commit()

    today = date(2026, 11, 1)  # after 2026-10-31
    result = _get_top_high5_mode_aware(
        db,
        requested_level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=today,
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["contest_mode"] == "participation"


# ---------------------------------------------------------------------------
# Phase 9: COUNTRY -- reproduces the exact confirmed production case.
# ---------------------------------------------------------------------------

def test_nomination_country_eligible_before_participation_country_close(db):
    """July nomination Country frozen rows exist; July participation country
    close hasn't passed yet. Nomination July Country must be eligible."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "nomcountry", submission_month_start=july)
    contest = _contest(db, "nomcountry", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="nomcountry")
    contestant = _contestant(db, suffix="nomcountry", rnd=rnd, contest=contest, country="Tanzania")
    _freeze_row(db, contestant=contestant, contest=contest, rnd=rnd, season=season,
                level=SeasonLevel.COUNTRY, jurisdiction="Tanzania", rank=1)
    db.commit()

    today = date(2026, 9, 22)
    # Nomination Country close for July = August 31 (M+1) -- already passed.
    assert _level_close_date_for_mode(rnd, SeasonLevel.COUNTRY, "nomination") == date(2026, 8, 31)
    assert _level_result_eligible(rnd, SeasonLevel.COUNTRY, "nomination", today) is True
    # Participation Country close for July = September 30 (M+2) -- NOT passed as of Sep 22.
    assert rnd.country_season_end_date == date(2026, 9, 30)
    assert _level_result_eligible(rnd, SeasonLevel.COUNTRY, "participation", today) is False

    result = _get_top_high5_mode_aware(
        db,
        requested_level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=today,
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["round_id"] == rnd.id
    assert result["contests"][0]["contest_mode"] == "nomination"


# ---------------------------------------------------------------------------
# Phase 10: REGIONAL -- reproduces the live production shape exactly
# (May + June nomination frozen; June participation regional end not passed).
# ---------------------------------------------------------------------------

def test_nomination_regional_selects_freshest_eligible_round_not_older_one(db):
    may = _month_start(date(2026, 5, 1))
    june = _month_start(date(2026, 6, 1))
    may_round = _round_for_month(db, "may", submission_month_start=may)
    june_round = _round_for_month(db, "june", submission_month_start=june)
    contest = _contest(db, "regional", mode="nomination")

    may_season = _season(db, may_round, level=SeasonLevel.REGIONAL, suffix="may")
    june_season = _season(db, june_round, level=SeasonLevel.REGIONAL, suffix="june")

    may_contestant = _contestant(db, suffix="mayreg", rnd=may_round, contest=contest, country="Tanzania", region="East Africa")
    june_contestant = _contestant(db, suffix="junereg", rnd=june_round, contest=contest, country="Tanzania", region="East Africa")

    _freeze_row(db, contestant=may_contestant, contest=contest, rnd=may_round, season=may_season,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    _freeze_row(db, contestant=june_contestant, contest=contest, rnd=june_round, season=june_season,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    db.commit()

    today = date(2026, 9, 22)
    # Nomination Regional close: May -> July 31 (M+2), June -> August 31 (M+2). Both passed.
    assert _level_result_eligible(may_round, SeasonLevel.REGIONAL, "nomination", today) is True
    assert _level_result_eligible(june_round, SeasonLevel.REGIONAL, "nomination", today) is True
    # June's PARTICIPATION regional_end_date (Sep 30) has NOT passed -- the exact production bug trigger.
    assert june_round.regional_end_date == date(2026, 9, 30)

    result = _get_top_high5_mode_aware(
        db,
        requested_level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=today,
    )
    assert len(result["contests"]) == 1
    # June (fresher), not May.
    assert result["contests"][0]["round_id"] == june_round.id
    assert result["round_id"] == june_round.id


# ---------------------------------------------------------------------------
# Phase 11: CONTINENTAL -- April + May nomination frozen; May participation
# continental end not passed.
# ---------------------------------------------------------------------------

def test_nomination_continental_selects_freshest_eligible_round(db):
    april = _month_start(date(2026, 4, 1))
    may = _month_start(date(2026, 5, 1))
    april_round = _round_for_month(db, "april", submission_month_start=april)
    may_round = _round_for_month(db, "may2", submission_month_start=may)
    contest = _contest(db, "continental", mode="nomination")

    april_season = _season(db, april_round, level=SeasonLevel.CONTINENT, suffix="april")
    may_season = _season(db, may_round, level=SeasonLevel.CONTINENT, suffix="may2")

    april_contestant = _contestant(db, suffix="aprilcont", rnd=april_round, contest=contest, country="Tanzania")
    may_contestant = _contestant(db, suffix="maycont", rnd=may_round, contest=contest, country="Tanzania")

    _freeze_row(db, contestant=april_contestant, contest=contest, rnd=april_round, season=april_season,
                level=SeasonLevel.CONTINENT, jurisdiction="Africa", rank=1)
    _freeze_row(db, contestant=may_contestant, contest=contest, rnd=may_round, season=may_season,
                level=SeasonLevel.CONTINENT, jurisdiction="Africa", rank=1)
    db.commit()

    today = date(2026, 9, 22)
    assert _level_result_eligible(may_round, SeasonLevel.CONTINENT, "nomination", today) is True
    # May's PARTICIPATION continental_end_date (Sep 30) has NOT passed.
    assert may_round.continental_end_date == date(2026, 9, 30)

    result = _get_top_high5_mode_aware(
        db,
        requested_level=SeasonLevel.CONTINENT, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=today,
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["round_id"] == may_round.id


# ---------------------------------------------------------------------------
# Phase 8: mandatory mixed-mode test.
# ---------------------------------------------------------------------------

def test_mixed_mode_each_contest_resolves_its_own_round(db):
    """
    Contest A (participation) and Contest B (nomination) both have frozen
    Regional results across the same two rounds (May, June). At the same
    as-of date, nomination's freshest eligible round is June; participation's
    is still May (June's own participation regional end hasn't passed).
    """
    may = _month_start(date(2026, 5, 1))
    june = _month_start(date(2026, 6, 1))
    may_round = _round_for_month(db, "mixmay", submission_month_start=may)
    june_round = _round_for_month(db, "mixjune", submission_month_start=june)

    contest_a = _contest(db, "mixA", mode="participation")
    contest_b = _contest(db, "mixB", mode="nomination")

    season_a_may = _season(db, may_round, level=SeasonLevel.REGIONAL, suffix="mixAmay")
    season_a_june = _season(db, june_round, level=SeasonLevel.REGIONAL, suffix="mixAjune")
    season_b_may = _season(db, may_round, level=SeasonLevel.REGIONAL, suffix="mixBmay")
    season_b_june = _season(db, june_round, level=SeasonLevel.REGIONAL, suffix="mixBjune")

    a_may_c = _contestant(db, suffix="aMay", rnd=may_round, contest=contest_a, country="Tanzania", region="East Africa")
    a_june_c = _contestant(db, suffix="aJune", rnd=june_round, contest=contest_a, country="Tanzania", region="East Africa")
    b_may_c = _contestant(db, suffix="bMay", rnd=may_round, contest=contest_b, country="Tanzania", region="East Africa")
    b_june_c = _contestant(db, suffix="bJune", rnd=june_round, contest=contest_b, country="Tanzania", region="East Africa")

    _freeze_row(db, contestant=a_may_c, contest=contest_a, rnd=may_round, season=season_a_may,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    _freeze_row(db, contestant=a_june_c, contest=contest_a, rnd=june_round, season=season_a_june,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    _freeze_row(db, contestant=b_may_c, contest=contest_b, rnd=may_round, season=season_b_may,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    _freeze_row(db, contestant=b_june_c, contest=contest_b, rnd=june_round, season=season_b_june,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    db.commit()

    today = date(2026, 9, 22)
    result = _get_top_high5_mode_aware(
        db,
        requested_level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=today,
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert by_contest[contest_a.id]["round_id"] == may_round.id  # participation: still May
    assert by_contest[contest_a.id]["contest_mode"] == "participation"
    assert by_contest[contest_b.id]["round_id"] == june_round.id  # nomination: fresher June
    assert by_contest[contest_b.id]["contest_mode"] == "nomination"


# ---------------------------------------------------------------------------
# Phase 12: Global regression -- untouched single-round path.
# ---------------------------------------------------------------------------

def test_global_still_uses_original_single_round_path(db):
    march = _month_start(date(2026, 3, 1))
    rnd = _round_for_month(db, "globalreg", submission_month_start=march)
    rnd.global_end_date = date(2026, 8, 31)  # force a definite, already-passed date
    db.add(rnd)
    contest = _contest(db, "globalreg", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.GLOBAL, suffix="globalreg")
    contestant = _contestant(db, suffix="globalreg", rnd=rnd, contest=contest, country="Tanzania")
    _freeze_row(db, contestant=contestant, contest=contest, rnd=rnd, season=season,
                level=SeasonLevel.GLOBAL, jurisdiction="Global", rank=1)
    db.commit()

    today = date(2026, 9, 22)
    result = _get_top_high5_single_round(
        db,
        round_id=None, requested_level=SeasonLevel.GLOBAL, selected_country="",
        variants=set(), today=today,
    )
    assert result["round_id"] == rnd.id
    assert len(result["contests"]) == 1
    # Global path's response entries do NOT carry the new round_id/contest_mode
    # fields (include_round_fields=False) -- exact prior shape preserved.
    assert "round_id" not in result["contests"][0]
    assert "contest_mode" not in result["contests"][0]


# ---------------------------------------------------------------------------
# Explicit round_id and CITY: unchanged behavior, sanity checks.
# ---------------------------------------------------------------------------

def test_explicit_round_id_bypasses_eligibility_gate(db):
    """An explicit ?round_id= is honored as-is, no eligibility gating --
    unchanged from before this fix."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "explicit", submission_month_start=july)
    contest = _contest(db, "explicit", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="explicit")
    contestant = _contestant(db, suffix="explicit", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _freeze_row(db, contestant=contestant, contest=contest, rnd=rnd, season=season,
                level=SeasonLevel.REGIONAL, jurisdiction="East Africa", rank=1)
    db.commit()

    today = date(2026, 9, 22)  # well before July participation's Oct 31 regional close
    result = _get_top_high5_single_round(
        db, round_id=rnd.id, requested_level=SeasonLevel.REGIONAL,
        selected_country="Tanzania", variants={"tanzania", "tz"}, today=today,
    )
    assert result["round_id"] == rnd.id
    assert len(result["contests"]) == 1


def test_city_level_always_empty(db):
    result = _get_top_high5_single_round(
        db, round_id=None, requested_level=SeasonLevel.CITY,
        selected_country="Tanzania", variants={"tanzania", "tz"}, today=date(2026, 9, 22),
    )
    assert result["contests"] == []
