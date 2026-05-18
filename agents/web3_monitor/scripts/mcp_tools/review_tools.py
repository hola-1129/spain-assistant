"""Review and backtest tools."""
from __future__ import annotations

from core.models import ToolContext, ToolResult


def get_review_summary(payload: dict, ctx: ToolContext) -> dict:
    return ToolResult(ok=True, tool="get_review_summary", data=ctx.service("store").get_score_summary()).to_json()
