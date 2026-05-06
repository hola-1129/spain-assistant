"""Scan the stock/ETF universe for unusual movers using yfinance batch download."""
from typing import Optional

import pandas as pd
import yfinance as yf

from scanner.scorer import compute_unusual_score, classify_level
from scanner.universe import ALL_ETFS, ALL_STOCKS, SYMBOL_SECTOR
from utils.logger import setup_logger

logger = setup_logger("stock_scanner")


class StockScanner:
    def scan(self, min_score: float = 30.0) -> list:
        """
        Returns list of dicts sorted by unusual_score desc.
        Only entries with score >= min_score are returned.
        """
        logger.info(f"Scanning {len(ALL_STOCKS)} symbols...")
        hist_all = self._fetch_batch(ALL_STOCKS)
        spy_hist = hist_all.get("SPY")

        results = []
        for sym in ALL_STOCKS:
            if sym not in hist_all:
                continue
            try:
                data = self._analyze(sym, hist_all[sym], spy_hist)
                if data and data["unusual_score"] >= min_score:
                    results.append(data)
            except Exception as e:
                logger.debug(f"{sym}: {e}")

        results.sort(key=lambda x: x["unusual_score"], reverse=True)
        logger.info(f"Scan done — {len(results)} unusual symbols found")
        return results

    # ─────────────────────────────────────────────────────── data fetch ──
    def _fetch_batch(self, symbols: list) -> dict:
        try:
            raw = yf.download(
                tickers=symbols,
                period="3mo",
                progress=False,
                group_by="ticker",
                threads=True,
                auto_adjust=True,
            )
            if raw.empty:
                return {}

            result = {}
            # single ticker: flat DataFrame
            if isinstance(raw.columns, pd.Index) and "Close" in raw.columns:
                sym = symbols[0]
                result[sym] = raw.dropna(how="all")
                return result

            # multiple tickers: MultiIndex columns (ticker, field)
            for sym in symbols:
                try:
                    df = raw[sym].dropna(how="all")
                    if not df.empty and "Close" in df.columns:
                        result[sym] = df
                except KeyError:
                    pass
            return result
        except Exception as e:
            logger.error(f"Batch fetch error: {e}")
            return {}

    # ──────────────────────────────────────────────────────── analysis ──
    def _analyze(self, symbol: str, hist: pd.DataFrame, spy_hist: Optional[pd.DataFrame]) -> Optional[dict]:
        if len(hist) < 22:
            return None

        close  = hist["Close"]
        vol    = hist.get("Volume", pd.Series(dtype=float))
        price  = float(close.iloc[-1])
        prev   = float(close.iloc[-2])
        daily_chg = (price - prev) / prev * 100

        # Volume ratio vs 20-day avg
        vol_ratio = 1.0
        if not vol.empty:
            vol_avg = vol.iloc[-21:-1].mean()
            if vol_avg > 0:
                vol_ratio = float(vol.iloc[-1] / vol_avg)

        # 20-day high/low (exclude today)
        c20       = close.iloc[-21:-1]
        h20, l20  = float(c20.max()), float(c20.min())
        new_20d_high = price > h20
        new_20d_low  = price < l20

        # 52-week high/low
        new_52w_high = new_52w_low = False
        if len(close) >= 252:
            c252 = close.iloc[-253:-1]
            new_52w_high = price > float(c252.max())
            new_52w_low  = price < float(c252.min())

        # Alpha vs SPY
        alpha_5d = alpha_20d = 0.0
        if spy_hist is not None and symbol != "SPY":
            sc = spy_hist["Close"]
            if len(close) >= 6 and len(sc) >= 6:
                alpha_5d  = (close.iloc[-1]/close.iloc[-6] - 1)*100 - (sc.iloc[-1]/sc.iloc[-6] - 1)*100
            if len(close) >= 21 and len(sc) >= 21:
                alpha_20d = (close.iloc[-1]/close.iloc[-21] - 1)*100 - (sc.iloc[-1]/sc.iloc[-21] - 1)*100

        asset_type = "etf" if symbol in ALL_ETFS else "stock"

        score = compute_unusual_score({
            "daily_change_pct": daily_chg,
            "volume_ratio":     vol_ratio,
            "new_52w_high":     new_52w_high,
            "new_52w_low":      new_52w_low,
            "new_20d_high":     new_20d_high,
            "new_20d_low":      new_20d_low,
            "alpha_5d":         alpha_5d,
            "alpha_20d":        alpha_20d,
            "asset_type":       asset_type,
        })

        # Build human-readable signal tags
        signals = []
        if new_52w_high:             signals.append("52周新高")
        elif new_52w_low:            signals.append("52周新低")
        elif new_20d_high:           signals.append("20日新高")
        elif new_20d_low:            signals.append("20日新低")
        if vol_ratio >= 2.0:         signals.append(f"量比{vol_ratio:.1f}×")
        if abs(alpha_5d) >= 5:       signals.append(f"5日Alpha{alpha_5d:+.1f}%")
        if abs(alpha_20d) >= 10:     signals.append(f"20日Alpha{alpha_20d:+.1f}%")

        return {
            "symbol":           symbol,
            "asset_type":       asset_type,
            "sector":           SYMBOL_SECTOR.get(symbol, "unknown"),
            "price":            price,
            "daily_change_pct": daily_chg,
            "volume_ratio":     vol_ratio,
            "new_52w_high":     new_52w_high,
            "new_52w_low":      new_52w_low,
            "new_20d_high":     new_20d_high,
            "new_20d_low":      new_20d_low,
            "alpha_5d":         alpha_5d,
            "alpha_20d":        alpha_20d,
            "unusual_score":    score,
            "level":            classify_level(score),
            "signals":          signals,
        }
