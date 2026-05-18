"""
Theme breadth analysis — RULE tier.
Computes breadth, participation, and leadership for each theme basket.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from .metrics import TickerMetrics

logger = logging.getLogger("radar.breadth")


@dataclass
class ThemeBreadth:
    theme_key: str
    theme_name: str
    as_of: date

    total_tickers: int = 0
    tickers_positive_rs_1m: int = 0
    tickers_above_20dma: int = 0
    tickers_above_50dma: int = 0

    # Participation ratios (0.0–1.0)
    breadth_rs: float = 0.0       # % with positive RS vs SPY 1M
    breadth_20dma: float = 0.0
    breadth_50dma: float = 0.0

    # Theme averages
    avg_rs_spy_1m: float = 0.0
    avg_rs_spy_1d: float = 0.0
    avg_volume_ratio: float = 1.0

    leaders: list[str] = field(default_factory=list)   # top 2 by RS 1M
    laggards: list[str] = field(default_factory=list)  # bottom 2

    breadth_score: float = 0.0    # composite 0–100
    signal: str = "NEUTRAL"       # STRONG / BROADENING / NEUTRAL / NARROWING / WEAK


def compute_theme_breadth(
    theme_key: str,
    theme_name: str,
    tickers: list[str],
    metrics: dict[str, TickerMetrics],
    thresholds: dict,
) -> ThemeBreadth:
    """Compute breadth metrics for one theme basket."""
    b = ThemeBreadth(theme_key=theme_key, theme_name=theme_name, as_of=date.today())

    available = [t for t in tickers if t in metrics]
    b.total_tickers = len(available)
    if b.total_tickers == 0:
        return b

    m_list = [metrics[t] for t in available]

    b.tickers_positive_rs_1m = sum(1 for m in m_list if m.rs_vs_spy_1m > 0)
    b.tickers_above_20dma    = sum(1 for m in m_list if m.above_20dma)
    b.tickers_above_50dma    = sum(1 for m in m_list if m.above_50dma)

    b.breadth_rs    = b.tickers_positive_rs_1m / b.total_tickers
    b.breadth_20dma = b.tickers_above_20dma    / b.total_tickers
    b.breadth_50dma = b.tickers_above_50dma    / b.total_tickers

    b.avg_rs_spy_1m    = sum(m.rs_vs_spy_1m    for m in m_list) / b.total_tickers
    b.avg_rs_spy_1d    = sum(m.rs_vs_spy_1d    for m in m_list) / b.total_tickers
    b.avg_volume_ratio = sum(m.volume_ratio_20d for m in m_list) / b.total_tickers

    ranked = sorted(m_list, key=lambda m: m.rs_vs_spy_1m, reverse=True)
    b.leaders  = [m.ticker for m in ranked[:2]]
    b.laggards = [m.ticker for m in ranked[-2:]]

    # Composite breadth score 0–100
    b.breadth_score = (b.breadth_rs * 0.6 + b.breadth_20dma * 0.4) * 100

    expand_min = thresholds.get("breadth_expansion_min", 0.6)
    narrow_max = thresholds.get("breadth_narrow_max", 0.3)
    rs_strong  = thresholds.get("rs_strong_threshold", 3.0)
    rs_weak    = thresholds.get("rs_weak_threshold", -3.0)

    if b.breadth_rs >= expand_min and b.avg_rs_spy_1m >= rs_strong:
        b.signal = "STRONG"
    elif b.breadth_rs >= expand_min:
        b.signal = "BROADENING"
    elif b.breadth_rs <= narrow_max and b.avg_rs_spy_1m <= rs_weak:
        b.signal = "WEAK"
    elif b.breadth_rs <= narrow_max:
        b.signal = "NARROWING"
    else:
        b.signal = "NEUTRAL"

    return b
