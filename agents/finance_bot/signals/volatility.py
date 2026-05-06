"""Bollinger Bands, ATR, 52-week range signals."""
import pandas as pd
from .base import Signal


def _bb(close: pd.Series, period=20, nstd=2.0):
    ma    = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    return (ma + nstd * sigma).iloc[-1], ma.iloc[-1], (ma - nstd * sigma).iloc[-1]


def _atr(hist: pd.DataFrame, period=14) -> pd.Series:
    h, l, c = hist["High"], hist["Low"], hist["Close"]
    tr = pd.concat([h - l,
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def analyze_volatility(symbol: str, hist: pd.DataFrame) -> list:
    if hist is None or len(hist) < 25:
        return []

    close   = hist["Close"]
    price   = close.iloc[-1]
    prev    = close.iloc[-2]
    signals = []

    # ── Bollinger Bands ───────────────────────────────────────────────────
    upper, mid, lower = _bb(close)
    prev_upper, _, prev_lower = _bb(close.iloc[:-1])

    if prev <= prev_upper and price > upper:
        pct = (price - upper) / upper * 100
        signals.append(Signal(symbol, "bb_break_up", "neutral",
            strength=min(pct / 3.0, 1.0),
            label="突破布林上轨",
            detail=f"${price:.2f} 超出上轨 ${upper:.2f}（+{pct:.1f}%），高波动",
            value=pct))
    elif prev >= prev_lower and price < lower:
        pct = (lower - price) / lower * 100
        signals.append(Signal(symbol, "bb_break_down", "bearish",
            strength=min(pct / 3.0, 1.0),
            label="跌破布林下轨",
            detail=f"${price:.2f} 跌破下轨 ${lower:.2f}（-{pct:.1f}%）",
            value=pct))

    # Bollinger squeeze（带宽收至近期最窄 → 方向性突破将至）
    if len(close) >= 40:
        bw_now  = (upper - lower) / mid if mid > 0 else 0
        bws     = []
        for i in range(-30, -1):
            s = close.iloc[:i]
            u2, m2, l2 = _bb(s)
            if m2 > 0:
                bws.append((u2 - l2) / m2)
        if bws and bw_now <= min(bws) * 1.05:
            signals.append(Signal(symbol, "bb_squeeze", "neutral",
                strength=0.5, label="布林带极度收窄",
                detail=f"带宽 {bw_now:.3f}，逼近近期最小，大方向突破临近",
                value=bw_now))

    # ── ATR 扩张 ─────────────────────────────────────────────────────────
    if "High" in hist.columns and "Low" in hist.columns:
        atr_s   = _atr(hist)
        atr_now = atr_s.iloc[-1]
        atr_avg = atr_s.iloc[-21:-1].mean()
        if atr_avg > 0:
            ratio = atr_now / atr_avg
            if ratio >= 1.8:
                signals.append(Signal(symbol, "atr_expansion", "neutral",
                    strength=min((ratio - 1.8) / 1.2 + 0.4, 1.0),
                    label="波动率骤升",
                    detail=f"ATR 是近期均值的 {ratio:.1f}×，市场正在剧烈波动",
                    value=ratio))

    # ── 52 周高低点 ───────────────────────────────────────────────────────
    if len(close) >= 252:
        high52 = close.rolling(252).max().iloc[-1]
        low52  = close.rolling(252).min().iloc[-1]
        if price >= high52 * 0.99:
            signals.append(Signal(symbol, "near_52w_high", "bullish",
                strength=0.7 if price >= high52 else 0.4,
                label="触及年内高点",
                detail=f"${price:.2f}，年高 ${high52:.2f}（{(price/high52-1)*100:+.1f}%）",
                value=price / high52))
        elif price <= low52 * 1.01:
            signals.append(Signal(symbol, "near_52w_low", "bearish",
                strength=0.7 if price <= low52 else 0.4,
                label="触及年内低点",
                detail=f"${price:.2f}，年低 ${low52:.2f}（{(price/low52-1)*100:+.1f}%）",
                value=price / low52))

    return signals
