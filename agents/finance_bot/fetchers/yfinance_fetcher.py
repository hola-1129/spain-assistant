from datetime import date, datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from utils.logger import setup_logger

logger = setup_logger("yfinance_fetcher")


class YFinanceFetcher:
    def __init__(self, config: dict):
        self.config = config

    def get_quotes(self, symbols: list) -> dict:
        """Current quote for each symbol."""
        result = {}
        for sym in symbols:
            try:
                fi = yf.Ticker(sym).fast_info
                result[sym] = {
                    "price":      fi.last_price,
                    "prev_close": fi.previous_close,
                    "open":       fi.open,
                    "high":       fi.day_high,
                    "low":        fi.day_low,
                    "volume":     fi.three_month_average_volume,
                    "market_cap": getattr(fi, "market_cap", None),
                }
            except Exception as e:
                logger.warning(f"{sym} quote failed: {e}")
        return result

    def get_history(self, symbols: list, period: str = "1y") -> dict:
        """Daily OHLCV history for each symbol."""
        result = {}
        for sym in symbols:
            try:
                hist = yf.Ticker(sym).history(period=period)
                if not hist.empty:
                    result[sym] = hist
            except Exception as e:
                logger.warning(f"{sym} history failed: {e}")
        return result

    def get_options_chain(
        self, symbol: str, dte_min: int = 21, dte_max: int = 45
    ) -> Optional[pd.DataFrame]:
        """Options chain for the nearest expiry inside [dte_min, dte_max]."""
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations:
                return None

            today = date.today()
            target_exp = None

            for exp_str in expirations:
                dte = (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days
                if dte_min <= dte <= dte_max:
                    target_exp = exp_str
                    break

            # fallback: first expiry beyond dte_min
            if not target_exp:
                for exp_str in expirations:
                    dte = (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days
                    if dte >= dte_min:
                        target_exp = exp_str
                        break

            if not target_exp:
                return None

            dte = (datetime.strptime(target_exp, "%Y-%m-%d").date() - today).days
            chain = ticker.option_chain(target_exp)

            calls = chain.calls.copy()
            puts  = chain.puts.copy()
            for df, otype in [(calls, "call"), (puts, "put")]:
                df["option_type"] = otype
                df["dte"]         = dte
                df["expiration"]  = target_exp

            return pd.concat([calls, puts], ignore_index=True)
        except Exception as e:
            logger.warning(f"{symbol} options failed: {e}")
            return None

    def get_earnings_date(self, symbol: str) -> Optional[str]:
        try:
            cal = yf.Ticker(symbol).calendar
            if cal is None:
                return None
            if "Earnings Date" in cal.index:
                val = cal.loc["Earnings Date"]
                # calendar returns a Series or scalar
                first = val.iloc[0] if hasattr(val, "iloc") else val
                return str(first)[:10]
        except Exception:
            pass
        return None
