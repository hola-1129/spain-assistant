"""Unified signal model for Web3 Monitor v2.

The monitor still accepts source-specific dictionaries, but persistence,
review, dashboard APIs, and future MCP tools should use this normalized shape.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Signal:
    source: str
    symbol: str
    signal_type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    chain: str | None = None
    token: str | None = None
    price: float | None = None
    volume: float | None = None
    liquidity: float | None = None
    score: float | None = None
    reason: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _source_from_raw(raw: dict[str, Any]) -> str:
    if raw.get("source"):
        return str(raw["source"])
    if raw.get("type") == "market_mover":
        return "coingecko"
    if raw.get("type") == "new_pool":
        return "geckoterminal"
    if raw.get("polymarket") and raw.get("dex"):
        return "cross_signal"
    if raw.get("polymarket"):
        return "polymarket"
    if raw.get("dex") or raw.get("type") == "dex":
        return "dexscreener"
    return "unknown"


def from_raw(raw: dict[str, Any]) -> Signal:
    """Normalize an existing v1/v1.2 signal dict into the v2 Signal model."""
    sig_type = str(raw.get("signal_type") or raw.get("type") or "unknown")
    source = _source_from_raw(raw)
    dex = raw.get("dex") or {}
    pm = raw.get("polymarket") or {}

    symbol = (
        raw.get("symbol")
        or raw.get("asset")
        or raw.get("token")
        or dex.get("asset")
        or pm.get("asset")
        or raw.get("name")
        or pm.get("title")
        or "UNKNOWN"
    )
    chain = raw.get("chain") or dex.get("chain")
    token = raw.get("token") or raw.get("token_address") or dex.get("token_address")

    price = (
        _num(raw.get("price"))
        or _num(dex.get("price"))
        or _num(pm.get("probability_now"))
    )
    volume = (
        _num(raw.get("volume"))
        or _num(raw.get("volume_1h_usd"))
        or _num(raw.get("volume_24h_usd"))
        or _num(dex.get("volume_1h_usd"))
        or _num(dex.get("volume_24h_usd"))
        or _num(pm.get("volume_24h_usd"))
    )
    liquidity = (
        _num(raw.get("liquidity"))
        or _num(raw.get("liquidity_usd"))
        or _num(dex.get("liquidity_usd"))
    )

    return Signal(
        source=source,
        symbol=str(symbol),
        chain=str(chain) if chain else None,
        token=str(token) if token else None,
        signal_type=sig_type,
        timestamp=str(raw.get("ts") or raw.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        price=price,
        volume=volume,
        liquidity=liquidity,
        score=_num(raw.get("score")),
        reason=str(raw.get("reason") or raw.get("interpretation") or ""),
        raw_data=raw,
    )
