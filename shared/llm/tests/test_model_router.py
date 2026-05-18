"""Tests for model_router.py — routing table correctness."""
import pytest
from shared.llm.model_router import (
    CC_EXCLUSIVE_TASKS, ModelTier, RouteDecision, TaskType, route
)


def test_cc_exclusive_tasks_route_to_cc():
    for task in CC_EXCLUSIVE_TASKS:
        decision = route(task)
        assert decision.tier == ModelTier.CC, f"{task} should route to CC"
        assert decision.fallback_tier is None, f"CC tasks have no fallback"


def test_qwen_tasks_route_to_qwen():
    qwen_tasks = [
        TaskType.SUMMARIZE_BULK,
        TaskType.TRANSLATE,
        TaskType.TELEGRAM_DRAFT,
        TaskType.SCHOOL_EXTRACT,
        TaskType.REPORT_DRAFT,
        TaskType.SIGNAL_EXPLAIN,
        TaskType.LOG_COMPRESS,
        TaskType.CLASSIFY_LOW_RISK,
    ]
    for task in qwen_tasks:
        decision = route(task)
        assert decision.tier == ModelTier.QWEN, f"{task} should route to Qwen"
        assert decision.fallback_tier == ModelTier.CC, f"Qwen falls back to CC"


def test_codex_tasks_route_to_codex():
    codex_tasks = [
        TaskType.FEATURE_IMPL,
        TaskType.BUG_FIX,
        TaskType.TEST_CREATION,
        TaskType.FORMATTER_IMPL,
        TaskType.BOILERPLATE,
    ]
    for task in codex_tasks:
        decision = route(task)
        assert decision.tier == ModelTier.CODEX, f"{task} should route to Codex"
        assert decision.fallback_tier == ModelTier.CC, f"Codex falls back to CC"


def test_rule_tasks_have_no_fallback():
    rule_tasks = [TaskType.SIGNAL_COMPUTE, TaskType.ALERT_THROTTLE, TaskType.DATA_FETCH]
    for task in rule_tasks:
        decision = route(task)
        assert decision.tier == ModelTier.RULE
        assert decision.fallback_tier is None


def test_signal_final_never_routes_to_qwen_or_codex():
    decision = route(TaskType.SIGNAL_FINAL)
    assert decision.tier not in (ModelTier.QWEN, ModelTier.CODEX)
    assert decision.tier == ModelTier.CC


def test_route_returns_route_decision():
    decision = route(TaskType.SCHOOL_EXTRACT)
    assert isinstance(decision, RouteDecision)
    assert decision.task_type == TaskType.SCHOOL_EXTRACT
    assert decision.model_id  # non-empty string
