#!/usr/bin/env python3
"""AI Narrative Rotation Radar — entry point."""
from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from alerts.telegram_alert import TelegramAlert
from alerts.throttle import can_send, record_sent
from core.theme_scorer import RadarSnapshot, build_snapshot
from reports.daily import format_daily_summary, format_leaps_alert
from reports.weekly import format_weekly_review
from scheduler import RadarScheduler
from storage.db import RadarDB
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger("main")

_CFG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(_CFG_PATH) as f:
        cfg = yaml.safe_load(f)
    cfg["telegram_token"]    = os.environ["TELEGRAM_BOT_TOKEN"]
    cfg["telegram_chat_id"]  = os.environ["TELEGRAM_CHAT_ID"]
    cfg["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
    cfg["qwen_api_key"]      = os.getenv("QWEN_API_KEY", "")
    return cfg


class RadarRunner:
    def __init__(self, cfg: dict):
        self.cfg     = cfg
        self.alert   = TelegramAlert(cfg["telegram_token"], cfg["telegram_chat_id"])
        self.db      = RadarDB(cfg["storage"]["db_path"])
        self.log_dir = cfg["storage"]["log_dir"]
        self._last:  RadarSnapshot | None = None
        self._reporting_on = self._init_reporter()

    def _init_reporter(self) -> bool:
        """Initialise shared reporting layer. Returns True if enabled and ready."""
        if not self.cfg.get("reporting", {}).get("enabled", False):
            return False
        try:
            _ws = Path(__file__).resolve().parents[2]
            if str(_ws) not in sys.path:
                sys.path.insert(0, str(_ws))
            # Import eagerly to catch missing deps at startup, not at report time
            from shared.reporting import write_report, render_html, build_brief  # noqa: F401
            from shared.reporting.index_builder import build_daily_index, build_nav_index  # noqa: F401
            from shared.utils.telegram import TelegramNotifier  # noqa: F401
            from reporting.report_builder import RadarReportBuilder  # noqa: F401
            logger.info("Reporting layer initialised (reporting.enabled=true)")
            return True
        except Exception as exc:
            logger.warning("Reporting layer init failed (reporting disabled): %s", exc)
            return False

    def run_daily_close(self) -> None:
        logger.info("Running daily close analysis...")
        try:
            snapshot = build_snapshot(self.cfg, self._last)
            self.db.save_snapshot(snapshot)
            self.db.export_csv(self.cfg["storage"]["csv_export_dir"])

            if self._reporting_on:
                # New path: MD → HTML → Telegram brief (replaces full daily summary push)
                self._run_reporting_pipeline(snapshot)
            else:
                # Original path: full text → Telegram
                self.alert.send(format_daily_summary(snapshot))

            # Rotation and LEAPS alerts always fire (standalone, not part of daily report)
            self._maybe_send_rotation_alert(snapshot)
            self._maybe_send_leaps_alerts(snapshot)
            self._last = snapshot
            logger.info("Daily close complete")
        except Exception as exc:
            logger.error("Daily close failed: %s", exc, exc_info=True)

    def _run_reporting_pipeline(self, snapshot: RadarSnapshot) -> None:
        """Write MD + HTML, send Telegram brief. Errors are non-fatal."""
        try:
            import datetime
            from reporting.report_builder import RadarReportBuilder
            from shared.reporting import write_report, render_html, build_brief
            from shared.reporting.index_builder import build_daily_index, build_nav_index
            from shared.utils.telegram import TelegramNotifier

            date_str     = snapshot.as_of.isoformat()
            min_score    = self.cfg.get("leaps_signal", {}).get("min_leaps_score", 75.0)

            report = RadarReportBuilder().build(snapshot, date_str, min_leaps_score=min_score)
            write_report(report)
            render_html(report)
            build_daily_index(date_str)
            build_nav_index()

            brief    = build_brief(date_str, [report])
            notifier = TelegramNotifier.from_config(self.cfg)
            notifier.send(brief, parse_mode="Markdown")
            logger.info("Reporting pipeline complete for %s", date_str)
        except Exception as exc:
            logger.error("Reporting pipeline failed (non-fatal): %s", exc, exc_info=True)

    def run_weekly_review(self) -> None:
        logger.info("Running weekly review...")
        try:
            snapshot = build_snapshot(self.cfg, self._last)
            self.db.save_snapshot(snapshot)
            self.alert.send(format_weekly_review(snapshot, self._last))
            self._last = snapshot
            logger.info("Weekly review complete")
        except Exception as exc:
            logger.error("Weekly review failed: %s", exc, exc_info=True)

    def _maybe_send_rotation_alert(self, snapshot: RadarSnapshot) -> None:
        rot = snapshot.rotation_signal
        if not (rot and rot.detected):
            return
        min_confidence = self.cfg.get("thresholds", {}).get("rotation_confidence_min", 60)
        if rot.confidence < min_confidence:
            return

        throttle = self.cfg.get("alerts", {}).get("throttle", {})
        if not can_send(
            "ROTATION",
            self.log_dir,
            min_hours=throttle.get("min_hours_between_same_type", 4),
            max_per_day=throttle.get("max_alerts_per_day", 5),
        ):
            return

        self.alert.send(self._format_rotation_alert(snapshot))
        record_sent("ROTATION", self.log_dir)

    def _maybe_send_leaps_alerts(self, snapshot: RadarSnapshot) -> None:
        leaps_cfg       = self.cfg.get("leaps_signal", {})
        min_score       = leaps_cfg.get("min_leaps_score", 75)
        strong_score    = leaps_cfg.get("strong_leaps_score", 85)
        throttle        = self.cfg.get("alerts", {}).get("throttle", {})
        min_hours       = throttle.get("min_hours_between_same_type", 4)
        max_per_day     = throttle.get("max_alerts_per_day", 5)

        for c in snapshot.leaps_candidates:
            if c.leaps_score < min_score:
                continue
            alert_key = f"LEAPS_{c.ticker}"
            if not can_send(alert_key, self.log_dir, min_hours=min_hours, max_per_day=max_per_day):
                continue
            self.alert.send(format_leaps_alert(c, strong_threshold=strong_score))
            record_sent(alert_key, self.log_dir)

    def _format_rotation_alert(self, snapshot: RadarSnapshot) -> str:
        rot        = snapshot.rotation_signal
        to_names   = [
            snapshot.theme_breadths[k].theme_name
            for k in rot.to_themes[:2] if k in snapshot.theme_breadths
        ]
        from_names = [
            snapshot.theme_breadths[k].theme_name
            for k in rot.from_themes[:2] if k in snapshot.theme_breadths
        ]
        evidence = []
        for k in rot.to_themes[:3]:
            if k in snapshot.theme_breadths:
                b = snapshot.theme_breadths[k]
                evidence.append(
                    f"• {b.theme_name}: RS {b.avg_rs_spy_1m:+.1f}%, "
                    f"Breadth {b.breadth_rs*100:.0f}%, Vol {b.avg_volume_ratio:.1f}x"
                )
        return (
            f"🚨 *THEME ROTATION DETECTED*\n\n"
            f"*Rotation:*\n{' / '.join(from_names)} → {' / '.join(to_names)}\n\n"
            f"*Evidence:*\n" + "\n".join(evidence) + "\n\n"
            f"*Confidence:* {rot.confidence}/100\n\n"
            f"_Manual review required. Not a trading signal._"
        )


def main() -> None:
    try:
        cfg = load_config()
    except KeyError as exc:
        print(f"ERROR: Missing required env var: {exc}", file=sys.stderr)
        sys.exit(1)

    runner    = RadarRunner(cfg)
    scheduler = RadarScheduler(runner, cfg)

    def _shutdown(sig, frame):
        logger.info("Shutting down (signal %s)...", sig)
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("AI Narrative Rotation Radar v1 starting...")
    if cfg.get("alerts", {}).get("startup_message", True):
        runner.alert.send("✅ AI Narrative Rotation Radar started.")

    # Write PID file
    pid_path = Path(cfg["storage"]["log_dir"]) / "ai_narrative_rotation_radar.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))

    scheduler.start()


if __name__ == "__main__":
    main()
