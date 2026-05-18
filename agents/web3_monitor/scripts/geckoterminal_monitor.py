"""GeckoTerminal monitor — trending pools, new pools, OHLCV fallback for DexScreener."""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger("web3_monitor.geckoterminal")

_BASE = "https://api.geckoterminal.com/api/v2"

# GeckoTerminal network slugs; map config chain names → API slugs
_NETWORK_MAP = {
    "ethereum": "eth",
    "base": "base",
    "arbitrum": "arbitrum",
    "solana": "solana",
    "polygon": "polygon_pos",
    "bsc": "bsc",
}


class GeckoTerminalMonitor:
    def __init__(self, min_gap_sec: float = 2.0, timeout: int = 20, thresholds: dict | None = None):
        self.min_gap = min_gap_sec
        self.timeout = timeout
        self.thresholds = thresholds or {}
        self._last_call = 0.0

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        gap = time.time() - self._last_call
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self._last_call = time.time()
        try:
            r = requests.get(
                f"{_BASE}{path}",
                params=params,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                try:
                    wait_sec = float(retry_after) if retry_after else max(self.min_gap * 3, 10)
                except ValueError:
                    wait_sec = max(self.min_gap * 3, 10)
                wait_sec = max(wait_sec, 10)
                logger.warning(f"GeckoTerminal {path} -> 429, retrying after {wait_sec:.1f}s")
                time.sleep(wait_sec)
                self._last_call = time.time()
                r = requests.get(
                    f"{_BASE}{path}",
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=self.timeout,
                )
            if r.status_code != 200:
                logger.warning(f"GeckoTerminal {path} -> {r.status_code}")
                return None
            return r.json()
        except Exception as e:
            logger.error(f"GeckoTerminal {path} error: {e}")
            return None

    def trending_pools(self, chain: str, page: int = 1) -> list[dict]:
        net = _NETWORK_MAP.get(chain.lower(), chain.lower())
        data = self._get(f"/networks/{net}/trending_pools", {"page": page})
        return (data or {}).get("data", []) or []

    def new_pools(self, chain: str, page: int = 1) -> list[dict]:
        net = _NETWORK_MAP.get(chain.lower(), chain.lower())
        data = self._get(f"/networks/{net}/new_pools", {"page": page})
        return (data or {}).get("data", []) or []

    def scan_new_pools(self, chains: list[str]) -> list[dict]:
        """v1: collect new-pool candidates across configured chains, no Telegram push."""
        min_liq = self.thresholds.get("min_liquidity_usd", 50000)
        out: list[dict] = []
        for chain in chains:
            for raw in self.new_pools(chain):
                attrs = raw.get("attributes", {}) or {}
                liq = float(attrs.get("reserve_in_usd") or 0)
                if liq < min_liq:
                    continue
                out.append({
                    "type": "new_pool",
                    "chain": chain,
                    "pool": attrs.get("address"),
                    "name": attrs.get("name"),
                    "liquidity_usd": liq,
                    "volume_24h_usd": float((attrs.get("volume_usd") or {}).get("h24") or 0),
                    "price_change_24h_pct": float((attrs.get("price_change_percentage") or {}).get("h24") or 0),
                    "pool_created_at": attrs.get("pool_created_at"),
                })
        logger.info(f"GeckoTerminal: {len(out)} new pools across {chains}")
        return out
