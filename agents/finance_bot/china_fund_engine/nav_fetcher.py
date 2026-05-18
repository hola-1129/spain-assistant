"""China fund NAV fetcher using AKShare.

Fetches latest NAV and daily change for each fund in holdings_master.csv.
Updates derived_units and current market values.

Strategy:
- Funds with code_status=VERIFIED: fetch from AKShare, update holding_units & market_value
- Funds with code_status=MANUAL_ONLY: skip, keep last_manual_value
- Holds: derived_units = market_value_cny / latest_nav (one-time bootstrap)
         daily update: market_value_cny = holding_units * latest_nav
"""

import csv
import os
import time
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

from utils.logger import setup_logger

logger = setup_logger("china_nav_fetcher")

_HOLDINGS_CSV = os.path.join(os.path.dirname(__file__), "holdings_master.csv")


class FundNAV:
    """NAV snapshot for a single fund."""
    def __init__(self, code: str, nav: float, daily_change_pct: float, nav_date: str):
        self.code             = code
        self.nav              = nav
        self.daily_change_pct = daily_change_pct
        self.nav_date         = nav_date

    def __repr__(self):
        return f"FundNAV({self.code}, nav={self.nav:.4f}, chg={self.daily_change_pct:+.2f}%, date={self.nav_date})"


def _fetch_single_nav(code: str, retries: int = 2) -> Optional[FundNAV]:
    """Fetch latest NAV for one fund code via AKShare."""
    try:
        import akshare as ak
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势", period="近1月")
        if df.empty:
            logger.warning(f"[nav] {code}: empty response")
            return None
        last = df.iloc[-1]
        nav      = float(last["单位净值"])
        daily    = float(last["日增长率"]) if last["日增长率"] != "" else 0.0
        nav_date = str(last["净值日期"])
        return FundNAV(code, nav, daily, nav_date)
    except Exception as e:
        if retries > 0:
            time.sleep(1)
            return _fetch_single_nav(code, retries - 1)
        logger.error(f"[nav] {code}: fetch failed — {e}")
        return None


def fetch_all_navs(holdings: List[dict]) -> Dict[str, FundNAV]:
    """Fetch NAV for all VERIFIED funds. Returns {code: FundNAV}."""
    codes = list({
        h["fund_code"]
        for h in holdings
        if h.get("code_status") == "VERIFIED" and h.get("fund_code")
    })
    logger.info(f"[nav] fetching {len(codes)} unique fund codes...")
    results: Dict[str, FundNAV] = {}
    for code in codes:
        nav = _fetch_single_nav(code)
        if nav:
            results[code] = nav
            logger.debug(f"[nav] {code}: {nav}")
        time.sleep(0.2)  # polite throttle
    logger.info(f"[nav] fetched {len(results)}/{len(codes)} successfully")
    return results


def load_holdings() -> List[dict]:
    """Load holdings_master.csv as list of dicts."""
    if not os.path.exists(_HOLDINGS_CSV):
        logger.error(f"[nav] holdings_master.csv not found at {_HOLDINGS_CSV}")
        return []
    with open(_HOLDINGS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_holdings(holdings: List[dict]) -> None:
    """Write holdings back to holdings_master.csv."""
    if not holdings:
        return
    fieldnames = list(holdings[0].keys())
    with open(_HOLDINGS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(holdings)


def update_market_values(holdings: List[dict], navs: Dict[str, FundNAV]) -> List[dict]:
    """Update market_value_cny and holding_units for each holding using fetched NAVs.

    Bootstrap logic:
    - If holding_units is empty and we have a NAV, derive units from last known MV.
    - Otherwise: market_value_cny = float(holding_units) * nav
    """
    today = date.today().isoformat()
    updated = []
    for h in holdings:
        code = h.get("fund_code", "")
        nav  = navs.get(code)
        h = dict(h)  # copy

        if not nav or h.get("code_status") != "VERIFIED":
            updated.append(h)
            continue

        units_str = h.get("holding_units", "").strip()
        mv_str    = h.get("market_value_cny", "").strip()

        if not units_str and mv_str:
            # Bootstrap: derive units from last known market value
            try:
                last_mv = float(mv_str)
                derived  = last_mv / nav.nav
                h["holding_units"] = f"{derived:.4f}"
                logger.info(f"[nav] {code} bootstrap units: {derived:.2f} @ NAV {nav.nav:.4f}")
            except (ValueError, ZeroDivisionError):
                updated.append(h)
                continue

        # Now compute updated market value
        try:
            units    = float(h["holding_units"])
            new_mv   = units * nav.nav
            h["market_value_cny"] = f"{new_mv:.2f}"
            h["last_verified"]    = today
        except (ValueError, ZeroDivisionError):
            pass

        updated.append(h)

    return updated


def run_daily_update() -> Tuple[List[dict], Dict[str, FundNAV]]:
    """Main entry: load → fetch NAVs → update → save. Returns (updated_holdings, navs)."""
    logger.info("[nav] starting daily NAV update")
    holdings = load_holdings()
    if not holdings:
        return [], {}
    navs     = fetch_all_navs(holdings)
    updated  = update_market_values(holdings, navs)
    save_holdings(updated)
    logger.info(f"[nav] daily update complete: {len(updated)} positions")
    return updated, navs
