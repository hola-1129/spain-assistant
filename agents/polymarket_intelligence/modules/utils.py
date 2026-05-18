from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def market_display_id(market: dict) -> str:
    return market.get("id") or market.get("conditionId") or "unknown"
