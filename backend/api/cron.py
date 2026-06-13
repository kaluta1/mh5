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
from app.services.cron_runner import run_scheduler_coro
import logging

logger = logging.getLogger(__name__)


def handler(request=None):
    """Combined cron handler that runs payment and contest-status checks."""
    try:
        run_scheduler_coro(payment_scheduler._check_pending_payments())
        run_scheduler_coro(contest_status_scheduler._check_contest_statuses())
        return {
            "statusCode": 200,
            "body": "Cron jobs executed successfully",
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
