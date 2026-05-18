"""
CC-EXCLUSIVE — do not modify without CC session + user confirmation.

Tool Permission Layer for Northstar SignalOS.

Enforces default-deny policy for all external tool calls and LLM iterations:
  - Per-model tool whitelist (qwen → zero tools)
  - Per-agent tool whitelist
  - Max tool call limit per run
  - Max iteration limit per run
  - Task-type allow list per model tier

Usage in agent code:
    from shared.llm.governance.tool_permissions import ToolPermissionChecker, AgentBudget

    checker = ToolPermissionChecker.load()
    budget  = AgentBudget(agent="finance_bot", model_tier="cc", checker=checker)

    # Before calling any external tool:
    budget.use_tool("stock_api")      # raises ToolDenied if not whitelisted
    result = stock_api.fetch(symbol)  # call the tool

    # Count each LLM call as one iteration:
    budget.tick_iteration()           # raises IterationLimitExceeded if over limit
    output = gateway.complete(...)

Usage in gateway:
    checker.check_task_allowed("qwen", "architecture")  # raises ToolDenied
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("signalos.llm.tool_permissions")

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "shared" / "configs" / "tool_permissions.yaml"
_ALLOW_ALL = "__all__"


# ── Exceptions ────────────────────────────────────────────────────────────────

class ToolDenied(PermissionError):
    """Agent or model attempted to use a tool not in its whitelist."""
    def __init__(self, tool: str, agent: str | None, model_tier: str | None, reason: str):
        self.tool = tool
        self.agent = agent
        self.model_tier = model_tier
        self.reason = reason
        super().__init__(
            f"Tool '{tool}' denied for agent={agent} model={model_tier}: {reason}"
        )


class IterationLimitExceeded(RuntimeError):
    """Agent exceeded its max_iterations limit for a single run."""
    def __init__(self, agent: str, limit: int, current: int):
        super().__init__(
            f"Agent '{agent}' exceeded max_iterations={limit} (attempted={current})"
        )


class ToolCallLimitExceeded(RuntimeError):
    """Agent exceeded its max_tool_calls limit for a single run."""
    def __init__(self, agent: str, limit: int, current: int):
        super().__init__(
            f"Agent '{agent}' exceeded max_tool_calls={limit} (attempted={current})"
        )


# ── Policy dataclasses ────────────────────────────────────────────────────────

@dataclass
class ModelPolicy:
    autonomous_mode: bool = False
    allowed_tasks: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    max_tool_calls: int = 0
    max_iterations: int = 1
    max_output_tokens: int = 4000


@dataclass
class AgentPolicy:
    allowed_tools: list[str] = field(default_factory=list)
    max_tool_calls: int = 20
    max_iterations: int = 5


# ── ToolPermissionChecker ─────────────────────────────────────────────────────

class ToolPermissionChecker:
    """
    Loads shared/configs/tool_permissions.yaml and enforces default-deny policy.
    Thread-safe. Config is immutable after __init__.
    """

    def __init__(self, config: dict[str, Any]):
        self._model_policies: dict[str, ModelPolicy] = {}
        self._agent_policies: dict[str, AgentPolicy] = {}
        self._parse(config)

    @classmethod
    def load(cls, path: Path | None = None) -> "ToolPermissionChecker":
        """Load config from YAML file. Requires pyyaml."""
        try:
            import yaml  # type: ignore[import]
        except ImportError as e:
            raise ImportError("pyyaml is required: pip install pyyaml") from e
        cfg_path = path or _CONFIG_PATH
        with open(cfg_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info("ToolPermissionChecker loaded from %s", cfg_path)
        return cls(config)

    def _parse(self, config: dict) -> None:
        for tier, raw in (config.get("models") or {}).items():
            self._model_policies[tier] = ModelPolicy(
                autonomous_mode=raw.get("autonomous_mode", False),
                allowed_tasks=raw.get("allowed_tasks") or [],
                allowed_tools=raw.get("allowed_tools") or [],
                max_tool_calls=raw.get("max_tool_calls", 0),
                max_iterations=raw.get("max_iterations", 1),
                max_output_tokens=raw.get("max_output_tokens", 4000),
            )
        for agent, raw in (config.get("agents") or {}).items():
            self._agent_policies[agent] = AgentPolicy(
                allowed_tools=raw.get("allowed_tools") or [],
                max_tool_calls=raw.get("max_tool_calls", 20),
                max_iterations=raw.get("max_iterations", 5),
            )

    # ── Public check methods ──────────────────────────────────────────────────

    def check_tool_allowed(
        self,
        tool: str,
        agent: str | None = None,
        model_tier: str | None = None,
    ) -> None:
        """
        Validate that `tool` is permitted for the given agent + model tier.
        Raises ToolDenied on violation.

        Intersection rule: tool must pass BOTH model-level AND agent-level check.
        Model "__all__" sentinel skips model-level check (agent list is the sole gate).
        """
        # Model-level
        if model_tier:
            mp = self._model_policies.get(model_tier)
            if mp is not None:
                if _ALLOW_ALL not in mp.allowed_tools and tool not in mp.allowed_tools:
                    raise ToolDenied(
                        tool, agent, model_tier,
                        reason=f"model tier '{model_tier}' does not permit tool '{tool}'",
                    )

        # Agent-level (default-deny: unknown agent → denied)
        if agent:
            ap = self._agent_policies.get(agent)
            if ap is None:
                raise ToolDenied(
                    tool, agent, model_tier,
                    reason=f"agent '{agent}' has no policy defined (default-deny)",
                )
            if _ALLOW_ALL not in ap.allowed_tools and tool not in ap.allowed_tools:
                raise ToolDenied(
                    tool, agent, model_tier,
                    reason=f"agent '{agent}' does not permit tool '{tool}'",
                )

    def check_task_allowed(self, model_tier: str, task_type: str) -> None:
        """
        Validate that a task type is permitted for the given model tier.
        Empty allowed_tasks list means no restriction (all tasks allowed for that tier).
        Raises ToolDenied on violation.
        """
        mp = self._model_policies.get(model_tier)
        if mp is None or not mp.allowed_tasks:
            return
        if task_type not in mp.allowed_tasks:
            raise ToolDenied(
                tool=task_type,
                agent=None,
                model_tier=model_tier,
                reason=(
                    f"task_type '{task_type}' not in allowed_tasks for model tier '{model_tier}'. "
                    f"Allowed: {mp.allowed_tasks}"
                ),
            )

    def get_max_iterations(self, agent: str | None, model_tier: str | None) -> int:
        """Return the most restrictive iteration limit across model + agent policies."""
        limits: list[int] = []
        if model_tier and model_tier in self._model_policies:
            limits.append(self._model_policies[model_tier].max_iterations)
        if agent and agent in self._agent_policies:
            limits.append(self._agent_policies[agent].max_iterations)
        return min(limits) if limits else 10

    def get_max_tool_calls(self, agent: str | None, model_tier: str | None) -> int:
        """Return the most restrictive tool call limit across model + agent policies."""
        limits: list[int] = []
        if model_tier and model_tier in self._model_policies:
            limits.append(self._model_policies[model_tier].max_tool_calls)
        if agent and agent in self._agent_policies:
            limits.append(self._agent_policies[agent].max_tool_calls)
        return min(limits) if limits else 50

    def model_policy(self, model_tier: str) -> ModelPolicy | None:
        return self._model_policies.get(model_tier)

    def agent_policy(self, agent: str) -> AgentPolicy | None:
        return self._agent_policies.get(agent)


# ── AgentBudget ───────────────────────────────────────────────────────────────

class AgentBudget:
    """
    Per-run budget tracker for a single agent invocation.
    Instantiate once per agent run; discard after the run completes.
    Thread-safe.

    Example:
        budget = AgentBudget("finance_bot", "cc", checker)
        budget.tick_iteration()          # LLM call about to happen
        output = gateway.complete(...)
        budget.use_tool("stock_api")     # external tool about to be called
        result = stock_api.fetch(...)
    """

    def __init__(self, agent: str, model_tier: str, checker: ToolPermissionChecker):
        self._agent = agent
        self._model_tier = model_tier
        self._checker = checker
        self._lock = threading.Lock()
        self._tool_calls = 0
        self._iterations = 0
        self._tools_used: list[str] = []
        self._max_tool_calls = checker.get_max_tool_calls(agent, model_tier)
        self._max_iterations = checker.get_max_iterations(agent, model_tier)

    def use_tool(self, tool: str) -> None:
        """Check permission, then increment the tool-call counter."""
        self._checker.check_tool_allowed(tool, self._agent, self._model_tier)
        with self._lock:
            self._tool_calls += 1
            if self._tool_calls > self._max_tool_calls:
                raise ToolCallLimitExceeded(
                    self._agent, self._max_tool_calls, self._tool_calls
                )
            self._tools_used.append(tool)
        logger.info(
            "tool_call agent=%s model=%s tool=%s count=%d/%d",
            self._agent, self._model_tier, tool,
            self._tool_calls, self._max_tool_calls,
        )

    def tick_iteration(self) -> None:
        """Record one LLM iteration. Raises IterationLimitExceeded on breach."""
        with self._lock:
            self._iterations += 1
            if self._iterations > self._max_iterations:
                raise IterationLimitExceeded(
                    self._agent, self._max_iterations, self._iterations
                )
        logger.debug(
            "iteration agent=%s iter=%d/%d",
            self._agent, self._iterations, self._max_iterations,
        )

    # ── Read-only stats ───────────────────────────────────────────────────────

    @property
    def tool_call_count(self) -> int:
        return self._tool_calls

    @property
    def iteration_count(self) -> int:
        return self._iterations

    @property
    def tools_used(self) -> list[str]:
        with self._lock:
            return list(self._tools_used)

    def summary(self) -> dict:
        with self._lock:
            return {
                "agent": self._agent,
                "model_tier": self._model_tier,
                "iterations": self._iterations,
                "max_iterations": self._max_iterations,
                "tool_calls": self._tool_calls,
                "max_tool_calls": self._max_tool_calls,
                "tools_used": list(self._tools_used),
            }
