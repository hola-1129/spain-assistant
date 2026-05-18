"""Signal review/backtest scaffolding for Web3 Monitor v2.

The first version focuses on database plumbing and summary statistics. Price
enrichment is deliberately pluggable so we can later use CoinGecko,
DexScreener, or another free source without changing the stored schema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from storage import SignalStore, resolve_db_path
except ModuleNotFoundError:
    from .storage import SignalStore, resolve_db_path

PriceFetcher = Callable[[dict[str, Any], str], float | None]


ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict[str, Any]:
    with (ROOT / "config.yaml").open("r") as f:
        return yaml.safe_load(f) or {}


def _pct_change(start: float | None, end: float | None) -> float | None:
    if start in (None, 0) or end is None:
        return None
    return (end - start) / start * 100


def review_pending_signals(fetch_price: PriceFetcher | None = None, limit: int = 200) -> int:
    """Fill 1h/6h/24h review fields when a price fetcher is available."""
    if fetch_price is None:
        return 0
    cfg = load_config()
    store = SignalStore(resolve_db_path(ROOT, cfg))
    updated = 0
    for row in store.get_recent_signals(limit=limit):
        base_price = row.get("price")
        if not base_price:
            continue
        updates: dict[str, Any] = {"reviewed_at": datetime.now(timezone.utc).isoformat()}
        for horizon in ("1h", "6h", "24h"):
            price = fetch_price(row, horizon)
            if price is None:
                continue
            updates[f"price_{horizon}"] = price
            updates[f"price_change_{horizon}_pct"] = _pct_change(float(base_price), price)
        if len(updates) > 1:
            store.update_signal_review(int(row["id"]), updates)
            updated += 1
    return updated


def summarize_reviews() -> dict[str, Any]:
    cfg = load_config()
    store = SignalStore(resolve_db_path(ROOT, cfg))
    return store.get_score_summary()


if __name__ == "__main__":
    summary = summarize_reviews()
    for group in summary["groups"]:
        print(group)
