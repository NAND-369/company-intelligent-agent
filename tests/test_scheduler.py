"""Tests for the in-process pipeline scheduler."""

import asyncio
import pytest

from app.config.settings import Settings
from app.core.scheduler import PipelineScheduler, get_scheduler


def test_scheduler_disabled_by_default() -> None:
    """Verify scheduler does not start when SCHEDULER_ENABLED is false."""
    settings = Settings(scheduler_enabled=False)
    scheduler = PipelineScheduler(settings=settings)

    scheduler.start()
    assert scheduler.is_running is False
    scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_starts_and_stops_cleanly() -> None:
    """Verify scheduler loop starts and cancels gracefully."""
    settings = Settings(scheduler_enabled=True, scheduler_interval_minutes=1)
    scheduler = PipelineScheduler(settings=settings)

    scheduler.start()
    assert scheduler.is_running is True

    # Allow task loop to initialize
    await asyncio.sleep(0.01)

    scheduler.stop()
    assert scheduler.is_running is False


def test_get_scheduler_singleton() -> None:
    """Verify get_scheduler returns consistent singleton instance."""
    s1 = get_scheduler()
    s2 = get_scheduler()
    assert s1 is s2
