"""
Cron entry point: Contest Status Updater.

Can be invoked by a Python-friendly cron service (e.g. Render cron) or by an
HTTP-triggered job that calls the backend scheduler endpoint.
"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.contest_status import contest_status_scheduler
from app.services.cron_runner import run_scheduler_coro
import logging

logger = logging.getLogger(__name__)


def handler(request=None):
    """Cron handler for contest status updates."""
    try:
        run_scheduler_coro(contest_status_scheduler._check_contest_statuses())
        return {
            "statusCode": 200,
            "body": "Contest status cron job executed successfully",
        }
    except Exception as e:
        logger.error(f"Contest status cron job error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}",
        }


if __name__ == "__main__":
    result = handler()
    print(result["body"])
    sys.exit(0 if result["statusCode"] == 200 else 1)
