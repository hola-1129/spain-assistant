import math
from datetime import date, datetime
from typing import Optional

import pandas as pd
from scipy.stats import norm


def _bs_delta(S: float, K: float, T: float, r: float, sigma: float, kind: str) -> float:
    """Black-Scholes delta. T in years."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return (1.0 if kind == "call" else 0.0) if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) if kind == "call" else norm.cdf(d1) - 1.0


def _ann_premium(premium: float, strike: float, dte: int) -> float:
    if strike <= 0 or dte <= 0:
        return 0.0
    return (premium / strike) * (365 / dte) * 100


def _iv_rank(current_iv: float, history: list) -> Optional[float]:
    if len(history) < 20:
        return None
    ivs  = [row[1] for row in history]
    lo, hi = min(ivs), max(ivs)
    return 0.0 if hi <= lo else (current_iv - lo) / (hi - lo) * 100


def check_options_rules(
    symbol: str,
    cfg: dict,
    options_df: Optional[pd.DataFrame],
    iv_history: list,
    current_price: float,
) -> list:
    if options_df is None or options_df.empty or not current_price:
        return []

    r               = cfg.get("risk_free_rate", 0.05)
    min_prem_pct    = cfg.get("min_annualized_premium_pct", 15.0)
    cc_delta_tgt    = cfg.get("covered_call_delta", 0.30)
    csp_delta_tgt   = cfg.get("csp_delta", -0.30)
    ivr_high        = cfg.get("iv_rank_high", 50)
    alerts          = []

    # --- IV Rank ----------------------------------------------------------
    calls = options_df[options_df["option_type"] == "call"]
    atm_iv = None
    if not calls.empty and "impliedVolatility" in calls.columns:
        idx    = (calls["strike"] - current_price).abs().idxmin()
        atm_iv = calls.loc[idx, "impliedVolatility"]

    ivr = _iv_rank(atm_iv, iv_history) if atm_iv else None
    if atm_iv and iv_history:
        if ivr is not None and ivr >= ivr_high:
            alerts.append(
                f"📊 *{symbol}* IV Rank {ivr:.0f} — 适合卖权\n"
                f"ATM IV: {atm_iv*100:.1f}%"
            )

    # --- Covered Call candidate -------------------------------------------
    if not calls.empty and "dte" in calls.columns:
        dte = int(calls["dte"].iloc[0])
        T   = dte / 365
        best, best_diff = None, float("inf")
        for _, row in calls.iterrows():
            iv = row.get("impliedVolatility") or 0
            if iv <= 0:
                continue
            d    = _bs_delta(current_price, row["strike"], T, r, iv, "call")
            diff = abs(d - cc_delta_tgt)
            if diff < best_diff:
                best_diff, best = diff, (row, d)

        if best:
            row, delta = best
            mid        = ((row.get("bid") or 0) + (row.get("ask") or 0)) / 2
            ann_yield  = _ann_premium(mid, row["strike"], dte)
            if ann_yield >= min_prem_pct:
                alerts.append(
                    f"📞 *{symbol}* Covered Call 候选\n"
                    f"行权价 ${row['strike']:.1f}  DTE {dte}  "
                    f"Δ {delta:.2f}  年化 {ann_yield:.1f}%\n"
                    f"到期 {row.get('expiration', 'N/A')}"
                )

    # --- Cash-Secured Put candidate ---------------------------------------
    puts = options_df[options_df["option_type"] == "put"]
    if not puts.empty and "dte" in puts.columns:
        dte = int(puts["dte"].iloc[0])
        T   = dte / 365
        best, best_diff = None, float("inf")
        for _, row in puts.iterrows():
            iv = row.get("impliedVolatility") or 0
            if iv <= 0:
                continue
            d    = _bs_delta(current_price, row["strike"], T, r, iv, "put")
            diff = abs(d - csp_delta_tgt)
            if diff < best_diff:
                best_diff, best = diff, (row, d)

        if best:
            row, delta = best
            mid        = ((row.get("bid") or 0) + (row.get("ask") or 0)) / 2
            ann_yield  = _ann_premium(mid, row["strike"], dte)
            if ann_yield >= min_prem_pct:
                alerts.append(
                    f"💰 *{symbol}* CSP 候选\n"
                    f"行权价 ${row['strike']:.1f}  DTE {dte}  "
                    f"Δ {delta:.2f}  年化 {ann_yield:.1f}%\n"
                    f"到期 {row.get('expiration', 'N/A')}"
                )

    return alerts


def check_earnings_alert(symbol: str, earnings_str: Optional[str], cfg: dict) -> list:
    if not earnings_str:
        return []
    n = cfg.get("earnings_alert_days", 14)
    try:
        ed   = datetime.strptime(earnings_str[:10], "%Y-%m-%d").date()
        days = (ed - date.today()).days
        if 0 <= days <= n:
            return [
                f"📅 *{symbol}* 财报日 {earnings_str[:10]}（{days} 天后）\n"
                f"注意 IV 膨胀，谨慎卖权"
            ]
    except (ValueError, TypeError):
        pass
    return []
