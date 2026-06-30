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
    """Run season migration pipeline (multi-pass on the 1st of the month)."""
    today = today or date.today()
    max_passes = 4 if today.day == 1 else 1
    combined: Dict[str, Any] = {"processed": 0, "results": [], "passes": 0}

    for pass_num in range(max_passes):
        out = season_migration_service.check_and_process_migrations(
            db, allow_multi_hop=(today.day == 1)
        )
        if not isinstance(out, dict):
            break
        n = int(out.get("processed") or 0)
        combined["passes"] = pass_num + 1
        combined["processed"] = int(combined["processed"]) + n
        combined["results"].extend(out.get("results") or [])
        if n == 0:
            break
        logger.info(
            "Season migration pass %s/%s: processed=%s",
            pass_num + 1,
            max_passes,
            n,
        )

    return combined


def run_monthly_calendar_ops(db: Session | None = None) -> Dict[str, Any]:
    """
    Full calendar pipeline:
    1. Dedupe / close stale vote flags
    2. Ensure current-month round + link contests
    3. Sync contest open/close flags
    4. Run all due season migrations (multi-pass on day 1)
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
