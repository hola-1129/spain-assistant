"""Registry of MCP-ready tool functions.

An MCP server can import this module and expose each function in TOOL_REGISTRY.
Every tool accepts (payload: dict, ctx: ToolContext) and returns a JSON-style dict.
"""
from __future__ import annotations

from mcp_tools.market_tools import (
    get_macro_snapshot,
    scan_dex_anomalies,
    scan_market_movers,
    scan_new_pools,
    scan_prediction_markets,
)
from mcp_tools.notify_tools import send_telegram_alert
from mcp_tools.review_tools import get_review_summary
from mcp_tools.signal_tools import get_recent_signals, get_score_summary, get_signal_by_id, persist_signal


TOOL_REGISTRY = {
    "scan_dex_anomalies": scan_dex_anomalies,
    "scan_market_movers": scan_market_movers,
    "scan_new_pools": scan_new_pools,
    "get_macro_snapshot": get_macro_snapshot,
    "scan_prediction_markets": scan_prediction_markets,
    "persist_signal": persist_signal,
    "get_recent_signals": get_recent_signals,
    "get_signal_by_id": get_signal_by_id,
    "get_score_summary": get_score_summary,
    "get_review_summary": get_review_summary,
    "send_telegram_alert": send_telegram_alert,
}


def list_tools() -> dict:
    return {
        "ok": True,
        "tools": sorted(TOOL_REGISTRY),
        "contract": "tool(payload: dict, ctx: ToolContext) -> JSON dict",
    }
