from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("polymarket_intelligence.signal")


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def detect_rapid_reprice(
    market_id: str,
    current: dict,
    recent: list[dict],
    windows: list[int],
    min_moves: dict,
) -> list[dict]:
    current_price = current.get("yes_price")
    if current_price is None:
        return []

    now = datetime.now(timezone.utc)
    signals = []

    for window in windows:
        threshold = min_moves.get(f"window_{window}m")
        if threshold is None:
            continue

        oldest_price: Optional[float] = None
        for snap in recent:
            snap_ts = _parse_ts(snap.get("timestamp", ""))
            if snap_ts is None:
                continue
            if (now - snap_ts).total_seconds() / 60 <= window:
                p = snap.get("yes_price")
                if p is not None and oldest_price is None:
                    oldest_price = p

        if oldest_price is None:
            continue

        delta = abs(current_price - oldest_price)
        if delta >= threshold:
            signals.append({
                "market_id": market_id,
                "timestamp": now.isoformat(),
                "signal_type": f"rapid_reprice_{window}m",
                "probability_before": oldest_price,
                "probability_after": current_price,
                "probability_delta": round(current_price - oldest_price, 4),
                "window_minutes": window,
                "liquidity_delta": None,
                "reason": (
                    f"Rapid {window}m move: {oldest_price:.1%} → {current_price:.1%}"
                    f" (Δ{current_price - oldest_price:+.1%})"
                ),
            })
            logger.info(
                f"Signal [rapid_reprice_{window}m] market={market_id}"
                f" delta={delta:.3f}"
            )

    return signals


def detect_liquidity_spike(
    market_id: str,
    current: dict,
    recent: list[dict],
    min_absolute: float = 10000.0,
    min_ratio: float = 1.5,
) -> list[dict]:
    current_liq = float(current.get("liquidity") or 0)
    if not recent:
        return []

    prev_liq: Optional[float] = None
    for snap in recent:
        v = snap.get("liquidity")
        if v is not None:
            fv = float(v)
            if prev_liq is None or fv < prev_liq:
                prev_liq = fv

    if prev_liq is None or prev_liq == 0:
        return []

    absolute_increase = current_liq - prev_liq
    if absolute_increase < min_absolute:
        return []
    if current_liq < prev_liq * min_ratio:
        return []

    now = datetime.now(timezone.utc)
    logger.info(
        f"Signal [liquidity_spike] market={market_id}"
        f" prev={prev_liq:,.0f} current={current_liq:,.0f}"
    )
    return [{
        "market_id": market_id,
        "timestamp": now.isoformat(),
        "signal_type": "liquidity_spike",
        "probability_before": None,
        "probability_after": None,
        "probability_delta": None,
        "window_minutes": None,
        "liquidity_delta": round(absolute_increase, 2),
        "reason": (
            f"Liquidity spike: ${prev_liq:,.0f} → ${current_liq:,.0f}"
            f" (+${absolute_increase:,.0f})"
        ),
    }]
