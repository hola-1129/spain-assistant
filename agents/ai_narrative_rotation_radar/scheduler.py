"""
APScheduler configuration — daily close + weekly review jobs.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("radar.scheduler")


class RadarScheduler:
    def __init__(self, runner, cfg: dict):
        self._runner = runner
        sched_cfg    = cfg.get("schedule", {})
        self._dc_hour   = sched_cfg.get("daily_close_hour", 16)
        self._dc_minute = sched_cfg.get("daily_close_minute", 30)
        self._wr_hour   = sched_cfg.get("weekly_review_hour", 10)
        self._wr_minute = sched_cfg.get("weekly_review_minute", 0)
        self._sched = BlockingScheduler(timezone="America/New_York")

    def _register(self) -> None:
        self._sched.add_job(
            self._runner.run_daily_close,
            CronTrigger(
                day_of_week="mon-fri",
                hour=self._dc_hour,
                minute=self._dc_minute,
                timezone="America/New_York",
            ),
            id="daily_close",
            name="Daily Close Analysis",
            misfire_grace_time=600,
        )
        self._sched.add_job(
            self._runner.run_weekly_review,
            CronTrigger(
                day_of_week="sat",
                hour=self._wr_hour,
                minute=self._wr_minute,
                timezone="America/New_York",
            ),
            id="weekly_review",
            name="Weekly Narrative Review",
            misfire_grace_time=3600,
        )
        logger.info(
            "Scheduled: daily_close Mon-Fri %02d:%02d ET, weekly_review Sat %02d:%02d ET",
            self._dc_hour, self._dc_minute, self._wr_hour, self._wr_minute,
        )

    def start(self) -> None:
        self._register()
        logger.info("Scheduler starting (blocking)...")
        self._sched.start()

    def stop(self) -> None:
        self._sched.shutdown(wait=False)
        logger.info("Scheduler stopped")
