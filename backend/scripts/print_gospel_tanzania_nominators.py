#!/usr/bin/env python3
"""
Print all nominators (users who submitted a nomination row) for a Gospel contest,
scoped to Tanzania (nominator country / row country / linked user country), same
idea as the API country filter.

Run from the backend folder with PYTHONPATH including the app root:

  cd backend
  set PYTHONPATH=.
  python scripts/print_gospel_tanzania_nominators.py

Options:

  python scripts/print_gospel_tanzania_nominators.py --contest-name Gospel --country Tanzania
  python scripts/print_gospel_tanzania_nominators.py --contest-id 42 --round-id 5
  python scripts/print_gospel_tanzania_nominators.py --csv gospel_tz_nominators.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Any, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.crud.crud_contest import _get_country_match_patterns
from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.user import User


def _resolve_contest(db, contest_id: Optional[int], contest_name: str) -> Contest:
    q = db.query(Contest).filter(Contest.is_deleted == False)
    if contest_id is not None:
        c = q.filter(Contest.id == contest_id).first()
        if not c:
            raise SystemExit(f"No contest with id={contest_id}")
        return c
    needle = (contest_name or "").strip().lower()
    if not needle:
        raise SystemExit("--contest-name is empty")
    rows = (
        q.filter(Contest.name.ilike(f"%{needle}%"))
        .order_by(Contest.id.asc())
        .all()
    )
    if not rows:
        raise SystemExit(f"No contest whose name contains {contest_name!r}")
    if len(rows) > 1:
        print("Multiple contests matched; use --contest-id to pick one:\n", file=sys.stderr)
        for r in rows:
            print(f"  id={r.id} name={r.name!r} mode={getattr(r, 'contest_mode', None)}", file=sys.stderr)
        raise SystemExit("Aborting (ambiguous). Pass --contest-id …")
    return rows[0]


def _country_clause(country: str, contestant: Any, user: Any):
    pats = _get_country_match_patterns(country) or [f"%{country.lower().strip()}%"]
    conds = []
    for pat in pats:
        conds.append(Contestant.country.ilike(pat))
        conds.append(Contestant.nominator_country.ilike(pat))
        conds.append(user.country.ilike(pat))
    return or_(*conds)


def main() -> None:
    ap = argparse.ArgumentParser(description="List nominators for Gospel (or named) contest in Tanzania")
    ap.add_argument("--contest-name", default="Gospel", help="Substring match on contest.name (default: Gospel)")
    ap.add_argument("--contest-id", type=int, default=None, help="Exact contest id (overrides name match)")
    ap.add_argument("--country", default="Tanzania", help="Country filter (default: Tanzania)")
    ap.add_argument("--round-id", type=int, default=None, help="Optional calendar round id filter")
    ap.add_argument("--csv", metavar="PATH", help="Also write CSV to this path")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        contest = _resolve_contest(db, args.contest_id, args.contest_name)
        mode = getattr(contest.contest_mode, "value", contest.contest_mode) or ""
        if str(mode).lower() not in ("nomination", "contestmode.nomination"):
            print(
                f"Warning: contest {contest.id} contest_mode={mode!r} (expected nomination). Listing nomination rows anyway.",
                file=sys.stderr,
            )

        u = User
        q = (
            db.query(Contestant)
            .options(joinedload(Contestant.user))
            .filter(
                Contestant.season_id == contest.id,
                Contestant.is_deleted == False,
                Contestant.entry_type == "nomination",
            )
            .join(u, Contestant.user_id == u.id)
        )
        q = q.filter(_country_clause(args.country, Contestant, u))
        if args.round_id is not None:
            q = q.filter(Contestant.round_id == args.round_id)

        rows: List[Contestant] = q.order_by(Contestant.id.asc()).all()

        print(f"contest_id={contest.id} name={contest.name!r} country={args.country!r} rows={len(rows)}")
        if args.round_id is not None:
            print(f"round_id filter={args.round_id}")
        print()

        fieldnames = [
            "contestant_id",
            "round_id",
            "nominator_user_id",
            "nominator_email",
            "nominator_name",
            "nominator_country",
            "nominee_country",
            "nomination_title",
        ]
        for c in rows:
            user = c.user
            email = getattr(user, "email", None) or ""
            name = (
                getattr(user, "full_name", None)
                or f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
                or getattr(user, "username", None)
                or ""
            )
            line = (
                f"id={c.id} round={c.round_id} user_id={c.user_id} "
                f"email={email!r} name={name!r} "
                f"nominator_country={c.nominator_country!r} row_country={c.country!r} "
                f"title={(c.title or '')[:80]!r}"
            )
            print(line)

        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as fp:
                w = csv.DictWriter(fp, fieldnames=fieldnames)
                w.writeheader()
                for c in rows:
                    user = c.user
                    email = getattr(user, "email", None) or ""
                    name = (
                        getattr(user, "full_name", None)
                        or f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
                        or getattr(user, "username", None)
                        or ""
                    )
                    w.writerow(
                        {
                            "contestant_id": c.id,
                            "round_id": c.round_id or "",
                            "nominator_user_id": c.user_id,
                            "nominator_email": email,
                            "nominator_name": name,
                            "nominator_country": c.nominator_country or "",
                            "nominee_country": c.country or "",
                            "nomination_title": (c.title or "").replace("\n", " ")[:500],
                        }
                    )
            print(f"\nWrote {args.csv}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
