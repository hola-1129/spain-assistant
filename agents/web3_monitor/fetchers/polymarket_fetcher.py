from datetime import datetime, timezone

import requests

from utils.logger import setup_logger

logger = setup_logger("polymarket_fetcher")

_BASE = "https://gamma-api.polymarket.com"


class PolymarketFetcher:
    def __init__(self, config: dict):
        pm_cfg          = config.get("prediction", {}).get("polymarket", {})
        self.keywords   = [k.lower() for k in pm_cfg.get("keywords", [])]
        self.min_volume = pm_cfg.get("min_volume_usd", 50_000)
        self.resolve_soon_days = pm_cfg.get("resolve_soon_days", 3)

    def get_active_markets(self) -> list:
        """返回所有活跃市场（按成交量降序，已按 min_volume 过滤）。"""
        try:
            resp = requests.get(
                f"{_BASE}/markets",
                params={"closed": "false", "sort": "volume", "order": "DESC", "limit": 50},
                timeout=15,
            )
            resp.raise_for_status()
            markets = resp.json()
        except Exception as e:
            logger.error(f"Polymarket fetch failed: {e}")
            return []

        result = []
        for m in markets:
            vol = float(m.get("volume", 0) or 0)
            if vol < self.min_volume:
                continue
            result.append({
                "question":    m.get("question", ""),
                "end_date":    m.get("endDate", ""),
                "volume_usd":  vol,
                "url":         f"https://polymarket.com/event/{m.get('slug', '')}",
            })
        return result

    def get_keyword_markets(self) -> list:
        """返回匹配关键词的市场。"""
        markets = self.get_active_markets()
        if not self.keywords:
            return markets
        return [
            m for m in markets
            if any(kw in m["question"].lower() for kw in self.keywords)
        ]

    def get_resolving_soon(self) -> list:
        """返回即将结算（≤ resolve_soon_days 天）的关键词市场。"""
        markets = self.get_keyword_markets()
        now     = datetime.now(timezone.utc)
        soon    = []
        for m in markets:
            end_str = m.get("end_date", "")
            if not end_str:
                continue
            try:
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                days_left = (end_dt - now).days
                if 0 <= days_left <= self.resolve_soon_days:
                    m["days_left"] = days_left
                    soon.append(m)
            except Exception:
                continue
        return soon
