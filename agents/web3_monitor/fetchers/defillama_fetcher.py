from typing import Optional

import requests

from utils.logger import setup_logger

logger = setup_logger("defillama_fetcher")

_TVL_BASE   = "https://api.llama.fi"
_YIELD_BASE = "https://yields.llama.fi"


class DefiLlamaFetcher:
    def __init__(self, config: dict):
        self.cfg = config.get("defi", {})

    def get_protocol_tvl(self, slug: str) -> Optional[float]:
        try:
            resp = requests.get(f"{_TVL_BASE}/tvl/{slug}", timeout=15)
            resp.raise_for_status()
            return float(resp.json())
        except Exception as e:
            logger.warning(f"TVL fetch failed [{slug}]: {e}")
            return None

    def get_yield_opportunities(self) -> list:
        """返回符合配置条件的 DeFi 收益池，按 APY 降序排列。"""
        scan_cfg  = self.cfg.get("yield_scan", {})
        min_apy   = scan_cfg.get("min_apy", 8.0)
        min_tvl   = scan_cfg.get("min_tvl_usd", 5_000_000)
        chains    = [c.lower() for c in scan_cfg.get("chains", [])]
        top_n     = scan_cfg.get("top_n", 5)

        try:
            resp = requests.get(f"{_YIELD_BASE}/pools", timeout=30)
            resp.raise_for_status()
            pools = resp.json().get("data", [])
        except Exception as e:
            logger.error(f"DeFiLlama yield fetch failed: {e}")
            return []

        filtered = [
            p for p in pools
            if (p.get("apy") or 0) >= min_apy
            and (p.get("tvlUsd") or 0) >= min_tvl
            and (not chains or (p.get("chain") or "").lower() in chains)
            and not p.get("ilRisk")          # 排除无常损失风险池
            and p.get("status") == "active"
        ]
        filtered.sort(key=lambda p: p.get("apy", 0), reverse=True)

        return [
            {
                "project":  p.get("project"),
                "symbol":   p.get("symbol"),
                "chain":    p.get("chain"),
                "apy":      round(p.get("apy", 0), 2),
                "tvl_usd":  p.get("tvlUsd"),
            }
            for p in filtered[:top_n]
        ]
