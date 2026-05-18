"""Signal persistence and query tools."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.models import ToolContext, ToolResult
from core.state import data_path
from scoring import score_raw_signal
from signal_model import from_raw as signal_from_raw


def append_signal_jsonl(signal: dict[str, Any], ctx: ToolContext) -> None:
    p = data_path(ctx.root, ctx.config, "signal_log_path", "data/signal_log.jsonl")
    with p.open("a") as f:
        f.write(json.dumps(signal, default=str, ensure_ascii=False) + "\n")


def persist_signal(payload: dict, ctx: ToolContext) -> dict:
    signal = dict(payload.get("signal") or {})
    telegram_sent = bool(payload.get("telegram_sent", False))
    if "ts" not in signal and "timestamp" not in signal:
        signal["ts"] = datetime.now(timezone.utc).isoformat()
    append_signal_jsonl(signal, ctx)

    normalized = signal_from_raw(signal)
    if normalized.score is None:
        score, reason = score_raw_signal(signal, ctx.config)
        normalized.score = score
        normalized.reason = normalized.reason or reason
    signal_id = ctx.service("store").save_signal(normalized, telegram_sent=telegram_sent)
    return ToolResult(
        ok=True,
        tool="persist_signal",
        data={"id": signal_id, "telegram_sent": telegram_sent},
        signals=[signal],
    ).to_json()


def get_recent_signals(payload: dict, ctx: ToolContext) -> dict:
    limit = int(payload.get("limit", 50))
    rows = ctx.service("store").get_recent_signals(limit=limit)
    return ToolResult(ok=True, tool="get_recent_signals", data={"signals": rows}).to_json()


def get_signal_by_id(payload: dict, ctx: ToolContext) -> dict:
    signal_id = int(payload["signal_id"])
    row = ctx.service("store").get_signal_by_id(signal_id)
    return ToolResult(ok=row is not None, tool="get_signal_by_id", data={"signal": row}).to_json()


def get_score_summary(payload: dict, ctx: ToolContext) -> dict:
    return ToolResult(ok=True, tool="get_score_summary", data=ctx.service("store").get_score_summary()).to_json()
