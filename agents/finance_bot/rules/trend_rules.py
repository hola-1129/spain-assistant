import pandas as pd


def _mas(df: pd.DataFrame, periods: list) -> dict:
    close = df["Close"]
    return {p: close.rolling(p).mean().iloc[-1] for p in periods if len(close) >= p}


def check_trend_rules(symbol: str, hist: pd.DataFrame, cfg: dict) -> list:
    if hist is None or hist.empty:
        return []

    periods = cfg.get("ma_periods", [20, 50, 200])
    mas     = _mas(hist, periods)
    price   = hist["Close"].iloc[-1]
    alerts  = []

    if cfg.get("alert_below_ma200") and 200 in mas:
        ma = mas[200]
        if price < ma:
            alerts.append(
                f"🔴 *{symbol}* 跌破 MA200（高风险）\n"
                f"当前: ${price:,.2f}  MA200: ${ma:,.2f}  "
                f"偏差: {(price/ma - 1)*100:.1f}%"
            )

    if cfg.get("alert_below_ma50") and 50 in mas:
        ma = mas[50]
        if price < ma:
            alerts.append(
                f"🟡 *{symbol}* 跌破 MA50\n"
                f"当前: ${price:,.2f}  MA50: ${ma:,.2f}  "
                f"偏差: {(price/ma - 1)*100:.1f}%"
            )

    return alerts
