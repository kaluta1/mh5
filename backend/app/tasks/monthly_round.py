"""
Celery tasks: ensure the current calendar-month round exists (submission window).
Runs daily so a missed API restart on the 1st still creates e.g. Round June 2026.
"""
import logging

from app.celery_app import celery_app
from app.services.monthly_round_scheduler import monthly_round_scheduler

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.monthly_round.ensure_current_month_round",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def ensure_current_month_round(self):
    try:
        round_obj = monthly_round_scheduler.ensure_current_month_round()
        if round_obj:
            logger.info(
                "ensure_current_month_round: ok id=%s name=%s submission_open=%s",
                round_obj.id,
                round_obj.name,
                round_obj.is_submission_open,
            )
            return {
                "ok": True,
                "round_id": round_obj.id,
                "round_name": round_obj.name,
                "is_submission_open": round_obj.is_submission_open,
            }
        return {"ok": False, "error": "no round returned"}
    except Exception as exc:
        logger.error("ensure_current_month_round failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
