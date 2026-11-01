"""Background worker for advertising (one of the application's schedulers)."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def run_once(session_factory) -> dict:
    from app.services import ad_delivery, ad_revenue_sharing

    result = ad_delivery.run_cycle(session_factory)
    db = session_factory()
    try:
        result["claimed_released"] = ad_revenue_sharing.release_claimed(db)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("Ad share claim release failed: %s", type(exc).__name__)
    finally:
        db.close()
    return result


class AdDeliveryScheduler:
    def __init__(self, interval_seconds: Optional[int] = None):
        self.interval = max(int(interval_seconds or os.getenv("AD_WORKER_INTERVAL_SECONDS", "30")), 10)
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Ad delivery worker started (interval: %ss)", self.interval)

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        await asyncio.sleep(30)
        while self.running:
            try:
                await self._run_pass()
            except Exception as exc:  # noqa: BLE001 - the scheduler must never die
                logger.error("Ad delivery pass failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval)

    async def _run_pass(self):
        from app.db.session import SessionLocal

        await asyncio.to_thread(run_once, SessionLocal)
