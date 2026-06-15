#!/usr/bin/env python3
"""Run nomination fix checks directly against DB (no HTTP server)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
if not os.getenv("DATABASE_URL"):
    load_dotenv(ROOT.parent / "backend" / ".env", override=False)
if not os.getenv("DATABASE_URL"):
    # Same fallback as fetch_contests.py for local verification only.
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://neondb_owner:npg_pBhM89cZikgE@ep-winter-heart-a7ysbm7f-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
    )

from app.api.api_v1.endpoints.rounds import _contest_eligible_at_ui_level
from app.crud.crud_contest import contest as contest_crud
from app.db.session import SessionLocal
from app.models.contest import Contest
from app.models.round import Round


def main() -> int:
    db = SessionLocal()
    failures = 0
    contest_id = 7
    round_id = 21
    try:
        c = db.query(Contest).filter(Contest.id == contest_id).first()
        r = db.query(Round).filter(Round.id == round_id).first()
        if not c or not r:
            print("Contest or round not found")
            return 1

        # 1) Regional list eligibility (cross-round season)
        reg_ok = _contest_eligible_at_ui_level(db, r, c, "nomination", "regional")
        print(f"[{'OK' if reg_ok else 'FAIL'}] regional eligible for list: {reg_ok}")
        if not reg_ok:
            failures += 1

        # 2) Continental detail must not use country season
        data = contest_crud.get_contest_with_enriched_contestants(
            db,
            contest_id=contest_id,
            current_user_id=None,
            filter_continent="Africa",
            entry_type="nomination",
            round_id=round_id,
            requested_ui_level="continental",
        )
        rows = (data or {}).get("contestants") or []
        season_level = (rows[0].get("season") or {}).get("level") if rows else None
        bad_continental = len(rows) > 0 and season_level not in ("continent", "continental")
        print(
            f"[{'OK' if not bad_continental else 'FAIL'}] continental detail count={len(rows)} season={season_level}"
        )
        if bad_continental:
            failures += 1

        # 3) List card count == detail roster for country
        card = contest_crud.count_nomination_roster_for_card(
            db,
            contest_id=contest_id,
            filter_country="Tanzania",
            entry_type="nomination",
            round_id=round_id,
            requested_ui_level="country",
        )
        detail_n = len(
            (contest_crud.get_contest_with_enriched_contestants(
                db,
                contest_id=contest_id,
                filter_country="Tanzania",
                entry_type="nomination",
                round_id=round_id,
                requested_ui_level="country",
            ) or {}).get("contestants")
            or []
        )
        match = card == detail_n
        print(f"[{'OK' if match else 'FAIL'}] country card={card} detail={detail_n}")
        if not match:
            failures += 1

        # 4) Regional card == detail when eligible
        if reg_ok:
            card_r = contest_crud.count_nomination_roster_for_card(
                db,
                contest_id=contest_id,
                filter_region="East Africa",
                entry_type="nomination",
                round_id=round_id,
                requested_ui_level="regional",
            )
            detail_r = len(
                (contest_crud.get_contest_with_enriched_contestants(
                    db,
                    contest_id=contest_id,
                    filter_region="East Africa",
                    entry_type="nomination",
                    round_id=round_id,
                    requested_ui_level="regional",
                ) or {}).get("contestants")
                or []
            )
            match_r = card_r == detail_r
            print(f"[{'OK' if match_r else 'FAIL'}] regional card={card_r} detail={detail_r}")
            if not match_r:
                failures += 1

        print(f"\n{failures} failure(s) — local code against live DB")
        return 1 if failures else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
