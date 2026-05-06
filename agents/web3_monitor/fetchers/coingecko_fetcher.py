import time

import requests

from utils.logger import setup_logger

logger = setup_logger("coingecko_fetcher")

_BASE = "https://api.coingecko.com/api/v3"


class CoinGeckoFetcher:
    def __init__(self, config: dict):
        self.id_map: dict = config.get("tokens", {}).get("crypto_id_map", {})
        self._last_call = 0.0
        self._min_gap   = 2.1  # free tier: ~30 req/min

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

    def get_prices(self, symbols: list) -> dict:
        ids = [self._cg_id(s) for s in symbols]
        try:
            data = self._get("/simple/price", {
                "ids":                 ",".join(ids),
                "vs_currencies":       "usd",
                "include_24hr_change": "true",
                "include_24hr_vol":    "true",
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
            logger.error(f"CoinGecko 价格获取失败: {e}")
            return {}
