"""
core/scheduler.py — Task Scheduler
=====================================
Wraps APScheduler with a clean, simple interface used throughout the assistant.

APScheduler supports:
- Cron-style jobs  (``add_cron_job``)
- Interval jobs    (``add_interval_job``)
- One-shot jobs    (``add_once_job``)

Jobs are kept in memory (not persisted to disk in this baseline).
To survive restarts, swap ``MemoryJobStore`` for ``SQLAlchemyJobStore`` later.

Usage
-----
    from core.scheduler import TaskScheduler

    scheduler = TaskScheduler(timezone="UTC")
    scheduler.start()

    # Run a function every 5 minutes
    scheduler.add_interval_job(
        func=my_function,
        job_id="my_job",
        minutes=5,
    )

    # Run at a cron schedule
    scheduler.add_cron_job(
        func=daily_report,
        job_id="daily_report",
        hour=8, minute=0,
    )

    # One-shot 10 seconds from now
    from datetime import datetime, timedelta
    scheduler.add_once_job(
        func=send_alert,
        job_id="alert_once",
        run_at=datetime.now() + timedelta(seconds=10),
    )
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.logger import get_logger

log = get_logger(__name__)


class TaskScheduler:
    """
    Application-level task scheduler.

    Wraps APScheduler's BackgroundScheduler so the rest of the codebase
    doesn't need to import APScheduler directly.
    """

    def __init__(self, timezone: str = "UTC", misfire_grace_time: int = 60) -> None:
        """
        Parameters
        ----------
        timezone           : Timezone string used for cron jobs, e.g. "Europe/London".
        misfire_grace_time : Seconds a job may be late before APScheduler skips it.
        """
        self._scheduler = BackgroundScheduler(
            timezone=timezone,
            job_defaults={"misfire_grace_time": misfire_grace_time},
        )
        self._timezone = timezone

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background scheduler thread."""
        if not self._scheduler.running:
            self._scheduler.start()
            log.info(f"Scheduler started (timezone={self._timezone})")

    def shutdown(self, wait: bool = True) -> None:
        """
        Stop the scheduler gracefully.

        Parameters
        ----------
        wait : If True, wait for currently running jobs to finish.
        """
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            log.info("Scheduler stopped")

    # ── Job registration ───────────────────────────────────────────────────────

    def add_interval_job(
        self,
        func: Callable,
        job_id: str,
        *,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        kwargs: dict[str, Any] | None = None,
        replace_existing: bool = True,
    ) -> None:
        """
        Run *func* repeatedly at the specified interval.

        At least one time unit must be > 0.

        Example
        -------
        scheduler.add_interval_job(check_weather, "weather", minutes=30)
        """
        trigger = IntervalTrigger(
            weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds,
            timezone=self._timezone,
        )
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs or {},
            replace_existing=replace_existing,
        )
        log.info(f"Scheduled interval job: {job_id!r}")

    def add_cron_job(
        self,
        func: Callable,
        job_id: str,
        *,
        year: str | int | None = None,
        month: str | int | None = None,
        day: str | int | None = None,
        week: str | int | None = None,
        day_of_week: str | int | None = None,
        hour: str | int | None = None,
        minute: str | int | None = None,
        second: str | int | None = None,
        kwargs: dict[str, Any] | None = None,
        replace_existing: bool = True,
    ) -> None:
        """
        Run *func* on a cron schedule.

        Accepts the same field names and values as standard cron expressions
        (including ranges like "0-5" and lists like "1,3,5").

        Example
        -------
        # Every weekday at 08:00
        scheduler.add_cron_job(morning_brief, "morning", day_of_week="mon-fri", hour=8)
        """
        trigger = CronTrigger(
            year=year, month=month, day=day, week=week,
            day_of_week=day_of_week, hour=hour, minute=minute, second=second,
            timezone=self._timezone,
        )
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs or {},
            replace_existing=replace_existing,
        )
        log.info(f"Scheduled cron job: {job_id!r}")

    def add_once_job(
        self,
        func: Callable,
        job_id: str,
        *,
        run_at: datetime,
        kwargs: dict[str, Any] | None = None,
        replace_existing: bool = True,
    ) -> None:
        """
        Run *func* exactly once at *run_at*.

        Example
        -------
        from datetime import datetime, timedelta
        scheduler.add_once_job(send_reminder, "reminder", run_at=datetime.now()+timedelta(hours=1))
        """
        trigger = DateTrigger(run_date=run_at, timezone=self._timezone)
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs or {},
            replace_existing=replace_existing,
        )
        log.info(f"Scheduled one-shot job: {job_id!r} at {run_at.isoformat()}")

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job by ID.

        Returns True if the job existed and was removed, False if not found.
        """
        try:
            self._scheduler.remove_job(job_id)
            log.info(f"Removed job: {job_id!r}")
            return True
        except Exception:
            return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return a summary of all currently scheduled jobs."""
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]

    @property
    def running(self) -> bool:
        """True if the scheduler background thread is active."""
        return self._scheduler.running
