#!/usr/bin/env python3
"""
Targeted, explicitly-approved repair for CONTINENT-level top_high5_results
groups whose `migrated=True` set is missing real, currently-active GLOBAL
destination-season members -- originally caused by the historical backfill
computing CONTINENT results from a current-vote recompute (see the 2026-09-15
production reconciliation audit and its Continental repair preflight, in
KALUTASOCIETY memory) instead of reading actual destination membership.

Design note -- ADDITIVE ONLY, never destructive:
An earlier version of this plan proposed deleting each affected bucket's
existing rows and rebuilding it from scratch. Checking real production data
before writing any code found that would have been wrong: affected buckets
mix real `migrated=True` rows (already correct) with real `migrated=False`
rows (a continent's own Top High5 members who legitimately never advanced to
GLOBAL -- see test_continent_freeze_differs_from_worldwide_global_pool in
test_top_high5_frozen_results.py for why that's a normal, correct outcome,
not a defect). Every one of the 132 missing-migration instances found in the
2026-09-15 audit had NO existing row at all for that contestant in its
bucket -- none were a misflagged existing row. So the correct, minimally
invasive repair is:

  - INSERT a new row (migrated=True) for a real destination member with no
    existing row in the bucket at all.
  - UPDATE (never delete) an existing row's `migrated` flag only if its own
    contestant is proven, by destination-membership evidence, to actually be
    migrated=True but is currently flagged False, or vice-versa (defensive;
    not expected to fire against real data, since `extra_in_frozen` was
    empty in every 2026-09-15 mismatch checked -- kept because a different,
    future target set might hit it, and because "never guess, always check"
    is cheaper than assuming).
  - NEVER DELETE a row. A bucket's pre-existing rows -- migrated or not --
    are historical fact and are never removed by this tool.

This is deliberately NOT part of the normal backfill script:
_freeze_top_high5_results' write-once guard ("already_frozen -> return 0")
protects historical immutability for normal operation and must not change.
Repairing an already-frozen, incomplete group is a separate, explicit,
narrowly-scoped operation.

Dry-run by default; pass --apply to write. --apply requires
--expected-current-total (the live top_high5_results row count the caller
observed immediately beforehand) as a baseline guard -- the run aborts
before touching anything if the live count doesn't match.

Targets are supplied explicitly, never inferred from `WHERE level =
'continent'` or "all rounds": a JSON file (--targets) listing exactly which
(contest_id, round_id) pairs are approved for repair, e.g.:

  [{"contest_id": 1001, "round_id": 42}, {"contest_id": 1002, "round_id": 42}]

For each approved pair, every CONTINENT jurisdiction bucket for that
contest+round is independently re-evaluated against real destination
(GLOBAL) season membership:

  - 0 real members for that jurisdiction  -> SKIPPED_NO_EVIDENCE, untouched
  - 1-5 real members                      -> READY: missing ones inserted,
                                              any misflagged existing row
                                              corrected, nothing deleted
  - >5 real members                       -> SKIPPED_OVER_CAP, untouched
                                              (never arbitrarily pick five)
  - already fully correct                 -> SKIPPED_ALREADY_CORRECT

Nothing outside a bucket found this way (always scoped to one contest, one
round, one jurisdiction, one destination season) is ever touched.

Examples:
  PYTHONPATH=. python scripts/repair_continent_top_high5.py --targets targets.json
  PYTHONPATH=. python scripts/repair_continent_top_high5.py --targets targets.json \
      --apply --expected-current-total 1808 --recovery-snapshot-out snapshot.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from backfill_top_high5_results import (  # noqa: E402  (path set up above)
    _contest_linked_season_for_level,
    _groups_from_actual_migration,
)

from app.db.session import SessionLocal  # noqa: E402
from app.models.contest import Contest  # noqa: E402
from app.models.contests import ContestantSeason, Contestant, SeasonLevel, TopHigh5Result  # noqa: E402
from app.services.contestant_contest_resolution import contestant_belongs_to_contest_clause  # noqa: E402
from app.services.season_migration import SeasonMigrationService  # noqa: E402
from app.services.voting_ranking import aggregate_rankings  # noqa: E402


class RepairAbort(Exception):
    """Raised for any guard violation. Always caught, always rolls back."""


@dataclass
class BucketPlan:
    contest_id: int
    round_id: int
    jurisdiction: str
    from_season_id: int
    to_season_id: int
    status: str  # READY | SKIPPED_NO_EVIDENCE | SKIPPED_OVER_CAP | SKIPPED_ALREADY_CORRECT
    reason: str
    existing_row_ids: list = field(default_factory=list)
    existing_contestant_ids: list = field(default_factory=list)
    target_contestant_ids: list = field(default_factory=list)
    to_insert_contestant_ids: list = field(default_factory=list)
    to_promote_row_ids: list = field(default_factory=list)  # existing, migrated False->True
    to_demote_row_ids: list = field(default_factory=list)  # existing, migrated True->False (defensive)


@dataclass
class GroupPlan:
    contest_id: int
    round_id: int
    status: str  # READY | SKIPPED_NO_SEASON_EVIDENCE
    reason: str
    contest_name: "str | None" = None
    buckets: list = field(default_factory=list)


def discover_group_plan(db, contest_id: int, round_id: int) -> GroupPlan:
    """
    Read-only. Resolves the exact CONTINENT source season and GLOBAL
    destination season for this one (contest, round) -- never a different
    contest's or round's season -- and evaluates every jurisdiction bucket
    against real destination-membership evidence only. Never falls back to
    current-vote recomputation: a bucket with no destination evidence, or a
    contest/round that doesn't resolve to real seasons at all, is reported
    and skipped, not guessed at.
    """
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if contest is None:
        return GroupPlan(contest_id, round_id, "SKIPPED_NO_SEASON_EVIDENCE", "contest not found")

    source_season = _contest_linked_season_for_level(db, contest_id, round_id, SeasonLevel.CONTINENT)
    dest_season = _contest_linked_season_for_level(db, contest_id, round_id, SeasonLevel.GLOBAL)
    if source_season is None or dest_season is None:
        return GroupPlan(
            contest_id,
            round_id,
            "SKIPPED_NO_SEASON_EVIDENCE",
            "no CONTINENT source season and/or GLOBAL destination season found for this exact "
            "contest+round -- refusing to guess or fall back to another round/contest's season",
            contest_name=contest.name,
        )

    # Existing frozen rows for this exact (contest, level, round) -- the
    # write-once guard's own scope -- grouped by jurisdiction.
    existing_rows = (
        db.query(TopHigh5Result)
        .filter(
            TopHigh5Result.contest_id == contest_id,
            TopHigh5Result.level == SeasonLevel.CONTINENT,
            TopHigh5Result.round_id == round_id,
        )
        .order_by(TopHigh5Result.jurisdiction, TopHigh5Result.rank)
        .all()
    )
    existing_by_jurisdiction: dict = {}
    for r in existing_rows:
        existing_by_jurisdiction.setdefault(r.jurisdiction, []).append(r)

    # Real, uncapped destination-membership evidence, exactly scoped to this
    # contest + this destination season (never another contest sharing the
    # same season, never another round).
    real_groups = _groups_from_actual_migration(db, contest, dest_season, "continent", cap=None)

    jurisdictions = set(existing_by_jurisdiction) | set(real_groups)
    buckets = []
    for jurisdiction in sorted(jurisdictions):
        existing = existing_by_jurisdiction.get(jurisdiction, [])
        existing_by_contestant = {r.contestant_id: r for r in existing}
        real_members = real_groups.get(jurisdiction, [])
        existing_row_ids = [r.id for r in existing]
        existing_contestant_ids = [r.contestant_id for r in existing]

        if len(real_members) == 0:
            buckets.append(
                BucketPlan(
                    contest_id,
                    round_id,
                    jurisdiction,
                    source_season.id,
                    dest_season.id,
                    "SKIPPED_NO_EVIDENCE",
                    "no active GLOBAL-destination member with this continent value for this contest "
                    "-- existing rows (if any) are left untouched, not deleted",
                    existing_row_ids,
                    existing_contestant_ids,
                )
            )
            continue
        if len(real_members) > 5:
            buckets.append(
                BucketPlan(
                    contest_id,
                    round_id,
                    jurisdiction,
                    source_season.id,
                    dest_season.id,
                    "SKIPPED_OVER_CAP",
                    f"{len(real_members)} real destination members exceeds the Top-5 cap -- "
                    "refusing to arbitrarily select five; existing rows left untouched",
                    existing_row_ids,
                    existing_contestant_ids,
                )
            )
            continue

        target_ids = [m.id for m in real_members]
        target_id_set = set(target_ids)

        to_insert_members = [m for m in real_members if m.id not in existing_by_contestant]
        to_promote_row_ids = [
            r.id for r in existing if r.contestant_id in target_id_set and not r.migrated
        ]
        to_demote_row_ids = [
            r.id for r in existing if r.migrated and r.contestant_id not in target_id_set
        ]

        if not to_insert_members and not to_promote_row_ids and not to_demote_row_ids:
            buckets.append(
                BucketPlan(
                    contest_id,
                    round_id,
                    jurisdiction,
                    source_season.id,
                    dest_season.id,
                    "SKIPPED_ALREADY_CORRECT",
                    "existing rows already exactly reflect real destination membership",
                    existing_row_ids,
                    existing_contestant_ids,
                    target_ids,
                )
            )
            continue

        buckets.append(
            BucketPlan(
                contest_id,
                round_id,
                jurisdiction,
                source_season.id,
                dest_season.id,
                "READY",
                f"insert {len(to_insert_members)} missing row(s), promote {len(to_promote_row_ids)} "
                f"misflagged existing row(s) to migrated=True, demote {len(to_demote_row_ids)} "
                "(defensive, not expected against real data); no rows deleted",
                existing_row_ids,
                existing_contestant_ids,
                target_ids,
                [m.id for m in to_insert_members],
                to_promote_row_ids,
                to_demote_row_ids,
            )
        )

    return GroupPlan(contest_id, round_id, "READY", "discovered", contest_name=contest.name, buckets=buckets)


def build_dry_run_report(db, group_plans: list) -> dict:
    """All figures calculated from the supplied targets + live data, never
    hard-coded."""
    ready_buckets = [b for g in group_plans for b in g.buckets if b.status == "READY"]
    all_buckets = [b for g in group_plans for b in g.buckets]
    current_total_rows = db.query(TopHigh5Result).count()
    rows_to_insert = sum(len(b.to_insert_contestant_ids) for b in ready_buckets)
    rows_to_promote = sum(len(b.to_promote_row_ids) for b in ready_buckets)
    rows_to_demote = sum(len(b.to_demote_row_ids) for b in ready_buckets)
    return {
        "TARGET_GROUPS": len(group_plans),
        "TARGET_GROUPS_WITH_READY_BUCKETS": len({(b.contest_id, b.round_id) for b in ready_buckets}),
        "TARGET_BUCKETS": len(ready_buckets),
        "TOTAL_BUCKETS_EVALUATED": len(all_buckets),
        "SKIPPED_NO_EVIDENCE": sum(1 for b in all_buckets if b.status == "SKIPPED_NO_EVIDENCE"),
        "SKIPPED_OVER_CAP": sum(1 for b in all_buckets if b.status == "SKIPPED_OVER_CAP"),
        "SKIPPED_ALREADY_CORRECT": sum(1 for b in all_buckets if b.status == "SKIPPED_ALREADY_CORRECT"),
        "SKIPPED_NO_SEASON_EVIDENCE_GROUPS": sum(
            1 for g in group_plans if g.status == "SKIPPED_NO_SEASON_EVIDENCE"
        ),
        "CURRENT_TARGET_ROWS": sum(len(b.existing_row_ids) for b in ready_buckets),
        "ROWS_TO_INSERT": rows_to_insert,
        "ROWS_TO_PROMOTE": rows_to_promote,
        "ROWS_TO_DEMOTE": rows_to_demote,
        "ROWS_TO_DELETE": 0,
        "CURRENT_TOTAL_ROWS": current_total_rows,
        "EXPECTED_TOTAL_ROWS_AFTER_REPAIR": current_total_rows + rows_to_insert,
    }


def build_recovery_snapshot(db, group_plans: list) -> dict:
    """Enough to fully restore pre-repair state: full column values for
    every existing row that will be UPDATED (promote/demote) -- inserts are
    brand new rows with no prior state to restore, so a full rollback only
    needs (a) this snapshot, applied as an update, and (b) the
    `inserted_row_ids` an --apply run reports, deleted."""
    ready_buckets = [b for g in group_plans for b in g.buckets if b.status == "READY"]
    touched_ids = [rid for b in ready_buckets for rid in (b.to_promote_row_ids + b.to_demote_row_ids)]
    if not touched_ids:
        return {"rows_to_be_updated": []}
    rows = db.query(TopHigh5Result).filter(TopHigh5Result.id.in_(touched_ids)).all()
    snapshot = []
    for r in rows:
        snapshot.append(
            {
                "id": r.id,
                "contestant_id": r.contestant_id,
                "contest_id": r.contest_id,
                "category_id": r.category_id,
                "level": r.level.value,
                "jurisdiction": r.jurisdiction,
                "round_id": r.round_id,
                "from_season_id": r.from_season_id,
                "to_season_id": r.to_season_id,
                "rank": r.rank,
                "total_points": r.total_points,
                "total_votes": r.total_votes,
                "shares": r.shares,
                "likes": r.likes,
                "comments": r.comments,
                "views": r.views,
                "migrated": r.migrated,
            }
        )
    return {"rows_to_be_updated": snapshot}


def _insert_missing(db, contest: Contest, bucket: BucketPlan, members: list) -> list:
    """Inserts brand-new rows (migrated=True) only for members with no
    existing row in this bucket. Ranks start after the current max rank in
    the bucket so they can never collide with the unique
    (contest_id, level, jurisdiction, round_id, rank) index."""
    if not members:
        return []
    existing_max_rank = (
        db.query(TopHigh5Result.rank)
        .filter(
            TopHigh5Result.contest_id == bucket.contest_id,
            TopHigh5Result.level == SeasonLevel.CONTINENT,
            TopHigh5Result.jurisdiction == bucket.jurisdiction,
            TopHigh5Result.round_id == bucket.round_id,
        )
        .order_by(TopHigh5Result.rank.desc())
        .limit(1)
        .scalar()
    ) or 0

    bucket_key = SeasonMigrationService._top_high5_bucket_key_for_contest(contest)
    contestant_ids = [m.id for m in members]
    ranking_rows = aggregate_rankings(
        db,
        season_ids=[bucket.from_season_id],
        contestant_ids=contestant_ids,
        contest_id=contest.id,
        bucket_key=bucket_key,
        require_votes=False,
    )
    scores_by_id = {row.contestant_id: row for row in ranking_rows}

    inserted_ids = []
    for offset, candidate in enumerate(members, start=1):
        score = scores_by_id.get(candidate.id)
        row = TopHigh5Result(
            contestant_id=candidate.id,
            contest_id=bucket.contest_id,
            category_id=contest.category_id,
            level=SeasonLevel.CONTINENT,
            jurisdiction=bucket.jurisdiction,
            round_id=bucket.round_id,
            from_season_id=bucket.from_season_id,
            to_season_id=bucket.to_season_id,
            rank=existing_max_rank + offset,
            total_points=score.total_points if score else 0,
            total_votes=score.total_votes if score else 0,
            shares=score.shares if score else 0,
            likes=score.likes if score else 0,
            comments=score.comments if score else 0,
            views=score.views if score else 0,
            migrated=True,
        )
        db.add(row)
        db.flush()
        inserted_ids.append(row.id)
    return inserted_ids


def run_repair(
    db,
    targets: list,
    *,
    apply: bool = False,
    expected_current_total: "int | None" = None,
    expected_snapshot: "dict | None" = None,
) -> dict:
    """
    Single entry point for both dry-run (apply=False, the default, needs no
    baseline, performs zero writes) and the real, transactional, additive
    repair (apply=True, requires expected_current_total). Any guard
    violation raises RepairAbort internally, caught here, rolls back, and is
    reported in the returned dict rather than left as a partial write.
    """
    group_plans = [discover_group_plan(db, t["contest_id"], t["round_id"]) for t in targets]
    report = build_dry_run_report(db, group_plans)
    recovery_snapshot = build_recovery_snapshot(db, group_plans)

    result = {
        "group_plans": group_plans,
        "report": report,
        "recovery_snapshot": recovery_snapshot,
        "applied": False,
        "aborted": False,
        "abort_reason": None,
        "rows_inserted": 0,
        "rows_promoted": 0,
        "rows_demoted": 0,
        "inserted_row_ids": [],
        "buckets_repaired": 0,
    }

    if not apply:
        return result

    if expected_current_total is None:
        result["aborted"] = True
        result["abort_reason"] = "apply requires --expected-current-total; refusing to guess a baseline"
        return result

    try:
        live_total = db.query(TopHigh5Result).count()
        if live_total != expected_current_total:
            raise RepairAbort(
                f"current total mismatch: expected {expected_current_total}, live is {live_total} -- "
                "someone else changed top_high5_results since the baseline was captured"
            )

        if expected_snapshot is not None:
            live_ids = sorted(r["id"] for r in recovery_snapshot.get("rows_to_be_updated", []))
            expected_ids = sorted(r["id"] for r in expected_snapshot.get("rows_to_be_updated", []))
            if live_ids != expected_ids:
                raise RepairAbort(
                    "the set of rows that would be updated changed since the supplied snapshot was "
                    f"captured -- expected ids {expected_ids}, live ids {live_ids}"
                )

        ready_buckets = [(g, b) for g in group_plans for b in g.buckets if b.status == "READY"]

        rows_inserted = 0
        rows_promoted = 0
        rows_demoted = 0
        inserted_row_ids: list = []
        touched_groups = set()

        for group_plan, bucket in ready_buckets:
            if bucket.to_promote_row_ids:
                rows_promoted += (
                    db.query(TopHigh5Result)
                    .filter(TopHigh5Result.id.in_(bucket.to_promote_row_ids))
                    .update({TopHigh5Result.migrated: True}, synchronize_session=False)
                )
            if bucket.to_demote_row_ids:
                rows_demoted += (
                    db.query(TopHigh5Result)
                    .filter(TopHigh5Result.id.in_(bucket.to_demote_row_ids))
                    .update({TopHigh5Result.migrated: False}, synchronize_session=False)
                )
            db.flush()

            contest = db.query(Contest).filter(Contest.id == bucket.contest_id).first()
            to_insert_set = set(bucket.to_insert_contestant_ids)
            members_to_insert = [
                m
                for m in db.query(Contestant).filter(Contestant.id.in_(bucket.to_insert_contestant_ids)).all()
            ]
            if len(members_to_insert) != len(to_insert_set):
                raise RepairAbort(
                    f"contest={bucket.contest_id} jurisdiction={bucket.jurisdiction!r}: "
                    "a target contestant vanished between discovery and insert"
                )
            # preserve the original (joined_at) order captured at discovery time
            by_id = {m.id: m for m in members_to_insert}
            ordered = [by_id[cid] for cid in bucket.to_insert_contestant_ids]
            new_ids = _insert_missing(db, contest, bucket, ordered)
            rows_inserted += len(new_ids)
            inserted_row_ids.extend(new_ids)

            touched_groups.add((bucket.contest_id, bucket.to_season_id))
        db.flush()

        # Internal reconciliation check, scoped to exactly what was touched --
        # mirrors check_top_high5_reconciliation.py's own comparison, but
        # only requires the buckets we actually repaired to now match; a
        # sibling jurisdiction we deliberately skipped (over-cap / no
        # evidence) legitimately keeps mismatching and must not trip this.
        for contest_id, to_season_id in touched_groups:
            frozen_migrated_ids = {
                row[0]
                for row in db.query(TopHigh5Result.contestant_id)
                .filter(
                    TopHigh5Result.contest_id == contest_id,
                    TopHigh5Result.to_season_id == to_season_id,
                    TopHigh5Result.migrated == True,  # noqa: E712
                )
                .all()
            }
            actual_ids = {
                row[0]
                for row in db.query(ContestantSeason.contestant_id)
                .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
                .filter(
                    ContestantSeason.season_id == to_season_id,
                    ContestantSeason.is_active == True,
                    contestant_belongs_to_contest_clause(contest_id),
                )
                .all()
            }
            repaired_ids = {
                cid
                for g in group_plans
                for b in g.buckets
                if b.status == "READY" and b.contest_id == contest_id and b.to_season_id == to_season_id
                for cid in b.target_contestant_ids
            }
            if not repaired_ids.issubset(frozen_migrated_ids) or not repaired_ids.issubset(actual_ids):
                raise RepairAbort(
                    f"post-repair reconciliation failed for contest={contest_id} to_season={to_season_id}"
                )

        db.commit()
        result["applied"] = True
        result["rows_inserted"] = rows_inserted
        result["rows_promoted"] = rows_promoted
        result["rows_demoted"] = rows_demoted
        result["inserted_row_ids"] = inserted_row_ids
        result["buckets_repaired"] = len(ready_buckets)
        return result

    except RepairAbort as e:
        db.rollback()
        result["aborted"] = True
        result["abort_reason"] = str(e)
        return result
    except Exception:
        db.rollback()
        raise


def _print_report(report: dict, group_plans: list) -> None:
    for key, value in report.items():
        print(f"{key}: {value}")
    print()
    for g in group_plans:
        print(f"contest={g.contest_id} ({g.contest_name}) round={g.round_id}: {g.status} -- {g.reason}")
        for b in g.buckets:
            print(
                f"  jurisdiction={b.jurisdiction!r} status={b.status} "
                f"existing={b.existing_contestant_ids} target={b.target_contestant_ids} -- {b.reason}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--targets", required=True, help='JSON file: [{"contest_id":.., "round_id":..}, ...]')
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run report only)")
    parser.add_argument("--expected-current-total", type=int, default=None)
    parser.add_argument("--expected-snapshot", default=None, help="JSON file from a prior --recovery-snapshot-out")
    parser.add_argument("--recovery-snapshot-out", default=None)
    args = parser.parse_args()

    with open(args.targets) as f:
        targets = json.load(f)

    expected_snapshot = None
    if args.expected_snapshot:
        with open(args.expected_snapshot) as f:
            expected_snapshot = json.load(f)

    db = SessionLocal()
    try:
        result = run_repair(
            db,
            targets,
            apply=args.apply,
            expected_current_total=args.expected_current_total,
            expected_snapshot=expected_snapshot,
        )

        if args.recovery_snapshot_out:
            with open(args.recovery_snapshot_out, "w") as f:
                json.dump(result["recovery_snapshot"], f, indent=2)
            print(f"Recovery snapshot written to {args.recovery_snapshot_out}")

        _print_report(result["report"], result["group_plans"])

        if result["aborted"]:
            print(f"\nABORTED: {result['abort_reason']}")
            sys.exit(1)
        if result["applied"]:
            print(
                f"\nAPPLIED: buckets_repaired={result['buckets_repaired']} "
                f"rows_inserted={result['rows_inserted']} rows_promoted={result['rows_promoted']} "
                f"rows_demoted={result['rows_demoted']}"
            )
            print(f"inserted_row_ids: {result['inserted_row_ids']}")
        else:
            print("\nDry run only -- pass --apply (with --expected-current-total) to write.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
