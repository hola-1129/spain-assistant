#!/usr/bin/env python3
"""Integration test: FinanceBotReportBuilder → shared reporting pipeline.

Run from agent root:
  .venv/bin/python reporting/test_integration.py

Uses synthetic PositionResult objects (no live API calls, no Telegram sends).
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Make shared importable
_AGENT_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT = _AGENT_ROOT.parents[1]
sys.path.insert(0, str(_WS_ROOT))
sys.path.insert(0, str(_AGENT_ROOT))  # so 'reporting' package is importable

# Override reports dir
_TMP = Path(tempfile.mkdtemp(prefix="fb_report_test_"))
os.environ["REPORTS_BASE_DIR"] = str(_TMP)
os.environ["REPORTS_BASE_URL"] = f"file://{_TMP}"

# ── Synthetic PositionResult (mirrors real dataclass) ─────────────────────────

@dataclass
class PositionResult:
    symbol: str
    label: str
    shares: int
    account: str
    current_price: float
    prev_close: float
    market_value: float
    cost_total: Optional[float]
    unrealized_pnl: Optional[float]
    pnl_pct: Optional[float]
    nav_pct: float
    day_change_pct: float
    rule_5a_done: bool
    rule_1b_exception: bool
    thesis: Optional[str]
    risk_flags: List[str] = field(default_factory=list)


SAMPLE_RESULTS = [
    PositionResult("NVDA", "NVDA", 50, "IBKR", 950.0, 935.0, 47500.0, 30000.0, 17500.0, 58.3, 0.029, 1.6, False, False, "AI infra picks"),
    PositionResult("HIMS", "HIMS", 800, "IBKR", 38.5, 40.2, 30800.0, 20000.0, 10800.0, 54.0, 0.019, -4.2, False, False, "GLP-1 play", ["今日跌幅超4%"]),
    PositionResult("PLTR", "PLTR", 300, "FUTU", 85.0, 84.0, 25500.0, 15000.0, 10500.0, 70.0, 0.016, 1.2, True, False, "AI Gov't contracts"),
    PositionResult("META", "META", 25, "IBKR", 520.0, 515.0, 13000.0, 9000.0, 4000.0, 44.4, 0.008, 1.0, False, False, None),
    PositionResult("RKLB", "RKLB", 500, "moomoo", 18.5, 19.2, 9250.0, 7000.0, 2250.0, 32.1, 0.006, -3.6, False, False, "Space theme"),
]

NAV_BASE = 163341.0
DATE_STR = "2026-05-14"


def main():
    print(f"Output: {_TMP}\n")

    # 1. Build report
    from reporting.report_builder import FinanceBotReportBuilder
    builder = FinanceBotReportBuilder()
    report = builder.build(
        results=SAMPLE_RESULTS,
        nav_base=NAV_BASE,
        date_str=DATE_STR,
        advice_text="🧠 *收盘分析*  ⚙️ Claude\nHIMS 今日跌幅-4.2%，已触发风险提示。NVDA +1.6%，持续强势。建议关注 HIMS 止损位置。",
        news_text="📰 *今日要闻*  ⚙️ Qwen\nHIMS — GLP-1 市场竞争加剧，新进入者获FDA批准\nNVDA — 数据中心需求持续超预期",
    )

    print(f"meta.agent:            {report.meta.agent}")
    print(f"meta.date:             {report.meta.date}")
    print(f"meta.summary:          {report.meta.summary}")
    print(f"meta.risk_level:       {report.meta.risk_level}")
    print(f"meta.opportunity_level:{report.meta.opportunity_level}")
    print(f"sections:              {[s.title for s in report.sections]}")
    print()

    # 2. Write Markdown
    from shared.reporting import write_report
    md_path = write_report(report)
    assert md_path.exists()
    print(f"✓ MD  ({md_path.stat().st_size} bytes)  →  {md_path.relative_to(_TMP)}")

    # Verify frontmatter
    from shared.reporting.md_writer import parse_frontmatter
    fm = parse_frontmatter(md_path)
    assert fm and fm["agent"] == "finance_bot"
    assert fm["risk_level"] == "medium"   # HIMS flag → medium
    print(f"  frontmatter: risk={fm['risk_level']} opp={fm['opportunity_level']}")

    # 3. Render HTML
    from shared.reporting import render_html
    html_path = render_html(report, nav_dates=[DATE_STR])
    assert html_path.exists()
    content = html_path.read_text()
    assert "finance_bot" in content.lower()
    assert "Chart.js" in content
    assert "Portfolio Performance" in content
    assert "Top Movers" in content
    sz = html_path.stat().st_size
    assert sz > 10_000, f"HTML too small: {sz}"
    print(f"✓ HTML ({sz} bytes)  →  {html_path.relative_to(_TMP)}")

    # Verify chart data is embedded
    assert "chart-portfolio-performance" in content or "ctx" in content
    print(f"  chart: embedded")

    # 4. Build daily index
    from shared.reporting.index_builder import build_daily_index, build_nav_index
    idx = build_daily_index(DATE_STR, nav_dates=[DATE_STR])
    assert idx and idx.exists()
    print(f"✓ index  → {idx.relative_to(_TMP)}")

    nav = build_nav_index()
    assert nav.exists()
    print(f"✓ nav    → {nav.relative_to(_TMP)}")

    # 5. Build Telegram brief
    from shared.reporting import build_brief
    brief = build_brief(DATE_STR, [report])
    assert "finance_bot" in brief or "finance\\_bot" in brief
    assert DATE_STR in brief
    assert len(brief) < 1000
    print(f"✓ brief  ({len(brief)} chars)")
    print()
    for line in brief.split("\n"):
        print(f"  {line}")

    # 6. Retention smoke
    from shared.reporting import run_retention
    run_retention({"full_html_days": 365})
    print(f"\n✓ retention: OK")

    print(f"\n✅ Integration test passed — {_TMP}")


if __name__ == "__main__":
    main()
