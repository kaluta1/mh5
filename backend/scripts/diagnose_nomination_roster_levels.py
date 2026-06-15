"""
Compare nomination roster counts across country / regional / continental UI levels.

Usage (on server with DATABASE_URL):
  cd backend && PYTHONPATH=. python scripts/diagnose_nomination_roster_levels.py \\
    --contest-id 15 --round-id 3 --country Tanzania --region "East Africa" --continent Africa
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crud.crud_contest import contest as contest_crud
from app.db.session import SessionLocal
from app.models.contest import Contest


LEVELS = [
    ("country", {"filter_country": None}),
    ("regional", {"filter_region": None}),
    ("continental", {"filter_continent": None}),
]


def roster_snapshot(db, contest_id: int, *, round_id, ui_level: str, geo: dict, user_id=None):
    data = contest_crud.get_contest_with_enriched_contestants(
        db,
        contest_id=contest_id,
        current_user_id=user_id,
        filter_country=geo.get("filter_country"),
        filter_region=geo.get("filter_region"),
        filter_continent=geo.get("filter_continent"),
        entry_type="nomination",
        round_id=round_id,
        requested_ui_level=ui_level,
    )
    rows = (data or {}).get("contestants") or []
    enrich = contest_crud.enrich_contest_with_stats(
        db,
        db.query(Contest).filter(Contest.id == contest_id).first(),
        current_user=db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=user_id).first() if user_id else None,
        filter_country=geo.get("filter_country"),
        filter_region=geo.get("filter_region"),
        filter_continent=geo.get("filter_continent"),
        entry_type="nomination",
        round_id=round_id,
        requested_ui_level=ui_level,
    )
    card_roster = contest_crud.count_nomination_roster_for_card(
        db,
        contest_id=contest_id,
        current_user_id=user_id,
        filter_country=geo.get("filter_country"),
        filter_region=geo.get("filter_region"),
        filter_continent=geo.get("filter_continent"),
        entry_type="nomination",
        round_id=round_id,
        requested_ui_level=ui_level,
    )
    return {
        "ui_level": ui_level,
        "geo": geo,
        "detail_count": len(rows),
        "card_roster_count": card_roster,
        "enrich_count": int(enrich.get("participants_count", enrich.get("entries_count", 0))),
        "contestant_ids": [r.get("id") for r in rows],
        "display_round_id": (data or {}).get("display_round_id"),
        "season_level": (rows[0].get("season") or {}).get("level") if rows else None,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--contest-id", type=int, required=True)
    p.add_argument("--round-id", type=int, required=True)
    p.add_argument("--country", default=None)
    p.add_argument("--region", default=None)
    p.add_argument("--continent", default=None)
    p.add_argument("--user-id", type=int, default=None)
    args = p.parse_args()

    db = SessionLocal()
    try:
        c = db.query(Contest).filter(Contest.id == args.contest_id).first()
        if not c:
            print(f"Contest {args.contest_id} not found")
            return 1
        print(f"Contest {c.id}: {c.name!r} mode={getattr(c, 'contest_mode', None)} round={args.round_id}\n")

        checks = [
            ("country", {"filter_country": args.country, "filter_region": None, "filter_continent": None}),
            ("regional", {"filter_country": None, "filter_region": args.region, "filter_continent": None}),
            ("continental", {"filter_country": None, "filter_region": None, "filter_continent": args.continent}),
        ]
        for ui_level, geo in checks:
            snap = roster_snapshot(
                db,
                args.contest_id,
                round_id=args.round_id,
                ui_level=ui_level,
                geo=geo,
                user_id=args.user_id,
            )
            mismatch = snap["detail_count"] != snap["enrich_count"] or snap["detail_count"] != snap["card_roster_count"]
            flag = " *** MISMATCH ***" if mismatch else ""
            print(f"=== {ui_level.upper()}{flag} ===")
            print(f"  geo: {geo}")
            print(f"  detail roster: {snap['detail_count']} ids={snap['contestant_ids'][:20]}")
            print(f"  card roster:   {snap['card_roster_count']}")
            print(f"  enrich count:  {snap['enrich_count']}")
            print(f"  season_level:  {snap['season_level']} display_round: {snap['display_round_id']}\n")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
