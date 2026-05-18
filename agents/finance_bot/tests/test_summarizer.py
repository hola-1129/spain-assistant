"""
Tests for finance_bot summarizer (Phase 2).

Validates:
  - Drafter init skipped when llm_enrichment.enabled=false (default)
  - Enrich methods return original on any failure
  - Enrich methods prepend snippet when Qwen succeeds
  - OutputGate rejection falls back to original message
  - signal_alerts invariant: no drafter wiring in signal paths
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from summarizer.daily_report_drafter import DailyReportDrafter
from shared.llm.interface import DraftOutput


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_qwen(text: str = "今日市场整体偏强，AI板块领涨。"):
    mock = MagicMock()
    mock.complete.return_value = MagicMock(text=text)
    return mock


def _stock_results(n: int = 5):
    return [
        {"symbol": f"SYM{i}", "daily_change_pct": float(i * 2 - 4), "asset_type": "stock"}
        for i in range(n)
    ]


@dataclass
class _FakePosition:
    label: str
    day_change_pct: float
    nav_pct: float = 0.1


# ── DailyReportDrafter: enrich_daily_summary ──────────────────────────────────

def test_enrich_daily_summary_prepends_snippet():
    drafter = DailyReportDrafter(_make_qwen("今日市场偏强。"))
    original = "📊 *今日 Market Movers*\n日期: 2026-05-10"
    result = drafter.enrich_daily_summary(original, _stock_results(), date_str="2026-05-10")
    assert result.startswith("今日市场偏强。")
    assert original in result


def test_enrich_daily_summary_returns_original_on_qwen_error():
    mock = MagicMock()
    mock.complete.side_effect = RuntimeError("Qwen timeout")
    drafter = DailyReportDrafter(mock)
    original = "📊 *今日 Market Movers*\n日期: 2026-05-10"
    result = drafter.enrich_daily_summary(original, _stock_results(), date_str="2026-05-10")
    assert result == original


def test_enrich_daily_summary_returns_original_on_gate_rejection():
    # API key pattern in Qwen output — gate rejects
    drafter = DailyReportDrafter(_make_qwen("sk-abc123DEF456GHI789JKL012MNO345 配置已更新"))
    original = "📊 *今日 Market Movers*"
    result = drafter.enrich_daily_summary(original, _stock_results(), date_str="2026-05-10")
    assert result == original  # gate rejected, fallback to original


def test_enrich_daily_summary_returns_original_if_result_too_long():
    long_snippet = "市场很好。" * 1000  # will make enriched > 4096 chars
    drafter = DailyReportDrafter(_make_qwen(long_snippet))
    original = "📊 *短消息*"
    result = drafter.enrich_daily_summary(original, _stock_results(), date_str="2026-05-10")
    assert result == original


# ── DailyReportDrafter: enrich_portfolio_report ───────────────────────────────

def test_enrich_portfolio_returns_original_on_empty_results():
    drafter = DailyReportDrafter(_make_qwen("组合稳定。"))
    original = "📊 *Portfolio Daily Report*"
    result = drafter.enrich_portfolio_report(original, [], date_str="2026-05-10")
    assert result == original


def test_enrich_portfolio_prepends_snippet():
    positions = [_FakePosition("NVDA", 3.2, 0.25), _FakePosition("PLTR", -1.1, 0.18)]
    drafter = DailyReportDrafter(_make_qwen("今日组合小幅上涨，NVDA 贡献最大。"))
    original = "📊 *Portfolio Daily Report*\n日期: 2026-05-10"
    result = drafter.enrich_portfolio_report(original, positions, date_str="2026-05-10")
    assert result.startswith("今日组合小幅上涨")
    assert original in result


def test_enrich_portfolio_returns_original_on_qwen_error():
    mock = MagicMock()
    mock.complete.side_effect = ConnectionError("network error")
    drafter = DailyReportDrafter(mock)
    original = "📊 *Portfolio Daily Report*"
    result = drafter.enrich_portfolio_report(original, [_FakePosition("NVDA", 1.5)], date_str="2026-05-10")
    assert result == original


# ── Scheduler invariant: drafter not wired to signal paths ───────────────────

def test_signal_paths_have_no_drafter_wiring():
    scheduler_path = Path(__file__).resolve().parents[1] / "scheduler.py"
    src = scheduler_path.read_text()
    signal_methods = [
        "_high_freq_check",
        "_mid_freq_check",
        "_low_freq_check",
        "_stock_scan",
        "_asia_scan",
        "_macro_scan",
    ]
    for method in signal_methods:
        # Extract method body (text between method name and next "def _")
        parts = src.split(f"def {method}")
        assert len(parts) >= 2, f"{method} not found in scheduler.py"
        body = parts[1].split("def _")[0]
        assert "drafter" not in body, (
            f"INVARIANT VIOLATED: drafter found in {method}. "
            "Trading signal paths must never use Qwen."
        )


# ── Config: llm_enrichment defaults ──────────────────────────────────────────

def test_llm_enrichment_defaults_to_disabled():
    import yaml
    cfg_path = Path(__file__).resolve().parents[1] / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    enrich = cfg.get("llm_enrichment", {})
    assert enrich.get("enabled") is False, "llm_enrichment.enabled must default to false"
    assert enrich.get("signal_alerts") is False, "signal_alerts must always be false"
