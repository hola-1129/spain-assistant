"""Tests for fallback.py — escalation chain logic."""
import pytest
from shared.llm.interface import DraftOutput
from shared.llm.model_router import ModelTier, TaskType
from shared.llm.fallback import FallbackExhausted, with_fallback


def _success_fn(source: str = "qwen") -> DraftOutput:
    return DraftOutput(text="ok", source=source, model="test")


def _fail_fn():
    raise RuntimeError("provider error")


# ── Primary succeeds ──────────────────────────────────────────────────────────

def test_returns_primary_on_success():
    result = with_fallback(
        primary_fn=lambda: _success_fn("qwen"),
        fallback_fn=lambda: _success_fn("claude"),
        task_type=TaskType.SCHOOL_EXTRACT,
        primary_tier=ModelTier.QWEN,
    )
    assert result.source == "qwen"


# ── Primary fails, fallback succeeds ─────────────────────────────────────────

def test_uses_fallback_when_primary_fails():
    result = with_fallback(
        primary_fn=_fail_fn,
        fallback_fn=lambda: _success_fn("claude"),
        task_type=TaskType.SCHOOL_EXTRACT,
        primary_tier=ModelTier.QWEN,
    )
    assert result.source == "claude"
    assert result.metadata.get("fallback_from") == "qwen"
    assert "provider error" in result.metadata.get("fallback_reason", "")


# ── Primary fails, no fallback available ─────────────────────────────────────

def test_raises_when_no_fallback():
    with pytest.raises(FallbackExhausted):
        with_fallback(
            primary_fn=_fail_fn,
            fallback_fn=None,
            task_type=TaskType.ARCHITECTURE,
            primary_tier=ModelTier.CC,
        )


# ── Both fail ─────────────────────────────────────────────────────────────────

def test_raises_when_both_fail():
    with pytest.raises(FallbackExhausted):
        with_fallback(
            primary_fn=_fail_fn,
            fallback_fn=_fail_fn,
            task_type=TaskType.SCHOOL_EXTRACT,
            primary_tier=ModelTier.QWEN,
        )


# ── Fallback escalates UP ─────────────────────────────────────────────────────

def test_fallback_from_qwen_uses_cc_not_codex():
    # The FALLBACK_CHAIN maps QWEN → CC. This test ensures the metadata tag is correct.
    result = with_fallback(
        primary_fn=_fail_fn,
        fallback_fn=lambda: DraftOutput(text="cc output", source="claude", model="claude-sonnet-4-6"),
        task_type=TaskType.TELEGRAM_DRAFT,
        primary_tier=ModelTier.QWEN,
    )
    assert result.source == "claude"
    assert result.metadata["fallback_from"] == "qwen"
