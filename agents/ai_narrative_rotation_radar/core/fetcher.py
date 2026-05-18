"""
Data fetch layer — RULE tier. No LLM.
Fetches OHLCV history via yfinance for all watchlist tickers.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger("radar.fetcher")

HISTORY_DAYS = 220  # covers 200DMA + buffer


def fetch_price_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV history for a list of tickers.
    Returns {ticker: DataFrame(OHLCV, indexed by date)}.
    Missing or bad tickers are silently skipped with a warning.
    """
    if not tickers:
        return {}

    end = date.today()
    start = end - timedelta(days=HISTORY_DAYS)

    logger.info("Fetching price history: %d tickers, %s → %s", len(tickers), start, end)
    try:
        raw = yf.download(
            tickers,
            start=start.isoformat(),
            end=end.isoformat(),
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
    except Exception as exc:
        logger.error("yfinance download failed: %s", exc)
        return {}

    results: dict[str, pd.DataFrame] = {}
    single = len(tickers) == 1

    for ticker in tickers:
        try:
            df = raw.copy() if single else raw[ticker].copy()
            df = df.dropna(subset=["Close"])
            if df.empty:
                logger.warning("%s: no data returned", ticker)
                continue
            results[ticker] = df
        except (KeyError, Exception) as exc:
            logger.warning("%s: extraction failed — %s", ticker, exc)

    logger.info("Fetched %d / %d tickers successfully", len(results), len(tickers))
    return results
