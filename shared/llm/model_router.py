"""
CC-EXCLUSIVE — do not modify without CC session + user confirmation.

Model routing table for Northstar SignalOS.

To change a route: open a CC session, explain the rationale, get approval, then edit.
No automated mutation of this file is permitted by any model or script.

Routing priority: task_type → tier → model_id → fallback_tier
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelTier(str, Enum):
    CC    = "cc"      # Claude — architecture, governance, reasoning
    CODEX = "codex"   # OpenAI/Codex — engineering execution
    QWEN  = "qwen"    # Qwen/DashScope — low-cost bulk processing
    RULE  = "rule"    # No LLM — deterministic rule-based handling


class TaskType(str, Enum):
    # ── CC-exclusive ─────────────────────────────────────────────────────────
    ARCHITECTURE         = "architecture"
    SECURITY_REVIEW      = "security_review"
    GOVERNANCE_GATE      = "governance_gate"
    PRODUCTION_APPROVAL  = "production_approval"
    MCP_DESIGN           = "mcp_design"
    SIGNAL_FINAL         = "signal_final"       # Final trading signal — CC sole authority
    FINANCIAL_ADVICE     = "financial_advice"   # Portfolio analysis & actionable insight — CC only

    # ── Codex ─────────────────────────────────────────────────────────────────
    FEATURE_IMPL         = "feature_impl"
    BUG_FIX              = "bug_fix"
    TEST_CREATION        = "test_creation"
    FORMATTER_IMPL       = "formatter_impl"
    BOILERPLATE          = "boilerplate"

    # ── Qwen ──────────────────────────────────────────────────────────────────
    SUMMARIZE_BULK       = "summarize_bulk"
    TRANSLATE            = "translate"
    TELEGRAM_DRAFT       = "telegram_draft"
    CLASSIFY_LOW_RISK    = "classify_low_risk"
    LOG_COMPRESS         = "log_compress"
    SIGNAL_EXPLAIN       = "signal_explain"     # Plain-language explanation only
    SCHOOL_EXTRACT       = "school_extract"
    REPORT_DRAFT         = "report_draft"
    NEWS_CURATION        = "news_curation"      # Portfolio news selection & summary

    # ── Rule-based (no LLM) ───────────────────────────────────────────────────
    SIGNAL_COMPUTE       = "signal_compute"
    ALERT_THROTTLE       = "alert_throttle"
    DATA_FETCH           = "data_fetch"


@dataclass(frozen=True)
class RouteDecision:
    task_type: TaskType
    tier: ModelTier
    model_id: str
    fallback_tier: ModelTier | None


# ── Routing table ─────────────────────────────────────────────────────────────
# CC retains override authority. Any change requires CC approval.
_ROUTING_TABLE: dict[TaskType, ModelTier] = {
    # CC exclusive
    TaskType.ARCHITECTURE:         ModelTier.CC,
    TaskType.SECURITY_REVIEW:      ModelTier.CC,
    TaskType.GOVERNANCE_GATE:      ModelTier.CC,
    TaskType.PRODUCTION_APPROVAL:  ModelTier.CC,
    TaskType.MCP_DESIGN:           ModelTier.CC,
    TaskType.SIGNAL_FINAL:         ModelTier.CC,
    TaskType.FINANCIAL_ADVICE:     ModelTier.CC,

    # Codex
    TaskType.FEATURE_IMPL:         ModelTier.CODEX,
    TaskType.BUG_FIX:              ModelTier.CODEX,
    TaskType.TEST_CREATION:        ModelTier.CODEX,
    TaskType.FORMATTER_IMPL:       ModelTier.CODEX,
    TaskType.BOILERPLATE:          ModelTier.CODEX,

    # Qwen
    TaskType.SUMMARIZE_BULK:       ModelTier.QWEN,
    TaskType.TRANSLATE:            ModelTier.QWEN,
    TaskType.TELEGRAM_DRAFT:       ModelTier.QWEN,
    TaskType.CLASSIFY_LOW_RISK:    ModelTier.QWEN,
    TaskType.LOG_COMPRESS:         ModelTier.QWEN,
    TaskType.SIGNAL_EXPLAIN:       ModelTier.QWEN,
    TaskType.SCHOOL_EXTRACT:       ModelTier.QWEN,
    TaskType.REPORT_DRAFT:         ModelTier.QWEN,
    TaskType.NEWS_CURATION:        ModelTier.QWEN,

    # Rule-based
    TaskType.SIGNAL_COMPUTE:       ModelTier.RULE,
    TaskType.ALERT_THROTTLE:       ModelTier.RULE,
    TaskType.DATA_FETCH:           ModelTier.RULE,
}

# Model IDs — updated by CC when providers or versions change
_MODEL_IDS: dict[ModelTier, str] = {
    ModelTier.CC:    "claude-sonnet-4-6",
    ModelTier.CODEX: "codex-mini-latest",
    ModelTier.QWEN:  "qwen-plus",
    ModelTier.RULE:  "__rule_based__",
}

# Fallback always escalates UP — never down to a lower-governance tier
_FALLBACK_CHAIN: dict[ModelTier, ModelTier | None] = {
    ModelTier.CC:    None,           # CC has no fallback — fail explicitly
    ModelTier.CODEX: ModelTier.CC,   # Codex fails → escalate to CC
    ModelTier.QWEN:  ModelTier.CC,   # Qwen fails → escalate to CC (not Codex)
    ModelTier.RULE:  None,
}

# CC-exclusive task types — gate enforces this at runtime
CC_EXCLUSIVE_TASKS: frozenset[TaskType] = frozenset({
    TaskType.ARCHITECTURE,
    TaskType.SECURITY_REVIEW,
    TaskType.GOVERNANCE_GATE,
    TaskType.PRODUCTION_APPROVAL,
    TaskType.MCP_DESIGN,
    TaskType.SIGNAL_FINAL,
    TaskType.FINANCIAL_ADVICE,
})


def route(task_type: TaskType) -> RouteDecision:
    """Return routing decision for a given task type."""
    tier = _ROUTING_TABLE.get(task_type, ModelTier.CC)
    return RouteDecision(
        task_type=task_type,
        tier=tier,
        model_id=_MODEL_IDS[tier],
        fallback_tier=_FALLBACK_CHAIN[tier],
    )


def get_model_id(tier: ModelTier) -> str:
    return _MODEL_IDS[tier]
