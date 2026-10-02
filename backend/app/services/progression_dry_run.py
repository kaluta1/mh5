"""READ-ONLY progression dry-run.

Answers one question without changing anything: "under the corrected ranking
and progression rules, who would advance from this stage?"

It uses the very selection promotion uses
(``SeasonMigrationService.select_progression_winners``), so what it reports is
what a promotion would do. It never calls a function that writes: no season is
created, no membership is activated or deactivated, no qualification flag, no
Top High5 row, no safety hold, no vote is touched. Every entry point checks
that the session holds no pending change before returning.

Two things promotion does first are deliberately NOT simulated because they
write: syncing cohort entries into the source season and repairing missing
source memberships. Entries those steps would add are counted in
``not_yet_in_source_season`` so the gap is visible.

A hop is evaluated on the state the database is in now. Once a cohort really
advances, its next hop depends on the votes cast in the new stage, so chained
hops are not predicted.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from app.models.contest import Contest
from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.round import Round, RoundStatus, round_contests
from app.services import participation_safety
from app.services.contestant_contest_resolution import LEGACY_COLLISION_CODES, explain_contest_resolution
from app.services.season_migration import SeasonMigrationService

NEXT_LEVEL = {
    SeasonLevel.CITY: SeasonLevel.COUNTRY,
    SeasonLevel.COUNTRY: SeasonLevel.REGIONAL,
    SeasonLevel.REGIONAL: SeasonLevel.CONTINENT,
    SeasonLevel.CONTINENT: SeasonLevel.GLOBAL,
}


class DryRunWroteSomething(RuntimeError):
    """The dry-run left a pending change in the session. Never expected."""


def _assert_untouched(db: Session) -> None:
    if db.new or db.dirty or db.deleted:
        db.rollback()
        raise DryRunWroteSomething("progression dry-run produced pending database changes")


def _level(value) -> SeasonLevel:
    return value if isinstance(value, SeasonLevel) else SeasonLevel(str(value).lower())


def _mode(contest: Contest) -> str:
    return (getattr(contest, "contest_mode", "") or "").strip().lower()


def simulate_hop(
    db: Session,
    *,
    contest: Contest,
    from_season: ContestSeason,
    limit: int = 5,
) -> dict:
    """What promoting ``contest`` out of ``from_season`` would do. Read-only."""
    from_level = _level(from_season.level)
    to_level = NEXT_LEVEL.get(from_level)
    round_obj: Optional[Round] = from_season.round
    report: dict = {
        "round_id": from_season.round_id,
        "round_name": getattr(round_obj, "name", None),
        "contest_id": contest.id,
        "contest_name": contest.name,
        "category_id": contest.category_id,
        "contest_mode": _mode(contest),
        "source_season_id": from_season.id,
        "source_stage": from_level.value,
        "destination_stage": to_level.value if to_level else None,
        "entries": [],
        "unplaced": [],
        "excluded_legacy_entries": [],
    }
    if to_level is None:
        report["error"] = "GLOBAL has no next stage"
        return report

    selection = SeasonMigrationService.select_progression_winners(
        db,
        contest=contest,
        from_season=from_season,
        from_level=from_level,
        to_level=to_level,
        limit=limit,
    )
    pool_ids = {int(c.id) for c in selection.pool}
    winner_ids = {int(c.id) for c in selection.winners}
    unplaced_reason = {int(item["contestant_id"]): item["reason"] for item in selection.unplaced}

    # Rank inside the scope the hop competes in: the group for every hop,
    # the contest's whole continental pool for Continental -> Global.
    rank_in_group: Dict[int, int] = {}
    if to_level == SeasonLevel.GLOBAL:
        from app.services import progression_ranking

        for position, contestant in enumerate(
            progression_ranking.rank_group(selection.pool, selection.scores), start=1
        ):
            rank_in_group[int(contestant.id)] = position
    else:
        for _group, ranked in selection.ranked_groups.items():
            for position, contestant in enumerate(ranked, start=1):
                rank_in_group[int(contestant.id)] = position

    destination = (
        db.query(ContestSeason)
        .join(ContestSeasonLink, ContestSeasonLink.season_id == ContestSeason.id)
        .filter(
            ContestSeason.level == to_level,
            ContestSeason.round_id == from_season.round_id,
            ContestSeason.is_deleted == False,  # noqa: E712
            ContestSeasonLink.contest_id == contest.id,
        )
        .order_by(ContestSeason.id.asc())
        .first()
    ) or (
        db.query(ContestSeason)
        .filter(
            ContestSeason.level == to_level,
            ContestSeason.round_id == from_season.round_id,
            ContestSeason.is_deleted == False,  # noqa: E712
        )
        .order_by(ContestSeason.id.asc())
        .first()
    )
    report["destination_season_id"] = destination.id if destination is not None else None
    report["destination_season_would_be_created"] = destination is None

    users = {}
    pool = (
        db.query(Contestant)
        .options(joinedload(Contestant.user))
        .filter(Contestant.id.in_(pool_ids or {-1}))
        .all()
    )
    for contestant in pool:
        users[int(contestant.id)] = contestant.user

    group_of = {int(cid): group for cid, group in selection.group_of.items()}

    for contestant in sorted(
        selection.pool,
        key=lambda c: (str(group_of.get(int(c.id), "~")), rank_in_group.get(int(c.id), 10**9), int(c.id)),
    ):
        cid = int(contestant.id)
        score = selection.scores[cid]
        rank = rank_in_group.get(cid)
        qualifies = cid in winner_ids
        safety = participation_safety.can_progress(db, contestant, reevaluate=False)
        if qualifies:
            outcome = "ADVANCES" if safety.eligible else "QUALIFIES_BUT_SAFETY_HELD"
        elif cid in unplaced_reason:
            outcome = f"UNPLACED:{unplaced_reason[cid]}"
        elif rank is None:
            outcome = "NOT_RANKED:SAME_NOMINATOR_HAS_A_BETTER_ENTRY"
        else:
            outcome = "OUTSIDE_TOP_%d" % limit
        user = users.get(cid)
        report["entries"].append({
            "contestant_id": cid,
            "entry_title": contestant.title,
            "nominator_user_id": contestant.user_id,
            "nominator_username": getattr(user, "username", None),
            "group": group_of.get(cid),
            "previous_stage_points": score.carried_points,
            "current_stage_points": score.stage_points,
            "cumulative_points": score.cumulative_points,
            "points_by_stage": dict(score.points_by_level),
            "shares": score.shares,
            "likes": score.likes,
            "comments": score.comments,
            "views": score.views,
            "submitted_at": score.submitted_at.isoformat() if score.submitted_at else None,
            "rank": rank,
            "qualifies": qualifies,
            "outcome": outcome,
            "safety_eligible": bool(safety.eligible),
            "safety_reason_codes": list(safety.reasons or ()),
            "destination_stage": to_level.value if qualifies else None,
            "regional_pool": (
                selection.destination_label.get(cid)
                or SeasonMigrationService.regional_pool_label_for_raw_country(
                    contestant.country or contestant.nominator_country
                )
            ),
            "ranking_scope": "worldwide" if to_level == SeasonLevel.GLOBAL else selection.location_field,
            "contest_resolution": explain_contest_resolution(db, contestant, contest.id).code,
        })

    report["unplaced"] = list(selection.unplaced)

    # Cohort entries that name this contest the legacy way but are not in the
    # pool: show why (not resolvable, not a member yet, inactive, ...).
    legacy_rows = (
        db.query(Contestant)
        .filter(
            Contestant.round_id == from_season.round_id,
            Contestant.contest_id.is_(None),
            Contestant.season_id == contest.id,
            Contestant.is_deleted == False,  # noqa: E712
        )
        .order_by(Contestant.id.asc())
        .all()
    )
    member_ids = {
        int(row[0])
        for row in db.query(ContestantSeason.contestant_id)
        .filter(ContestantSeason.season_id == from_season.id, ContestantSeason.is_active == True)  # noqa: E712
        .all()
    }
    for contestant in legacy_rows:
        if int(contestant.id) in pool_ids:
            continue
        resolution = explain_contest_resolution(db, contestant, contest.id)
        report["excluded_legacy_entries"].append({
            "contestant_id": contestant.id,
            "entry_title": contestant.title,
            "contest_resolution": resolution.code,
            "resolved_to_this_contest": resolution.belongs,
            "active_member_of_source_season": int(contestant.id) in member_ids,
            "is_active": bool(contestant.is_active),
        })

    # Entries the (writing) pre-promotion sync would still add to the source season.
    cohort_ids = {
        int(row[0])
        for row in db.query(Contestant.id)
        .filter(
            Contestant.season_id == contest.id,
            Contestant.round_id == from_season.round_id,
            Contestant.is_active == True,  # noqa: E712
            Contestant.is_deleted == False,  # noqa: E712
            SeasonMigrationService.origin_matches_mode_clause(_mode(contest)),
        )
        .all()
    }
    any_membership = {
        int(row[0])
        for row in db.query(ContestantSeason.contestant_id)
        .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
        .filter(
            ContestSeason.round_id == from_season.round_id,
            ContestantSeason.is_active == True,  # noqa: E712
            ContestantSeason.contestant_id.in_(cohort_ids or {-1}),
        )
        .all()
    }
    report["not_yet_in_source_season"] = sorted(cohort_ids - any_membership)

    # Top High5 rows already frozen for this stage are write-once: promotion
    # would keep them. Report when they no longer match the corrected ranking.
    frozen = (
        db.query(TopHigh5Result)
        .filter(
            TopHigh5Result.contest_id == contest.id,
            TopHigh5Result.level == from_level,
            TopHigh5Result.round_id == from_season.round_id,
        )
        .order_by(TopHigh5Result.jurisdiction.asc(), TopHigh5Result.rank.asc())
        .all()
    )
    frozen_by_group: Dict[str, List[int]] = {}
    frozen_rows_by_group: Dict[str, List[TopHigh5Result]] = {}
    for row in frozen:
        frozen_by_group.setdefault(row.jurisdiction, []).append(int(row.contestant_id))
        frozen_rows_by_group.setdefault(row.jurisdiction, []).append(row)
    corrected_by_group = {group: [int(c.id) for c in top] for group, top in selection.freeze_groups}

    # Row-level reconciliation: the frozen row at each rank next to what the
    # corrected ranking puts there. Nothing is changed.
    reconciliation = []
    winner_id_set = {int(c.id) for c in selection.winners}
    for group in sorted(set(frozen_rows_by_group) | set(corrected_by_group), key=str):
        existing = {int(r.rank): r for r in frozen_rows_by_group.get(group, [])}
        corrected = corrected_by_group.get(group, [])
        for rank in sorted(set(existing) | set(range(1, len(corrected) + 1))):
            old = existing.get(rank)
            new_id = corrected[rank - 1] if rank <= len(corrected) else None
            new_score = selection.scores.get(new_id) if new_id is not None else None
            reasons = []
            if old is None:
                reasons.append("NO_FROZEN_ROW")
            elif new_id is None:
                reasons.append("FROZEN_ENTRY_NOT_IN_CORRECTED_TOP5")
            else:
                if int(old.contestant_id) != new_id:
                    reasons.append(
                        "DIFFERENT_ENTRY_AT_RANK"
                        if int(old.contestant_id) in corrected
                        else "FROZEN_ENTRY_NOT_IN_CORRECTED_TOP5"
                    )
                elif int(old.total_points or 0) != int(new_score.cumulative_points):
                    reasons.append("POINTS_DIFFER_STAGE_ONLY_VS_CUMULATIVE")
                elif (old.shares, old.likes, old.comments, old.views) != (
                    new_score.shares, new_score.likes, new_score.comments, new_score.views
                ):
                    reasons.append("ENGAGEMENT_VALUES_DIFFER")
                if bool(old.migrated) != (int(old.contestant_id) in winner_id_set):
                    reasons.append("MIGRATED_FLAG_WOULD_BE_STALE_AFTER_PROMOTION")
            reconciliation.append({
                "round_id": from_season.round_id,
                "stage": from_level.value,
                "contest_id": contest.id,
                "contest_name": contest.name,
                "group": group,
                "rank": rank,
                "existing_row_id": old.id if old is not None else None,
                "existing_contestant_id": int(old.contestant_id) if old is not None else None,
                "existing_points": int(old.total_points or 0) if old is not None else None,
                "existing_migrated": bool(old.migrated) if old is not None else None,
                "corrected_contestant_id": new_id,
                "corrected_cumulative_points": new_score.cumulative_points if new_score is not None else None,
                "corrected_would_advance": (new_id in winner_id_set) if new_id is not None else None,
                "needs_reconciliation": bool(reasons) and old is not None,
                "reason": ";".join(reasons) or "MATCHES",
            })
    report["top_high5_reconciliation"] = reconciliation
    report["top_high5"] = {
        "already_frozen_rows": len(frozen),
        "groups_frozen_and_matching": sorted(
            g for g, ids in frozen_by_group.items() if corrected_by_group.get(g) == ids
        ),
        "groups_frozen_but_different": sorted(
            g for g, ids in frozen_by_group.items() if corrected_by_group.get(g) != ids
        ),
        "groups_not_frozen_yet": sorted(g for g in corrected_by_group if g not in frozen_by_group),
    }

    report["summary"] = {
        "pool": len(selection.pool),
        "source_contestants": len(selection.pool) + len(report["excluded_legacy_entries"]),
        "eligible": len(selection.pool),
        "blocked_by_safety": sum(1 for e in report["entries"] if e["outcome"] == "QUALIFIES_BUT_SAFETY_HELD"),
        "blocked_by_unresolved_legacy_ownership": sum(
            1 for e in report["excluded_legacy_entries"] if not e["resolved_to_this_contest"]
        ),
        "blocked_by_missing_regional_pool": sum(
            1 for item in selection.unplaced if item["reason"] == "NO_REGIONAL_POOL_CONFIGURED"
        ),
        "frozen_rows_needing_reconciliation": sum(1 for r in reconciliation if r["needs_reconciliation"]),
        "groups": len(selection.ranked_groups),
        "would_advance": sum(1 for e in report["entries"] if e["outcome"] == "ADVANCES"),
        "qualify_but_safety_held": sum(1 for e in report["entries"] if e["outcome"] == "QUALIFIES_BUT_SAFETY_HELD"),
        "unplaced": len(selection.unplaced),
        "excluded_legacy_entries": len(report["excluded_legacy_entries"]),
        "legacy_entries_resolved_by_round_evidence": sum(
            1 for e in report["entries"] if e["contest_resolution"] in LEGACY_COLLISION_CODES
        ),
    }
    _assert_untouched(db)
    return report


def _effective_country_season_id(db: Session, contest_id: int, round_id: int) -> Optional[int]:
    """Read-only twin of ensure_active_country_round_link_for_nomination's lookup."""
    row = (
        db.query(ContestSeasonLink.season_id)
        .join(ContestSeason, ContestSeasonLink.season_id == ContestSeason.id)
        .filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeason.round_id == round_id,
            ContestSeason.level == SeasonLevel.COUNTRY,
            ContestSeason.is_deleted == False,  # noqa: E712
        )
        .order_by(
            ContestSeasonLink.is_active.desc(),
            ContestSeasonLink.linked_at.desc(),
            ContestSeasonLink.id.desc(),
        )
        .first()
    )
    return int(row[0]) if row else None


def due_transitions(
    db: Session,
    *,
    today: Optional[date] = None,
    round_ids: Optional[Iterable[int]] = None,
    contest_ids: Optional[Iterable[int]] = None,
) -> List[tuple]:
    """(contest, source season) pairs the scheduler would try to promote on
    ``today``, found with the scheduler's own predicates. Read-only."""
    from app.services.contest_category_integrity import filter_contest_ids_one_per_category

    today = today or date.today()
    wanted_rounds = {int(v) for v in round_ids} if round_ids else None
    wanted_contests = {int(v) for v in contest_ids} if contest_ids else None

    seasons = (
        db.query(ContestSeason)
        .filter(and_(ContestSeason.is_deleted == False, ContestSeason.round_id.isnot(None)))  # noqa: E712
        .order_by(ContestSeason.id.desc())
        .all()
    )
    found: List[tuple] = []
    for season in seasons:
        round_obj = season.round
        if round_obj is None or round_obj.status == RoundStatus.CANCELLED:
            continue
        if wanted_rounds is not None and int(round_obj.id) not in wanted_rounds:
            continue
        level = _level(season.level)
        next_level = NEXT_LEVEL.get(level)
        if next_level is None:
            continue

        if level == SeasonLevel.COUNTRY:
            candidates: List[int] = []
            rows = db.execute(
                select(round_contests.c.contest_id).where(round_contests.c.round_id == round_obj.id)
            ).fetchall()
            for cid in dict.fromkeys(row[0] for row in rows):
                contest = db.query(Contest).filter(Contest.id == cid).first()
                if contest is None or _mode(contest) != "nomination":
                    continue
                if not SeasonMigrationService._promotion_due_for_contest(
                    round_obj, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, "nomination", today
                ):
                    continue
                if SeasonMigrationService.contest_has_active_higher_level_link(
                    db, cid, round_obj.id, SeasonLevel.COUNTRY
                ):
                    continue
                if _effective_country_season_id(db, cid, round_obj.id) != season.id:
                    continue
                candidates.append(int(cid))
            candidates = filter_contest_ids_one_per_category(db, candidates)
            participation = (
                db.query(ContestSeasonLink.contest_id)
                .join(Contest, Contest.id == ContestSeasonLink.contest_id)
                .filter(ContestSeasonLink.season_id == season.id, ContestSeasonLink.is_active == True)  # noqa: E712
                .all()
            )
            for (cid,) in participation:
                contest = db.query(Contest).filter(Contest.id == cid).first()
                if contest is not None and _mode(contest) == "participation":
                    candidates.append(int(cid))
            candidate_ids = sorted(set(candidates))
        else:
            candidate_ids = [
                int(row[0])
                for row in db.query(ContestSeasonLink.contest_id)
                .filter(ContestSeasonLink.season_id == season.id, ContestSeasonLink.is_active == True)  # noqa: E712
                .order_by(ContestSeasonLink.contest_id.asc())
                .all()
            ]

        for cid in candidate_ids:
            if wanted_contests is not None and cid not in wanted_contests:
                continue
            contest = db.query(Contest).filter(Contest.id == cid).first()
            if contest is None:
                continue
            if not SeasonMigrationService._promotion_due_for_contest(
                round_obj, level, next_level, _mode(contest), today
            ):
                continue
            already_there = (
                db.query(ContestSeasonLink.id)
                .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                .filter(
                    ContestSeasonLink.contest_id == cid,
                    ContestSeasonLink.is_active == True,  # noqa: E712
                    ContestSeason.round_id == round_obj.id,
                    ContestSeason.level == next_level,
                    ContestSeason.is_deleted == False,  # noqa: E712
                )
                .first()
            )
            if already_there:
                continue
            found.append((contest, season))
    _assert_untouched(db)
    return found


def simulate_due_progressions(
    db: Session,
    *,
    today: Optional[date] = None,
    round_ids: Optional[Iterable[int]] = None,
    contest_ids: Optional[Iterable[int]] = None,
    include_empty: bool = False,
    limit: int = 5,
) -> dict:
    """Dry-run every transition that is due on ``today``. Read-only.

    ``include_empty`` also lists due transitions with no candidate at all
    (contest/rounds nobody entered); they are only counted by default.
    """
    today = today or date.today()
    hops = []
    empty = 0
    for contest, season in due_transitions(db, today=today, round_ids=round_ids, contest_ids=contest_ids):
        hop = simulate_hop(db, contest=contest, from_season=season, limit=limit)
        if not hop["entries"] and not hop["excluded_legacy_entries"] and not include_empty:
            empty += 1
            continue
        hops.append(hop)
    hops.sort(key=lambda h: (h["round_id"], h["source_stage"], h["contest_id"]))
    totals = {
        "as_of": today.isoformat(),
        "due_transitions_with_entries": len(hops),
        "due_transitions_without_any_entry": empty,
        "would_advance": sum(h["summary"]["would_advance"] for h in hops),
        "qualify_but_safety_held": sum(h["summary"]["qualify_but_safety_held"] for h in hops),
        "unplaced": sum(h["summary"]["unplaced"] for h in hops),
        "legacy_entries_resolved_by_round_evidence": sum(
            h["summary"]["legacy_entries_resolved_by_round_evidence"] for h in hops
        ),
        "excluded_legacy_entries": sum(h["summary"]["excluded_legacy_entries"] for h in hops),
    }
    _assert_untouched(db)
    return {"totals": totals, "transitions": hops}


# ---------------------------------------------------------------------------
# GLOBAL finalization that is due (it freezes Top High5 rows when it runs)
# ---------------------------------------------------------------------------

def pending_global_finalizations(
    db: Session,
    *,
    today: Optional[date] = None,
    round_ids: Optional[Iterable[int]] = None,
    include_historical: bool = False,
) -> List[dict]:
    """GLOBAL stages whose voting is over and whose Top High5 is not frozen
    yet. Read-only.

    Default: exactly what the automatic scheduler would freeze, i.e. without
    the stages that closed before the corrected finalization rule took effect.
    ``include_historical=True`` lists those too: what an explicit, separately
    authorized historical finalization would freeze."""
    from app.services import progression_ranking

    today = today or date.today()
    wanted_rounds = {int(v) for v in round_ids} if round_ids else None
    out: List[dict] = []
    seasons = (
        db.query(ContestSeason)
        .filter(
            ContestSeason.level == SeasonLevel.GLOBAL,
            ContestSeason.is_deleted == False,  # noqa: E712
            ContestSeason.round_id.isnot(None),
        )
        .order_by(ContestSeason.id.asc())
        .all()
    )
    for season in seasons:
        round_obj = season.round
        if round_obj is None or round_obj.status == RoundStatus.CANCELLED:
            continue
        if wanted_rounds is not None and int(round_obj.id) not in wanted_rounds:
            continue
        links = (
            db.query(ContestSeasonLink.contest_id)
            .filter(ContestSeasonLink.season_id == season.id, ContestSeasonLink.is_active == True)  # noqa: E712
            .order_by(ContestSeasonLink.contest_id.asc())
            .all()
        )
        for (cid,) in links:
            contest = db.query(Contest).filter(Contest.id == cid).first()
            if contest is None:
                continue
            if not SeasonMigrationService._global_finalization_due(round_obj, _mode(contest), today):
                continue
            historical = SeasonMigrationService.global_stage_is_historical(round_obj, _mode(contest))
            if historical and not include_historical:
                continue
            already = (
                db.query(TopHigh5Result.id)
                .filter(
                    TopHigh5Result.contest_id == contest.id,
                    TopHigh5Result.level == SeasonLevel.GLOBAL,
                    TopHigh5Result.jurisdiction == "Global",
                    TopHigh5Result.round_id == season.round_id,
                )
                .first()
            )
            if already:
                continue
            members = SeasonMigrationService._global_final_members(db, contest, season)
            if not members:
                continue
            scores = progression_ranking.score_candidates(
                db, contest=contest, round_obj=round_obj, level=SeasonLevel.GLOBAL, contestants=members
            )
            ranked = progression_ranking.rank_group(members, scores)[:5]
            out.append({
                "round_id": season.round_id,
                "round_name": round_obj.name,
                "contest_id": contest.id,
                "contest_name": contest.name,
                "global_season_id": season.id,
                "stage_closed_on": str(SeasonMigrationService._global_stage_close_date(round_obj, _mode(contest))),
                "historical": historical,
                "members": len(members),
                "would_freeze": [
                    {
                        "rank": position,
                        "contestant_id": int(c.id),
                        "cumulative_points": scores[int(c.id)].cumulative_points,
                        "contest_resolution": explain_contest_resolution(db, c, contest.id).code,
                    }
                    for position, c in enumerate(ranked, start=1)
                ],
            })
    _assert_untouched(db)
    return out


# ---------------------------------------------------------------------------
# Legacy ownership audit
# ---------------------------------------------------------------------------

def audit_legacy_collisions(db: Session) -> dict:
    """Classify every entry without a contest_id whose season_id is both a
    ContestSeason id and a Contest id (the historical collision). Read-only.

    RESOLVED_SAFELY  the legacy contest is proven by round evidence
    AMBIGUOUS        season_id may be the entry's own season (same round) or
                     the entry has no round: not provable either way
    CONFLICT         evidence names a different contest (votes, or another
                     case resolves the row to another contest)
    UNRESOLVED       nothing resolves it (e.g. contest not in the entry's round)
    """
    from app.models.voting import ContestantVoting

    rows = (
        db.query(Contestant)
        .filter(
            Contestant.contest_id.is_(None),
            Contestant.season_id.in_(select(ContestSeason.id)),
            Contestant.season_id.in_(select(Contest.id)),
        )
        .order_by(Contestant.id.asc())
        .all()
    )
    names = {int(c.id): c.name for c in db.query(Contest).filter(Contest.id.in_({int(r.season_id) for r in rows} or {-1}))}
    entries = []
    for row in rows:
        legacy_contest_id = int(row.season_id)
        resolution = explain_contest_resolution(db, row, legacy_contest_id)
        # Only an active season link (Case C) or the entry's own votes (Case D)
        # can resolve such a row to a contest other than its legacy one.
        other_candidates = {
            int(r[0])
            for r in db.query(ContestSeasonLink.contest_id)
            .filter(ContestSeasonLink.season_id == row.season_id, ContestSeasonLink.is_active == True)  # noqa: E712
            .all()
        } | {
            int(r[0])
            for r in db.query(ContestantVoting.contest_id)
            .filter(ContestantVoting.contestant_id == row.id, ContestantVoting.contest_id.isnot(None))
            .distinct()
            .all()
        }
        other_candidates.discard(legacy_contest_id)
        claimed_by = sorted(
            cid for cid in other_candidates if explain_contest_resolution(db, row, cid).belongs
        )
        if claimed_by or resolution.code == "AMBIGUOUS_COLLISION_VOTES_NAME_ANOTHER_CONTEST":
            status = "CONFLICT"
        elif resolution.belongs and resolution.code in LEGACY_COLLISION_CODES:
            status = "RESOLVED_SAFELY"
        elif resolution.belongs:
            status = "RESOLVED_SAFELY"
        elif resolution.code in ("AMBIGUOUS_COLLISION_SAME_ROUND", "AMBIGUOUS_COLLISION_ENTRY_ROUND_UNKNOWN"):
            status = "AMBIGUOUS"
        else:
            status = "UNRESOLVED"
        entries.append({
            "contestant_id": int(row.id),
            "round_id": row.round_id,
            "legacy_contest_id": legacy_contest_id,
            "legacy_contest_name": names.get(legacy_contest_id),
            "status": status,
            "code": resolution.code,
            "also_resolves_to_contests": claimed_by,
            "is_active": bool(row.is_active),
            "is_deleted": bool(row.is_deleted),
        })
    counts: Dict[str, int] = {}
    by_contest: Dict[str, Dict[str, int]] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        bucket = by_contest.setdefault(f"{entry['legacy_contest_id']}:{entry['legacy_contest_name']}", {})
        bucket[entry["status"]] = bucket.get(entry["status"], 0) + 1
    _assert_untouched(db)
    return {"total": len(entries), "counts": counts, "by_contest": by_contest, "entries": entries}
