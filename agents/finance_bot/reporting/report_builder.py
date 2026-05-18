"""Build a ReportData from finance_bot portfolio data.

Called from scheduler._portfolio_daily_report() after quotes are fetched
and positions evaluated. Outputs a ReportData ready for:
    write_report() → render_html() → build_daily_index() → send_brief()

No LLM calls here — drafter output is passed in as pre-built strings.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

# Make shared importable whether called from agent root or venv
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.reporting.base_report import (
    ChartDataset,
    ChartSpec,
    OpportunityLevel,
    ReportData,
    RiskLevel,
)

_ACCOUNT_ORDER = ["IBKR", "FUTU", "moomoo"]


class FinanceBotReportBuilder:
    """Convert portfolio evaluation results into a structured ReportData."""

    def build(
        self,
        results: list,           # List[PositionResult] — avoid hard import for flexibility
        nav_base: float,
        date_str: str,
        advice_text: str = "",   # From drafter.build_advice_close()
        news_text: str = "",     # From drafter.build_news_section()
        macro_snapshot: Optional[Dict] = None,
    ) -> ReportData:

        agg = _Aggregates(results, nav_base)

        report = ReportData.for_agent(
            agent="finance_bot",
            date=date_str,
            summary=self._make_summary(agg),
            risk_level=self._risk_level(agg),
            opportunity_level=self._opp_level(agg),
        )

        report.add_section(
            "Portfolio Performance",
            self._section_performance(agg, date_str),
            chart=self._performance_chart(agg),
        )
        report.add_section(
            "Top Movers",
            self._section_movers(agg),
        )

        if agg.flagged:
            report.add_section(
                "Risk Signals",
                self._section_risk(agg),
            )

        if agg.house_positions:
            report.add_section(
                "House Money Positions",
                self._section_house(agg),
                collapsed=True,
            )

        if macro_snapshot:
            report.add_section(
                "Market Context",
                self._section_macro(macro_snapshot),
                collapsed=True,
            )

        if news_text:
            report.add_section(
                "Today's News",
                _strip_telegram_header(news_text),
                collapsed=True,
            )

        if advice_text:
            report.add_section(
                "AI Analysis (Claude)",
                _strip_telegram_header(advice_text),
                collapsed=True,
            )

        report.add_section(
            "Full Position Table",
            self._section_full_table(agg),
            collapsed=True,
        )

        return report

    # ── Summary sentence ──────────────────────────────────────────────────────

    def _make_summary(self, agg: "_Aggregates") -> str:
        day_str = f"{agg.overall_day_pct:+.1f}%"
        parts = [f"组合今日 {day_str}"]
        if agg.top_contributor:
            r = agg.top_contributor
            parts.append(f"{r.label} +{r.day_change_pct:.1f}% 贡献最大")
        if agg.top_detractor:
            r = agg.top_detractor
            parts.append(f"{r.label} {r.day_change_pct:.1f}% 拖累最大")
        if agg.flagged:
            parts.append(f"{len(agg.flagged)} 个仓位有风险提示")
        return "，".join(parts) + "。"

    # ── Risk / opportunity levels ─────────────────────────────────────────────

    def _risk_level(self, agg: "_Aggregates") -> RiskLevel:
        n_flags = sum(len(r.risk_flags) for r in agg.flagged)
        pct = agg.overall_day_pct
        if pct <= -3 or n_flags >= 3:
            return "high"
        if pct <= -1.5 or n_flags >= 1:
            return "medium"
        return "low"

    def _opp_level(self, agg: "_Aggregates") -> OpportunityLevel:
        pct = agg.overall_day_pct
        if pct >= 2:
            return "high"
        if pct >= 0.5:
            return "medium"
        return "low"

    # ── Section builders ──────────────────────────────────────────────────────

    def _section_performance(self, agg: "_Aggregates", date_str: str) -> str:
        lines = [
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 日期 | {date_str} |",
            f"| 总市值 | {_fmt_usd(agg.total_mv)} |",
            f"| 今日涨跌 | {agg.overall_day_pct:+.2f}% ({_fmt_signed_usd(agg.overall_day_usd)}) |",
        ]
        if agg.total_upnl is not None:
            upnl_base = agg.total_mv - agg.total_upnl
            upnl_pct = agg.total_upnl / upnl_base * 100 if upnl_base else 0
            lines.append(f"| 累计浮盈 | {_fmt_usd(agg.total_upnl)} ({upnl_pct:+.1f}%) |")
        lines.append(f"| NAV 基数 | {_fmt_usd(agg.nav_base)} |")
        lines.append("")

        # Per-account table
        lines.append("### 账户明细")
        lines.append("")
        by_acct: Dict[str, list] = defaultdict(list)
        for r in agg.results:
            by_acct[r.account].append(r)
        ordered = [a for a in _ACCOUNT_ORDER if a in by_acct]
        ordered += [a for a in by_acct if a not in _ACCOUNT_ORDER]

        for acct in ordered:
            group = by_acct[acct]
            acct_mv = sum(r.market_value for r in group)
            acct_day_pct = sum(r.day_change_pct * r.market_value for r in group) / acct_mv if acct_mv else 0
            lines.append(f"**{acct}** — {_fmt_usd(acct_mv)} ({acct_day_pct:+.1f}% 今日)")
            lines.append("")

        return "\n".join(lines)

    def _section_movers(self, agg: "_Aggregates") -> str:
        # Top 3 contributors
        contributors = sorted(agg.results, key=lambda r: r.day_change_pct, reverse=True)[:3]
        detractors = sorted(agg.results, key=lambda r: r.day_change_pct)[:3]

        lines = ["### 今日贡献项", ""]
        lines.append("| 标的 | 账户 | 今日 | 总盈亏 | 市值 |")
        lines.append("|------|------|------|--------|------|")
        for r in contributors:
            pnl = f"{r.pnl_pct:+.1f}%" if r.pnl_pct is not None else "—"
            lines.append(
                f"| {r.label} | {r.account} | {r.day_change_pct:+.1f}% | {pnl} | {_fmt_usd(r.market_value)} |"
            )

        lines += ["", "### 今日拖累项", ""]
        lines.append("| 标的 | 账户 | 今日 | 总盈亏 | 市值 |")
        lines.append("|------|------|------|--------|------|")
        for r in detractors:
            pnl = f"{r.pnl_pct:+.1f}%" if r.pnl_pct is not None else "—"
            lines.append(
                f"| {r.label} | {r.account} | {r.day_change_pct:+.1f}% | {pnl} | {_fmt_usd(r.market_value)} |"
            )
        return "\n".join(lines)

    def _section_risk(self, agg: "_Aggregates") -> str:
        lines = []
        for r in agg.flagged:
            for flag in r.risk_flags:
                lines.append(f"- **{r.label}** ({r.account}): {flag}")
        return "\n".join(lines)

    def _section_house(self, agg: "_Aggregates") -> str:
        lines = ["| 标的 | 总盈亏 | 市值 | 说明 |"]
        lines.append("|------|--------|------|------|")
        for r in agg.house_positions:
            pnl = f"{r.pnl_pct:+.1f}%" if r.pnl_pct is not None else "—"
            thesis = r.thesis or "—"
            lines.append(f"| {r.label} | {pnl} | {_fmt_usd(r.market_value)} | {thesis} |")
        return "\n".join(lines)

    def _section_macro(self, macro_snapshot: dict) -> str:
        if not macro_snapshot:
            return "_暂无宏观数据_"
        lines = []
        for key, val in macro_snapshot.items():
            if isinstance(val, float):
                lines.append(f"- **{key}**: {val:+.2f}%")
            else:
                lines.append(f"- **{key}**: {val}")
        return "\n".join(lines) if lines else "_暂无宏观数据_"

    def _section_full_table(self, agg: "_Aggregates") -> str:
        lines = ["| 标的 | 账户 | 股数 | 现价 | 市值 | 今日 | 总盈亏 | NAV% |"]
        lines.append("|------|------|------|------|------|------|--------|------|")
        for r in sorted(agg.results, key=lambda r: r.market_value, reverse=True):
            pnl = f"{r.pnl_pct:+.1f}%" if r.pnl_pct is not None else "—"
            lines.append(
                f"| {r.label} | {r.account} | {r.shares:,} "
                f"| ${r.current_price:.2f} | {_fmt_usd(r.market_value)} "
                f"| {r.day_change_pct:+.1f}% | {pnl} | {r.nav_pct:.1%} |"
            )
        return "\n".join(lines)

    # ── Chart ─────────────────────────────────────────────────────────────────

    def _performance_chart(self, agg: "_Aggregates") -> ChartSpec:
        # Top 5 movers by abs(day_change_pct)
        top = sorted(agg.results, key=lambda r: abs(r.day_change_pct), reverse=True)[:8]
        labels = [r.label for r in top]
        data = [round(r.day_change_pct, 2) for r in top]
        return ChartSpec(
            chart_type="bar",
            labels=labels,
            datasets=[ChartDataset(label="今日涨跌%", data=data)],
            title="持仓今日涨跌",
            y_suffix="%",
            height_px=200,
        )


# ── Internal aggregator ───────────────────────────────────────────────────────

class _Aggregates:
    def __init__(self, results: list, nav_base: float):
        self.results = results
        self.nav_base = nav_base
        self.total_mv = sum(r.market_value for r in results)
        prev_mv = sum(r.prev_close * r.shares for r in results)
        self.overall_day_usd = self.total_mv - prev_mv
        self.overall_day_pct = (self.overall_day_usd / prev_mv * 100) if prev_mv else 0.0
        self.total_upnl: Optional[float] = None
        for r in results:
            if r.unrealized_pnl is not None:
                self.total_upnl = (self.total_upnl or 0) + r.unrealized_pnl
        self.flagged = [r for r in results if r.risk_flags]
        self.house_positions = [r for r in results if r.rule_5a_done]
        pos = [r for r in results if r.day_change_pct > 0]
        neg = [r for r in results if r.day_change_pct < 0]
        self.top_contributor = max(pos, key=lambda r: r.day_change_pct) if pos else None
        self.top_detractor = min(neg, key=lambda r: r.day_change_pct) if neg else None


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_usd(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val/1_000_000:.2f}M"
    if abs(val) >= 1_000:
        return f"${val/1_000:.1f}K"
    return f"${val:.0f}"


def _fmt_signed_usd(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return sign + _fmt_usd(val)


def _strip_telegram_header(text: str) -> str:
    """Remove the first line of drafter output (e.g. '📰 *今日要闻*  ⚙️ Qwen') for cleaner HTML body."""
    lines = text.strip().splitlines()
    if lines and ("*" in lines[0] or lines[0].startswith(("📰", "🧠", "📊"))):
        lines = lines[1:]
    return "\n".join(lines).strip()
