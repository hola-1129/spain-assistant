#!/usr/bin/env python3
"""Integration test: Web3ReportBuilder → shared reporting pipeline.

Run from web3_monitor/scripts/:
  python reporting/test_integration.py

Uses synthetic signal data — no live API calls, no Telegram sends.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]   # web3_monitor/scripts/
_AGENT_ROOT   = _SCRIPTS_ROOT.parent                  # web3_monitor/
_WS_ROOT      = _AGENT_ROOT.parents[1]                # ai_workspace/
sys.path.insert(0, str(_WS_ROOT))
sys.path.insert(0, str(_SCRIPTS_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="web3_report_test_"))
os.environ["REPORTS_BASE_DIR"] = str(_TMP)
os.environ["REPORTS_BASE_URL"] = f"file://{_TMP}"

DATE_STR = "2026-05-14"


def _make_data() -> dict:
    signals = [
        {
            "source": "cross_signal",
            "symbol": "WLD",
            "chain": "ethereum",
            "signal_type": "cross_dex_polymarket",
            "score": 88.0,
            "reason": "DEX volume surge coincides with Polymarket AI odds move",
            "volume": 12_500_000.0,
            "liquidity": 8_000_000.0,
            "timestamp": f"{DATE_STR}T22:15:00Z",
        },
        {
            "source": "coingecko",
            "symbol": "ETH",
            "chain": None,
            "signal_type": "market_mover",
            "score": 75.0,
            "reason": "ETH volume +120% on ETF approval rumour",
            "volume": 35_000_000_000.0,
            "liquidity": None,
            "timestamp": f"{DATE_STR}T18:00:00Z",
        },
        {
            "source": "dexscreener",
            "symbol": "PEPE",
            "chain": "ethereum",
            "signal_type": "volume_anomaly",
            "score": 62.0,
            "reason": "1h volume +85% vs 24h baseline",
            "volume": 4_200_000.0,
            "liquidity": 950_000.0,
            "timestamp": f"{DATE_STR}T20:30:00Z",
        },
        {
            "source": "geckoterminal",
            "symbol": "NEWPOOL/USDC",
            "chain": "base",
            "signal_type": "new_pool",
            "score": 42.0,
            "reason": "New pool with $1.2M liquidity in 30min",
            "volume": 800_000.0,
            "liquidity": 1_200_000.0,
            "timestamp": f"{DATE_STR}T21:00:00Z",
        },
        {
            "source": "coingecko",
            "symbol": "BTC",
            "chain": None,
            "signal_type": "market_mover",
            "score": 58.0,
            "reason": "BTC -2.5% on macro data",
            "volume": 28_000_000_000.0,
            "liquidity": None,
            "timestamp": f"{DATE_STR}T16:00:00Z",
        },
    ]
    by_source = {
        "cross_signal":  {"count": 1, "max_score": 88.0, "avg_score": 88.0},
        "coingecko":     {"count": 2, "max_score": 75.0, "avg_score": 66.5},
        "dexscreener":   {"count": 1, "max_score": 62.0, "avg_score": 62.0},
        "geckoterminal": {"count": 1, "max_score": 42.0, "avg_score": 42.0},
    }
    cross_signals = [s for s in signals if s["source"] == "cross_signal"]
    top_signals   = sorted(signals, key=lambda s: s["score"] or 0, reverse=True)[:10]
    return {
        "date": DATE_STR,
        "total_raw": 34,
        "signals": signals,
        "by_source": by_source,
        "cross_signals": cross_signals,
        "top_signals": top_signals,
    }


def main():
    print(f"Output: {_TMP}\n")

    data = _make_data()

    # 1. Build report
    from reporting.report_builder import Web3ReportBuilder
    report = Web3ReportBuilder().build(data)

    print(f"meta.agent:             {report.meta.agent}")
    print(f"meta.date:              {report.meta.date}")
    print(f"meta.summary:           {report.meta.summary}")
    print(f"meta.risk_level:        {report.meta.risk_level}")
    print(f"meta.opportunity_level: {report.meta.opportunity_level}")
    print(f"sections:               {[s.title for s in report.sections]}")
    print()

    assert report.meta.agent == "web3_monitor"
    assert report.meta.opportunity_level in ("medium", "high")  # score 88 + cross signal

    # 2. Write Markdown
    from shared.reporting import write_report
    md_path = write_report(report)
    assert md_path.exists()
    content_md = md_path.read_text()
    assert "WLD" in content_md
    print(f"✓ MD   ({md_path.stat().st_size} bytes)  →  {md_path.relative_to(_TMP)}")

    from shared.reporting.md_writer import parse_frontmatter
    fm = parse_frontmatter(md_path)
    assert fm["agent"] == "web3_monitor"
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
    assert "Cross Signal" in content or "cross" in content.lower()
    print(f"✓ HTML ({sz} bytes)  →  {html_path.relative_to(_TMP)}")

    # 4. Daily index
    from shared.reporting.index_builder import build_daily_index, build_nav_index
    idx = build_daily_index(DATE_STR, nav_dates=[DATE_STR])
    assert idx and idx.exists()
    print(f"✓ index  → {idx.relative_to(_TMP)}")

    # 5. Telegram brief
    from shared.reporting import build_brief
    brief = build_brief(DATE_STR, [report])
    assert "web3" in brief.lower() or "monitor" in brief.lower()
    assert DATE_STR in brief
    assert len(brief) < 1000
    print(f"✓ brief  ({len(brief)} chars)")
    print()
    for line in brief.split("\n"):
        print(f"  {line}")

    print(f"\n✅ Integration test passed — {_TMP}")


if __name__ == "__main__":
    main()
