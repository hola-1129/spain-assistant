"""
Market regime classifier.
Output: risk level (risk_on / caution / risk_off) + 0–10 score.
"""
import pandas as pd


def classify_regime(stock_hist: dict, vix_data: dict) -> dict:
    score = 5  # start neutral

    # ── VIX ──────────────────────────────────────────────────────────────
    vix = (vix_data.get("^VIX") or {}).get("price")
    if vix:
        if vix < 15:   score += 2
        elif vix < 20: score += 1
        elif vix < 25: score += 0
        elif vix < 30: score -= 2
        else:          score -= 3

    # ── SPY 趋势 ──────────────────────────────────────────────────────────
    spy_trend = "unknown"
    spy = stock_hist.get("SPY")
    if spy is not None and len(spy) >= 200:
        price  = spy["Close"].iloc[-1]
        ma50   = spy["Close"].rolling(50).mean().iloc[-1]
        ma200  = spy["Close"].rolling(200).mean().iloc[-1]
        if price > ma50 > ma200:
            spy_trend = "above_ma50"; score += 2
        elif price > ma200:
            spy_trend = "above_ma200"; score += 1
        else:
            spy_trend = "below_ma200"; score -= 2

    # ── QQQ vs SPY 5日强弱 ────────────────────────────────────────────────
    qqq = stock_hist.get("QQQ")
    spread_note = ""
    if spy is not None and qqq is not None and len(spy) > 6 and len(qqq) > 6:
        spy5 = (spy["Close"].iloc[-1] / spy["Close"].iloc[-6] - 1) * 100
        qqq5 = (qqq["Close"].iloc[-1] / qqq["Close"].iloc[-6] - 1) * 100
        diff = qqq5 - spy5
        if diff >= 3:
            score += 1
            spread_note = f"科技领涨（QQQ-SPY 5日差 {diff:+.1f}%）"
        elif diff <= -3:
            score -= 1
            spread_note = f"科技落后（QQQ-SPY 5日差 {diff:+.1f}%）"

    # ── US10Y 趋势（利率走向）────────────────────────────────────────────────
    tnx = stock_hist.get("^TNX")
    if tnx is not None and len(tnx) >= 20:
        tnx_price = tnx["Close"].iloc[-1]
        tnx_ma20  = tnx["Close"].rolling(20).mean().iloc[-1]
        if tnx_price > tnx_ma20 * 1.02:   # 利率明显高于 MA20 → 紧缩压力
            score -= 1

    # ── 5Y-10Y 收益率曲线 ─────────────────────────────────────────────────────
    fvx = stock_hist.get("^FVX")
    yield_curve_note = ""
    if tnx is not None and fvx is not None and len(tnx) > 1 and len(fvx) > 1:
        tnx_val  = tnx["Close"].iloc[-1]
        fvx_val  = fvx["Close"].iloc[-1]
        spread   = fvx_val - tnx_val          # 正值 = 5Y > 10Y = 倒挂
        if spread > 0:
            score -= 1
            yield_curve_note = f"⚠️ 收益率曲线倒挂（5Y {fvx_val:.2f}% > 10Y {tnx_val:.2f}%）"
        elif spread < -0.5:                   # 陡峭正常曲线 → 略加分
            score += 1
            yield_curve_note = f"利率曲线陡峭（5Y {fvx_val:.2f}%，10Y {tnx_val:.2f}%，差 {spread:.2f}%）"
        else:
            yield_curve_note = f"利率曲线正常（5Y {fvx_val:.2f}%，10Y {tnx_val:.2f}%）"

    # ── Gold vs SPY 5日强弱（避险信号）──────────────────────────────────────
    gold = stock_hist.get("GC=F")
    gold_note = ""
    if gold is not None and spy is not None and len(gold) > 6 and len(spy) > 6:
        gold5 = (gold["Close"].iloc[-1] / gold["Close"].iloc[-6] - 1) * 100
        spy5r = (spy["Close"].iloc[-1]  / spy["Close"].iloc[-6]  - 1) * 100
        diff  = gold5 - spy5r
        if diff >= 5:
            score -= 1
            gold_note = f"黄金避险（Gold 5日 {gold5:+.1f}% vs SPY {spy5r:+.1f}%）"

    score = max(0, min(10, score))

    if score >= 8:
        risk_level, label = "risk_on",     "风险偏好 🟢"
    elif score >= 6:
        risk_level, label = "recovery",    "宽松重启 🔵"
    elif score >= 4:
        risk_level, label = "caution",     "谨慎观望 🟡"
    elif score >= 2:
        risk_level, label = "stagflation", "滞胀警戒 🟠"
    else:
        risk_level, label = "risk_off",    "规避风险 🔴"

    return {
        "risk_level":        risk_level,
        "label":             label,
        "score":             score,
        "vix":               vix,
        "spy_trend":         spy_trend,
        "spread_note":       spread_note,
        "yield_curve_note":  yield_curve_note,
        "gold_note":         gold_note,
    }
