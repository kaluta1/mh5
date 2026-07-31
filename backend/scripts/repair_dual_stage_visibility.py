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
from app.models.round import Round
from app.services.season_migration import SeasonMigrationService
from datetime import date


HIGHER = (SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL)


def main(apply: bool = False) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist repairs")
    args = parser.parse_args()
    apply = apply or args.apply

    db = SessionLocal()
    fixed_links = 0
    fixed_memberships = 0
    fixed_premature_regional = 0
    fixed_mismatched_cohort = 0
    fixed_wrong_submission_month = 0
    try:
        today = date.today()

        # Stale pooled memberships: active regional+ on round 1 while nominee is round 21.
        from app.models.contests import Contestant

        mismatched = (
            db.query(ContestantSeason, ContestSeason, Contestant, ContestSeasonLink)
            .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
            .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
            .join(
                ContestSeasonLink,
                ContestSeasonLink.season_id == ContestSeason.id,
            )
            .join(Contest, Contest.id == ContestSeasonLink.contest_id)
            .filter(
                ContestantSeason.is_active == True,
                ContestSeason.level != SeasonLevel.COUNTRY,
                ContestSeason.round_id.isnot(None),
                Contestant.round_id.isnot(None),
                Contestant.round_id != ContestSeason.round_id,
                ContestSeason.is_deleted == False,
            )
            .all()
        )
        for cs_row, seas, cont, _link in mismatched:
            c_obj = db.query(Contest).filter(Contest.id == cont.season_id).first()
            if not c_obj or (getattr(c_obj, "contest_mode", "") or "").lower() != "nomination":
                continue
            print(
                f"mismatched cohort membership contestant={cs_row.contestant_id} "
                f"contestant.round_id={cont.round_id} season.round_id={seas.round_id} "
                f"level={seas.level} season_id={seas.id}"
            )
            if apply:
                cs_row.is_active = False
            fixed_mismatched_cohort += 1
            fixed_memberships += 1

        # Also deactivate active country rows on the wrong calendar round.
        mismatched_country = (
            db.query(ContestantSeason, ContestSeason, Contestant)
            .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
            .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
            .filter(
                ContestantSeason.is_active == True,
                ContestSeason.level == SeasonLevel.COUNTRY,
                ContestSeason.round_id.isnot(None),
                Contestant.round_id.isnot(None),
                Contestant.round_id != ContestSeason.round_id,
                ContestSeason.is_deleted == False,
            )
            .all()
        )
        for cs_row, seas, cont in mismatched_country:
            c_obj = db.query(Contest).filter(Contest.id == cont.season_id).first()
            if not c_obj or (getattr(c_obj, "contest_mode", "") or "").lower() != "nomination":
                continue
            print(
                f"mismatched country membership contestant={cs_row.contestant_id} "
                f"contestant.round_id={cont.round_id} season.round_id={seas.round_id}"
            )
            if apply:
                cs_row.is_active = False
            fixed_mismatched_cohort += 1
            fixed_memberships += 1

        # Wrong submission month: e.g. registered 2026-04-04 but active on March GLOBAL season.
        from sqlalchemy import func, or_

        wrong_submission_month = (
            db.query(ContestantSeason, ContestSeason, Contestant, Round)
            .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
            .join(Contestant, Contestant.id == ContestantSeason.contestant_id)
            .join(Round, Round.id == ContestSeason.round_id)
            .filter(
                ContestantSeason.is_active == True,
                ContestSeason.level.in_(
                    [SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL]
                ),
                ContestSeason.is_deleted == False,
                Contestant.created_at.isnot(None),
                Round.submission_start_date.isnot(None),
                Round.submission_end_date.isnot(None),
                or_(
                    func.date(Contestant.created_at) < Round.submission_start_date,
                    func.date(Contestant.created_at) > Round.submission_end_date,
                ),
            )
            .all()
        )
        for cs_row, seas, cont, rnd in wrong_submission_month:
            c_obj = db.query(Contest).filter(Contest.id == cont.season_id).first()
            if not c_obj or (getattr(c_obj, "contest_mode", "") or "").lower() != "nomination":
                continue
            print(
                f"wrong submission month contestant={cs_row.contestant_id} "
                f"created={cont.created_at} round={rnd.name} "
                f"window={rnd.submission_start_date}..{rnd.submission_end_date} "
                f"level={seas.level}"
            )
            if apply:
                cs_row.is_active = False
            fixed_wrong_submission_month += 1
            fixed_memberships += 1

        premature_links = (
            db.query(ContestSeasonLink, ContestSeason)
            .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
            .filter(
                ContestSeasonLink.is_active == True,
                ContestSeason.level == SeasonLevel.REGIONAL,
                ContestSeason.is_deleted == False,
                ContestSeason.round_id.isnot(None),
            )
            .all()
        )
        for link, seas in premature_links:
            contest = db.query(Contest).filter(Contest.id == link.contest_id).first()
            if not contest or (getattr(contest, "contest_mode", "") or "").lower() != "nomination":
                continue
            round_obj = db.query(Round).filter(Round.id == seas.round_id).first()
            if not round_obj:
                continue
            vote_open = SeasonMigrationService._nomination_vote_open_date_for_level(
                round_obj, SeasonLevel.REGIONAL
            )
            if vote_open and today < vote_open:
                print(
                    f"premature regional link contest={link.contest_id} "
                    f"round={seas.round_id} season={seas.id} (vote opens {vote_open})"
                )
                if apply:
                    link.is_active = False
                    db.query(ContestantSeason).filter(
                        ContestantSeason.season_id == seas.id,
                        ContestantSeason.is_active == True,
                    ).update({"is_active": False}, synchronize_session=False)
                fixed_premature_regional += 1
                fixed_links += 1

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
            print(
                f"Applied: links={fixed_links}, memberships_touched={fixed_memberships}, "
                f"premature_regional={fixed_premature_regional}, mismatched_cohort={fixed_mismatched_cohort}, "
                f"wrong_submission_month={fixed_wrong_submission_month}"
            )
        else:
            print(
                f"Dry-run: would deactivate {fixed_links} links "
                f"(premature_regional={fixed_premature_regional}, "
                f"mismatched_cohort={fixed_mismatched_cohort}, "
                f"wrong_submission_month={fixed_wrong_submission_month})"
            )
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
