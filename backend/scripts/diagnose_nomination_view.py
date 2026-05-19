"""
Diagnose empty nomination view for a user on a contest.

  docker compose -f backend/docker-compose.yml exec app \\
    python scripts/diagnose_nomination_view.py --contest-id 7 --user-id YOUR_ID
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import or_

from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.contests import Contestant
from app.services.contest_category_integrity import (
    contest_ids_for_category,
    find_duplicate_nominator_nomination_groups,
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--contest-id", type=int, required=True)
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--round-id", type=int, default=None)
    args = p.parse_args()

    db = SessionLocal()
    try:
        c = db.query(Contest).filter(Contest.id == args.contest_id).first()
        if not c:
            print(f"Contest {args.contest_id} not found")
            return 1

        siblings = contest_ids_for_category(
            db,
            category_id=getattr(c, "category_id", None),
            contest_type=getattr(c, "contest_type", None) or "",
        )
        print(f"Contest {c.id} {c.name!r} category_id={c.category_id} siblings={siblings}")

        q = db.query(Contestant).filter(
            Contestant.user_id == args.user_id,
            Contestant.is_deleted == False,
            or_(Contestant.entry_type == "nomination", Contestant.entry_type.is_(None)),
        )
        if args.round_id:
            q = q.filter(Contestant.round_id == args.round_id)

        rows = q.order_by(Contestant.id.desc()).all()
        print(f"\nUser {args.user_id} nomination rows ({len(rows)}):")
        for r in rows:
            on_this = "ON THIS CONTEST" if r.season_id == args.contest_id else "OTHER CONTEST"
            print(
                f"  id={r.id} season_id(contest)={r.season_id} round_id={r.round_id} "
                f"nominator_country={r.nominator_country!r} {on_this}"
            )

        if rows and not any(r.season_id == args.contest_id for r in rows):
            print(
                "\n>>> ROOT CAUSE: nomination is stored on a sibling contest id, "
                "not on this contest. Re-home with fix_nomination_integrity --apply "
                "or redeploy backend (rehome on submit)."
            )

        groups = find_duplicate_nominator_nomination_groups(
            db, round_id=args.round_id
        )
        for g in groups:
            if g["user_id"] == args.user_id and g["category_scope"] in (
                f"cat:{c.category_id}",
                f"ty:{c.contest_type}",
            ):
                print(f"\nDuplicate group: {g}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
