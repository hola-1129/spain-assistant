#!/usr/bin/env python3
"""One-shot real-data reporting test.

Reads from live SQLite DBs, builds reports, writes HTML, prints Telegram brief.
No Telegram send — dry run only.

Run from ai_workspace/agents/:
  polymarket_intelligence/.venv/bin/python run_real_data_test.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_AGENTS_ROOT = Path(__file__).resolve().parent
_WS_ROOT     = _AGENTS_ROOT.parent
sys.path.insert(0, str(_WS_ROOT))
sys.path.insert(0, str(_AGENTS_ROOT / "polymarket_intelligence"))

DATE_STR = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Write to a real-looking reports dir so HTML is inspectable
_REPORTS_DIR = _WS_ROOT / "reports"
os.environ["REPORTS_BASE_DIR"] = str(_REPORTS_DIR)
os.environ["REPORTS_BASE_URL"] = f"file://{_REPORTS_DIR}"

from shared.reporting import (
    build_cross_brief,
    build_daily_index,
    render_html,
    write_report,
)
from shared.reporting.index_builder import build_monthly_index, build_nav_index


def run_polymarket(date_str: str):
    print("\n── Polymarket Intelligence ──────────────────────────────────")
    from polymarket_intelligence.reporting.aggregator import fetch_daily_signals
    from polymarket_intelligence.reporting.report_builder import PolymarketReportBuilder

    db = _AGENTS_ROOT / "polymarket_intelligence/storage/intelligence.db"
    data = fetch_daily_signals(db, date_str)
    print(f"  raw={data['total_raw']}  deduped={len(data['signals'])}  types={list(data['by_type'].keys())}")

    report = PolymarketReportBuilder().build(data)
    print(f"  risk={report.meta.risk_level}  opp={report.meta.opportunity_level}")
    print(f"  summary: {report.meta.summary}")

    md  = write_report(report)
    html = render_html(report)
    print(f"  md  → {md.relative_to(_WS_ROOT)}  ({md.stat().st_size} bytes)")
    print(f"  html→ {html.relative_to(_WS_ROOT)}  ({html.stat().st_size} bytes)")
    return report


def run_web3(date_str: str):
    print("\n── Web3 Monitor ─────────────────────────────────────────────")
    # Web3 scripts dir must be on path
    sys.path.insert(0, str(_AGENTS_ROOT / "web3_monitor/scripts"))
    from reporting.aggregator import fetch_daily_signals
    from reporting.report_builder import Web3ReportBuilder

    db = _AGENTS_ROOT / "web3_monitor/data/web3_monitor.db"
    data = fetch_daily_signals(db, date_str)
    print(f"  raw={data['total_raw']}  deduped={len(data['signals'])}  sources={list(data['by_source'].keys())}")

    report = Web3ReportBuilder().build(data)
    print(f"  risk={report.meta.risk_level}  opp={report.meta.opportunity_level}")
    print(f"  summary: {report.meta.summary}")

    md  = write_report(report)
    html = render_html(report)
    print(f"  md  → {md.relative_to(_WS_ROOT)}  ({md.stat().st_size} bytes)")
    print(f"  html→ {html.relative_to(_WS_ROOT)}  ({html.stat().st_size} bytes)")
    return report


def main():
    print(f"Date: {DATE_STR}")
    print(f"Reports dir: {_REPORTS_DIR}")

    reports = []

    try:
        reports.append(run_polymarket(DATE_STR))
    except Exception as e:
        print(f"  ✗ polymarket failed: {e}")
        import traceback; traceback.print_exc()

    try:
        reports.append(run_web3(DATE_STR))
    except Exception as e:
        print(f"  ✗ web3 failed: {e}")
        import traceback; traceback.print_exc()

    if not reports:
        print("\n✗ No reports generated — aborting.")
        sys.exit(1)

    print(f"\n── Cross-agent index ────────────────────────────────────────")
    nav_dates = [DATE_STR]

    idx = build_daily_index(DATE_STR, nav_dates=nav_dates)
    if idx:
        print(f"  daily index → {idx.relative_to(_WS_ROOT)}  ({idx.stat().st_size} bytes)")

    nav = build_nav_index()
    print(f"  nav index   → {nav.relative_to(_WS_ROOT)}  ({nav.stat().st_size} bytes)")

    midx = build_monthly_index(DATE_STR[:7])
    if midx:
        print(f"  month index → {midx.relative_to(_WS_ROOT)}  ({midx.stat().st_size} bytes)")

    print(f"\n── Telegram brief (dry-run) ─────────────────────────────────")
    brief = build_cross_brief(DATE_STR)
    print()
    for line in brief.split("\n"):
        print(f"  {line}")

    print(f"\n✅ Done. Open in browser:")
    if idx:
        print(f"   open '{idx}'")


if __name__ == "__main__":
    main()
