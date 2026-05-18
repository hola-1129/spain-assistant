#!/usr/bin/env python3
"""Integration test: PolymarketReportBuilder → shared reporting pipeline.

Run from agent root:
  python reporting/test_integration.py

Uses synthetic signal data — no live API calls, no Telegram sends.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT    = _AGENT_ROOT.parents[1]
sys.path.insert(0, str(_WS_ROOT))
sys.path.insert(0, str(_AGENT_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="poly_report_test_"))
os.environ["REPORTS_BASE_DIR"] = str(_TMP)
os.environ["REPORTS_BASE_URL"] = f"file://{_TMP}"

DATE_STR = "2026-05-14"


def _make_data() -> dict:
    signals = [
        {
            "signal_type": "rapid_reprice_5m",
            "score": 92,
            "market_id": "market-001",
            "question": "Will BTC exceed $100k by June 2026?",
            "event_title": "Crypto",
            "category": "crypto",
            "url": "https://polymarket.com/event/btc-100k",
            "probability_before": 0.35,
            "probability_after": 0.52,
            "probability_delta": 0.17,
            "window_minutes": 5,
            "liquidity_delta": None,
            "reason": "Sharp 5-min move on BTC ETF approval news",
        },
        {
            "signal_type": "rapid_reprice_15m",
            "score": 78,
            "market_id": "market-002",
            "question": "Will Fed cut rates in June 2026?",
            "event_title": "Macro",
            "category": "macro",
            "url": "https://polymarket.com/event/fed-june",
            "probability_before": 0.60,
            "probability_after": 0.44,
            "probability_delta": -0.16,
            "window_minutes": 15,
            "liquidity_delta": None,
            "reason": "CPI beat expectations; rate-cut odds drop",
        },
        {
            "signal_type": "liquidity_spike",
            "score": 65,
            "market_id": "market-003",
            "question": "Will ETH ETF be approved in 2026?",
            "event_title": "Crypto ETF",
            "category": "crypto",
            "url": "https://polymarket.com/event/eth-etf",
            "probability_before": None,
            "probability_after": None,
            "probability_delta": None,
            "window_minutes": None,
            "liquidity_delta": 250_000,
            "reason": "Sudden liquidity injection after SEC filing",
        },
        {
            "signal_type": "rapid_reprice_60m",
            "score": 45,
            "market_id": "market-004",
            "question": "2026 US recession?",
            "event_title": "Macro",
            "category": "macro",
            "url": None,
            "probability_before": 0.20,
            "probability_after": 0.28,
            "probability_delta": 0.08,
            "window_minutes": 60,
            "liquidity_delta": None,
            "reason": "Jobs data miss",
        },
    ]
    by_type = {
        "rapid_reprice_5m":  {"count": 1, "max_score": 92},
        "rapid_reprice_15m": {"count": 1, "max_score": 78},
        "rapid_reprice_60m": {"count": 1, "max_score": 45},
        "liquidity_spike":   {"count": 1, "max_score": 65},
    }
    by_category = {
        "crypto": {"count": 2, "max_score": 92},
        "macro":  {"count": 2, "max_score": 78},
    }
    return {
        "date": DATE_STR,
        "total_raw": 18,
        "signals": signals,
        "by_type": by_type,
        "by_category": by_category,
    }


def main():
    print(f"Output: {_TMP}\n")

    data = _make_data()

    # 1. Build report
    from reporting.report_builder import PolymarketReportBuilder
    report = PolymarketReportBuilder().build(data, min_score=40)

    print(f"meta.agent:             {report.meta.agent}")
    print(f"meta.date:              {report.meta.date}")
    print(f"meta.summary:           {report.meta.summary}")
    print(f"meta.risk_level:        {report.meta.risk_level}")
    print(f"meta.opportunity_level: {report.meta.opportunity_level}")
    print(f"sections:               {[s.title for s in report.sections]}")
    print()

    assert report.meta.agent == "polymarket_intelligence"
    assert report.meta.risk_level in ("medium", "high")  # 2 reprices + score 92
    assert report.meta.opportunity_level in ("low", "medium")

    # 2. Write Markdown
    from shared.reporting import write_report
    md_path = write_report(report)
    assert md_path.exists()
    content_md = md_path.read_text()
    assert "BTC" in content_md
    print(f"✓ MD   ({md_path.stat().st_size} bytes)  →  {md_path.relative_to(_TMP)}")

    from shared.reporting.md_writer import parse_frontmatter
    fm = parse_frontmatter(md_path)
    assert fm["agent"] == "polymarket_intelligence"
    assert fm["date"] == DATE_STR
    print(f"  frontmatter: risk={fm['risk_level']} opp={fm['opportunity_level']}")

    # 3. Render HTML
    from shared.reporting import render_html
    html_path = render_html(report, nav_dates=[DATE_STR])
    assert html_path.exists()
    content = html_path.read_text()
    sz = html_path.stat().st_size
    assert sz > 8_000, f"HTML too small: {sz}"
    assert "Chart.js" in content
    assert "Rapid Reprice" in content
    assert "Liquidity Spike" in content
    print(f"✓ HTML ({sz} bytes)  →  {html_path.relative_to(_TMP)}")

    # 4. Daily index
    from shared.reporting.index_builder import build_daily_index, build_nav_index
    idx = build_daily_index(DATE_STR, nav_dates=[DATE_STR])
    assert idx and idx.exists()
    print(f"✓ index  → {idx.relative_to(_TMP)}")

    # 5. Telegram brief
    from shared.reporting import build_brief
    brief = build_brief(DATE_STR, [report])
    assert "polymarket" in brief.lower() or "Polymarket" in brief
    assert DATE_STR in brief
    assert len(brief) < 1000
    print(f"✓ brief  ({len(brief)} chars)")
    print()
    for line in brief.split("\n"):
        print(f"  {line}")

    print(f"\n✅ Integration test passed — {_TMP}")


if __name__ == "__main__":
    main()
