"""DeFiLlama monitor — chain TVL, protocol TVL, stablecoin flows."""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger("web3_monitor.defillama")

_LLAMA = "https://api.llama.fi"
_STABLES = "https://stablecoins.llama.fi"


class DefiLlamaMonitor:
    def __init__(self, min_gap_sec: float = 1.0, timeout: int = 20):
        self.min_gap = min_gap_sec
        self.timeout = timeout
        self._last_call = 0.0

    def _get(self, url: str, params: dict | None = None) -> dict | list | None:
        gap = time.time() - self._last_call
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self._last_call = time.time()
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            if r.status_code != 200:
                logger.warning(f"DeFiLlama {url} -> {r.status_code}")
                return None
            return r.json()
        except Exception as e:
            logger.error(f"DeFiLlama {url} error: {e}")
            return None

    def chains_tvl(self) -> list[dict]:
        data = self._get(f"{_LLAMA}/v2/chains")
        return data or []

    def protocols(self) -> list[dict]:
        data = self._get(f"{_LLAMA}/protocols")
        return data or []

    def stablecoins(self) -> list[dict]:
        data = self._get(f"{_STABLES}/stablecoins")
        return (data or {}).get("peggedAssets", []) or []

    def macro_snapshot(self, watch_chains: list[str]) -> dict:
        """Lightweight macro snapshot for cross_signal_engine context (not scored directly)."""
        chains = self.chains_tvl()
        watch_lower = {c.lower() for c in watch_chains}
        filt = [c for c in chains if (c.get("name") or "").lower() in watch_lower]
        return {
            "ts": time.time(),
            "watch_chains_tvl": [
                {
                    "chain": c.get("name"),
                    "tvl_usd": c.get("tvl"),
                    "change_1d_pct": c.get("change_1d"),
                    "change_7d_pct": c.get("change_7d"),
                }
                for c in filt
            ],
        }
