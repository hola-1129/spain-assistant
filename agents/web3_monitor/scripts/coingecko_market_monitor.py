"""CoinGecko market monitor — top-100 crypto unusual movers.

Read-only public API. This replaces finance_bot's crypto unusual mover alerts.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger("web3_monitor.coingecko")

_BASE = "https://api.coingecko.com/api/v3"
_BASELINE_TURNOVER = 0.03


class CoinGeckoMarketMonitor:
    def __init__(self, min_gap_sec: float = 2.1, timeout: int = 20, thresholds: dict | None = None):
        self.min_gap = min_gap_sec
        self.timeout = timeout
        self.thresholds = thresholds or {}
        self._last_call = 0.0

    def _get(self, path: str, params: dict | None = None) -> Any:
        gap = time.time() - self._last_call
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self._last_call = time.time()
        try:
            r = requests.get(f"{_BASE}{path}", params=params, timeout=self.timeout)
            if r.status_code == 429:
                wait_sec = 30
                logger.warning(f"CoinGecko {path} -> 429, retrying after {wait_sec}s")
                time.sleep(wait_sec)
                self._last_call = time.time()
                r = requests.get(f"{_BASE}{path}", params=params, timeout=self.timeout)
            if r.status_code != 200:
                logger.warning(f"CoinGecko {path} -> {r.status_code}")
                return None
            return r.json()
        except Exception as e:
            logger.error(f"CoinGecko {path} error: {e}")
            return None

    def scan_top100(self, min_score: float = 60.0) -> list[dict]:
        markets = self._get("/coins/markets", {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h,7d",
        })
        if not markets:
            return []

        btc_7d = next(
            (c.get("price_change_percentage_7d_in_currency") or 0
             for c in markets if (c.get("symbol") or "").upper() == "BTC"),
            0.0,
        )

        out: list[dict] = []
        for coin in markets:
            try:
                symbol = (coin.get("symbol") or "").upper()
                chg_24h = float(coin.get("price_change_percentage_24h") or 0)
                chg_7d = float(coin.get("price_change_percentage_7d_in_currency") or 0)
                market_cap = float(coin.get("market_cap") or 0)
                volume_24h = float(coin.get("total_volume") or 0)
                turnover_ratio = (volume_24h / market_cap / _BASELINE_TURNOVER) if market_cap > 0 else 1.0
                alpha_7d = chg_7d - float(btc_7d)
                market_cap_rank = coin.get("market_cap_rank")
                score = _score_market_move(chg_24h, turnover_ratio, alpha_7d, market_cap_rank)
                if score < min_score:
                    continue
                high_score = self.thresholds.get("coingecko_market_high_score", 70)
                out.append({
                    "type": "market_mover",
                    "source": "coingecko",
                    "asset": symbol,
                    "name": coin.get("name") or "",
                    "coingecko_id": coin.get("id"),
                    "price": float(coin.get("current_price") or 0),
                    "price_change_24h_pct": chg_24h,
                    "change_7d_pct": chg_7d,
                    "alpha_7d_vs_btc_pct": alpha_7d,
                    "turnover_ratio": turnover_ratio,
                    "volume_24h_usd": volume_24h,
                    "market_cap_usd": market_cap,
                    "market_cap_rank": market_cap_rank,
                    "score": score,
                    "level": "HIGH" if score >= high_score else "MEDIUM",
                    "interpretation": _interpret(symbol, chg_24h, turnover_ratio, alpha_7d),
                })
            except Exception as e:
                logger.debug(f"{coin.get('id')}: {e}")

        out.sort(key=lambda item: item["score"], reverse=True)
        logger.info(f"CoinGecko market movers: {len(out)} above score {min_score}")
        return out


def _score_market_move(chg_24h: float, turnover_ratio: float, alpha_7d: float,
                       market_cap_rank: int | None) -> int:
    score = 0.0
    move = abs(chg_24h)
    if move >= 8:
        score += min(move / 24.0 * 30.0, 30.0)
    if turnover_ratio >= 2:
        score += min((turnover_ratio - 1.0) / 4.0 * 25.0, 25.0)
    score += min(abs(alpha_7d) / 15.0 * 20.0, 20.0)
    if chg_24h * alpha_7d > 0 and abs(alpha_7d) >= 5:
        score += 10
    if turnover_ratio >= 3 and move >= 10:
        score += 10
    if isinstance(market_cap_rank, int):
        if market_cap_rank <= 50:
            score += 5
        elif market_cap_rank <= 100:
            score += 3
    return int(round(min(score, 100.0)))


def _interpret(symbol: str, chg_24h: float, turnover_ratio: float, alpha_7d: float) -> str:
    parts = [f"{symbol} 24h {chg_24h:+.1f}%"]
    if turnover_ratio >= 2:
        parts.append(f"换手强度 {turnover_ratio:.1f}x 基准")
    if abs(alpha_7d) >= 10:
        parts.append(f"7d vs BTC {alpha_7d:+.1f}%")
    return "；".join(parts)


def format_market_alert(signal: dict) -> str:
    chg = float(signal.get("price_change_24h_pct") or 0)
    arrow = "📈" if chg > 0 else "📉"
    lines = [
        "⚡ Web3 Market Signal",
        "",
        f"Score: {signal.get('score', 0)}/100",
        f"Level: {signal.get('level', 'MEDIUM')}",
        "",
        f"Asset: {signal.get('asset', '?')}",
        f"Rank: #{signal.get('market_cap_rank', '?')}",
        f"Price: ${float(signal.get('price') or 0):,.4f}",
        f"24h: {arrow} {chg:+.2f}%",
        f"Turnover: {float(signal.get('turnover_ratio') or 0):.1f}x baseline",
        f"7d Alpha vs BTC: {float(signal.get('alpha_7d_vs_btc_pct') or 0):+.1f}%",
        "",
        "Interpretation:",
        signal.get("interpretation", ""),
        "",
        "Action:",
        "只提醒，不自动交易。建议人工检查新闻、流动性和风险来源。",
    ]
    if signal.get("qwen_explanation"):
        lines.append(f"\n💡 {signal['qwen_explanation']}")
    return "\n".join(lines)
