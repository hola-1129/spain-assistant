"""Polymarket monitor — Gamma + CLOB + Data APIs, READ-ONLY.

Strict v1 boundary: never call any endpoint that places, cancels, or modifies orders.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger("web3_monitor.polymarket")

_GAMMA = "https://gamma-api.polymarket.com"
_CLOB = "https://clob.polymarket.com"
_DATA = "https://data-api.polymarket.com"


def _days_to_resolve(value: str | None) -> float | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        end = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta = end - datetime.now(timezone.utc)
    return max(delta.total_seconds() / 86400, 0)


class PolymarketMonitor:
    def __init__(self, min_gap_sec: float = 1.0, timeout: int = 20, thresholds: dict | None = None):
        self.min_gap = min_gap_sec
        self.timeout = timeout
        self.thresholds = thresholds or {}
        self._last_call = 0.0

    def _get(self, url: str, params: dict | None = None) -> dict | list | None:
        gap = time.time() - self._last_call
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self._last_call = time.time()
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            if r.status_code != 200:
                logger.warning(f"Polymarket {url} -> {r.status_code}")
                return None
            return r.json()
        except Exception as e:
            logger.error(f"Polymarket {url} error: {e}")
            return None

    # ── Gamma ─────────────────────────────────────────────────────────
    def events(self, tag: str | None = None, limit: int = 100, closed: bool = False) -> list[dict]:
        params: dict = {"limit": limit, "closed": str(closed).lower()}
        if tag:
            params["tag"] = tag
        data = self._get(f"{_GAMMA}/events", params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("events") or data.get("data") or []
        return []

    def markets(self, limit: int = 100, closed: bool = False) -> list[dict]:
        data = self._get(f"{_GAMMA}/markets", {"limit": limit, "closed": str(closed).lower()})
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("markets") or data.get("data") or []
        return []

    # ── CLOB (READ ONLY) ──────────────────────────────────────────────
    def orderbook(self, token_id: str) -> dict | None:
        return self._get(f"{_CLOB}/book", {"token_id": token_id})

    def prices_history(self, market_id: str, interval: str = "1h") -> dict | None:
        return self._get(f"{_CLOB}/prices-history", {"market": market_id, "interval": interval})

    # ── Data (READ ONLY) ──────────────────────────────────────────────
    def trades(self, market_id: str, limit: int = 50) -> list[dict]:
        data = self._get(f"{_DATA}/trades", {"market": market_id, "limit": limit})
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("trades") or data.get("data") or []
        return []

    # ── Scan ──────────────────────────────────────────────────────────
    def scan_categories(self, categories: list[str], prev_state: dict | None = None) -> list[dict]:
        """Pull events for each tag, compute basic anomaly metrics vs prev_state.

        prev_state: dict mapping event_id -> {"probability": float, "volume": float} from the prior cycle.
        """
        prev = prev_state or {}
        has_baseline = bool(prev)
        prob_thr = self.thresholds.get("polymarket_probability_change_pct", 8)
        vol_thr = self.thresholds.get("polymarket_volume_change_pct", 100)

        out: list[dict] = []
        for tag in categories:
            for ev in self.events(tag=tag, limit=100, closed=False):
                eid = str(ev.get("id") or ev.get("slug") or ev.get("ticker") or "")
                if not eid:
                    continue
                # Probability proxy: if event has markets, use the first YES outcomePrice
                markets = ev.get("markets") or []
                prob_now = None
                for m in markets:
                    op = m.get("outcomePrices") or m.get("outcome_prices")
                    if isinstance(op, str):
                        try:
                            import json as _json
                            op = _json.loads(op)
                        except Exception:
                            op = None
                    if isinstance(op, list) and op:
                        try:
                            prob_now = float(op[0])
                            break
                        except (TypeError, ValueError):
                            continue
                vol_now = float(ev.get("volume") or ev.get("volume24hr") or 0)

                p = prev.get(eid) or {}
                prob_prev = p.get("probability")
                vol_prev = p.get("volume", 0)

                prob_change_pct = ((prob_now - prob_prev) * 100) if (prob_now is not None and prob_prev is not None) else 0
                vol_change_pct = ((vol_now - vol_prev) / vol_prev * 100) if vol_prev > 0 else 0

                end_date = ev.get("endDate") or ev.get("end_date")
                is_signal = (
                    has_baseline
                    and (abs(prob_change_pct) >= prob_thr or vol_change_pct >= vol_thr)
                )

                out.append({
                    "type": "polymarket",
                    "is_signal": is_signal,
                    "event_id": eid,
                    "title": ev.get("title") or ev.get("question") or "",
                    "tag": tag,
                    "probability_now": prob_now,
                    "probability_prev": prob_prev,
                    "probability_change_pct": prob_change_pct,
                    "volume_24h_usd": vol_now,
                    "volume_change_pct": vol_change_pct,
                    "end_date": end_date,
                    "days_to_resolve": _days_to_resolve(end_date),
                    "closed": ev.get("closed", False),
                })

        signal_count = sum(1 for item in out if item.get("is_signal"))
        logger.info(f"Polymarket: {len(out)} event snapshots, {signal_count} signals across {categories}")
        return out
