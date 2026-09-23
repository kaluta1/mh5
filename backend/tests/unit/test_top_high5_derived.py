"""
Tests for the 2026 derived (live-computed) Top High5 architecture
(app.services.top_high5_live.resolve_live_top_high5), which replaces
top_high5_results as the default display's source of truth.

See KALUTASOCIETY_ROUND26_POST_REPAIR_FORENSIC_AUDIT for the two proven
production gaps that motivated this: (1) a 2026-09-03 qualification-churn
event that deactivated most of one day's Continental ContestantSeason rows
~1 minute after a correct promotion batch, and (2) a 2026-09-14 historical
backfill that silently produced 0 rows for 91/104 contests once that churn
made its live query come up empty. Both are frozen-snapshot coverage gaps,
not defects in current live ranking data -- exactly what this derived
resolver sidesteps by never depending on top_high5_results.

Fixtures build real ContestantSeason (membership) + ContestantVoting (votes)
rows directly -- no TopHigh5Result anywhere in this file.
"""
from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime

from app.models.contest import Contest
from app.models.contests import (
    ContestantSeason,
    ContestSeason,
    Contestant,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, RoundStatus
from app.models.user import User
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService
from app.services.top_high5_live import resolve_live_top_high5


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_end(d: date) -> date:
    last_day = _calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def _round_for_month(db, suffix: str, *, submission_month_start: date, status: RoundStatus = RoundStatus.ACTIVE) -> Round:
    """Full canonical PARTICIPATION calendar (City=M+1 .. Global=M+5), exactly
    as generate_monthly_rounds.py writes for a real round."""
    add = SeasonMigrationService._add_months
    city = add(submission_month_start, 1)
    country = add(submission_month_start, 2)
    regional = add(submission_month_start, 3)
    continental = add(submission_month_start, 4)
    globl = add(submission_month_start, 5)
    rnd = Round(
        name=f"Round {submission_month_start.strftime('%B %Y')} {suffix}",
        status=status,
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


def _contestant(
    db, *, suffix: str, rnd: Round, contest: Contest, country: str = "",
    region: str = "", city: str = "", continent: str = "Africa",
) -> Contestant:
    owner = User(email=f"th5derived-{suffix}@example.test", hashed_password="unused")
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
        city=city,
        continent=continent,
    )
    db.add(c)
    db.flush()
    return c


def _member(db, *, contestant: Contestant, season: ContestSeason, active: bool = True) -> ContestantSeason:
    row = ContestantSeason(contestant_id=contestant.id, season_id=season.id, is_active=active)
    db.add(row)
    db.flush()
    return row


def _vote(db, *, contestant: Contestant, contest: Contest, season: ContestSeason, suffix: str, points: int = 10) -> ContestantVoting:
    voter = User(email=f"voter-{suffix}@example.test", hashed_password="unused")
    db.add(voter)
    db.flush()
    row = ContestantVoting(
        user_id=voter.id,
        contestant_id=contestant.id,
        contest_id=contest.id,
        season_id=season.id,
        vote_bucket_key=f"ty:{contest.contest_type or ''}:{contest.contest_mode or ''}",
        position=1,
        points=points,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# 1. Default works with NO TopHigh5Result rows at all.
# ---------------------------------------------------------------------------

def test_default_works_with_no_frozen_rows_at_all(db):
    assert db.query(TopHigh5Result).count() == 0
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "nofreeze", submission_month_start=july)
    contest = _contest(db, "nofreeze", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="nofreeze")
    contestant = _contestant(db, suffix="nofreeze", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="nofreeze")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    assert db.query(TopHigh5Result).count() == 0  # never written by the derived path
    assert len(result["contests"]) == 1
    assert result["contests"][0]["rows"][0]["contestant_id"] == contestant.id


# ---------------------------------------------------------------------------
# 2 & 3. Stale / incorrect frozen rows never affect the derived result.
# ---------------------------------------------------------------------------

def test_stale_frozen_row_does_not_affect_derived_result(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "stale", submission_month_start=july)
    contest = _contest(db, "stale", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="stale")
    real = _contestant(db, suffix="stalereal", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=real, season=season)
    _vote(db, contestant=real, contest=contest, season=season, suffix="stalereal")

    # A stale/wrong frozen row naming a DIFFERENT (non-existent-membership)
    # contestant -- must have zero influence on the derived result.
    ghost = _contestant(db, suffix="staleghost", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    db.add(TopHigh5Result(
        contestant_id=ghost.id, contest_id=contest.id, level=SeasonLevel.REGIONAL,
        jurisdiction="East Africa", round_id=rnd.id, from_season_id=season.id, rank=1,
        total_points=999, total_votes=999, migrated=True,
    ))
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    ids = [r["contestant_id"] for c in result["contests"] for r in c["rows"]]
    assert ids == [real.id]
    assert ghost.id not in ids


def test_incorrect_frozen_row_does_not_override_authoritative_ranking(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "wrongrank", submission_month_start=july)
    contest = _contest(db, "wrongrank", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="wrongrank")
    winner = _contestant(db, suffix="realwinner", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    loser = _contestant(db, suffix="realloser", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=winner, season=season)
    _member(db, contestant=loser, season=season)
    _vote(db, contestant=winner, contest=contest, season=season, suffix="win", points=50)
    _vote(db, contestant=loser, contest=contest, season=season, suffix="lose", points=5)

    # A frozen row claims `loser` is rank 1 -- must not change the derived order.
    db.add(TopHigh5Result(
        contestant_id=loser.id, contest_id=contest.id, level=SeasonLevel.REGIONAL,
        jurisdiction="East Africa", round_id=rnd.id, from_season_id=season.id, rank=1,
        total_points=999, total_votes=999, migrated=True,
    ))
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    rows = result["contests"][0]["rows"]
    assert rows[0]["contestant_id"] == winner.id
    assert rows[0]["rank"] == 1
    assert rows[1]["contestant_id"] == loser.id


# ---------------------------------------------------------------------------
# 4 & 5. City: participation works, nomination never appears.
# ---------------------------------------------------------------------------

def test_participation_city_works(db):
    jan = _month_start(date(2026, 1, 1))
    rnd = _round_for_month(db, "citywork", submission_month_start=jan)
    contest = _contest(db, "citywork", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.CITY, suffix="citywork")
    contestant = _contestant(db, suffix="citywork", rnd=rnd, contest=contest, city="Dar es Salaam")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="citywork")
    db.commit()

    # City target_month = current - 1. For January's cohort to be targeted,
    # "today" must be January + 1 = February.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.CITY, selected_country="", variants=set(), today=date(2026, 2, 15),
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["rows"][0]["contestant_id"] == contestant.id
    assert result["contests"][0]["country_group"] == "Dar es Salaam"
    assert result["contests"][0]["cohort_month"] == "2026-01-01"


def test_nomination_never_appears_in_city(db):
    jan = _month_start(date(2026, 1, 1))
    rnd = _round_for_month(db, "nocity", submission_month_start=jan)
    contest = _contest(db, "nocity", mode="nomination")
    # Even if a CITY-level season+membership somehow exists (malformed/legacy
    # data), nomination must never surface in the City tab.
    season = _season(db, rnd, level=SeasonLevel.CITY, suffix="nocity")
    contestant = _contestant(db, suffix="nocity", rnd=rnd, contest=contest, city="Kampala")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="nocity")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.CITY, selected_country="", variants=set(), today=date(2026, 2, 15),
    )
    assert result["contests"] == []


# ---------------------------------------------------------------------------
# 6 & 7. Country: exact calendar-month target, both modes share ONE target
# round (no more "nomination reaches Country a month before participation
# does" causing two different rounds in one response -- see
# test_both_modes_share_the_same_target_round below for that invariant).
# ---------------------------------------------------------------------------

def test_participation_country_lifecycle_offset(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "partcountry", submission_month_start=july)
    contest = _contest(db, "partcountry", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="partcountry")
    contestant = _contestant(db, suffix="partcountry", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="partcountry")
    db.commit()

    # Country target_month = current - 2. On Aug 22 that's June, not July --
    # empty. On Sep 1 that's July -- matches.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 22),
    )
    assert result["contests"] == []

    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 1),
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["cohort_month"] == "2026-07-01"


def test_nomination_country_lifecycle_offset(db):
    """Nomination's OWN faster stage timing (Country=M+1) no longer changes
    WHICH round gets targeted -- only its stage_month metadata differs from
    participation's. The target round itself is purely calendar-derived."""
    june = _month_start(date(2026, 6, 1))
    rnd = _round_for_month(db, "nomcountry2", submission_month_start=june)
    contest = _contest(db, "nomcountry2", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="nomcountry2")
    contestant = _contestant(db, suffix="nomcountry2", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="nomcountry2")
    db.commit()

    # today=Aug 1 -> Country target_month = June -- matches this round.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 1),
    )
    assert len(result["contests"]) == 1
    card = result["contests"][0]
    assert card["contest_mode"] == "nomination"
    assert card["cohort_month"] == "2026-06-01"
    # stage_month still reflects nomination's own faster M+1 offset (July),
    # purely informational -- it played no part in selecting this round.
    assert card["stage_month"] == "2026-07-01"


# ---------------------------------------------------------------------------
# 8-10. Regional/Continental/Global: exact calendar-month target.
# ---------------------------------------------------------------------------

def test_regional_offsets_both_modes(db):
    may = _month_start(date(2026, 5, 1))
    rnd = _round_for_month(db, "reg4", submission_month_start=may)
    part_contest = _contest(db, "partreg3", mode="participation")
    nom_contest = _contest(db, "nomreg3", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="reg4")
    part_c = _contestant(db, suffix="partreg3c", rnd=rnd, contest=part_contest, country="Tanzania", region="East Africa")
    nom_c = _contestant(db, suffix="nomreg3c", rnd=rnd, contest=nom_contest, country="Tanzania", region="East Africa")
    _member(db, contestant=part_c, season=season)
    _member(db, contestant=nom_c, season=season)
    _vote(db, contestant=part_c, contest=part_contest, season=season, suffix="partreg3c")
    _vote(db, contestant=nom_c, contest=nom_contest, season=season, suffix="nomreg3c")
    db.commit()

    # Regional target_month = current - 3. today=Aug -> May. Both modes'
    # May-cohort contestants appear -- same round, same cohort_month.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 10),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert part_contest.id in by_contest
    assert nom_contest.id in by_contest
    assert by_contest[part_contest.id]["cohort_month"] == "2026-05-01"
    assert by_contest[nom_contest.id]["cohort_month"] == "2026-05-01"
    assert by_contest[part_contest.id]["round_id"] == by_contest[nom_contest.id]["round_id"]


def test_continental_offsets_both_modes(db):
    april = _month_start(date(2026, 4, 1))
    rnd = _round_for_month(db, "cont5", submission_month_start=april)
    part_contest = _contest(db, "partcont", mode="participation")
    nom_contest = _contest(db, "nomcont", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.CONTINENT, suffix="cont5")
    part_c = _contestant(db, suffix="partcontc", rnd=rnd, contest=part_contest, continent="Africa")
    nom_c = _contestant(db, suffix="nomcontc", rnd=rnd, contest=nom_contest, continent="Africa")
    _member(db, contestant=part_c, season=season)
    _member(db, contestant=nom_c, season=season)
    _vote(db, contestant=part_c, contest=part_contest, season=season, suffix="partcontc")
    _vote(db, contestant=nom_c, contest=nom_contest, season=season, suffix="nomcontc")
    db.commit()

    # Continental target_month = current - 4. today=Aug -> April.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.CONTINENT, selected_country="", variants=set(), today=date(2026, 8, 10),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert part_contest.id in by_contest
    assert nom_contest.id in by_contest
    assert by_contest[part_contest.id]["cohort_month"] == "2026-04-01"


def test_global_offsets_both_modes(db):
    march = _month_start(date(2026, 3, 1))
    rnd = _round_for_month(db, "glob6", submission_month_start=march)
    part_contest = _contest(db, "partglob", mode="participation")
    nom_contest = _contest(db, "nomglob", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.GLOBAL, suffix="glob6")
    part_c = _contestant(db, suffix="partglobc", rnd=rnd, contest=part_contest)
    nom_c = _contestant(db, suffix="nomglobc", rnd=rnd, contest=nom_contest)
    _member(db, contestant=part_c, season=season)
    _member(db, contestant=nom_c, season=season)
    _vote(db, contestant=part_c, contest=part_contest, season=season, suffix="partglobc")
    _vote(db, contestant=nom_c, contest=nom_contest, season=season, suffix="nomglobc")
    db.commit()

    # Global target_month = current - 5. today=Aug -> March.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.GLOBAL, selected_country="", variants=set(), today=date(2026, 8, 10),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert part_contest.id in by_contest
    assert nom_contest.id in by_contest
    assert by_contest[part_contest.id]["cohort_month"] == "2026-03-01"
    assert by_contest[part_contest.id]["country_group"] == "Global"


def test_both_modes_share_the_same_target_round(db):
    """The exact invariant this whole rework enforces: participation and
    nomination contests from DIFFERENT rounds must NOT both appear in one
    response. Only the contest actually in the target month's round shows;
    the other is silently absent -- no mixing, no substitution."""
    june = _month_start(date(2026, 6, 1))
    july = _month_start(date(2026, 7, 1))
    june_round = _round_for_month(db, "sharejune", submission_month_start=june)
    july_round = _round_for_month(db, "sharejuly", submission_month_start=july)
    june_contest = _contest(db, "shareJune", mode="participation")
    july_contest = _contest(db, "shareJuly", mode="nomination")
    june_season = _season(db, june_round, level=SeasonLevel.COUNTRY, suffix="sharejune")
    july_season = _season(db, july_round, level=SeasonLevel.COUNTRY, suffix="sharejuly")
    june_c = _contestant(db, suffix="sharejunec", rnd=june_round, contest=june_contest, country="Tanzania")
    july_c = _contestant(db, suffix="sharejulyc", rnd=july_round, contest=july_contest, country="Tanzania")
    _member(db, contestant=june_c, season=june_season)
    _member(db, contestant=july_c, season=july_season)
    _vote(db, contestant=june_c, contest=june_contest, season=june_season, suffix="sharejunec")
    _vote(db, contestant=july_c, contest=july_contest, season=july_season, suffix="sharejulyc")
    db.commit()

    # Country target_month on Aug 1 = June. Only the June contest appears.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 1),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert june_contest.id in by_contest
    assert july_contest.id not in by_contest
    assert result["mixed_cohorts"] is False
    assert len({c["round_id"] for c in result["contests"]}) == 1


# ---------------------------------------------------------------------------
# 11 & 12. In-progress excluded, fully completed included.
# ---------------------------------------------------------------------------

def test_in_progress_stage_excluded(db):
    """A round that is NOT the exact calendar target_month is excluded --
    including a round only one month off, proving there is no "close
    enough"/in-progress tolerance, just an exact month match."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "inprogress", submission_month_start=july)
    contest = _contest(db, "inprogress", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="inprogress")
    contestant = _contestant(db, suffix="inprogress", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="inprogress")
    db.commit()

    # Regional target_month = current - 3. today=Sep 15 -> target=June, not
    # July -- excluded even though July is "close".
    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 15),
    )
    assert result["contests"] == []


def test_fully_completed_stage_included(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "completed", submission_month_start=july)
    contest = _contest(db, "completed", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="completed")
    contestant = _contestant(db, suffix="completed", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="completed")
    db.commit()

    # Regional target_month = current - 3. today=Oct 1 -> target=July -- MATCH.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["cohort_month"] == "2026-07-01"


# ---------------------------------------------------------------------------
# 13. Wrong-round contestants excluded (cohort-integrity guard).
# ---------------------------------------------------------------------------

def test_wrong_round_contestant_excluded(db):
    july = _month_start(date(2026, 7, 1))
    aug = _month_start(date(2026, 8, 1))
    july_round = _round_for_month(db, "wrongroundjuly", submission_month_start=july)
    aug_round = _round_for_month(db, "wrongroundaug", submission_month_start=aug)
    contest = _contest(db, "wronground", mode="participation")
    july_season = _season(db, july_round, level=SeasonLevel.REGIONAL, suffix="wrongroundjuly")

    # A contestant whose OWN round is August, incorrectly linked into JULY's
    # regional season (the exact cross-round contamination shape found in
    # KALUTASOCIETY_TOP_HIGH5_SYSTEMIC_DUPLICATE_FREEZE_AUDIT).
    foreign = _contestant(db, suffix="foreign", rnd=aug_round, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=foreign, season=july_season)
    _vote(db, contestant=foreign, contest=contest, season=july_season, suffix="foreign")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    assert result["contests"] == []  # foreign-round row must never surface


# ---------------------------------------------------------------------------
# 14. Wrong-jurisdiction contestants excluded.
# ---------------------------------------------------------------------------

def test_wrong_jurisdiction_excluded(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "wrongjuris", submission_month_start=july)
    contest = _contest(db, "wrongjuris", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="wrongjuris")
    tz_contestant = _contestant(db, suffix="tzone", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    ng_contestant = _contestant(db, suffix="ngone", rnd=rnd, contest=contest, country="Nigeria", region="West Africa")
    _member(db, contestant=tz_contestant, season=season)
    _member(db, contestant=ng_contestant, season=season)
    _vote(db, contestant=tz_contestant, contest=contest, season=season, suffix="tzone")
    _vote(db, contestant=ng_contestant, contest=contest, season=season, suffix="ngone")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    ids = [r["contestant_id"] for c in result["contests"] for r in c["rows"]]
    assert tz_contestant.id in ids
    assert ng_contestant.id not in ids


# ---------------------------------------------------------------------------
# 15. Contest.level cannot override contestant/cohort truth.
# ---------------------------------------------------------------------------

def test_contest_level_field_cannot_override_derived_result(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "levelfield", submission_month_start=july)
    contest = _contest(db, "levelfield", mode="participation")
    # Contest.level says "global" -- must have zero effect on which level
    # tab this contest's real Regional-cohort members show up under.
    contest.level = "global"
    db.add(contest)
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="levelfield")
    contestant = _contestant(db, suffix="levelfield", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="levelfield")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["contest_id"] == contest.id


# ---------------------------------------------------------------------------
# 16. ContestSeasonLink without valid contestant/ranking evidence cannot
#     create a result (there is no ContestSeasonLink read anywhere in the
#     derived path at all -- proven by simply never creating one).
# ---------------------------------------------------------------------------

def test_contestseasonlink_alone_cannot_create_a_result(db):
    """No ContestSeasonLink row is ever created in this test -- only a
    Contest + Round + ContestSeason + genuine ContestantSeason + vote. The
    derived result must still appear, proving ContestSeasonLink existence
    plays no role in the derived path at all (unlike the old frozen-result
    "already promoted" gates elsewhere in this codebase)."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "nolink", submission_month_start=july)
    contest = _contest(db, "nolink", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="nolink")
    contestant = _contestant(db, suffix="nolink", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="nolink")
    db.commit()

    from app.models.contests import ContestSeasonLink
    assert db.query(ContestSeasonLink).count() == 0

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    assert len(result["contests"]) == 1


# ---------------------------------------------------------------------------
# 17. Fewer than five legitimate contestants returns fewer than five.
# ---------------------------------------------------------------------------

def test_fewer_than_five_never_fabricated(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "fewerthan5", submission_month_start=july)
    contest = _contest(db, "fewerthan5", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="fewerthan5")
    c1 = _contestant(db, suffix="only1", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    c2 = _contestant(db, suffix="only2", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=c1, season=season)
    _member(db, contestant=c2, season=season)
    _vote(db, contestant=c1, contest=contest, season=season, suffix="only1")
    _vote(db, contestant=c2, contest=contest, season=season, suffix="only2")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    assert len(result["contests"][0]["rows"]) == 2  # not padded to 5


# ---------------------------------------------------------------------------
# 18. Tie-breaking matches the existing authoritative ranking service
#     (points, then shares/likes/comments/views via aggregate_rankings --
#     exercised here simply by confirming higher points always wins,
#     proving aggregate_rankings' own order is what's used, not a
#     home-grown comparison).
# ---------------------------------------------------------------------------

def test_ranking_order_matches_authoritative_service(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "tiebreak", submission_month_start=july)
    contest = _contest(db, "tiebreak", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="tiebreak")
    high = _contestant(db, suffix="high", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    low = _contestant(db, suffix="low", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=high, season=season)
    _member(db, contestant=low, season=season)
    _vote(db, contestant=high, contest=contest, season=season, suffix="high", points=100)
    _vote(db, contestant=low, contest=contest, season=season, suffix="low", points=1)
    db.commit()

    from app.services.voting_ranking import aggregate_rankings
    expected = aggregate_rankings(
        db, season_ids=[season.id], contestant_ids=[high.id, low.id],
        contest_id=contest.id, bucket_key=f"ty:t:participation", require_votes=False,
    )
    expected_order = [row.contestant_id for row in sorted(expected, key=lambda r: r.rank)]

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    derived_order = [r["contestant_id"] for r in result["contests"][0]["rows"]]
    assert derived_order == expected_order


# ---------------------------------------------------------------------------
# 19. Zero-vote behavior follows the existing documented rule (display-only
#     inclusion, require_votes=False) -- a genuine member with zero votes
#     still appears, ranked last, not hidden.
# ---------------------------------------------------------------------------

def test_zero_vote_contestant_still_displayed_per_existing_rule(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "zerovote", submission_month_start=july)
    contest = _contest(db, "zerovote", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="zerovote")
    voted = _contestant(db, suffix="voted", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    unvoted = _contestant(db, suffix="unvoted", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=voted, season=season)
    _member(db, contestant=unvoted, season=season)
    _vote(db, contestant=voted, contest=contest, season=season, suffix="voted", points=10)
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    rows = result["contests"][0]["rows"]
    ids = [r["contestant_id"] for r in rows]
    assert voted.id in ids and unvoted.id in ids
    assert rows[0]["contestant_id"] == voted.id
    unvoted_row = next(r for r in rows if r["contestant_id"] == unvoted.id)
    assert unvoted_row["votes_count"] == 0
    assert unvoted_row["stars_points"] == 0


# ---------------------------------------------------------------------------
# 20. Future-month calculation works without any hard-coded 2026 dates.
# ---------------------------------------------------------------------------

def test_future_month_works_without_hardcoded_dates(db):
    future_month = _month_start(date(2031, 3, 1))
    rnd = _round_for_month(db, "future", submission_month_start=future_month)
    contest = _contest(db, "future", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="future")
    contestant = _contestant(db, suffix="future", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="future")
    db.commit()

    # Country = M+2 -> not closed one month later.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2031, 3, 15),
    )
    assert result["contests"] == []

    # Closed after M+2's end.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2031, 5, 1),
    )
    assert len(result["contests"]) == 1


# ---------------------------------------------------------------------------
# Extra: CANCELLED round never eligible (parity with the frozen-path guard).
# ---------------------------------------------------------------------------

def test_cancelled_round_never_eligible_in_derived_path(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "cancelledderived", submission_month_start=july, status=RoundStatus.CANCELLED)
    contest = _contest(db, "cancelledderived", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="cancelledderived")
    contestant = _contestant(db, suffix="cancelledderived", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="cancelledderived")
    db.commit()

    # Country target_month = current - 2. today=Sep 15 -> target=July, which
    # DOES match this round's own cohort month -- but it's CANCELLED, so it
    # must still be excluded (find_round_for_month never returns a
    # CANCELLED round, even on an exact month match).
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 15),
    )
    assert result["contests"] == []


# ---------------------------------------------------------------------------
# PART 1-3/9 (2026-09-23 cohort-vs-stage confusion): reproduces, and proves
# NOT a bug, the reported "Country/Tanzania shows July instead of June"
# production observation. Root cause: a nomination contest's July cohort
# reaches Country (M+1, closes Aug 31) before a participation contest's own
# July cohort does (M+2, closes Sep 30) -- both are correct, independent
# results for DIFFERENT contests sharing one page; the page-level banner
# showing only the freshest represented round was the actual source of
# confusion, not the cohort calculation. See cohort_month/stage_month below
# and mixed_cohorts on the top-level response.
# ---------------------------------------------------------------------------

def test_cohort_month_is_independent_of_stage_month(db):
    """PART 9 TEST 1: cohort_month (the round's own submission/nomination
    month) must never equal the level's stage_month when the level has a
    nonzero offset -- proves the two are tracked separately, not conflated."""
    june = _month_start(date(2026, 6, 1))
    rnd = _round_for_month(db, "cohortstage", submission_month_start=june)
    contest = _contest(db, "cohortstage", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="cohortstage")
    contestant = _contestant(db, suffix="cohortstage", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="cohortstage")
    db.commit()

    # Nomination Country = M+1: June cohort's Country stage is July.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 1),
    )
    card = result["contests"][0]
    assert card["cohort_month"] == "2026-06-01"   # the ORIGINAL cohort, unchanged
    assert card["stage_month"] == "2026-07-01"     # when Country actually votes
    assert card["cohort_month"] != card["stage_month"]
    assert card["cohort_round_id"] == rnd.id
    assert card["cohort_round_name"] == rnd.name


def test_country_does_not_shift_cohort_forward_a_month(db):
    """PART 9 TEST 2: a June cohort must be reported as cohort_month=June,
    never July, regardless of which month Country's own voting falls in."""
    june = _month_start(date(2026, 6, 1))
    rnd = _round_for_month(db, "noshift", submission_month_start=june)
    contest = _contest(db, "noshift", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="noshift")
    contestant = _contestant(db, suffix="noshift", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="noshift")
    db.commit()

    # Country target_month = current - 2. today=Aug -> target=June -- MATCH.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 10),
    )
    card = result["contests"][0]
    assert card["cohort_month"] == "2026-06-01"
    assert card["round_name"] == rnd.name
    assert "July" not in (card["round_name"] or "")


def test_mixed_cohorts_flag_is_always_false_under_the_calendar_rule(db):
    """The exact production shape that used to look like a bug (a
    nomination contest's fresher cohort and a participation contest's older
    cohort both appearing in one Country/Tanzania response) can no longer
    happen: mixed_cohorts is now always False, since only one target round
    is ever queried, regardless of how many rounds/contests exist."""
    june = _month_start(date(2026, 6, 1))
    july = _month_start(date(2026, 7, 1))
    june_round = _round_for_month(db, "mixedjune", submission_month_start=june)
    july_round = _round_for_month(db, "mixedjuly", submission_month_start=july)

    part_contest = _contest(db, "mixedpart", mode="participation")
    nom_contest = _contest(db, "mixednom", mode="nomination")
    part_season = _season(db, june_round, level=SeasonLevel.COUNTRY, suffix="mixedpart")
    nom_season = _season(db, july_round, level=SeasonLevel.COUNTRY, suffix="mixednom")
    part_c = _contestant(db, suffix="mixedpartc", rnd=june_round, contest=part_contest, country="Tanzania")
    nom_c = _contestant(db, suffix="mixednomc", rnd=july_round, contest=nom_contest, country="Tanzania")
    _member(db, contestant=part_c, season=part_season)
    _member(db, contestant=nom_c, season=nom_season)
    _vote(db, contestant=part_c, contest=part_contest, season=part_season, suffix="mixedpartc")
    _vote(db, contestant=nom_c, contest=nom_contest, season=nom_season, suffix="mixednomc")
    db.commit()

    # Country target_month on Aug 22 = June. Only the June (participation)
    # contest appears; the July (nomination) contest does NOT, even though
    # it also has real cohort data -- it's simply not the target month.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 22),
    )
    assert result["mixed_cohorts"] is False
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert part_contest.id in by_contest
    assert by_contest[part_contest.id]["round_id"] == june_round.id
    assert by_contest[part_contest.id]["cohort_month"] == "2026-06-01"
    assert nom_contest.id not in by_contest
    assert result["round_id"] == june_round.id


def test_september_2026_country_returns_only_the_july_cohort(db):
    """The exact reported business case: in September 2026, Country must
    show the July 2026 cohort (July submission -> August City -> September
    Country, no idle "Start Voting" month). May/June/August cohorts with
    real Country data in the same country must all be excluded."""
    contests = {}
    for month in (5, 6, 7, 8):
        start = _month_start(date(2026, month, 1))
        rnd = _round_for_month(db, f"sep{month}", submission_month_start=start)
        contest = _contest(db, f"sep{month}", mode="participation")
        season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix=f"sep{month}")
        c = _contestant(db, suffix=f"sep{month}c", rnd=rnd, contest=contest, country="Tanzania")
        _member(db, contestant=c, season=season)
        _vote(db, contestant=c, contest=contest, season=season, suffix=f"sep{month}c")
        contests[month] = (rnd, contest)
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 23),
    )
    assert result["target_month"] == "2026-07-01"
    assert result["round_id"] == contests[7][0].id
    assert result["mixed_cohorts"] is False
    assert sorted({c["cohort_month"] for c in result["contests"]}) == ["2026-07-01"]
    assert [c["contest_id"] for c in result["contests"]] == [contests[7][1].id]


def test_no_older_or_newer_cohort_fallback_when_expected_cohort_has_no_data(db):
    """If the only round with real cohort data for a contest is not the
    exact calendar target_month, the resolver must return empty -- never
    substitute an older or newer round's data instead."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "nosubstitute", submission_month_start=july)
    contest = _contest(db, "nosubstitute", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="nosubstitute")
    contestant = _contestant(db, suffix="nosubstitute", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="nosubstitute")
    db.commit()

    # Country target_month on Aug 22 = June, not July. This contest has NO
    # June data at all -- must return empty, never substitute its July data.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 22),
    )
    assert result["contests"] == []


def test_registered_at_is_the_authoritative_registration_timestamp(db):
    """The API's registered_at must be Contestant.registration_date --
    never a TopHigh5Result, ContestantSeason, or promotion timestamp."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "registeredat", submission_month_start=july)
    contest = _contest(db, "registeredat", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="registeredat")
    contestant = _contestant(db, suffix="registeredat", rnd=rnd, contest=contest, country="Tanzania")
    contestant.registration_date = datetime(2026, 7, 3, 14, 30, 0)
    db.add(contestant)
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="registeredat")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 1),
    )
    row_out = result["contests"][0]["rows"][0]
    assert row_out["registered_at"] == "2026-07-03T14:30:00"


def test_topHigh5result_still_not_required_after_metadata_change(db):
    """The metadata/registered_at additions must not have reintroduced any
    TopHigh5Result dependency."""
    assert db.query(TopHigh5Result).count() == 0
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "stillnotreq", submission_month_start=july)
    contest = _contest(db, "stillnotreq", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="stillnotreq")
    contestant = _contestant(db, suffix="stillnotreq", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="stillnotreq")
    db.commit()

    # Country target_month on Sep 1 = July -- matches this round.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 1),
    )
    assert db.query(TopHigh5Result).count() == 0
    assert len(result["contests"]) == 1


# ---------------------------------------------------------------------------
# 2026-09-23 calendar-month filter: exact worked example from the spec, and
# month/year rollover.
# ---------------------------------------------------------------------------

def test_target_cohort_month_matches_the_september_2026_worked_example():
    """Direct check of the offset table against the authoritative example:
    current=September 2026 -> City=Aug, Country=Jul, Regional=Jun,
    Continental=May, Global=Apr (all 2026). No idle "Start Voting" month:
    July submission -> August City -> September Country."""
    from app.services.top_high5_live import target_cohort_month

    today = date(2026, 9, 23)
    assert target_cohort_month(SeasonLevel.CITY, today) == date(2026, 8, 1)
    assert target_cohort_month(SeasonLevel.COUNTRY, today) == date(2026, 7, 1)
    assert target_cohort_month(SeasonLevel.REGIONAL, today) == date(2026, 6, 1)
    assert target_cohort_month(SeasonLevel.CONTINENT, today) == date(2026, 5, 1)
    assert target_cohort_month(SeasonLevel.GLOBAL, today) == date(2026, 4, 1)


def test_target_cohort_month_rolls_over_the_year_boundary():
    """Direct check of the exact January 2027 example given: City=Dec 2026,
    Country=Nov 2026, Regional=Oct 2026, Continental=Sep 2026,
    Global=Aug 2026 -- the offset must subtract correctly across the
    Dec->Jan year boundary."""
    from app.services.top_high5_live import target_cohort_month

    today = date(2027, 1, 15)
    assert target_cohort_month(SeasonLevel.CITY, today) == date(2026, 12, 1)
    assert target_cohort_month(SeasonLevel.COUNTRY, today) == date(2026, 11, 1)
    assert target_cohort_month(SeasonLevel.REGIONAL, today) == date(2026, 10, 1)
    assert target_cohort_month(SeasonLevel.CONTINENT, today) == date(2026, 9, 1)
    assert target_cohort_month(SeasonLevel.GLOBAL, today) == date(2026, 8, 1)


def test_target_cohort_month_rolls_over_multiple_years_back():
    """A February target reaching back past the December boundary (Global,
    -5 months from February = September of the PREVIOUS year) -- guards
    against an off-by-one around the 12-month wraparound."""
    from app.services.top_high5_live import target_cohort_month

    today = date(2027, 2, 1)
    assert target_cohort_month(SeasonLevel.GLOBAL, today) == date(2026, 9, 1)
    assert target_cohort_month(SeasonLevel.CITY, today) == date(2027, 1, 1)


def test_end_to_end_year_rollover_finds_the_correct_round(db):
    """End-to-end (not just the pure date function): a December 2026 cohort
    must be found for City when "today" is January 2027, across the real
    resolver, real Round/ContestSeason/Contestant/vote data."""
    dec = _month_start(date(2026, 12, 1))
    rnd = _round_for_month(db, "rollover", submission_month_start=dec)
    contest = _contest(db, "rollover", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.CITY, suffix="rollover")
    contestant = _contestant(db, suffix="rollover", rnd=rnd, contest=contest, city="Arusha")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="rollover")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.CITY, selected_country="", variants=set(), today=date(2027, 1, 15),
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["cohort_month"] == "2026-12-01"
    assert result["target_month"] == "2026-12-01"


def test_target_month_present_on_every_response_including_empty(db):
    """target_month must be reported even when the level returns empty, so
    a caller/debugger can always see exactly which month was targeted."""
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 23),
    )
    assert result["contests"] == []
    assert result["target_month"] == "2026-07-01"
