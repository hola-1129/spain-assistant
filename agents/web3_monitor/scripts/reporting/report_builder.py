"""Build ReportData from aggregated web3 daily signals."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.reporting.base_report import (
    ChartDataset,
    ChartSpec,
    OpportunityLevel,
    ReportData,
    RiskLevel,
)

_SOURCE_LABEL = {
    "coingecko":    "📈 CoinGecko Market Mover",
    "cross_signal": "🔗 Cross Signal (DEX × Polymarket)",
    "dexscreener":  "📊 DEX Screener",
    "geckoterminal":"🦎 GeckoTerminal New Pool",
    "polymarket":   "🎯 Polymarket",
}


class Web3ReportBuilder:
    def build(self, data: dict[str, Any], min_score: float = 30.0) -> ReportData:
        """
        data: output of aggregator.fetch_daily_signals()
        min_score: minimum score to include in notable signals
        """
        date_str    = data["date"]
        signals     = data.get("signals", [])
        by_source   = data.get("by_source", {})
        cross       = data.get("cross_signals", [])
        top         = data.get("top_signals", [])

        coingecko   = [s for s in signals if s["source"] == "coingecko"]
        dex         = [s for s in signals if s["source"] == "dexscreener"]
        new_pools   = [s for s in signals if s["source"] == "geckoterminal"]

        report = ReportData.for_agent(
            agent="web3_monitor",
            date=date_str,
            summary=self._make_summary(top, by_source, cross),
            risk_level=self._risk_level(top, cross),
            opportunity_level=self._opp_level(top, cross),
        )

        # 1. Source breakdown overview
        report.add_section(
            "Signal Source Overview",
            self._section_overview(data),
            chart=self._source_chart(by_source),
        )

        # 2. Top signals across all sources
        if top:
            report.add_section(
                "Top Signals Today",
                self._section_top(top),
            )

        # 3. Cross signals (highest alpha — DEX + Polymarket combined)
        if cross:
            report.add_section(
                "Cross Signals (DEX × Polymarket)",
                self._section_cross(cross[:10]),
            )

        # 4. Market movers (CoinGecko)
        if coingecko:
            report.add_section(
                "Market Movers (CoinGecko)",
                self._section_movers(coingecko[:10]),
            )

        # 5. DEX anomalies
        if dex:
            report.add_section(
                "DEX Anomalies",
                self._section_dex(dex[:10]),
                collapsed=True,
            )

        # 6. New pools
        if new_pools:
            report.add_section(
                "New Pools (GeckoTerminal)",
                self._section_pools(new_pools[:8]),
                collapsed=True,
            )

        # 7. Full signal table
        report.add_section(
            "All Signals (Full Table)",
            self._section_all(signals[:60]),
            collapsed=True,
        )

        return report

    # ── Summary ───────────────────────────────────────────────────────────────

    def _make_summary(self, top, by_source, cross) -> str:
        parts = []
        if top:
            best = top[0]
            sym  = best.get("symbol") or "?"
            src  = _SOURCE_LABEL.get(best.get("source", ""), best.get("source", ""))
            sc   = best.get("score") or 0
            reason = (best.get("reason") or "")[:30]
            parts.append(f"最高信号：{sym}（{sc:.0f}分，{reason}）")
        if cross:
            parts.append(f"跨信号 {len(cross)} 条（DEX×Polymarket 联动）")
        total = sum(s.get("count", 0) for s in by_source.values())
        if not total:
            total = sum(1 for _ in by_source.values())
        sources = len(by_source)
        parts.append(f"共 {sources} 个数据源")
        return "，".join(parts) + "。" if parts else "今日无显著信号。"

    def _risk_level(self, top, cross) -> RiskLevel:
        max_sc = max((s.get("score") or 0 for s in top), default=0)
        # High-score negative signals → risk
        neg = [s for s in top if s.get("reason") and any(k in s["reason"] for k in ("-", "下跌", "跌", "空"))]
        if max_sc >= 80 and neg:
            return "high"
        if max_sc >= 60 and neg:
            return "medium"
        return "low"

    def _opp_level(self, top, cross) -> OpportunityLevel:
        max_sc = max((s.get("score") or 0 for s in top), default=0)
        if max_sc >= 80:
            return "high"
        if max_sc >= 60 or (cross and len(cross) >= 3):
            return "medium"
        if max_sc >= 40:
            return "low"
        return "none"

    # ── Sections ──────────────────────────────────────────────────────────────

    def _section_overview(self, data: dict) -> str:
        by_source = data.get("by_source", {})
        lines = [
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 原始信号总数 | {data.get('total_raw', 0):,} |",
            f"| 去重后信号数 | {len(data.get('signals', []))} |",
            "",
            "| 数据源 | 信号数 | 最高分 | 均分 |",
            "|--------|--------|--------|------|",
        ]
        for src, stats in sorted(by_source.items(), key=lambda x: x[1]["max_score"], reverse=True):
            label = _SOURCE_LABEL.get(src, src)
            lines.append(
                f"| {label} | {stats['count']} | {stats['max_score']:.0f} | {stats['avg_score']:.1f} |"
            )
        return "\n".join(lines)

    def _section_top(self, top: list) -> str:
        lines = [
            "| 标的 | 来源 | 链 | 类型 | 分数 | 原因 |",
            "|------|------|----|----|------|------|",
        ]
        for s in top:
            src    = _SOURCE_LABEL.get(s.get("source", ""), s.get("source", ""))[:18]
            chain  = s.get("chain") or "—"
            reason = (s.get("reason") or "")[:40]
            score  = s.get("score") or 0
            lines.append(
                f"| **{s.get('symbol', '?')}** | {src} | {chain} "
                f"| {s.get('signal_type', '?')} | {score:.0f} | {reason} |"
            )
        return "\n".join(lines)

    def _section_cross(self, cross: list) -> str:
        lines = [
            "| 标的 | 链 | 分数 | 原因 |",
            "|------|----|----|------|",
        ]
        for s in cross:
            chain  = s.get("chain") or "—"
            reason = (s.get("reason") or "")[:50]
            score  = s.get("score") or 0
            lines.append(f"| **{s.get('symbol', '?')}** | {chain} | {score:.0f} | {reason} |")
        return "\n".join(lines)

    def _section_movers(self, movers: list) -> str:
        lines = [
            "| 标的 | 分数 | 交易量 | 原因 |",
            "|------|------|--------|------|",
        ]
        for s in movers:
            vol    = f"${s['volume']:,.0f}" if s.get("volume") else "—"
            reason = (s.get("reason") or "")[:50]
            score  = s.get("score") or 0
            lines.append(f"| **{s.get('symbol', '?')}** | {score:.0f} | {vol} | {reason} |")
        return "\n".join(lines)

    def _section_dex(self, dex: list) -> str:
        lines = [
            "| 标的 | 链 | 流动性 | 分数 | 原因 |",
            "|------|----|----|------|------|",
        ]
        for s in dex:
            chain = s.get("chain") or "—"
            liq   = f"${s['liquidity']:,.0f}" if s.get("liquidity") else "—"
            reason = (s.get("reason") or "")[:40]
            score  = s.get("score") or 0
            lines.append(f"| {s.get('symbol', '?')} | {chain} | {liq} | {score:.0f} | {reason} |")
        return "\n".join(lines)

    def _section_pools(self, pools: list) -> str:
        lines = ["| 标的 | 链 | 流动性 | 交易量 |", "|------|----|----|------|"]
        for s in pools:
            chain = s.get("chain") or "—"
            liq   = f"${s['liquidity']:,.0f}" if s.get("liquidity") else "—"
            vol   = f"${s['volume']:,.0f}" if s.get("volume") else "—"
            lines.append(f"| {s.get('symbol', '?')} | {chain} | {liq} | {vol} |")
        return "\n".join(lines)

    def _section_all(self, signals: list) -> str:
        lines = [
            "| 标的 | 来源 | 链 | 类型 | 分数 | 原因 |",
            "|------|------|----|----|------|------|",
        ]
        for s in signals:
            src    = s.get("source", "?")[:12]
            chain  = s.get("chain") or "—"
            reason = (s.get("reason") or "")[:35]
            score  = s.get("score") or 0
            lines.append(
                f"| {s.get('symbol', '?')} | {src} | {chain} "
                f"| {s.get('signal_type', '?')} | {score:.0f} | {reason} |"
            )
        return "\n".join(lines)

    def _source_chart(self, by_source: dict) -> ChartSpec:
        items = sorted(by_source.items(), key=lambda x: x[1]["max_score"], reverse=True)[:6]
        return ChartSpec(
            chart_type="bar",
            labels=[_SOURCE_LABEL.get(s, s).split("(")[0].strip().replace("📈 ", "").replace("🔗 ", "").replace("📊 ", "").replace("🦎 ", "").replace("🎯 ", "") for s, _ in items],
            datasets=[ChartDataset("最高信号分", [v["max_score"] for _, v in items])],
            title="数据源最高信号分",
            height_px=180,
        )
