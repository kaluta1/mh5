"""
Combined cron entry point for background scheduler tasks.

This module is intended for Python-friendly cron services. For Vercel Cron,
the frontend proxy routes hit the backend scheduler endpoints instead.
"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.payment_scheduler import payment_scheduler
from app.services.contest_status import contest_status_scheduler
from app.services.season_migration_scheduler import season_migration_scheduler
from app.services.monthly_round_scheduler import monthly_round_scheduler
from app.services.cron_runner import run_scheduler_coro
import logging

logger = logging.getLogger(__name__)


def handler(request=None):
    """Combined cron handler: payments, contest status, season migrations."""
    try:
        run_scheduler_coro(payment_scheduler._check_pending_payments())
        run_scheduler_coro(contest_status_scheduler._check_contest_statuses())
        run_scheduler_coro(season_migration_scheduler._process_migrations())
        run_scheduler_coro(monthly_round_scheduler.ensure_month_and_run_migrations())
        return {
            "statusCode": 200,
            "body": "Cron jobs executed successfully (payments, contest-status, season-migration, monthly-round)",
        }
    except Exception as e:
        logger.error(f"Cron job error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}",
        }


if __name__ == "__main__":
    result = handler()
    print(result["body"])
    sys.exit(0 if result["statusCode"] == 200 else 1)
