"""Tests for output_gate.py — all gate rules."""
import pytest
from shared.llm.interface import DraftOutput
from shared.llm.model_router import TaskType
from shared.llm.governance.output_gate import (
    GateRejection, validate, validate_safe
)


def _draft(text: str, source: str = "qwen", **metadata) -> DraftOutput:
    return DraftOutput(text=text, source=source, model="test-model", metadata=metadata)


# ── Happy path ────────────────────────────────────────────────────────────────

def test_clean_qwen_draft_passes():
    draft = _draft("BTC 上涨 3%，市场情绪偏多。", source="qwen")
    out = validate(draft, TaskType.TELEGRAM_DRAFT)
    assert out.gate_passed
    assert out.validated
    assert out.text == draft.text


def test_clean_claude_draft_passes():
    draft = _draft("Market regime: bullish. VIX at 14.", source="claude")
    out = validate(draft, TaskType.REPORT_DRAFT)
    assert out.gate_passed


# ── Rule: no_api_keys ─────────────────────────────────────────────────────────

def test_rejects_openai_key_pattern():
    draft = _draft("Config: sk-abc123DEF456GHI789JKL012MNO345 is the key")
    with pytest.raises(GateRejection) as exc:
        validate(draft)
    assert exc.value.rule == "no_api_keys"


def test_rejects_bearer_token():
    draft = _draft("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123")
    with pytest.raises(GateRejection) as exc:
        validate(draft)
    assert exc.value.rule == "no_api_keys"


# ── Rule: no_wallet_addresses ─────────────────────────────────────────────────

def test_rejects_eth_wallet():
    draft = _draft("Send to 0xAbCdEf0123456789AbCdEf0123456789AbCdEf01")
    with pytest.raises(GateRejection) as exc:
        validate(draft)
    assert exc.value.rule == "no_wallet_addresses"


# ── Rule: no_financial_advice ─────────────────────────────────────────────────

def test_rejects_buy_recommendation():
    draft = _draft("You should buy NVDA right now.")
    with pytest.raises(GateRejection) as exc:
        validate(draft)
    assert exc.value.rule == "no_financial_advice"


def test_analytical_statement_passes():
    # Analytical language is fine; advisory directed at user is not
    draft = _draft("NVDA shows bullish momentum with RSI 68 and MACD crossover.")
    out = validate(draft)
    assert out.gate_passed


# ── Rule: no_unvalidated_trading_signal ───────────────────────────────────────

def test_rejects_qwen_trading_signal():
    draft = _draft("Strong buy signal", source="qwen", signal_type="trading")
    with pytest.raises(GateRejection) as exc:
        validate(draft, TaskType.SIGNAL_EXPLAIN)
    assert exc.value.rule == "no_unvalidated_trading_signal"


def test_claude_trading_signal_passes_if_task_is_not_signal_final():
    # Claude output for a report draft is fine even with signal content
    draft = _draft("Signal: BTC bullish regime detected.", source="claude")
    out = validate(draft, TaskType.REPORT_DRAFT)
    assert out.gate_passed


# ── Rule: cc_exclusive_task ───────────────────────────────────────────────────

def test_rejects_qwen_for_cc_exclusive_task():
    draft = _draft("Architecture decision: use microservices.", source="qwen")
    with pytest.raises(GateRejection) as exc:
        validate(draft, TaskType.ARCHITECTURE)
    assert exc.value.rule == "cc_exclusive_task"


def test_claude_passes_for_cc_exclusive_task():
    draft = _draft("Architecture decision.", source="claude")
    out = validate(draft, TaskType.ARCHITECTURE)
    assert out.gate_passed


# ── Rule: length_limit_4096 ───────────────────────────────────────────────────

def test_rejects_message_over_telegram_limit():
    draft = _draft("x" * 4097)
    with pytest.raises(GateRejection) as exc:
        validate(draft)
    assert exc.value.rule == "length_limit_4096"


def test_message_at_limit_passes():
    draft = _draft("x" * 4096)
    out = validate(draft)
    assert out.gate_passed


# ── validate_safe (non-raising) ───────────────────────────────────────────────

def test_validate_safe_returns_false_on_rejection():
    draft = _draft("You should buy NVDA now.")
    result = validate_safe(draft)
    assert not result.passed
    assert result.output is None
    assert result.rejection_rule == "no_financial_advice"


def test_validate_safe_returns_true_on_clean():
    draft = _draft("BTC 市场分析：多头信号增强。")
    result = validate_safe(draft)
    assert result.passed
    assert result.output is not None
