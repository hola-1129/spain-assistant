"""Public tool facade for Dashboard, Codex, and future MCP server.

This module keeps a simple Python API while routing through the MCP-ready
registry contract: tool(payload: dict, ctx: ToolContext) -> JSON dict.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from agent_orchestrator import Web3MonitorAgent
from mcp_tool_registry import TOOL_REGISTRY, list_tools

ROOT = _HERE.parent


def _ctx():
    return Web3MonitorAgent(ROOT).ctx


def call_tool(name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if name not in TOOL_REGISTRY:
        return {"ok": False, "tool": name, "errors": [f"unknown tool: {name}"], "data": {}, "signals": [], "meta": {}}
    return TOOL_REGISTRY[name](payload or {}, _ctx())


def get_recent_signals(limit: int = 50) -> list[dict[str, Any]]:
    return call_tool("get_recent_signals", {"limit": limit})["data"]["signals"]


def get_signal_by_id(signal_id: int) -> dict[str, Any] | None:
    return call_tool("get_signal_by_id", {"signal_id": signal_id})["data"]["signal"]


def get_score_summary() -> dict[str, Any]:
    return call_tool("get_score_summary")["data"]


def send_telegram_alert(text: str) -> bool:
    return bool(call_tool("send_telegram_alert", {"text": text}).get("ok"))


def run_monitor_once() -> int:
    Web3MonitorAgent(ROOT).run_once()
    return 0
