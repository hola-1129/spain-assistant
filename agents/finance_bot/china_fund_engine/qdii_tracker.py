"""QDII exposure tracker.

Aggregates US-facing QDII exposure across all accounts and
identifies overlap with direct US stock holdings.

Key outputs:
- Total QDII exposure by underlying market (US_TECH, US_TECH_INDEX, US_BROAD, etc.)
- Currency exposure (USD-denominated assets)
- Cross-account overlap (same strategy in multiple banks)
- Combined US tech exposure (direct stocks + QDII)
"""

from typing import Dict, List, Optional

from utils.logger import setup_logger

logger = setup_logger("qdii_tracker")

# How each underlying_market label maps to display categories
_MARKET_LABELS = {
    "US_TECH":       "美股科技（主动）",
    "US_TECH_INDEX": "美股科技指数（纳斯达克100等）",
    "US_BROAD":      "美股宽基（标普500等）",
    "GLOBAL_MULTI":  "全球多资产",
    "ASIA_PACIFIC":  "亚太",
    "GOLD":          "黄金",
    "A_STOCK":       "A股",
    "FIXED_INCOME":  "固定收益",
    "CASH":          "现金/货币",
}


class QDIIExposure:
    def __init__(self, underlying_market: str):
        self.underlying_market = underlying_market
        self.display_label     = _MARKET_LABELS.get(underlying_market, underlying_market)
        self.total_mv_cny:   float = 0.0
        self.positions:      List[dict] = []
        self.accounts:       List[str]  = []


def _f(row: dict, key: str) -> float:
    try:
        return float(row.get(key, 0) or 0)
    except (ValueError, TypeError):
        return 0.0


def _b(row: dict, key: str) -> bool:
    return str(row.get(key, "")).lower() in ("true", "1", "yes")


def aggregate_qdii_exposure(holdings: List[dict]) -> Dict[str, QDIIExposure]:
    """Aggregate QDII holdings by underlying_market."""
    exposures: Dict[str, QDIIExposure] = {}
    for h in holdings:
        if not _b(h, "qdii_flag") or not _b(h, "included_in_total_nav"):
            continue
        market = h.get("underlying_market", "UNKNOWN")
        if market not in exposures:
            exposures[market] = QDIIExposure(market)
        e = exposures[market]
        e.total_mv_cny += _f(h, "market_value_cny")
        e.positions.append(h)
        acct = h.get("account_name", "")
        if acct not in e.accounts:
            e.accounts.append(acct)
    return exposures


def compute_us_tech_total_cny(exposures: Dict[str, QDIIExposure]) -> float:
    """Sum of all US-facing QDII exposure in CNY."""
    return sum(
        e.total_mv_cny for mkt, e in exposures.items()
        if mkt in ("US_TECH", "US_TECH_INDEX", "US_BROAD")
    )


def overlap_summary(holdings: List[dict]) -> List[dict]:
    """Identify fund codes that appear in multiple accounts (strategy overlap risk)."""
    from collections import defaultdict
    code_rows: Dict[str, List[dict]] = defaultdict(list)
    for h in holdings:
        if not _b(h, "qdii_flag"):
            continue
        code = h.get("fund_code", "")
        if code and not code.startswith("MANUAL"):
            code_rows[code].append(h)

    overlaps = []
    for code, rows in code_rows.items():
        accts = list({r["account_name"] for r in rows})
        if len(accts) > 1:
            total = sum(_f(r, "market_value_cny") for r in rows)
            overlaps.append({
                "fund_code":   code,
                "fund_name":   rows[0].get("fund_name", code),
                "accounts":    accts,
                "total_mv_cny": total,
            })
    return overlaps


def build_qdii_report(
    holdings: List[dict],
    usd_cny_rate: float = 6.8,
    direct_us_stocks_usd: Optional[float] = None,
) -> dict:
    """Build comprehensive QDII exposure report.

    direct_us_stocks_usd: total market value of direct US stock holdings in USD.
                           If provided, computes combined US tech exposure.
    """
    exposures   = aggregate_qdii_exposure(holdings)
    overlaps    = overlap_summary(holdings)
    us_tech_cny = compute_us_tech_total_cny(exposures)
    us_tech_usd = us_tech_cny / usd_cny_rate

    # Build exposure table
    exposure_table = []
    for mkt, e in sorted(exposures.items(), key=lambda x: x[1].total_mv_cny, reverse=True):
        exposure_table.append({
            "market":      mkt,
            "label":       e.display_label,
            "mv_cny":      e.total_mv_cny,
            "mv_usd":      e.total_mv_cny / usd_cny_rate,
            "fund_count":  len(e.positions),
            "accounts":    e.accounts,
        })

    combined_us_usd = None
    if direct_us_stocks_usd is not None:
        combined_us_usd = us_tech_usd + direct_us_stocks_usd

    report = {
        "exposure_table":       exposure_table,
        "us_tech_qdii_cny":     us_tech_cny,
        "us_tech_qdii_usd":     us_tech_usd,
        "combined_us_total_usd": combined_us_usd,
        "overlap_risks":        overlaps,
        "usd_cny_rate":         usd_cny_rate,
    }
    logger.info(
        f"[qdii] US tech QDII: ¥{us_tech_cny:,.0f} / ${us_tech_usd:,.0f} USD"
        + (f"  Combined US: ${combined_us_usd:,.0f}" if combined_us_usd else "")
    )
    return report
