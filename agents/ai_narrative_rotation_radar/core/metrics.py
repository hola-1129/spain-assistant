"""
Signal computation — RULE tier. Pure math, no LLM.
Computes per-ticker RS, MA structure, volume, and drawdown metrics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

logger = logging.getLogger("radar.metrics")


@dataclass
class TickerMetrics:
    ticker: str
    as_of: date

    last_close: float = 0.0

    ret_1d: float = 0.0
    ret_5d: float = 0.0
    ret_1m: float = 0.0
    ret_3m: float = 0.0
    ret_ytd: float = 0.0

    # Excess return vs benchmarks (ticker_return - benchmark_return)
    rs_vs_spy_1d: float = 0.0
    rs_vs_spy_5d: float = 0.0
    rs_vs_spy_1m: float = 0.0
    rs_vs_qqq_1m: float = 0.0
    rs_vs_soxx_1m: float = 0.0

    above_20dma: bool = False
    above_50dma: bool = False
    above_200dma: bool = False
    ma20_slope: float = 0.0   # % change of MA(20) over 5 days
    ma50_slope: float = 0.0
    ma50_value: float = 0.0   # actual 50DMA price (for extension calculation)

    volume_ratio_20d: float = 1.0    # today's volume / 20D average
    drawdown_from_52w_high: float = 0.0

    composite_score: float = 0.0     # simple summary score


# ── helpers ──────────────────────────────────────────────────────────────────

def _ret_n(df: pd.DataFrame, n: int) -> float:
    closes = df["Close"].dropna()
    if len(closes) < n + 1:
        return 0.0
    return float((closes.iloc[-1] / closes.iloc[-(n + 1)] - 1) * 100)


def _ma(df: pd.DataFrame, n: int) -> float:
    closes = df["Close"].dropna()
    if len(closes) < n:
        return float(closes.mean()) if not closes.empty else 0.0
    return float(closes.tail(n).mean())


def _ma_slope(df: pd.DataFrame, n: int, window: int = 5) -> float:
    """% change of MA(n) over `window` days."""
    closes = df["Close"].dropna()
    if len(closes) < n + window:
        return 0.0
    ma_now  = float(closes.tail(n).mean())
    ma_past = float(closes.iloc[-(n + window):-window].mean())
    return (ma_now / ma_past - 1) * 100 if ma_past else 0.0


# ── main ─────────────────────────────────────────────────────────────────────

def compute_ticker_metrics(
    ticker: str,
    df: pd.DataFrame,
    benchmark_dfs: dict[str, pd.DataFrame],
) -> TickerMetrics:
    """Compute full metrics for one ticker against benchmark DataFrames."""
    closes = df["Close"].dropna()
    if closes.empty:
        return TickerMetrics(ticker=ticker, as_of=date.today())

    m = TickerMetrics(ticker=ticker, as_of=date.today())
    m.last_close = float(closes.iloc[-1])

    m.ret_1d = _ret_n(df, 1)
    m.ret_5d = _ret_n(df, 5)
    m.ret_1m = _ret_n(df, 21)
    m.ret_3m = _ret_n(df, 63)

    # YTD return
    year_start = date(date.today().year, 1, 1)
    ytd_mask = df.index.normalize() >= pd.Timestamp(year_start)
    ytd_df = df[ytd_mask]
    if len(ytd_df) > 1:
        m.ret_ytd = float(
            (ytd_df["Close"].iloc[-1] / ytd_df["Close"].iloc[0] - 1) * 100
        )

    # Relative strength vs benchmarks
    spy  = benchmark_dfs.get("SPY")
    qqq  = benchmark_dfs.get("QQQ")
    soxx = benchmark_dfs.get("SOXX")

    if spy is not None:
        m.rs_vs_spy_1d = m.ret_1d - _ret_n(spy, 1)
        m.rs_vs_spy_5d = m.ret_5d - _ret_n(spy, 5)
        m.rs_vs_spy_1m = m.ret_1m - _ret_n(spy, 21)
    if qqq is not None:
        m.rs_vs_qqq_1m = m.ret_1m - _ret_n(qqq, 21)
    if soxx is not None:
        m.rs_vs_soxx_1m = m.ret_1m - _ret_n(soxx, 21)

    # MA structure
    ma20  = _ma(df, 20)
    ma50  = _ma(df, 50)
    ma200 = _ma(df, 200)
    m.above_20dma  = m.last_close > ma20
    m.above_50dma  = m.last_close > ma50
    m.above_200dma = m.last_close > ma200
    m.ma20_slope   = _ma_slope(df, 20)
    m.ma50_slope   = _ma_slope(df, 50)
    m.ma50_value   = ma50

    # Volume
    if "Volume" in df.columns:
        vol = df["Volume"].dropna()
        if len(vol) >= 21:
            avg_20d = float(vol.tail(20).mean())
            if avg_20d > 0:
                m.volume_ratio_20d = float(vol.iloc[-1]) / avg_20d

    # Drawdown from 52-week high
    lookback = min(252, len(closes))
    high_52w = float(closes.tail(lookback).max())
    if high_52w > 0:
        m.drawdown_from_52w_high = (m.last_close / high_52w - 1) * 100

    # Composite score: RS (1M) weighted + MA structure + volume
    ma_score  = (m.above_20dma + m.above_50dma + m.above_200dma) / 3.0  # 0–1
    vol_score = min(m.volume_ratio_20d / 2.0, 1.0)
    m.composite_score = (
        m.rs_vs_spy_1m * 0.5
        + ma_score * 10 * 0.3
        + vol_score * 10 * 0.2
    )

    return m
