"""Volume anomaly signals — accumulation / distribution / dry-up."""
import pandas as pd
from .base import Signal


def analyze_volume(symbol: str, hist: pd.DataFrame) -> list:
    if hist is None or "Volume" not in hist.columns or len(hist) < 22:
        return []

    close   = hist["Close"]
    vol     = hist["Volume"]
    price   = close.iloc[-1]
    prev    = close.iloc[-2]
    pct     = (price - prev) / prev * 100
    vol_now = vol.iloc[-1]
    vol_avg = vol.iloc[-21:-1].mean()

    if vol_avg <= 0:
        return []

    ratio   = vol_now / vol_avg
    signals = []

    if ratio >= 2.0 and abs(pct) >= 0.8:
        direction = "bullish" if pct > 0 else "bearish"
        label     = "放量上涨（积累）" if pct > 0 else "放量下跌（派发）"
        signals.append(Signal(symbol, "volume_spike", direction,
            strength=min((ratio - 2.0) / 2.0 + 0.5, 1.0),
            label=label,
            detail=f"量比 {ratio:.1f}×，日涨跌 {pct:+.1f}%",
            value=ratio))

    elif ratio >= 1.5 and abs(pct) >= 2.0:
        # 量不够大但价格波动显著——方向性信号
        direction = "bullish" if pct > 0 else "bearish"
        signals.append(Signal(symbol, "volume_mild_spike", direction,
            strength=0.35,
            label="温和放量" + ("上涨" if pct > 0 else "下跌"),
            detail=f"量比 {ratio:.1f}×，日涨跌 {pct:+.1f}%",
            value=ratio))

    elif ratio <= 0.35 and abs(pct) < 0.5:
        # 极度缩量平盘 = 方向未定，关注后续
        signals.append(Signal(symbol, "volume_dryup", "neutral",
            strength=0.3, label="极度缩量",
            detail=f"量比 {ratio:.1f}×，价格几乎不动，蓄势待发",
            value=ratio))

    return signals
