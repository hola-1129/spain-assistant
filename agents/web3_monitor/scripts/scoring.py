"""Configurable 0-100 signal scoring for Web3 Monitor v2."""
from __future__ import annotations

from typing import Any


DEFAULT_WEIGHTS = {
    "price_move": 20,
    "volume_move": 20,
    "whale_activity": 20,
    "liquidity_change": 20,
    "prediction_market": 20,
}


def _weight(cfg: dict[str, Any], key: str) -> float:
    weights = cfg.get("signal_scoring", {}).get("weights", {})
    return float(weights.get(key, DEFAULT_WEIGHTS[key]))


def _cap(value: float, max_score: float) -> float:
    return max(0.0, min(value, max_score))


def score_features(features: dict[str, Any], cfg: dict[str, Any]) -> tuple[int, str]:
    """Return (score, reason) from normalized feature values.

    Expected feature keys are percentages or simple scores:
    price_change_pct, volume_change_pct, whale_score, liquidity_change_pct,
    polymarket_change_pct.
    """
    thresholds = cfg.get("thresholds", {})
    parts: list[str] = []
    score = 0.0

    price = abs(float(features.get("price_change_pct") or 0))
    price_thr = float(thresholds.get("price_change_1h_pct", 8))
    price_score = _cap(price / max(price_thr, 1) * _weight(cfg, "price_move"), _weight(cfg, "price_move"))
    if price_score:
        parts.append(f"价格异动 {price:.1f}%")
    score += price_score

    volume = float(features.get("volume_change_pct") or 0)
    vol_thr = float(thresholds.get("volume_change_1h_pct", 80))
    volume_score = _cap(volume / max(vol_thr, 1) * _weight(cfg, "volume_move"), _weight(cfg, "volume_move"))
    if volume_score:
        parts.append(f"成交量变化 {volume:.0f}%")
    score += volume_score

    whale_score = _cap(float(features.get("whale_score") or 0), _weight(cfg, "whale_activity"))
    if whale_score:
        parts.append("出现鲸鱼/聪明钱线索")
    score += whale_score

    liquidity = abs(float(features.get("liquidity_change_pct") or 0))
    liq_score = _cap(liquidity / 50.0 * _weight(cfg, "liquidity_change"), _weight(cfg, "liquidity_change"))
    if liq_score:
        parts.append(f"流动性变化 {liquidity:.0f}%")
    score += liq_score

    pm = abs(float(features.get("polymarket_change_pct") or 0))
    pm_thr = float(thresholds.get("polymarket_probability_change_pct", 8))
    pm_score = _cap(pm / max(pm_thr, 1) * _weight(cfg, "prediction_market"), _weight(cfg, "prediction_market"))
    if pm_score:
        parts.append(f"预测市场概率变化 {pm:.1f}%")
    score += pm_score

    return int(round(min(score, 100))), "；".join(parts) or "未触发主要评分因子"


def score_raw_signal(raw: dict[str, Any], cfg: dict[str, Any]) -> tuple[int, str]:
    """Score existing v1 dictionaries without forcing data sources to change yet."""
    if raw.get("score") is not None:
        return int(round(float(raw["score"]))), str(raw.get("reason") or raw.get("interpretation") or "")

    dex = raw.get("dex") or {}
    pm = raw.get("polymarket") or {}
    features = {
        "price_change_pct": raw.get("price_change_1h_pct") or raw.get("price_change_24h_pct") or dex.get("price_change_1h_pct") or dex.get("price_change_24h_pct"),
        "volume_change_pct": raw.get("volume_change_1h_pct") or raw.get("volume_change_pct") or dex.get("volume_change_1h_pct"),
        "whale_score": 20 if raw.get("whale_signal") or dex.get("whale_signal") else 0,
        "liquidity_change_pct": raw.get("liquidity_change_pct") or dex.get("liquidity_change_pct"),
        "polymarket_change_pct": raw.get("probability_change_pct") or pm.get("probability_change_pct"),
    }
    return score_features(features, cfg)
