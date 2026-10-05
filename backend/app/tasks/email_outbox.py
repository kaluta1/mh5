"""Celery task draining the email outbox (used when USE_CELERY replaces the
in-process schedulers)."""
import logging

from app.celery_app import celery_app
from app.core.config import settings
from app.services.email_outbox import outbox_executor, run_outbox_once

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.email_outbox.drain_email_outbox")
def drain_email_outbox():
    if not settings.EMAIL_OUTBOX_ENABLED:
        return {"enabled": False}
    if outbox_executor() != "celery":
        # Without USE_CELERY=true the web process drains the outbox itself.
        return {"skipped": "in-process scheduler is the executor"}
    try:
        return run_outbox_once()
    except Exception as exc:  # noqa: BLE001
        logger.error("Email outbox pass failed: %s", type(exc).__name__)
        return {"error": type(exc).__name__}
