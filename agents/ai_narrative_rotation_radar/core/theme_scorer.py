"""
Theme scoring engine — RULE tier orchestrator.
Fetches data, computes all metrics, scores themes, detects rotation.
Returns a self-contained RadarSnapshot.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .breadth import ThemeBreadth, compute_theme_breadth
from .fetcher import fetch_price_history
from .leaps_signal import LEAPSCandidate, scan_leaps_candidates
from .metrics import TickerMetrics, compute_ticker_metrics
from .rotation import RotationSignal, detect_rotation

logger = logging.getLogger("radar.theme_scorer")


@dataclass
class RadarSnapshot:
    as_of: date
    ticker_metrics:    dict[str, TickerMetrics]  = field(default_factory=dict)
    theme_breadths:    dict[str, ThemeBreadth]   = field(default_factory=dict)
    benchmark_metrics: dict[str, TickerMetrics]  = field(default_factory=dict)
    rotation_signal:   Optional[RotationSignal]  = None
    leaps_candidates:  list[LEAPSCandidate]      = field(default_factory=list)
    ticker_to_theme:   dict[str, str]            = field(default_factory=dict)


def build_snapshot(
    cfg: dict,
    prior_snapshot: Optional[RadarSnapshot] = None,
) -> RadarSnapshot:
    """
    Full pipeline: fetch → metrics → breadth → rotation.
    prior_snapshot provides the historical baseline for rotation detection.
    """
    snapshot = RadarSnapshot(as_of=date.today())

    benchmarks    = cfg.get("benchmarks", ["SPY", "QQQ", "SOXX"])
    core_pool     = cfg.get("core_pool", [])
    secondary     = cfg.get("secondary_pool", [])
    themes_cfg    = cfg.get("themes", {})
    thresholds    = cfg.get("thresholds", {})

    all_tickers = list(set(core_pool + secondary + benchmarks))

    price_data = fetch_price_history(all_tickers)
    if not price_data:
        logger.error("No price data returned — aborting snapshot")
        return snapshot

    benchmark_dfs = {t: price_data[t] for t in benchmarks if t in price_data}

    # Compute metrics for all watchlist tickers
    for ticker in set(core_pool + secondary):
        if ticker not in price_data:
            continue
        try:
            snapshot.ticker_metrics[ticker] = compute_ticker_metrics(
                ticker, price_data[ticker], benchmark_dfs
            )
        except Exception as exc:
            logger.error("%s: metrics failed — %s", ticker, exc)

    # Benchmark metrics (for context in reports)
    for bench in benchmarks:
        if bench in price_data:
            try:
                snapshot.benchmark_metrics[bench] = compute_ticker_metrics(
                    bench, price_data[bench], benchmark_dfs
                )
            except Exception as exc:
                logger.error("%s: benchmark metrics failed — %s", bench, exc)

    # Theme breadths
    for theme_key, theme_cfg in themes_cfg.items():
        if theme_cfg.get("excluded_from_scoring"):
            continue
        try:
            snapshot.theme_breadths[theme_key] = compute_theme_breadth(
                theme_key,
                theme_cfg.get("name", theme_key),
                theme_cfg.get("tickers", []),
                snapshot.ticker_metrics,
                thresholds,
            )
        except Exception as exc:
            logger.error("Theme %s: breadth failed — %s", theme_key, exc)

    # Build ticker → primary theme mapping (first-write-wins for duplicates)
    for theme_key, theme_cfg in themes_cfg.items():
        if theme_cfg.get("excluded_from_scoring"):
            continue
        for ticker in theme_cfg.get("tickers", []):
            snapshot.ticker_to_theme.setdefault(ticker, theme_key)

    # Rotation detection vs prior snapshot
    if prior_snapshot and prior_snapshot.theme_breadths:
        try:
            snapshot.rotation_signal = detect_rotation(
                snapshot.theme_breadths,
                prior_snapshot.theme_breadths,
                thresholds,
            )
        except Exception as exc:
            logger.error("Rotation detection failed — %s", exc)

    # LEAPS candidate scan
    try:
        snapshot.leaps_candidates = scan_leaps_candidates(
            snapshot.ticker_metrics,
            snapshot.theme_breadths,
            snapshot.ticker_to_theme,
            cfg,
        )
    except Exception as exc:
        logger.error("LEAPS scan failed — %s", exc)

    logger.info(
        "Snapshot built: %d tickers, %d themes, rotation=%s, leaps=%d",
        len(snapshot.ticker_metrics),
        len(snapshot.theme_breadths),
        "YES" if snapshot.rotation_signal and snapshot.rotation_signal.detected else "NO",
        len(snapshot.leaps_candidates),
    )
    return snapshot
