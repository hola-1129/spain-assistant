"""
Phase 3 tests for web3_monitor Qwen enrichment layer.

Validates:
  - SignalExplainer returns None on Qwen error (never blocks delivery)
  - SignalExplainer returns None on OutputGate rejection
  - SignalExplainer returns explanation on clean Qwen output
  - format_signal_alert appends qwen_explanation when present
  - format_signal_alert unchanged when qwen_explanation absent (backward-compat)
  - _handle_market_movers has no Qwen wiring (invariant)
  - config defaults all false
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Workspace root on path (for shared.llm)
_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# Scripts directory on path (for local imports)
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from summarizer.signal_explainer import SignalExplainer
from shared.llm.interface import DraftOutput


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_qwen(text: str = "BTC DEX成交量突破异常，链上活跃度显著上升。"):
    mock = MagicMock()
    mock.complete.return_value = MagicMock(text=text)
    return mock


def _cross_signal(score: int = 75) -> dict:
    return {
        "asset": "BTC", "chain": "ethereum",
        "type": "cross", "score": score,
        "interpretation": "DEX volume spike + Polymarket probability shift",
        "dex": {"price_change_1h_pct": 3.2, "volume_change_1h_pct": 180.0},
        "polymarket": {"probability_change_pct": 12.0, "title": "Will BTC hit 100k?"},
    }


# ── SignalExplainer ───────────────────────────────────────────────────────────

def test_explain_returns_text_on_clean_output():
    explainer = SignalExplainer(_make_qwen("BTC DEX成交量激增，Polymarket概率同步上涨，多头动能增强。"))
    result = explainer.explain(_cross_signal())
    assert result is not None
    assert "BTC" in result or len(result) > 5


def test_explain_returns_none_on_qwen_error():
    mock = MagicMock()
    mock.complete.side_effect = RuntimeError("Qwen timeout")
    explainer = SignalExplainer(mock)
    result = explainer.explain(_cross_signal())
    assert result is None


def test_explain_returns_none_on_gate_rejection():
    # API key pattern → gate rejects
    explainer = SignalExplainer(_make_qwen("sk-abc123DEF456GHI789JKL012MNO345 配置"))
    result = explainer.explain(_cross_signal())
    assert result is None


def test_explain_returns_none_for_financial_advice():
    explainer = SignalExplainer(_make_qwen("You should buy BTC right now."))
    result = explainer.explain(_cross_signal())
    assert result is None


def test_explain_returns_none_on_empty_qwen_output():
    explainer = SignalExplainer(_make_qwen(""))
    result = explainer.explain(_cross_signal())
    assert result is None


# ── telegram_notify: backward compatibility ───────────────────────────────────

def test_format_signal_alert_unchanged_without_explanation():
    from telegram_notify import format_signal_alert
    signal = _cross_signal()
    text = format_signal_alert(signal)
    assert "💡" not in text
    assert "qwen_explanation" not in text
    assert "Web3 Quant Signal" in text


def test_format_signal_alert_appends_explanation_when_present():
    from telegram_notify import format_signal_alert
    signal = {**_cross_signal(), "qwen_explanation": "链上活跃度上升，多头情绪增强。"}
    text = format_signal_alert(signal)
    assert "💡 链上活跃度上升" in text
    assert "Web3 Quant Signal" in text


def test_format_signal_alert_omits_empty_explanation():
    from telegram_notify import format_signal_alert
    signal = {**_cross_signal(), "qwen_explanation": ""}
    text = format_signal_alert(signal)
    assert "💡" not in text


# ── Invariant: market movers have no Qwen wiring ─────────────────────────────

def test_market_movers_have_no_qwen_wiring():
    src = (_SCRIPTS_DIR / "agent_orchestrator.py").read_text()
    body = src.split("def _handle_market_movers")[1].split("def _")[0]
    assert "qwen_explanation" not in body, (
        "INVARIANT VIOLATED: qwen_explanation found in _handle_market_movers"
    )
    assert "explainer" not in body, (
        "INVARIANT VIOLATED: explainer found in _handle_market_movers"
    )


# ── Config defaults ───────────────────────────────────────────────────────────

def test_llm_enrichment_defaults_to_disabled():
    import yaml
    cfg_path = _SCRIPTS_DIR.parent / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    enrich = cfg.get("llm_enrichment", {})
    assert enrich.get("enabled") is False
    assert enrich.get("signal_explain") is False
    assert enrich.get("project_screen") is False
