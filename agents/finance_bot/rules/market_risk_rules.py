import pandas as pd


def _drawdown_from_high(series: pd.Series, lookback: int = 252) -> float:
    recent  = series.tail(lookback)
    peak    = recent.max()
    current = recent.iloc[-1]
    return 0.0 if peak <= 0 else (current / peak - 1) * 100


def check_market_risk_rules(market_data: dict, hist: dict, cfg: dict) -> list:
    alerts = []

    # VIX
    vix_data = market_data.get("^VIX", {})
    vix      = vix_data.get("price")
    if vix:
        if vix >= cfg.get("vix_extreme", 35):
            alerts.append(
                f"🚨 *VIX* 极端恐慌: {vix:.1f}\n市场剧烈动荡，严控风险敞口"
            )
        elif vix >= cfg.get("vix_high", 25):
            alerts.append(
                f"⚠️ *VIX* 偏高: {vix:.1f}\n波动率上升，注意仓位"
            )

    # SPY / QQQ 回撤
    for sym in ["SPY", "QQQ"]:
        if sym not in hist:
            continue
        dd        = _drawdown_from_high(hist[sym]["Close"])
        threshold = cfg.get(f"{sym.lower()}_drawdown_pct", 10.0)
        if dd <= -threshold:
            price = hist[sym]["Close"].iloc[-1]
            alerts.append(
                f"📉 *{sym}* 从高点回撤 {abs(dd):.1f}%\n当前: ${price:,.2f}"
            )

    return alerts
