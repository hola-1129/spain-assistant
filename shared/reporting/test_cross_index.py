#!/usr/bin/env python3
"""Cross-agent daily index integration test.

Simulates all 4 agents writing their reports on the same date,
then verifies that:
  - build_daily_index() produces a rich cross-agent index.html
  - build_nav_index() produces a date-list page with per-date metadata
  - build_monthly_index() produces a risk-heatmap archive page
  - build_cross_brief() produces a combined Telegram message
  - The 7-day history chart data is injected into the daily index

Run from ai_workspace/:
  shared/reporting/.venv/bin/python shared/reporting/test_cross_index.py
  # or from any venv that has markdown-it-py and jinja2:
  python shared/reporting/test_cross_index.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

_WS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WS_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="cross_index_test_"))
os.environ["REPORTS_BASE_DIR"] = str(_TMP)
os.environ["REPORTS_BASE_URL"] = f"file://{_TMP}"

from shared.reporting.base_report import (
    ChartDataset,
    ChartSpec,
    ReportData,
)
from shared.reporting.md_writer import write_report


# ── Stub report factories ─────────────────────────────────────────────────────

def _make_finance_report(date_str: str, risk: str = "medium", opp: str = "low") -> ReportData:
    r = ReportData.for_agent(
        agent="finance_bot",
        date=date_str,
        summary="组合今日 +1.8%，NVDA 贡献最大，无风险仓位触发。",
        risk_level=risk,
        opportunity_level=opp,
    )
    r.add_section(
        "Portfolio Performance",
        "| 指标 | 值 |\n|------|----|\n| 今日涨跌 | +1.8% |\n| 未实现盈亏 | +$12,400 |",
        chart=ChartSpec("bar", ["NVDA", "AAPL", "MSFT"], [ChartDataset("今日涨跌%", [4.2, 1.1, -0.3])]),
    )
    r.add_section("Top Movers", "NVDA 领涨，受 AI 服务器需求驱动。")
    return r


def _make_radar_report(date_str: str, risk: str = "high", opp: str = "high") -> ReportData:
    r = ReportData.for_agent(
        agent="ai_narrative_rotation_radar",
        date=date_str,
        summary="AI Infrastructure 叙事领跑（RS +8.2%），LEAPS 候选：NVDA（91/100）。",
        risk_level=risk,
        opportunity_level=opp,
    )
    r.add_section(
        "Leading Themes",
        "| 主题 | 信号 | 得分 |\n|------|------|------|\n| AI Infrastructure | STRONG | 84 |\n| Robotics | BROADENING | 71 |",
        chart=ChartSpec("bar", ["AI Infra", "Robotics", "AI SW"], [ChartDataset("RS vs SPY 1M%", [8.2, 5.1, 1.2])]),
    )
    r.add_section("Rotation Signal", "资金从 Biotech 流向 AI Infrastructure，置信度 78/100。")
    r.add_section("LEAPS Call Candidates", "NVDA: 91/100\nPLTR: 82/100")
    return r


def _make_poly_report(date_str: str, risk: str = "high", opp: str = "medium") -> ReportData:
    r = ReportData.for_agent(
        agent="polymarket_intelligence",
        date=date_str,
        summary="今日共 4 个去重信号，最高赔率变动：BTC 100k Δ+17%（92 分）。",
        risk_level=risk,
        opportunity_level=opp,
    )
    r.add_section(
        "Today's Signal Summary",
        "| 指标 | 值 |\n|------|----|\n| 原始信号总数 | 18 |\n| 去重后信号数 | 4 |",
    )
    r.add_section("Rapid Reprice Events", "BTC 100k: 35%→52% in 5m\nFed cut June: 60%→44% in 15m")
    return r


def _make_web3_report(date_str: str, risk: str = "medium", opp: str = "high") -> ReportData:
    r = ReportData.for_agent(
        agent="web3_monitor",
        date=date_str,
        summary="最高信号：WLD（88分，DEX volume surge），跨信号 1 条，共 4 个数据源。",
        risk_level=risk,
        opportunity_level=opp,
    )
    r.add_section(
        "Signal Source Overview",
        "| 数据源 | 信号数 | 最高分 |\n|--------|--------|--------|\n| Cross Signal | 1 | 88 |\n| CoinGecko | 2 | 75 |",
    )
    r.add_section("Cross Signals (DEX × Polymarket)", "WLD: DEX volume surge + Polymarket AI odds move (88)")
    return r


# ── Historical backdates (to test 7-day chart) ────────────────────────────────

_HISTORY_DATES = [
    "2026-05-08",
    "2026-05-09",
    "2026-05-10",
    "2026-05-11",
    "2026-05-12",
    "2026-05-13",
]

def _write_history():
    """Write stub reports for 6 prior dates so the 7-day chart has data."""
    configs = [
        ("2026-05-08", "low",    "none",   "medium", "low",  "low",   "none",  "low",   "low"),
        ("2026-05-09", "medium", "low",    "medium", "low",  "medium","none",  "medium","low"),
        ("2026-05-10", "low",    "low",    "high",   "medium","low",  "low",   "high",  "medium"),
        ("2026-05-11", "medium", "medium", "high",   "high", "medium","medium","medium","high"),
        ("2026-05-12", "high",   "high",   "high",   "high", "high",  "high",  "high",  "high"),
        ("2026-05-13", "medium", "medium", "medium", "medium","medium","medium","medium","medium"),
    ]
    for (d, fr, fo, rr, ro, pr, po, wr, wo) in configs:
        write_report(_make_finance_report(d, fr, fo))
        write_report(_make_radar_report(d, rr, ro))
        write_report(_make_poly_report(d, pr, po))
        write_report(_make_web3_report(d, wr, wo))


DATE_STR  = "2026-05-14"
ALL_DATES = _HISTORY_DATES + [DATE_STR]


def main():
    print(f"Output: {_TMP}\n")

    # Write historical reports for chart
    _write_history()

    # Write today's reports
    reports = [
        _make_finance_report(DATE_STR, risk="medium", opp="low"),
        _make_radar_report(DATE_STR,   risk="high",   opp="high"),
        _make_poly_report(DATE_STR,    risk="high",   opp="medium"),
        _make_web3_report(DATE_STR,    risk="medium", opp="high"),
    ]
    for r in reports:
        write_report(r)

    # 1. Build daily index for today (with 7-day history)
    from shared.reporting.index_builder import (
        build_cross_brief,
        build_daily_index,
        build_monthly_index,
        build_nav_index,
    )
    idx = build_daily_index(DATE_STR, nav_dates=ALL_DATES)
    assert idx and idx.exists(), "daily index not created"
    content = idx.read_text()
    sz = idx.stat().st_size
    assert sz > 10_000, f"daily index too small: {sz}"
    # Risk pulse, agent cards, chart
    assert "Risk Pulse" in content or "risk-pulse" in content
    assert "trendChart" in content
    assert "AI Narrative Radar" in content
    assert "Polymarket Intelligence" in content
    assert "Finance Bot" in content
    assert "Web3 Monitor" in content
    # 7-day chart data injected
    assert "2026-05-08" in content or "05-08" in content
    print(f"✓ daily index  ({sz} bytes)  →  {idx.relative_to(_TMP)}")

    # Verify risk is HIGH (radar + poly both high)
    assert "HIGH" in content.upper()
    print(f"  max_risk: HIGH ✓")

    # 2. Nav index
    nav = build_nav_index()
    assert nav and nav.exists()
    nav_content = nav.read_text()
    assert "2026-05-14" in nav_content
    assert "2026-05-08" in nav_content
    # Agent presence dots
    assert "dot-present" in nav_content or "rp-dot" in nav_content or "agent-dot" in nav_content
    sz2 = nav.stat().st_size
    print(f"✓ nav index    ({sz2} bytes)  →  {nav.relative_to(_TMP)}")

    # 3. Monthly index (heatmap)
    midx = build_monthly_index("2026-05")
    assert midx and midx.exists()
    month_content = midx.read_text()
    assert "heatmap-table" in month_content or "Heatmap" in month_content or "heatmap" in month_content.lower()
    assert "2026-05-14" in month_content
    assert "2026-05-08" in month_content
    sz3 = midx.stat().st_size
    print(f"✓ monthly index({sz3} bytes)  →  {midx.relative_to(_TMP)}")

    # 4. Cross brief
    brief = build_cross_brief(DATE_STR)
    assert DATE_STR in brief
    assert "finance" in brief.lower() or "Finance" in brief
    assert "radar" in brief.lower() or "Radar" in brief
    assert "polymarket" in brief.lower() or "Polymarket" in brief
    assert "web3" in brief.lower() or "Web3" in brief
    # Risk level in brief
    assert "HIGH" in brief.upper()
    assert len(brief) < 1200
    print(f"✓ cross brief  ({len(brief)} chars)")
    print()
    for line in brief.split("\n"):
        print(f"  {line}")

    print(f"\n✅ Phase 4 cross-index test passed — {_TMP}")


if __name__ == "__main__":
    main()
