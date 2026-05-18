"""Account reconciliation engine for China fund holdings.

Responsibilities:
1. Aggregate system-computed totals by account
2. Detect cross-account duplicate fund codes (same fund held in multiple banks)
3. Compare system totals against user-verified reference values
4. Flag discrepancies above threshold for manual review
5. NEVER silently correct discrepancies — always flag for human decision
"""

from typing import Dict, List, Optional, Tuple

from utils.logger import setup_logger

logger = setup_logger("china_reconciliation")

_DISCREPANCY_THRESHOLD_PCT = 3.0  # flag if system vs reference differs by >3%


class AccountSummary:
    def __init__(self, account: str):
        self.account        = account
        self.positions:     List[dict] = []
        self.total_mv_cny:  float = 0.0
        self.total_cost_cny:float = 0.0
        self.unrealized_pnl:float = 0.0
        self.pnl_pct:       float = 0.0

    def finalize(self):
        self.total_mv_cny   = sum(_f(p, "market_value_cny") for p in self.positions)
        self.total_cost_cny = sum(_f(p, "cost_basis_cny") for p in self.positions)
        self.unrealized_pnl = self.total_mv_cny - self.total_cost_cny
        if self.total_cost_cny:
            self.pnl_pct = self.unrealized_pnl / self.total_cost_cny * 100.0


class DuplicateFundAlert:
    def __init__(self, code: str, name: str, accounts: List[str], total_mv: float):
        self.code     = code
        self.name     = name
        self.accounts = accounts
        self.total_mv = total_mv


class DiscrepancyAlert:
    def __init__(self, account: str, system_mv: float, reference_mv: float, diff_pct: float):
        self.account      = account
        self.system_mv    = system_mv
        self.reference_mv = reference_mv
        self.diff_pct     = diff_pct


def _f(row: dict, key: str) -> float:
    try:
        return float(row.get(key, 0) or 0)
    except (ValueError, TypeError):
        return 0.0


def _b(row: dict, key: str) -> bool:
    return str(row.get(key, "")).lower() in ("true", "1", "yes")


def aggregate_by_account(holdings: List[dict]) -> Dict[str, AccountSummary]:
    """Build per-account summaries from holdings (included_in_total_nav=true only)."""
    summaries: Dict[str, AccountSummary] = {}
    for h in holdings:
        if not _b(h, "included_in_total_nav"):
            continue
        acct = h.get("account_name", "UNKNOWN")
        if acct not in summaries:
            summaries[acct] = AccountSummary(acct)
        summaries[acct].positions.append(h)
    for s in summaries.values():
        s.finalize()
    return summaries


def detect_cross_account_duplicates(holdings: List[dict]) -> List[DuplicateFundAlert]:
    """Identify the same fund code held across multiple accounts.

    Note: this is NOT double-counting (each holding is separate).
    It IS a concentration risk — same underlying fund in multiple banks.
    """
    from collections import defaultdict
    code_accts: Dict[str, List[dict]] = defaultdict(list)
    for h in holdings:
        code = h.get("fund_code", "")
        if (
            _b(h, "included_in_total_nav")
            and code
            and not code.startswith("MANUAL")
            and not code.startswith("STRATEGY")
        ):
            code_accts[code].append(h)

    alerts = []
    for code, rows in code_accts.items():
        accounts = list({r["account_name"] for r in rows})
        if len(accounts) > 1:
            total_mv  = sum(_f(r, "market_value_cny") for r in rows)
            fund_name = rows[0].get("fund_name", code)
            alerts.append(DuplicateFundAlert(code, fund_name, accounts, total_mv))
    return alerts


def compute_portfolio_total(summaries: Dict[str, AccountSummary]) -> Tuple[float, float, float]:
    """Return (total_mv, total_cost, total_pnl) across all accounts."""
    total_mv   = sum(s.total_mv_cny   for s in summaries.values())
    total_cost = sum(s.total_cost_cny for s in summaries.values())
    total_pnl  = sum(s.unrealized_pnl for s in summaries.values())
    return total_mv, total_cost, total_pnl


def check_discrepancies(
    summaries: Dict[str, AccountSummary],
    reference_values: Optional[Dict[str, float]] = None,
) -> List[DiscrepancyAlert]:
    """Compare system-computed account totals against user-provided reference values.

    reference_values: {account_name: verified_market_value_cny}
    Returns alerts for accounts where discrepancy > _DISCREPANCY_THRESHOLD_PCT.

    If reference_values is None or empty, no alerts are generated.
    """
    if not reference_values:
        return []
    alerts = []
    for acct, ref_mv in reference_values.items():
        sys_mv = summaries.get(acct)
        if not sys_mv or ref_mv <= 0:
            continue
        diff_pct = abs(sys_mv.total_mv_cny - ref_mv) / ref_mv * 100.0
        if diff_pct > _DISCREPANCY_THRESHOLD_PCT:
            alerts.append(DiscrepancyAlert(acct, sys_mv.total_mv_cny, ref_mv, diff_pct))
            logger.warning(
                f"[reconcile] {acct}: system={sys_mv.total_mv_cny:,.0f} "
                f"reference={ref_mv:,.0f} diff={diff_pct:.1f}%"
            )
    return alerts


def run_reconciliation(
    holdings: List[dict],
    reference_values: Optional[Dict[str, float]] = None,
) -> dict:
    """Full reconciliation pass. Returns structured report dict."""
    summaries   = aggregate_by_account(holdings)
    duplicates  = detect_cross_account_duplicates(holdings)
    discrepancies = check_discrepancies(summaries, reference_values)
    total_mv, total_cost, total_pnl = compute_portfolio_total(summaries)

    report = {
        "total_mv_cny":    total_mv,
        "total_cost_cny":  total_cost,
        "total_pnl_cny":   total_pnl,
        "pnl_pct":         (total_pnl / total_cost * 100) if total_cost else 0,
        "account_summaries": summaries,
        "duplicate_alerts":  duplicates,
        "discrepancy_alerts": discrepancies,
        "needs_manual_review": bool(discrepancies),
    }
    logger.info(
        f"[reconcile] total MV: ¥{total_mv:,.0f}  PnL: ¥{total_pnl:+,.0f} ({report['pnl_pct']:+.1f}%)"
        f"  duplicates: {len(duplicates)}  discrepancies: {len(discrepancies)}"
    )
    return report
