import pandas as pd


def _ret(series: pd.Series, days: int):
    if len(series) < days + 1:
        return None
    return (series.iloc[-1] / series.iloc[-days - 1] - 1) * 100


def check_alpha_rules(
    symbol: str,
    stock_hist: dict,
    crypto_hist: dict,
    cfg: dict,
) -> list:
    threshold = cfg.get("underperform_threshold_pct", 10.0)
    alerts    = []

    # vs SPY / QQQ
    if symbol in stock_hist:
        sym_s = stock_hist[symbol]["Close"]
        for bm in ["SPY", "QQQ"]:
            if bm not in stock_hist:
                continue
            bm_s = stock_hist[bm]["Close"]
            for days in cfg.get("vs_spy_qqq_periods", [20, 60]):
                sr = _ret(sym_s, days)
                br = _ret(bm_s, days)
                if sr is None or br is None:
                    continue
                diff = sr - br
                if diff <= -threshold:
                    alerts.append(
                        f"⚠️ *{symbol}* 跑输 {bm} {days} 日\n"
                        f"{symbol}: {sr:+.1f}%  {bm}: {br:+.1f}%  差距: {diff:.1f}%"
                    )

    # vs BTC (only for crypto assets)
    if symbol in crypto_hist and "BTC" in crypto_hist:
        sym_s = crypto_hist[symbol]["Close"]
        btc_s = crypto_hist["BTC"]["Close"]
        for days in cfg.get("vs_btc_periods", [7, 30]):
            sr = _ret(sym_s, days)
            br = _ret(btc_s, days)
            if sr is None or br is None:
                continue
            diff = sr - br
            if diff <= -threshold:
                alerts.append(
                    f"⚠️ *{symbol}* 跑输 BTC {days} 日\n"
                    f"{symbol}: {sr:+.1f}%  BTC: {br:+.1f}%  差距: {diff:.1f}%"
                )

    return alerts
