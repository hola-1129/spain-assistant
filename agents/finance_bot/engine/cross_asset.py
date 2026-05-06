"""
Cross-asset divergence signals:
  - SPY vs QQQ rotation
  - BTC vs ETH internal crypto health
  - Individual crypto diverging from ETH
"""
from signals.base import Signal


def _ret(hist_dict: dict, symbol: str, days: int):
    h = hist_dict.get(symbol)
    if h is None or len(h) < days + 1:
        return None
    s = h["Close"] if "Close" in h.columns else h.iloc[:, 0]
    return (s.iloc[-1] / s.iloc[-days - 1] - 1) * 100


def analyze_cross_asset(stock_hist: dict, crypto_hist: dict) -> list:
    signals = []

    # ── SPY vs QQQ ────────────────────────────────────────────────────────
    spy5 = _ret(stock_hist, "SPY", 5)
    qqq5 = _ret(stock_hist, "QQQ", 5)
    if spy5 is not None and qqq5 is not None:
        diff = qqq5 - spy5
        if diff <= -5:
            signals.append(Signal("MARKET", "growth_rotation_out", "bearish",
                strength=min(abs(diff) / 10, 1.0),
                label="成长股资金流出",
                detail=f"QQQ 5日 {qqq5:+.1f}% vs SPY {spy5:+.1f}%，科技承压",
                value=diff))
        elif diff >= 5:
            signals.append(Signal("MARKET", "growth_rotation_in", "bullish",
                strength=min(diff / 10, 1.0),
                label="成长股资金流入",
                detail=f"QQQ 5日 {qqq5:+.1f}% vs SPY {spy5:+.1f}%，科技领跑",
                value=diff))

    # ── BTC vs ETH ────────────────────────────────────────────────────────
    btc3 = _ret(crypto_hist, "BTC", 3)
    eth3 = _ret(crypto_hist, "ETH", 3)
    if btc3 is not None and eth3 is not None:
        div = eth3 - btc3
        if div >= 8:
            signals.append(Signal("CRYPTO", "altcoin_season_hint", "bullish",
                strength=min(div / 15, 1.0),
                label="ETH 跑赢 BTC",
                detail=f"ETH 3日 {eth3:+.1f}% vs BTC {btc3:+.1f}%，山寨生态活跃",
                value=div))
        elif div <= -8:
            signals.append(Signal("CRYPTO", "btc_dominance_rise", "neutral",
                strength=min(abs(div) / 15, 1.0),
                label="BTC 主导上升",
                detail=f"BTC 3日 {btc3:+.1f}% vs ETH {eth3:+.1f}%，资金回流主流",
                value=div))

    # ── WLD vs ETH ────────────────────────────────────────────────────────
    wld5 = _ret(crypto_hist, "WLD", 5)
    eth5 = _ret(crypto_hist, "ETH", 5)
    if wld5 is not None and eth5 is not None:
        diff = wld5 - eth5
        if abs(diff) >= 12:
            direction = "bullish" if diff > 0 else "bearish"
            signals.append(Signal("WLD", "wld_diverge", direction,
                strength=min(abs(diff) / 20, 1.0),
                label="WLD 独立走" + ("强" if diff > 0 else "弱"),
                detail=f"WLD 5日 {wld5:+.1f}% vs ETH {eth5:+.1f}%，差距 {diff:+.0f}%",
                value=diff))

    return signals
