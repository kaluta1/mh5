#!/usr/bin/env python3
"""
Merge duplicate Round rows into canonical rounds, then delete the duplicate.

Use when two rounds exist for the same calendar month (e.g. bad scheduler run).
Example from UI:
  Keep May 2026 id=208, remove duplicate May id=210   -> --merge 210:208
  Keep April 2026 id=209, remove duplicate April       -> --merge <dup_id>:209

Note: A primary key cannot appear twice; if the UI shows "(210)" for two rows,
one of those labels may be wrong — list rounds with --list to see real ids.

Usage:
  cd backend && PYTHONPATH=. python scripts/merge_duplicate_rounds.py --list
  PYTHONPATH=. python scripts/merge_duplicate_rounds.py --merge 210:208 --merge 211:209 --dry-run
  PYTHONPATH=. python scripts/merge_duplicate_rounds.py --merge 210:208 --merge 211:209
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

# Ensure backend is on path when run as script
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import select, delete, insert
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("merge_duplicate_rounds")


def _setup():
    from app.db.session import SessionLocal  # noqa: lazy after path fix
    from app.models.round import Round, round_contests
    from app.models.contests import ContestSeason, Contestant
    from app.models.contest import Contest, ContestVote
    from app.models.vote_ranking import UserVoteRanking
    return SessionLocal, Round, round_contests, ContestSeason, Contestant, Contest, ContestVote, UserVoteRanking


def list_rounds(db: Session, Round) -> None:
    rows = db.query(Round).order_by(Round.id.desc()).limit(80).all()
    for r in rows:
        print(f"  id={r.id:>5}  name={r.name!r}  status={r.status}")


def merge_round_into(
    db: Session,
    duplicate_id: int,
    keep_id: int,
    dry_run: bool,
    *,
    Round,
    round_contests,
    ContestSeason,
    Contestant,
    Contest,
    ContestVote,
    UserVoteRanking,
) -> dict:
    dup = db.query(Round).filter(Round.id == duplicate_id).first()
    keep = db.query(Round).filter(Round.id == keep_id).first()
    if not dup:
        raise SystemExit(f"Round id={duplicate_id} not found")
    if not keep:
        raise SystemExit(f"Round id={keep_id} not found")
    if duplicate_id == keep_id:
        raise SystemExit("duplicate_id and keep_id must differ")

    stats = {"round_contests_copied": 0, "vote_rankings_merged": 0, "vote_rankings_deleted": 0}

    # 1) round_contests: copy links (round_id, contest_id) unique per pair
    links = db.execute(
        select(round_contests.c.contest_id).where(round_contests.c.round_id == duplicate_id)
    ).fetchall()
    contest_ids = [row[0] for row in links]
    for cid in contest_ids:
        exists = db.execute(
            select(round_contests.c.id).where(
                round_contests.c.round_id == keep_id,
                round_contests.c.contest_id == cid,
            )
        ).first()
        if not exists:
            if not dry_run:
                db.execute(
                    insert(round_contests).values(
                        round_id=keep_id,
                        contest_id=cid,
                        created_at=datetime.utcnow(),
                    )
                )
            stats["round_contests_copied"] += 1

    # 2) Legacy Contest.round_id
    if not dry_run:
        db.query(Contest).filter(Contest.round_id == duplicate_id).update(
            {Contest.round_id: keep_id}, synchronize_session=False
        )

    # 3) Contestant.round_id
    if not dry_run:
        db.query(Contestant).filter(Contestant.round_id == duplicate_id).update(
            {Contestant.round_id: keep_id}, synchronize_session=False
        )

    # 4) contest_seasons: repoint to canonical round
    if not dry_run:
        db.query(ContestSeason).filter(ContestSeason.round_id == duplicate_id).update(
            {ContestSeason.round_id: keep_id}, synchronize_session=False
        )

    # 5) contest_votes (legacy score votes)
    if not dry_run:
        db.query(ContestVote).filter(ContestVote.round_id == duplicate_id).update(
            {ContestVote.round_id: keep_id}, synchronize_session=False
        )

    # 6) user_vote_rankings — unique (user_id, round_id, contestant_id)
    rankings = (
        db.query(UserVoteRanking).filter(UserVoteRanking.round_id == duplicate_id).all()
    )
    for vr in rankings:
        existing = (
            db.query(UserVoteRanking)
            .filter(
                UserVoteRanking.user_id == vr.user_id,
                UserVoteRanking.round_id == keep_id,
                UserVoteRanking.contestant_id == vr.contestant_id,
            )
            .first()
        )
        if existing:
            if vr.points > existing.points:
                existing.position = vr.position
                existing.points = vr.points
                existing.updated_at = datetime.utcnow()
            if not dry_run:
                db.delete(vr)
            stats["vote_rankings_deleted"] += 1
        else:
            if not dry_run:
                vr.round_id = keep_id
            stats["vote_rankings_merged"] += 1

    # 7) Legacy Round.contest_id on duplicate row (rare)
    if dup.contest_id and not dry_run:
        k = db.query(Contest).filter(Contest.id == dup.contest_id).first()
        if k and k.round_id == duplicate_id:
            k.round_id = keep_id

    # 8) Remove remaining association rows for duplicate round, then delete round
    if not dry_run:
        db.execute(delete(round_contests).where(round_contests.c.round_id == duplicate_id))
        db.delete(dup)
        db.commit()
        logger.info(
            "Merged round %s -> %s: copied %s round_contests, rankings touched=%s/%s",
            duplicate_id,
            keep_id,
            stats["round_contests_copied"],
            stats["vote_rankings_merged"],
            stats["vote_rankings_deleted"],
        )
    else:
        logger.info(
            "[dry-run] Would merge round %s -> %s; "
            "round_contests to add=%s; vote_rankings move=%s conflict_drop=%s",
            duplicate_id,
            keep_id,
            stats["round_contests_copied"],
            stats["vote_rankings_merged"],
            stats["vote_rankings_deleted"],
        )

    return stats


def parse_merge(s: str) -> tuple[int, int]:
    if ":" not in s:
        raise argparse.ArgumentTypeError("Expected DUPLICATE_ID:KEEP_ID")
    a, b = s.split(":", 1)
    return int(a.strip()), int(b.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge duplicate rounds into canonical rounds")
    ap.add_argument("--list", action="store_true", help="List recent rounds (ids + names)")
    ap.add_argument(
        "--merge",
        action="append",
        type=parse_merge,
        default=[],
        metavar="DUP:KEEP",
        help="Merge duplicate round DUP into KEEP (repeat for multiple pairs)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Show actions without committing")
    args = ap.parse_args()

    SessionLocal, Round, round_contests, ContestSeason, Contestant, Contest, ContestVote, UserVoteRanking = _setup()
    db = SessionLocal()
    try:
        if args.list:
            list_rounds(db, Round)
            return
        if not args.merge:
            ap.print_help()
            print("\nExample: --merge 210:208 --merge 211:209")
            raise SystemExit(1)

        for dup_id, keep_id in args.merge:
            merge_round_into(
                db,
                dup_id,
                keep_id,
                args.dry_run,
                Round=Round,
                round_contests=round_contests,
                ContestSeason=ContestSeason,
                Contestant=Contestant,
                Contest=Contest,
                ContestVote=ContestVote,
                UserVoteRanking=UserVoteRanking,
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
