"""APScheduler integration for the autonomous publishing workflow.

Starts automatically with the FastAPI lifespan and shuts down gracefully.
``max_instances=1`` prevents overlapping publishing cycles.
"""

from datetime import timezone as dt_timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from publisher.config import settings
from publisher.database import SessionLocal
from publisher.services.publisher import publisher
from publisher.utils.logger import get_logger

logger = get_logger("publisher.scheduler")

JOB_ID = "publish_cycle"
MISFIRE_GRACE_SECONDS = 600


async def _publish_job() -> None:
    """Scheduler entry point: run one publishing cycle inside a session."""
    logger.info("Scheduler job started")
    async with SessionLocal() as session:
        await publisher.run_cycle(session)
    logger.info("Scheduler job finished")


class SchedulerManager:
    """Owns the single AsyncIOScheduler used by the application."""

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None

    @property
    def status(self) -> str:
        """Human-readable scheduler status for the dashboard."""
        if self._scheduler is not None and self._scheduler.running:
            return "running"
        return "stopped"

    @property
    def next_run_time(self) -> str | None:
        """ISO timestamp of the next scheduled run, if any."""
        if self._scheduler is None:
            return None
        job = self._scheduler.get_job(JOB_ID)
        if job is None or job.next_run_time is None:
            return None
        return job.next_run_time.isoformat()

    def start(self) -> None:
        """Configure and start the interval-triggered publishing job."""
        if not settings.scheduler_enabled:
            logger.info("Scheduler disabled via SCHEDULER_ENABLED=false")
            return

        self._scheduler = AsyncIOScheduler(timezone=dt_timezone.utc)
        self._scheduler.add_job(
            _publish_job,
            trigger=IntervalTrigger(
                minutes=settings.scheduler_interval_minutes,
                timezone=dt_timezone.utc,
            ),
            id=JOB_ID,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "Scheduler started: interval=%s minutes",
            settings.scheduler_interval_minutes,
        )

    def shutdown(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")


scheduler_manager = SchedulerManager()
