"""
Asia markets scanner: A股、港股、日本、韩国.
Reuses StockScanner's batch-download + scoring infrastructure.
"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from scanner.scorer import classify_level, compute_unusual_score
from scanner.stock_scanner import StockScanner
from scanner.universe import ASIA_MARKETS, ASIA_NAMES, asia_all_symbols
from utils.logger import setup_logger

logger = setup_logger("asia_scanner")


def is_market_open(market_key: str) -> bool:
    info = ASIA_MARKETS[market_key]
    now  = datetime.now(ZoneInfo(info["tz"]))
    if now.weekday() >= 5:
        return False
    mins   = now.hour * 60 + now.minute
    lo, hi = info["open_range"]
    return lo <= mins <= hi


class AsiaScanner(StockScanner):

    def scan_market(self, market_key: str, min_score: float = 30.0) -> list:
        info     = ASIA_MARKETS[market_key]
        symbols  = asia_all_symbols(market_key)
        bench_id = info["benchmark"]

        logger.info(f"Scanning {info['flag']} {info['label']} ({len(symbols)} symbols)...")
        hist_all   = self._fetch_batch(symbols + [bench_id], period="3mo")
        bench_hist = hist_all.get(bench_id)

        results = []
        for sym in symbols:
            if sym not in hist_all:
                continue
            try:
                data = self._analyze(sym, hist_all[sym], bench_hist)
                if data is None:
                    continue
                # Attach Asia-specific metadata
                data["market"]    = market_key
                data["flag"]      = info["flag"]
                data["mkt_label"] = info["label"]
                data["currency"]  = info["currency"]
                data["name"]      = ASIA_NAMES.get(sym, sym)
                data["sector"]    = _find_sector(sym, info["sectors"])
                if data["unusual_score"] >= min_score:
                    results.append(data)
            except Exception as e:
                logger.debug(f"{sym}: {e}")

        results.sort(key=lambda x: x["unusual_score"], reverse=True)
        logger.info(f"{info['label']}: {len(results)} unusual symbols")
        return results

    def scan_open_markets(self, min_score: float = 30.0) -> dict:
        """Scan all currently open Asia markets. Returns {market_key: [results]}."""
        out = {}
        for key in ASIA_MARKETS:
            if is_market_open(key):
                out[key] = self.scan_market(key, min_score)
            else:
                logger.debug(f"{key} market closed, skipping")
        return out

    def fetch_indices(self) -> dict:
        """Fetch current values for all Asia major indices."""
        import yfinance as yf
        out = {}
        for key, info in ASIA_MARKETS.items():
            for idx in info.get("indices", []):
                try:
                    fi = yf.Ticker(idx).fast_info
                    out[idx] = {
                        "symbol":    idx,
                        "name":      ASIA_NAMES.get(idx, idx),
                        "market":    key,
                        "flag":      info["flag"],
                        "label":     info["label"],
                        "price":     fi.last_price,
                        "prev_close": fi.previous_close,
                        "change_pct": (
                            (fi.last_price - fi.previous_close) / fi.previous_close * 100
                            if fi.last_price and fi.previous_close else None
                        ),
                    }
                except Exception:
                    pass
        return out


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_sector(symbol: str, sectors: dict) -> str:
    for sec, syms in sectors.items():
        if symbol in syms:
            return sec
    return "其他"


def format_asia_alert(result: dict) -> str:
    level    = result["level"]
    sym      = result["symbol"]
    name     = result.get("name", sym)
    flag     = result.get("flag", "")
    mkt      = result.get("mkt_label", "")
    cur      = result.get("currency", "")
    chg      = result["daily_change_pct"]
    vol_r    = result.get("volume_ratio", 1.0)
    score    = result["unusual_score"]
    price    = result.get("price", 0)
    signals  = result.get("signals", [])

    emoji = "🚨" if level == "HIGH" else "⚡"
    arrow = "📈" if chg > 0 else "📉"

    lines = [
        f"{emoji} *[UNUSUAL][{level}][{flag} {mkt}]*",
        f"*{name}* ({sym})  {arrow} {chg:+.2f}%  {cur}{price:,.2f}",
        f"📊 Volume: {vol_r:.1f}× avg",
    ]
    if signals:
        lines.append(f"🎯 {' + '.join(signals)}")
    lines.append(f"Score: {score:.0f}/100")
    return "\n".join(lines)
