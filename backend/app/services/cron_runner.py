"""
Utilities for running scheduler coroutines from synchronous cron entry points.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def run_scheduler_coro(coro):
    """
    Run an async scheduler coroutine from a synchronous context (e.g. a cron
    script or a CLI entry point). Handles the common case where no event loop
    is running; if a loop is already running, schedule the coroutine on it and
    wait for the result.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    return asyncio.run(coro)
