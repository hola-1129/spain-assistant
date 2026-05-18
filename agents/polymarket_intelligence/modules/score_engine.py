from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from modules.market_filter import priority_keyword_match

logger = logging.getLogger("polymarket_intelligence.score")


def _market_spread(market: dict) -> Optional[float]:
    try:
        bid = float(market.get("bestBid") or 0)
        ask = float(market.get("bestAsk") or 0)
        if bid > 0 and ask > 0:
            return round(ask - bid, 4)
    except (ValueError, TypeError):
        pass
    return None


def _hours_to_close(market: dict) -> Optional[float]:
    end_date = market.get("endDate") or market.get("end_date")
    if not end_date:
        return None
    try:
        end_dt = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
        return (end_dt - datetime.now(timezone.utc)).total_seconds() / 3600
    except Exception:
        return None


def score_signal(signal: dict, market: dict, cfg: dict) -> int:
    score = 0
    signal_type = signal.get("signal_type", "")

    if "rapid_reprice_5m" in signal_type:
        score += 35
    elif "rapid_reprice_15m" in signal_type:
        score += 30
    elif "rapid_reprice_60m" in signal_type:
        score += 25
    elif "liquidity_spike" in signal_type:
        score += 20

    matched_kw = priority_keyword_match(market, cfg.get("priority_keywords", []))
    if matched_kw:
        score += 20

    volume = float(market.get("volume", 0) or 0)
    liquidity = float(market.get("liquidity", 0) or 0)
    spread = _market_spread(market)
    max_spread = float(cfg.get("max_spread", 0.08))

    if volume > 250000:
        score += 10
    if liquidity > 100000:
        score += 10
    if spread is not None and spread <= 0.04:
        score += 10
    if spread is not None and spread > max_spread:
        score -= 20
    if volume < 50000:
        score -= 20

    hours_left = _hours_to_close(market)
    if hours_left is not None and hours_left < 6:
        score -= 15

    final = max(0, min(score, 100))
    logger.debug(f"Score {final}/100 for market {market.get('id')}")
    return final
