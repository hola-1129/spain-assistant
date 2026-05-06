"""RSI, MACD, MA crossover signals."""
import math
import pandas as pd
from .base import Signal


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean().iloc[-1]
    loss  = (-delta.clip(upper=0)).rolling(period).mean().iloc[-1]
    if loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def _macd_hist(close: pd.Series, fast=12, slow=26, sig=9):
    ml = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sl = ml.ewm(span=sig, adjust=False).mean()
    return (ml - sl).iloc[-1], (ml - sl).iloc[-2]


def _macd_lines(close: pd.Series, fast=12, slow=26, sig=9):
    """Returns (macd_now, signal_now, macd_prev, signal_prev)."""
    ml = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sl = ml.ewm(span=sig, adjust=False).mean()
    return ml.iloc[-1], sl.iloc[-1], ml.iloc[-2], sl.iloc[-2]


def _rolling_ma(close: pd.Series, p: int):
    m = close.rolling(p).mean()
    return m.iloc[-1], m.iloc[-2]


def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    # loss=0 → rs=inf → RSI=100 (all gains, no losses); handled naturally
    rs = gain / loss
    return 100.0 - 100.0 / (1.0 + rs)


def _find_divergence(close: pd.Series, lookback: int = 20):
    """Detect RSI divergence over the last `lookback` bars.
    Returns 'bull' (底背离), 'bear' (顶背离), or None.
    Requires price swing amplitude ≥ 2% to filter noise.
    """
    if len(close) < lookback + 15:
        return None

    rsi_full = _rsi_series(close)
    prices   = close.iloc[-lookback:].values
    rsi_vals = rsi_full.iloc[-lookback:].values

    highs, lows = [], []
    for i in range(1, len(prices) - 1):
        if prices[i] > prices[i - 1] and prices[i] > prices[i + 1]:
            highs.append((prices[i], rsi_vals[i]))
        if prices[i] < prices[i - 1] and prices[i] < prices[i + 1]:
            lows.append((prices[i], rsi_vals[i]))

    if len(highs) >= 2:
        p1, r1 = highs[-2]
        p2, r2 = highs[-1]

        if not (math.isnan(r1) or math.isnan(r2)):
            if p2 > p1 * 1.02 and r2 < r1:   # 价格高点抬升 ≥2% 但 RSI 下降
                return "bear"

    if len(lows) >= 2:
        p1, r1 = lows[-2]
        p2, r2 = lows[-1]

        if not (math.isnan(r1) or math.isnan(r2)):
            if p2 < p1 * 0.98 and r2 > r1:   # 价格低点下移 ≥2% 但 RSI 抬升
                return "bull"

    return None


def analyze_momentum(symbol: str, hist: pd.DataFrame) -> list:
    if hist is None or len(hist) < 30:
        return []

    close   = hist["Close"]
    price   = close.iloc[-1]
    prev    = close.iloc[-2]
    signals = []

    # ── RSI ──────────────────────────────────────────────────────────────
    if len(close) >= 16:
        rsi_now  = _rsi(close)
        rsi_prev = _rsi(close.iloc[:-1])

        if rsi_now <= 30:
            signals.append(Signal(symbol, "rsi_oversold", "bullish",
                strength=min((30 - rsi_now) / 20, 1.0),
                label="RSI 超卖",
                detail=f"RSI={rsi_now:.0f}，历史支撑区域",
                value=rsi_now))
        elif rsi_now >= 70:
            signals.append(Signal(symbol, "rsi_overbought", "bearish",
                strength=min((rsi_now - 70) / 20, 1.0),
                label="RSI 超买",
                detail=f"RSI={rsi_now:.0f}，注意回调风险",
                value=rsi_now))

        if rsi_prev < 50 <= rsi_now:
            signals.append(Signal(symbol, "rsi_cross_up", "bullish",
                strength=0.4, label="RSI 穿越 50",
                detail=f"RSI {rsi_prev:.0f}→{rsi_now:.0f}，动能转正",
                value=rsi_now))
        elif rsi_prev > 50 >= rsi_now:
            signals.append(Signal(symbol, "rsi_cross_down", "bearish",
                strength=0.4, label="RSI 跌破 50",
                detail=f"RSI {rsi_prev:.0f}→{rsi_now:.0f}，动能转负",
                value=rsi_now))

    # ── RSI 背离 ─────────────────────────────────────────────────────────
    if len(close) >= 35:
        div = _find_divergence(close)
        if div == "bear":
            signals.append(Signal(symbol, "rsi_divergence_bear", "bearish",
                strength=0.7, label="RSI 顶背离",
                detail="价格创近期新高但 RSI 未跟进，动能衰减，注意反转",
                value=0.0))
        elif div == "bull":
            signals.append(Signal(symbol, "rsi_divergence_bull", "bullish",
                strength=0.7, label="RSI 底背离",
                detail="价格创近期新低但 RSI 未跟进，卖压减弱，关注反弹",
                value=0.0))

    # ── MACD ─────────────────────────────────────────────────────────────
    if len(close) >= 27:
        h_now, h_prev = _macd_hist(close)
        if h_prev < 0 <= h_now:
            signals.append(Signal(symbol, "macd_golden", "bullish",
                strength=0.6, label="MACD 金叉",
                detail=f"柱状图翻正，动能加速向上",
                value=h_now))
        elif h_prev > 0 >= h_now:
            signals.append(Signal(symbol, "macd_death", "bearish",
                strength=0.6, label="MACD 死叉",
                detail=f"柱状图翻负，动能减速",
                value=h_now))

        # MACD 线 vs 信号线交叉（传统金叉/死叉，比柱状图叉更早）
        ml_now, sl_now, ml_prev, sl_prev = _macd_lines(close)
        if ml_prev <= sl_prev and ml_now > sl_now:
            signals.append(Signal(symbol, "macd_line_cross_up", "bullish",
                strength=0.6, label="MACD 线叉（多头）",
                detail=f"MACD线 {ml_now:.4f} 上穿信号线 {sl_now:.4f}",
                value=ml_now - sl_now))
        elif ml_prev >= sl_prev and ml_now < sl_now:
            signals.append(Signal(symbol, "macd_line_cross_down", "bearish",
                strength=0.6, label="MACD 线叉（空头）",
                detail=f"MACD线 {ml_now:.4f} 下穿信号线 {sl_now:.4f}",
                value=ml_now - sl_now))

    # ── MA 穿越 / 跌破 ────────────────────────────────────────────────────
    if len(close) >= 52:
        ma50_now,  ma50_prev  = _rolling_ma(close, 50)
        # price vs MA50
        if prev >= ma50_prev and price < ma50_now:
            signals.append(Signal(symbol, "break_ma50", "bearish",
                strength=0.65, label="跌破 MA50",
                detail=f"${price:.2f} 跌破 MA50=${ma50_now:.2f}",
                value=price))
        elif prev <= ma50_prev and price > ma50_now:
            signals.append(Signal(symbol, "reclaim_ma50", "bullish",
                strength=0.65, label="收复 MA50",
                detail=f"${price:.2f} 重回 MA50=${ma50_now:.2f}",
                value=price))

    if len(close) >= 201:
        ma200_now, ma200_prev = _rolling_ma(close, 200)
        ma50_now,  ma50_prev  = _rolling_ma(close, 50)

        # price vs MA200
        if prev >= ma200_prev and price < ma200_now:
            signals.append(Signal(symbol, "break_ma200", "bearish",
                strength=0.9, label="跌破 MA200（高风险）",
                detail=f"${price:.2f} 跌破 MA200=${ma200_now:.2f}",
                value=price))
        elif prev <= ma200_prev and price > ma200_now:
            signals.append(Signal(symbol, "reclaim_ma200", "bullish",
                strength=0.9, label="收复 MA200",
                detail=f"${price:.2f} 重回 MA200=${ma200_now:.2f}",
                value=price))

        # Golden / Death cross (MA50 vs MA200)
        if ma50_prev <= ma200_prev and ma50_now > ma200_now:
            signals.append(Signal(symbol, "golden_cross", "bullish",
                strength=1.0, label="黄金交叉 MA50×MA200",
                detail=f"MA50={ma50_now:.2f} 上穿 MA200={ma200_now:.2f}",
                value=ma50_now))
        elif ma50_prev >= ma200_prev and ma50_now < ma200_now:
            signals.append(Signal(symbol, "death_cross", "bearish",
                strength=1.0, label="死亡交叉 MA50×MA200",
                detail=f"MA50={ma50_now:.2f} 下穿 MA200={ma200_now:.2f}",
                value=ma50_now))

    return signals
