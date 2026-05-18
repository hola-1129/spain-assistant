"""DexScreener monitor — pulls pool & token data, returns DEX-anomaly candidates.

v1 skeleton: only public free endpoints, read-only, with timeout + min-gap rate limit.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

import requests

logger = logging.getLogger("web3_monitor.dexscreener")

_BASE = "https://api.dexscreener.com/latest/dex"


class DexScreenerMonitor:
    def __init__(self, min_gap_sec: float = 1.0, timeout: int = 20, thresholds: dict | None = None):
        self.min_gap = min_gap_sec
        self.timeout = timeout
        self.thresholds = thresholds or {}
        self._last_call = 0.0

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        gap = time.time() - self._last_call
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self._last_call = time.time()
        url = f"{_BASE}{path}"
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            if r.status_code != 200:
                logger.warning(f"DexScreener {path} -> {r.status_code}")
                return None
            return r.json()
        except Exception as e:
            logger.error(f"DexScreener {path} error: {e}")
            return None

    # ── Public methods ────────────────────────────────────────────────
    def search(self, query: str) -> list[dict]:
        data = self._get("/search", {"q": query})
        if not data:
            return []
        return data.get("pairs", []) or []

    def token_pairs(self, token_address: str) -> list[dict]:
        data = self._get(f"/tokens/{token_address}")
        if not data:
            return []
        return data.get("pairs", []) or []

    def scan_assets(self, assets: Iterable[str], allowed_chains: Iterable[str] | None = None) -> list[dict]:
        """For each asset symbol, search DexScreener and return candidates passing thresholds.

        Returns a list of dicts shaped for cross_signal_engine.
        """
        chain_allowlist = {c.lower() for c in (allowed_chains or [])}
        min_liq = self.thresholds.get("min_liquidity_usd", 50000)
        min_vol_1h_usd = self.thresholds.get("min_volume_1h_usd", 50000)
        min_price_1h = self.thresholds.get("price_change_1h_pct", 8)
        min_vol_1h = self.thresholds.get("volume_change_1h_pct", 80)

        candidates: list[dict] = []
        for sym in assets:
            pairs = self.search(sym)
            # Group by token address to detect multi-pool synchrony
            best_by_token: dict[str, dict] = {}
            for p in pairs:
                chain = (p.get("chainId") or "").lower()
                if chain_allowlist and chain not in chain_allowlist:
                    continue
                base = p.get("baseToken") or {}
                if (base.get("symbol") or "").upper() != sym.upper():
                    continue
                liq = float((p.get("liquidity") or {}).get("usd") or 0)
                if liq < min_liq:
                    continue
                price_1h = float((p.get("priceChange") or {}).get("h1") or 0)
                vol_1h = float((p.get("volume") or {}).get("h1") or 0)
                vol_24h = float((p.get("volume") or {}).get("h24") or 0)
                if vol_1h < min_vol_1h_usd:
                    continue
                # crude 1h volume "ratio" vs 24h average hour
                avg_hourly_vol_24h = vol_24h / 24 if vol_24h > 0 else 0
                vol_change_1h_pct = ((vol_1h - avg_hourly_vol_24h) / avg_hourly_vol_24h * 100) if avg_hourly_vol_24h > 0 else 0

                token_addr = base.get("address", "")
                cand = {
                    "asset": sym.upper(),
                    "chain": p.get("chainId"),
                    "pool": p.get("pairAddress"),
                    "token_address": token_addr,
                    "price_change_1h_pct": price_1h,
                    "price_change_24h_pct": float((p.get("priceChange") or {}).get("h24") or 0),
                    "volume_1h_usd": vol_1h,
                    "volume_24h_usd": vol_24h,
                    "volume_change_1h_pct": vol_change_1h_pct,
                    "liquidity_usd": liq,
                    "dex_id": p.get("dexId"),
                    "url": p.get("url"),
                }
                if abs(price_1h) < min_price_1h and vol_change_1h_pct < min_vol_1h:
                    continue
                # keep best (largest liquidity) per token
                prev = best_by_token.get(token_addr)
                if not prev or liq > prev["liquidity_usd"]:
                    best_by_token[token_addr] = cand

            # multi-pool flag
            for cand in best_by_token.values():
                same_token_pairs = [
                    p for p in pairs
                    if (p.get("baseToken") or {}).get("address") == cand["token_address"]
                    and (not chain_allowlist or (p.get("chainId") or "").lower() in chain_allowlist)
                    and float((p.get("priceChange") or {}).get("h1") or 0) * cand["price_change_1h_pct"] > 0
                ]
                cand["multi_pool"] = len(same_token_pairs) >= 2
                candidates.append(cand)

        logger.info(f"DexScreener: {len(candidates)} candidates for {list(assets)}")
        return candidates
