"""
CC-EXCLUSIVE — do not modify without CC session + user confirmation.

LLMGateway: unified entry point for all LLM calls in Northstar SignalOS.

Usage:
    from shared.llm.gateway import LLMGateway
    from shared.llm.model_router import TaskType

    gw = LLMGateway.from_cfg(cfg)
    output = gw.complete(TaskType.SCHOOL_EXTRACT, system_prompt, user_prompt,
                         agent_name="school_helper")
    text = output.text  # ValidatedOutput — gate has already passed

The gateway:
  1. Routes the task to the correct provider tier via model_router.py
  2. Enforces task-type allow list for each model tier (ToolPermissionChecker)
  3. Calls the provider with retry / fallback (escalates UP — never down)
  4. Validates the draft through OutputGate
  5. Records the call in AuditLog with token counts, latency, cost
  6. Records estimated cost in CostAccumulator
  7. Returns ValidatedOutput

Agents never call provider clients directly — always go through LLMGateway.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .fallback import FallbackExhausted, with_fallback
from .governance.audit_log import AuditLog
from .governance.cost_tracker import get_accumulator
from .governance.output_gate import GateRejection, validate_safe
from .interface import DraftOutput, LLMClient, ValidatedOutput
from .model_router import ModelTier, RouteDecision, TaskType, get_model_id, route

logger = logging.getLogger("signalos.llm.gateway")

# ToolPermissionChecker is optional — loaded lazily to avoid hard-failing agents
# that don't have pyyaml installed yet.
_CHECKER_SENTINEL = object()
_checker_cache: object = _CHECKER_SENTINEL


def _get_checker():
    """Return a cached ToolPermissionChecker, or None if unavailable."""
    global _checker_cache
    if _checker_cache is _CHECKER_SENTINEL:
        try:
            from .governance.tool_permissions import ToolPermissionChecker
            _checker_cache = ToolPermissionChecker.load()
            logger.info("ToolPermissionChecker loaded")
        except Exception as e:
            logger.warning("ToolPermissionChecker unavailable (skipping task-type gate): %s", e)
            _checker_cache = None
    return _checker_cache


class LLMGateway:
    """
    Unified LLM gateway. All agents use this; no direct provider calls.

    Providers are initialized lazily on first use — agents without certain
    API keys can still instantiate LLMGateway and use available tiers.
    """

    def __init__(
        self,
        anthropic: LLMClient | None = None,
        qwen: LLMClient | None = None,
        codex: LLMClient | None = None,
        audit_log: AuditLog | None = None,
    ):
        self._providers: dict[ModelTier, object] = {}
        if anthropic:
            self._providers[ModelTier.CC] = anthropic
        if qwen:
            self._providers[ModelTier.QWEN] = qwen
        if codex:
            self._providers[ModelTier.CODEX] = codex
        self._audit = audit_log or AuditLog()
        self._cost  = get_accumulator()

    @classmethod
    def from_cfg(cls, cfg: dict, audit_path: Path | None = None) -> "LLMGateway":
        """Build a gateway from an agent config dict. Silently skips unavailable providers."""
        anthropic, qwen, codex = None, None, None

        if cfg.get("anthropic_api_key"):
            try:
                from .providers.anthropic_client import AnthropicClient, AnthropicConfig
                anthropic = AnthropicClient(AnthropicConfig.from_cfg(cfg))
            except Exception as e:
                logger.warning("Anthropic client init failed: %s", e)

        if cfg.get("qwen_api_key"):
            try:
                from .providers.qwen_client import QwenClient, QwenConfig
                qwen = QwenClient(QwenConfig.from_cfg(cfg))
            except Exception as e:
                logger.warning("Qwen client init failed: %s", e)

        if cfg.get("openai_api_key"):
            try:
                from .providers.codex_client import CodexClient, CodexConfig
                codex = CodexClient(CodexConfig.from_cfg(cfg))
            except Exception as e:
                logger.warning("Codex client init failed: %s", e)

        # OpenRouter — V1 governance: Qwen tier ONLY.
        # CC stays direct Anthropic. Codex is manual handoff in V1 (no API path).
        # See specs/MODEL_GOVERNANCE.md for rationale.
        if cfg.get("openrouter_api_key") and qwen is None:
            try:
                from .providers.openrouter_client import OpenRouterClient, OpenRouterConfig
                llm = cfg.get("llm", {})
                model = llm.get("openrouter_qwen_model", "qwen/qwen-plus")
                qwen = OpenRouterClient(OpenRouterConfig.from_cfg(cfg, model))
                logger.info("OpenRouter → Qwen tier: %s", model)
            except Exception as e:
                logger.warning("OpenRouter client init failed: %s", e)

        audit = AuditLog(audit_path) if audit_path else AuditLog()
        return cls(anthropic=anthropic, qwen=qwen, codex=codex, audit_log=audit)

    def complete(
        self,
        task_type: TaskType,
        system: str,
        user: str,
        *,
        agent_name: str | None = None,
    ) -> ValidatedOutput:
        """
        Route, enforce permissions, call, validate, audit, track cost.
        Returns ValidatedOutput.
        Raises GateRejection if the output fails governance.
        Raises FallbackExhausted if all tiers fail.
        Raises ToolDenied if the task type is not permitted for the routed tier.
        """
        decision = route(task_type)

        # Task-type permission gate: e.g. blocks Qwen from doing ARCHITECTURE tasks
        checker = _get_checker()
        if checker is not None:
            try:
                checker.check_task_allowed(decision.tier.value, task_type.value)
            except Exception as denied:
                logger.error(
                    "Task-type denied. task=%s tier=%s agent=%s: %s",
                    task_type.value, decision.tier.value, agent_name, denied,
                )
                raise

        t0 = time.monotonic()
        draft = self._call_with_fallback(decision, system, user)
        latency_ms = (time.monotonic() - t0) * 1000.0

        result = validate_safe(draft, task_type)

        in_tok  = int(draft.metadata.get("input_tokens",  0))
        out_tok = int(draft.metadata.get("output_tokens", 0))
        cost    = self._cost.record(
            agent=agent_name or "unknown",
            model_id=decision.model_id,
            task_type=task_type.value,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
        )

        self._audit.record_call(
            task_type=task_type,
            tier=decision.tier,
            model_id=decision.model_id,
            draft=draft,
            gate_passed=result.passed,
            rejection_rule=result.rejection_rule,
            agent=agent_name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
            cost_usd=cost,
        )

        if not result.passed:
            raise GateRejection(
                result.rejection_rule or "unknown",
                result.rejection_reason or "Gate rejected draft",
            )
        return result.output  # type: ignore[return-value]

    def complete_safe(
        self,
        task_type: TaskType,
        system: str,
        user: str,
        *,
        agent_name: str | None = None,
    ) -> ValidatedOutput | None:
        """Non-raising variant. Returns None on gate rejection or provider failure."""
        try:
            return self.complete(task_type, system, user, agent_name=agent_name)
        except (GateRejection, FallbackExhausted) as e:
            logger.warning("Gateway complete_safe absorbed error: %s", e)
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _call_with_fallback(
        self, decision: RouteDecision, system: str, user: str
    ) -> DraftOutput:
        provider = self._providers.get(decision.tier)
        if provider is None:
            logger.warning(
                "Provider not configured for tier=%s task=%s, trying fallback",
                decision.tier.value, decision.task_type.value,
            )
            return self._call_fallback(decision, system, user,
                                       reason=f"tier={decision.tier.value} not configured")

        fallback_fn = None
        if decision.fallback_tier and self._providers.get(decision.fallback_tier):
            fb_provider = self._providers[decision.fallback_tier]
            fallback_fn = lambda: fb_provider.complete(system, user)  # type: ignore[union-attr]

        return with_fallback(
            primary_fn=lambda: provider.complete(system, user),  # type: ignore[union-attr]
            fallback_fn=fallback_fn,
            task_type=decision.task_type,
            primary_tier=decision.tier,
        )

    def _call_fallback(
        self, decision: RouteDecision, system: str, user: str, reason: str
    ) -> DraftOutput:
        if decision.fallback_tier is None:
            raise FallbackExhausted(
                f"No fallback tier for {decision.tier.value} and provider not configured"
            )
        fb_provider = self._providers.get(decision.fallback_tier)
        if fb_provider is None:
            raise FallbackExhausted(
                f"Fallback tier={decision.fallback_tier.value} also not configured"
            )
        draft = fb_provider.complete(system, user)  # type: ignore[union-attr]
        draft.metadata["fallback_from"] = decision.tier.value
        draft.metadata["fallback_reason"] = reason
        return draft
