"""In-process asynchronous periodic pipeline scheduler."""

import asyncio
import logging
from typing import Optional

from app.config.settings import Settings, get_settings
from app.database.enums import PipelineRunStatus, TriggerType
from app.database.repositories import PipelineRunRepository
from app.database.session import async_session_factory
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Manages recurring, scheduled batch executions of the intelligence pipeline."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        """Return True if background scheduler loop is active."""
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the background scheduler task if enabled."""
        if not self.settings.scheduler_enabled:
            logger.info("Periodic pipeline scheduler is disabled via SCHEDULER_ENABLED=false.")
            return

        if self.is_running:
            logger.warning("Pipeline scheduler is already running.")
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(
            "Pipeline scheduler started (interval=%d minutes).",
            self.settings.scheduler_interval_minutes,
        )

    def stop(self) -> None:
        """Cancel and stop the background scheduler task."""
        if not self._running:
            return

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Pipeline scheduler stopped.")

    async def _scheduler_loop(self) -> None:
        """Internal asynchronous polling and execution loop."""
        interval_seconds = max(60, self.settings.scheduler_interval_minutes * 60)

        while self._running:
            try:
                # Wait for next interval
                await asyncio.sleep(interval_seconds)
                if not self._running:
                    break

                logger.info("Periodic scheduler triggering scheduled pipeline run...")
                async with async_session_factory() as session:
                    orchestrator = PipelineOrchestrator(session=session)
                    request = PipelineRunRequest(
                        sync_to_sheets=True,
                        trigger_type=TriggerType.SCHEDULED,
                    )
                    await orchestrator.run_pipeline(request)

            except asyncio.CancelledError:
                logger.info("Scheduler task cancelled.")
                break
            except Exception as exc:
                logger.error("Error during scheduled pipeline run: %s", exc, exc_info=True)


_global_scheduler: Optional[PipelineScheduler] = None


def get_scheduler() -> PipelineScheduler:
    """Return the global singleton instance of PipelineScheduler."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = PipelineScheduler()
    return _global_scheduler
