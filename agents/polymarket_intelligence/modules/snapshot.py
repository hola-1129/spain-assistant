from __future__ import annotations

import logging
from typing import Optional

from modules.utils import utcnow_iso

logger = logging.getLogger("polymarket_intelligence.snapshot")


def _extract_yes_no_prices(market: dict) -> tuple[Optional[float], Optional[float]]:
    yes_price: Optional[float] = None
    no_price: Optional[float] = None

    outcomes = market.get("outcomes", [])
    prices = market.get("outcomePrices", [])
    if isinstance(outcomes, list) and isinstance(prices, list):
        for i, outcome in enumerate(outcomes):
            if i >= len(prices):
                break
            try:
                val = float(prices[i])
            except (ValueError, TypeError):
                continue
            if str(outcome).upper() == "YES":
                yes_price = val
            elif str(outcome).upper() == "NO":
                no_price = val

    if yes_price is None:
        for field in ("lastTradePrice", "price"):
            raw = market.get(field)
            if raw is not None:
                try:
                    yes_price = float(raw)
                    break
                except (ValueError, TypeError):
                    pass

    return yes_price, no_price


def _extract_orderbook_prices(
    orderbook: dict,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    try:
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if bids:
            best_bid = float(bids[0]["price"])
        if asks:
            best_ask = float(asks[0]["price"])
        if best_bid is not None and best_ask is not None:
            spread = round(best_ask - best_bid, 4)
    except Exception as e:
        logger.warning(f"Orderbook parse error: {e}")
    return best_bid, best_ask, spread


def build_snapshot(market: dict, orderbook: Optional[dict] = None) -> dict:
    market_id = market.get("id") or market.get("conditionId", "")
    yes_price, no_price = _extract_yes_no_prices(market)

    best_bid, best_ask, spread = (None, None, None)
    if orderbook:
        best_bid, best_ask, spread = _extract_orderbook_prices(orderbook)

    return {
        "market_id": market_id,
        "timestamp": utcnow_iso(),
        "yes_price": yes_price,
        "no_price": no_price,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "volume": float(market.get("volume", 0) or 0),
        "liquidity": float(market.get("liquidity", 0) or 0),
    }
