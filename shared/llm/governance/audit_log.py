"""
Append-only audit log for all LLM outputs in Northstar SignalOS.

Every model call (success or failure) is recorded with:
  - timestamp, task_type, tier, model_id, agent
  - actual input/output token counts (from provider response)
  - latency_ms, retries
  - gate result and rejection reason
  - tool_calls count
  - estimated cost (USD)

Log format: JSONL, one entry per line.
Default path: ai_workspace/logs/llm_audit/audit.jsonl
Rotation: handled externally (logrotate or scheduled cleanup).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.llm.interface import DraftOutput
from shared.llm.model_router import ModelTier, TaskType

logger = logging.getLogger("signalos.llm.audit")

_DEFAULT_AUDIT_PATH = Path("/Volumes/AI_DISK/ai_workspace/logs/llm_audit/audit.jsonl")


class AuditLog:
    def __init__(self, path: Path = _DEFAULT_AUDIT_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record_call(
        self,
        task_type: TaskType,
        tier: ModelTier,
        model_id: str,
        draft: DraftOutput | None,
        gate_passed: bool | None,
        rejection_rule: str | None = None,
        # ── New observability fields ──────────────────────────────────────────
        agent: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: float | None = None,
        tool_calls: int | None = None,
        cost_usd: float | None = None,
        retries: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        # Prefer explicit token counts; fall back to draft.metadata; then char estimate.
        in_tok  = input_tokens  if input_tokens  is not None else (draft.metadata.get("input_tokens",  0) if draft else 0)
        out_tok = output_tokens if output_tokens is not None else (draft.metadata.get("output_tokens", 0) if draft else 0)
        attempt = draft.metadata.get("attempt", 1) if draft else 1

        entry: dict[str, Any] = {
            "ts":             datetime.now(timezone.utc).isoformat(),
            "task_type":      task_type.value,
            "tier":           tier.value,
            "model_id":       model_id,
            "agent":          agent,
            "source":         draft.source if draft else None,
            "input_tokens":   in_tok,
            "output_tokens":  out_tok,
            "output_chars":   len(draft.text) if draft else 0,
            "latency_ms":     round(latency_ms, 1) if latency_ms is not None else None,
            "tool_calls":     tool_calls if tool_calls is not None else 0,
            "cost_usd":       cost_usd,
            "retries":        (attempt - 1) if retries is None else retries,
            "gate_passed":    gate_passed,
            "rejection_rule": rejection_rule,
        }
        if draft and draft.metadata.get("fallback_from"):
            entry["fallback_from"] = draft.metadata["fallback_from"]
        if extra:
            entry.update(extra)

        self._append(entry)

    def record_error(
        self,
        task_type: TaskType,
        tier: ModelTier,
        model_id: str,
        error: str,
        agent: str | None = None,
        latency_ms: float | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts":          datetime.now(timezone.utc).isoformat(),
            "task_type":   task_type.value,
            "tier":        tier.value,
            "model_id":    model_id,
            "agent":       agent,
            "error":       error,
            "latency_ms":  round(latency_ms, 1) if latency_ms is not None else None,
            "gate_passed": None,
        }
        self._append(entry)
        logger.error(
            "LLM call error logged. task=%s tier=%s agent=%s error=%s",
            task_type.value, tier.value, agent, error,
        )

    def _append(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
