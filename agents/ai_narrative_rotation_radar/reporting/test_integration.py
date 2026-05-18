#!/usr/bin/env python3
"""Integration test: RadarReportBuilder → shared reporting pipeline.

Run from agent root:
  .venv/bin/python reporting/test_integration.py

Uses synthetic RadarSnapshot objects (no live API calls, no Telegram sends).
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

_AGENT_ROOT = Path(__file__).resolve().parents[1]
_WS_ROOT    = _AGENT_ROOT.parents[1]
sys.path.insert(0, str(_WS_ROOT))
sys.path.insert(0, str(_AGENT_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="radar_report_test_"))
os.environ["REPORTS_BASE_DIR"] = str(_TMP)
os.environ["REPORTS_BASE_URL"] = f"file://{_TMP}"

# ── Minimal stub dataclasses matching radar core models ─────────────────────

@dataclass
class TickerMetrics:
    ticker: str
    as_of: date = field(default_factory=date.today)
    last_close: float = 100.0
    ret_1d: float = 0.0
    ret_5d: float = 0.0
    ret_1m: float = 0.0
    ret_3m: float = 0.0
    ret_ytd: float = 0.0
    rs_vs_spy_1d: float = 0.0
    rs_vs_spy_1m: float = 0.0
    rs_vs_qqq_1m: float = 0.0
    rs_vs_soxx_1m: float = 0.0
    above_20dma: bool = True
    above_50dma: bool = True
    above_200dma: bool = True
    ma20_slope: float = 0.0
    ma50_slope: float = 0.0
    ma50_value: float = 95.0
    volume_ratio_20d: float = 1.0
    drawdown_from_52w_high: float = 0.0
    composite_score: float = 50.0


@dataclass
class ThemeBreadth:
    theme_key: str
    theme_name: str
    as_of: date = field(default_factory=date.today)
    total_tickers: int = 5
    tickers_positive_rs_1m: int = 4
    tickers_above_20dma: int = 4
    tickers_above_50dma: int = 3
    breadth_rs: float = 0.80
    breadth_20dma: float = 0.80
    breadth_50dma: float = 0.60
    avg_rs_spy_1m: float = 0.0
    avg_rs_spy_1d: float = 0.0
    avg_volume_ratio: float = 1.0
    leaders: list = field(default_factory=list)
    laggards: list = field(default_factory=list)
    breadth_score: float = 70.0
    signal: str = "NEUTRAL"


@dataclass
class RotationSignal:
    detected: bool = False
    from_themes: list = field(default_factory=list)
    to_themes: list = field(default_factory=list)
    max_swing: float = 0.0
    confidence: int = 0
    description: str = ""
    as_of: date = field(default_factory=date.today)


@dataclass
class LEAPSCandidate:
    ticker: str
    as_of: date = field(default_factory=date.today)
    theme_key: str = ""
    theme_name: str = ""
    theme_score: float = 0.0
    rotation_score: float = 0.0
    rs_score: float = 0.0
    trend_score: float = 0.0
    pullback_score: float = 0.0
    options_score: float = 0.0
    risk_score: float = 0.0
    leaps_score: float = 0.0
    signal_type: str = "LEAPS_CALL_CANDIDATE"
    triggers: list = field(default_factory=list)
    risk_notes: list = field(default_factory=list)
    is_pullback_setup: bool = False
    drawdown_pct: float = 0.0
    pct_above_50dma: float = 0.0
    has_leaps: bool = True
    nearest_leaps_expiry: str = "2027-01-16"
    options_quality: str = "GOOD"


@dataclass
class RadarSnapshot:
    as_of: date = field(default_factory=date.today)
    ticker_metrics: dict = field(default_factory=dict)
    theme_breadths: dict = field(default_factory=dict)
    benchmark_metrics: dict = field(default_factory=dict)
    rotation_signal: Optional[RotationSignal] = None
    leaps_candidates: list = field(default_factory=list)
    ticker_to_theme: dict = field(default_factory=dict)


# ── Build synthetic snapshot ──────────────────────────────────────────────────

def _make_snapshot() -> RadarSnapshot:
    snap = RadarSnapshot(as_of=date(2026, 5, 14))

    # Benchmark metrics
    snap.benchmark_metrics = {
        "SPY":  TickerMetrics("SPY",  ret_1d=-0.5, ret_5d=-1.2, ret_1m=2.1, ret_3m=8.5, rs_vs_spy_1m=0.0, composite_score=60),
        "QQQ":  TickerMetrics("QQQ",  ret_1d=-0.8, ret_5d=-1.8, ret_1m=3.2, ret_3m=12.0, rs_vs_spy_1m=1.1, composite_score=65),
        "SOXX": TickerMetrics("SOXX", ret_1d=-1.1, ret_5d=-2.0, ret_1m=1.5, ret_3m=6.0, rs_vs_spy_1m=-0.6, composite_score=55),
    }

    # Theme breadths
    snap.theme_breadths = {
        "ai_infra": ThemeBreadth(
            "ai_infra", "AI Infrastructure", avg_rs_spy_1m=8.2, avg_rs_spy_1d=0.6,
            breadth_rs=0.80, breadth_20dma=0.85, avg_volume_ratio=1.9,
            leaders=["NVDA", "AVGO"], laggards=["AMD", "INTC"],
            breadth_score=84.0, signal="STRONG",
        ),
        "robotics": ThemeBreadth(
            "robotics", "Robotics & Automation", avg_rs_spy_1m=5.1, avg_rs_spy_1d=0.3,
            breadth_rs=0.67, breadth_20dma=0.72, avg_volume_ratio=1.4,
            leaders=["ISRG", "FANUY"], laggards=["IRBT"],
            breadth_score=71.0, signal="BROADENING",
        ),
        "ai_software": ThemeBreadth(
            "ai_software", "AI Software", avg_rs_spy_1m=1.2, avg_rs_spy_1d=-0.2,
            breadth_rs=0.50, breadth_20dma=0.55, avg_volume_ratio=1.1,
            leaders=["PLTR", "AI"], laggards=["PATH", "BBAI"],
            breadth_score=52.0, signal="NEUTRAL",
        ),
        "fintech": ThemeBreadth(
            "fintech", "Fintech", avg_rs_spy_1m=-2.1, avg_rs_spy_1d=-0.8,
            breadth_rs=0.30, breadth_20dma=0.35, avg_volume_ratio=0.9,
            leaders=["SQ"], laggards=["AFRM", "SOFI"],
            breadth_score=32.0, signal="NARROWING",
        ),
        "biotech": ThemeBreadth(
            "biotech", "Biotech & GLP1", avg_rs_spy_1m=-4.5, avg_rs_spy_1d=-1.2,
            breadth_rs=0.20, breadth_20dma=0.25, avg_volume_ratio=0.8,
            leaders=["LLY"], laggards=["HIMS", "AMGN"],
            breadth_score=22.0, signal="WEAK",
        ),
    }

    # Ticker metrics
    tickers = {
        "NVDA":  TickerMetrics("NVDA",  ret_1d=1.8, ret_1m=12.5, rs_vs_spy_1m=10.4, rs_vs_spy_1d=2.3, above_20dma=True, volume_ratio_20d=2.1, composite_score=91),
        "AVGO":  TickerMetrics("AVGO",  ret_1d=0.9, ret_1m=9.8,  rs_vs_spy_1m=7.7,  rs_vs_spy_1d=1.4, above_20dma=True, volume_ratio_20d=1.6, composite_score=83),
        "PLTR":  TickerMetrics("PLTR",  ret_1d=1.2, ret_1m=6.1,  rs_vs_spy_1m=4.0,  rs_vs_spy_1d=1.7, above_20dma=True, volume_ratio_20d=1.8, composite_score=77),
        "ISRG":  TickerMetrics("ISRG",  ret_1d=0.5, ret_1m=5.2,  rs_vs_spy_1m=3.1,  rs_vs_spy_1d=1.0, above_20dma=True, volume_ratio_20d=1.3, composite_score=72),
        "HIMS":  TickerMetrics("HIMS",  ret_1d=-4.2, ret_1m=-6.8, rs_vs_spy_1m=-8.9, rs_vs_spy_1d=-3.7, above_20dma=False, volume_ratio_20d=0.7, composite_score=28),
    }
    snap.ticker_metrics = tickers
    snap.ticker_to_theme = {
        "NVDA": "ai_infra", "AVGO": "ai_infra",
        "PLTR": "ai_software",
        "ISRG": "robotics",
        "HIMS": "biotech",
    }

    # Rotation signal
    snap.rotation_signal = RotationSignal(
        detected=True,
        from_themes=["biotech", "fintech"],
        to_themes=["ai_infra", "robotics"],
        max_swing=12.7,
        confidence=78,
        description="过去5日 AI 基础设施相对强度显著提升，Biotech 资金流出加速。",
    )

    # LEAPS candidates
    snap.leaps_candidates = [
        LEAPSCandidate(
            "NVDA", theme_key="ai_infra", theme_name="AI Infrastructure",
            leaps_score=91.0, signal_type="LEAPS_CALL_CANDIDATE",
            triggers=["主题得分 Strong (84/100)", "RS vs SPY 1M: +10.4%"],
            risk_notes=["距52W高点仅-8%，注意回调风险"],
            has_leaps=True, nearest_leaps_expiry="2027-01-16", options_quality="GOOD",
        ),
        LEAPSCandidate(
            "PLTR", theme_key="ai_software", theme_name="AI Software",
            leaps_score=82.0, signal_type="LEAPS_CALL_CANDIDATE",
            triggers=["政府合同驱动，基本面改善"],
            risk_notes=["估值偏高"],
            has_leaps=True, nearest_leaps_expiry="2027-01-16", options_quality="ACCEPTABLE",
        ),
    ]
    return snap


DATE_STR = "2026-05-14"


def main():
    print(f"Output: {_TMP}\n")

    snap = _make_snapshot()

    # 1. Build report
    from reporting.report_builder import RadarReportBuilder
    report = RadarReportBuilder().build(snap, DATE_STR, min_leaps_score=75.0)

    print(f"meta.agent:             {report.meta.agent}")
    print(f"meta.date:              {report.meta.date}")
    print(f"meta.summary:           {report.meta.summary}")
    print(f"meta.risk_level:        {report.meta.risk_level}")
    print(f"meta.opportunity_level: {report.meta.opportunity_level}")
    print(f"sections:               {[s.title for s in report.sections]}")
    print()

    # 2. Write Markdown
    from shared.reporting import write_report
    md_path = write_report(report)
    assert md_path.exists()
    content_md = md_path.read_text()
    assert "AI Infrastructure" in content_md
    assert "NVDA" in content_md
    print(f"✓ MD   ({md_path.stat().st_size} bytes)  →  {md_path.relative_to(_TMP)}")

    from shared.reporting.md_writer import parse_frontmatter
    fm = parse_frontmatter(md_path)
    assert fm["agent"] == "ai_narrative_rotation_radar"
    assert fm["risk_level"] in ("medium", "high")   # biotech WEAK + narrowing fintech
    print(f"  frontmatter: risk={fm['risk_level']} opp={fm['opportunity_level']}")

    # 3. Render HTML
    from shared.reporting import render_html
    html_path = render_html(report, nav_dates=[DATE_STR])
    assert html_path.exists()
    content = html_path.read_text()
    sz = html_path.stat().st_size
    assert sz > 12_000, f"HTML too small: {sz}"
    assert "Chart.js" in content
    assert "LEAPS" in content
    assert "Rotation" in content
    print(f"✓ HTML ({sz} bytes)  →  {html_path.relative_to(_TMP)}")

    # 4. Build daily index
    from shared.reporting.index_builder import build_daily_index, build_nav_index
    idx = build_daily_index(DATE_STR, nav_dates=[DATE_STR])
    assert idx and idx.exists()
    print(f"✓ index  → {idx.relative_to(_TMP)}")

    # 5. Telegram brief
    from shared.reporting import build_brief
    brief = build_brief(DATE_STR, [report])
    assert "narrative" in brief.lower() or "radar" in brief.lower()
    assert DATE_STR in brief
    assert len(brief) < 1000
    print(f"✓ brief  ({len(brief)} chars)")
    print()
    for line in brief.split("\n"):
        print(f"  {line}")

    print(f"\n✅ Integration test passed — {_TMP}")


if __name__ == "__main__":
    main()
