#!/usr/bin/env python3
"""Smoke test for the unified reporting layer.

Run with any agent venv python:
  .venv/bin/python ../../shared/reporting/smoke_test.py

Writes test output to /tmp/reporting_smoke_test/ and prints a summary.
No external API calls, no Telegram sends.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Make shared importable
_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent.parent
sys.path.insert(0, str(_WORKSPACE))

# Override reports dir so we don't pollute real reports/
_TMP = Path(tempfile.mkdtemp(prefix="reporting_smoke_"))
os.environ["REPORTS_BASE_DIR"] = str(_TMP)
os.environ["REPORTS_BASE_URL"] = f"file://{_TMP}"

from shared.reporting.base_report import ChartDataset, ChartSpec, ReportData
from shared.reporting.html_renderer import render_daily_index, render_html
from shared.reporting.index_builder import build_daily_index, build_nav_index
from shared.reporting.md_writer import parse_frontmatter, write_report
from shared.reporting.retention import run_retention
from shared.reporting.telegram_summary import build_brief

DATE = "2026-05-14"
AGENTS = [
    "finance_bot",
    "ai_narrative_rotation_radar",
    "polymarket_intelligence",
    "web3_monitor",
]

_SAMPLE_CONTENT = {
    "finance_bot": {
        "summary": "美股小幅下跌，组合今日 -0.8%，HIMS 是主要拖累项，AI 软件板块分化。",
        "risk_level": "medium",
        "opp_level": "low",
        "sections": [
            (
                "Portfolio Performance",
                "| 账户 | 市值 | 日收益 | 累计收益 |\n"
                "|------|------|--------|----------|\n"
                "| IBKR | $120K | -0.9% | +32% |\n"
                "| FUTU | $45K | -0.4% | +18% |",
                False,
                ChartSpec(
                    chart_type="bar",
                    labels=["IBKR", "FUTU", "moomoo"],
                    datasets=[ChartDataset("日收益%", [-0.9, -0.4, 0.1])],
                    title="账户日收益",
                    y_suffix="%",
                    height_px=180,
                ),
            ),
            (
                "Top Movers",
                "**拖累项**：HIMS -4.2%、SOFI -2.1%\n\n**贡献项**：NVDA +1.8%、META +0.9%",
                False,
                None,
            ),
            (
                "Risk Signals",
                "- VIX 升至 18.4（+12%）\n- 美债 10Y 收益率 4.52%",
                True,
                None,
            ),
        ],
    },
    "ai_narrative_rotation_radar": {
        "summary": "AI 基础设施叙事强势，Software 叙事分化，LEAPS 候选 NVDA / PLTR 评分 >85。",
        "risk_level": "low",
        "opp_level": "medium",
        "sections": [
            (
                "Leading Themes",
                "| 叙事 | 信号 | RS 1M | Breadth |\n"
                "|------|------|-------|---------|\n"
                "| AI Infrastructure | STRONG | +8.2% | 78% |\n"
                "| Robotics | BROADENING | +5.1% | 62% |",
                False,
                None,
            ),
            (
                "LEAPS Candidates",
                "- **NVDA** Score 91/100 | AI Infrastructure | LEAPS available\n"
                "- **PLTR** Score 86/100 | AI Software | LEAPS available",
                False,
                None,
            ),
        ],
    },
    "polymarket_intelligence": {
        "summary": "美联储 6 月暂停加息概率升至 74%，赔率较昨日 +9ppt，成交量显著放大。",
        "risk_level": "low",
        "opp_level": "medium",
        "sections": [
            (
                "Today's Top Signals",
                "| 市场 | 信号类型 | 概率变化 | 评分 |\n"
                "|------|---------|---------|------|\n"
                "| Fed June pause | Rapid reprice | 65% → 74% | 88/100 |\n"
                "| Trump tariff extension | Liquidity spike | — | 72/100 |",
                False,
                None,
            ),
        ],
    },
    "web3_monitor": {
        "summary": "Base 链 DEX 成交量异动 +340%，跨信号评分 82/100，Polymarket 联动信号出现。",
        "risk_level": "low",
        "opp_level": "low",
        "sections": [
            (
                "DEX Anomalies",
                "| 资产 | 链 | 价格 1h | 成交量 1h | 评分 |\n"
                "|------|------|--------|----------|------|\n"
                "| TOKEN/USDC | Base | +12.4% | $2.1M | 82/100 |",
                False,
                None,
            ),
        ],
    },
}


def build_sample_report(agent: str) -> ReportData:
    cfg = _SAMPLE_CONTENT[agent]
    r = ReportData.for_agent(
        agent=agent,
        date=DATE,
        summary=cfg["summary"],
        risk_level=cfg["risk_level"],
        opportunity_level=cfg["opp_level"],
    )
    for title, content, collapsed, chart in cfg["sections"]:
        r.add_section(title, content, collapsed=collapsed, chart=chart)
    return r


def main() -> None:
    print(f"Smoke test output: {_TMP}\n")
    reports = []

    for agent in AGENTS:
        print(f"  [{agent}]")

        r = build_sample_report(agent)

        # 1. Write Markdown
        md_path = write_report(r)
        assert md_path.exists(), f"MD not written: {md_path}"
        print(f"    ✓ MD  → {md_path.relative_to(_TMP)}")

        # 2. Parse frontmatter back
        fm = parse_frontmatter(md_path)
        assert fm is not None, "Frontmatter parse failed"
        assert fm["agent"] == agent
        assert fm["date"] == DATE
        print(f"    ✓ frontmatter OK  (risk={fm['risk_level']})")

        # 3. Render HTML
        html_path = render_html(r, nav_dates=[DATE])
        assert html_path.exists(), f"HTML not written: {html_path}"
        content = html_path.read_text()
        assert "Chart.js" in content
        assert agent in content           # agent name appears in title/nav
        assert html_path.stat().st_size > 5_000, "HTML suspiciously small"
        print(f"    ✓ HTML → {html_path.relative_to(_TMP)}")

        reports.append(r)

    # 4. Build daily index
    print(f"\n  [daily index]")
    idx = build_daily_index(DATE, nav_dates=[DATE])
    assert idx is not None and idx.exists()
    print(f"    ✓ {idx.relative_to(_TMP)}")

    # 5. Build nav index
    nav = build_nav_index()
    assert nav.exists()
    print(f"    ✓ nav index: {nav.relative_to(_TMP)}")

    # 6. Build Telegram brief
    print(f"\n  [telegram brief]")
    brief = build_brief(DATE, reports)
    assert DATE in brief
    assert len(brief) < 1200, f"Brief too long: {len(brief)} chars"
    print(f"    ✓ Brief ({len(brief)} chars):")
    print()
    for line in brief.split("\n"):
        print(f"      {line}")

    # 7. Retention (nothing to purge yet — just verify it runs)
    print(f"\n  [retention]")
    run_retention({"full_html_days": 365})
    print(f"    ✓ retention run OK (no files purged at 365-day threshold)")

    print(f"\n✅ All checks passed — output in {_TMP}")


if __name__ == "__main__":
    main()
