#!/usr/bin/env python3
"""
Repair historical nomination rows that are hidden in "view nominations".

Why rows become hidden:
1) `contestants.entry_type` was stored as `participation` for nomination contests.
2) `contestants.season_id` was stored as `contest_seasons.id` instead of `contest.id`
   (legacy ID-resolution collision path), so contest-scoped queries miss the row.

This script performs safe, targeted fixes for nomination contests only.
Run first with --dry-run, then with --apply.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import text

from app.db.session import SessionLocal


@dataclass
class RepairStats:
    wrong_season_rows: int = 0
    wrong_entry_rows: int = 0
    fixed_season_rows: int = 0
    fixed_entry_rows: int = 0


def collect_stats(db) -> RepairStats:
    stats = RepairStats()

    # contestants.season_id points to contest_seasons.id linked to a nomination contest
    # and differs from the linked contest id -> hidden in contest-scoped listing
    wrong_season_sql = text(
        """
        SELECT COUNT(*)
        FROM contestants ct
        JOIN contest_season_links csl
          ON csl.season_id = ct.season_id
         AND csl.is_active = true
        JOIN contest c
          ON c.id = csl.contest_id
        WHERE ct.is_deleted = false
          AND lower(coalesce(c.contest_mode, '')) = 'nomination'
          AND ct.season_id <> c.id
        """
    )
    stats.wrong_season_rows = int(db.execute(wrong_season_sql).scalar() or 0)

    # nomination contests but entry_type is not nomination
    wrong_entry_sql = text(
        """
        SELECT COUNT(*)
        FROM contestants ct
        JOIN contest c
          ON c.id = ct.season_id
        WHERE ct.is_deleted = false
          AND lower(coalesce(c.contest_mode, '')) = 'nomination'
          AND lower(coalesce(ct.entry_type, 'participation')) <> 'nomination'
        """
    )
    stats.wrong_entry_rows = int(db.execute(wrong_entry_sql).scalar() or 0)

    return stats


def apply_repairs(db) -> RepairStats:
    stats = RepairStats()

    fix_season_sql = text(
        """
        UPDATE contestants AS ct
        SET season_id = c.id
        FROM contest_season_links csl
        JOIN contest c
          ON c.id = csl.contest_id
        WHERE csl.season_id = ct.season_id
          AND csl.is_active = true
          AND ct.is_deleted = false
          AND lower(coalesce(c.contest_mode, '')) = 'nomination'
          AND ct.season_id <> c.id
        """
    )
    season_res = db.execute(fix_season_sql)
    stats.fixed_season_rows = int(season_res.rowcount or 0)

    fix_entry_sql = text(
        """
        UPDATE contestants AS ct
        SET entry_type = 'nomination'
        FROM contest c
        WHERE c.id = ct.season_id
          AND ct.is_deleted = false
          AND lower(coalesce(c.contest_mode, '')) = 'nomination'
          AND lower(coalesce(ct.entry_type, 'participation')) <> 'nomination'
        """
    )
    entry_res = db.execute(fix_entry_sql)
    stats.fixed_entry_rows = int(entry_res.rowcount or 0)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair hidden nomination contestants")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Without this flag, only prints audit counts.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        before = collect_stats(db)
        print("=== Nomination visibility audit (before) ===")
        print(f"wrong season_id rows: {before.wrong_season_rows}")
        print(f"wrong entry_type rows: {before.wrong_entry_rows}")

        if not args.apply:
            print("\nDry run only. Re-run with --apply to repair.")
            return 0

        fixed = apply_repairs(db)
        db.commit()

        after = collect_stats(db)
        print("\n=== Repair applied ===")
        print(f"season_id rows fixed: {fixed.fixed_season_rows}")
        print(f"entry_type rows fixed: {fixed.fixed_entry_rows}")
        print("\n=== Nomination visibility audit (after) ===")
        print(f"wrong season_id rows: {after.wrong_season_rows}")
        print(f"wrong entry_type rows: {after.wrong_entry_rows}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

