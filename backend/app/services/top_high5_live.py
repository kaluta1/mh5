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
WHAT THIS MODULE DOES INSTEAD
============================================================================
For each level (CITY / COUNTRY / REGIONAL / CONTINENT / GLOBAL), this
derives "who is the current Top 5" LIVE, straight from the same
authoritative sources `promote_to_next_level` itself reads to decide who
gets promoted:

  CURRENT DATE
      -> CONTEST MODE (participation / nomination; own lifecycle calendar)
      -> per-contest COHORT/ROUND (each contest's own freshest fully
         completed round at this level -- never in-progress)
      -> ELIGIBLE CONTESTANTS for that (contest, round, level): existence
         of a ContestantSeason row (active OR inactive -- see "why not
         is_active" below) in this level's own ContestSeason for this
         round, whose Contestant.round_id matches the round (cohort
         integrity guard, same defense-in-depth already used by
         `_contestants_for_contest_in_season` / `get_top_contestants_by_location`)
      -> `aggregate_rankings` (the one authoritative ranking/tie-break
         service every promotion and every existing Top High5 freeze
         already uses) for the real vote/points/engagement data
      -> grouped by this level's own jurisdiction field, deduped by
         nominator (`dedupe_contestants_by_nominator`), Top N

`TopHigh5Result` is never read or written here. It remains exactly what it
was for explicit-round / historical / audit purposes (see
`_get_top_high5_single_round` for an explicit `?round_id=`), just no longer
in the path of the *default* display.

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
ContestantSeason row at this exact level for this exact round (not
"currently active"), combined with the contestant's own immutable
`round_id` matching that round (cohort integrity -- prevents a different
round's contestant riding in on a shared/pooled season), combined with the
lifecycle's own mode-aware close date (prevents showing an in-progress
stage). No single field is trusted alone.
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

# PARTICIPATION's own calendar close date column for each level (City=M+1
# .. Global=M+5, see generate_monthly_rounds.py). Nomination never uses
# these columns -- see _level_close_date_for_mode.
_PARTICIPATION_END_DATE_ATTR = {
    SeasonLevel.CITY: "city_season_end_date",
    SeasonLevel.COUNTRY: "country_season_end_date",
    SeasonLevel.REGIONAL: "regional_end_date",
    SeasonLevel.CONTINENT: "continental_end_date",
    SeasonLevel.GLOBAL: "global_end_date",
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


def _level_close_date_for_mode(round_obj: Round, level: SeasonLevel, contest_mode: str):
    mode = (contest_mode or "").strip().lower()
    if mode == "nomination":
        return SeasonMigrationService._nomination_vote_close_date_for_level(round_obj, level)
    attr = _PARTICIPATION_END_DATE_ATTR.get(level)
    return getattr(round_obj, attr, None) if attr else None


def _stage_fully_completed(round_obj: Round, level: SeasonLevel, contest_mode: str, today: date) -> bool:
    """
    True only when this (round, level) voting window has genuinely closed
    for this contest's mode -- never an in-progress or future stage. A
    CANCELLED round is never eligible regardless of its date columns (same
    guard as the frozen-result resolver). Nomination has no CITY offset at
    all (see _nomination_vote_close_date_for_level), so a nomination
    contest can only reach this level's date branch via the COMPLETED-status
    fallback below, which nomination's own CITY-less lifecycle never
    satisfies for a CITY level in the first place -- in practice enforced
    upstream anyway (see resolve_live_top_high5's explicit mode check).
    """
    if round_obj.status == RoundStatus.CANCELLED:
        return False
    close = _level_close_date_for_mode(round_obj, level, contest_mode)
    if close is not None:
        return close <= today
    return round_obj.status == RoundStatus.COMPLETED


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


def _empty_response(level: SeasonLevel, selected_country: str, *, reason: str = "no_eligible_data") -> dict:
    return {
        "round_id": None,
        "round_name": None,
        "country": selected_country,
        "level": level.value,
        "contests": [],
        "fallback_applied": False,
        "diagnostics": {
            "requested_level": level.value,
            "message": "No contestants currently satisfy the lifecycle/ranking conditions for this level.",
            "source": "derived",
            "reason": reason,
        },
    }


def _row_dict(contest: Contest, contestant: Contestant, rank: int, ranking_row, migrated: bool) -> dict:
    author_name = None
    author_email = None
    user = contestant.user
    if user is not None:
        author_name = user.full_name or user.username or user.email
        author_email = user.email
    return {
        "rank": rank,
        "migrates_next_stage": bool(migrated),
        "contestant_id": contestant.id,
        "contestant_title": contestant.title,
        "author_name": author_name,
        "author_email": author_email,
        "city": contestant.city,
        "country": contestant.country,
        "region": contestant.region,
        "continent": contestant.continent,
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
    Derive Top High5 for one level, live, from current authoritative
    lifecycle + membership + voting data. Never reads or writes
    TopHigh5Result. See module docstring for the full rationale.

    Batched (no N+1): eligibility/cohort data is fetched in a small,
    bounded number of queries covering every round at this level at once;
    only contests that survive every filter (completed stage + real cohort
    + jurisdiction match) get a final per-contest ranking query.
    """
    # ---- Batch: every ContestSeason at this level, across all rounds.
    level_seasons = (
        db.query(ContestSeason)
        .options(joinedload(ContestSeason.round))
        .filter(ContestSeason.level == level, ContestSeason.is_deleted == False)
        .all()
    )
    season_by_round: dict[int, ContestSeason] = {
        s.round_id: s for s in level_seasons if s.round_id is not None
    }
    if not season_by_round:
        return _empty_response(level, selected_country, reason="no_seasons_at_level")

    season_ids = [s.id for s in level_seasons if s.round_id is not None]
    season_round_id = {s.id: s.round_id for s in level_seasons}

    # ---- Batch: existence-based cohort membership across ALL those rounds
    # in one query (active or not -- see module docstring).
    member_rows = (
        db.query(ContestantSeason.season_id, Contestant)
        .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
        .options(joinedload(Contestant.user))
        .filter(
            ContestantSeason.season_id.in_(season_ids),
            Contestant.is_active == True,
            Contestant.is_deleted == False,
        )
        .all()
    )

    by_contest: dict[int, dict[int, list[Contestant]]] = {}
    for season_id, contestant in member_rows:
        round_id = season_round_id.get(season_id)
        # Cohort-integrity guard: only trust a membership row whose season
        # and the contestant's own fixed round agree (defense-in-depth
        # already used by _contestants_for_contest_in_season /
        # get_top_contestants_by_location) -- prevents a different round's
        # contestant riding in on a shared/pooled season.
        if round_id is None or contestant.round_id != round_id:
            continue
        contest_id = contestant.season_id
        if contest_id is None:
            continue
        by_contest.setdefault(contest_id, {}).setdefault(round_id, []).append(contestant)

    if not by_contest:
        return _empty_response(level, selected_country, reason="no_cohort_membership")

    # ---- Batch: contest_mode / category for every contest involved.
    contest_ids = list(by_contest.keys())
    contests = (
        db.query(Contest)
        .options(joinedload(Contest.category))
        .filter(Contest.id.in_(contest_ids))
        .all()
    )
    contest_by_id = {c.id: c for c in contests}

    eligibility_cache: dict[tuple, bool] = {}

    def _eligible(round_id: int, mode: str) -> bool:
        key = (round_id, mode)
        cached = eligibility_cache.get(key)
        if cached is not None:
            return cached
        season = season_by_round.get(round_id)
        round_obj = season.round if season else None
        result = bool(round_obj) and _stage_fully_completed(round_obj, level, mode, today)
        eligibility_cache[key] = result
        return result

    # ---- Each contest picks its own freshest fully-completed round.
    chosen: dict[int, int] = {}
    for contest_id, rounds_map in by_contest.items():
        contest = contest_by_id.get(contest_id)
        if not contest:
            continue
        mode = (getattr(contest, "contest_mode", "") or "").strip().lower()
        if level == SeasonLevel.CITY and mode != "participation":
            # Nomination has no City stage (see _nomination_*_for_level,
            # which never defines a CITY offset) -- explicit guard here as
            # well, not relying only on the absence of CITY seasons upstream.
            continue
        eligible_rounds = [r for r in rounds_map if _eligible(r, mode)]
        if not eligible_rounds:
            continue
        chosen[contest_id] = max(eligible_rounds)

    if not chosen:
        return _empty_response(level, selected_country, reason="no_fully_completed_stage")

    def _passes_prefilter(contest_id: int, round_id: int) -> bool:
        candidates = by_contest[contest_id][round_id]
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

    ranked_contest_ids = [cid for cid, rid in chosen.items() if _passes_prefilter(cid, rid)]
    if not ranked_contest_ids:
        return _empty_response(level, selected_country, reason="no_jurisdiction_match")

    nxt = next_level(level)
    next_season_by_round: dict[int, ContestSeason] = {}
    if nxt is not None:
        next_seasons = (
            db.query(ContestSeason)
            .filter(ContestSeason.level == nxt, ContestSeason.is_deleted == False,
                     ContestSeason.round_id.in_(set(chosen.values())))
            .all()
        )
        next_season_by_round = {s.round_id: s for s in next_seasons}

    groups: dict[tuple[int, str], list] = {}
    rounds_represented: set[int] = set()
    all_selected_ids: list[int] = []
    per_group_selected: dict[tuple[int, str], list[Contestant]] = {}
    per_group_rank: dict[tuple[int, str], dict] = {}

    for contest_id in ranked_contest_ids:
        round_id = chosen[contest_id]
        rounds_represented.add(round_id)
        contest = contest_by_id[contest_id]
        candidates = by_contest[contest_id][round_id]
        candidate_ids = [c.id for c in candidates if c.id is not None]
        if not candidate_ids:
            continue

        season = season_by_round[round_id]
        bucket_key = SeasonMigrationService._top_high5_bucket_key_for_contest(contest)
        ranking_rows = aggregate_rankings(
            db,
            season_ids=[season.id],
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
        return _empty_response(level, selected_country, reason="no_ranked_contestants")

    # ---- Batch "migrated" flag: is this contestant CURRENTLY (present
    # tense -- a legitimate use of is_active) an active member of the NEXT
    # level's season for the SAME round? Unrelated to historical proof; this
    # is describing right-now state, not reconstructing the past.
    migrated_ids: set = set()
    if nxt is not None and next_season_by_round:
        migrated_rows = (
            db.query(ContestantSeason.contestant_id)
            .filter(
                ContestantSeason.season_id.in_([s.id for s in next_season_by_round.values()]),
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

    contests_out = []
    for (contest_id, jurisdiction), top in per_group_selected.items():
        contest = contest_by_id[contest_id]
        round_id = chosen[contest_id]
        round_obj = season_by_round[round_id].round
        rank_by_id = per_group_rank[(contest_id, jurisdiction)]
        rows = [
            _row_dict(contest, c, idx, rank_by_id[c.id], c.id in migrated_ids)
            for idx, c in enumerate(top, start=1)
        ]
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
            "round_id": round_id,
            "round_name": round_obj.name if round_obj else None,
            "contest_mode": (getattr(contest, "contest_mode", "") or "").strip().lower(),
        })
    contests_out.sort(key=lambda c: (c["country_group"] or "").lower())

    rounds_used = sorted(rounds_represented, reverse=True)
    top_round = season_by_round[rounds_used[0]].round if rounds_used else None

    return {
        "round_id": top_round.id if top_round else None,
        "round_name": top_round.name if top_round else None,
        "country": selected_country,
        "level": level.value,
        "contests": contests_out,
        "fallback_applied": False,
        "diagnostics": {
            "round_id": top_round.id if top_round else None,
            "round_name": top_round.name if top_round else None,
            "country": selected_country,
            "requested_level": level.value,
            "source": "derived",
            "distinct_rounds_represented": rounds_used,
        },
    }
