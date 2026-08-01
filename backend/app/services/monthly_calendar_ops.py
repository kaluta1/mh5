"""
First-of-month and daily calendar operations: ensure round + season migrations.

Run from schedulers, cron, or deploy scripts so nominations promote on the 1st
(country → regional → continental → global) without manual intervention.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.contest_status import contest_status_service
from app.services.monthly_round_scheduler import (
    close_stale_voting_rounds,
    dedupe_submission_month_rounds,
    monthly_round_scheduler,
)
from app.services.season_migration import season_migration_service

logger = logging.getLogger(__name__)


def run_season_migrations(db: Session, *, today: date | None = None) -> Dict[str, Any]:
    """
    Run season migration pipeline with multi-pass hops.

    Always allow multi-hop + up to 4 passes so backlog clears even after the 1st
    (e.g. June COUNTRY→REGIONAL then May REGIONAL→CONTINENT on the same run).
    """
    today = today or date.today()
    max_passes = 4
    combined: Dict[str, Any] = {"processed": 0, "results": [], "passes": 0}

    for pass_num in range(max_passes):
        out = season_migration_service.check_and_process_migrations(
            db, allow_multi_hop=True
        )
        if not isinstance(out, dict):
            break
        results = out.get("results") or []
        # Count only real promotions so empty skips do not burn all passes.
        real = [
            r
            for r in results
            if isinstance(r.get("result"), dict)
            and not r["result"].get("skipped")
            and not r["result"].get("error")
        ]
        n = len(real)
        combined["passes"] = pass_num + 1
        combined["processed"] = int(combined["processed"]) + n
        combined["results"].extend(results)
        logger.info(
            "Season migration pass %s/%s: real_promotions=%s total_actions=%s",
            pass_num + 1,
            max_passes,
            n,
            len(results),
        )
        if n == 0:
            break

    return combined


def run_monthly_calendar_ops(db: Session | None = None) -> Dict[str, Any]:
    """
    Full calendar pipeline:
    1. Dedupe / close stale vote flags
    2. Ensure all official nomination cohort rounds (March…current) exist
    3. Ensure current-month round + link contests
    4. Sync contest open/close flags
    5. Run all due season migrations (multi-pass backlog)
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    today = date.today()
    summary: Dict[str, Any] = {
        "date": today.isoformat(),
        "is_first_of_month": today.day == 1,
    }

    try:
        dedupe_submission_month_rounds(db, today)
        close_stale_voting_rounds(db, today)

        from app.services.monthly_round_scheduler import ensure_nomination_cohort_rounds

        cohort_rounds = ensure_nomination_cohort_rounds(db, today)
        summary["cohort_rounds"] = [
            {"id": r.id, "name": r.name} for r in cohort_rounds if r is not None
        ]

        rnd = monthly_round_scheduler.ensure_current_month_round()
        summary["round"] = (
            {"id": rnd.id, "name": rnd.name} if rnd else None
        )

        try:
            contest_status_service.update_contest_statuses(db)
            db.commit()
        except Exception as exc:
            logger.warning("contest status sync failed: %s", exc)
            db.rollback()

        migration = run_season_migrations(db, today=today)
        summary["migration"] = migration
        logger.info(
            "Monthly calendar ops complete: round=%s migrations_processed=%s passes=%s",
            summary.get("round"),
            migration.get("processed"),
            migration.get("passes"),
        )
        return summary
    finally:
        if own_session and db is not None:
            db.close()


def run_monthly_calendar_ops_sync() -> Dict[str, Any]:
    """Thread-safe entry for asyncio schedulers."""
    return run_monthly_calendar_ops()
