"""Build a ReportData from a RadarSnapshot.

Called from main.py RadarRunner.run_daily_close() after snapshot is built.
Outputs a ReportData ready for write_report() → render_html() → send_brief().

No LLM calls — all content is RULE-tier derived from RadarSnapshot fields.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

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

_SIGNAL_LABEL = {
    "STRONG":     "🟢 Strong",
    "BROADENING": "🔵 Broadening",
    "NEUTRAL":    "⚪ Neutral",
    "NARROWING":  "🟡 Narrowing",
    "WEAK":       "🔴 Weak",
}


class RadarReportBuilder:
    """Convert a RadarSnapshot into a structured ReportData."""

    def build(self, snapshot, date_str: str, min_leaps_score: float = 75.0) -> ReportData:
        """
        snapshot: RadarSnapshot instance
        date_str: YYYY-MM-DD string
        min_leaps_score: LEAPS candidates below this are omitted from the report
        """
        theme_breadths = list(snapshot.theme_breadths.values())
        sorted_themes  = sorted(theme_breadths, key=lambda b: b.avg_rs_spy_1m, reverse=True)
        leading        = [b for b in sorted_themes if b.signal in ("STRONG", "BROADENING")]
        weakening      = [b for b in sorted_themes if b.signal in ("WEAK", "NARROWING")]
        neutral        = [b for b in sorted_themes if b.signal == "NEUTRAL"]
        leaps_hits     = [c for c in snapshot.leaps_candidates if c.leaps_score >= min_leaps_score]
        rotation       = snapshot.rotation_signal

        report = ReportData.for_agent(
            agent="ai_narrative_rotation_radar",
            date=date_str,
            summary=self._make_summary(sorted_themes, leaps_hits, rotation),
            risk_level=self._risk_level(weakening, rotation),
            opportunity_level=self._opp_level(leading, leaps_hits),
        )

        # 1. Benchmark context
        if snapshot.benchmark_metrics:
            report.add_section(
                "Benchmark Context",
                self._section_benchmarks(snapshot.benchmark_metrics),
            )

        # 2. Leading themes (always visible)
        if leading:
            report.add_section(
                "Leading Themes",
                self._section_themes(leading),
                chart=self._themes_chart(sorted_themes[:8]),
            )
        else:
            report.add_section(
                "Theme Overview",
                self._section_themes(sorted_themes[:6]),
                chart=self._themes_chart(sorted_themes[:8]),
            )

        # 3. Weakening themes
        if weakening:
            report.add_section(
                "Weakening Themes",
                self._section_themes(weakening),
            )

        # 4. Rotation signal (only when detected)
        if rotation and rotation.detected:
            report.add_section(
                "Rotation Signal",
                self._section_rotation(rotation, snapshot.theme_breadths),
            )

        # 5. Individual leaders
        top_tickers = sorted(
            snapshot.ticker_metrics.values(),
            key=lambda m: m.composite_score,
            reverse=True,
        )[:8]
        if top_tickers:
            report.add_section(
                "Individual Leaders",
                self._section_leaders(top_tickers),
            )

        # 6. LEAPS candidates
        if leaps_hits:
            report.add_section(
                "LEAPS Call Candidates",
                self._section_leaps(leaps_hits),
            )

        # 7. Neutral themes (collapsed)
        if neutral:
            report.add_section(
                "Neutral Themes",
                self._section_themes(neutral),
                collapsed=True,
            )

        # 8. Full theme table (collapsed)
        report.add_section(
            "All Themes (Full Table)",
            self._section_all_themes(sorted_themes),
            collapsed=True,
        )

        # 9. Full ticker table (collapsed)
        all_metrics = sorted(
            snapshot.ticker_metrics.values(),
            key=lambda m: m.composite_score,
            reverse=True,
        )
        if all_metrics:
            report.add_section(
                "All Tickers (Full Table)",
                self._section_all_tickers(all_metrics, snapshot.ticker_to_theme),
                collapsed=True,
            )

        return report

    # ── Summary ───────────────────────────────────────────────────────────────

    def _make_summary(self, sorted_themes, leaps_hits, rotation) -> str:
        parts = []
        if sorted_themes:
            top = sorted_themes[0]
            if top.signal in ("STRONG", "BROADENING"):
                parts.append(f"{top.theme_name} 叙事领跑（RS {top.avg_rs_spy_1m:+.1f}%）")
        if leaps_hits:
            top_leaps = leaps_hits[0]
            parts.append(f"LEAPS 候选：{top_leaps.ticker}（{top_leaps.leaps_score:.0f}/100）")
        if rotation and rotation.detected:
            parts.append(f"资金轮动信号（置信度 {rotation.confidence}/100）")
        if not parts:
            parts.append("多数叙事中性，未见明显强势方向")
        return "，".join(parts) + "。"

    # ── Risk / opportunity ────────────────────────────────────────────────────

    def _risk_level(self, weakening, rotation) -> RiskLevel:
        n_weak = sum(1 for b in weakening if b.signal == "WEAK")
        if n_weak >= 3 or (rotation and rotation.detected and rotation.confidence >= 80 and n_weak >= 2):
            return "high"
        if n_weak >= 1 or len(weakening) >= 3:
            return "medium"
        return "low"

    def _opp_level(self, leading, leaps_hits) -> OpportunityLevel:
        n_strong = sum(1 for b in leading if b.signal == "STRONG")
        if n_strong >= 2 or (n_strong >= 1 and leaps_hits):
            return "high"
        if leading or leaps_hits:
            return "medium"
        return "low"

    # ── Section builders ──────────────────────────────────────────────────────

    def _section_benchmarks(self, benchmark_metrics: dict) -> str:
        lines = ["| 标的 | 1D | 5D | 1M | 3M |"]
        lines.append("|------|----|----|----|-----|")
        for ticker, m in benchmark_metrics.items():
            lines.append(
                f"| {ticker} | {m.ret_1d:+.1f}% | {m.ret_5d:+.1f}% "
                f"| {m.ret_1m:+.1f}% | {m.ret_3m:+.1f}% |"
            )
        return "\n".join(lines)

    def _section_themes(self, themes: list) -> str:
        if not themes:
            return "_无数据_"
        lines = ["| 叙事 | 信号 | RS vs SPY 1M | Breadth | Vol Ratio | Leaders |"]
        lines.append("|------|------|-------------|---------|-----------|---------|")
        for b in themes:
            label   = _SIGNAL_LABEL.get(b.signal, b.signal)
            leaders = " / ".join(b.leaders[:2]) if b.leaders else "—"
            lines.append(
                f"| {b.theme_name} | {label} "
                f"| {b.avg_rs_spy_1m:+.1f}% "
                f"| {b.breadth_rs*100:.0f}% "
                f"| {b.avg_volume_ratio:.1f}x "
                f"| {leaders} |"
            )
        return "\n".join(lines)

    def _section_rotation(self, rotation, theme_breadths: dict) -> str:
        to_names   = [
            theme_breadths[k].theme_name for k in rotation.to_themes[:3] if k in theme_breadths
        ]
        from_names = [
            theme_breadths[k].theme_name for k in rotation.from_themes[:3] if k in theme_breadths
        ]
        lines = [
            f"**资金流向**：{' / '.join(from_names) or '—'} → {' / '.join(to_names) or '—'}",
            f"**置信度**：{rotation.confidence}/100",
            f"**RS 最大摆动**：{rotation.max_swing:+.1f}%",
            "",
            rotation.description if rotation.description else "_无描述_",
        ]
        return "\n".join(lines)

    def _section_leaders(self, top_metrics: list) -> str:
        lines = ["| 标的 | 1D | RS 1M | RS 1D | 20D MA | Vol Ratio | Score |"]
        lines.append("|------|----|----|-------|--------|-----------|-------|")
        for m in top_metrics:
            ma_str = "↑20D" if m.above_20dma else "↓20D"
            lines.append(
                f"| {m.ticker} | {m.ret_1d:+.1f}% "
                f"| {m.rs_vs_spy_1m:+.1f}% | {m.rs_vs_spy_1d:+.1f}% "
                f"| {ma_str} | {m.volume_ratio_20d:.1f}x "
                f"| {m.composite_score:.0f} |"
            )
        return "\n".join(lines)

    def _section_leaps(self, candidates: list) -> str:
        lines = [
            "| 标的 | 叙事 | Score | 信号类型 | Options | Triggers |",
            "|------|------|-------|---------|---------|----------|",
        ]
        signal_short = {
            "LEAPS_CALL_CANDIDATE":        "Candidate",
            "LEAPS_SETUP_PULLBACK":        "Pullback",
            "LEAPS_RESEARCH_ONLY":         "Research",
            "LEAPS_HIGH_RISK_SPECULATIVE": "High Risk",
        }
        for c in candidates:
            sig  = signal_short.get(c.signal_type, c.signal_type)
            opts = f"{c.options_quality} ({c.nearest_leaps_expiry})" if c.has_leaps else "需手动确认"
            trigs = "; ".join(c.triggers[:2]) if c.triggers else "—"
            lines.append(
                f"| **{c.ticker}** | {c.theme_name} "
                f"| {c.leaps_score:.0f}/100 | {sig} | {opts} | {trigs} |"
            )
        lines.append("")
        lines.append("_LEAPS 信号仅供研究参考，需人工复核。不是自动交易信号。_")
        return "\n".join(lines)

    def _section_all_themes(self, themes: list) -> str:
        lines = [
            "| 叙事 | 信号 | RS 1M | RS 1D | Breadth | 20DMA | Vol | Score |",
            "|------|------|-------|-------|---------|-------|-----|-------|",
        ]
        for b in themes:
            label = _SIGNAL_LABEL.get(b.signal, b.signal)
            lines.append(
                f"| {b.theme_name} | {label} "
                f"| {b.avg_rs_spy_1m:+.1f}% | {b.avg_rs_spy_1d:+.1f}% "
                f"| {b.breadth_rs*100:.0f}% | {b.breadth_20dma*100:.0f}% "
                f"| {b.avg_volume_ratio:.1f}x | {b.breadth_score:.0f} |"
            )
        return "\n".join(lines)

    def _section_all_tickers(self, all_metrics: list, ticker_to_theme: dict) -> str:
        lines = [
            "| 标的 | 叙事 | RS 1M | RS 1D | 1M | 3M | Vol | 20D |",
            "|------|------|-------|-------|----|----|-----|-----|",
        ]
        for m in all_metrics:
            theme = ticker_to_theme.get(m.ticker, "—")
            ma    = "↑" if m.above_20dma else "↓"
            lines.append(
                f"| {m.ticker} | {theme} "
                f"| {m.rs_vs_spy_1m:+.1f}% | {m.rs_vs_spy_1d:+.1f}% "
                f"| {m.ret_1m:+.1f}% | {m.ret_3m:+.1f}% "
                f"| {m.volume_ratio_20d:.1f}x | {ma} |"
            )
        return "\n".join(lines)

    # ── Chart ─────────────────────────────────────────────────────────────────

    def _themes_chart(self, themes: list) -> ChartSpec:
        labels  = [b.theme_name[:14] for b in themes]  # truncate for readability
        data    = [round(b.avg_rs_spy_1m, 2) for b in themes]
        return ChartSpec(
            chart_type="bar",
            labels=labels,
            datasets=[ChartDataset(label="RS vs SPY 1M (%)", data=data)],
            title="主题 RS vs SPY 1M",
            y_suffix="%",
            height_px=220,
        )
