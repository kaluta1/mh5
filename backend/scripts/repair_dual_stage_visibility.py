#!/usr/bin/env python3
"""
Repair nominees that appear in both country and regional (or higher) Vote stages.

Root cause: ensure_active_country_round_link_for_nomination + _sync_contestants_to_season
reactivated COUNTRY ContestSeasonLink / ContestantSeason after promotion.

Usage (VPS):
  cd /root/mh5/backend && source venv/bin/activate
  export PYTHONPATH=/root/mh5/backend
  python scripts/repair_dual_stage_visibility.py          # dry-run
  python scripts/repair_dual_stage_visibility.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import ContestSeason, ContestSeasonLink, ContestantSeason, SeasonLevel
from app.services.season_migration import SeasonMigrationService


HIGHER = (SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL)


def main(apply: bool = False) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist repairs")
    args = parser.parse_args()
    apply = apply or args.apply

    db = SessionLocal()
    fixed_links = 0
    fixed_memberships = 0
    try:
        higher_links = (
            db.query(ContestSeasonLink, ContestSeason)
            .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
            .filter(
                ContestSeasonLink.is_active == True,
                ContestSeason.level.in_(HIGHER),
                ContestSeason.is_deleted == False,
                ContestSeason.round_id.isnot(None),
            )
            .all()
        )
        seen = set()
        for link, seas in higher_links:
            key = (link.contest_id, seas.round_id)
            if key in seen:
                continue
            seen.add(key)
            contest = db.query(Contest).filter(Contest.id == link.contest_id).first()
            if not contest or (getattr(contest, "contest_mode", "") or "").lower() != "nomination":
                continue

            promoted_ids = SeasonMigrationService.contestant_ids_active_beyond_level(
                db, link.contest_id, int(seas.round_id), SeasonLevel.COUNTRY
            )

            country_links = (
                db.query(ContestSeasonLink, ContestSeason)
                .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                .filter(
                    ContestSeasonLink.contest_id == link.contest_id,
                    ContestSeason.round_id == seas.round_id,
                    ContestSeason.level == SeasonLevel.COUNTRY,
                    ContestSeason.is_deleted == False,
                )
                .all()
            )
            for clink, cseas in country_links:
                if clink.is_active:
                    print(
                        f"deactivate country ContestSeasonLink contest={link.contest_id} "
                        f"round={seas.round_id} season={cseas.id}"
                    )
                    if apply:
                        clink.is_active = False
                    fixed_links += 1
                synced_before = (
                    db.query(ContestantSeason)
                    .filter(
                        ContestantSeason.season_id == cseas.id,
                        ContestantSeason.is_active == True,
                    )
                    .count()
                )
                if apply:
                    SeasonMigrationService._sync_contestants_to_season(
                        db, link.contest_id, int(seas.round_id), cseas.id
                    )
                synced_after = (
                    db.query(ContestantSeason)
                    .filter(
                        ContestantSeason.season_id == cseas.id,
                        ContestantSeason.is_active == True,
                    )
                    .count()
                )
                if synced_before != synced_after or synced_before:
                    print(
                        f"  country ContestantSeason active: {synced_before} -> "
                        f"{synced_after if apply else '(dry-run)'}"
                    )
                    fixed_memberships += max(0, synced_before - (synced_after if apply else 0))

            # Hard deactivate country membership for anyone already in regional+ pool.
            if promoted_ids and apply:
                stale_country_rows = (
                    db.query(ContestantSeason)
                    .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
                    .filter(
                        ContestSeason.round_id == seas.round_id,
                        ContestSeason.level == SeasonLevel.COUNTRY,
                        ContestSeason.is_deleted == False,
                        ContestantSeason.contestant_id.in_(list(promoted_ids)),
                        ContestantSeason.is_active == True,
                    )
                    .all()
                )
                for row in stale_country_rows:
                    row.is_active = False
                    fixed_memberships += 1
                    print(
                        f"  deactivate country ContestantSeason contestant={row.contestant_id} "
                        f"season={row.season_id}"
                    )
            elif promoted_ids:
                n_stale = (
                    db.query(ContestantSeason.id)
                    .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
                    .filter(
                        ContestSeason.round_id == seas.round_id,
                        ContestSeason.level == SeasonLevel.COUNTRY,
                        ContestSeason.is_deleted == False,
                        ContestantSeason.contestant_id.in_(list(promoted_ids)),
                        ContestantSeason.is_active == True,
                    )
                    .count()
                )
                if n_stale:
                    print(f"  would deactivate {n_stale} stale country ContestantSeason row(s)")
                    fixed_memberships += n_stale

        if apply:
            db.commit()
            print(f"Applied: links={fixed_links}, memberships_touched={fixed_memberships}")
        else:
            print(f"Dry-run: would deactivate {fixed_links} country links")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
