"""Risk filter — final gate before push.

v1 conservative: only checks fields available from free APIs (DexScreener pool data).
Other checks (verified contract, honeypot, tax, holder concentration) are placeholders
and will be wired in v2 with GoPlus / Honeypot.is.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("web3_monitor.risk")


def evaluate(signal: dict[str, Any], cfg: dict[str, Any]) -> dict:
    """Return {passed: bool, penalty: int (0..15), reasons: [str]}."""
    rf = cfg.get("risk_filter", {})
    thr = cfg.get("thresholds", {})
    reasons: list[str] = []
    penalty = 0
    passed = True

    dex = signal.get("dex") or {}
    pm = signal.get("polymarket") or {}

    # ── Liquidity ────────────────────────────────────────────────────
    if dex:
        liq = float(dex.get("liquidity_usd") or 0)
        min_liq = thr.get("min_liquidity_usd", 50000)
        if liq < min_liq:
            reasons.append("low_liquidity")
            penalty += 5
            if rf.get("reject_low_liquidity", True):
                passed = False
        vol = float(dex.get("volume_1h_usd") or dex.get("volume_24h_usd") or 0)
        min_vol = thr.get("min_volume_1h_usd", 0)
        if vol < min_vol:
            reasons.append("low_volume")
            penalty += 5
            if rf.get("reject_low_volume", True):
                passed = False

    # ── Contract verification (placeholder) ──────────────────────────
    if dex and rf.get("reject_unknown_contract", True):
        if dex.get("contract_verified") is False:
            reasons.append("unknown_contract")
            penalty += 5
            passed = False

    # ── Honeypot / tax / holder concentration: v2 ────────────────────
    if dex.get("honeypot") is True:
        reasons.append("honeypot")
        penalty += 10
        if rf.get("reject_honeypot_if_detected", True):
            passed = False
    if isinstance(dex.get("buy_tax_pct"), (int, float)) and dex["buy_tax_pct"] > 10:
        reasons.append("high_buy_tax")
        penalty += 3
        if rf.get("reject_high_tax_if_detected", True):
            passed = False
    if isinstance(dex.get("top_holder_pct"), (int, float)) and dex["top_holder_pct"] > 30:
        reasons.append("holder_concentration")
        penalty += 2
        if rf.get("reject_holder_concentration_if_detected", True):
            passed = False

    # ── Polymarket noise filter ──────────────────────────────────────
    if pm:
        if pm.get("closed"):
            reasons.append("event_closed")
            passed = False
        vol = float(pm.get("volume_24h_usd") or 0)
        if vol < 5000:
            reasons.append("polymarket_low_volume")
            penalty += 3

    penalty = min(penalty, 15)
    return {"passed": passed, "penalty": penalty, "reasons": reasons}
