"""Portfolio position monitor — evaluates holdings against NAV risk rules."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from utils.logger import setup_logger

logger = setup_logger("portfolio_monitor")

# Theme → (display_label, nav_pct_warning_threshold)
_THEME_RULES: Dict[str, tuple] = {
    "space": ("Space 主题 (RKLB+PL)", 0.12),
    "hims":  ("HIMS 合并仓位",         0.12),
}


@dataclass
class PositionResult:
    symbol:          str
    label:           str
    shares:          int
    account:         str
    current_price:   float
    prev_close:      float
    market_value:    float
    cost_total:      Optional[float]
    unrealized_pnl:  Optional[float]
    pnl_pct:         Optional[float]
    nav_pct:         float
    day_change_pct:  float
    rule_5a_done:    bool
    rule_1b_exception: bool
    thesis:          Optional[str]
    risk_flags:      List[str] = field(default_factory=list)


class PortfolioMonitor:
    """Evaluate portfolio positions against NAV-based risk rules.

    Positions are configured in config.yaml under ``portfolio.positions``.
    Each entry must have at least: symbol, shares, account.
    Optional fields: cost_per_share, label, rule_5a_done, rule_1b_exception,
                     thesis, theme.
    """

    def __init__(self, config: dict):
        pcfg = config.get("portfolio", {})
        self.nav_base   = float(pcfg.get("nav_base", 1_000_000))
        self.rule_1a    = float(pcfg.get("rule_1a_pct", 0.12))
        self.rule_1b    = float(pcfg.get("rule_1b_pct", 0.20))
        self._positions = [p for p in pcfg.get("positions", []) if p.get("shares")]

    # ── Public API ────────────────────────────────────────────────────────

    def get_symbols(self) -> List[str]:
        """Unique ticker symbols needed for quote fetch."""
        return list({p["symbol"] for p in self._positions})

    def evaluate(self, quotes: Dict[str, dict]) -> List[PositionResult]:
        """Return a PositionResult for each configured position.

        Positions missing from quotes are skipped with a warning.
        Results are sorted by market_value descending.
        """
        # First pass: build results and accumulate theme totals
        theme_nav: Dict[str, float] = {}
        results: List[PositionResult] = []

        for pos in self._positions:
            sym    = pos["symbol"]
            shares = pos["shares"]
            q      = quotes.get(sym)
            if not q:
                logger.warning(f"[portfolio] no quote for {sym}, skipping")
                continue

            price   = q.get("price") or 0.0
            prev    = q.get("prev_close") or price
            mv      = price * shares
            nav_pct = mv / self.nav_base if self.nav_base else 0.0
            day_chg = ((price - prev) / prev * 100.0) if prev else 0.0

            cost_ps    = pos.get("cost_per_share")
            cost_total = (cost_ps * shares) if cost_ps else None
            upnl       = (mv - cost_total) if cost_total is not None else None
            pnl_pct    = ((mv / cost_total - 1) * 100.0) if cost_total else None

            label   = pos.get("label", sym)
            rule_5a = bool(pos.get("rule_5a_done", False))
            rule_1b = bool(pos.get("rule_1b_exception", False))
            thesis  = pos.get("thesis")
            theme   = pos.get("theme")

            if theme:
                theme_nav[theme] = theme_nav.get(theme, 0.0) + nav_pct

            r = PositionResult(
                symbol=sym,
                label=label,
                shares=shares,
                account=pos.get("account", ""),
                current_price=price,
                prev_close=prev,
                market_value=mv,
                cost_total=cost_total,
                unrealized_pnl=upnl,
                pnl_pct=pnl_pct,
                nav_pct=nav_pct,
                day_change_pct=day_chg,
                rule_5a_done=rule_5a,
                rule_1b_exception=rule_1b,
                thesis=thesis,
            )
            results.append(r)

        # Second pass: attach per-position risk flags
        for r in results:
            r.risk_flags = self._flags(r, theme_nav)

        results.sort(key=lambda r: r.market_value, reverse=True)
        return results

    # ── Risk flag evaluation ──────────────────────────────────────────────

    def _flags(self, r: PositionResult, theme_nav: Dict[str, float]) -> List[str]:
        flags: List[str] = []

        # Single-position concentration
        if r.nav_pct > self.rule_1b:
            flags.append(f"🚨 超 Rule 1B 上限: {r.nav_pct:.1%} > {self.rule_1b:.0%}")
        elif r.nav_pct > self.rule_1a:
            if r.rule_1b_exception:
                flags.append(f"ℹ️  Rule 1B 例外生效 ({r.nav_pct:.1%})")
            else:
                flags.append(f"🔴 Rule 1A 触发: {r.nav_pct:.1%} > {self.rule_1a:.0%}")
        elif r.nav_pct > self.rule_1a * 0.85:
            flags.append(f"🟡 接近 Rule 1A: {r.nav_pct:.1%}")

        # Loss position check (non-house-money only)
        if r.pnl_pct is not None and r.pnl_pct < -20 and not r.rule_5a_done:
            flags.append(f"⚠️  亏损 {r.pnl_pct:.1f}% — 确认 Thesis 仍有效")

        # Theme-level concentration
        pos_cfg = next(
            (p for p in self._positions if p.get("label", p["symbol"]) == r.label),
            {}
        )
        theme = pos_cfg.get("theme")
        if theme and theme in theme_nav and theme in _THEME_RULES:
            disp, threshold = _THEME_RULES[theme]
            total = theme_nav[theme]
            if total > threshold:
                flag = f"🟡 {disp}: {total:.1%} 合计 > {threshold:.0%}"
                if flag not in flags:
                    flags.append(flag)

        return flags

    def has_alerts(self, results: List[PositionResult]) -> bool:
        return any(r.risk_flags for r in results)
