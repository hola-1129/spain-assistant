"""
Unusual score (0–100).

Weights:
  A. Price movement      30 %
  B. Volume ratio        25 %
  C. Breakout/breakdown  25 %
  D. Relative alpha      20 %
"""


# Per-asset-type price-move thresholds that count as "unusual"
_PRICE_THRESHOLD = {"stock": 5.0, "etf": 2.5, "crypto": 8.0}


def compute_unusual_score(data: dict) -> float:
    score = 0.0

    atype     = data.get("asset_type", "stock")
    threshold = _PRICE_THRESHOLD.get(atype, 5.0)

    # ── A. Price (30 pts) ────────────────────────────────────────────────
    move = abs(data.get("daily_change_pct", 0.0))
    if move >= threshold:
        score += min(move / (threshold * 3.0) * 30.0, 30.0)

    # ── B. Volume (25 pts) ───────────────────────────────────────────────
    ratio = data.get("volume_ratio", 1.0)
    if ratio >= 2.0:
        score += min((ratio - 1.0) / 4.0 * 25.0, 25.0)

    # ── C. Breakout / breakdown (25 pts) ─────────────────────────────────
    if data.get("new_52w_high") or data.get("new_52w_low"):
        score += 25.0
    elif data.get("new_20d_high") or data.get("new_20d_low"):
        score += 14.0

    # ── D. Alpha (20 pts) ────────────────────────────────────────────────
    alpha = max(abs(data.get("alpha_5d", 0.0)),
                abs(data.get("alpha_20d", 0.0)))
    score += min(alpha / 15.0 * 20.0, 20.0)

    return round(min(score, 100.0), 1)


def classify_level(score: float) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    return "LOW"


def format_alert(result: dict) -> str:
    level   = result["level"]
    sym     = result["symbol"]
    chg     = result["daily_change_pct"]
    vol_r   = result.get("volume_ratio", 1.0)
    score   = result["unusual_score"]
    signals = result.get("signals", [])
    price   = result.get("price", 0)

    emoji   = "🚨" if level == "HIGH" else "⚡"
    arrow   = "📈" if chg > 0 else "📉"

    lines = [
        f"{emoji} *[UNUSUAL][{level}]*",
        f"*{sym}*  {arrow} {chg:+.2f}%  ${price:,.2f}",
        f"📊 Volume: {vol_r:.1f}× avg",
    ]
    if signals:
        lines.append(f"🎯 {' + '.join(signals)}")
    lines.append(f"Score: {score:.0f}/100")
    return "\n".join(lines)
