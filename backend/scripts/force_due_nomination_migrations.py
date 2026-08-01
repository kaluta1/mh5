#!/usr/bin/env python3
"""
Force all due nomination migrations (country → regional → continental → global).

On August 1 this promotes:
  - June cohort: COUNTRY → REGIONAL
  - May cohort: REGIONAL → CONTINENTAL (after regional exists)
  - April cohort: CONTINENT → GLOBAL (after continental exists)
  - plus any backlog from earlier months

Usage (VPS):
  cd /root/mh5/backend && source .venv/bin/activate
  export PYTHONPATH=/root/mh5/backend
  python scripts/force_due_nomination_migrations.py
"""
from __future__ import annotations

import logging
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    from datetime import date

    from app.db.session import SessionLocal
    from app.models.contests import ContestSeason, ContestSeasonLink, SeasonLevel
    from app.models.round import Round
    from app.services.monthly_calendar_ops import run_monthly_calendar_ops

    today = date.today()
    print(f"=== Force due nomination migrations ({today.isoformat()}) ===")
    print("Expected Vote chips today:")
    print("  Country      → cohort month - 1")
    print("  Regional     → cohort month - 2  (June in August)")
    print("  Continental  → cohort month - 3  (May in August)")
    print("  Global       → cohort month - 4  (April in August)")

    summary = run_monthly_calendar_ops()
    mig = summary.get("migration") or {}
    print(
        f"\nRound: {summary.get('round')!r}\n"
        f"Cohort rounds ensured: {len(summary.get('cohort_rounds') or [])}\n"
        f"Migrations processed: {mig.get('processed')} (passes={mig.get('passes')})"
    )

    for item in mig.get("results") or []:
        cid = item.get("contest_id")
        action = item.get("action")
        res = item.get("result") or {}
        if not isinstance(res, dict):
            continue
        if res.get("error"):
            print(f"  contest {cid} {action}: ERROR {res.get('error')}")
        elif res.get("skipped"):
            print(f"  contest {cid} {action}: skip {str(res.get('message') or '')[:90]}")
        else:
            n = len(res.get("promoted_contestant_ids") or [])
            print(f"  contest {cid} {action}: promoted={n}")

    db = SessionLocal()
    try:
        print("\n=== Active nomination season links by round/level ===")
        rounds = (
            db.query(Round)
            .filter(Round.name.ilike("%2026%"))
            .order_by(Round.id.asc())
            .all()
        )
        for rnd in rounds:
            counts = {}
            for level in (
                SeasonLevel.COUNTRY,
                SeasonLevel.REGIONAL,
                SeasonLevel.CONTINENT,
                SeasonLevel.GLOBAL,
            ):
                n = (
                    db.query(ContestSeasonLink)
                    .join(ContestSeason, ContestSeason.id == ContestSeasonLink.season_id)
                    .filter(
                        ContestSeason.round_id == rnd.id,
                        ContestSeason.level == level,
                        ContestSeason.is_deleted == False,
                        ContestSeasonLink.is_active == True,
                    )
                    .count()
                )
                counts[level.value] = n
            print(
                f"  {rnd.name} (id={rnd.id}): "
                f"country={counts['country']} regional={counts['regional']} "
                f"continent={counts['continent']} global={counts['global']}"
            )
    finally:
        db.close()

    print("\nDone. Refresh Vote → Regional / Continental / Global.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
