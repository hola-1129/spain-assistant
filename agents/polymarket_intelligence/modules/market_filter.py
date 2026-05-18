from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("polymarket_intelligence.filter")


def _match_keyword(text: str, keywords: list[str]) -> Optional[str]:
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return kw
    return None


def priority_keyword_match(market: dict, keywords: list[str]) -> Optional[str]:
    text = f"{market.get('question', '')} {market.get('event_title', '')}".strip()
    return _match_keyword(text, keywords)


def should_ignore(market: dict, ignored_keywords: list[str]) -> bool:
    text = f"{market.get('question', '')} {market.get('event_title', '')}".strip()
    match = _match_keyword(text, ignored_keywords)
    if match:
        logger.debug(f"Ignored [{market.get('id')}] — keyword: {match}")
        return True
    return False


def filter_markets(markets: list[dict], cfg: dict) -> list[dict]:
    min_volume = float(cfg.get("min_market_volume", 50000))
    min_liquidity = float(cfg.get("min_market_liquidity", 25000))
    ignored = cfg.get("ignored_keywords", [])

    accepted = []
    for m in markets:
        if should_ignore(m, ignored):
            continue
        volume = float(m.get("volume", 0) or 0)
        liquidity = float(m.get("liquidity", 0) or 0)
        if volume < min_volume or liquidity < min_liquidity:
            continue
        accepted.append(m)

    logger.info(f"Market filter: {len(markets)} total → {len(accepted)} accepted")
    return accepted
