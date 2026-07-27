#!/usr/bin/env python3
"""
One-shot ops script (run on VPS after deploy or on the 1st of the month):

  1. Create / fix Round {Current Month YYYY} (submission open, contests linked)
  2. Run all pending season migrations (country → regional → continent → global)

Usage (from repo root ~/mh5 — do not use bare system python3; no pydantic there):

  bash backend/scripts/run_ensure_month_round_and_migrations.sh

Or inside a running API container (backend-app):

  docker exec -i backend-app python scripts/ensure_month_round_and_migrations.py

Or with backend/.venv:

  cd backend && source .venv/bin/activate && pip install -r requirements.txt
  export PYTHONPATH=.
  python scripts/ensure_month_round_and_migrations.py
"""
from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Ensure current month round + run migrations")
    parser.add_argument(
        "--june-2026-only",
        action="store_true",
        help="Only create Round June 2026 (target_date=2026-06-01) then exit",
    )
    args = parser.parse_args()

    from datetime import date

    from app.db.session import SessionLocal
    from app.models.round import Round
    from app.scripts.generate_monthly_rounds import generate_monthly_round
    from app.services.monthly_calendar_ops import run_monthly_calendar_ops

    if args.june_2026_only:
        db = SessionLocal()
        try:
            rnd = generate_monthly_round(db, target_date=date(2026, 6, 1))
            sync_round_calendar_flags(db, rnd)
            link_active_contests_to_round(db, rnd.id)
            print(f"OK: {rnd.name} id={rnd.id} submission_open={rnd.is_submission_open}")
        finally:
            db.close()
        return 0

    logger.info("=== Monthly calendar ops (round + migrations) ===")
    summary = run_monthly_calendar_ops()
    rnd_info = summary.get("round") or {}
    mig = summary.get("migration") or {}
    processed = int(mig.get("processed") or 0)
    print(
        f"Round: {rnd_info!r} | migrations processed: {processed} "
        f"(passes={mig.get('passes')}) first_of_month={summary.get('is_first_of_month')}"
    )

    # Repair stale country links/memberships after promotion (idempotent).
    try:
        from scripts.repair_dual_stage_visibility import main as repair_dual_visibility

        logger.info("=== Repair dual country+regional visibility ===")
        repair_dual_visibility(apply=True)
    except Exception as exc:
        logger.warning("Dual-stage repair skipped or failed: %s", exc)
    for item in mig.get("results", []) or []:
        cid = item.get("contest_id")
        action = item.get("action")
        res = item.get("result") or {}
        if isinstance(res, dict) and res.get("error"):
            print(f"  contest {cid} {action}: ERROR {res.get('error')}")
        elif isinstance(res, dict) and res.get("skipped"):
            print(f"  contest {cid} {action}: skip {res.get('message', '')[:80]}")
        else:
            n = len(res.get("promoted_contestant_ids") or []) if isinstance(res, dict) else 0
            print(f"  contest {cid} {action}: promoted={n}")

    db = SessionLocal()
    try:
        logger.info("=== Round snapshot ===")
        rows = (
            db.query(Round)
            .filter(Round.name.ilike("%2026%"))
            .order_by(Round.id.asc())
            .all()
        )
        for r in rows[-6:]:
            print(
                f"  id={r.id} {r.name!r} status={r.status} "
                f"sub_open={r.is_submission_open} vote_open={r.is_voting_open} "
                f"country={r.country_season_start_date}..{r.country_season_end_date} "
                f"regional={r.regional_start_date}..{r.regional_end_date}"
            )
    finally:
        db.close()

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
