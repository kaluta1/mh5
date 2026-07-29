#!/usr/bin/env python3
"""Find a nominee visible at both country and regional — run on VPS against prod DB."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
)
from app.services.season_migration import SeasonMigrationService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", default="mentali", help="Substring in contestant title/description")
    args = parser.parse_args()
    needle = args.search.strip().lower()
    if not needle:
        print("Provide --search")
        return 1

    db = SessionLocal()
    try:
        rows = (
            db.query(Contestant, Contest)
            .join(Contest, Contest.id == Contestant.season_id)
            .filter(Contestant.is_deleted == False)
            .all()
        )
        hits = []
        for c, contest in rows:
            mode = str(getattr(contest, "contest_mode", "") or "").lower()
            if "nomination" not in mode:
                continue
            title = (getattr(c, "title", None) or getattr(c, "name", None) or "").lower()
            desc = (getattr(c, "description", None) or "").lower()
            if needle in title or needle in desc:
                hits.append((c, contest))

        if not hits:
            print(f"No nomination contestants matching {needle!r}")
            return 0

        for c, contest in hits:
            print("=" * 60)
            print(f"contestant_id={c.id} contest_id={contest.id} name={contest.name!r}")
            print(f"  title={getattr(c, 'title', None)!r} round_id={c.round_id}")
            print(f"  country={c.country!r} region={getattr(c, 'region', None)!r}")

            memberships = (
                db.query(ContestantSeason, ContestSeason, ContestSeasonLink)
                .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
                .join(ContestSeasonLink, ContestSeasonLink.season_id == ContestSeason.id)
                .filter(
                    ContestantSeason.contestant_id == c.id,
                    ContestSeasonLink.contest_id == contest.id,
                    ContestSeason.is_deleted == False,
                )
                .all()
            )
            if not memberships:
                print("  ContestantSeason: (none)")
            for cs, seas, link in memberships:
                lvl = seas.level.value if hasattr(seas.level, "value") else seas.level
                print(
                    f"  ContestantSeason season_id={seas.id} level={lvl} "
                    f"round_id={seas.round_id} active={cs.is_active} link_active={link.is_active}"
                )

            if c.round_id:
                rid = int(c.round_id)
                promoted = SeasonMigrationService.contestant_ids_active_beyond_level(
                    db, contest.id, rid, SeasonLevel.COUNTRY
                )
                regional = SeasonMigrationService.contestant_ids_in_regional_season_for_round(
                    db, contest.id, rid
                )
                print(f"  promoted_beyond_country={c.id in promoted}")
                print(f"  in_regional_pool={c.id in regional}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
