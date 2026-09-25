"""
Derived (live-computed) Top High5 resolver.

============================================================================
WHY THIS MODULE EXISTS
============================================================================
Historical `TopHigh5Result` snapshots are frozen, write-once records that
only exist when `promote_to_next_level` actually ran *and* successfully
froze for a given (contest, level, round, jurisdiction) group. Two separate
2026 forensic investigations proved real, non-trivial coverage gaps in that
snapshot table:

  - KALUTASOCIETY_TOP_HIGH5_SYSTEMIC_DUPLICATE_FREEZE_AUDIT: 54% of all
    historical rows were cross-round contamination artifacts (since fixed
    going forward, but historical rows were not all repairable).
  - KALUTASOCIETY_ROUND26_POST_REPAIR_FORENSIC_AUDIT: a one-time
    qualification-churn event on 2026-09-03 (a bulk re-convergence pass
    inside `promote_to_next_level`, ~1 minute after the original correct
    promotion batch) deactivated 89% of that day's Continental
    ContestantSeason rows; a later historical backfill on 2026-09-14 then
    silently produced 0 rows for 91 of 104 contests because its live
    `qualified_only=True` query came up empty by then, with no error raised.

Neither gap is a live, ongoing defect in `promote_to_next_level` itself --
they are historical snapshot-coverage gaps. But depending on
`TopHigh5Result` for the *default* Top High5 display means the display's
correctness is hostage to whether every historical freeze happened to
succeed, which has now been proven false more than once.

============================================================================
THE CALENDAR-MONTH TARGETING RULE (2026-09-23)
============================================================================
An earlier version of this module let each contest independently pick its
own "freshest fully-completed round" per level. That correctly avoided
in-progress data, but two different contests (participation vs nomination,
different lifecycle offsets) could legitimately land on two different
cohort months in the same response -- which, while not a data bug (traced
and proven correct, see git history), was confusing on the page and is
explicitly disallowed going forward.

The rule now is a single, uniform calendar calculation with **no
per-contest search and no fallback**:

    target_month(level) = current_calendar_month - offset(level)
    offset = {CITY: 1, COUNTRY: 2, REGIONAL: 3, CONTINENT: 4, GLOBAL: 5}

This offset is anchored directly to PARTICIPATION's own lifecycle
(Submission=M, City=M+1, Country=M+2, Regional=M+3, Continental=M+4,
Global=M+5): each level targets the cohort whose participation stage for
that level falls in the current calendar month. E.g. in September 2026,
Country targets the July 2026 cohort (July submission -> August City ->
September Country). There is NO extra "Start Voting" month between
submission/nomination and the first voting stage -- "Start Voting" is only
a UI action/status, not a level, season or calendar month. (Corrected
2026-09-23: the first version of this rule used offsets one month larger,
{CITY: 2 .. GLOBAL: 6}, which wrongly assumed such an idle month.)
NOMINATION (City-less, Nomination=M, Country=M+1..Global=M+4) is queried
against the SAME one target round -- there is no separate target month
per mode, which is exactly why a level's response contains exactly one
cohort month, never a mix.

    current_month -> target_month -> the ONE Round whose own cohort month
    equals target_month -> contests/contestants that genuinely belong to
    THAT round's cohort at this level -> rank -> display.

If no Round exists for target_month, or no contest has real membership
there, the level returns empty. Never substitutes an older or newer month.
CITY remains participation-only (nomination has no City stage at all).

============================================================================
WHY NOT `ContestantSeason.is_active` ALONE, OR `ContestSeasonLink` ALONE
============================================================================
Both are proven, on real production data, to be unreliable as a *sole*
signal of "did this contestant genuinely reach this level":

  - `ContestSeasonLink.is_active` only says a CONTEST is linked to a
    season; it is never touched by contestant-level membership changes, so
    it can (and does, in production) stay active with zero real contestant
    members underneath it -- see
    KALUTASOCIETY_ROUND26_POST_REPAIR_FORENSIC_AUDIT's Phase 8 finding.
  - `ContestantSeason.is_active` reliably describes the PRESENT moment, but
    a later stage's own promotion/re-convergence activity can flip an
    EARLIER, already-genuine level's row inactive without that meaning the
    earlier level's result was ever wrong (same audit, Phase 3).

The minimum authoritative combination used here is: EXISTENCE of a
ContestantSeason row at this exact level for the target round's season (not
"currently active"), combined with the contestant's own immutable
`round_id` equalling the target round (cohort integrity -- proven, by a
2026-09-23 live trace, to be exactly what prevents a contestant who also
has stray ContestantSeason rows at other rounds -- e.g. from repeated
re-sync activity -- from leaking into the wrong cohort's card). No single
field is trusted alone.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.contest import Contest
from app.models.contests import Contestant, ContestantSeason, ContestSeason, SeasonLevel
from app.models.round import Round, RoundStatus
from app.services.season_migration import SeasonMigrationService
from app.services.voting_ranking import aggregate_rankings
from app.services.contest_category_integrity import dedupe_contestants_by_nominator


_LEVEL_ORDER = [
    SeasonLevel.CITY,
    SeasonLevel.COUNTRY,
    SeasonLevel.REGIONAL,
    SeasonLevel.CONTINENT,
    SeasonLevel.GLOBAL,
]

# Fixed calendar offset (in months, subtracted from the current month) used
# to compute the single target cohort month for each level. See the
# "CALENDAR-MONTH TARGETING RULE" section above for the exact rationale.
_TARGET_MONTH_OFFSET = {
    SeasonLevel.CITY: 1,
    SeasonLevel.COUNTRY: 2,
    SeasonLevel.REGIONAL: 3,
    SeasonLevel.CONTINENT: 4,
    SeasonLevel.GLOBAL: 5,
}

# PARTICIPATION's own calendar close/open date columns for each level (City
# =M+1 .. Global=M+5, see generate_monthly_rounds.py). Nomination never uses
# these columns -- see _level_close_date_for_mode/_level_open_date_for_mode.
# Debug/metadata only in this module: no longer used to decide eligibility
# (see module docstring), only to populate stage_open_date/stage_close_date
# on each card for verification purposes.
_PARTICIPATION_END_DATE_ATTR = {
    SeasonLevel.CITY: "city_season_end_date",
    SeasonLevel.COUNTRY: "country_season_end_date",
    SeasonLevel.REGIONAL: "regional_end_date",
    SeasonLevel.CONTINENT: "continental_end_date",
    SeasonLevel.GLOBAL: "global_end_date",
}
_PARTICIPATION_START_DATE_ATTR = {
    SeasonLevel.CITY: "city_season_start_date",
    SeasonLevel.COUNTRY: "country_season_start_date",
    SeasonLevel.REGIONAL: "regional_start_date",
    SeasonLevel.CONTINENT: "continental_start_date",
    SeasonLevel.GLOBAL: "global_start_date",
}

# Each level's own jurisdiction grouping field, mirroring exactly how
# `promote_to_next_level._freeze_top_high5_results` groups a level's own
# result ("Keyed by the FROM-level's own jurisdiction field (e.g. city for
# CITY->COUNTRY, country for COUNTRY->REGIONAL)"). GLOBAL has no next level
# and uses a single fixed "Global" bucket (see _location_value).
_LEVEL_JURISDICTION_FIELD = {
    SeasonLevel.CITY: "city",
    SeasonLevel.COUNTRY: "country",
    SeasonLevel.REGIONAL: "region",
    SeasonLevel.CONTINENT: "continent",
}


def next_level(level: SeasonLevel) -> Optional[SeasonLevel]:
    idx = _LEVEL_ORDER.index(level)
    return _LEVEL_ORDER[idx + 1] if idx < len(_LEVEL_ORDER) - 1 else None


def _add_months(base_year: int, base_month: int, delta: int) -> tuple[int, int]:
    """1-indexed (year, month) shifted by `delta` months (may be negative),
    correct across year boundaries in either direction."""
    index = base_year * 12 + (base_month - 1) + delta
    year, month0 = divmod(index, 12)
    return year, month0 + 1


def target_cohort_month(level: SeasonLevel, today: date) -> date:
    """
    The ONE cohort month this level displays right now, computed directly
    from the CURRENT calendar month via a fixed offset -- see the
    CALENDAR-MONTH TARGETING RULE section in the module docstring. No
    per-contest search, no mode branching in the offset, no fallback to any
    other month. Correct across year boundaries (verified by tests).
    """
    offset = _TARGET_MONTH_OFFSET[level]
    year, month = _add_months(today.year, today.month, -offset)
    return date(year, month, 1)


def _cohort_month(round_obj: Round) -> Optional[date]:
    """The round's OWN submission/nomination month ("M" in the M/M+1/M+2..
    lifecycle notation) -- the contest's original cohort, never a later
    stage's month."""
    return SeasonMigrationService._round_month_start(round_obj)


def find_round_for_month(db: Session, target_month: date) -> Optional[Round]:
    """
    The one Round whose own cohort month equals `target_month` -- reuses
    `_cohort_month` (SeasonMigrationService._round_month_start), the same
    authoritative month-derivation already used throughout this codebase.
    Never a CANCELLED round. If several somehow match the same month
    (not expected -- each calendar month has exactly one real round), the
    highest id wins as a defensive, deterministic tie-break.
    """
    candidates = db.query(Round).filter(Round.status != RoundStatus.CANCELLED).all()
    matches = [r for r in candidates if _cohort_month(r) == target_month]
    if not matches:
        return None
    matches.sort(key=lambda r: r.id, reverse=True)
    return matches[0]


def _level_close_date_for_mode(round_obj: Round, level: SeasonLevel, contest_mode: str):
    mode = (contest_mode or "").strip().lower()
    if mode == "nomination":
        return SeasonMigrationService._nomination_vote_close_date_for_level(round_obj, level)
    attr = _PARTICIPATION_END_DATE_ATTR.get(level)
    return getattr(round_obj, attr, None) if attr else None


def _level_open_date_for_mode(round_obj: Round, level: SeasonLevel, contest_mode: str):
    """Debug/metadata only -- see module docstring. Not used for any
    eligibility decision; the target month itself is the only gate."""
    mode = (contest_mode or "").strip().lower()
    if mode == "nomination":
        return SeasonMigrationService._nomination_vote_open_date_for_level(round_obj, level)
    attr = _PARTICIPATION_START_DATE_ATTR.get(level)
    return getattr(round_obj, attr, None) if attr else None


def _location_value(level: SeasonLevel, contestant: Contestant) -> Optional[str]:
    if level == SeasonLevel.CITY:
        return contestant.city
    if level == SeasonLevel.COUNTRY:
        return SeasonMigrationService._canonical_country_label(
            contestant.country or contestant.nominator_country
        )
    if level == SeasonLevel.REGIONAL:
        return (
            SeasonMigrationService.regional_pool_label_for_raw_country(
                contestant.country or contestant.nominator_country
            )
            or contestant.region
        )
    if level == SeasonLevel.CONTINENT:
        return contestant.continent
    return "Global"


def _empty_response(
    level: SeasonLevel, selected_country: str, *, target_month: Optional[date] = None,
    reason: str = "no_eligible_data",
) -> dict:
    return {
        "round_id": None,
        "round_name": None,
        "country": selected_country,
        "level": level.value,
        "target_month": target_month.isoformat() if target_month else None,
        "mixed_cohorts": False,
        "contests": [],
        "fallback_applied": False,
        "diagnostics": {
            "requested_level": level.value,
            "message": "No contestants currently satisfy the target calendar month for this level.",
            "source": "derived",
            "reason": reason,
            "target_month": target_month.isoformat() if target_month else None,
        },
    }


def public_author_name(user) -> Optional[str]:
    """Public display name for a TopHigh5 row. This payload is served to
    anonymous viewers, so it must never contain or fall back to an email."""
    if user is None:
        return None
    return user.full_name or user.username or None


def _row_dict(contest: Contest, contestant: Contestant, rank: int, ranking_row, migrated: bool) -> dict:
    author_name = public_author_name(contestant.user)
    # Authoritative original registration/entry timestamp. NOT
    # TopHigh5Result.created_at / ContestantSeason.created_at / any
    # promotion or ranking timestamp -- Contestant.registration_date is the
    # purpose-built field, set once at submission/nomination time (verified
    # against production: populated for every row, 0 nulls; matches
    # Contestant.created_at to the millisecond, confirming it is genuinely
    # stamped at row-creation/entry time, not backfilled or rewritten later
    # the way top_high5_results rows have repeatedly been proven to be).
    registered_at = contestant.registration_date
    return {
        "rank": rank,
        "migrates_next_stage": bool(migrated),
        "contestant_id": contestant.id,
        "contestant_title": contestant.title,
        "author_name": author_name,
        "city": contestant.city,
        "country": contestant.country,
        "region": contestant.region,
        "continent": contestant.continent,
        "registered_at": registered_at.isoformat() if registered_at else None,
        "stars_points": ranking_row.total_points,
        "votes_count": ranking_row.total_votes,
        "shares": ranking_row.shares,
        "likes": ranking_row.likes,
        "comments": ranking_row.comments,
        "views": ranking_row.views,
    }


def resolve_live_top_high5(
    db: Session,
    *,
    level: SeasonLevel,
    selected_country: str,
    variants: set,
    today: date,
    limit: int = 5,
) -> dict:
    """
    Derive Top High5 for one level, live, for the SINGLE calendar-derived
    target cohort month (see module docstring). Never reads or writes
    TopHigh5Result.

    Batched (no N+1): exactly one target round is resolved per call; every
    contest/contestant query below is scoped to that one round's season, so
    cost is bounded by the number of contests genuinely in that cohort, not
    by the whole system's history.
    """
    target_month = target_cohort_month(level, today)
    target_round = find_round_for_month(db, target_month)
    if target_round is None:
        return _empty_response(level, selected_country, target_month=target_month, reason="no_round_for_target_month")

    target_season = (
        db.query(ContestSeason)
        .filter(
            ContestSeason.level == level,
            ContestSeason.round_id == target_round.id,
            ContestSeason.is_deleted == False,
        )
        .first()
    )
    if target_season is None:
        return _empty_response(level, selected_country, target_month=target_month, reason="no_season_for_target_round")

    # ---- Existence-based cohort membership, scoped to the ONE target
    # season (active or not -- see module docstring), plus the
    # cohort-integrity guard: only a contestant whose own immutable
    # round_id equals the target round is trusted, regardless of how many
    # other ContestantSeason rows they may have at other rounds.
    member_rows = (
        db.query(Contestant)
        .join(ContestantSeason, ContestantSeason.contestant_id == Contestant.id)
        .options(joinedload(Contestant.user))
        .filter(
            ContestantSeason.season_id == target_season.id,
            Contestant.is_active == True,
            Contestant.is_deleted == False,
            Contestant.round_id == target_round.id,
        )
        .all()
    )

    by_contest: dict[int, list[Contestant]] = {}
    for contestant in member_rows:
        contest_id = contestant.season_id
        if contest_id is None:
            continue
        by_contest.setdefault(contest_id, []).append(contestant)

    if not by_contest:
        return _empty_response(level, selected_country, target_month=target_month, reason="no_cohort_membership_for_target_month")

    contest_ids = list(by_contest.keys())
    contests = (
        db.query(Contest)
        .options(joinedload(Contest.category))
        .filter(Contest.id.in_(contest_ids))
        .all()
    )
    contest_by_id = {c.id: c for c in contests}

    # ---- CITY is participation-only; nomination has no City stage at all.
    ranked_contest_ids = []
    for contest_id in by_contest:
        contest = contest_by_id.get(contest_id)
        if not contest:
            continue
        mode = (getattr(contest, "contest_mode", "") or "").strip().lower()
        if level == SeasonLevel.CITY and mode != "participation":
            continue
        ranked_contest_ids.append(contest_id)

    if not ranked_contest_ids:
        return _empty_response(level, selected_country, target_month=target_month, reason="no_eligible_contests_for_target_month")

    def _passes_prefilter(contest_id: int) -> bool:
        candidates = by_contest[contest_id]
        if level == SeasonLevel.COUNTRY:
            if contest_id == 17 and any(v in variants for v in {"tanzania", "tz"}):
                return False  # existing Singeli/Tanzania override, preserved
            return any(
                (c.country or c.nominator_country or "").strip().lower() in variants
                for c in candidates
            )
        if level == SeasonLevel.REGIONAL:
            selected_pool_id = SeasonMigrationService.regional_pool_id_for_raw_country(selected_country)
            if selected_pool_id is None:
                return True
            for c in candidates:
                loc = _location_value(level, c)
                if loc and SeasonMigrationService.regional_pool_id_for_region_label(loc) == selected_pool_id:
                    return True
            return False
        return True

    ranked_contest_ids = [cid for cid in ranked_contest_ids if _passes_prefilter(cid)]
    if not ranked_contest_ids:
        return _empty_response(level, selected_country, target_month=target_month, reason="no_jurisdiction_match")

    nxt = next_level(level)
    next_season = None
    if nxt is not None:
        next_season = (
            db.query(ContestSeason)
            .filter(
                ContestSeason.level == nxt,
                ContestSeason.round_id == target_round.id,
                ContestSeason.is_deleted == False,
            )
            .first()
        )

    per_group_selected: dict[tuple[int, str], list[Contestant]] = {}
    per_group_rank: dict[tuple[int, str], dict] = {}
    all_selected_ids: list[int] = []

    for contest_id in ranked_contest_ids:
        contest = contest_by_id[contest_id]
        candidates = by_contest[contest_id]
        candidate_ids = [c.id for c in candidates if c.id is not None]
        if not candidate_ids:
            continue

        bucket_key = SeasonMigrationService._top_high5_bucket_key_for_contest(contest)
        ranking_rows = aggregate_rankings(
            db,
            season_ids=[target_season.id],
            contestant_ids=candidate_ids,
            contest_id=contest_id,
            bucket_key=bucket_key,
            # Documented, already-shipped zero-vote-inclusion display rule
            # (display-only, never a promotion signal) -- unchanged.
            require_votes=False,
        )
        rank_by_id = {row.contestant_id: row for row in ranking_rows}

        by_jurisdiction: dict[str, list[Contestant]] = {}
        for c in candidates:
            if c.id not in rank_by_id:
                continue
            loc = _location_value(level, c)
            if not loc:
                continue
            by_jurisdiction.setdefault(loc, []).append(c)

        if level == SeasonLevel.COUNTRY:
            by_jurisdiction = {k: v for k, v in by_jurisdiction.items() if k.strip().lower() in variants}
        elif level == SeasonLevel.REGIONAL:
            selected_pool_id = SeasonMigrationService.regional_pool_id_for_raw_country(selected_country)
            if selected_pool_id is not None:
                by_jurisdiction = {
                    k: v for k, v in by_jurisdiction.items()
                    if SeasonMigrationService.regional_pool_id_for_region_label(k) == selected_pool_id
                }

        for jurisdiction, members in by_jurisdiction.items():
            members.sort(key=lambda c: rank_by_id[c.id].rank)
            members = dedupe_contestants_by_nominator(
                members,
                points_by_contestant={cid: row.total_points for cid, row in rank_by_id.items()},
            )
            top = members[:limit]
            if not top:
                continue
            key = (contest_id, jurisdiction)
            per_group_selected[key] = top
            per_group_rank[key] = rank_by_id
            all_selected_ids.extend(c.id for c in top)

    if not per_group_selected:
        return _empty_response(level, selected_country, target_month=target_month, reason="no_ranked_contestants")

    # ---- Batch "migrated" flag: is this contestant CURRENTLY (present
    # tense -- a legitimate use of is_active) an active member of the NEXT
    # level's season for the SAME target round? Unrelated to historical
    # proof; this describes right-now state, not reconstructing the past.
    migrated_ids: set = set()
    if next_season is not None:
        migrated_rows = (
            db.query(ContestantSeason.contestant_id)
            .filter(
                ContestantSeason.season_id == next_season.id,
                ContestantSeason.is_active == True,
                ContestantSeason.contestant_id.in_(all_selected_ids),
            )
            .all()
        )
        migrated_ids = {r[0] for r in migrated_rows}

    ranking_scope = (
        "global" if level == SeasonLevel.GLOBAL
        else "country_group" if level == SeasonLevel.COUNTRY
        else "regional_pool" if level == SeasonLevel.REGIONAL
        else "continent_in_country" if level == SeasonLevel.CONTINENT
        else "city_group"
    )
    cohort_month_str = target_month.isoformat()

    contests_out = []
    for (contest_id, jurisdiction), top in per_group_selected.items():
        contest = contest_by_id[contest_id]
        rank_by_id = per_group_rank[(contest_id, jurisdiction)]
        rows = [
            _row_dict(contest, c, idx, rank_by_id[c.id], c.id in migrated_ids)
            for idx, c in enumerate(top, start=1)
        ]
        mode = (getattr(contest, "contest_mode", "") or "").strip().lower()
        stage_open = _level_open_date_for_mode(target_round, level, mode)
        stage_close = _level_close_date_for_mode(target_round, level, mode)
        contests_out.append({
            "contest_id": contest.id,
            "contest_name": contest.name,
            "category_id": contest.category_id,
            "category_name": (contest.category.name if contest.category else None),
            "from_level": level.value,
            "to_level": nxt.value if nxt else None,
            "country_group": jurisdiction,
            "ranking_scope": ranking_scope,
            "promotion_limit": limit,
            "rows": rows,
            "round_id": target_round.id,
            "round_name": target_round.name,
            "contest_mode": mode,
            # Debug/verification metadata: every card in this response
            # shares the same cohort_round_id/cohort_month by construction
            # (single target round for the whole level) -- stage_* remains
            # per-mode/informational (when THIS level's own voting window
            # runs for that shared cohort), never used to select the round.
            "cohort_round_id": target_round.id,
            "cohort_round_name": target_round.name,
            "cohort_month": cohort_month_str,
            "stage_month": stage_close.replace(day=1).isoformat() if stage_close else None,
            "stage_open_date": stage_open.isoformat() if stage_open else None,
            "stage_close_date": stage_close.isoformat() if stage_close else None,
        })
    contests_out.sort(key=lambda c: (c["country_group"] or "").lower())

    return {
        "round_id": target_round.id,
        "round_name": target_round.name,
        "country": selected_country,
        "level": level.value,
        "target_month": cohort_month_str,
        # Always False now: every card in a response shares the single
        # calendar-derived target round. Kept (rather than removed) so the
        # frontend's existing mixed_cohorts branch degrades harmlessly.
        "mixed_cohorts": False,
        "contests": contests_out,
        "fallback_applied": False,
        "diagnostics": {
            "round_id": target_round.id,
            "round_name": target_round.name,
            "country": selected_country,
            "requested_level": level.value,
            "source": "derived",
            "target_month": cohort_month_str,
            "distinct_rounds_represented": [target_round.id],
        },
    }
