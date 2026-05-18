"""
Alert throttle — RULE tier.
Prevents duplicate/spam alerts using a simple JSON state file.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("radar.throttle")


def _state_path(log_dir: str) -> Path:
    return Path(log_dir) / "alert_state.json"


def _load(log_dir: str) -> dict:
    p = _state_path(log_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save(log_dir: str, state: dict) -> None:
    p = _state_path(log_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def can_send(
    alert_type: str,
    log_dir: str,
    min_hours: int = 4,
    max_per_day: int = 5,
) -> bool:
    """Return True if alert_type is not throttled."""
    state    = _load(log_dir)
    now      = datetime.utcnow()
    today    = now.strftime("%Y-%m-%d")

    day_rec = state.get("day_count", {})
    if day_rec.get("date") != today:
        day_rec = {"date": today, "count": 0}
    if day_rec["count"] >= max_per_day:
        logger.info("Alert throttled: daily cap %d reached", max_per_day)
        return False

    last_sent = state.get("last_sent", {})
    if alert_type in last_sent:
        elapsed = now - datetime.fromisoformat(last_sent[alert_type])
        if elapsed < timedelta(hours=min_hours):
            logger.info("Alert throttled: %s sent %s ago", alert_type, elapsed)
            return False

    return True


def record_sent(alert_type: str, log_dir: str) -> None:
    """Record that an alert of alert_type was just sent."""
    state    = _load(log_dir)
    now      = datetime.utcnow()
    today    = now.strftime("%Y-%m-%d")

    day_rec = state.get("day_count", {"date": today, "count": 0})
    if day_rec.get("date") != today:
        day_rec = {"date": today, "count": 0}
    day_rec["count"] += 1

    last_sent = state.get("last_sent", {})
    last_sent[alert_type] = now.isoformat()

    state["day_count"] = day_rec
    state["last_sent"] = last_sent
    _save(log_dir, state)
