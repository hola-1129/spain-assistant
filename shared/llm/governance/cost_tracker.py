"""
CC-EXCLUSIVE — do not modify without CC session + user confirmation.

Token cost estimation and daily aggregation for Northstar SignalOS.

Pricing is approximate (USD per 1K tokens) and for internal visibility only.
Update _PRICE_TABLE when model pricing changes.

Usage:
    from shared.llm.governance.cost_tracker import get_accumulator

    acc = get_accumulator()
    cost = acc.record(
        agent="finance_bot",
        model_id="qwen-plus",
        task_type="summarize_bulk",
        input_tokens=800,
        output_tokens=300,
        latency_ms=1250,
    )
    # → float (estimated USD)

    summary = acc.daily_summary()   # today's aggregated stats
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any

logger = logging.getLogger("signalos.llm.cost")

# ── Pricing table: (input_per_1k_usd, output_per_1k_usd) ─────────────────────
# Updated by CC. Values approximate public pricing as of 2026-05.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6":    (0.003,    0.015),
    "claude-opus-4-7":      (0.015,    0.075),
    "claude-haiku-4-5":     (0.0008,   0.004),
    "qwen-plus":            (0.0004,   0.0012),
    "qwen-max":             (0.0024,   0.0072),
    "qwen-turbo":           (0.00005,  0.0002),
    "codex-mini-latest":    (0.0015,   0.006),
    "gpt-4o":               (0.005,    0.015),
    "gpt-4o-mini":          (0.00015,  0.0006),
    # OpenRouter pass-through (includes ~10% markup estimate)
    "qwen/qwen-plus":       (0.00044,  0.00132),
}

_DEFAULT_PRICE = (0.002, 0.008)  # Unknown model: conservative fallback

_COST_LOG_PATH = Path("/Volumes/AI_DISK/ai_workspace/logs/llm_audit/cost_log.jsonl")


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for one LLM call. Returns 0.0 if both counts are 0."""
    if input_tokens == 0 and output_tokens == 0:
        return 0.0
    in_p, out_p = _PRICE_TABLE.get(model_id, _DEFAULT_PRICE)
    return round((input_tokens / 1000.0) * in_p + (output_tokens / 1000.0) * out_p, 8)


# ── CostAccumulator ───────────────────────────────────────────────────────────

class CostAccumulator:
    """
    Thread-safe per-day cost aggregator.
    Appends JSONL records to cost_log.jsonl; builds in-memory daily totals.
    """

    def __init__(self, path: Path = _COST_LOG_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # date_str → {total_cost_usd, total_calls, by_model, by_agent, ...}
        self._daily: dict[str, dict[str, Any]] = {}

    def record(
        self,
        agent: str,
        model_id: str,
        task_type: str,
        input_tokens: int,
        output_tokens: int,
        tool_calls: int = 0,
        latency_ms: float = 0.0,
        retries: int = 0,
    ) -> float:
        """Append a call record and return the estimated USD cost."""
        cost = estimate_cost(model_id, input_tokens, output_tokens)
        ts = datetime.now(timezone.utc).isoformat()
        date_str = ts[:10]
        entry = {
            "ts":            ts,
            "agent":         agent,
            "model_id":      model_id,
            "task_type":     task_type,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "tool_calls":    tool_calls,
            "latency_ms":    round(latency_ms, 1),
            "cost_usd":      cost,
            "retries":       retries,
        }
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._update_daily(date_str, agent, model_id, input_tokens, output_tokens, cost, tool_calls)
        return cost

    def _update_daily(
        self,
        date_str: str,
        agent: str,
        model_id: str,
        in_tok: int,
        out_tok: int,
        cost: float,
        tool_calls: int,
    ) -> None:
        day = self._daily.setdefault(date_str, {
            "total_cost_usd":      0.0,
            "total_calls":         0,
            "total_input_tokens":  0,
            "total_output_tokens": 0,
            "total_tool_calls":    0,
            "by_model":            {},
            "by_agent":            {},
        })
        day["total_cost_usd"]      += cost
        day["total_calls"]         += 1
        day["total_input_tokens"]  += in_tok
        day["total_output_tokens"] += out_tok
        day["total_tool_calls"]    += tool_calls

        for bucket, key in ((day["by_model"], model_id), (day["by_agent"], agent)):
            e = bucket.setdefault(key, {
                "calls":         0,
                "cost_usd":      0.0,
                "input_tokens":  0,
                "output_tokens": 0,
            })
            e["calls"]         += 1
            e["cost_usd"]      += cost
            e["input_tokens"]  += in_tok
            e["output_tokens"] += out_tok

    def daily_summary(self, date_str: str | None = None) -> dict[str, Any]:
        """Return aggregated totals for a date (default: today UTC)."""
        if date_str is None:
            date_str = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            return dict(self._daily.get(date_str, {}))

    def load_from_log(self, date_str: str | None = None) -> dict[str, Any]:
        """
        Rebuild daily summary by replaying cost_log.jsonl.
        Use this when the process restarts and in-memory state is lost.
        """
        target = date_str or datetime.now(timezone.utc).date().isoformat()
        if not self._path.exists():
            return {}
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("ts", "")[:10] == target:
                        self._update_daily(
                            target,
                            rec.get("agent", "unknown"),
                            rec.get("model_id", "unknown"),
                            rec.get("input_tokens", 0),
                            rec.get("output_tokens", 0),
                            rec.get("cost_usd", 0.0),
                            rec.get("tool_calls", 0),
                        )
            return dict(self._daily.get(target, {}))


# ── Module-level singleton ────────────────────────────────────────────────────

_default_accumulator: CostAccumulator | None = None
_acc_lock = threading.Lock()


def get_accumulator() -> CostAccumulator:
    """Return the module-level shared accumulator (created on first call)."""
    global _default_accumulator
    with _acc_lock:
        if _default_accumulator is None:
            _default_accumulator = CostAccumulator()
        return _default_accumulator
