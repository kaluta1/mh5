"""
Unified manager for all background scheduler tasks.

The manager owns the scheduler instances and exposes a single start/stop API
for the application lifespan, plus a run-now helper for cron endpoints.
"""
import asyncio
import logging
from typing import Dict, Any

from app.services.payment_scheduler import PaymentScheduler
from app.services.contest_status import ContestStatusScheduler
from app.services.season_migration_scheduler import SeasonMigrationScheduler
from app.services.monthly_round_scheduler import MonthlyRoundScheduler

logger = logging.getLogger(__name__)

# Task name -> (scheduler instance, coroutine factory name)
_SCHEDULER_CONFIG: Dict[str, tuple[Any, str]] = {
    "payments": (PaymentScheduler(), "_check_pending_payments"),
    "contest-status": (ContestStatusScheduler(), "_check_contest_statuses"),
    "season-migration": (SeasonMigrationScheduler(), "_process_migrations"),
    "monthly-round": (MonthlyRoundScheduler(), "ensure_month_and_run_migrations"),
    "monthly-ops": (MonthlyRoundScheduler(), "ensure_month_and_run_migrations"),
}


class BackgroundSchedulerManager:
    """Coordinates all background schedulers."""

    def __init__(self):
        self._schedulers: Dict[str, Any] = {
            name: config[0] for name, config in _SCHEDULER_CONFIG.items()
        }
        self._task_methods: Dict[str, str] = {
            name: config[1] for name, config in _SCHEDULER_CONFIG.items()
        }
        self._running = False

    async def start(self, delay_seconds: float = 10.0):
        """Start all registered schedulers after an optional warm-up delay."""
        if self._running:
            logger.warning("Background schedulers already running")
            return

        if delay_seconds > 0:
            logger.info(f"Waiting {delay_seconds}s before starting background schedulers...")
            await asyncio.sleep(delay_seconds)

        self._running = True
        for name, scheduler in self._schedulers.items():
            try:
                await scheduler.start()
                logger.info(f"{name} scheduler started")
            except Exception as e:
                logger.error(f"Failed to start {name} scheduler: {e}", exc_info=True)

    async def stop(self):
        """Stop all registered schedulers."""
        if not self._running:
            return
        self._running = False
        for name, scheduler in self._schedulers.items():
            try:
                await scheduler.stop()
                logger.info(f"{name} scheduler stopped")
            except Exception as e:
                logger.error(f"Failed to stop {name} scheduler: {e}", exc_info=True)

    async def run_task(self, name: str):
        """Run a single scheduler task once (used by cron endpoints/scripts)."""
        if name not in self._schedulers:
            raise ValueError(f"Unknown scheduler task: {name}. Valid: {list(self._schedulers)}")

        scheduler = self._schedulers[name]
        method_name = self._task_methods[name]
        method = getattr(scheduler, method_name)
        await method()

    def list_tasks(self):
        """Return the list of supported scheduler task names."""
        return list(self._schedulers.keys())


# Global manager instance used by the application lifespan and cron endpoints.
scheduler_manager = BackgroundSchedulerManager()
