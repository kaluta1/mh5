"""
HTTP endpoints for triggering background scheduler tasks.

These endpoints are meant to be called by Vercel Cron (via the frontend proxy
routes) or by any other authorized HTTP cron service. They are protected by a
shared CRON_SECRET that must be provided in the request header.
"""
import logging
from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import settings
from app.services.scheduler_manager import scheduler_manager

router = APIRouter()
logger = logging.getLogger(__name__)


def _verify_cron_secret(x_cron_secret: str | None):
    if not settings.CRON_SECRET:
        logger.error("CRON_SECRET is not configured on the backend.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cron authentication is not configured",
        )
    if not x_cron_secret or x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )


@router.post("/run/{task}")
async def run_scheduler_task(
    task: str,
    x_cron_secret: str | None = Header(None, alias="x-cron-secret"),
):
    """Run a single scheduler task once."""
    _verify_cron_secret(x_cron_secret)

    try:
        await scheduler_manager.run_task(task)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Scheduler task '{task}' failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scheduler task '{task}' failed: {str(e)}",
        )

    return {"status": "ok", "task": task}


@router.get("/tasks")
async def list_scheduler_tasks():
    """List available scheduler task names."""
    return {"tasks": scheduler_manager.list_tasks()}
