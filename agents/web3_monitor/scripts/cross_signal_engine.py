"""Cross-signal engine — combines DEX + Polymarket + cross-validation, returns 100-point score.

Components (per strategies/cross_signal_engine.md):
  A. DEX anomaly        35
  B. Polymarket event   25
  C. Cross validation   25
  D. Risk filter        15  (subtracted from full 15 by penalty)
"""
from __future__ import annotations

import logging
from typing import Iterable

from risk_filter import evaluate as risk_evaluate

logger = logging.getLogger("web3_monitor.engine")

# Common-name aliases so "Bitcoin" matches BTC, "Ethereum" matches ETH, etc.
_ASSET_ALIASES: dict[str, list[str]] = {
    "BTC":   ["BITCOIN", "BTC"],
    "ETH":   ["ETHEREUM", "ETHER", "ETH"],
    "SOL":   ["SOLANA", "SOL"],
    "BNB":   ["BINANCE", "BNB"],
    "DOGE":  ["DOGECOIN", "DOGE"],
    "LINK":  ["CHAINLINK", "LINK"],
    "UNI":   ["UNISWAP", "UNI"],
    "ARB":   ["ARBITRUM", "ARB"],
    "OP":    ["OPTIMISM", "OP"],
    "WLD":   ["WORLDCOIN", "WLD"],
    "MATIC": ["POLYGON", "MATIC"],
    "ONDO":  ["ONDO"],
    "AAVE":  ["AAVE"],
    "PEPE":  ["PEPE"],
}

# Polymarket tags that indicate a crypto-related event
_CRYPTO_TAGS = {"crypto", "bitcoin", "ethereum", "defi", "etf", "blockchain"}


# ── A: DEX score ────────────────────────────────────────────────────
def _dex_score(dex: dict, thresholds: dict) -> int:
    if not dex:
        return 0
    price_thr = thresholds.get("price_change_1h_pct", 8)
    price24_thr = thresholds.get("price_change_24h_pct", 20)
    vol_thr = thresholds.get("volume_change_1h_pct", 80)
    min_liq = thresholds.get("min_liquidity_usd", 50000)

    # Price (max 10): take stronger of 1h or 24h normalized
    p1h = abs(float(dex.get("price_change_1h_pct") or 0))
    p24 = abs(float(dex.get("price_change_24h_pct") or 0))
    price_score = max(min(p1h / price_thr, 1.0), min(p24 / price24_thr, 1.0)) * 10

    # Volume (max 10)
    v1h = float(dex.get("volume_change_1h_pct") or 0)
    volume_score = min(max(v1h / vol_thr, 0.0), 1.0) * 10

    # Liquidity quality (max 10)
    liq = float(dex.get("liquidity_usd") or 0)
    if liq <= 0:
        liquidity_score = 0
    else:
        # 50k → 5 pts, 500k → 8 pts, 5M+ → 10 pts (log-ish)
        if liq < min_liq:
            liquidity_score = 0
        elif liq < min_liq * 10:
            liquidity_score = 5 + (liq - min_liq) / (min_liq * 9) * 3
        else:
            liquidity_score = min(8 + (liq - min_liq * 10) / (min_liq * 90) * 2, 10)

    # Multi-pool sync (max 5)
    multi_pool_score = 5 if dex.get("multi_pool") else 0

    return int(round(price_score + volume_score + liquidity_score + multi_pool_score))


# ── B: Polymarket score ─────────────────────────────────────────────
def _polymarket_score(pm: dict, thresholds: dict, relevant_tags: Iterable[str]) -> int:
    if not pm:
        return 0
    prob_thr = thresholds.get("polymarket_probability_change_pct", 8)
    vol_thr = thresholds.get("polymarket_volume_change_pct", 100)

    prob_change = abs(float(pm.get("probability_change_pct") or 0))
    prob_score = min(prob_change / prob_thr, 1.0) * 10

    vol_change = float(pm.get("volume_change_pct") or 0)
    vol_score = min(max(vol_change / vol_thr, 0.0), 1.0) * 5

    # Time proximity (max 5): closer = higher
    days_to_resolve = pm.get("days_to_resolve")
    time_score = 0
    if isinstance(days_to_resolve, (int, float)):
        if days_to_resolve <= 7:
            time_score = 5
        elif days_to_resolve <= 14:
            time_score = 4
        elif days_to_resolve <= 30:
            time_score = 2

    # Relevance (max 5): tag in relevant set
    rel = 5 if (pm.get("tag") in set(relevant_tags)) else 0

    return int(round(prob_score + vol_score + time_score + rel))


# ── C: Cross-validation ─────────────────────────────────────────────
def _cross_score(dex: dict, pm: dict) -> tuple[int, str]:
    if not dex or not pm:
        return 0, ""
    score = 0
    notes: list[str] = []

    # Polymarket prob ↑ aligned with DEX price ↑ (or both down)
    p_change_pm = float(pm.get("probability_change_pct") or 0)
    p_change_dex = float(dex.get("price_change_1h_pct") or 0)
    if p_change_pm * p_change_dex > 0 and abs(p_change_pm) >= 5 and abs(p_change_dex) >= 3:
        score += 10
        notes.append("Polymarket 概率与链上价格同向异动")

    # Volume both up
    v_pm = float(pm.get("volume_change_pct") or 0)
    v_dex = float(dex.get("volume_change_1h_pct") or 0)
    if v_pm > 50 and v_dex > 50:
        score += 5
        notes.append("DEX 成交量与事件热度同步上升")

    # Multi-chain (uses multi_pool flag as proxy)
    if dex.get("multi_pool"):
        score += 5
        notes.append("多池/多链同步异动")

    # Whale slot reserved (v1 placeholder)
    if dex.get("whale_signal"):
        score += 5
        notes.append("巨鲸/聪明钱线索")

    return min(score, 25), "；".join(notes)


# ── D: Risk score (15 - penalty) ────────────────────────────────────
def _risk_score(signal: dict, cfg: dict) -> tuple[int, dict]:
    res = risk_evaluate(signal, cfg)
    score = max(0, 15 - res["penalty"])
    return score, res


# ── Public API ──────────────────────────────────────────────────────
def evaluate(dex: dict | None, pm: dict | None, cfg: dict) -> dict | None:
    """Build a combined signal and return scored dict, or None if risk filter rejects."""
    thresholds = cfg.get("thresholds", {})
    relevant_tags = cfg.get("polymarket_categories", [])

    signal: dict = {
        "type": "cross" if (dex and pm) else ("dex" if dex else "polymarket"),
        "asset": (dex or {}).get("asset") or (pm or {}).get("asset"),
        "chain": (dex or {}).get("chain"),
        "dex": dex,
        "polymarket": pm,
    }

    a = _dex_score(dex or {}, thresholds)
    b = _polymarket_score(pm or {}, thresholds, relevant_tags)
    c, cross_note = _cross_score(dex or {}, pm or {})
    d, risk_res = _risk_score(signal, cfg)

    total = min(a + b + c + d, 100)
    high = thresholds.get("high_signal_score", 80)
    minp = thresholds.get("min_signal_score", 60)

    if not risk_res["passed"]:
        logger.info(f"risk reject {signal.get('asset')}: {risk_res['reasons']}")
        return None

    level = "HIGH" if total >= high else ("MEDIUM" if total >= minp else "LOW")
    interp_parts: list[str] = []
    if cross_note:
        interp_parts.append(cross_note)
    if pm:
        interp_parts.append(f"事件 '{pm.get('title','')[:60]}' 概率/成交量短期变化")
    if dex:
        interp_parts.append(f"DEX 池子 1h 价格 {dex.get('price_change_1h_pct',0):+.1f}%、量比变化 {dex.get('volume_change_1h_pct',0):+.0f}%")

    signal.update({
        "score": total,
        "level": level,
        "components": {"A": a, "B": b, "C": c, "D": d},
        "risk": risk_res,
        "interpretation": "；".join(interp_parts),
    })
    return signal


def pair_dex_with_polymarket(
    dex_candidates: list[dict], pm_snapshots: list[dict]
) -> list[tuple[dict | None, dict | None]]:
    """Alias-aware pairing: title match first, crypto-tag fallback second.

    Pass 1 — alias title match: check asset symbol and common-name aliases
      against the Polymarket event title (e.g. "Bitcoin" matches BTC).
    Pass 2 — crypto-tag fallback: remaining DEX candidates without a PM match
      are paired with any leftover crypto-tagged PM events, one-to-one.
    Pass 3 — unpaired items passed through as (dex, None) / (None, pm).
    """
    pairs: list[tuple[dict | None, dict | None]] = []
    used_pm: set[int] = set()

    logger.debug("pairing: %d DEX candidates, %d PM snapshots",
                 len(dex_candidates), len(pm_snapshots))

    # Pass 1: alias-aware title match
    for d in dex_candidates:
        sym = (d.get("asset") or "").upper()
        keywords = _ASSET_ALIASES.get(sym, [sym]) if sym else []
        match = None
        for i, pm in enumerate(pm_snapshots):
            if i in used_pm:
                continue
            title = (pm.get("title") or "").upper()
            if any(kw in title for kw in keywords):
                match = pm
                used_pm.add(i)
                logger.debug("[pass1] alias  %s → \"%s\" (kw=%s)",
                             sym, pm.get("title", "")[:50],
                             next(kw for kw in keywords if kw in title))
                break
        if match is None:
            logger.debug("[pass1] no-match %s (keywords=%s)", sym, keywords)
        pairs.append((d, match))

    # Pass 2: crypto-tag fallback for still-unmatched DEX candidates
    crypto_pm_pool = [
        (i, pm) for i, pm in enumerate(pm_snapshots)
        if i not in used_pm and (pm.get("tag") or "").lower() in _CRYPTO_TAGS
    ]
    logger.debug("[pass2] %d unmatched DEX, %d crypto-tagged PM available for fallback",
                 sum(1 for _, pm in pairs if pm is None), len(crypto_pm_pool))
    fallback_iter = iter(crypto_pm_pool)
    for idx, (d, pm) in enumerate(pairs):
        if pm is not None:
            continue
        try:
            i, fallback_pm = next(fallback_iter)
            pairs[idx] = (d, fallback_pm)
            used_pm.add(i)
            logger.debug("[pass2] fallback %s → \"%s\" (tag=%s)",
                         d.get("asset"), fallback_pm.get("title", "")[:50],
                         fallback_pm.get("tag"))
        except StopIteration:
            break

    # Pass 3: unpaired PM events scored independently
    solo_pm = 0
    for i, pm in enumerate(pm_snapshots):
        if i not in used_pm:
            pairs.append((None, pm))
            solo_pm += 1
            logger.debug("[pass3] solo-pm  \"%s\" (tag=%s)",
                         pm.get("title", "")[:50], pm.get("tag"))

    matched  = sum(1 for d, pm in pairs if d and pm)
    dex_only = sum(1 for d, pm in pairs if d and not pm)
    logger.info("pairing done: %d matched, %d dex-only, %d pm-only",
                matched, dex_only, solo_pm)

    return pairs
