"""
Read-only diagnostic: find duplicate ContestSeason rows sharing the same
(round_id, level), which can occur when two background-scheduler triggers
(Vercel Cron, the in-process asyncio scheduler, and/or Celery beat) race to
call SeasonMigrationService.get_or_create_season() at the same moment.

This script makes NO writes. It reports how many contest links, contestant
memberships, and votes are attached to each duplicate row so a human can
decide how to merge them (if at all) with full visibility, rather than
having that decision made automatically.

Usage:
    python -m backend.scripts.detect_duplicate_contest_seasons
    (or, from backend/):  python scripts/detect_duplicate_contest_seasons.py
"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from collections import defaultdict

from app.db.session import SessionLocal
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    ContestantSeason,
)
from app.models.voting import ContestantVoting


def main() -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(ContestSeason)
            .filter(ContestSeason.is_deleted == False)  # noqa: E712
            .filter(ContestSeason.round_id.isnot(None))
            .order_by(ContestSeason.round_id.asc(), ContestSeason.id.asc())
            .all()
        )

        groups = defaultdict(list)
        for row in rows:
            groups[(row.round_id, row.level)].append(row)

        duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}

        if not duplicate_groups:
            print("No duplicate ContestSeason rows found for (round_id, level).")
            return 0

        print(f"Found {len(duplicate_groups)} duplicated (round_id, level) group(s):\n")
        for (round_id, level), seasons in duplicate_groups.items():
            print(f"round_id={round_id} level={level.value if hasattr(level, 'value') else level}")
            for season in seasons:
                link_count = (
                    db.query(ContestSeasonLink)
                    .filter(ContestSeasonLink.season_id == season.id)
                    .count()
                )
                member_count = (
                    db.query(ContestantSeason)
                    .filter(ContestantSeason.season_id == season.id)
                    .count()
                )
                vote_count = (
                    db.query(ContestantVoting)
                    .filter(ContestantVoting.season_id == season.id)
                    .count()
                )
                print(
                    f"  season_id={season.id} created via title={season.title!r} "
                    f"contest_links={link_count} contestant_members={member_count} votes={vote_count}"
                )
            print()

        print(
            "These groups likely split rankings/MyHigh5/TopHigh5 results across two "
            "season rows for the same round+level. Merging them safely requires "
            "reassigning ContestantVoting.season_id as well as the link/membership "
            "rows, which touches vote history — do this manually with a reviewed "
            "script, not automatically."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
