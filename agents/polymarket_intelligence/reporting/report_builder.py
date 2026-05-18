"""Build ReportData from aggregated polymarket daily signals."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

_SIGNAL_LABELS = {
    "rapid_reprice_5m":  "⚡ Rapid Reprice 5m",
    "rapid_reprice_15m": "⚡ Rapid Reprice 15m",
    "rapid_reprice_60m": "⚡ Rapid Reprice 60m",
    "liquidity_spike":   "💧 Liquidity Spike",
}


class PolymarketReportBuilder:
    def build(self, data: dict[str, Any], min_score: int = 40) -> ReportData:
        """
        data: output of aggregator.fetch_daily_signals()
        min_score: minimum score to include in report (default 40 — show all non-trivial)
        """
        date_str = data["date"]
        signals  = data.get("signals", [])
        by_type  = data.get("by_type", {})
        by_cat   = data.get("by_category", {})

        notable  = [s for s in signals if (s["score"] or 0) >= min_score]
        reprices = [s for s in notable if "rapid_reprice" in (s["signal_type"] or "")]
        spikes   = [s for s in notable if "liquidity_spike" in (s["signal_type"] or "")]

        report = ReportData.for_agent(
            agent="polymarket_intelligence",
            date=date_str,
            summary=self._make_summary(signals, by_type, reprices),
            risk_level=self._risk_level(reprices, signals),
            opportunity_level=self._opp_level(reprices),
        )

        # 1. Signal summary stats
        report.add_section(
            "Today's Signal Summary",
            self._section_summary(data),
            chart=self._type_chart(by_type),
        )

        # 2. High-score signals (top N notable)
        if notable:
            report.add_section(
                "Notable Signals (deduped)",
                self._section_notable(notable[:20]),
            )

        # 3. Rapid reprice events
        if reprices:
            report.add_section(
                "Rapid Reprice Events",
                self._section_reprices(reprices),
            )

        # 4. Liquidity spikes
        if spikes:
            report.add_section(
                "Liquidity Spike Events",
                self._section_spikes(spikes[:10]),
                collapsed=True,
            )

        # 5. Category breakdown
        if by_cat:
            report.add_section(
                "Signal Categories",
                self._section_categories(by_cat),
                collapsed=True,
            )

        # 6. Full deduped signal table
        report.add_section(
            "All Signals (Full Table)",
            self._section_all(signals[:50]),
            collapsed=True,
        )

        return report

    # ── Summary ───────────────────────────────────────────────────────────────

    def _make_summary(self, signals, by_type, reprices) -> str:
        n_deduped = len(signals)
        parts = [f"今日共 {n_deduped} 个去重信号"]
        if reprices:
            top_r = reprices[0]
            q = top_r.get("question") or top_r.get("event_title") or "—"
            pd = top_r.get("probability_delta")
            pd_str = f"Δ{pd:+.1%}" if pd is not None else ""
            parts.append(f"最高赔率变动：{q[:20]} {pd_str}（{top_r['score']} 分）")
        else:
            max_score = max((s.get("score") or 0 for s in signals), default=0)
            parts.append(f"最高信号评分 {max_score}")
        types_str = "、".join(f"{t}×{v['count']}" for t, v in by_type.items())
        if types_str:
            parts.append(types_str)
        return "，".join(parts) + "。"

    def _risk_level(self, reprices, signals) -> RiskLevel:
        max_score = max((s.get("score") or 0 for s in signals), default=0)
        if max_score >= 85 or (len(reprices) >= 3):
            return "high"
        if max_score >= 70 or reprices:
            return "medium"
        return "low"

    def _opp_level(self, reprices) -> OpportunityLevel:
        if len(reprices) >= 2:
            return "medium"
        if reprices:
            return "low"
        return "none"

    # ── Sections ──────────────────────────────────────────────────────────────

    def _section_summary(self, data: dict) -> str:
        by_type = data.get("by_type", {})
        lines = [
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 原始信号总数 | {data.get('total_raw', 0):,} |",
            f"| 去重后信号数 | {len(data.get('signals', []))} |",
        ]
        for t, stats in sorted(by_type.items(), key=lambda x: x[1]['count'], reverse=True):
            label = _SIGNAL_LABELS.get(t, t)
            lines.append(f"| {label} | {stats['count']} 条，最高 {stats['max_score']} 分 |")
        return "\n".join(lines)

    def _section_notable(self, signals: list) -> str:
        lines = [
            "| 市场 | 信号类型 | 分数 | 概率变化 | 原因 |",
            "|------|---------|------|---------|------|",
        ]
        for s in signals:
            q     = (s.get("question") or s.get("event_title") or "—")[:30]
            label = _SIGNAL_LABELS.get(s["signal_type"], s["signal_type"])
            score = s.get("score") or 0
            pd    = s.get("probability_delta")
            pb    = s.get("probability_before")
            pa    = s.get("probability_after")
            if pb is not None and pa is not None:
                prob_str = f"{pb:.0%} → {pa:.0%} (Δ{pd:+.1%})" if pd else f"{pb:.0%} → {pa:.0%}"
            elif pd is not None:
                prob_str = f"Δ{pd:+.1%}"
            else:
                prob_str = "—"
            reason = (s.get("reason") or "")[:40]
            lines.append(f"| {q} | {label} | {score} | {prob_str} | {reason} |")
        return "\n".join(lines)

    def _section_reprices(self, reprices: list) -> str:
        lines = [
            "| 市场 | 窗口 | 概率变化 | 分数 | 链接 |",
            "|------|------|---------|------|------|",
        ]
        for s in reprices:
            q      = (s.get("question") or s.get("event_title") or "—")[:35]
            window = f"{s.get('window_minutes')}m" if s.get("window_minutes") else "—"
            pb     = s.get("probability_before")
            pa     = s.get("probability_after")
            pd     = s.get("probability_delta")
            prob   = f"{pb:.0%}→{pa:.0%} Δ{pd:+.1%}" if pb and pa and pd else "—"
            score  = s.get("score") or 0
            url    = s.get("url") or s.get("market_url") or ""
            link   = f"[→]({url})" if url else "—"
            lines.append(f"| {q} | {window} | {prob} | {score} | {link} |")
        return "\n".join(lines)

    def _section_spikes(self, spikes: list) -> str:
        lines = [
            "| 市场 | 流动性增量 | 分数 |",
            "|------|-----------|------|",
        ]
        for s in spikes:
            q   = (s.get("question") or s.get("event_title") or "—")[:40]
            ld  = s.get("liquidity_delta")
            liq = f"+${ld:,.0f}" if ld else "—"
            lines.append(f"| {q} | {liq} | {s.get('score') or 0} |")
        return "\n".join(lines)

    def _section_categories(self, by_cat: dict) -> str:
        lines = ["| 分类 | 信号数 | 最高分 |", "|------|--------|--------|"]
        for cat, stats in sorted(by_cat.items(), key=lambda x: x[1]["count"], reverse=True):
            lines.append(f"| {cat} | {stats['count']} | {stats['max_score']} |")
        return "\n".join(lines)

    def _section_all(self, signals: list) -> str:
        lines = ["| 市场 | 类型 | 分数 | 概率Δ | 流动性Δ |", "|------|------|------|------|--------|"]
        for s in signals:
            q   = (s.get("question") or s.get("event_title") or s.get("market_id") or "—")[:30]
            t   = _SIGNAL_LABELS.get(s["signal_type"], s["signal_type"])
            pd  = s.get("probability_delta")
            ld  = s.get("liquidity_delta")
            lines.append(
                f"| {q} | {t} | {s.get('score') or 0} "
                f"| {f'{pd:+.1%}' if pd else '—'} "
                f"| {f'+${ld:,.0f}' if ld else '—'} |"
            )
        return "\n".join(lines)

    def _type_chart(self, by_type: dict) -> ChartSpec:
        items = sorted(by_type.items(), key=lambda x: x[1]["count"], reverse=True)[:6]
        return ChartSpec(
            chart_type="bar",
            labels=[_SIGNAL_LABELS.get(t, t).replace("⚡ ", "").replace("💧 ", "") for t, _ in items],
            datasets=[ChartDataset("信号数量", [v["count"] for _, v in items])],
            title="今日信号类型分布",
            height_px=180,
        )
