#!/usr/bin/env python3
"""
Delete all voting-related rows for a clean slate (MyHigh5, legacy votes, rankings data).

Does NOT remove: contestants, favorites, comments, likes, shares.

Usage (from backend/, venv active):
  python scripts/clear_all_votes.py --dry-run
  python scripts/clear_all_votes.py --yes
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.contests import ContestantRanking
from app.models.voting import ContestantVoting, Vote, VoteSession

# Optional vote tables: always use raw SQL (COUNT/DELETE) so production DBs that
# diverge from SQLAlchemy models (e.g. missing round_id on user_vote_rankings) still work.


def _sql_count(session, table: str) -> int | None:
    """Count rows without ORM (avoids model/schema drift on older DBs)."""
    try:
        return session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    except Exception:
        return None


def _sql_delete(session, table: str) -> int:
    """DELETE FROM table; returns rowcount or 0 if table missing / error."""
    try:
        r = session.execute(text(f"DELETE FROM {table}"))
        return r.rowcount if r.rowcount is not None else 0
    except Exception as e:
        print(f"  (skipped {table}: {e})")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove all votes from the database.")
    parser.add_argument("--dry-run", action="store_true", help="Show counts only, do not delete.")
    parser.add_argument("--yes", action="store_true", help="Required to perform deletion.")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Specify --dry-run to preview, or --yes to delete all votes.")
        sys.exit(1)

    db = SessionLocal()
    try:
        counts = {
            "contestant_voting": db.query(ContestantVoting).count(),
            "votes": db.query(Vote).count(),
            "vote_sessions": db.query(VoteSession).count(),
        }
        # Raw SQL: production DB may not match ORM (e.g. missing round_id on user_vote_rankings)
        uvr = _sql_count(db, "user_vote_rankings")
        if uvr is not None:
            counts["user_vote_rankings"] = uvr
        else:
            counts["user_vote_rankings"] = "(table missing or unreadable)"
        cv = _sql_count(db, "contest_votes")
        counts["contest_votes"] = cv if cv is not None else "(table missing or unreadable)"
        counts["contestant_rankings_rows"] = db.query(ContestantRanking).count()

        print("Current row counts:")
        for k, v in counts.items():
            print(f"  {k}: {v}")

        if args.dry_run:
            print("\nDry run — no changes.")
            return

        # Deletes (order: optional tables first — raw SQL only, no ORM)
        n = _sql_delete(db, "contest_votes")
        print(f"Deleted contest_votes: {n}")

        n = _sql_delete(db, "user_vote_rankings")
        print(f"Deleted user_vote_rankings: {n}")

        n = db.query(ContestantVoting).delete(synchronize_session=False)
        print(f"Deleted contestant_voting: {n}")

        n = db.query(Vote).delete(synchronize_session=False)
        print(f"Deleted votes: {n}")

        n = db.query(VoteSession).delete(synchronize_session=False)
        print(f"Deleted vote_sessions: {n}")

        # Reset aggregated vote fields on stage rankings (keep rows, zero counts)
        r = (
            db.query(ContestantRanking)
            .update(
                {
                    ContestantRanking.total_votes: 0,
                    ContestantRanking.total_points: 0,
                    ContestantRanking.final_rank: None,
                },
                synchronize_session=False,
            )
        )
        print(f"Reset contestant_rankings (rows updated): {r}")

        db.commit()
        print("\nDone. All vote rows removed; ranking totals reset to 0.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
