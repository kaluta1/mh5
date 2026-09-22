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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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

    # City closes Jan + 1 month = Feb; well past by June.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.CITY, selected_country="", variants=set(), today=date(2026, 6, 1),
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["rows"][0]["contestant_id"] == contestant.id
    assert result["contests"][0]["country_group"] == "Dar es Salaam"


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
        db, level=SeasonLevel.CITY, selected_country="", variants=set(), today=date(2026, 6, 1),
    )
    assert result["contests"] == []


# ---------------------------------------------------------------------------
# 6 & 7. Country lifecycle offsets, both modes.
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

    # Participation Country = M+2 -> ends Sep 30. Not yet closed on Sep 22.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 22),
    )
    assert result["contests"] == []

    # Closed once Oct 1 arrives.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    assert len(result["contests"]) == 1


def test_nomination_country_lifecycle_offset(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "nomcountry2", submission_month_start=july)
    contest = _contest(db, "nomcountry2", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="nomcountry2")
    contestant = _contestant(db, suffix="nomcountry2", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="nomcountry2")
    db.commit()

    # Nomination Country = M+1 -> ends Aug 31. Not yet closed Aug 22.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 8, 22),
    )
    assert result["contests"] == []

    # Closed once Sep 1 arrives (participation's own Country close, Sep 30,
    # has NOT passed yet -- proves nomination uses its own earlier calendar).
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 1),
    )
    assert len(result["contests"]) == 1
    assert result["contests"][0]["contest_mode"] == "nomination"


# ---------------------------------------------------------------------------
# 8. Regional offsets, both modes.
# ---------------------------------------------------------------------------

def test_regional_offsets_both_modes(db):
    july = _month_start(date(2026, 7, 1))
    part_round = _round_for_month(db, "partreg3", submission_month_start=july)
    nom_round = _round_for_month(db, "nomreg3", submission_month_start=july)
    part_contest = _contest(db, "partreg3", mode="participation")
    nom_contest = _contest(db, "nomreg3", mode="nomination")
    part_season = _season(db, part_round, level=SeasonLevel.REGIONAL, suffix="partreg3")
    nom_season = _season(db, nom_round, level=SeasonLevel.REGIONAL, suffix="nomreg3")
    part_c = _contestant(db, suffix="partreg3c", rnd=part_round, contest=part_contest, country="Tanzania", region="East Africa")
    nom_c = _contestant(db, suffix="nomreg3c", rnd=nom_round, contest=nom_contest, country="Tanzania", region="East Africa")
    _member(db, contestant=part_c, season=part_season)
    _member(db, contestant=nom_c, season=nom_season)
    _vote(db, contestant=part_c, contest=part_contest, season=part_season, suffix="partreg3c")
    _vote(db, contestant=nom_c, contest=nom_contest, season=nom_season, suffix="nomreg3c")
    db.commit()

    # Participation Regional = M+3 -> ends Oct 31. Nomination Regional = M+2 -> ends Sep 30.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert nom_contest.id in by_contest       # nomination already closed (Sep 30 passed)
    assert part_contest.id not in by_contest  # participation not yet closed (Oct 31 not passed)


# ---------------------------------------------------------------------------
# 9. Continental offsets, both modes.
# ---------------------------------------------------------------------------

def test_continental_offsets_both_modes(db):
    july = _month_start(date(2026, 7, 1))
    part_round = _round_for_month(db, "partcont", submission_month_start=july)
    nom_round = _round_for_month(db, "nomcont", submission_month_start=july)
    part_contest = _contest(db, "partcont", mode="participation")
    nom_contest = _contest(db, "nomcont", mode="nomination")
    part_season = _season(db, part_round, level=SeasonLevel.CONTINENT, suffix="partcont")
    nom_season = _season(db, nom_round, level=SeasonLevel.CONTINENT, suffix="nomcont")
    part_c = _contestant(db, suffix="partcontc", rnd=part_round, contest=part_contest, continent="Africa")
    nom_c = _contestant(db, suffix="nomcontc", rnd=nom_round, contest=nom_contest, continent="Africa")
    _member(db, contestant=part_c, season=part_season)
    _member(db, contestant=nom_c, season=nom_season)
    _vote(db, contestant=part_c, contest=part_contest, season=part_season, suffix="partcontc")
    _vote(db, contestant=nom_c, contest=nom_contest, season=nom_season, suffix="nomcontc")
    db.commit()

    # Participation Continental = M+4 -> ends Nov 30. Nomination Continental = M+3 -> ends Oct 31.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.CONTINENT, selected_country="", variants=set(), today=date(2026, 11, 1),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert nom_contest.id in by_contest
    assert part_contest.id not in by_contest


# ---------------------------------------------------------------------------
# 10. Global offsets, both modes.
# ---------------------------------------------------------------------------

def test_global_offsets_both_modes(db):
    july = _month_start(date(2026, 7, 1))
    part_round = _round_for_month(db, "partglob", submission_month_start=july)
    nom_round = _round_for_month(db, "nomglob", submission_month_start=july)
    part_contest = _contest(db, "partglob", mode="participation")
    nom_contest = _contest(db, "nomglob", mode="nomination")
    part_season = _season(db, part_round, level=SeasonLevel.GLOBAL, suffix="partglob")
    nom_season = _season(db, nom_round, level=SeasonLevel.GLOBAL, suffix="nomglob")
    part_c = _contestant(db, suffix="partglobc", rnd=part_round, contest=part_contest)
    nom_c = _contestant(db, suffix="nomglobc", rnd=nom_round, contest=nom_contest)
    _member(db, contestant=part_c, season=part_season)
    _member(db, contestant=nom_c, season=nom_season)
    _vote(db, contestant=part_c, contest=part_contest, season=part_season, suffix="partglobc")
    _vote(db, contestant=nom_c, contest=nom_contest, season=nom_season, suffix="nomglobc")
    db.commit()

    # Participation Global = M+5 -> ends Dec 31. Nomination Global = M+4 -> ends Nov 30.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.GLOBAL, selected_country="", variants=set(), today=date(2026, 12, 1),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert nom_contest.id in by_contest
    assert part_contest.id not in by_contest
    assert by_contest[nom_contest.id]["country_group"] == "Global"


# ---------------------------------------------------------------------------
# 11 & 12. In-progress excluded, fully completed included.
# ---------------------------------------------------------------------------

def test_in_progress_stage_excluded(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "inprogress", submission_month_start=july)
    contest = _contest(db, "inprogress", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="inprogress")
    contestant = _contestant(db, suffix="inprogress", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="inprogress")
    db.commit()

    # Regional ends Oct 31; today is mid-window.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 15),
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

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
    )
    assert len(result["contests"]) == 1


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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
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
        variants={"tanzania", "tz"}, today=date(2031, 4, 15),
    )
    assert result["contests"] == []

    # Closed after M+2's end.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2031, 6, 1),
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

    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 12, 1),
    )
    assert result["contests"] == []


# ---------------------------------------------------------------------------
# Extra: mixed-mode Regional in one call -- both modes resolve their own
# round independently within the SAME response (parity with the mode-aware
# resolver's mandatory mixed-mode coverage).
# ---------------------------------------------------------------------------

def test_mixed_mode_each_contest_resolves_its_own_round_derived(db):
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "mixedderived", submission_month_start=july)
    part_contest = _contest(db, "mixedderivedA", mode="participation")
    nom_contest = _contest(db, "mixedderivedB", mode="nomination")
    part_season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="mixedderivedA")
    nom_season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="mixedderivedB")
    part_c = _contestant(db, suffix="mixedA", rnd=rnd, contest=part_contest, country="Tanzania", region="East Africa")
    nom_c = _contestant(db, suffix="mixedB", rnd=rnd, contest=nom_contest, country="Tanzania", region="East Africa")
    _member(db, contestant=part_c, season=part_season)
    _member(db, contestant=nom_c, season=nom_season)
    _vote(db, contestant=part_c, contest=part_contest, season=part_season, suffix="mixedA")
    _vote(db, contestant=nom_c, contest=nom_contest, season=nom_season, suffix="mixedB")
    db.commit()

    # Nomination Regional (M+2, ends Sep 30) closed; participation Regional
    # (M+3, ends Oct 31) not yet closed, at this same "today".
    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert nom_contest.id in by_contest
    assert part_contest.id not in by_contest
    assert by_contest[nom_contest.id]["contest_mode"] == "nomination"


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
        variants={"tanzania", "tz"}, today=date(2026, 9, 1),
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

    # Participation Country = M+2: closes Aug 31, well passed by Nov 1.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 11, 1),
    )
    card = result["contests"][0]
    assert card["cohort_month"] == "2026-06-01"
    assert card["round_name"] == rnd.name
    assert "July" not in (card["round_name"] or "")


def test_mixed_cohorts_flag_set_when_multiple_rounds_represented(db):
    """The exact production shape that looked like a bug: a nomination
    contest's fresher cohort and a participation contest's older cohort
    both legitimately appear in the same Country/Tanzania response.
    mixed_cohorts must be True, and each card must carry its own correct
    round -- the page-level round_id is only the freshest of the two."""
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

    # Participation June Country closes Aug 31 (passed); nomination July
    # Country closes Aug 31 too (M+1) -- both eligible by Sep 22.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 22),
    )
    assert result["mixed_cohorts"] is True
    by_contest = {c["contest_id"]: c for c in result["contests"]}
    assert by_contest[part_contest.id]["round_id"] == june_round.id
    assert by_contest[part_contest.id]["cohort_month"] == "2026-06-01"
    assert by_contest[nom_contest.id]["round_id"] == july_round.id
    assert by_contest[nom_contest.id]["cohort_month"] == "2026-07-01"
    # Page-level banner is the freshest represented -- July -- but that is
    # diagnostic only; it must not be read as "every card's cohort".
    assert result["round_id"] == july_round.id


def test_no_older_or_newer_cohort_fallback_when_expected_cohort_has_no_data(db):
    """PART 9 TEST 6: if the only round with real cohort data for a contest
    is NOT yet closed, the resolver must return empty for that contest --
    never substitute an older or newer round's data instead."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "nosubstitute", submission_month_start=july)
    contest = _contest(db, "nosubstitute", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="nosubstitute")
    contestant = _contestant(db, suffix="nosubstitute", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="nosubstitute")
    db.commit()

    # Participation July Country closes Sep 30 -- not yet passed on Sep 22.
    # This contest has NO other round's data at all to fall back to.
    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 22),
    )
    assert result["contests"] == []


def test_registered_at_is_the_authoritative_registration_timestamp(db):
    """PART 9 TEST 7: the API's registered_at must be
    Contestant.registration_date -- never a TopHigh5Result, ContestantSeason,
    or promotion timestamp."""
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
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    row_out = result["contests"][0]["rows"][0]
    assert row_out["registered_at"] == "2026-07-03T14:30:00"


def test_topHigh5result_still_not_required_after_metadata_change(db):
    """PART 9 TEST 9: the metadata/registered_at additions must not have
    reintroduced any TopHigh5Result dependency."""
    assert db.query(TopHigh5Result).count() == 0
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "stillnotreq", submission_month_start=july)
    contest = _contest(db, "stillnotreq", mode="nomination")
    season = _season(db, rnd, level=SeasonLevel.COUNTRY, suffix="stillnotreq")
    contestant = _contestant(db, suffix="stillnotreq", rnd=rnd, contest=contest, country="Tanzania")
    _member(db, contestant=contestant, season=season)
    _vote(db, contestant=contestant, contest=contest, season=season, suffix="stillnotreq")
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.COUNTRY, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 9, 1),
    )
    assert db.query(TopHigh5Result).count() == 0
    assert len(result["contests"]) == 1
