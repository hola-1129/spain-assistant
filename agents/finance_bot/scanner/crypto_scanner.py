"""Scan top-100 crypto by market cap for unusual movers via CoinGecko."""
import time

import requests

from scanner.scorer import classify_level, compute_unusual_score
from utils.logger import setup_logger

logger = setup_logger("crypto_scanner")

_BASE           = "https://api.coingecko.com/api/v3"
_BASELINE_TURN  = 0.03   # 3 % daily turnover = vol_ratio 1.0


class CryptoScanner:
    def __init__(self):
        self._last_call = 0.0
        self._gap       = 2.1  # free tier: ~30 req/min

    def _get(self, path: str, params: dict = None):
        gap = time.time() - self._last_call
        if gap < self._gap:
            time.sleep(self._gap - gap)
        self._last_call = time.time()
        resp = requests.get(f"{_BASE}{path}", params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def scan(self, min_score: float = 30.0) -> list:
        """Returns unusual movers from top-100 crypto, sorted by score desc."""
        logger.info("Scanning top-100 crypto...")
        try:
            markets = self._get("/coins/markets", {
                "vs_currency":             "usd",
                "order":                   "market_cap_desc",
                "per_page":                100,
                "page":                    1,
                "sparkline":               "false",
                "price_change_percentage": "24h,7d",
            })
        except Exception as e:
            logger.error(f"CoinGecko scan failed: {e}")
            return []

        # BTC 7-day return as crypto benchmark
        btc_7d = next(
            (c.get("price_change_percentage_7d_in_currency") or 0
             for c in markets if c["symbol"].upper() == "BTC"),
            0.0,
        )

        results = []
        for coin in markets:
            try:
                chg_24h = float(coin.get("price_change_percentage_24h") or 0)
                chg_7d  = float(coin.get("price_change_percentage_7d_in_currency") or 0)
                mc      = float(coin.get("market_cap") or 0)
                vol     = float(coin.get("total_volume") or 0)

                vol_ratio = (vol / mc / _BASELINE_TURN) if mc > 0 else 1.0
                alpha_7d  = chg_7d - btc_7d

                score = compute_unusual_score({
                    "daily_change_pct": chg_24h,
                    "volume_ratio":     vol_ratio,
                    "new_52w_high":     False,
                    "new_52w_low":      False,
                    "new_20d_high":     False,
                    "new_20d_low":      False,
                    "alpha_5d":         0.0,
                    "alpha_20d":        alpha_7d,
                    "asset_type":       "crypto",
                })

                if score < min_score:
                    continue

                signals = []
                if abs(chg_24h) >= 8:   signals.append(f"24h {chg_24h:+.1f}%")
                if vol_ratio >= 2.0:     signals.append(f"量比{vol_ratio:.1f}×")
                if abs(alpha_7d) >= 10:  signals.append(f"7日Alpha{alpha_7d:+.1f}%")

                results.append({
                    "symbol":           coin["symbol"].upper(),
                    "name":             coin.get("name", ""),
                    "coingecko_id":     coin["id"],
                    "asset_type":       "crypto",
                    "price":            float(coin.get("current_price") or 0),
                    "daily_change_pct": chg_24h,
                    "change_7d":        chg_7d,
                    "volume_ratio":     vol_ratio,
                    "market_cap_rank":  coin.get("market_cap_rank"),
                    "alpha_7d":         alpha_7d,
                    "unusual_score":    score,
                    "level":            classify_level(score),
                    "signals":          signals,
                })
            except Exception as e:
                logger.debug(f"{coin.get('id')}: {e}")

        results.sort(key=lambda x: x["unusual_score"], reverse=True)
        logger.info(f"Crypto scan: {len(results)} unusual movers")
        return results
