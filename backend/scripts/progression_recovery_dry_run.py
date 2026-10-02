#!/usr/bin/env python3
"""
READ-ONLY dry-run of contest progression under the corrected ranking rules
(cumulative voting points, engagement tie-breakers, top five per group, no
vote required, legacy contest ownership resolved from evidence).

It reports, for every transition that is due, who WOULD advance. It writes
nothing: on PostgreSQL the whole run happens inside a READ ONLY transaction,
so the database itself refuses any write, and the transaction is rolled back
at the end.

Examples:
  PYTHONPATH=. python scripts/progression_recovery_dry_run.py
  PYTHONPATH=. python scripts/progression_recovery_dry_run.py --round 28 --round 27
  PYTHONPATH=. python scripts/progression_recovery_dry_run.py --round 26 --contest 5 --json out.json
  PYTHONPATH=. python scripts/progression_recovery_dry_run.py --as-of 2026-10-02 --csv entries.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services.progression_dry_run import (  # noqa: E402
    audit_legacy_collisions,
    pending_global_finalizations,
    simulate_due_progressions,
)

ENTRY_COLUMNS = [
    "round_id", "round_name", "contest_id", "contest_name", "category_id", "source_season_id",
    "source_stage", "contestant_id", "entry_title", "nominator_user_id", "nominator_username",
    "group", "previous_stage_points", "current_stage_points", "cumulative_points", "shares",
    "likes", "comments", "views", "submitted_at", "rank", "qualifies", "outcome",
    "destination_stage", "regional_pool", "ranking_scope", "safety_eligible", "contest_resolution",
]


def _rows(report: dict):
    for hop in report["transitions"]:
        head = {key: hop[key] for key in (
            "round_id", "round_name", "contest_id", "contest_name", "category_id",
            "source_season_id", "source_stage",
        )}
        for entry in hop["entries"]:
            yield {**head, **{key: entry.get(key) for key in ENTRY_COLUMNS if key not in head}}


def _print_text(report: dict) -> None:
    totals = report["totals"]
    print("PROGRESSION DRY-RUN (read-only) as of", totals["as_of"])
    for key, value in totals.items():
        if key != "as_of":
            print(f"  {key}: {value}")
    for hop in report["transitions"]:
        print()
        print(
            f"round {hop['round_id']} ({hop['round_name']}) | contest {hop['contest_id']} "
            f"{hop['contest_name']!r} [{hop['contest_mode']}] | {hop['source_stage']} season "
            f"{hop['source_season_id']} -> {hop['destination_stage']} season "
            f"{hop['destination_season_id'] or 'NEW'}"
        )
        print("  summary:", hop["summary"])
        print("  top_high5:", hop["top_high5"])
        if hop["not_yet_in_source_season"]:
            print("  not_yet_in_source_season:", hop["not_yet_in_source_season"])
        for entry in hop["entries"]:
            print(
                "   {group!s:<18} #{rank!s:<3} id={contestant_id:<6} prev={previous_stage_points:<4} "
                "now={current_stage_points:<4} total={cumulative_points:<4} sh={shares} li={likes} "
                "co={comments} vi={views} sub={submitted_at} {outcome} [{contest_resolution}]".format(**entry)
            )
        for item in hop["excluded_legacy_entries"]:
            print("   EXCLUDED legacy entry", item)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--round", dest="rounds", type=int, action="append", help="limit to this round id (repeatable)")
    parser.add_argument("--contest", dest="contests", type=int, action="append", help="limit to this contest id (repeatable)")
    parser.add_argument("--as-of", help="evaluate what is due on this date (YYYY-MM-DD); default today")
    parser.add_argument("--include-empty", action="store_true", help="also list due transitions with no entry at all")
    parser.add_argument("--json", dest="json_out", help="write the full report to this file")
    parser.add_argument("--csv", dest="csv_out", help="write one row per entry to this file")
    parser.add_argument("--legacy-audit", action="store_true",
                        help="also classify every legacy entry whose season_id collides with a season id")
    parser.add_argument("--global-finalizations", action="store_true",
                        help="also list GLOBAL stages whose Top High5 freeze is due")
    parser.add_argument("--quiet", action="store_true", help="print only the totals")
    args = parser.parse_args()

    today = date.fromisoformat(args.as_of) if args.as_of else date.today()
    db = SessionLocal()
    try:
        if db.get_bind().dialect.name == "postgresql":
            # The database enforces it: any write in this transaction fails.
            db.execute(text("SET TRANSACTION READ ONLY"))
            read_only = db.execute(text("SHOW transaction_read_only")).scalar()
            if str(read_only).lower() != "on":
                raise SystemExit("refusing to run: the transaction is not READ ONLY")
            print("transaction_read_only =", read_only)
        report = simulate_due_progressions(
            db,
            today=today,
            round_ids=args.rounds,
            contest_ids=args.contests,
            include_empty=args.include_empty,
        )
        if args.global_finalizations:
            report["pending_global_finalizations"] = pending_global_finalizations(
                db, today=today, round_ids=args.rounds
            )
        if args.legacy_audit:
            report["legacy_audit"] = audit_legacy_collisions(db)
    finally:
        db.rollback()
        db.close()

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, default=str)
    if args.csv_out:
        with open(args.csv_out, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ENTRY_COLUMNS)
            writer.writeheader()
            writer.writerows(_rows(report))
    if args.quiet:
        print(json.dumps(report["totals"], indent=2))
    else:
        _print_text(report)
    if "legacy_audit" in report:
        audit = report["legacy_audit"]
        print()
        print("LEGACY AUDIT:", audit["total"], audit["counts"])
        for key, value in sorted(audit["by_contest"].items()):
            print("  ", key, value)
    if "pending_global_finalizations" in report:
        print()
        print("GLOBAL FINALIZATIONS DUE:", len(report["pending_global_finalizations"]))
    print()
    print("NO DATABASE WRITE WAS MADE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
