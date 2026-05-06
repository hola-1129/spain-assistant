"""Per-asset inflection detector: combines signals into a confluence score."""
from typing import Optional

import pandas as pd

from signals.base import InflectionEvent, Signal
from signals.momentum import analyze_momentum
from signals.volatility import analyze_volatility
from signals.volume import analyze_volume

# 每种信号的基础权重（越重要权重越高）
_WEIGHTS = {
    "golden_cross":      3.0,
    "death_cross":       3.0,
    "break_ma200":       2.5,
    "reclaim_ma200":     2.5,
    "macd_golden":            1.8,
    "macd_death":             1.8,
    "macd_line_cross_up":     1.4,
    "macd_line_cross_down":   1.4,
    "rsi_divergence_bull":    1.6,
    "rsi_divergence_bear":    1.6,
    "break_ma50":        1.5,
    "reclaim_ma50":      1.5,
    "volume_spike":      1.8,
    "atr_expansion":     1.2,
    "bb_break_down":     1.4,
    "bb_break_up":       1.0,
    "near_52w_high":     1.2,
    "near_52w_low":      1.2,
    "rsi_oversold":      1.0,
    "rsi_overbought":    1.0,
    "rsi_cross_up":      0.8,
    "rsi_cross_down":    0.8,
    "bb_squeeze":        0.6,
    "volume_mild_spike": 0.5,
    "volume_dryup":      0.3,
}


def detect_inflection(
    symbol: str,
    hist: pd.DataFrame,
    min_score: float = 2.5,
) -> Optional[InflectionEvent]:
    """
    Returns an InflectionEvent if multiple signals align (score >= min_score),
    otherwise None.
    """
    all_signals = (
        analyze_momentum(symbol, hist)
        + analyze_volatility(symbol, hist)
        + analyze_volume(symbol, hist)
    )

    if not all_signals:
        return None

    score = sum(_WEIGHTS.get(s.kind, 0.5) * s.strength for s in all_signals)
    score = min(round(score, 1), 10.0)

    if score < min_score:
        return None

    bullish = sum(1 for s in all_signals if s.direction == "bullish")
    bearish = sum(1 for s in all_signals if s.direction == "bearish")
    direction = ("bullish" if bullish > bearish
                 else "bearish" if bearish > bullish
                 else "mixed")

    # sort: high-weight signals first
    ranked = sorted(all_signals,
                    key=lambda s: _WEIGHTS.get(s.kind, 0.5) * s.strength,
                    reverse=True)

    return InflectionEvent(
        symbol=symbol,
        score=score,
        direction=direction,
        signals=ranked[:6],   # top 6 signals in the message
    )
