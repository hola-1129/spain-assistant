"""
CC-EXCLUSIVE — do not modify without CC session + user confirmation.

Fallback chain for the Northstar SignalOS LLM layer.

Invariant: fallback always escalates UP the governance hierarchy.
  Qwen fails  → try CC
  Codex fails → try CC
  CC fails    → raise FallbackExhausted (never silently drop)
"""
from __future__ import annotations

import logging
from typing import Callable

from .interface import DraftOutput
from .model_router import ModelTier, TaskType

logger = logging.getLogger("signalos.llm.fallback")


class FallbackExhausted(RuntimeError):
    """Raised when all tiers in the fallback chain are exhausted."""


def with_fallback(
    primary_fn: Callable[[], DraftOutput],
    fallback_fn: Callable[[], DraftOutput] | None,
    task_type: TaskType,
    primary_tier: ModelTier,
) -> DraftOutput:
    """
    Call primary_fn. On failure, log and call fallback_fn if available.
    If fallback_fn is None (CC tier or rule tier), re-raises immediately.
    """
    try:
        return primary_fn()
    except Exception as primary_err:
        if fallback_fn is None:
            logger.critical(
                "LLM call failed with no fallback available. "
                "task=%s tier=%s error=%s",
                task_type.value, primary_tier.value, primary_err,
            )
            raise FallbackExhausted(
                f"No fallback for tier={primary_tier.value}, task={task_type.value}: {primary_err}"
            ) from primary_err

        logger.warning(
            "Primary LLM failed, escalating to fallback. "
            "task=%s primary_tier=%s error=%s",
            task_type.value, primary_tier.value, primary_err,
        )
        try:
            result = fallback_fn()
            result.metadata["fallback_from"] = primary_tier.value
            result.metadata["fallback_reason"] = str(primary_err)
            return result
        except Exception as fallback_err:
            logger.critical(
                "Fallback also failed. task=%s error=%s",
                task_type.value, fallback_err,
            )
            raise FallbackExhausted(
                f"Both primary ({primary_tier.value}) and fallback failed "
                f"for task={task_type.value}: {fallback_err}"
            ) from fallback_err
