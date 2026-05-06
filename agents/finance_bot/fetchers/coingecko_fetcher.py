import time
from typing import Optional

import pandas as pd
import requests

from utils.logger import setup_logger

logger = setup_logger("coingecko_fetcher")

_BASE = "https://api.coingecko.com/api/v3"


class CoinGeckoFetcher:
    def __init__(self, config: dict):
        self.id_map: dict = config.get("assets", {}).get("crypto_id_map", {})
        self._last_call = 0.0
        self._min_gap   = 2.1  # free tier: ~30 req/min

    # ---------------------------------------------------------------- helpers
    def _cg_id(self, symbol: str) -> str:
        return self.id_map.get(symbol, symbol.lower())

    def _get(self, path: str, params: dict = None) -> dict:
        gap = time.time() - self._last_call
        if gap < self._min_gap:
            time.sleep(self._min_gap - gap)
        self._last_call = time.time()
        resp = requests.get(f"{_BASE}{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # --------------------------------------------------------------- current
    def get_prices(self, symbols: list) -> dict:
        ids = [self._cg_id(s) for s in symbols]
        try:
            data = self._get("/simple/price", {
                "ids":                   ",".join(ids),
                "vs_currencies":         "usd",
                "include_24hr_change":   "true",
                "include_24hr_vol":      "true",
            })
            result = {}
            for sym in symbols:
                cid = self._cg_id(sym)
                if cid in data:
                    d = data[cid]
                    result[sym] = {
                        "price":          d.get("usd"),
                        "change_24h_pct": d.get("usd_24h_change"),
                        "volume":         d.get("usd_24h_vol"),
                    }
            return result
        except Exception as e:
            logger.error(f"CoinGecko price fetch failed: {e}")
            return {}

    # -------------------------------------------------------------- historical
    def get_history(self, symbols: list, days: int = 65) -> dict:
        result = {}
        for sym in symbols:
            cid = self._cg_id(sym)
            try:
                data = self._get(f"/coins/{cid}/market_chart", {
                    "vs_currency": "usd",
                    "days":        days,
                    "interval":    "daily",
                })
                prices = data.get("prices", [])
                if prices:
                    df = pd.DataFrame(prices, columns=["ts_ms", "Close"])
                    df["Date"] = pd.to_datetime(df["ts_ms"], unit="ms")
                    result[sym] = df.set_index("Date")[["Close"]]
            except Exception as e:
                logger.warning(f"CoinGecko history failed for {sym}: {e}")
        return result
